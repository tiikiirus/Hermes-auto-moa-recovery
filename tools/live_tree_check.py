#!/usr/bin/env python3
"""Gate the live hermes-agent tree: only patch files may be dirty.

The recovery patch is a byte-exact export of the live diff. Any other dirty
file (e.g. package-lock.json after a manual `npm audit fix`) silently breaks
that invariant and risks leaking into the next patch export.

Allowlist = the 9 patch files (5 modified + 4 intent-to-add):
  agent/moa_loop.py, agent/moa_trace.py, agent/turn_request_assembly.py,
  hermes_cli/moa_cmd.py, hermes_cli/moa_config.py,
  agent/moa_auto_router.py,
  tests/agent/test_moa_auto_router.py, tests/agent/test_moa_auto_runtime.py,
  tests/hermes_cli/test_moa_cmd_auto.py

Usage:
  python tools/live_tree_check.py [--check]   # report only, exit 1 on noise
  python tools/live_tree_check.py --fix       # `git checkout --` TRACKED noise
                                              # only (restorable from HEAD);
                                              # untracked files are user data
                                              # and are only reported, never
                                              # deleted.

Exit codes: 0 = clean, 1 = noise found, 2 = repo/error.
"""
import subprocess
import sys
from pathlib import Path

ALLOWLIST = {
    "agent/moa_loop.py",
    "agent/moa_trace.py",
    "agent/turn_request_assembly.py",
    "hermes_cli/moa_cmd.py",
    "hermes_cli/moa_config.py",
    "agent/moa_auto_router.py",
    "tests/agent/test_moa_auto_router.py",
    "tests/agent/test_moa_auto_runtime.py",
    "tests/hermes_cli/test_moa_cmd_auto.py",
}

TRACKED_NOISE_PREFIXES = ("M ", " M", "MM", "AM", " D", "D ")


def live_repo() -> Path:
    import os

    return Path(
        os.environ.get("LOCALAPPDATA", "")) / "hermes" / "hermes-agent"


def status_lines(repo: Path) -> list:
    out = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        print(f"[live-tree] not a git worktree: {repo}")
        raise SystemExit(2)
    rows = []
    for line in out.stdout.splitlines():
        if len(line) < 4:
            continue
        rows.append((line[:2], line[3:].strip().strip('"')))
    return rows


def main() -> int:
    fix = "--fix" in sys.argv
    repo = live_repo()
    if not repo.exists():
        print(f"[live-tree] repo not found: {repo}")
        return 2
    noise = [(s, p) for s, p in status_lines(repo) if p not in ALLOWLIST]
    if not noise:
        print("[live-tree] CLEAN (only patch files dirty)")
        return 0
    print("[live-tree] NOISE outside the patch:")
    for st, path in noise:
        print(f"  {st} {path}")
    if not fix:
        print("[live-tree] run with --fix to revert TRACKED noise "
              "(untracked is only reported, never deleted)")
        return 1
    reverted, kept = [], []
    for st, path in noise:
        if st in TRACKED_NOISE_PREFIXES:
            r = subprocess.run(["git", "-C", str(repo), "checkout", "--", path])
            (reverted if r.returncode == 0 else kept).append(path)
        else:
            kept.append(f"{path} (untracked: not touched)")
    for path in reverted:
        print(f"  reverted: {path}")
    for path in kept:
        print(f"  kept (manual review needed): {path}")
    return 1 if kept else 0


if __name__ == "__main__":
    raise SystemExit(main())
