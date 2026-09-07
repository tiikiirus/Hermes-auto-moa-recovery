#!/usr/bin/env python3
"""Rotate a dead model out of the Hermes MoA scheme.

Replaces every occurrence of DEAD (aggregators, reference slots,
fallback_providers) with REPLACEMENT across:
  - %LOCALAPPDATA%\\hermes\\config.yaml
  - profiles aiqa / fantrax / mxstat config.yaml
  - recovery backup auto-moa-moa-section.yaml

Usage:
  python rotate-moa-model.bat <dead-model> <replacement-model>

After running: verify with `hermes config check`, test affected presets
via `hermes -z "ping" --provider moa -m <preset> --cli`, restart Hermes
Desktop so the gateway picks up the new config.
"""
import os
import shutil
import sys
import datetime
import difflib
import yaml
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERMES_DIR = Path.home() / "AppData/Local/hermes"
RECOVERY = Path(__file__).resolve().parent
CONFIGS = [
    HERMES_DIR / "config.yaml",
    HERMES_DIR / "profiles/aiqa/config.yaml",
    HERMES_DIR / "profiles/fantrax/config.yaml",
    HERMES_DIR / "profiles/mxstat/config.yaml",
    HERMES_DIR / "profiles/auto-moa/config.yaml",
]
BACKUP_YAML = RECOVERY / "auto-moa-moa-section.yaml"


def replace_model(cfg: dict, dead: str, repl: str) -> list:
    changes = []
    moa = cfg.get("moa") or {}
    for name, preset in (moa.get("presets") or {}).items():
        agg = preset.get("aggregator") or {}
        if agg.get("model") == dead:
            agg["model"] = repl
            changes.append(f"{name}: aggregator -> {repl}")
        for r in preset.get("reference_models") or []:
            if r.get("model") == dead:
                r["model"] = repl
                changes.append(f"{name}: reference -> {repl}")
    for e in cfg.get("fallback_providers") or []:
        if e.get("model") == dead:
            e["model"] = repl
            changes.append("fallback_providers -> " + repl)
    if (cfg.get("model") or {}).get("default") == dead:
        cfg["model"]["default"] = repl
        changes.append("model.default -> " + repl)
    return changes


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    dead, repl = sys.argv[1], sys.argv[2]
    if dead == repl:
        print("[rotate] dead == replacement; nothing to do")
        return 2
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    touched = False
    rotated_backup = False
    for path in CONFIGS + ([BACKUP_YAML] if BACKUP_YAML.exists() else []):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        cfg = yaml.safe_load(text) or {}
        if path == BACKUP_YAML:
            # backup file nests everything under top-level 'moa'
            changes = replace_model({"moa": cfg.get("moa")}, dead, repl)
        else:
            changes = replace_model(cfg, dead, repl)
        if not changes:
            continue
        touched = True
        rotated_backup = rotated_backup or path == BACKUP_YAML
        shutil.copy2(path, path.with_name(path.name + f".bak-rotate-{stamp}"))
        new_text = yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True,
                                  default_flow_style=False, width=200)
        # atomic write: tmp file + os.replace, so a killed process cannot
        # leave a half-written config.yaml (Windows: os.replace is atomic)
        tmp = path.with_name(path.name + ".tmp-rotate")
        tmp.write_bytes(new_text.encode("utf-8"))
        os.replace(tmp, path)
        print(f"[rotate] {path.name} ({path.parent.name}):")
        for c in changes:
            print("   *", c)
    if touched and rotated_backup:
        sums = RECOVERY / "SHA256SUMS.txt"
        if sums.exists():
            import hashlib

            target = BACKUP_YAML.name
            new_line = hashlib.sha256(BACKUP_YAML.read_bytes()).hexdigest() + " *" + target
            lines = sums.read_text(encoding="utf-8").splitlines()
            replaced = False
            for i, ln in enumerate(lines):
                if ln.split("*", 1)[-1].strip() == target:
                    lines[i] = new_line
                    replaced = True
                    break
            if replaced:
                sums.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
                print(f"[rotate] SHA256SUMS.txt: {target} entry updated")
            else:
                print(f"[rotate] WARNING: no {target} entry in SHA256SUMS.txt; update it manually")
    if not touched:
        print(f"[rotate] model {dead} not found anywhere; nothing changed")
        return 1
    print()
    print("[rotate] DONE. Next steps:")
    print("  1. hermes config check")
    print(f"  2. test affected presets: hermes -z \"ping\" --provider moa -m <preset> --cli")
    print("  3. restart Hermes Desktop (gateway caches config)")
    print(f"  4. python {RECOVERY / 'check-moa-models.py'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
