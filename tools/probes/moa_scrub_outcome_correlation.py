"""Read-only: do MoA scrub events co-occur with turn-outcome symptoms?

Proxy only: there is NO per-turn success/fail label in the logs, so this cannot
prove causation. It measures whether minutes with scrub activity (fabricated
tool claims cut/marked by the anti-fabrication detector) also carry tool errors,
upstream retries or reference failures more often than the background rate.

Symptom classes (all from the profile's errors.log / agent.log):
  tool_error   agent.tool_executor "Tool X returned error"
  retry        agent.conversation_loop "API call failed (attempt ...)"
  upstream429  chat_completion_helpers streaming failure with 429
  refs_failed  agent.moa_loop "all N reference(s) failed"
Excluded as environmental noise: MCP server parking, credential-pool token
exchange, SessionDB handle warnings, context-engine fallback.

Usage:
    python tools/probes/moa_scrub_outcome_correlation.py [logs_dir]
    # logs_dir = <profile>/logs, e.g. %LOCALAPPDATA%/hermes/profiles/fantrax/logs
"""
from __future__ import annotations

import pathlib
import re
import statistics
import sys

TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
SCRUB_RE = re.compile(r"MoA scrubbed unverified tool claims in advisor outputs: removed=(\d+) marked=(\d+)")
SYMPTOM_RES = {
    "tool_error": re.compile(r"agent\.tool_executor: Tool \S+ returned error"),
    "retry": re.compile(r"agent\.conversation_loop: API call failed \(attempt"),
    "upstream429": re.compile(r"chat_completion_helpers: Streaming failed before delivery.*429"),
    "refs_failed": re.compile(r"MoA: all \d+ reference\(s\) failed"),
}
NOISE_RES = (
    re.compile(r"MCP server .* failed initial connection"),
    re.compile(r"credential_pool: Copilot token exchange"),
    re.compile(r"hermes_state: \d+ live SessionDB handles"),
    re.compile(r"Context engine .* not found"),
)

WINDOW_S = 180  # +/- seconds around a scrub event


def _epoch(ts: str) -> float:
    import datetime
    return datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").timestamp()


def main(logs_dir: pathlib.Path) -> int:
    scrub: list[dict] = []
    symptoms: list[tuple[float, str]] = []
    for logfile in (logs_dir / "errors.log", logs_dir / "agent.log"):
        if not logfile.exists():
            continue
        for line in logfile.read_text(encoding="utf-8", errors="replace").splitlines():
            m = TS_RE.match(line)
            if not m:
                continue
            t = _epoch(m.group(1))
            sm = SCRUB_RE.search(line)
            if sm:
                scrub.append({
                    "t": t, "ts": m.group(1),
                    "removed": int(sm.group(1)), "marked": int(sm.group(2)),
                })
                continue
            if any(rx.search(line) for rx in NOISE_RES):
                continue
            for name, rx in SYMPTOM_RES.items():
                if rx.search(line):
                    symptoms.append((t, name))
                    break

    # The same event is logged to errors.log AND agent.log: dedupe by identity.
    scrub = sorted({(e["ts"], e["removed"], e["marked"]): e for e in scrub}.values(),
                   key=lambda e: e["t"])
    print(f"scrub_events={len(scrub)}  symptom_events={len(symptoms)}")
    print(f"symptom mix: {dict(__import__('collections').Counter(n for _, n in symptoms))}")
    if not scrub:
        print("no scrub events found in the given logs; nothing to correlate")
        return 0

    rows = []
    for e in scrub:
        near = [(n, t) for t, n in symptoms if abs(t - e["t"]) <= WINDOW_S]
        e["symptoms"] = len(near)
        e["symptom_types"] = dict(__import__("collections").Counter(n for n, _ in near))
        rows.append(e)

    background = sum(1 for t, _ in symptoms
                     if not any(abs(t - e["t"]) <= WINDOW_S for e in scrub))
    print(f"background_symptoms (no scrub event within {WINDOW_S}s): {background}")
    print(f"{'time':<20} {'rem':>4} {'mar':>4} {'sym':>4}  types")
    for e in rows:
        print(f"{e['ts']:<20} {e['removed']:>4} {e['marked']:>4} {e['symptoms']:>4}  {e['symptom_types']}")

    heavy = [e for e in rows if e["removed"] + e["marked"] >= 3]
    light = [e for e in rows if e["removed"] + e["marked"] < 3]
    def mean(xs, key):
        return round(statistics.mean([key(x) for x in xs]), 2) if xs else 0.0
    print(f"\nscrub events with symptoms: {sum(1 for e in rows if e['symptoms'])}/{len(rows)}")
    print(f"heavy events (removed+marked>=3): {len(heavy)}, "
          f"mean symptoms={mean(heavy, lambda e: e['symptoms'])}")
    print(f"light events (removed+marked<3):  {len(light)}, "
          f"mean symptoms={mean(light, lambda e: e['symptoms'])}")

    xs = [e["removed"] + e["marked"] for e in rows]
    ys = [e["symptoms"] for e in rows]
    if len(rows) > 2 and statistics.pstdev(xs) > 0 and statistics.pstdev(ys) > 0:
        r = sum((x - statistics.mean(xs)) * (y - statistics.mean(ys))
                for x, y in zip(xs, ys)) / (
            len(rows) * statistics.pstdev(xs) * statistics.pstdev(ys)
        )
        print(f"pearson(scrub_weight, symptoms) = {r:.3f}")
    else:
        print("pearson: not computable (too few events or zero variance)")
    print("\ncaveat: proxy signal, no per-turn outcome label; symptoms may be "
          "environmental (upstream capacity) rather than caused by the turn.")
    return 0


if __name__ == "__main__":
    base = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else (
        pathlib.Path.home() / "AppData/Local/hermes/profiles/fantrax/logs"
    )
    raise SystemExit(main(base))