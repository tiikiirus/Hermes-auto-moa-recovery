"""R1: repair contract — three outcomes, mixed findings, partial success.

Run:  <hermes venv>/python.exe -m pytest tools/tests/test_repair.py -q
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

TOOLS_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))

import recovery_integrity as ri  # noqa: E402
import fleet_consistency as fc  # noqa: E402
from repair import RepairResult, repair  # noqa: E402


def _git(cwd: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def make_live(tmp_path: pathlib.Path) -> pathlib.Path:
    live = tmp_path / "live"
    live.mkdir(parents=True, exist_ok=True)
    if not (live / ".git").exists():
        _git(live, "init", "-q")
        _git(live, "config", "user.email", "a@a.invalid")
        _git(live, "config", "user.name", "a")
        _git(live, "config", "core.autocrlf", "true")
        (live / "agent").mkdir(parents=True, exist_ok=True)
        (live / "agent" / "moa_loop.py").write_text("x\n", encoding="utf-8", newline="")
        _git(live, "add", "-A")
        _git(live, "commit", "-qm", "init")
    return live


def make_recovery(tmp_path: pathlib.Path) -> pathlib.Path:
    repo = tmp_path / "recovery"
    (repo / "tools").mkdir(parents=True, exist_ok=True)
    (repo / "tools" / "sealed_tool.py").write_text("print('hi')\n", encoding="utf-8", newline="")
    (repo / ".gitattributes").write_text("tools/sealed_tool.py text eol=lf\n", encoding="utf-8", newline="")
    ri.seal(repo, "tools/sealed_tool.py")
    (repo / "auto-moa-current.patch").write_text("", encoding="utf-8")
    return repo


# ── R1.1: three outcomes are distinct ───────────────────────────────


def test_repair_result_has_three_buckets():
    r = RepairResult(
        repaired=(ri.Finding("stale_seal", "block", "a"),),
        skipped=(ri.Finding("live_tree_noise", "block", "b", "untracked"),),
        refused=(ri.Finding("patch_drift", "block", "c"),),
    )
    assert len(r.repaired) == 1 and len(r.skipped) == 1 and len(r.refused) == 1
    assert r.summary == "repaired=1 skipped=1 refused=1"
    assert r.any_refused is True


def test_repair_success_is_not_bool():
    """R1: success is not a bool — caller must inspect buckets for N->M log."""
    report = ri.Report((ri.Finding("stale_seal", "block", "tools/sealed_tool.py"),))
    repo = make_recovery(pathlib.Path(__import__("tempfile").mkdtemp()))
    live = make_live(pathlib.Path(__import__("tempfile").mkdtemp()))
    # Use synthetic report with temp repo that has the file
    import tempfile, pathlib as pl

    tmp = pl.Path(tempfile.mkdtemp())
    repo = make_recovery(tmp)
    live = make_live(tmp)
    # Make stale
    (repo / "tools" / "sealed_tool.py").write_text("changed\n", encoding="utf-8", newline="")
    stale_report = ri.verify(repo, live)
    assert any(f.flavour == "stale_seal" for f in stale_report.findings)
    result = repair(stale_report, repo, live)
    assert len(result.repaired) == 1
    assert len(result.refused) == 0
    # N->M can be built from result, not by re-running verify
    assert result.summary.startswith("repaired=")


# ── R1.2: mixed findings in one Report ──────────────────────────────


def test_repair_mixed_findings_are_handled_independently(tmp_path):
    """One Report with stale + untracked + fleet must repair/skips/refuse per flavour."""
    repo = make_recovery(tmp_path)
    live = make_live(tmp_path)
    # Create stale
    (repo / "tools" / "sealed_tool.py").write_text("changed\n", encoding="utf-8", newline="")
    # Create untracked noise
    (live / "scratch.txt").write_text("junk\n", encoding="utf-8", newline="")
    # Synthetic fleet finding
    fleet_finding = fc.Finding("fleet_drift", "block", "mxstat", "drift")
    # Build mixed report
    stale_report = ri.verify(repo, live)
    # stale_report has stale + live_tree_noise (untracked)
    mixed = ri.Report(tuple(list(stale_report.findings) + [fleet_finding]))
    assert any(f.flavour == "stale_seal" for f in mixed.findings)
    assert any(f.flavour == "live_tree_noise" for f in mixed.findings)
    assert any(f.flavour == "fleet_drift" for f in mixed.findings)

    result = repair(mixed, repo, live)
    # stale -> repaired, untracked -> skipped, fleet -> skipped
    assert any(f.flavour == "stale_seal" for f in result.repaired)
    assert any(f.flavour == "live_tree_noise" for f in result.skipped)
    assert any(f.flavour == "fleet_drift" for f in result.skipped)
    assert len(result.refused) == 0
    # No exception, all three processed


def test_repair_never_touches_untracked(tmp_path):
    live = make_live(tmp_path)
    repo = make_recovery(tmp_path)
    stray = live / "untracked.txt"
    stray.write_text("untracked\n", encoding="utf-8", newline="")
    report = ri.verify(repo, live)
    assert any("untracked" in f.detail for f in report.findings)
    result = repair(report, repo, live)
    assert stray.exists(), "untracked must be kept"
    assert any(f.flavour == "live_tree_noise" for f in result.skipped)


# ── R1.3: order / partial success with patch_drift + stale ─────────


def _patch_for(live: pathlib.Path) -> pathlib.Path:
    (live / "agent" / "moa_loop.py").write_text("patched\n", encoding="utf-8", newline="")
    diff = _git(live, "diff", "--", "agent/moa_loop.py").stdout
    (live / "agent" / "moa_loop.py").write_text("baseline\n", encoding="utf-8", newline="")
    out = live.parent / "auto-moa-current.patch"
    out.write_text(diff, encoding="utf-8", newline="")
    return out


def test_repair_partial_success_with_patch_drift_and_stale(tmp_path):
    """If Report has both stale and patch_drift, stale is repaired, patch is refused."""
    repo = make_recovery(tmp_path)
    live = make_live(tmp_path)
    # stale
    (repo / "tools" / "sealed_tool.py").write_text("changed\n", encoding="utf-8", newline="")
    # patch drift
    patch = _patch_for(live)  # live is baseline, so patch drift
    stale_part = ri.verify(repo, live, patch=pathlib.Path("/nonexistent"))  # without patch drift
    # Build report that has both
    patch_report = ri.verify(repo, live, patch=patch)
    assert any(f.flavour == "stale_seal" for f in stale_part.findings)
    assert any(f.flavour == "patch_drift" for f in patch_report.findings)
    mixed = ri.Report(tuple(list(stale_part.findings) + [f for f in patch_report.findings if f.flavour == "patch_drift"]))
    result = repair(mixed, repo, live, patch=patch)
    assert any(f.flavour == "stale_seal" for f in result.repaired), "stale must be repaired even when patch_drift present"
    assert any(f.flavour == "patch_drift" for f in result.refused), "patch_drift must be refused"
    # Verify stale is actually fixed on next verify (without patch drift)
    after = ri.verify(repo, live, patch=pathlib.Path("/nonexistent"))
    assert not any(f.flavour == "stale_seal" for f in after.findings)


def test_repair_does_not_abort_on_first_unrepairable(tmp_path):
    """One refused finding must not prevent repairing the next."""
    repo = make_recovery(tmp_path)
    live = make_live(tmp_path)
    # Two stales: one repairable, one with missing file
    (repo / "tools" / "sealed_tool.py").write_text("changed\n", encoding="utf-8", newline="")
    # Create a second sealed file then delete it to get missing
    (repo / "tools" / "extra.py").write_text("x\n", encoding="utf-8", newline="")
    (repo / ".gitattributes").write_text("tools/sealed_tool.py text eol=lf\ntools/extra.py text eol=lf\n", encoding="utf-8", newline="")
    ri.seal(repo, "tools/extra.py")
    (repo / "tools" / "extra.py").unlink()
    report = ri.verify(repo, live)
    assert any(f.flavour == "stale_seal" for f in report.findings)
    assert any(f.flavour == "missing_seal" for f in report.findings)
    result = repair(report, repo, live)
    assert any(f.flavour == "stale_seal" for f in result.repaired)
    assert any(f.flavour == "missing_seal" for f in result.refused)
