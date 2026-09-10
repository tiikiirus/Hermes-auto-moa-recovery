# Read-only probes of the anti-fabrication scrubber (no edits to the repo).
import sys, time

REPO = r"C:/Users/tiki/AppData/Local/hermes/hermes-agent"
sys.path.insert(0, REPO)

try:
    from agent.moa_loop import _scrub_unverified_tool_claims as scrub, _TOOL_CLAIM_RES
    print("IMPORT: live module OK")
except Exception as e:
    print("IMPORT FAILED:", type(e).__name__, e)
    sys.exit(2)

CTX_OK = 'лог хода: [tool result]: {"output": "ok"} конец лога'
cases = [
    ("verbatim bare quote (should MARK)", '[tool result]: {"output": "ok"}', CTX_OK),
    ("VERIFIED-prefixed honest quote (contract says quote under VERIFIED)", 'VERIFIED: [tool result]: {"output": "ok"}', CTX_OK),
    ("honest quote with bullet prefix", '- [tool result]: {"output": "ok"}', CTX_OK),
    ("single-quote dict repr (python shape)", "[tool result]: {'exit_code': 1}", "любой контекст"),
    ("bare stdout: label", "stdout: bash: command not found", "любой"),
    ("bare stderr: label", "stderr: permission denied", "любой"),
    ("unquoted exit_code:", "exit_code: 0", "любой"),
    ("HTTP status line", "HTTP/1.1 404 Not Found", "любой"),
    ("Status: 200", "Status: 200 OK", "любой"),
    ("PID line", "PID 12345 — процесс жив", "любой"),
    ("uppercase [TOOL RESULT]", "[TOOL RESULT] payload", "любой"),
    ("mid-sentence [tool result] mention", "как показано в [tool result] выше — нет", "как показано в [tool result] выше — нет"),
    ("containerTag in prose", "containerTag: проверь написание поля", "любой"),
    ("multiline JSON body after marker removal", '[tool result]\n{"output": "all good",\n "duration_ms": 42}\nСовет.', "другой контекст"),
]
print("--- behavior probes ---")
for name, t, c in cases:
    out, rm, mk = scrub(t, c)
    print(f"{name!r}: removed={rm} marked={mk} out={out!r}")

print("--- perf probe ---")
big = ("x " * 100 + "\n") * 20000          # ~2.4 MB context
many = "\n".join(f'[tool result]: {{"output": "line{i}"}}' for i in range(5000))
t0 = time.perf_counter()
r = scrub(many, big)
dt = time.perf_counter() - t0
print(f"5000 tool-shaped lines vs ~2.4MB context: {dt:.2f}s, removed={r[1]}")

moderate = ("x " * 100 + "\n") * 2000      # ~240KB context
t0 = time.perf_counter()
scrub(many, moderate)
print(f"5000 tool-shaped lines vs ~240KB context: {time.perf_counter()-t0:.2f}s")

t0 = time.perf_counter()
scrub("Совет обычный, ничего tool-shaped.\n" * 2000, big)
print(f"2000 clean lines vs ~2.4MB context: {time.perf_counter()-t0:.3f}s (regex-only cost)")
