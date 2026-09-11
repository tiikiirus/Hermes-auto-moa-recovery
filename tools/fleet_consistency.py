"""Cross-profile consistency — Task 2a.

Two-level drift for the "does the live graph equal the canon?" question,
kept separate from the byte-integrity question (recovery_integrity).

Level 1 — registry vs canon:
  Every entry in profile_overrides_registry.yaml must be reflected verbatim
  in auto-moa-moa-section.yaml:profile_overrides, and vice versa. Without
  this, the registry is stale docs and cross-check cannot be trusted.

Level 2 — fleet vs canon(+registry):
  For every profile in the fleet:
    - without an override — moa: block must be byte-identical (after
      normalisation) to the canon;
    - with an override — moa: block must equal canon merged with that
      profile's overrides (moa_sync.merged_moa);
    - lab profile (local-llm-lab) — absence of moa: is expected, presence
      is a finding. This is an explicit rule, not "missing file = bug".

Both levels are pure read-only (clarification 3). The same
test_verify_writes_nothing discipline applies here.

Registry + canon must be committed atomically (clarification 2). A
canary override gets status: canary so the two levels stay coherent
from the first commit.

This module is in the sync-tool zone (moa_sync), not the byte-integrity
zone (recovery_integrity). It reuses Report/Finding shapes from
recovery_integrity for a uniform doctor report.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # noqa: E402

from recovery_integrity import Finding, Report  # noqa: E402

# Reuse the same sync primitives so fleet check cannot drift from real sync.
import moa_sync  # noqa: E402

REGISTRY_NAME = "profile_overrides_registry.yaml"
CANON_NAME = "auto-moa-moa-section.yaml"
LAB_PROFILE = "local-llm-lab"


def registry_path(repo: Path) -> Path:
    return Path(repo) / REGISTRY_NAME


def canon_path(repo: Path) -> Path:
    return Path(repo) / CANON_NAME


def _load_registry(repo: Path) -> list[dict]:
    p = registry_path(repo)
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    # Support both {registry: [...]} and bare [...]
    if isinstance(data, dict) and "registry" in data:
        return list(data["registry"] or [])
    if isinstance(data, list):
        return data
    return []


def _registry_to_overrides(registry: list[dict]) -> dict:
    """registry list -> {profile: {presets: {preset: {key: value}}}}"""
    out: dict[str, dict] = {}
    for entry in registry:
        profile = entry.get("profile")
        preset = entry.get("preset")
        key = entry.get("key")
        value = entry.get("value")
        if not profile or not preset or not key:
            continue
        out.setdefault(profile, {}).setdefault("presets", {}).setdefault(preset, {})[key] = value
    return out


def _canon_overrides(canon: dict) -> dict:
    """Extract profile_overrides subtree from canon's moa block."""
    moa = (canon or {}).get("moa") or {}
    return (moa.get("profile_overrides") or {})  # type: ignore[return-value]


def _overrides_to_entries(overrides: dict) -> set[tuple]:
    """Flatten {profile: {presets: {preset: {k:v}}}} -> {(profile, preset, k, v)}"""
    entries: set[tuple] = set()
    for profile, cfg in (overrides or {}).items():
        presets = (cfg or {}).get("presets") or {}
        for preset, fields in presets.items():
            if not isinstance(fields, dict):
                continue
            for k, v in fields.items():
                entries.add((profile, preset, k, str(v) if v is not None else v))
    return entries


def _registry_to_entries(registry: list[dict]) -> set[tuple]:
    return {
        (e.get("profile"), e.get("preset"), e.get("key"), str(e.get("value")))
        for e in registry
        if e.get("profile") and e.get("preset") and e.get("key")
    }


# ── Level 1: registry vs canon ────────────────────────────────────────


def check_registry_vs_canon(repo: Path) -> Report:
    """Second level: does the explicit registry match the actual canon?"""
    repo = Path(repo)
    canon_file = canon_path(repo)
    if not canon_file.exists():
        return Report((Finding("registry_vs_canon_mismatch", "block", str(canon_file), "canon file missing"),))
    try:
        canon = yaml.safe_load(canon_file.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        return Report((Finding("registry_vs_canon_mismatch", "block", str(canon_file), f"canon yaml parse error: {exc}"),))

    registry = _load_registry(repo)
    canon_entries = _overrides_to_entries(_canon_overrides(canon))
    reg_entries = _registry_to_entries(registry)

    findings: list[Finding] = []

    missing_in_canon = reg_entries - canon_entries
    extra_in_canon = canon_entries - reg_entries

    for profile, preset, key, value in sorted(missing_in_canon):
        findings.append(
            Finding(
                "registry_vs_canon_mismatch",
                "block",
                f"{profile}:{preset}:{key}",
                f"registry expects {value!r} but canon has no such override (registry drift)",
            )
        )
    for profile, preset, key, value in sorted(extra_in_canon):
        findings.append(
            Finding(
                "registry_vs_canon_mismatch",
                "block",
                f"{profile}:{preset}:{key}",
                f"canon has override {value!r} with no registry entry (canon drift)",
            )
        )
    # Value mismatches are covered by the two sets above (same tuple diff),
    # but also handle case where key exists with different value: already in diff.
    return Report(tuple(findings))


# ── Level 2: fleet vs canon(+registry) ─────────────────────────────────


def _fleet_profile_paths(repo: Path | None = None) -> dict[str, Path]:
    """Profile name -> config.yaml path for the fleet (excluding lab)."""
    # Recompute from env at call time, not import time, so tests can monkeypatch LOCALAPPDATA.
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes"
    out: dict[str, Path] = {}
    # Import-time PROFILE_PATHS may be stale; rebuild the same set dynamically.
    for name in ("default", "mxstat", "fantrax", "aiqa", "auto-moa"):
        if name == "default":
            out[name] = base / "config.yaml"
        else:
            out[name] = base / "profiles" / name / "config.yaml"
    return out


def _lab_config_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "profiles" / LAB_PROFILE / "config.yaml"


def check_fleet(
    repo: Path,
    profile_paths: dict[str, Path] | None = None,
    lab_path: Path | None = None,
) -> Report:
    """Second level: does each live profile equal canon merged for that profile?

    Pure read-only. Lab profile: moa: absent is expected, present is a finding.
    """
    repo = Path(repo)
    canon_file = canon_path(repo)
    try:
        canon = yaml.safe_load(canon_file.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        return Report((Finding("fleet_drift", "block", str(canon_file), f"canon parse error: {exc}"),))
    canonical_moa = canon.get("moa")
    if not isinstance(canonical_moa, dict):
        return Report((Finding("fleet_drift", "block", str(canon_file), "missing top-level moa mapping"),))

    if profile_paths is None:
        profile_paths = _fleet_profile_paths(repo)
    if lab_path is None:
        lab_path = _lab_config_path()

    findings: list[Finding] = []

    for name, path in profile_paths.items():
        try:
            data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        except FileNotFoundError:
            findings.append(Finding("fleet_drift", "block", name, f"missing {path}"))
            continue
        except Exception as exc:  # noqa: BLE001
            findings.append(Finding("fleet_drift", "block", name, f"yaml error: {exc}"))
            continue

        # Use the same merge/drift primitives as the real sync tool.
        desired = moa_sync.merged_moa(data, canonical_moa, profile_name=name)
        if moa_sync.needs_sync(data, desired):
            findings.append(
                Finding(
                    "fleet_drift",
                    "block",
                    name,
                    f"moa block differs from canon merged for {name}",
                )
            )
            continue
        # Also run semantic_checks so a drifted default/provider is not missed.
        errs = moa_sync.semantic_checks(name, data)
        for err in errs:
            findings.append(Finding("fleet_drift", "block", f"{name}:{err}", err))

    # Lab exception — explicit. Lab profile must have no moa, but this is
    # a warn, not a block: lab is intentionally excluded from PROFILE_PATHS
    # and may carry a leftover moa block from an old sync. The finding is
    # still surfaced so a doctor report does not silently ignore it.
    if lab_path is not None and Path(lab_path).exists():
        try:
            lab_data = yaml.safe_load(Path(lab_path).read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001
            findings.append(Finding("lab_has_moa", "warn", LAB_PROFILE, f"lab yaml error: {exc}"))
        else:
            if "moa" in lab_data and lab_data["moa"] not in (None, {}, []):
                findings.append(
                    Finding(
                        "lab_has_moa",
                        "warn",
                        LAB_PROFILE,
                        f"{lab_path}: moa block present but lab profile must have no moa",
                    )
                )

    return Report(tuple(findings))


def check_all(repo: Path) -> Report:
    """Both levels together for a doctor report."""
    r1 = check_registry_vs_canon(repo)
    r2 = check_fleet(repo)
    return Report(r1.findings + r2.findings)
