"""R4/R5: patch_drift re-export + idempotence (restore->verify->repair->verify).

Two стык tests:
  - fuzzy restore -> drift  (offset/fuzzy patch must not be silent)
  - refused plateau          (repair on patch_drift stays refused, no state churn)

Plus idempotence of the full cycle for the byte_integrity zone.

Run:  <hermes venv>/python.exe -m pytest tools/tests/test_patch_reexport.py -q
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

TOOLS_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))

import recovery_integrity as ri  # noqa: E402
from repair import repair  # noqa: E402


def _git(cwd: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def make_live_long(tmp_path: pathlib.Path) -> pathlib.Path:
    """Live repo with a long file so a patch hunk is not at line 1."""
    live = tmp_path / "live"
    live.mkdir(parents=True, exist_ok=True)
    if not (live / ".git").exists():
        _git(live, "init", "-q")
        _git(live, "config", "user.email", "a@a.invalid")
        _git(live, "config", "user.name", "a")
        _git(live, "config", "core.autocrlf", "false")
        (live / "agent").mkdir(parents=True, exist_ok=True)
        # 20 lines, so hunk at line 7 is mid-file
        lines = [f"line{i}" for i in range(1, 21)]
        (live / "agent" / "moa_loop.py").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        _git(live, "add", "-A")
        _git(live, "commit", "-qm", "baseline long")
    return live


def make_recovery(tmp_path: pathlib.Path) -> pathlib.Path:
    repo = tmp_path / "recovery"
    (repo / "tools").mkdir(parents=True, exist_ok=True)
    (repo / "tools" / "sealed_tool.py").write_text("print('hi')\n", encoding="utf-8", newline="\n")
    (repo / ".gitattributes").write_text("tools/sealed_tool.py text eol=lf\n", encoding="utf-8", newline="\n")
    # also need git init for fresh_bytes check-attr to work
    if not (repo / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "a@a.invalid"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "a"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=repo, capture_output=True, check=True)
    ri.seal(repo, "tools/sealed_tool.py")
    (repo / "auto-moa-current.patch").write_text("", encoding="utf-8")
    return repo


def _patch_for_long(live: pathlib.Path) -> pathlib.Path:
    """Patch that changes line10 in the long file."""
    f = live / "agent" / "moa_loop.py"
    lines = [f"line{i}" for i in range(1, 21)]
    lines[9] = "line10 CHANGED"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    diff = _git(live, "diff", "--", "agent/moa_loop.py").stdout
    # restore baseline
    lines[9] = "line10"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    out = live.parent / "auto-moa-current.patch"
    out.write_text(diff, encoding="utf-8", newline="\n")
    return out


# ── R4: fuzzy / offset restore must be reported as drift ────────────────


def test_fuzzy_restore_reports_drift(tmp_path):
    """A patch that reverse-applies with offset must still be drift.

    The hunk is mid-file (line 7), so inserting a line at the top shifts
    the hunk by 1.  git apply succeeds with 'offset 1 line' but the live
    diff is no longer byte-identical to the stored patch.  verify() must
    report patch_drift (R4), not silent success.
    """
    live = make_live_long(tmp_path)
    repo = make_recovery(tmp_path)
    patch = _patch_for_long(live)
    # Apply patch fully (so live is patched and verify is clean)
    _git(live, "apply", str(patch))
    assert ri.verify(repo, live, patch=patch).findings == (), "patched live must be clean"
    # Now cause offset: insert a line at the very top (far from hunk)
    f = live / "agent" / "moa_loop.py"
    content = f.read_text(encoding="utf-8")
    f.write_text("INSERTED_AT_TOP\n" + content, encoding="utf-8", newline="\n")
    report = ri.verify(repo, live, patch=patch)
    assert any(fl.flavour == "patch_drift" for fl in report.findings), (
        f"offset live must be drift, got {report.findings} ; patch still reverse-applies with offset but diff differs"
    )
    assert report.blocked
    # Re-export must heal it: fresh diff should now equal re-exported patch
    exported = ri.export_patch(live, repo, patch)
    assert exported == patch
    # After re-export, the same live (with insertion) is now the source of truth,
    # so verify with the new patch must be clean.
    report2 = ri.verify(repo, live, patch=patch)
    assert report2.findings == (), f"after re-export, drift must disappear, got {report2.findings}"


def test_fuzzy_restore_reverse_check_with_offset_is_drift(tmp_path):
    """Direct check that git offset success is still considered drift by verify."""
    live = make_live_long(tmp_path)
    repo = make_recovery(tmp_path)
    patch = _patch_for_long(live)
    _git(live, "apply", str(patch))
    f = live / "agent" / "moa_loop.py"
    f.write_text("PREPEND\n" + f.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    # git itself would succeed with offset 1 (rc 0) — verify must not be fooled
    res = subprocess.run(
        ["git", "apply", "--reverse", "--check", str(patch)], cwd=live, capture_output=True, text=True
    )
    assert res.returncode == 0, "offset patch reverse-check succeeds with rc 0 (the hazard)"
    # But our verifier must still block
    report = ri.verify(repo, live, patch=patch)
    assert any(fl.flavour == "patch_drift" for fl in report.findings)


# ── R5: refused plateau ─────────────────────────────────────────────────


def test_refused_plateau_patch_drift_stays_refused(tmp_path):
    """repair on patch_drift is refused and stays refused on the next call.

    No file is written, no patch is re-exported by repair (byte_integrity
    repair is refused for patch_drift), and a second repair on the same
    report (or on a fresh verify) returns the same refused set — plateau,
    not escalation or healing.
    """
    live = make_live_long(tmp_path)
    repo = make_recovery(tmp_path)
    patch = _patch_for_long(live)
    # live stays at baseline => patch drift
    report = ri.verify(repo, live, patch=patch)
    assert any(f.flavour == "patch_drift" for f in report.findings)
    # Snapshot before repair
    before = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file() and ".git" not in p.parts}
    result1 = repair(report, repo, live, patch=patch)
    assert any(f.flavour == "patch_drift" for f in result1.refused), "patch_drift must be refused"
    after1 = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file() and ".git" not in p.parts}
    # repair must not have written the patch (refused) — plateau requires no churn
    assert before == after1, "refused repair must not write"
    # Second call with the same report must be identical (plateau)
    result2 = repair(report, repo, live, patch=patch)
    assert len(result2.refused) == len(result1.refused)
    assert {f.flavour for f in result2.refused} == {f.flavour for f in result1.refused}
    # And a fresh verify after refused repair must still report the same drift
    report2 = ri.verify(repo, live, patch=patch)
    assert any(f.flavour == "patch_drift" for f in report2.findings)
    assert len([f for f in report2.findings if f.flavour == "patch_drift"]) == len(
        [f for f in report.findings if f.flavour == "patch_drift"]
    )


def test_refused_plateau_is_stable_across_verify_repair_verify(tmp_path):
    """Full cycle: verify -> repair(refused) -> verify must be idempotent."""
    live = make_live_long(tmp_path)
    repo = make_recovery(tmp_path)
    patch = _patch_for_long(live)
    report1 = ri.verify(repo, live, patch=patch)
    assert report1.blocked
    repair(report1, repo, live, patch=patch)
    report2 = ri.verify(repo, live, patch=patch)
    # Still blocked, same flavour, not healed, not worsened
    assert report2.blocked
    assert {f.flavour for f in report1.findings} == {f.flavour for f in report2.findings}
    # Third verify after second repair also same — true plateau
    repair(report2, repo, live, patch=patch)
    report3 = ri.verify(repo, live, patch=patch)
    assert {f.flavour for f in report2.findings} == {f.flavour for f in report3.findings}


# ── R5: idempotence restore -> verify -> repair -> verify ───────────────


def test_restore_verify_repair_verify_idempotence_stale_seal(tmp_path):
    """Stale seal: restore (seal) -> verify clean -> repair -> verify clean, second repair no-op."""
    repo = make_recovery(tmp_path)
    live = make_live_long(tmp_path)
    # Make stale
    (repo / "tools" / "sealed_tool.py").write_text("print('changed')\n", encoding="utf-8", newline="\n")
    report1 = ri.verify(repo, live)
    assert any(f.flavour == "stale_seal" for f in report1.findings)
    result = repair(report1, repo, live)
    assert any(f.flavour == "stale_seal" for f in result.repaired)
    report2 = ri.verify(repo, live)
    assert report2.findings == (), f"after repair, verify must be clean, got {report2.findings}"
    # Second repair on clean report must be no-op
    result2 = repair(report2, repo, live)
    assert result2.repaired == () and result2.refused == ()
    report3 = ri.verify(repo, live)
    assert report3.findings == ()


def test_restore_verify_repair_verify_idempotence_tracked_noise(tmp_path):
    """Tracked live_tree_noise: restore -> verify -> repair(revert) -> verify clean, second repair no-op."""
    live = make_live_long(tmp_path)
    repo = make_recovery(tmp_path)
    # Tracked noise: modify a tracked file outside scope and commit it so checkout can revert
    # make_live already committed baseline; now add a tracked file outside scope
    (live / "hermes_cli").mkdir(parents=True, exist_ok=True)
    (live / "hermes_cli" / "other.py").write_text("original\n", encoding="utf-8", newline="\n")
    _git(live, "add", "-A")
    _git(live, "commit", "-qm", "add other")
    # Dirty it (tracked noise)
    (live / "hermes_cli" / "other.py").write_text("dirty\n", encoding="utf-8", newline="\n")
    report1 = ri.verify(repo, live)
    assert any(f.flavour == "live_tree_noise" and "tracked" in f.detail for f in report1.findings)
    result = repair(report1, repo, live)
    assert any(f.flavour == "live_tree_noise" for f in result.repaired)
    report2 = ri.verify(repo, live)
    assert not any(f.flavour == "live_tree_noise" for f in report2.findings), f"after repair, noise must be gone: {report2.findings}"
    # Idempotence: second repair is no-op
    result2 = repair(report2, repo, live)
    assert result2.repaired == ()
    assert ri.verify(repo, live).findings == ()


def test_repair_does_not_touch_fleet_and_is_idempotent_on_mixed_report(tmp_path):
    """Fleet findings are skipped and stay skipped across the cycle (R6 + idempotence)."""
    live = make_live_long(tmp_path)
    repo = make_recovery(tmp_path)
    # Create a mixed report: stale + untracked + fleet
    (repo / "tools" / "sealed_tool.py").write_text("changed\n", encoding="utf-8", newline="\n")
    (live / "scratch.txt").write_text("untracked\n", encoding="utf-8", newline="\n")
    # Synthetic fleet finding
    import fleet_consistency as fc

    fleet_finding = fc.Finding("fleet_drift", "block", "mxstat", "drift")
    base = ri.verify(repo, live)
    mixed = ri.Report(tuple(list(base.findings) + [fleet_finding]))
    result1 = repair(mixed, repo, live)
    assert any(f.flavour == "fleet_drift" for f in result1.skipped)
    # Repair the stale part, fleet stays skipped
    assert any(f.flavour == "stale_seal" for f in result1.repaired)
    # Second round: fleet still skipped, no new repaired
    # After first repair, stale is fixed, so only untracked + fleet remain
    report2 = ri.verify(repo, live)
    mixed2 = ri.Report(tuple(list(report2.findings) + [fleet_finding]))
    result2 = repair(mixed2, repo, live)
    assert any(f.flavour == "fleet_drift" for f in result2.skipped)
    assert not any(f.flavour == "stale_seal" for f in result2.repaired), "second repair must be idempotent for already-repaired stale"
