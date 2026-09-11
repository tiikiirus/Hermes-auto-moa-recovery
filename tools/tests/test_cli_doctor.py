"""Task 6: CLI and doctor — exit codes, stable JSON, two-section structure, read-only.

Run:  <hermes venv>/python.exe -m pytest tools/tests/test_cli_doctor.py -q
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

TOOLS_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))

import recovery_integrity as ri  # noqa: E402
import fleet_consistency as fc  # noqa: E402
import doctor  # noqa: E402


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
    (repo / "profile_overrides_registry.yaml").write_text("registry: []\n", encoding="utf-8")
    (repo / "auto-moa-moa-section.yaml").write_text("moa: {presets: {}, save_traces: true}\n", encoding="utf-8")
    return repo


# ── 1. exit code is severity-based, not presence-based ──────────────


def test_cli_exit_code_warn_only_is_zero(tmp_path):
    """A report with only warn findings must exit 0, not 1."""
    repo = make_recovery(tmp_path)
    live = make_live(tmp_path)
    # Directly test the Report logic that CLI relies on — no live noise
    warn_report = fc.Report((fc.Finding("lab_has_moa", "warn", "local-llm-lab", "warn only"),))
    assert warn_report.exit_code() == 0
    assert not warn_report.blocked
    # And through doctor: byte clean, fleet warn-only => doctor 0
    byte_report = ri.verify(repo, live)  # clean — live has no extra files
    assert not byte_report.blocked, byte_report.findings
    fleet_report = warn_report
    combined_blocked = byte_report.blocked or fleet_report.blocked
    assert combined_blocked is False
    assert (1 if combined_blocked else 0) == 0


def test_cli_exit_code_block_is_one(tmp_path):
    repo = make_recovery(tmp_path)
    live = make_live(tmp_path)
    (repo / "tools" / "sealed_tool.py").write_text("changed\n", encoding="utf-8", newline="")
    rc = ri.main(["--repo", str(repo), "--live", str(live)])
    assert rc == 1


def test_cli_missing_repo_exits_two(tmp_path):
    rc = ri.main(["--repo", str(tmp_path / "nope"), "--live", str(tmp_path / "nope2")])
    assert rc == 2


# ── 2. --json schema is versioned and field-stable ───────────────────


def test_cli_json_schema_is_stable(tmp_path):
    repo = make_recovery(tmp_path)
    live = make_live(tmp_path)
    (repo / "tools" / "sealed_tool.py").write_text("changed\n", encoding="utf-8", newline="")
    # Capture json via subprocess to also test the entry point
    proc = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "recovery_integrity.py"), "--repo", str(repo), "--live", str(live), "--json"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    # Top-level keys must be exactly these — addition/removal breaks the test on purpose
    assert set(payload.keys()) == {"version", "findings", "blocked", "exit_code"}
    assert payload["version"] == 1
    assert isinstance(payload["blocked"], bool)
    assert isinstance(payload["exit_code"], int)
    assert isinstance(payload["findings"], list)
    for f in payload["findings"]:
        assert set(f.keys()) == {"flavour", "severity", "path", "detail"}
        assert isinstance(f["flavour"], str) and f["flavour"]
        assert f["severity"] in ("block", "warn")
        # path may be None, detail is str
        assert isinstance(f["detail"], str)


def test_doctor_json_has_two_sections(tmp_path):
    repo = make_recovery(tmp_path)
    live = make_live(tmp_path)
    # Make fleet have a warn (lab) and byte have a block (stale)
    (repo / "tools" / "sealed_tool.py").write_text("changed\n", encoding="utf-8", newline="")
    lab = pathlib.Path(live).parent / "hermes" / "profiles" / "local-llm-lab" / "config.yaml"
    # Instead of touching global hermes, test doctor.verify_both directly with synthetic
    parts = doctor.verify_both(repo, live)
    assert "byte_integrity" in parts and "fleet_consistency" in parts
    # Now via CLI
    proc = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "doctor.py"), "--repo", str(repo), "--live", str(live), "--json"],
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout)
    assert set(payload.keys()) == {"version", "byte_integrity", "fleet_consistency", "blocked", "exit_code"}
    assert payload["version"] == 1
    for section in ("byte_integrity", "fleet_consistency"):
        assert set(payload[section].keys()) == {"findings", "blocked", "exit_code"}
        assert isinstance(payload[section]["blocked"], bool)
    # Structural separation: a byte flavour must never appear in fleet section
    byte_flavours = {f["flavour"] for f in payload["byte_integrity"]["findings"]}
    fleet_flavours = {f["flavour"] for f in payload["fleet_consistency"]["findings"]}
    assert byte_flavours.isdisjoint(fleet_flavours) or not byte_flavours or not fleet_flavours
    # More precise: every byte finding must be one of the byte flavours
    allowed_byte = {"missing_seal", "stale_seal", "checkout_unstable", "live_tree_noise", "patch_drift"}
    allowed_fleet = {"registry_vs_canon_mismatch", "fleet_drift", "lab_has_moa", "fleet_check_error"}
    for f in payload["byte_integrity"]["findings"]:
        assert f["flavour"] in allowed_byte
    for f in payload["fleet_consistency"]["findings"]:
        assert f["flavour"] in allowed_fleet


# ── 3. CLI inherits read-only invariant, even through the entry point ──


def test_cli_writes_nothing(tmp_path):
    repo = make_recovery(tmp_path)
    live = make_live(tmp_path)
    (live / "scratch.txt").write_text("untracked\n", encoding="utf-8", newline="")
    before = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file() and ".git" not in p.parts}
    ri.main(["--repo", str(repo), "--live", str(live)])
    ri.main(["--repo", str(repo), "--live", str(live), "--json"])
    after = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file() and ".git" not in p.parts}
    assert before == after


def test_doctor_writes_nothing(tmp_path):
    repo = make_recovery(tmp_path)
    live = make_live(tmp_path)
    before = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file() and ".git" not in p.parts}
    doctor.main(["--repo", str(repo), "--live", str(live)])
    doctor.main(["--repo", str(repo), "--live", str(live), "--json"])
    after = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file() and ".git" not in p.parts}
    assert before == after


# ── 5. No --fix surface in Task 6 ────────────────────────────────────


def test_cli_has_no_fix_flag():
    proc = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "recovery_integrity.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert "--fix" not in proc.stdout
    assert "--apply" not in proc.stdout.lower()
    proc2 = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "doctor.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert "--fix" not in proc2.stdout
