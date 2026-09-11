"""Doctor — combined report: byte_integrity vs fleet_consistency.

Two questions, two objects, one process. The two zones stay structurally
separate so a finding from one zone can never leak into the other's key.

JSON schema (versioned):
{
  "version": 1,
  "byte_integrity": {"findings": [...], "blocked": bool, "exit_code": int},
  "fleet_consistency": {"findings": [...], "blocked": bool, "exit_code": int},
  "blocked": bool,        # OR of the two
  "exit_code": int        # 0 if no block, 1 if any block, 2 on error
}

Human output renders two sections with headers, never a flat list.

This is the read-only doctor for Task 6 point 3. Repair is not here.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # noqa: E402

import fleet_consistency as _fleet  # noqa: E402
import recovery_integrity as _ri  # noqa: E402


def _report_to_dict(report) -> dict:
    return {
        "findings": [
            {"flavour": f.flavour, "severity": f.severity, "path": f.path, "detail": f.detail}
            for f in report.findings
        ],
        "blocked": report.blocked,
        "exit_code": report.exit_code(),
    }


def verify_both(repo: Path, live: Path) -> dict:
    """Return the two-zone reports without printing."""
    byte_report = _ri.verify(repo, live)
    # fleet_consistency reads the registry + live fleet; live arg is not needed
    # for its check, but we pass repo so the two zones share the same root.
    try:
        fleet_report = _fleet.check_all(repo)
    except Exception as exc:  # noqa: BLE001
        # Fleet check failure is a verifier error at doctor level — surface as
        # a synthetic finding in fleet_consistency so the JSON stays typed.
        fleet_report = _fleet.Report(
            (_fleet.Finding("fleet_check_error", "block", None, f"fleet check failed: {exc}"),)
        )
    return {"byte_integrity": byte_report, "fleet_consistency": fleet_report}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Doctor — byte_integrity + fleet_consistency (read-only)")
    parser.add_argument("--repo", type=Path, default=_ri.repo_root())
    parser.add_argument("--live", type=Path, default=_ri.live_tree())
    parser.add_argument("--json", action="store_true", help="emit versioned JSON with two sections")
    args = parser.parse_args(argv)

    try:
        repo = Path(args.repo)
        live = Path(args.live)
        if not repo.exists():
            print(f"error: repo not found: {repo}", file=sys.stderr)
            return 2
        if not live.exists():
            print(f"error: live tree not found: {live}", file=sys.stderr)
            return 2
        parts = verify_both(repo, live)
        byte_report = parts["byte_integrity"]
        fleet_report = parts["fleet_consistency"]
        blocked = byte_report.blocked or fleet_report.blocked
        exit_code = 1 if blocked else 0
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"error: doctor failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        payload = {
            "version": 1,
            "byte_integrity": _report_to_dict(byte_report),
            "fleet_consistency": _report_to_dict(fleet_report),
            "blocked": blocked,
            "exit_code": exit_code,
        }
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        # Human: two hard sections, never a flat list
        sys.stdout.write("== byte_integrity (are our bytes what we sealed?) ==\n")
        sys.stdout.write(_ri._human_report(byte_report) + "\n\n")
        sys.stdout.write("== fleet_consistency (does live graph equal canon?) ==\n")
        # Reuse fleet's own human render if available, else same helper
        sys.stdout.write(_ri._human_report(fleet_report) + "\n\n")
        sys.stdout.write(f"doctor blocked={blocked} exit={exit_code}\n")
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
