#!/usr/bin/env python3
"""Monitor liveness of the models used by the Hermes MoA scheme (free + pay tiers).

Works WITHOUT a valid API key: the Nous inference API performs the
model/free-period check BEFORE authentication, so:
  404 "free period has ended"  -> ROTATE  (free model left the free tier)
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
    """Collect models referenced by the MoA scheme, split into free and paid tiers."""
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    free, paid = [], []
    moa = cfg.get("moa") or {}
    for name, preset in (moa.get("presets") or {}).items():
        slots = list(preset.get("reference_models") or [])
        if preset.get("aggregator"):
            slots.append(preset["aggregator"])
        for s in slots:
            m = s.get("model", "")
            if m.endswith(":free"):
                free.append(m)
            elif m:
                paid.append(m)
    for e in cfg.get("fallback_providers") or []:
        m = e.get("model", "")
        (free if m.endswith(":free") else paid).append(m)
    primary = (cfg.get("model") or {}).get("default") or ""
    if primary:
        (free if primary.endswith(":free") else paid).append(primary)
    return sorted(set(free)), sorted(set(paid))


def fetch_catalog():
    req = urllib.request.Request(CATALOG_URL, headers={"User-Agent": "moa-monitor/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    items = data.get("data", data) if isinstance(data, dict) else data
    return [m["id"] if isinstance(m, dict) else m for m in items]


def fetch_account_gate():
    """Read paid_access from the Nous portal. Returns dict or None on failure.

    The Nous portal gates paid models on paid_access (Plus subscription or
    purchased credits). Promo subscription credits on a Free plan do NOT set
    it — with paid_access=false every pay_* MoA preset silently degrades to
    free models (verified 2026-09-01 via model-identity probes).
    """
    try:
        auth = json.loads((HERMES_DIR / "auth.json").read_text(encoding="utf-8"))
        tok = auth["providers"]["nous"].get("access_token")
        if not tok:
            return None
    except Exception:
        return None
    req = urllib.request.Request(
        "https://portal.nousresearch.com/api/oauth/account",
        headers={"Authorization": "Bearer " + tok, "User-Agent": "moa-monitor/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None  # expired token etc. — hermes refreshes it on next CLI run
    access = data.get("paid_service_access") or {}
    sub = data.get("subscription") or {}
    return {
        "plan": sub.get("plan"),
        "credits_remaining": sub.get("credits_remaining"),
        "purchased_credits": data.get("purchased_credits_remaining"),
        "paid_access": access.get("paid_access"),
    }


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
    free_models, paid_models = models_in_use()
    print(f"[monitor] {len(free_models)} free models in use:")
    for m in free_models:
        print(f"  - {m}")
    if paid_models:
        print(f"[monitor] {len(paid_models)} paid models (pay_auto_moa tier):")
        for m in paid_models:
            print(f"  - {m}")
    print()
    try:
        catalog = fetch_catalog()
    except Exception as e:
        catalog = None
        print(f"[monitor] catalog fetch failed: {e}")

    results = {}
    need_rotation = False
    gate_warning = False

    def probe_section(models, label):
        nonlocal need_rotation
        if not models:
            return
        print(f"[monitor] {label}:")
        for m in models:
            status, detail = probe(m)
            results[m] = {"status": status, "detail": detail}
            mark = {"ALIVE": "OK     ", "ROTATE": "ROTATE ", "REMOVED": "REMOVED", "UNKNOWN": "CHECK  "}[status]
            if status in ("ROTATE", "REMOVED"):
                need_rotation = True
            print(f"  [{mark}] {m:44} {detail}")

    probe_section(free_models, "free tier")
    probe_section(paid_models, "pay tier")

    gate = fetch_account_gate()
    if gate is not None:
        print()
        print(f"[monitor] account gate: plan={gate['plan']} credits={gate['credits_remaining']} "
              f"purchased={gate['purchased_credits']} paid_access={gate['paid_access']}")
        if paid_models and gate["paid_access"] is not True:
            gate_warning = True
            print("[monitor] WARNING: pay_auto_moa presets exist but paid_access=false —")
            print("           they SILENTLY run free models. Buy Plus subscription or")
            print("           PAYG credits at https://portal.nousresearch.com to enable pay mode.")
    else:
        # fetch_account_gate() swallows all failures (no/expired token, portal
        # endpoint or shape change). Silence here once hid a live subscription,
        # so say so loudly instead of printing nothing.
        print()
        print("[monitor] account gate: UNAVAILABLE (portal check failed — token")
        print("           missing/expired or endpoint changed). paid_access UNKNOWN:")
        print("           verify spend in https://portal.nousresearch.com instead.")

    if catalog is not None:
        catalog_free = sorted(m for m in catalog if m.endswith(":free"))
        new_free = [m for m in catalog_free if m not in free_models]
        print()
        print(f"[monitor] catalog has {len(catalog_free)} :free models; not yet in scheme:")
        for m in new_free:
            print(f"  + {m}")

    print()
    if need_rotation:
        print("[monitor] RESULT: ACTION NEEDED — run rotate-moa-model.bat <dead-model> <replacement>")
        print("[monitor] free candidates: see list above / https://portal.nousresearch.com/models")
    elif gate_warning:
        print("[monitor] RESULT: pay mode is gated — free scheme fully operational.")
    else:
        print("[monitor] RESULT: all models healthy.")

    stamp = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{stamp} {'ACTION NEEDED' if need_rotation else ('GATED' if gate_warning else 'OK')} "
                f"{json.dumps(results, ensure_ascii=False)}\n")
    if json_out:
        Path(json_out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if need_rotation else 0


if __name__ == "__main__":
    sys.exit(main())
