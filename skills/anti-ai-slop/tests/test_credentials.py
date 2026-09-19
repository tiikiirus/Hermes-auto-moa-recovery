#!/usr/bin/env python3
"""Tests for key sources and saved setup. No real keys, no network beyond localhost.

Run: python3 tests/test_credentials.py
"""

import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, os.pardir, "scripts")
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, SCRIPTS)

import credentials  # noqa: E402

SECRET = "fake-key-for-tests-only-0000"


def check(label, ok, detail=""):
    print("{:4}  {}{}".format("ok" if ok else "FAIL", label, "  ({})".format(detail) if detail else ""))
    return ok


def raises(fn):
    try:
        fn()
    except credentials.CredentialError as exc:
        return str(exc)
    return None


class Gateway(BaseHTTPRequestHandler):
    models = ["claude-opus-5", "gemini-3.5-flash", "gemini-3.8-flash"]

    def do_GET(self):
        if self.path != "/v1/models" or self.headers.get("Authorization") != "Bearer " + SECRET:
            self.send_response(401)
            self.end_headers()
            return
        body = json.dumps({"data": [{"id": m} for m in self.models]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    ok = True
    tmp = tempfile.mkdtemp()
    os.environ["ANTI_SLOP_CONFIG"] = os.path.join(tmp, "cfg", "config.json")

    os.environ["T_KEY"] = SECRET
    ok &= check("env source resolves", credentials.resolve("env:T_KEY") == SECRET)
    msg = raises(lambda: credentials.resolve("env:T_MISSING"))
    ok &= check("missing env var is a clear error", msg and "T_MISSING" in msg)

    keyfile = os.path.join(tmp, "key")
    with open(keyfile, "w") as fh:
        fh.write(SECRET + "\n")
    os.chmod(keyfile, 0o600)
    ok &= check("file source reads the first line", credentials.resolve("file:" + keyfile) == SECRET)

    real_run, real_platform = subprocess.run, sys.platform
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0 if "good" in " ".join(cmd) else 44, SECRET + "\n", SECRET)

    subprocess.run, sys.platform = fake_run, "darwin"
    try:
        ok &= check("keychain source resolves", credentials.resolve("keychain:good@my-account") == SECRET)
        ok &= check("keychain call passes service and account",
                    calls[-1] == ["security", "find-generic-password", "-s", "good", "-a", "my-account", "-w"])
        ok &= check("1Password source resolves", credentials.resolve("op://Vault/good/credential") == SECRET)
        msg = raises(lambda: credentials.resolve("keychain:missing"))
        ok &= check("failed lookup never echoes the secret", msg and SECRET not in msg, msg)
    finally:
        subprocess.run, sys.platform = real_run, real_platform

    ok &= check("unknown source type rejected", raises(lambda: credentials.resolve("vault:x")) is not None)
    ok &= check("https gateway accepted", credentials.check_url("https://gw.example/") == "https://gw.example")
    ok &= check("plain http to a remote host rejected",
                raises(lambda: credentials.check_url("http://gw.example")) is not None)

    server = HTTPServer(("127.0.0.1", 0), Gateway)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:{}".format(server.server_address[1])
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("LITELLM_PROXY", "GEMINI_API", "ANTHROPIC_API", "OPENAI_API"))}
    grade = [sys.executable, os.path.join(SCRIPTS, "grade.py")]

    def run(*extra):
        return subprocess.run(grade + list(extra), capture_output=True, text=True, env=env, timeout=120)

    proc = run("--check-setup")
    ok &= check("check-setup reports not ready before setup",
                proc.returncode == 2 and "Not ready" in proc.stdout, proc.stdout.strip()[:80])

    proc = run("--setup", "--gateway", base, "--key-from", "file:" + keyfile)
    ok &= check("setup verifies the gateway and saves", proc.returncode == 0, (proc.stdout + proc.stderr)[-160:])
    saved = open(os.environ["ANTI_SLOP_CONFIG"]).read()
    ok &= check("saved setup holds the location, not the key", SECRET not in saved and keyfile in saved)
    mode = stat.S_IMODE(os.stat(os.environ["ANTI_SLOP_CONFIG"]).st_mode)
    ok &= check("setup file is private to the user", mode == 0o600, oct(mode))

    proc = run("--check-setup")
    ok &= check("check-setup is ready from the saved setup",
                proc.returncode == 0 and "litellm_proxy/gemini-3.8-flash" in proc.stdout, proc.stdout.strip()[:120])
    ok &= check("no output ever contains the key", SECRET not in proc.stdout + proc.stderr)

    try:
        import litellm  # noqa: F401
        passing = json.dumps({"verdict": "PASS", "human_score": 88, "human_score_reason": "ok",
                              "blocking": [], "fix": [], "note": [], "unverifiable": []})
        proc = run(os.path.join(FIX, "slop.md"), os.path.join(FIX, "clean.md"), "--json",
                   "--mock-response", passing)
        out = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
        model = (out.get("graders") or [{}])[0].get("model")
        ok &= check("a plain run uses the saved gateway setup",
                    proc.returncode == 0 and model == "litellm_proxy/gemini-3.8-flash", str(model))
    except ImportError:
        print("skip  saved-setup run: litellm is not installed")

    bad = os.path.join(tmp, "bad")
    with open(bad, "w") as fh:
        fh.write("wrong-fake-key\n")
    os.chmod(bad, 0o600)
    proc = run("--setup", "--gateway", base, "--key-from", "file:" + bad)
    ok &= check("setup refuses a key the gateway rejects", proc.returncode == 2 and "401" in proc.stderr,
                proc.stderr.strip()[:100])

    server.shutdown()
    print("\n{}".format("all checks passed" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
