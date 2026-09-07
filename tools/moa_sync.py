#!/usr/bin/env python3
"""Synchronize the canonical MoA graph into all Hermes live profiles.

The canonical graph is auto-moa-moa-section.yaml in this recovery repository.
Only the top-level `moa` section is replaced; profile model/default settings
remain profile-specific. Writes are atomic and backups are created first.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import yaml

PROFILE_PATHS = {
    "default": Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "config.yaml",
    "mxstat": Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "profiles" / "mxstat" / "config.yaml",
    "fantrax": Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "profiles" / "fantrax" / "config.yaml",
    "aiqa": Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "profiles" / "aiqa" / "config.yaml",
    "auto-moa": Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "profiles" / "auto-moa" / "config.yaml",
}
EXPECTED_DEFAULTS = {
    "default": "free_auto_moa",
    "mxstat": "pay_auto_moa",
    "fantrax": "free_auto_moa",
    "aiqa": "free_auto_moa",
    "auto-moa": "free_auto_moa",
}


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: YAML root is not a mapping")
    return data


def dump_yaml(data: dict[str, Any]) -> bytes:
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def atomic_write(path: Path, data: bytes) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _normalize(value: Any) -> Any:
    """Ignore harmless legacy `enabled: true` flags on reference slots."""
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items() if k != "enabled"}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def graph(canonical: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical preset graph and shared runtime policies."""
    moa = canonical["moa"]
    return _normalize({
        "presets": moa.get("presets", {}),
        "save_traces": moa.get("save_traces"),
        "privacy_filter": moa.get("privacy_filter"),
    })


def profile_graph(data: dict[str, Any]) -> dict[str, Any]:
    """Return the comparable canonical graph from a live profile."""
    moa = data.get("moa") or {}
    return _normalize({
        "presets": moa.get("presets", {}),
        "save_traces": moa.get("save_traces"),
        "privacy_filter": moa.get("privacy_filter"),
    })


def semantic_checks(name: str, data: dict[str, Any]) -> list[str]:
    model = data.get("model") or {}
    moa = data.get("moa") or {}
    presets = moa.get("presets") or {}
    errors: list[str] = []
    expected = EXPECTED_DEFAULTS[name]
    if model.get("provider") != "moa":
        errors.append(f"provider={model.get('provider')!r}, expected 'moa'")
    if model.get("default") != expected:
        errors.append(f"model.default={model.get('default')!r}, expected {expected!r}")
    if moa.get("default_preset") != expected:
        errors.append(f"moa.default_preset={moa.get('default_preset')!r}, expected {expected!r}")
    if len(presets) != 12:
        errors.append(f"preset count={len(presets)}, expected 12")
    if "auto_moa" in presets:
        errors.append("legacy preset auto_moa is present")
    pay = {"pay_default", "pay_code_logic_deep", "pay_logic_deep", "pay_code_visual_deep", "pay_logic_visual_deep", "pay_auto_moa"}
    for preset_name, preset in presets.items():
        model_name = ((preset or {}).get("aggregator") or {}).get("model")
        if preset_name in pay and model_name != "z-ai/glm-5.3-flash":
            errors.append(f"{preset_name}.aggregator={model_name!r}, expected z-ai/glm-5.3-flash")
        if preset_name not in pay and "luna-pro" in str(model_name):
            errors.append(f"free preset {preset_name} uses luna-pro")
    return errors


def merged_moa(data: dict[str, Any], canonical_moa: dict[str, Any]) -> dict[str, Any]:
    """Build the exact canonical MoA section with a profile-specific default."""
    current = data.get("moa") or {}
    result = copy.deepcopy(canonical_moa)
    result["default_preset"] = current.get("default_preset") or "free_auto_moa"
    return result


def needs_sync(data: dict[str, Any], canonical_moa: dict[str, Any]) -> bool:
    """Detect graph drift, including stale legacy top-level MoA keys."""
    desired = merged_moa(data, canonical_moa)
    return _normalize(data.get("moa") or {}) != _normalize(desired)


def catalog_models() -> set[str] | None:
    """Fetch the live provider model catalog; None if unreachable."""
    import json
    import urllib.request

    auth_path = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "auth.json"
    if not auth_path.exists():
        return None
    try:
        auth = json.loads(auth_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    def find_tokens(obj: Any) -> list[str]:
        out: list[str] = []
        if isinstance(obj, dict):
            for key, val in obj.items():
                if "token" in key.lower() and isinstance(val, str) and len(val) > 20:
                    out.append(val)
                else:
                    out.extend(find_tokens(val))
        elif isinstance(obj, list):
            for val in obj:
                out.extend(find_tokens(val))
        return out

    for token in find_tokens(auth):
        try:
            req = urllib.request.Request(
                "https://inference-api.nousresearch.com/v1/models",
                headers={"Authorization": f"Bearer {token}", "User-Agent": "hermes-moa-sync"},
            )
            data = json.loads(urllib.request.urlopen(req, timeout=30).read())
            return {m["id"] for m in data.get("data", [])}
        except Exception:
            continue
    return None


def configured_models(data: dict[str, Any]) -> set[str]:
    """All model ids referenced by a profile config."""
    names: set[str] = set()
    for preset in (data.get("moa") or {}).get("presets", {}).values():
        preset = preset or {}
        agg = (preset.get("aggregator") or {}).get("model")
        if agg:
            names.add(agg)
        for ref in preset.get("reference_models") or []:
            if ref.get("model"):
                names.add(ref["model"])
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--check", action="store_true", help="check drift without changing files")
    parser.add_argument("--sync", action="store_true", help="backup and synchronize all profiles")
    parser.add_argument("--catalog", action="store_true", help="also verify configured models exist in the provider catalog")
    args = parser.parse_args()
    if args.check == args.sync:
        parser.error("choose exactly one of --check or --sync")

    catalog: set[str] | None = catalog_models() if args.catalog else None
    if args.catalog and catalog is None:
        print("catalog: UNREACHABLE (skipping catalog checks)")

    canonical_path = args.repo / "auto-moa-moa-section.yaml"
    canonical = load_yaml(canonical_path)
    if not isinstance(canonical.get("moa"), dict):
        raise ValueError(f"{canonical_path}: missing top-level moa mapping")
    canonical_moa = graph(canonical)
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    loaded: dict[str, dict[str, Any]] = {}
    failures: list[str] = []

    for name, path in PROFILE_PATHS.items():
        if not path.exists():
            failures.append(f"{name}: missing {path}")
            continue
        try:
            loaded[name] = load_yaml(path)
        except Exception as exc:  # noqa: BLE001 - report all config parse failures
            failures.append(f"{name}: {exc}")
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        return 1

    backup_dir: Path | None = None
    if args.sync:
        backup_root = Path(os.environ.get("LOCALAPPDATA", str(args.repo))) / "hermes" / "backups"
        backup_dir = backup_root / f"moa-sync-{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=False)
        for name, path in PROFILE_PATHS.items():
            shutil.copy2(path, backup_dir / f"{name}.config.yaml")
        print(f"backups: {backup_dir}")

    changed = 0
    all_ok = True
    for name, path in PROFILE_PATHS.items():
        data = loaded[name]
        graph_same = profile_graph(data) == canonical_moa
        exact_same = not needs_sync(data, canonical_moa)
        errors = semantic_checks(name, data)
        if catalog is not None:
            for missing in sorted(configured_models(data) - catalog):
                errors.append(f"model not in provider catalog: {missing}")
        if not exact_same:
            changed += 1
        if args.sync and (not exact_same or errors):
            data["moa"] = merged_moa(data, canonical_moa)
            atomic_write(path, dump_yaml(data))
            data = load_yaml(path)
            errors = semantic_checks(name, data)
            if catalog is not None:
                for missing in sorted(configured_models(data) - catalog):
                    errors.append(f"model not in provider catalog: {missing}")
            graph_same = profile_graph(data) == canonical_moa
            exact_same = not needs_sync(data, canonical_moa)
        if errors or not exact_same:
            all_ok = False
        status = "OK" if exact_same and not errors else "DRIFT"
        print(f"{name}: {status} graph={'same' if exact_same else 'different'}")
        if errors:
            for error in errors:
                print(f"  {error}")
    if args.sync:
        print(f"synchronized profiles changed: {changed}")
    if not all_ok:
        print("FAIL")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
