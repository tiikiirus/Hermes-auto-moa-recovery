"""Read-only verifier for seals, live-tree noise and patch applicability.

Run:  <hermes venv>/python.exe -m pytest tools/tests -q
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

TOOLS_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))

import recovery_integrity as ri  # noqa: E402


def _git(cwd: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def make_live(tmp_path: pathlib.Path, autocrlf: str = "true") -> pathlib.Path:
    """Real git repo with one commit.

    core.autocrlf is set EXPLICITLY: a test that depends on the machine's
    global setting is green locally and red in CI — the worst kind of test.
    """
    live = tmp_path / "live"
    live.mkdir(parents=True, exist_ok=True)
    # Re-init if already exists (test may reuse tmp_path)
    if not (live / ".git").exists():
        _git(live, "init", "-q")
        _git(live, "config", "user.email", "fixture@example.invalid")
        _git(live, "config", "user.name", "fixture")
        _git(live, "config", "core.autocrlf", autocrlf)
        (live / "agent").mkdir(parents=True, exist_ok=True)
        (live / "agent" / "moa_loop.py").write_text("patch target\n", encoding="utf-8", newline="")
        _git(live, "add", "-A")
        _git(live, "commit", "-qm", "baseline")
    else:
        _git(live, "config", "core.autocrlf", autocrlf)
    return live


def make_recovery(tmp_path: pathlib.Path) -> pathlib.Path:
    """Miniature recovery repo: seals + .gitattributes rules."""
    repo = tmp_path / "recovery"
    (repo / "tools").mkdir(parents=True, exist_ok=True)
    (repo / "tools" / "sealed_tool.py").write_text("print('hi')\n", encoding="utf-8", newline="")
    (repo / ".gitattributes").write_text("tools/sealed_tool.py text eol=lf\n", encoding="utf-8", newline="")
    ri.seal(repo, "tools/sealed_tool.py")  # test helper: writes the ledger line
    return repo


def test_clean_fixture_reports_no_drift(tmp_path):
    report = ri.verify(repo=make_recovery(tmp_path), live=make_live(tmp_path))
    assert report.findings == ()
    assert report.exit_code() == 0


def test_scope_matches_live_tree_check_allowlist():
    """Temporary bridge: while live_tree_check lives, two copies of scope must not diverge.

    Deleted together with tools/live_tree_check.py in Step 2.
    """
    source = (TOOLS_DIR / "live_tree_check.py").read_text(encoding="utf-8")
    assert set(ri.paths()) == ri._allowlist_from_source(source)
    assert len(ri.paths()) == 9


def test_stale_seal_blocks(tmp_path):
    repo, live = make_recovery(tmp_path), make_live(tmp_path)
    (repo / "tools" / "sealed_tool.py").write_text("print('changed')\n", encoding="utf-8", newline="")
    report = ri.verify(repo=repo, live=live)
    assert [f.flavour for f in report.findings] == ["stale_seal"]
    assert report.blocked and report.exit_code() == 1


def test_missing_sealed_file_blocks(tmp_path):
    repo, live = make_recovery(tmp_path), make_live(tmp_path)
    (repo / "tools" / "sealed_tool.py").unlink()
    assert [f.flavour for f in ri.verify(repo=repo, live=live).findings] == ["missing_seal"]


def test_ledger_with_crlf_lines_reads_cleanly(tmp_path):
    """Ledger in repo is CRLF (-text), so parsing must be CRLF-safe.

    Naive split("\\n") leaves \\r in the filename and turns every seal into
    a false missing_seal — exactly what sha256sum -c from Git Bash does.
    """
    repo, live = make_recovery(tmp_path), make_live(tmp_path)
    ledger = repo / "SHA256SUMS.txt"
    ledger.write_bytes(ledger.read_bytes().replace(b"\n", b"\r\n"))
    assert ri.verify(repo=repo, live=live).findings == ()


def test_undeclared_lf_file_is_checkout_unstable(tmp_path):
    """Exact hazard from phase 0: LF on disk, no attr, autocrlf=true."""
    repo = make_recovery(tmp_path)
    target = repo / "tools" / "pending.py"
    target.write_text("x = 1\n", encoding="utf-8", newline="")
    # Keep the existing sealed file declared, only the new file is undeclared.
    (repo / ".gitattributes").write_text("tools/sealed_tool.py text eol=lf\n", encoding="utf-8", newline="")
    ri.seal(repo, "tools/pending.py")
    findings = ri.verify(repo=repo, live=make_live(tmp_path)).findings
    assert [f.flavour for f in findings] == ["checkout_unstable"]
    assert findings[0].path == "tools/pending.py"


def test_declared_lf_file_is_stable(tmp_path):
    """Negative control: a properly declared file must not be flagged."""
    repo, live = make_recovery(tmp_path), make_live(tmp_path)
    assert ri.verify(repo=repo, live=live).findings == ()


def test_seal_unit_is_what_a_clone_produces(tmp_path):
    """fresh_bytes model is checked against real git, not its own logic."""
    live = make_live(tmp_path)
    (live / "agent" / "tool.py").write_text("y = 2\n", encoding="utf-8", newline="")  # LF, not declared
    _git(live, "add", "-A")
    _git(live, "commit", "-qm", "add tool")
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(live), str(clone))
    assert (clone / "agent" / "tool.py").read_bytes() != (live / "agent" / "tool.py").read_bytes()
    assert ri.fresh_bytes(live / "agent" / "tool.py", live) == (clone / "agent" / "tool.py").read_bytes()


def test_verify_writes_nothing(tmp_path):
    """Step 1 invariant: verifier must not mutate any file."""
    repo, live = make_recovery(tmp_path), make_live(tmp_path)
    before = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file() and ".git" not in p.parts}
    ri.verify(repo=repo, live=live)
    after = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file() and ".git" not in p.parts}
    assert before == after


# ── Task 3 follow-up: autocrlf=input + dash-text ───────────────────


def test_dash_text_attribute_not_converted(tmp_path):
    """Golden test for -text (text: unset) — must not be converted on autocrlf=true.

    This is the hazard that silently made 12/20 sealed files look stale on a
    real repo (auto-moa-hook.sh etc. are -text). Fresh must equal raw for
    -text even when core.autocrlf=true, otherwise every -text file becomes
    a false stale_seal on any Windows clone.
    """
    repo = tmp_path / "recovery_dash"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "a@a.invalid"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "a"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "core.autocrlf", "true"], cwd=repo, capture_output=True, check=True)
    (repo / ".gitattributes").write_text("tool.bin -text\n", encoding="utf-8", newline="\n")
    (repo / "tool.bin").write_bytes(b"\x00\x01\x02\n")  # binary-ish but also text-like
    # also a plain -text with LF
    (repo / "hook.sh").write_text("echo hi\n", encoding="utf-8", newline="\n")
    (repo / ".gitattributes").write_text("tool.bin -text\nhook.sh -text\n", encoding="utf-8", newline="\n")
    # Seal both
    ri.seal(repo, "tool.bin")
    ri.seal(repo, "hook.sh")
    # Fresh must equal raw for -text even when core.autocrlf=true
    assert ri.fresh_bytes(repo / "tool.bin", repo) == (repo / "tool.bin").read_bytes()
    assert ri.fresh_bytes(repo / "hook.sh", repo) == (repo / "hook.sh").read_bytes()
    # Also verify via real clone after commit
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-qm", "add"], cwd=repo, capture_output=True, check=True)
    clone = tmp_path / "clone_dash"
    subprocess.run(["git", "clone", "-q", str(repo), str(clone)], capture_output=True, check=True)
    # For -text, clone must equal raw (no conversion)
    assert (clone / "hook.sh").read_bytes() == (repo / "hook.sh").read_bytes()
    assert (clone / "tool.bin").read_bytes() == (repo / "tool.bin").read_bytes()
    # And verify reports no drift for this repo
    live2 = make_live(tmp_path / "live_dash_parent", autocrlf="true")
    assert ri.verify(repo=repo, live=live2).findings == ()


def test_autocrlf_input_normalises_to_lf(tmp_path):
    """Third value of core.autocrlf must be explicit, not accidental.

    input means CRLF->LF on commit, checkout leaves LF. A file with CRLF
    on disk and no declaration should be fresh=LF, so fresh != raw marks
    checkout_unstable (the reverse of the true->CRLF hazard).
    """
    repo = tmp_path / "recovery_input"
    (repo / "tools").mkdir(parents=True, exist_ok=True)
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "a@a.invalid"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "a"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "core.autocrlf", "input"], cwd=repo, capture_output=True, check=True)
    (repo / "tools").mkdir(parents=True, exist_ok=True)
    (repo / "tools" / "sealed_tool.py").write_text("print('hi')\n", encoding="utf-8", newline="")
    (repo / ".gitattributes").write_text("tools/sealed_tool.py text eol=lf\n", encoding="utf-8", newline="")
    ri.seal(repo, "tools/sealed_tool.py")
    # New file with CRLF on disk, no attr, autocrlf=input -> fresh should be LF
    (repo / "tools" / "crlf.py").write_bytes(b"x = 1\r\n")
    (repo / ".gitattributes").write_text("tools/sealed_tool.py text eol=lf\n", encoding="utf-8", newline="")
    ri.seal(repo, "tools/crlf.py")
    # Seal is LF (fresh), raw is CRLF -> checkout_unstable
    live_parent = tmp_path / "live_input_parent"
    live_parent.mkdir(parents=True, exist_ok=True)
    live = make_live(live_parent, autocrlf="input")
    findings = ri.verify(repo=repo, live=live).findings
    # crlf.py should be checkout_unstable because fresh (LF) != raw (CRLF)
    assert any(f.flavour == "checkout_unstable" and f.path == "tools/crlf.py" for f in findings)


# ── Task 4: live-tree noise (port of live_tree_check) ───────────────


def test_tracked_noise_outside_scope_blocks(tmp_path):
    live = make_live(tmp_path)
    (live / "hermes_cli").mkdir()
    (live / "hermes_cli" / "other.py").write_text("dirty\n", encoding="utf-8", newline="")
    findings = ri.verify(repo=make_recovery(tmp_path), live=live).findings
    assert [f.flavour for f in findings] == ["live_tree_noise"]
    assert "tracked" in findings[0].detail


def test_dirty_file_inside_scope_is_not_noise(tmp_path):
    live = make_live(tmp_path)
    (live / "agent" / "moa_loop.py").write_text("patched\n", encoding="utf-8", newline="")
    assert ri.verify(repo=make_recovery(tmp_path), live=live).findings == ()


def test_untracked_noise_is_reported_and_kept(tmp_path):
    live = make_live(tmp_path)
    stray = live / "scratch.txt"
    stray.write_text("junk\n", encoding="utf-8", newline="")
    report = ri.verify(repo=make_recovery(tmp_path), live=live)
    assert [f.flavour for f in report.findings] == ["live_tree_noise"]
    assert "untracked" in report.findings[0].detail
    assert stray.exists()  # verify() must not delete or checkout


def test_live_tree_noise_writes_nothing(tmp_path):
    """Task 4 invariant: live-tree check is read-only, like seals."""
    repo, live = make_recovery(tmp_path), make_live(tmp_path)
    (live / "scratch.txt").write_text("junk\n", encoding="utf-8", newline="")
    before = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file() and ".git" not in p.parts}
    ri.verify(repo=repo, live=live)
    after = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file() and ".git" not in p.parts}
    assert before == after


def test_noise_uses_paths_scope_not_duplicate_list(tmp_path):
    """Scope is the single paths() declaration, not a second hard-coded list."""
    live = make_live(tmp_path)
    # Every allowed path, when dirty, must NOT be noise
    for rel in ri.paths():
        (live / rel).parent.mkdir(parents=True, exist_ok=True)
        (live / rel).write_text("dirty\n", encoding="utf-8", newline="")
    assert ri.verify(repo=make_recovery(tmp_path), live=live).findings == ()


# ── Task 5: patch applicability ─────────────────────────────────────


def _patch_for(live: pathlib.Path) -> pathlib.Path:
    """Patch that applies to baseline and stops reverse-applying after a change."""
    (live / "agent" / "moa_loop.py").write_text("patched\n", encoding="utf-8", newline="")
    diff = _git(live, "diff", "--", "agent/moa_loop.py").stdout
    (live / "agent" / "moa_loop.py").write_text("baseline\n", encoding="utf-8", newline="")
    out = live.parent / "auto-moa-current.patch"
    out.write_text(diff, encoding="utf-8", newline="")
    return out


def test_patch_applies_cleanly_when_intact(tmp_path):
    live = make_live(tmp_path)
    patch = _patch_for(live)
    (live / "agent" / "moa_loop.py").write_text("patched\n", encoding="utf-8", newline="")
    assert ri.verify(repo=make_recovery(tmp_path), live=live, patch=patch).findings == ()


def test_patch_drift_blocks(tmp_path):
    live = make_live(tmp_path)
    patch = _patch_for(live)
    report = ri.verify(repo=make_recovery(tmp_path), live=live, patch=patch)  # live == baseline
    assert [f.flavour for f in report.findings] == ["patch_drift"]
    assert report.blocked


def test_patch_check_is_read_only_and_uses_correct_cwd(tmp_path):
    """--reverse --check must not write, and must be run from live root with a/b prefixes."""
    live = make_live(tmp_path)
    patch = _patch_for(live)
    before = {p: p.read_bytes() for p in sorted(live.rglob("*")) if p.is_file() and ".git" not in p.parts}
    ri.verify(repo=make_recovery(tmp_path), live=live, patch=patch)
    after = {p: p.read_bytes() for p in sorted(live.rglob("*")) if p.is_file() and ".git" not in p.parts}
    assert before == after
    # Also check that patch with wrong cwd would fail: our verify uses cwd=live,
    # so an a/b prefixed diff must succeed when live is the cwd.
    (live / "agent" / "moa_loop.py").write_text("patched\n", encoding="utf-8", newline="")
    assert ri.verify(repo=make_recovery(tmp_path), live=live, patch=patch).findings == ()
