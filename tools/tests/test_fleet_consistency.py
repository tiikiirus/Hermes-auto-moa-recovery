"""Task 2a: registry vs canon + fleet vs canon+registry + lab exception.

Both levels are pure read-only — same discipline as verify().

Run:  <hermes venv>/python.exe -m pytest tools/tests/test_fleet_consistency.py -q
"""
from __future__ import annotations

import pathlib
import sys

import pytest
import yaml

TOOLS_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))

import fleet_consistency as fc  # noqa: E402
import moa_sync  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────


def _canon_with_overrides(overrides: dict) -> dict:
    """Minimal canon moa dict with given profile_overrides."""
    # Reuse the 12-preset shape from test_moa_sync_splice
    from test_moa_sync_splice import _canonical_moa  # type: ignore

    moa = _canonical_moa()
    if overrides:
        moa["profile_overrides"] = overrides
    return {"moa": moa}


def _write_canon(repo: pathlib.Path, overrides: dict) -> None:
    (repo / "auto-moa-moa-section.yaml").write_text(
        yaml.safe_dump(_canon_with_overrides(overrides), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _write_registry(repo: pathlib.Path, entries: list[dict]) -> None:
    (repo / "profile_overrides_registry.yaml").write_text(
        yaml.safe_dump({"registry": entries}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _write_profile(path: pathlib.Path, moa: dict, profile_name: str | None = None) -> None:
    """Write a minimal profile config.yaml with given moa block."""
    # model/default must match EXPECTED_DEFAULTS for semantic_checks to pass
    if profile_name is None:
        profile_name = path.parent.name if "profiles" in path.parts else path.stem
    expected = moa_sync.EXPECTED_DEFAULTS.get(profile_name, "free_auto_moa")
    data = {
        "model": {"provider": "moa", "default": expected},
        "moa": moa,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _overrides_fixture() -> tuple[dict, list[dict]]:
    """One-profile, one-preset overrides + matching registry entries."""
    overrides = {
        "mxstat": {"presets": {"pay_default": {"fanout": "every_n:3"}}},
    }
    registry = [
        {
            "profile": "mxstat",
            "preset": "pay_default",
            "key": "fanout",
            "value": "every_n:3",
            "status": "active",
            "justification": "test",
        }
    ]
    return overrides, registry


# ── Level 1: registry vs canon ───────────────────────────────────────


def test_registry_matches_canon_when_aligned(tmp_path):
    overrides, registry = _overrides_fixture()
    _write_canon(tmp_path, overrides)
    _write_registry(tmp_path, registry)
    report = fc.check_registry_vs_canon(tmp_path)
    assert report.findings == (), report.findings
    assert report.exit_code() == 0


def test_registry_vs_canon_catches_missing_in_canon(tmp_path):
    overrides, registry = _overrides_fixture()
    _write_canon(tmp_path, {})  # canon has no overrides
    _write_registry(tmp_path, registry)
    report = fc.check_registry_vs_canon(tmp_path)
    assert any(f.flavour == "registry_vs_canon_mismatch" for f in report.findings)
    assert report.blocked


def test_registry_vs_canon_catches_extra_in_canon(tmp_path):
    overrides, registry = _overrides_fixture()
    _write_canon(tmp_path, overrides)  # canon has one
    _write_registry(tmp_path, [])  # registry empty
    report = fc.check_registry_vs_canon(tmp_path)
    assert any(f.flavour == "registry_vs_canon_mismatch" for f in report.findings)
    assert report.blocked
    assert "canon drift" in report.findings[0].detail


def test_registry_vs_canon_catches_value_mismatch(tmp_path):
    overrides = {"mxstat": {"presets": {"pay_default": {"fanout": "user_turn"}}}}
    _, registry = _overrides_fixture()  # registry says every_n:3
    _write_canon(tmp_path, overrides)
    _write_registry(tmp_path, registry)
    report = fc.check_registry_vs_canon(tmp_path)
    assert report.blocked
    assert len(report.findings) == 2  # missing expected + extra actual


def test_registry_vs_canon_writes_nothing(tmp_path):
    overrides, registry = _overrides_fixture()
    _write_canon(tmp_path, overrides)
    _write_registry(tmp_path, registry)
    before = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    fc.check_registry_vs_canon(tmp_path)
    after = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    assert before == after


# ── Level 2: fleet vs canon(+registry) ───────────────────────────────


def test_fleet_profile_matches_when_synced(tmp_path, monkeypatch):
    overrides, registry = _overrides_fixture()
    _write_canon(tmp_path, overrides)
    _write_registry(tmp_path, registry)
    # Precondition: registry vs canon clean
    assert fc.check_registry_vs_canon(tmp_path).findings == ()

    # Build a synced fleet: moa block == merged_canon for each profile
    from test_moa_sync_splice import _canonical_moa

    canon_moa = _canonical_moa()
    canon_moa["profile_overrides"] = overrides

    fleet_dir = tmp_path / "fleet"
    profile_paths: dict[str, pathlib.Path] = {}
    for name in ("default", "mxstat"):
        cfg = tmp_path / f"{name}.yaml"
        data = {
            "model": {"provider": "moa", "default": moa_sync.EXPECTED_DEFAULTS[name]},
            "moa": {"default_preset": moa_sync.EXPECTED_DEFAULTS[name]},
        }
        desired = moa_sync.merged_moa(data, canon_moa, profile_name=name)
        _write_profile(cfg, desired, profile_name=name)
        profile_paths[name] = cfg

    report = fc.check_fleet(tmp_path, profile_paths=profile_paths, lab_path=tmp_path / "no-lab.yaml")
    assert report.findings == (), report.findings


def test_fleet_drift_detected(tmp_path):
    overrides, registry = _overrides_fixture()
    _write_canon(tmp_path, overrides)
    _write_registry(tmp_path, registry)

    cfg = tmp_path / "drift.yaml"
    _write_profile(cfg, {"presets": {}, "default_preset": "default"}, profile_name="mxstat")  # wrong
    report = fc.check_fleet(tmp_path, profile_paths={"mxstat": cfg}, lab_path=tmp_path / "no-lab.yaml")
    assert any(f.flavour == "fleet_drift" for f in report.findings)
    assert report.blocked


def test_lab_has_no_moa_is_expected(tmp_path):
    overrides, registry = _overrides_fixture()
    _write_canon(tmp_path, overrides)
    _write_registry(tmp_path, registry)

    lab = tmp_path / "lab.yaml"
    lab.write_text("model:\n  provider: openai\n", encoding="utf-8")
    cfg = tmp_path / "default.yaml"
    from test_moa_sync_splice import _canonical_moa

    canon_moa = _canonical_moa()
    canon_moa["profile_overrides"] = overrides
    desired = moa_sync.merged_moa({"moa": {}}, canon_moa, profile_name="default")
    _write_profile(cfg, desired, profile_name="default")

    report = fc.check_fleet(tmp_path, profile_paths={"default": cfg}, lab_path=lab)
    assert not any(f.flavour == "lab_has_moa" for f in report.findings)


def test_lab_has_moa_detected(tmp_path):
    overrides, registry = _overrides_fixture()
    _write_canon(tmp_path, overrides)
    _write_registry(tmp_path, registry)

    lab = tmp_path / "lab.yaml"
    lab.write_text("moa:\n  presets: {}\n", encoding="utf-8")
    report = fc.check_fleet(tmp_path, profile_paths={}, lab_path=lab)
    assert any(f.flavour == "lab_has_moa" for f in report.findings)
    # lab_has_moa is warn, not block — it is surfaced but does not block the fleet
    assert any(f.severity == "warn" for f in report.findings if f.flavour == "lab_has_moa")
    assert not report.blocked


def test_cross_check_writes_nothing(tmp_path, monkeypatch):
    overrides, registry = _overrides_fixture()
    _write_canon(tmp_path, overrides)
    _write_registry(tmp_path, registry)
    cfg = tmp_path / "default.yaml"
    from test_moa_sync_splice import _canonical_moa

    canon_moa = _canonical_moa()
    canon_moa["profile_overrides"] = overrides
    desired = moa_sync.merged_moa({"moa": {}}, canon_moa, profile_name="default")
    _write_profile(cfg, desired, profile_name="default")
    lab = tmp_path / "lab.yaml"
    lab.write_text("model:\n  provider: openai\n", encoding="utf-8")

    before = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    fc.check_registry_vs_canon(tmp_path)
    fc.check_fleet(tmp_path, profile_paths={"default": cfg}, lab_path=lab)
    after = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    assert before == after
