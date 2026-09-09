# MoA Anti-Fabrication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Советники MoA перестают оформлять выдумки как факты: промпт запрещает эмуляцию tool-вывода и требует секции VERIFIED/INFERRED, механический детектор вырезает «голые» tool-блоки и маркирует цитаты, агрегатор предупреждается в header.

**Architecture:** Вся работа — в `agent/moa_loop.py` live-дерева + тесты; детектор — чистая функция с явным контрактом; в проводку встраивается в двух местах сборки guidance (loop-путь `_build_guidance`, one-shot `aggregate_moa_context`); патч реэкспортируется тем же списком из 9 файлов.

**Tech Stack:** Python 3.11 (venv hermes-agent), pytest 9.1.1, PowerShell 5.1, git apply.

## Global Constraints

- PowerShell 5.1 only: no `&&`/`||` chaining (`;` for sequencing), no `Select-Object -First` on infinite streams, `-LiteralPath` for paths.
- NEVER run `git reset --hard`, `git clean`, `git checkout .` in the live tree (`C:\Users\tiki\AppData\Local\hermes\hermes-agent`); never `git apply --reject`.
- Patch export covers EXACTLY these 9 paths (no `package-lock.json`, no new files this time): `agent/moa_loop.py`, `agent/moa_trace.py`, `agent/turn_request_assembly.py`, `hermes_cli/moa_cmd.py`, `hermes_cli/moa_config.py`, `agent/moa_auto_router.py`, `tests/agent/test_moa_auto_router.py`, `tests/agent/test_moa_auto_runtime.py`, `tests/hermes_cli/test_moa_cmd_auto.py`.
- Tests run via `C:\Users\tiki\Documents\Hermes-auto-moa-recovery\run-moa-tests.bat` (fresh `--basetemp`, no cache provider) or the same venv pytest flags.
- After any live-tree edit: `SHA256SUMS.txt` refresh, `ALL FRESH` check, `hermes-update.bat --check` → HEALTHY (warning-free), commit in the recovery repo only.
- Live tree keeps working state uncommitted by design (it IS the patch source); recovery repo commits are the snapshots.
- Do NOT touch `peel_reference_guidance` / `peel` shapes, `state.db`, or any `C:/Fantrax` tree.

---

## File Structure

Modify:
- `C:\Users\tiki\AppData\Local\hermes\hermes-agent\agent\moa_loop.py` — prompt clause (Task 1), detector + wiring (Tasks 2–3).
- `C:\Users\tiki\AppData\Local\hermes\hermes-agent\tests\agent\test_moa_auto_runtime.py` — append tests (Tasks 1–3).
- `C:\Users\tiki\Documents\Hermes-auto-moa-recovery\auto-moa-current.patch` — re-export (Task 4).
- `C:\Users\tiki\Documents\Hermes-auto-moa-recovery\SHA256SUMS.txt` — refresh (Task 4).

No new files. Detector lives in `moa_loop.py` next to `_join_reference_outputs` (single responsibility: text scrubbing; no I/O, no logging except a debug line).

**Interfaces:**
- ` _scrub_unverified_tool_claims(text: str, context_text: str) -> tuple[str, int, int]` — Task 2 produces; Task 3 consumes. Returns `(scrubbed_text, removed_count, marked_count)`.
- `_REFERENCE_SYSTEM_PROMPT` — Task 1 appends the anti-fabrication clause; Task 2 tests do not depend on its wording, only Task 1's test does.

---

### Task 1: Anti-fabrication clause in the advisor system prompt

**Files:**
- Modify: `C:\Users\tiki\AppData\Local\hermes\hermes-agent\agent\moa_loop.py` (append to `_REFERENCE_SYSTEM_PROMPT`, ~line 257).
- Test: `C:\Users\tiki\AppData\Local\hermes\hermes-agent\tests\agent\test_moa_auto_runtime.py` (append).

**Interfaces:**
- Consumes: nothing new.
- Produces: prompt text containing the `VERIFIED`/`INFERRED` contract (Task 2's detector is independent of wording).

- [ ] **Step 1: Write the failing test**

```python
def test_reference_system_prompt_bans_tool_output_fabrication():
    from agent.moa_loop import _REFERENCE_SYSTEM_PROMPT

    assert "VERIFIED" in _REFERENCE_SYSTEM_PROMPT
    assert "INFERRED" in _REFERENCE_SYSTEM_PROMPT
    assert "[called tool" in _REFERENCE_SYSTEM_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:\Users\tiki\AppData\Local\hermes\hermes-agent\.venv\Scripts\python.exe -m pytest tests/agent/test_moa_auto_runtime.py::test_reference_system_prompt_bans_tool_output_fabrication -p no:cacheprovider --basetemp="C:\Users\tiki\AppData\Local\Temp\opencode\ptest-plan1" -q` (workdir: hermes-agent)
Expected: FAIL with `AssertionError` on `"VERIFIED" in ...`.

- [ ] **Step 3: Append the clause to the prompt**

In `agent/moa_loop.py`, extend the `_REFERENCE_SYSTEM_PROMPT` tuple with this exact string (append as a new element before the closing paren):

```python
    "Provenance contract — obey it exactly. Split your response into two "
    "sections with these exact headings:\n"
    "VERIFIED: only claims directly supported by a quote from the conversation "
    "above (quote the supporting words).\n"
    "INFERRED: hypotheses, guesses, and recommendations — mark every uncertain "
    "claim with [uncertain].\n"
    "You MUST NEVER emit text shaped like a tool result: no lines starting "
    "with '[called tool:', no '[tool result' blocks, no JSON with exit_code / "
    "stdout / containerTag fields, no PIDs/ports/statuses of commands you did "
    "not run. If you need to reference a tool result from the conversation, "
    "quote it verbatim under VERIFIED instead of re-rendering it."
```

- [ ] **Step 4: Run test to verify it passes**

Run: same command as Step 2.
Expected: PASS.

- [ ] **Step 5: Run the MoA suite (no regressions)**

Run: `C:\Users\tiki\Documents\Hermes-auto-moa-recovery\run-moa-tests.bat`
Expected: exit 0, all tests pass (count printed at tail).

---

### Task 2: Pure detector `_scrub_unverified_tool_claims`

**Files:**
- Modify: `C:\Users\tiki\AppData\Local\hermes\hermes-agent\agent\moa_loop.py` (insert after `_join_reference_outputs`, ~line 816).
- Test: `C:\Users\tiki\AppData\Local\hermes\hermes-agent\tests\agent\test_moa_auto_runtime.py` (append).

**Interfaces:**
- Consumes: advisor text + flattened advisory-view text (both `str`).
- Produces: `_scrub_unverified_tool_claims(text, context_text) -> tuple[str, int, int]` = `(scrubbed, removed, marked)` for Task 3.

Detection rule (exact): a line starts a tool-shaped block if it matches any of
`^\s*\[called tool:`, `^\s*\[tool result`, `containerTag\s*[:=]`, `"\s*exit_code\s*"\s*:`.
Each matching line is judged on its own as a single-line block (deliberately NOT grouped with following lines: grouping merged adjacent markers plus trailing prose into one block and ate legitimate advice in the spec's own tests).
Naked check: collapse whitespace in the line and in `context_text`; if the line is NOT a substring → cut, replace with `[removed unverified tool-output claim]`, `removed += 1`. Else wrap the line as `[UNVERIFIED-CLAIM, quoted from context — not executed by the advisor]` + the line, `marked += 1`. Text without markers returns unchanged with `(0, 0)`.

- [ ] **Step 1: Write the failing tests**

```python
_FABRICATED_ECHO = (
    "Совет: проверь статус.\n"
    '[called tool: terminal({"command":"curl localhost:3001"})]\n'
    '[tool result]: {"output": "200 OK"}\n'
    "Дальше действуй сам."
)

_QUOTED_ECHO = (
    "Совет: как видишь выше.\n"
    '[tool result]: {"output": "ok"}\n'
    "Повторяю вывод из контекста."
)


def test_scrub_cuts_naked_tool_blocks():
    from agent.moa_loop import _scrub_unverified_tool_claims

    scrubbed, removed, marked = _scrub_unverified_tool_claims(
        _FABRICATED_ECHO, "совершенно другой контекст без этих строк"
    )
    assert removed == 2
    assert marked == 0
    assert "[called tool:" not in scrubbed
    assert "[removed unverified tool-output claim]" in scrubbed
    assert "Дальше действуй сам." in scrubbed


def test_scrub_marks_but_keeps_quoted_blocks():
    from agent.moa_loop import _scrub_unverified_tool_claims

    ctx = 'лог хода: [tool result]: {"output": "ok"} конец лога'
    scrubbed, removed, marked = _scrub_unverified_tool_claims(_QUOTED_ECHO, ctx)
    assert removed == 0
    assert marked == 1
    assert "[UNVERIFIED-CLAIM" in scrubbed
    assert '{"output": "ok"}' in scrubbed


def test_scrub_leaves_clean_advice_untouched():
    from agent.moa_loop import _scrub_unverified_tool_claims

    text = "VERIFIED: пользователь просит починить парсер.\nINFERRED: вероятно, дело в кавычках [uncertain]."
    assert _scrub_unverified_tool_claims(text, "другой контекст") == (text, 0, 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `...\.venv\Scripts\python.exe -m pytest tests/agent/test_moa_auto_runtime.py -p no:cacheprovider --basetemp="C:\Users\tiki\AppData\Local\Temp\opencode\ptest-plan2" -q -k "scrub_"` (workdir: hermes-agent)
Expected: FAIL with `ImportError`/`AttributeError` (no such function).

- [ ] **Step 3: Implement the detector**

Insert after `_join_reference_outputs` in `agent/moa_loop.py`:

```python
_TOOL_CLAIM_RES = (
    re.compile(r"^\s*\[called tool:"),
    re.compile(r"^\s*\[tool result"),
    re.compile(r"containerTag\s*[:=]"),
    re.compile(r"\"\s*exit_code\s*\"\s*:"),
)
_REMOVED_TOOL_CLAIM_NOTE = "[removed unverified tool-output claim]"


def _scrub_unverified_tool_claims(text: str, context_text: str) -> tuple[str, int, int]:
    """Cut tool-shaped blocks the advisor could not have quoted, mark the rest.

    A block matching _TOOL_CLAIM_RES is 'quoted' only if its whitespace-collapsed
    text is a substring of the collapsed advisory input; quoted blocks are kept
    with an [UNVERIFIED-CLAIM ...] wrapper, naked ones are cut. Returns
    ``(scrubbed_text, removed_count, marked_count)``. Pure function, no I/O.
    """
    if not isinstance(text, str) or not text:
        return text, 0, 0
    collapsed_context = " ".join(str(context_text or "").split())
    lines = text.splitlines()
    out: list[str] = []
    removed = 0
    marked = 0
    index = 0
    while index < len(lines):
        if any(rx.search(lines[index]) for rx in _TOOL_CLAIM_RES):
            # Single-line blocks (see Detection rule above for why).
            block = [lines[index]]
            index += 1
            collapsed_block = " ".join(" ".join(block).split())
            if collapsed_block and collapsed_block in collapsed_context:
                out.append(
                    "[UNVERIFIED-CLAIM, quoted from context — not executed "
                    "by the advisor]"
                )
                out.extend(block)
                marked += 1
            else:
                out.append(_REMOVED_TOOL_CLAIM_NOTE)
                removed += 1
        else:
            out.append(lines[index])
            index += 1
    if removed or marked:
        logger.debug(
            "MoA scrubbed unverified tool claims: removed=%d marked=%d",
            removed,
            marked,
        )
    return "\n".join(out), removed, marked
```

(`re` and `logger` already imported at module top of `moa_loop.py` — verify with `grep -n "^import re\|^import logging\|^logger" agent/moa_loop.py` before inserting; if missing, add the import in the same edit.)

- [ ] **Step 4: Run tests to verify they pass**

Run: same command as Step 2.
Expected: 3 passed.

- [ ] **Step 5: Run the MoA suite (no regressions)**

Run: `C:\Users\tiki\Documents\Hermes-auto-moa-recovery\run-moa-tests.bat`
Expected: exit 0.

---

### Task 3: Wire the detector into both guidance paths + aggregator header note

**Files:**
- Modify: `C:\Users\tiki\AppData\Local\hermes\hermes-agent\agent\moa_loop.py` (`_build_guidance` ~line 1339, `aggregate_moa_context` ~line 855).
- Test: `C:\Users\tiki\AppData\Local\hermes\hermes-agent\tests\agent\test_moa_auto_runtime.py` (append).

**Interfaces:**
- Consumes: `_scrub_unverified_tool_claims` from Task 2.
- Produces: scrubbed guidance on both paths; no signature changes to public functions.

- [ ] **Step 1: Write the failing test**

```python
def test_loop_guidance_scrubs_fabricated_tool_echo(tmp_path, monkeypatch):
    from agent.moa_loop import MoAChatCompletions

    calls = []

    def fake_call_llm(**kwargs):
        calls.append(kwargs.get("task"))
        if kwargs.get("task") == "moa_reference":
            return _response(
                "Совет.\n"
                '[called tool: terminal({"command":"doom"})]\n'
                "Конец."
            )
        return _response("acted")

    monkeypatch.setattr("agent.moa_loop.call_llm", fake_call_llm)

    facade = MoAChatCompletions("default")
    out = facade.create(
        model="default",
        messages=[{"role": "user", "content": "обычный вопрос"}],
    )

    assert calls.count("moa_reference") >= 1
    assert "[called tool:" not in out["messages"][-1]["content"]
    assert "[removed unverified tool-output claim]" in out["messages"][-1]["content"]
```

Note: this test needs a resolvable `default` preset without HERMES_HOME config — `create(model="default", ...)` uses `_resolve_preset_cached`, which falls back to defaults when no config file exists. If the fallback path raises in this environment, set `HERMES_HOME` to a `tmp_path` home exactly like `test_reference_max_tokens_absent_means_uncapped` does and use its `_write_auto_config` home. Check how `facade.create` returns: it returns the prepared/aggregator request dict whose `["messages"][-1]["content"]` carries the attached guidance (see `rebase_prepared_request`/`_attach_reference_guidance` shape (a)). If `create` returns the final response object instead, assert on the trace-independent path: call `facade._build_guidance` directly with a fabricated `reference_outputs` list and assert the scrubbed string. Prefer the direct `_build_guidance` assertion if the `create` shape differs — read `_call_prepared_aggregator` return first.

- [ ] **Step 2: Run test to verify it fails**

Run: same pytest single-test command pattern as Task 1 Step 2 with `-k loop_guidance_scrubs`.
Expected: FAIL (`[called tool:` still present).

- [ ] **Step 3: Wire scrubbing into `_build_guidance`**

`_build_guidance` currently has no access to the advisory input text. Change its body (not its public callers' expectations): it already receives `self`; the advisory messages are NOT on self. Minimal approach without signature churn across the codebase: scrub per-reference text against the flattened guidance context available at the call site. Concretely, in `create()` where `guidance = self._build_guidance(reference_outputs, ...)` is computed (~line 1510), `ref_messages` is in scope: flatten it with the existing `_text_content`-style helper (`flatten_message_text` from `agent.message_content`, already imported in `moa_loop.py` — verify import) into `advisory_text`, then scrub each successful reference output BEFORE `_build_guidance`:

```python
from agent.message_content import flatten_message_text as _flatten_for_scrub  # top of create(), next to other local imports — or reuse module import if present
advisory_text = "\n".join(
    _flatten_for_scrub(m.get("content")) for m in ref_messages if isinstance(m, dict)
)
scrubbed_outputs = []
for label, ref_text, acct in reference_outputs:
    clean, _, _ = _scrub_unverified_tool_claims(ref_text, advisory_text)
    scrubbed_outputs.append((label, clean, acct))
guidance = self._build_guidance(scrubbed_outputs, aggregator, str(preset.get("degraded_reference_policy") or "loud"))
```

And in `aggregate_moa_context`, apply the same scrub to `reference_outputs` right after `_run_references_parallel` returns (advisory text = flattened `ref_messages` variable already in scope there — verify name; it is the second positional arg passed to `_run_references_parallel`).

Also append one sentence to the `_build_guidance` header after `"answer the user directly or call tools as needed.\n\n"`:

```python
"Reference responses are unverified advisor opinions; blocks marked "
"[UNVERIFIED-CLAIM] were not executed by anyone — verify with tools "
"before acting on them.\n\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: same single-test command.
Expected: PASS.

- [ ] **Step 5: Run the MoA suite (no regressions)**

Run: `C:\Users\tiki\Documents\Hermes-auto-moa-recovery\run-moa-tests.bat`
Expected: exit 0.

---

### Task 4: Re-export patch, verify, commit

**Files:**
- Modify ( regenerate ): `C:\Users\tiki\Documents\Hermes-auto-moa-recovery\auto-moa-current.patch` (same 9 paths, no new files).
- Modify: `C:\Users\tiki\Documents\Hermes-auto-moa-recovery\SHA256SUMS.txt` (first line only).
- No doc edits unless behavior changes beyond the above.

**Interfaces:**
- Consumes: green suite from Task 3.
- Produces: committed patch + fresh SHA + HEALTHY gate.

- [ ] **Step 1: Re-export the patch byte-exact**

Run (workdir: hermes-agent; PowerShell 5.1 — no `&&`):

```powershell
C:\Python314\python.exe -c "import subprocess; r=subprocess.run(['git','diff','--','agent/moa_loop.py','agent/moa_trace.py','agent/turn_request_assembly.py','hermes_cli/moa_cmd.py','hermes_cli/moa_config.py','agent/moa_auto_router.py','tests/agent/test_moa_auto_router.py','tests/agent/test_moa_auto_runtime.py','tests/hermes_cli/test_moa_cmd_auto.py'],capture_output=True,cwd=r'C:\Users\tiki\AppData\Local\hermes\hermes-agent'); open(r'C:\Users\tiki\Documents\Hermes-auto-moa-recovery\auto-moa-current.patch','wb').write(r.stdout); print(len(r.stdout))"
```

Expected: byte count > previous 64369; `grep -c "^diff --git"` on the patch prints `9`.

- [ ] **Step 2: Verify both directions**

Run (workdir: hermes-agent):

```powershell
git apply --reverse --check "C:\Users\tiki\Documents\Hermes-auto-moa-recovery\auto-moa-current.patch"; echo "reverse:$?"
git worktree add --detach "C:\Users\tiki\AppData\Local\Temp\opencode\patchverify-af" 9fd44b4df
git -C "C:\Users\tiki\AppData\Local\Temp\opencode\patchverify-af" apply --check "C:\Users\tiki\Documents\Hermes-auto-moa-recovery\auto-moa-current.patch"; echo "clean:$?"
```

Expected: both `True`. Then run the 4 MoA test files inside `patchverify-af` with the venv python (`--basetemp` under `Temp\opencode`, `-p no:cacheprovider`), expect all pass; then `git worktree remove --force` + `Remove-Item` fallback + `git worktree prune`.

- [ ] **Step 3: Refresh SHA and verify freshness**

Run (workdir: recovery repo): recompute only the `*auto-moa-current.patch` line of `SHA256SUMS.txt`, then run the full-file check (every line must match). Expected: `ALL FRESH`.

- [ ] **Step 4: Final gates and commit**

Run: `hermes-update.bat --check` (expect `HEALTHY`, no warnings), `python tools/moa_sync.py --check` (expect `PASS`), `git status --short` (expect exactly `M auto-moa-current.patch`, `M SHA256SUMS.txt`). Then:

```powershell
git add auto-moa-current.patch SHA256SUMS.txt
git commit -m "feat(moa): anti-fabrication contract + tool-claim scrubber on both guidance paths"
git push origin main
```

Expected: push prints `main -> main`, `git status -sb` shows `## main...origin/main` with no `ahead`.
