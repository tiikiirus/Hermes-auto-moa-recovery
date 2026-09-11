"""Repair — byte_integrity zone only, consumes a Report (R1).

Contract (auditor R1/1-3):
  RepairResult distinguishes three outcomes, not a bool:
    repaired — finding was acted on and is expected to disappear on next verify
    skipped  — finding was intentionally not touched (untracked noise, fleet)
    refused  — finding cannot be repaired here (patch_drift requiring re-export,
               missing file for stale_seal)

  repair(report, repo, live) iterates all findings independently:
    - mixed Report with stale + untracked + fleet must repair the repairable
      subset and skip/refuse the rest, not fail on the first unrepairable.
    - if a Report contains both stale_seal and patch_drift, stale is still
      repaired and patch_drift goes to refused — partial success, not all-or-nothing
      (ADR: "refuses only if patch physically does not apply").

  Watchdog log N->M is built directly from RepairResult, not by re-running
  verify() and diffing. Idempotence (R5) and fleet no-op (R6) are tested from
  this contract.

This module is read-only except for the explicit reseal / git checkout paths
for stale_seal and tracked live_tree_noise. It never touches fleet zone.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # noqa: E402

from recovery_integrity import Finding, Report, fresh_bytes, git  # noqa: E402

# Fleet flavours — repair must no-op on them (R6)
FLEET_FLAVOURS = {"registry_vs_canon_mismatch", "fleet_drift", "lab_has_moa", "fleet_check_error"}


@dataclass(frozen=True)
class RepairResult:
    repaired: Tuple[Finding, ...] = ()
    skipped: Tuple[Finding, ...] = ()
    refused: Tuple[Finding, ...] = ()

    @property
    def any_refused(self) -> bool:
        return bool(self.refused)

    @property
    def summary(self) -> str:
        return f"repaired={len(self.repaired)} skipped={len(self.skipped)} refused={len(self.refused)}"


def _reseal_one(repo: Path, rel: str) -> bool:
    """Reseal one sealed file by fresh_bytes. Returns True on success."""
    target = repo / rel
    if not target.exists():
        return False
    # Recompute fresh digest and upsert ledger line (same logic as test helper seal())
    import hashlib

    try:
        digest = hashlib.sha256(fresh_bytes(target, repo)).hexdigest()
    except Exception:
        return False
    ledger = repo / "SHA256SUMS.txt"
    line = f"{digest} *{rel}\n"
    try:
        if not ledger.exists():
            ledger.write_text(line, encoding="utf-8", newline="\n")
            return True
        existing = ledger.read_text(encoding="utf-8").splitlines()
        out: list[str] = []
        found = False
        for raw in existing:
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                out.append(raw)
                continue
            _hex, _, name = stripped.partition(" ")
            name = name.lstrip("*").strip()
            if name == rel:
                out.append(line.rstrip("\n"))
                found = True
            else:
                out.append(raw)
        if not found:
            out.append(line.rstrip("\n"))
        newline = "\r\n" if b"\r\n" in ledger.read_bytes() else "\n"
        ledger.write_text("\n".join(out) + "\n", encoding="utf-8", newline=newline)
        return True
    except Exception:
        return False


def repair(report: Report, repo: Path, live: Path, patch: Path | None = None) -> RepairResult:
    """Apply repair for the byte_integrity findings in report.

    Pure dispatcher: each finding is handled independently, never aborts the
    loop on a single failure. Fleet findings are skipped, patch_drift is
    refused (requires re-export), stale_seal is resealed, tracked live_tree_noise
    is reverted via git checkout, untracked is skipped.
    """
    repo = Path(repo)
    live = Path(live)
    repaired: list[Finding] = []
    skipped: list[Finding] = []
    refused: list[Finding] = []

    for f in report.findings:
        try:
            # R6: fleet zone is never touched here
            if f.flavour in FLEET_FLAVOURS:
                skipped.append(f)
                continue

            if f.flavour == "stale_seal":
                # f.path is the sealed rel path
                rel = f.path or ""
                if not rel:
                    refused.append(f)
                    continue
                target = repo / rel
                if not target.exists():
                    # R2 edge: file deleted after stale was reported
                    refused.append(f)
                    continue
                ok = _reseal_one(repo, rel)
                (repaired if ok else refused).append(f)
                continue

            if f.flavour == "missing_seal":
                # No file to reseal from — refuse, surface distinctly
                refused.append(f)
                continue

            if f.flavour == "checkout_unstable":
                # EOL hazard: reseal alone won't fix (fresh != raw but seal already matches fresh)
                # Repair would need to normalize the working-tree bytes, which is out of scope
                # for the reseal path — treat as refused for now (future: normalize file).
                refused.append(f)
                continue

            if f.flavour == "live_tree_noise":
                # Distinguish tracked vs untracked via detail prefix (as produced by verify)
                detail = (f.detail or "").lower()
                is_untracked = "untracked" in detail
                is_tracked = "tracked" in detail
                # R3: untracked is never auto-deleted
                if is_untracked:
                    skipped.append(f)
                    continue
                if is_tracked:
                    # Tracked noise outside scope — revert via git checkout
                    rel = f.path or ""
                    if not rel:
                        refused.append(f)
                        continue
                    # Only revert if file is actually tracked (git checkout will fail otherwise)
                    res = git("checkout", "--", rel, cwd=live)
                    if res.rc == 0:
                        repaired.append(f)
                    else:
                        refused.append(f)
                    continue
                # Unknown detail shape — be conservative and skip
                skipped.append(f)
                continue

            if f.flavour == "patch_drift":
                # R4: only refusal — requires re-export of the patch, not auto-fix
                refused.append(f)
                continue

            # Unknown flavour — skip, do not block other findings
            skipped.append(f)
        except Exception:
            # Never let one finding's exception abort the whole repair
            refused.append(f)

    return RepairResult(tuple(repaired), tuple(skipped), tuple(refused))
