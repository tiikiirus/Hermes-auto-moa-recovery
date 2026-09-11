"""Read-only verifier for recovery integrity — Task 1: git seam + Report.

This is Step 1 of docs/superpowers/plans/2026-09-11-recovery-integrity-step1.md.
Task 1 delivers ONLY the git seam, the Report/Finding types and a pure
verify() that returns an empty report. No file is written, no patch is
applied. Later tasks add paths()/sealed()/fresh_bytes() and the three
drift checks.

Every tool in this repo does sys.stdout.reconfigure(encoding="utf-8")
because the Windows console is cp1251/cp866 and would otherwise raise on
non-ASCII.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # noqa: E402

# ── git seam ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GitResult:
    rc: int
    stdout: str = ""
    stderr: str = ""


def git(*args: str, cwd: Path | None = None) -> GitResult:
    """Single seam to git. Never raises — rc carries the signal."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        return GitResult(rc=127, stderr=str(exc))
    return GitResult(proc.returncode, proc.stdout, proc.stderr)


# ── Findings / Report ─────────────────────────────────────────────────


@dataclass(frozen=True)
class Finding:
    flavour: str
    severity: str
    path: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class Report:
    findings: Tuple[Finding, ...] = ()

    @property
    def blocked(self) -> bool:
        return any(f.severity == "block" for f in self.findings)

    def exit_code(self) -> int:
        return 1 if self.blocked else 0


# ── sealed ledger + fresh_bytes — Task 3 ───────────────────────────

from dataclasses import dataclass as _dc2  # noqa: F811

@dataclass(frozen=True)
class Seal:
    path: str
    digest: str


def sealed(repo: Path) -> list[Seal]:
    """Parse SHA256SUMS.txt with universal newlines (CRLF-safe)."""
    ledger = Path(repo) / "SHA256SUMS.txt"
    if not ledger.exists():
        return []
    out: list[Seal] = []
    # universal newlines: splitlines() drops \r, so a CRLF ledger reads clean.
    for raw in ledger.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # format: "<hex> *<path>"  — digest, space, mode char, path
        # Use partition on space; the path part may start with *.
        hex_part, _, rest = line.partition(" ")
        hex_part = hex_part.strip()
        path = rest.lstrip(" *").strip()
        # \r must never remain in path (CRLF hazard)
        path = path.replace("\r", "")
        if len(hex_part) == 64 and path:
            out.append(Seal(path=path, digest=hex_part.lower()))
    return out


def fresh_bytes(path: Path, repo: Path) -> bytes:
    """Bytes a fresh checkout would produce for *path*.

    Single source for the seal unit: what a clone sees, not what is on disk
    now. Handles the eol normalisation hazard that already happened once:
    a file with LF on disk and no .gitattributes entry becomes CRLF in a
    clone when core.autocrlf=true, so its seal would be stale even though
    it looks fresh locally.

    Git is the oracle: ask check-attr for text/eol. If the file is declared
    text (set/auto) or eol==lf, git normalises CRLF->LF on checkout, so
    fresh is LF. Otherwise, if core.autocrlf true and the file looks like
    text, git converts LF->CRLF on checkout.
    """
    raw = Path(path).read_bytes()
    try:
        rel = Path(path).relative_to(Path(repo))
    except ValueError:
        return raw
    rel_posix = rel.as_posix()
    res = git("check-attr", "text", "eol", "--", rel_posix, cwd=repo)
    if res.rc != 0:
        # git unavailable — fail-open, return raw; caller may add a warn finding
        return raw
    text_val: str | None = None
    eol_val: str | None = None
    for line in res.stdout.splitlines():
        # format: "rel: text: set"  or "rel: eol: lf"
        if ": text:" in line:
            text_val = line.rsplit(":", 1)[-1].strip()
        elif ": eol:" in line:
            eol_val = line.rsplit(":", 1)[-1].strip()
    # Declared text or lf -> checkout is LF-normalised (as plan specifies)
    if text_val in ("set", "auto") or eol_val == "lf":
        return raw.replace(b"\r\n", b"\n")
    # Undeclared: respect core.autocrlf for text files, but -text (text: unset)
    # means binary / no conversion, even if autocrlf is set.
    # git check-attr for -text returns "text: unset".
    if text_val == "unset":
        return raw
    cfg = git("config", "--get", "core.autocrlf", cwd=repo)
    autocrlf = cfg.stdout.strip().lower() if cfg.rc == 0 else ""
    if autocrlf == "input" and b"\x00" not in raw:
        # input: normalise CRLF->LF on commit, checkout leaves LF
        return raw.replace(b"\r\n", b"\n")
    if autocrlf == "true" and b"\x00" not in raw and b"\n" in raw:
        # Text file with LF on disk will be checked out as CRLF
        if b"\r\n" not in raw:
            return raw.replace(b"\n", b"\r\n")
    return raw


def _verify_seals(repo: Path) -> list[Finding]:
    findings: list[Finding] = []
    for seal in sealed(repo):
        target = Path(repo) / seal.path
        if not target.exists():
            findings.append(Finding("missing_seal", "block", seal.path, f"sealed file missing: {seal.path}"))
            continue
        raw = target.read_bytes()
        fresh = fresh_bytes(target, repo)
        # stale: seal digest vs fresh
        fresh_digest = hashlib.sha256(fresh).hexdigest()
        if fresh_digest != seal.digest:
            findings.append(
                Finding(
                    "stale_seal",
                    "block",
                    seal.path,
                    f"seal {seal.digest[:8]}.. != fresh {fresh_digest[:8]}..",
                )
            )
            continue
        # checkout_unstable: fresh vs raw
        if fresh != raw:
            findings.append(
                Finding(
                    "checkout_unstable",
                    "block",
                    seal.path,
                    f"bytes on disk differ from fresh checkout (eol normalisation hazard)",
                )
            )
    return findings


# ── live-tree noise — Task 4 (port of live_tree_check) ────────────

def _live_status(live: Path) -> list[tuple[str, str]]:
    # --untracked-files=all ensures a directory like hermes_cli/ is expanded to
    # individual files, otherwise an allowed file inside an untracked dir would
    # be reported as noise for the directory name.
    res = git("status", "--porcelain", "--untracked-files=all", cwd=live)
    if res.rc != 0:
        return []  # not a git worktree — caller will surface separately if needed
    rows: list[tuple[str, str]] = []
    for line in res.stdout.splitlines():
        if len(line) < 4:
            continue
        # porcelain: XY<space>path  (path may be quoted)
        st = line[:2]
        path = line[3:].strip().strip('"')
        # Handle renames: "R  old -> new" — take the destination
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[-1].strip().strip('"')
        rows.append((st, path))
    return rows


def _verify_live_tree_noise(live: Path) -> list[Finding]:
    live = Path(live)
    if not (live / ".git").exists() and not git("rev-parse", "--git-dir", cwd=live).stdout.strip():
        return []  # not a live tree — no noise to report here
    allowed = set(paths())
    findings: list[Finding] = []
    for st, path in _live_status(live):
        if path in allowed:
            continue
        # Noise inside the 9 is not noise (the patch owns those files)
        if st == "??":
            findings.append(
                Finding(
                    "live_tree_noise",
                    "block",
                    path,
                    f"untracked noise: {path} (kept, manual review needed)",
                )
            )
        else:
            findings.append(
                Finding(
                    "live_tree_noise",
                    "block",
                    path,
                    f"tracked noise: {st} {path}",
                )
            )
    return findings


# ── patch applicability — Task 5 ─────────────────────────────────────

def _verify_patch(repo: Path, live: Path, patch: Path | None = None) -> list[Finding]:
    repo = Path(repo)
    live = Path(live)
    if patch is None:
        patch = repo / "auto-moa-current.patch"
    patch = Path(patch)
    if not patch.exists():
        return []
    try:
        if patch.stat().st_size == 0 or not patch.read_text(encoding="utf-8", errors="ignore").strip():
            return []
    except Exception:
        return []
    # Pure --check: never writes, never applies, even with fuzz warnings
    # git apply may succeed with warnings (e.g. fuzzy); we treat any
    # non-zero rc as drift, and also surface stderr as detail.
    # Prefixes a/b are the default -p1; cwd must be the live tree root.
    res = git("apply", "--reverse", "--check", str(patch), cwd=live)
    if res.rc != 0:
        detail = (res.stderr or res.stdout).strip()[:500]
        # Detect fuzzy warning even when rc==0 would be caught above; if git
        # ever warns but returns 0, the stderr still contains "warning:" — we
        # treat that as drift in a stricter follow-up, but for Task 5 the
        # contract is rc-based. Keep the detail for the report.
        return [
            Finding(
                "patch_drift",
                "block",
                str(patch),
                f"patch no longer reverse-applies: {detail}" if detail else "patch no longer reverse-applies",
            )
        ]
    # Stricter: if git warned about fuzz but still returned 0, the patch
    # technically applied but with offset — treat as drift as well.
    warn = (res.stderr or res.stdout).lower()
    if "warning:" in warn and "fuzz" in warn:
        return [
            Finding(
                "patch_drift",
                "block",
                str(patch),
                f"patch applies only with fuzz: {(res.stderr or res.stdout).strip()[:500]}",
            )
        ]
    return []


# ── verify — Tasks 1-5 combined (pure read-only) ─────────────────────

def verify(repo: Path, live: Path, patch: Path | None = None) -> Report:
    """Pure read-only verifier — Tasks 1-5.

    No file is written, no patch is applied (--check only). The invariants
    test_verify_writes_nothing / test_cross_check_writes_nothing pin this.
    """
    findings: list[Finding] = []
    findings.extend(_verify_seals(Path(repo)))
    findings.extend(_verify_live_tree_noise(Path(live)))
    findings.extend(_verify_patch(Path(repo), Path(live), patch))
    return Report(tuple(findings))


# ── test helper: seal() — NOT part of the public Step 1 surface ──────

def seal(repo: Path, rel: str) -> None:
    """Write/update one ledger line for *rel* (test helper).

    Computes sha256 of the *fresh* bytes (what a clone would see) and
    upserts ``<hex> *<rel>`` into SHA256SUMS.txt. The seal unit is the
    bytes a fresh checkout produces, not the bytes currently on disk —
    otherwise a file with LF on disk and no eol declaration would look
    fresh locally (LF) but be CRLF in a clone and the seal would be
    stale. Used only by tools/tests/test_recovery_integrity.py fixtures.
    """
    repo = Path(repo)
    target = repo / rel
    digest = hashlib.sha256(fresh_bytes(target, repo)).hexdigest()
    ledger = repo / "SHA256SUMS.txt"
    line = f"{digest} *{rel}\n"
    if not ledger.exists():
        ledger.write_text(line, encoding="utf-8", newline="\n")
        return
    # Preserve CRLF ledger as-is — read with universal newlines.
    existing = ledger.read_text(encoding="utf-8").splitlines()
    found = False
    out: list[str] = []
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
    # Keep ledger's own newline style (recovery repo uses CRLF for it,
    # but test temp repos use LF — honour what was there).
    newline = "\r\n" if b"\r\n" in ledger.read_bytes() else "\n"
    ledger.write_text("\n".join(out) + "\n", encoding="utf-8", newline=newline)


# ── patch scope — single source of truth (Task 2) ───────────────────

_PATCH_SCOPE: tuple[str, ...] = (
    "agent/moa_loop.py",
    "agent/moa_trace.py",
    "agent/turn_request_assembly.py",
    "hermes_cli/moa_cmd.py",
    "hermes_cli/moa_config.py",
    "agent/moa_auto_router.py",
    "tests/agent/test_moa_auto_router.py",
    "tests/agent/test_moa_auto_runtime.py",
    "tests/hermes_cli/test_moa_cmd_auto.py",
)


def paths() -> tuple[str, ...]:
    """Nine live-tree paths the recovery patch touches — single declaration.

    Order follows the patch header order; the set is what live_tree_check
    allowlists. Temporary bridge to live_tree_check is verified by
    test_scope_matches_live_tree_check_allowlist.
    """
    return _PATCH_SCOPE


def _allowlist_from_source(source: str) -> set[str]:
    """Extract ALLOWLIST literals from live_tree_check.py source.

    Parses the ``ALLOWLIST = { ... }`` assignment via AST so refactors that
    move the block do not silently desync the two scopes. Temporary helper
    — deleted with tools/live_tree_check.py in Step 2.
    """
    import ast

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "ALLOWLIST":
                    val = node.value
                    if isinstance(val, ast.Set):
                        out: set[str] = set()
                        for elt in val.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                out.add(elt.value)
                        return out
                    if isinstance(val, ast.Dict):  # pragma: no cover — defensive
                        return {
                            k.value
                            for k in val.keys
                            if isinstance(k, ast.Constant) and isinstance(k.value, str)
                        }
    return set()


# ── CLI — Task 6 (read-only, no --fix) ─────────────────────────────

def _human_report(report: Report) -> str:
    if not report.findings:
        return "OK — no blocking drift"
    lines: list[str] = []
    # Group by flavour for scanability
    from collections import Counter

    by_flavour: dict[str, list[Finding]] = {}
    for f in report.findings:
        by_flavour.setdefault(f.flavour, []).append(f)
    for flavour in sorted(by_flavour):
        for f in by_flavour[flavour]:
            sev = f.severity.upper()
            path = f" {f.path}" if f.path else ""
            detail = f" — {f.detail}" if f.detail else ""
            lines.append(f"[{sev}] {flavour}{path}{detail}")
    lines.append(f"blocked={report.blocked} exit={report.exit_code()}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry — read-only verifier.

    Exit codes:
      0 — no blocking findings (warn-only is 0, see test_cli_exit_code_warn_only_is_zero)
      1 — at least one block finding
      2 — verifier itself failed (bad args, missing repo, exception)
    """
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Read-only recovery integrity verifier (Task 6)")
    parser.add_argument("--repo", type=Path, default=repo_root(), help="recovery repo root")
    parser.add_argument("--live", type=Path, default=live_tree(), help="live hermes-agent checkout")
    parser.add_argument("--json", action="store_true", help="emit stable JSON (versioned schema)")
    args = parser.parse_args(argv)

    try:
        repo = Path(args.repo)
        live = Path(args.live)
        # Missing repo/live is a verifier error (exit 2), not a drift finding.
        if not repo.exists():
            print(f"error: repo not found: {repo}", file=sys.stderr)
            return 2
        if not live.exists():
            print(f"error: live tree not found: {live}", file=sys.stderr)
            return 2
        report = verify(repo, live)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"error: verifier failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        payload = {
            "version": 1,
            "findings": [
                {"flavour": f.flavour, "severity": f.severity, "path": f.path, "detail": f.detail}
                for f in report.findings
            ],
            "blocked": report.blocked,
            "exit_code": report.exit_code(),
        }
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(_human_report(report) + "\n")
    return report.exit_code()


# ── minimal repo/live resolvers — Task 1 stub, real impl in Task 7 ───

def repo_root() -> Path:  # pragma: no cover
    return Path(__file__).resolve().parent.parent


def live_tree() -> Path:  # pragma: no cover
    import os

    return Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "hermes-agent"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
