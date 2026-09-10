#!/usr/bin/env python3
"""Apply the MoA preset audit (F1-F6) to the canonical graph and every live config.

Why a script instead of ``tools/moa_sync.py --sync``:
``moa_sync`` re-serializes the ENTIRE config with PyYAML (``dump_yaml`` on the
whole document), which silently drops comments. ``profiles/aiqa/config.yaml``
and ``profiles/fantrax/config.yaml`` carry 36 comment lines each. This tool
instead rewrites only the lines it owns inside the ``moa:`` block, preserving
comments, key order and formatting byte-for-byte elsewhere.

It is indentation-relative (the canonical uses 6-space list items and YAML
anchors; the live profiles use 8-space list items and no anchors) and
idempotent: re-running it is a no-op. After applying, ``tools/moa_sync.py
--check`` must still print PASS, which is what proves the live profiles stayed
semantically equal to the canonical graph.

Changes applied
---------------
F1  drop the dead ``max_tokens`` preset key (not in ``_FLAT_PRESET_KEYS``; the
    only recognized output cap is ``reference_max_tokens``, so the aggregator
    was never actually capped).
F2  add ``reference_timeout: 240`` to non-``pay_`` presets only. The code
    deliberately does not cap strong/long-thinking advisors (see
    ``_coerce_reference_timeout``), but a ``:free`` flash advisor inherits
    ``auxiliary.moa_reference.timeout`` = 900s, which is a 15-minute stall risk.
F3  ``code_logic_deep.aggregator`` -> ``meituan/longcat-2.0:free``. The free
    auto-router sends code turns here, and its aggregator was
    ``poolside/laguna-s-2.1:free`` -- weaker than the aggregator of the auto
    preset it routes from.
F4  replace the ``inclusionai/ling-3.0-flash-sante:free`` advisor slot with
    ``stepfun/step-3.7-flash:free``: two of the three default advisors were
    variants of the same ``ling-3.0-flash`` family, so MoA independence was
    nominal.
F6  make ``degraded_reference_policy: loud`` explicit (it is already the code
    default -- this only makes the effective policy readable).

Deliberately NOT applied
------------------------
F5  ``fanout: every_n:3`` stays scoped to mxstat via ``profile_overrides``.
    That is a considered, documented decision (NEWLOG-704) and expanding it
    globally would multiply advisor spend on every profile.
F6b explicit ``reference_temperature`` / ``aggregator_temperature``: inventing
    values that override provider defaults is not defensible without evidence.

Usage:
    python tools/moa_preset_audit_apply.py --dry-run
    python tools/moa_preset_audit_apply.py --apply
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import sys
from pathlib import Path

HERMES = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "hermes"
REPO = Path(__file__).resolve().parent.parent

DEAD_KEY = "max_tokens"
FREE_TIMEOUT = 240
DEGRADED_POLICY = "loud"
SANTE_MODEL = "inclusionai/ling-3.0-flash-sante:free"
SANTE_REPLACEMENT = "stepfun/step-3.7-flash:free"
CODE_DEEP_PRESET = "code_logic_deep"
CODE_DEEP_AGGREGATOR = "meituan/longcat-2.0:free"

TARGETS = [
    REPO / "auto-moa-moa-section.yaml",
    HERMES / "config.yaml",
    HERMES / "profiles" / "aiqa" / "config.yaml",
    HERMES / "profiles" / "fantrax" / "config.yaml",
    HERMES / "profiles" / "mxstat" / "config.yaml",
    HERMES / "profiles" / "auto-moa" / "config.yaml",
    HERMES / "profiles" / "local-llm-lab" / "config.yaml",
]


def _backup_target(path: Path, stamp: str) -> Path:
    """Live configs follow the established Hermes convention (backup beside the
    file, e.g. ``config.yaml.bak-moa-rotate-...``); repo artifacts go under
    ``hermes/backups`` so the recovery tree stays clean (its integrity gate wants
    exactly the intended files in ``git status``)."""
    try:
        path.relative_to(REPO)
        in_repo = True
    except ValueError:
        in_repo = False
    if in_repo:
        return HERMES / "backups" / f"moa-preset-audit-{stamp}" / f"canonical.{path.name}"
    return path.with_name(path.name + f".bak-moa-preset-audit-{stamp}")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _key_name(stripped: str) -> str:
    """``aggregator: &anchor`` -> ``aggregator``; ``model: x`` -> ``model``."""
    head = stripped.split(":", 1)[0].strip()
    return head


def _split_value(stripped: str) -> tuple[str, str]:
    key, _, value = stripped.partition(":")
    return key.strip(), value.strip()


def audit_block(lines: list[str], path: Path) -> tuple[list[str], list[str]]:
    """Return ``(new_lines, notes)`` for one file's full line list."""
    start = next((i for i, l in enumerate(lines) if l.strip() == "moa:" and _indent(l) == 0), None)
    if start is None:
        return lines, [f"{path.name}: no top-level 'moa:' block -- skipped"]
    end = next(
        (j for j in range(start + 1, len(lines)) if lines[j].strip() and _indent(lines[j]) == 0),
        len(lines),
    )
    block = lines[start:end]
    notes: list[str] = []

    presets_indent = next(
        (_indent(l) for l in block if l.strip() == "presets:"), None
    )
    if presets_indent is None:
        return lines, [f"{path.name}: no 'presets:' under moa -- skipped"]
    preset_indent = presets_indent + 2
    key_indent = preset_indent + 2

    # Pass 1: which keys does each preset already declare? (idempotency)
    current = None
    declared: dict[str | None, set[str]] = {}
    for line in block:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        ind = _indent(line)
        if ind == preset_indent and stripped.endswith(":"):
            current = stripped[:-1].strip()
            declared.setdefault(current, set())
        elif ind == key_indent and ":" in stripped and current is not None:
            declared[current].add(_key_name(stripped))
    notes.append(
        f"{path.name}: presets={len([k for k in declared if k])} "
        f"declared_keys={sorted({k for v in declared.values() for k in v})}"
    )

    # Pass 2: transform.
    out: list[str] = []
    current = None
    current_key = None
    in_overrides = False
    removed_dead = added = retargeted = 0
    for line in block:
        stripped = line.strip()
        bare = stripped.rstrip()
        if not stripped:
            out.append(line)
            continue
        if in_overrides:
            out.append(line)
            continue
        if stripped.startswith("#"):
            out.append(line)
            continue
        ind = _indent(line)
        if ind == presets_indent and bare == "profile_overrides:":
            in_overrides = True
            out.append(line)
            continue
        if ind == preset_indent and stripped.endswith(":"):
            current = stripped[:-1].strip()
            current_key = None
            out.append(line)
            continue
        if ind == key_indent and ":" in stripped:
            current_key = _key_name(stripped)
            key, value = _split_value(stripped)
            if key == DEAD_KEY:  # F1
                removed_dead += 1
                continue
            if key == "reference_max_tokens":
                out.append(line)
                pad = " " * ind
                eol = line[len(line.rstrip("\r\n")):] or "\n"
                if current and not current.startswith("pay_") and "reference_timeout" not in declared.get(current, ()):
                    out.append(f"{pad}reference_timeout: {FREE_TIMEOUT}{eol}")  # F2
                    added += 1
                if "degraded_reference_policy" not in declared.get(current, ()):
                    out.append(f"{pad}degraded_reference_policy: {DEGRADED_POLICY}{eol}")  # F6
                    added += 1
                continue
            out.append(line)
            continue
        # Deeper lines: advisor slots and aggregator members.
        if ": " in stripped:
            key, value = _split_value(stripped)
            if key == "model" and value == SANTE_MODEL:  # F4
                out.append(line.replace(SANTE_MODEL, SANTE_REPLACEMENT))
                retargeted += 1
                continue
            if (
                key == "model"
                and current == CODE_DEEP_PRESET
                and current_key == "aggregator"
                and value != CODE_DEEP_AGGREGATOR
            ):  # F3
                out.append(line.replace(value, CODE_DEEP_AGGREGATOR))
                retargeted += 1
                continue
        out.append(line)

    notes.append(
        f"{path.name}: removed_dead_key={removed_dead} inserted_keys={added} retargeted_models={retargeted}"
    )
    return lines[:start] + out + lines[end:], notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="report intended edits, write nothing")
    group.add_argument("--apply", action="store_true", help="back up and write")
    args = parser.parse_args()

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    touched = 0
    for path in TARGETS:
        if not path.exists():
            print(f"SKIP (missing): {path}")
            continue
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            print(f"SKIP (not utf-8): {path}")
            continue
        new_text, notes = audit_block(text.splitlines(keepends=True), path)
        for note in notes:
            print("  " + note)
        changed = new_text != text.splitlines(keepends=True)
        if not changed:
            print(f"UNCHANGED: {path}")
            continue
        touched += 1
        if args.dry_run:
            print(f"WOULD CHANGE: {path}")
            continue
        backup = _backup_target(path, stamp)
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        new_text_str = "".join(new_text)
        tmp = path.with_name(f".{path.name}.audit.tmp")
        tmp.write_text(new_text_str, encoding="utf-8", newline="")
        os.replace(tmp, path)
        print(f"WROTE: {path}  (backup: {backup})")

    print(f"\n{'would change' if args.dry_run else 'changed'}: {touched} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
