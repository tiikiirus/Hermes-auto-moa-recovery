"""Read-only projection: advisor fan-out spend when a profile's ``fanout`` cadence changes.

Answers one question before touching a preset: what does moving a profile from
``fanout: user_turn`` (one advisor fan-out per user turn) to ``fanout: every_n:N``
cost the advisor budget?

Cadence semantics (``agent/moa_loop._fanout_cache_key``, verified in source):
``user_turn`` runs the advisors on iteration 1 of a turn and every later iteration is
a cache HIT, so a turn costs exactly ONE fan-out no matter how deep the tool loop
goes. ``every_n:N`` runs them on iteration 1 and then every Nth tool iteration,
in-between iterations reusing the cached guidance. For a turn with T aggregator
iterations:

    fan-outs(today)     = 1
    fan-outs(every_n:N) = floor((T - 1) / N) + 1

Two consequences worth stating plainly: the cadence only ever ADDS advisor calls, and
the paid aggregator is unaffected in BOTH modes (it runs once per iteration and merely
receives unrefreshed guidance in between; ``moa_loop`` says so explicitly).

Why this reads ``agent.log`` and not the traces: the trace writer stores
``aggregator.input_messages`` as of the fan-out, which the auto-router trims to
``context_messages: 8`` — turn depth is simply not in a trace. The log is, because
each model call logs ``moa_reference: using …`` / ``moa_aggregator: using …`` once.

Measurement, and its limits:

    * A fan-out is a burst of ``moa_reference`` lines within ``--burst-window`` seconds
      (advisors are dispatched in parallel, so a real fan-out logs within milliseconds;
      bursts larger than the preset's advisor count mean two fan-outs landed inside the
      window).
    * T for the k-th turn is the number of ``moa_aggregator`` lines between fan-out k and
      fan-out k+1. That counts RETRIES as iterations, so T is an upper bound; the last
      burst is open-ended and excluded from the statistics.
    * The log spans whatever config generations it spans, so treat the ratio as the shape
      of the workload (how deep fantrax turns run), not as an exact per-preset figure.

Usage:
    python tools/probes/moa_fanout_spend_projection.py [--n 3] [--profile fantrax] [--burst-window 1.0]

Reads logs and traces only; writes nothing.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

# Windows consoles default to cp1251/cp866 and would raise on non-ASCII output.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_TIMESTAMP = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+")
_REFERENCE = re.compile(r"moa_reference: using nous \(([^)]+)\)")
_AGGREGATOR = re.compile(r"moa_aggregator: using nous \(([^)]+)\)")
_RATE_LIMIT = re.compile(r"(rate limit|429|exceeded)", re.IGNORECASE)


def hermes_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "hermes"


def profile_dirs(only: str | None) -> list[tuple[str, Path]]:
    """(name, profile dir) for every profile with a logs/agent.log, plus the default."""
    root = hermes_root()
    out: list[tuple[str, Path]] = []
    if only:
        candidates = [("default", root), (only, root / "profiles" / only)]
    else:
        candidates = [("default", root)]
        candidates += [(p.name, p) for p in sorted((root / "profiles").glob("*")) if p.is_dir()]
    for name, base in candidates:
        if (base / "logs" / "agent.log").exists():
            out.append((name, base))
    return out


def parse_events(log: Path) -> tuple[list[tuple[str, datetime, str]], int]:
    """(events, rate-limit line count); events are ('ref'|'agg', ts, model)."""
    events: list[tuple[str, datetime, str]] = []
    rate_limited = 0
    with log.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            stamp = _TIMESTAMP.match(line)
            if not stamp:
                continue
            if _RATE_LIMIT.search(line) and "moa" in line.lower():
                rate_limited += 1
            reference = _REFERENCE.search(line)
            aggregator = _AGGREGATOR.search(line)
            if reference:
                events.append(("ref", datetime.strptime(stamp.group(1), "%Y-%m-%d %H:%M:%S"), reference.group(1)))
            elif aggregator:
                events.append(("agg", datetime.strptime(stamp.group(1), "%Y-%m-%d %H:%M:%S"), aggregator.group(1)))
    return events, rate_limited


def fanout_bursts(events: list, window: float) -> list[list[tuple]]:
    """Group consecutive reference calls dispatched within ``window`` seconds."""
    bursts: list[list[tuple]] = []
    current: list[tuple] = []
    for kind, ts, model in events:
        if kind != "ref":
            continue
        if current and (ts - current[-1][1]).total_seconds() <= window:
            current.append((kind, ts, model))
        else:
            if current:
                bursts.append(current)
            current = [(kind, ts, model)]
    if current:
        bursts.append(current)
    return bursts


# Mirrors agent/moa_loop._MAX_FANOUTS_PER_TURN: every_n fan-outs stop after
# this many advisor runs per user turn no matter how deep the tool loop goes.
MAX_FANOUTS_PER_TURN = 4


def fanouts_for(t: int, n: int) -> int:
    """Fan-outs in a turn with ``t`` aggregator iterations under ``every_n:n``."""
    if t <= 1:
        return 1
    return min(MAX_FANOUTS_PER_TURN, (t - 1) // n + 1)


def spend_snapshot(profile_dir: Path) -> dict:
    """Advisor $/token snapshot from the profile's traces (cost side of the question)."""
    snap = {"slots": 0, "cost_usd": 0.0, "cost_unknown": 0, "in_tokens": 0, "out_tokens": 0, "files": 0}
    for trace in sorted((profile_dir / "moa-traces").glob("*.jsonl")):
        snap["files"] += 1
        for line in trace.open(encoding="utf-8", errors="replace"):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue
            for ref in record.get("references") or []:
                snap["slots"] += 1
                usage = ref.get("usage") or {}
                snap["in_tokens"] += int(usage.get("input_tokens") or 0)
                snap["out_tokens"] += int(usage.get("output_tokens") or 0)
                cost = ref.get("cost_usd")
                if isinstance(cost, (int, float)):
                    snap["cost_usd"] += float(cost)
                elif ref.get("cost_status") == "unknown":
                    snap["cost_unknown"] += 1
    return snap


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=3, help="cadence to project (default 3)")
    parser.add_argument("--profile", default=None, help="only this profile")
    parser.add_argument("--burst-window", type=float, default=1.0, help="seconds (default 1.0)")
    args = parser.parse_args(argv[1:])
    if args.n < 2:
        parser.error("--n must be >= 2 (every_n:1 is per_iteration)")

    print(f"projection: fanout=user_turn -> every_n:{args.n}   (fan-outs/turn: 1 -> floor((T-1)/N)+1)")
    print("T = aggregator iterations per turn, measured from agent.log\n")
    print(f"{'profile':<12} {'fan-outs':>9} {'advisors':>9} {'T median':>9} {'T max':>6}"
          f" {'proj median':>11} {'mean ratio':>10} {'max':>5}  {'429/rate-limit lines':>20}")

    for name, base in profile_dirs(args.profile):
        events, rate_limited = parse_events(base / "logs" / "agent.log")
        bursts = fanout_bursts(events, args.burst_window)
        # Keep only real fan-outs: a single reference line is a retry, not a turn's fan-out.
        bursts = [b for b in bursts if len(b) >= 2]
        if len(bursts) < 2:
            print(f"{name:<12} {'—':>9} {'—':>9} {'—':>9} {'—':>6} {'—':>11} {'—':>10} {'—':>5}  {rate_limited:>20}")
            continue
        starts = [b[0][1] for b in bursts]
        depths: list[int] = []
        for index in range(len(bursts) - 1):  # last burst is open-ended
            lo, hi = starts[index], starts[index + 1]
            depths.append(sum(1 for kind, ts, _ in events if kind == "agg" and lo <= ts < hi))
        projections = [fanouts_for(t, args.n) for t in depths]
        advisors = sum(len(b) for b in bursts)
        print(f"{name:<12} {len(bursts):>9} {advisors:>9} {statistics.median(depths):>9.0f}"
              f" {max(depths):>6} {statistics.median(projections):>11.0f}"
              f" {statistics.mean(projections):>9.2f}x {max(projections):>5}"
              f"  {rate_limited:>20}")
        gains = sum(1 for p in projections if p > 1)
        snap = spend_snapshot(base)
        print(f"{'':<12} turns that gain: {gains}/{len(depths)}"
              f" | advisor $ in traces: ${snap['cost_usd']:.4f}"
              f" (slots with cost_status=unknown: {snap['cost_unknown']})"
              f" | advisor tokens: {snap['in_tokens']} in / {snap['out_tokens']} out")
        print(f"{'':<12} fan-out sizes seen: {sorted(collections.Counter(len(b) for b in bursts).items())}")

    print("\nReading of the numbers:")
    print("  * ratio > 1 means the cadence ADDS advisor requests; it can never remove them.")
    print("  * the paid aggregator call count is unchanged in both modes.")
    print("  * advisor $ is 0 wherever the advisors are :free models — the real budget is")
    print("    free-tier request quota and added latency, which is why the 429 column matters.")
    print("  * T counts retries as iterations (upper bound); the last burst is excluded.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
