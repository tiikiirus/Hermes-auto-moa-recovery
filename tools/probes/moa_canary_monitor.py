"""Read-only 7-day 429 rate monitor for the fantrax canary.

Baseline is 7 days BEFORE the canary commit (30fb6a4).  Hard trigger:
429 rate > 2× baseline sustained 48h.  Soft trigger: end-of-week review
(> baseline but < hard, or single-day spike).  Writes nothing.

Usage:
  python tools/probes/moa_canary_monitor.py [--profile fantrax] [--baseline-days 7]

Reads %LOCALAPPDATA%\\hermes\\profiles\\<profile>\\logs\\agent.log
Counts 429/rate-limit lines vs MoA request volume (moa_reference + moa_aggregator
lines).  Rate = 429 / requests, per day.  Also supports reading the
default profile logs.

The canary in auto-moa-moa-section.yaml is 2/6 every_n:3 (fantrax default +
free_auto_moa).  Projection: T median 4 / max 42 => ~2.9× advisor requests avg
(tools/probes/moa_fanout_spend_projection.py). Hard trigger protects the free-tier
quota.

Writes nothing; exit 0 always (monitoring, not gating).
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_TS = re.compile(r"^(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}")
_429 = re.compile(r"(429|rate limit|exceeded)", re.IGNORECASE)
_MOA_REF = re.compile(r"moa_reference:")
_MOA_AGG = re.compile(r"moa_aggregator:")

# Canary commit timestamp for baseline window (from git log 30fb6a4)
CANARY_DATE = datetime(2026, 9, 11)


def hermes_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "hermes"


def parse_log(log: Path) -> dict[str, dict]:
    """day -> {requests,429}."""
    per_day: dict[str, dict] = collections.defaultdict(lambda: {"requests": 0, "r429": 0})
    if not log.exists():
        return per_day
    with log.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _TS.match(line)
            if not m:
                continue
            day = m.group(1)
            if _MOA_REF.search(line) or _MOA_AGG.search(line):
                per_day[day]["requests"] += 1
            if _429.search(line) and "moa" in line.lower():
                per_day[day]["r429"] += 1
    return per_day


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="fantrax", help="profile to monitor")
    parser.add_argument("--baseline-days", type=int, default=7, help="baseline window days")
    args = parser.parse_args(argv)

    root = hermes_root()
    # fantrax logs are per-profile; default also has logs
    if args.profile == "default":
        log = root / "logs" / "agent.log"
    else:
        log = root / "profiles" / args.profile / "logs" / "agent.log"

    per_day = parse_log(log)
    if not per_day:
        print(f"no log: {log}")
        print("canary monitor: no data (log missing or empty)")
        return 0

    sorted_days = sorted(per_day.keys())
    print(f"profile: {args.profile}")
    print(f"log    : {log}")
    print(f"days   : {sorted_days[0]} .. {sorted_days[-1]} ({len(sorted_days)} days)")
    print()
    print(f"{'day':<12} {'req':>7} {'429':>6} {'rate':>8}  flag")
    rates: dict[str, float] = {}
    for day in sorted_days:
        d = per_day[day]
        rate = (d["r429"] / d["requests"]) if d["requests"] else 0.0
        rates[day] = rate
        flag = ""
        # Mark baseline window vs canary window
        try:
            dt = datetime.strptime(day, "%Y-%m-%d")
            if dt < CANARY_DATE:
                flag = "baseline"
            elif dt >= CANARY_DATE:
                flag = "canary"
        except Exception:
            pass
        print(f"{day:<12} {d['requests']:>7} {d['r429']:>6} {rate:>7.4%}  {flag}")

    # Baseline = median rate over 7 days before canary
    baseline_days = []
    for day in sorted_days:
        try:
            dt = datetime.strptime(day, "%Y-%m-%d")
        except Exception:
            continue
        if CANARY_DATE - timedelta(days=args.baseline_days) <= dt < CANARY_DATE:
            baseline_days.append(day)
    baseline_rates = [rates[d] for d in baseline_days if d in rates]
    if baseline_rates:
        # Use median to be robust to single-day spikes
        baseline_rates_sorted = sorted(baseline_rates)
        mid = len(baseline_rates_sorted) // 2
        baseline = (
            baseline_rates_sorted[mid]
            if len(baseline_rates_sorted) % 2 == 1
            else (baseline_rates_sorted[mid - 1] + baseline_rates_sorted[mid]) / 2
        )
        print()
        print(f"baseline window: {baseline_days[0] if baseline_days else '?'} .. {(CANARY_DATE - timedelta(days=1)).date()} ({len(baseline_days)} days)")
        print(f"baseline rate  : {baseline:.4%}  (median over {len(baseline_rates)} days)")
        print(f"hard trigger   : > {baseline*2:.4%} sustained 48h  (>2x baseline)")
        print(f"soft trigger   : > {baseline:.4%} at end-week review")
        # Check last 48h
        last_two = sorted_days[-2:] if len(sorted_days) >= 2 else sorted_days
        if last_two:
            last_rates = [rates[d] for d in last_two]
            hard = all(r > baseline * 2 for r in last_rates) if baseline > 0 else any(r > 0 for r in last_rates)
            print()
            print(f"last 48h ({', '.join(last_two)}): rates {[f'{r:.4%}' for r in last_rates]} -> {'HARD TRIGGER' if hard and baseline>0 else 'no hard trigger'}")
            if hard and baseline > 0:
                print("ACTION: hard trigger fires — rollback fantrax canary 2/6 -> 0 per docs/canary/2026-09-11-fantrax-canary-revert.md (partial revert, keep hygiene)")
            else:
                # Soft: any canary day above baseline
                canary_rates = [rates[d] for d in sorted_days if d in rates and datetime.strptime(d, "%Y-%m-%d") >= CANARY_DATE]
                soft = any(r > baseline for r in canary_rates) if canary_rates else False
                if soft:
                    print(f"soft note: canary rate above baseline on some days — review at end-week, not immediate rollback")
                else:
                    print("soft: no canary day above baseline")
    else:
        print()
        print(f"baseline window {args.baseline_days} days before {CANARY_DATE.date()} has no data — cannot compute trigger")
        print("hint: baseline is 7 days BEFORE canary commit 30fb6a4 (2026-09-11)")

    print()
    print("notes:")
    print("  - rate = 429 / requests (requests = moa_reference + moa_aggregator lines)")
    print("  - 429 lines counted only when 'moa' in line (excludes unrelated 429)")
    print("  - hard trigger requires >2x baseline sustained 48h (two consecutive days)")
    print("  - soft trigger is end-week review; single-day spike is not hard")
    print("  - writes nothing; run daily via cron or manually")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
