#!/usr/bin/env python3
"""Offline tests for grade.py and detect.py. No network, no API keys.

Needs litellm installed for the grade.py checks; they are skipped without it.
Run: python3 tests/test_grade.py
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, os.pardir, "scripts")
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, SCRIPTS)

PASS = json.dumps({"verdict": "PASS", "human_score": 90, "human_score_reason": "Specific.",
                   "blocking": [], "fix": [], "note": [], "unverifiable": []})
FAIL = "```json\n" + json.dumps({
    "verdict": "FAIL", "human_score": 55, "human_score_reason": "Tricolons throughout.",
    "blocking": [{"line": 3, "issue": "invented figure", "quote": "40%", "fix": "cut"}],
    "fix": [], "note": [], "unverifiable": ["40%"]}) + "\n```"


def check(label, ok, detail=""):
    print("{:4}  {}{}".format("ok" if ok else "FAIL", label, "  ({})".format(detail) if detail else ""))
    return ok


def run_grade(*extra, env=None):
    cmd = [sys.executable, os.path.join(SCRIPTS, "grade.py"),
           os.path.join(FIX, "slop.md"), os.path.join(FIX, "clean.md"), "--json"] + list(extra)
    env = dict(env if env is not None else os.environ)
    # Never let a real saved setup on this machine change what the tests see.
    env["ANTI_SLOP_CONFIG"] = os.path.join(tempfile.mkdtemp(), "config.json")
    for name in ("LITELLM_PROXY_API_BASE", "LITELLM_PROXY_API_KEY"):
        env.pop(name, None)
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
    try:
        return proc.returncode, json.loads(proc.stdout)
    except ValueError:
        return proc.returncode, {"stderr": proc.stderr[-400:]}


def main():
    ok = True
    try:
        import litellm  # noqa: F401
        have_litellm = True
    except ImportError:
        have_litellm = False
        print("skip  grade.py checks: litellm is not installed")

    if have_litellm:
        from grade import parse_json
        ok &= check("parses a fenced JSON reply", parse_json(FAIL)["verdict"] == "FAIL")

        code, out = run_grade("--models", "anthropic/claude-opus-5,openai/gpt-5", "--mock-response", PASS)
        ok &= check("two-provider panel passes", code == 0 and out["summary"]["passed"], str(code))
        ok &= check("panel reports cost", out["summary"].get("total_cost_usd") is not None)
        ok &= check("mixed panel is not flagged single-provider",
                    out["summary"].get("single_provider_panel") is False)

        code, out = run_grade("--models", "anthropic/claude-opus-5", "--mock-response", FAIL)
        ok &= check("blocking finding fails the panel", code == 1 and not out["summary"]["passed"], str(code))

        code, out = run_grade("--models", "anthropic/claude-opus-5", "--mock-response", "looks fine")
        ok &= check("unparseable reply exits 2", code == 2, str(code))

        env = {k: v for k, v in os.environ.items()
               if k not in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL",
                            "OPENAI_BASE_URL")}
        code, out = run_grade("--models", "openai/gpt-5", "--timeout", "15", env=env)
        err = (out.get("graders") or [{}])[0].get("error", out.get("stderr", ""))
        ok &= check("missing key is reported, not a crash", code == 2 and "key" in err, err[:80])

        from grade import pick_gateway_model
        ok &= check("gateway pick prefers 3.8 Flash over older and lite",
                    pick_gateway_model(["gemini-3.5-flash", "gemini-3.8-flash-lite", "gemini/gemini-3.8-flash"])
                    == "gemini/gemini-3.8-flash")
        ok &= check("gateway pick falls back to newest other Flash",
                    pick_gateway_model(["gemini-2.9-flash", "gemini-3.9-flash"]) == "gemini-3.9-flash")
        ok &= check("gateway pick returns None without Flash",
                    pick_gateway_model(["claude-opus-5", "gpt-5"]) is None)

    import detect
    sent = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=None):
        sent["body"] = json.loads(req.data)
        return Resp(json.dumps({"score": 0.2, "sentence_scores": [
            {"score": 0.4, "sentence": "A sentence."}]}).encode())

    real = urllib.request.urlopen
    urllib.request.urlopen = fake
    try:
        result = detect.sapling(detect.prose_only(open(os.path.join(FIX, "masking.md")).read()), 5, "k" * 32)
    finally:
        urllib.request.urlopen = real
    ok &= check("detector parses score and sentences",
                result["score"] == 0.2 and result["sentences"][0]["score"] == 0.4)
    ok &= check("code and URLs never leave the machine",
                "```" not in sent["body"]["text"] and "https://" not in sent["body"]["text"])

    print("\n{}".format("all checks passed" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
