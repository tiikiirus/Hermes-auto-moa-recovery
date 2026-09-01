#!/usr/bin/env python3
"""Monitor liveness of the :free models used by the Hermes MoA scheme.

Works WITHOUT a valid API key: the Nous inference API performs the
model/free-period check BEFORE authentication, so:
  404 "free period has ended"  -> ROTATE  (model left the free tier)
  404 "not found"              -> REMOVED (model gone from catalog)
  401 / 429 / any other        -> ALIVE  (auth/rate-limit errors, not model errors)

Also diffs the live :free catalog against the models in use and reports
new free models that could be added to the scheme.

Usage:
  python check-moa-models.py [--json OUTFILE]

Exit codes: 0 = all healthy, 1 = rotation needed, 2 = config/API error.
"""
import json
import sys
import urllib.error
import urllib.request
import yaml
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERMES_DIR = Path.home() / "AppData/Local/hermes"
CONFIG = HERMES_DIR / "config.yaml"
LOG = HERMES_DIR / "logs/model-monitor.log"
CATALOG_URL = "https://inference-api.nousresearch.com/v1/models"
CHAT_URL = "https://inference-api.nousresearch.com/v1/chat/completions"
PROBE_KEY = "unauthenticated-liveness-probe"


def models_in_use():
    """Collect every :free model referenced by the MoA scheme + fallbacks."""
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    used = []
    moa = cfg.get("moa") or {}
    for name, preset in (moa.get("presets") or {}).items():
        for r in preset.get("reference_models") or []:
            if r.get("model", "").endswith(":free"):
                used.append(r["model"])
        agg = (preset.get("aggregator") or {}).get("model") or ""
        if agg.endswith(":free"):
            used.append(agg)
    for e in cfg.get("fallback_providers") or []:
        if e.get("model", "").endswith(":free"):
            used.append(e["model"])
    primary = (cfg.get("model") or {}).get("default") or ""
    if primary.endswith(":free"):
        used.append(primary)
    return sorted(set(used))


def fetch_catalog():
    req = urllib.request.Request(CATALOG_URL, headers={"User-Agent": "moa-monitor/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    items = data.get("data", data) if isinstance(data, dict) else data
    return [m["id"] if isinstance(m, dict) else m for m in items]


def probe(model):
    """Unauthenticated chat probe. Returns (status, detail)."""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }).encode("utf-8")
    req = urllib.request.Request(
        CHAT_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + PROBE_KEY,
            "User-Agent": "moa-monitor/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return "ALIVE", "HTTP 200"
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        if e.code == 404:
            if "free period" in detail:
                return "ROTATE", "free period has ended"
            if "not found" in detail.lower():
                return "REMOVED", "model not found in catalog"
            return "UNKNOWN", detail[:120]
        # 401 invalid key / 429 rate limit / 5xx transient -> model itself is fine
        return "ALIVE", f"HTTP {e.code} (auth/rate-limit layer)"
    except Exception as e:  # network trouble: report UNKNOWN, do not panic
        return "UNKNOWN", f"{type(e).__name__}: {e}"


def main():
    json_out = None
    if "--json" in sys.argv:
        json_out = sys.argv[sys.argv.index("--json") + 1]
    if not CONFIG.exists():
        print(f"[monitor] config not found: {CONFIG}")
        return 2
    used = models_in_use()
    print(f"[monitor] {len(used)} free models in use:")
    for m in used:
        print(f"  - {m}")
    print()
    try:
        catalog = fetch_catalog()
    except Exception as e:
        catalog = None
        print(f"[monitor] catalog fetch failed: {e}")

    results = {}
    need_rotation = False
    for m in used:
        status, detail = probe(m)
        results[m] = {"status": status, "detail": detail}
        mark = {"ALIVE": "OK     ", "ROTATE": "ROTATE ", "REMOVED": "REMOVED", "UNKNOWN": "CHECK  "}[status]
        if status in ("ROTATE", "REMOVED"):
            need_rotation = True
        print(f"  [{mark}] {m:44} {detail}")

    if catalog is not None:
        catalog_free = sorted(m for m in catalog if m.endswith(":free"))
        new_free = [m for m in catalog_free if m not in used]
        print()
        print(f"[monitor] catalog has {len(catalog_free)} :free models; not yet in scheme:")
        for m in new_free:
            print(f"  + {m}")

    print()
    if need_rotation:
        print("[monitor] RESULT: ACTION NEEDED — run rotate-moa-model.bat <dead-model> <replacement>")
        print("[monitor] free candidates: see list above / https://portal.nousresearch.com/models")
    else:
        print("[monitor] RESULT: all models healthy.")

    stamp = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{stamp} {'ACTION NEEDED' if need_rotation else 'OK'} {json.dumps(results, ensure_ascii=False)}\n")
    if json_out:
        Path(json_out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if need_rotation else 0


if __name__ == "__main__":
    sys.exit(main())
