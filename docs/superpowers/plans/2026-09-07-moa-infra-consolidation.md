# MoA Infra Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify everything landed in the MoA sessions of 2026-09-01…07, close the four known open items, and leave both trees clean with proof.

**Architecture:** No new architecture. This plan consolidates: read-only verification of landed work (router, reasoning, dedup, monitor), three small closes (fantrax live proof, gate diagnosis, restore safety), one user decision (pay escalation), docs + commits.

**Tech Stack:** Windows PowerShell 5.1, Python 3.14 (stdlib + PyYAML via hermes-agent `.venv`), pytest 9.1.1, `hermes` CLI, git.

## Global Constraints

- PowerShell 5.1 only: no `&&` chaining, no `Select-Object -First` on infinite streams; use `;` for sequencing and `-LiteralPath` for paths.
- Never print secrets: tokens/keys are `[REDACTED]`; check only presence/length/metadata.
- Live SQLite DBs: copy backup first (`state.db.<reason>-<date>.bak` next to the DB), `sqlite3` timeout 30, `PRAGMA integrity_check` after writes.
- No live-tree code change without focused pytest green + `hermes-update.bat --check` → HEALTHY afterwards.
- Recovery-repo commit only when `git status` shows exactly the intended files.
- Console renders non-ASCII as mojibake: verify text edits by byte/hash comparison or targeted reads, never by eyeballing Cyrillic in PS output.

---

## File Structure

Modify (only if its task executes):
- `C:\Users\tiki\Documents\Hermes-auto-moa-recovery\restore-auto-moa-after-update.bat` — preserve per-profile `default_preset` on graph restore + warn on divergence (Task 8).
- `C:\Users\tiki\Documents\Hermes-auto-moa-recovery\README.md` — only if Task 7 picks escalation (aggregator table).
- Live profile configs — only if Task 7 picks escalation (pay aggregator model strings).

Read-only references (never modify in this plan):
- `C:\Users\tiki\AppData\Local\hermes\hermes-agent\agent\moa_auto_router.py`, `agent\moa_loop.py`
- `%LOCALAPPDATA%\hermes\profiles\*\moa-traces\*.jsonl` (evidence)
- `%LOCALAPPDATA%\hermes\profiles\*\state.db` (reads; writes only via Task 4 re-verification if needed — none expected)

---

### Task 1: Verify trees, patch equivalence, self-healing health

**Files:** none modified.

**Interfaces:**
- Consumes: nothing.
- Produces: HEALTHY signal + patch hash used by Task 9.

- [ ] **Step 1: Confirm both trees clean**

```powershell
git -C "C:\Users\tiki\Documents\Hermes-auto-moa-recovery" status --short
git -C "$env:LOCALAPPDATA\hermes\hermes-agent" status --short
```

Run: both commands.
Expected: both print nothing (empty = clean). If either prints lines, stop and report — do not proceed.

- [ ] **Step 2: Prove patch file equals live diff**

```powershell
git -C "$env:LOCALAPPDATA\hermes\hermes-agent" diff "e60983a69" HEAD --output="C:\Users\tiki\AppData\Local\Temp\opencode\live_diff_check.patch"
```

Run: command above, then compare hashes:

```powershell
(Get-FileHash -LiteralPath "C:\Users\tiki\AppData\Local\Temp\opencode\live_diff_check.patch" -Algorithm SHA256).Hash
(Get-FileHash -LiteralPath "C:\Users\tiki\Documents\Hermes-auto-moa-recovery\auto-moa-current.patch" -Algorithm SHA256).Hash
```

Expected: identical hashes. Rationale: recovery patch must be a byte-exact export of the live commits, otherwise `--check` lies.

- [ ] **Step 3: Self-healing check**

```powershell
& "C:\Users\tiki\Documents\Hermes-auto-moa-recovery\hermes-update.bat" --check
```

Expected: `[auto-moa] HEALTHY`.

---

### Task 2: Focused pytest suite green

**Files:** none modified.

**Interfaces:**
- Consumes: nothing.
- Produces: pass count for the record.

- [ ] **Step 1: Run the exact focused list from the restore script**

```powershell
& "C:\Users\tiki\AppData\Local\hermes\hermes-agent\.venv\Scripts\python.exe" -m pytest tests/agent/test_moa_auto_router.py tests/agent/test_moa_empty_reference.py tests/agent/test_moa_route_relay.py tests/hermes_cli/test_moa_config.py tests/hermes_cli/test_moa_auto_route.py -q
```

Run in workdir: `C:\Users\tiki\AppData\Local\hermes\hermes-agent`.
Expected: `85 passed`. If any fail, stop and report the failing test name — do not continue to config tasks.

---

### Task 3: Configs — 12 presets, valid, no dead names

**Files:** none modified.

**Interfaces:**
- Consumes: nothing.
- Produces: per-profile preset counts for Task 9 commit message if needed.

- [ ] **Step 1: CLI check on all four configs**

```powershell
hermes -p mxstat config check
hermes -p fantrax config check
hermes -p aiqa config check
hermes config check
```

Expected: each exits 0 (verify with `$LASTEXITCODE` after each; any non-zero stops the plan).

- [ ] **Step 2: Preset census**

```powershell
hermes -p mxstat moa list
hermes -p fantrax moa list
```

Expected: 12 preset names each; the string `auto_moa` appears only inside `pay_auto_moa`/`free_auto_moa` (no standalone `auto_moa` line). fantrax header reads `Default: free_auto_moa`, mxstat header `Default: pay_auto_moa`.

---

### Task 4: Sessions migration still holds

**Files:** none modified (backups `state.db.preset-dedup-20260907.bak` already exist next to each DB).

**Interfaces:**
- Consumes: nothing.
- Produces: leftover counts (must be zero).

- [ ] **Step 1: Count leftovers (read-only)**

```powershell
C:\Python314\python.exe C:\Users\tiki\AppData\Local\Temp\opencode\migrate_sessions.py
```

Expected output ends with `leftover model=0 cfg=0` for aiqa, fantrax, mxstat (DRY-RUN mode makes no writes). `integrity=ok` for aiqa; fantrax/mxstat report a pre-existing FTS trigram warning — known, out of scope, do not touch FTS tables.

- [ ] **Step 2: Backups present**

```powershell
Get-ChildItem -LiteralPath "C:\Users\tiki\AppData\Local\hermes\profiles\mxstat","C:\Users\tiki\AppData\Local\hermes\profiles\aiqa","C:\Users\tiki\AppData\Local\hermes\profiles\fantrax" -Filter "state.db.preset-dedup-20260907.bak"
```

Expected: 3 files listed. If any missing, stop — migration evidence is incomplete.

---

### Task 5: fantrax routing live proof

**Files:** none modified. **Cost note:** one real turn ≈ $0.01 — this is the only spending step in Phases A–B.

**Interfaces:**
- Consumes: fantrax `free_auto_moa` graph (aligned 2026-09-07).
- Produces: trace record proving routing (used by Task 9 summary).

- [ ] **Step 1: Send a code question through the fantrax router**

```powershell
hermes -p fantrax -z "напиши функцию сортировки списка python" --provider moa -m free_auto_moa --cli
```

Expected: a normal answer (any text). Cost ≈ $0.01 on flash models.

- [ ] **Step 2: Confirm the turn routed (not fallback)**

Write the checker (PowerShell 5.1 has no `ConvertFrom-Json -Depth`, so use a file):

```python
import json
import sys

line = open(sys.argv[1], encoding="utf-8").read().strip().splitlines()[-1]
r = json.loads(line)
print(r.get("preset"))
print((r.get("routing") or {}).get("category"))
print((r.get("routing") or {}).get("complexity"))
```

Save as: `C:\Users\tiki\AppData\Local\Temp\opencode\trace_check.py`. Then run:

```powershell
$latest = Get-ChildItem -LiteralPath "C:\Users\tiki\AppData\Local\hermes\profiles\fantrax\moa-traces" -Filter "*.jsonl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
C:\Python314\python.exe C:\Users\tiki\AppData\Local\Temp\opencode\trace_check.py $latest.FullName
```

Expected three lines: `code_logic_deep`, `code`, complexity tier (`standard` for this short question). If preset is `default`/fallback instead, the alignment did not take — stop and report.

---

### Task 6: Diagnose the monitor gate 401

**Files:** none modified (diagnosis only; fix is a follow-up pending findings).

**Interfaces:**
- Consumes: monitor output.
- Produces: root cause (expired token vs endpoint/scope) + verdict: patchable now or parked for interactive re-login.

- [ ] **Step 1: Reproduce the silence-turned-loud**

```powershell
& "C:\Users\tiki\Documents\Hermes-auto-moa-recovery\check-moa-models.bat" | Select-String -Pattern "account gate" -Context 0,4
```

Expected: the `account gate: UNAVAILABLE (portal check failed ...)` block (shipped 2026-09-07). If a real gate line with `paid_access=` appears instead, the portal healed itself — record that and skip to Step 3.

- [ ] **Step 2: Read token metadata (never the token)**

```powershell
C:\Python314\python.exe C:\Users\tiki\AppData\Local\Temp\opencode\probe_latest.py
```

Expected: prints key names, `expires_at`, `scope` (currently `inference:invoke`, expired 2026-09-01) — no secret values. Verdict rule: if a fresh token exists anywhere with a portal scope, the fix is switching the gate check to it; if all tokens are `inference:invoke`-scoped, the portal endpoint needs either a new endpoint path (check `https://portal.nousresearch.com/` docs) or an interactive Desktop re-login — in both cases park the fix and report, do not guess URLs into the monitor.

- [ ] **Step 3: Record verdict**

Write the verdict (one paragraph: cause + fixable-now vs parked) into the final summary of Task 9. No code change in this task.

---

### Task 7: Pay escalation decision (user gate)

**Files (only the chosen variant):** live profile configs + recovery `README.md` aggregator table.

**Interfaces:**
- Consumes: one week of spend data (portal UI) + redo-rate impression from the user.
- Produces: either no change, or new pay aggregator model strings everywhere consistently.

Context (measured 2026-09-07): ping turn via `glm-5.3-flash` cost $0.00004; heavy turn ≈ $0.015; $22 ≈ a thousand heavy turns. Flagship models cost tens of times more.

- [ ] **Step 1: Ask the user to pick a variant**

Variants: (a) keep flash aggregators everywhere (current, cheapest); (b) strong aggregator (e.g. Claude Sonnet / GPT / Gemini — exact model named by user) for anchor hard tasks only, flash stays default; (c) strong aggregator as pay-panel default.
Recommendation: (b) — one precise strong turn beats three weak redos, total spend stays far under $22.

- [ ] **Step 2: Apply ONLY the chosen variant**

Variant (a): change nothing, record decision in Task 9 summary.
Variant (b)/(c): replace the aggregator `model:` string in the 5 pay presets (`pay_default`, `pay_code_logic_deep`, `pay_logic_deep`, `pay_code_visual_deep`, `pay_logic_visual_deep` — NOT the router `pay_auto_moa`, which only carries dead-weight mirrored slots) in all 4 live configs + backup yaml, using the exact model id the user named. Then re-run Task 3 Step 1 (config check exit 0 on all four) and the Task 2 suite (unaffected files, must stay green).

- [ ] **Step 3: Keep the receipt**

Record the chosen model id and the measured first-bill spend (portal UI) in the Task 9 summary.

---

### Task 8: Restore preserves per-profile default_preset

**Files:**
- Modify: `C:\Users\tiki\Documents\Hermes-auto-moa-recovery\restore-auto-moa-after-update.bat`
- Test: temp copies only, never live configs.

**Interfaces:**
- Consumes: current restore one-liner (line ~88).
- Produces: restore that syncs the graph without flipping the profile default, warning on divergence.

Background: restore does `d['moa']=s['moa']` wholesale, so a future fantrax restore would flip its `default_preset: free_auto_moa` to the backup's `default`. Same for mxstat's `pay_auto_moa`.

- [ ] **Step 1: Prove the clobber on a temp copy (failing test)**

```powershell
Copy-Item -LiteralPath "C:\Users\tiki\AppData\Local\hermes\profiles\fantrax\config.yaml" -Destination "C:\Users\tiki\AppData\Local\Temp\opencode\restore_dryrun.yaml"
C:\Python314\python.exe -c "import sys,yaml; from pathlib import Path; p=Path(sys.argv[1]); b=Path(sys.argv[2]); d=yaml.safe_load(p.read_text(encoding='utf-8')) or {}; s=yaml.safe_load(b.read_text(encoding='utf-8')) or {}; d['moa']=s['moa']; p.write_text(yaml.safe_dump(d,sort_keys=False,allow_unicode=True),encoding='utf-8')" "C:\Users\tiki\AppData\Local\Temp\opencode\restore_dryrun.yaml" "C:\Users\tiki\Documents\Hermes-auto-moa-recovery\auto-moa-moa-section.yaml"
C:\Python314\python.exe -c "import yaml; print(yaml.safe_load(open(r'C:\Users\tiki\AppData\Local\Temp\opencode\restore_dryrun.yaml',encoding='utf-8'))['moa'].get('default_preset'))"
```

Expected: prints `default` — proving the live `free_auto_moa` default gets clobbered. (This is the red test.)

- [ ] **Step 2: Minimal fix in the .bat**

Replace the restore one-liner so it carries the profile default across and warns on divergence (single-quote style to match the existing `.bat` line):

```python
import sys,yaml; from pathlib import Path; p=Path(sys.argv[1]); b=Path(sys.argv[2]); d=yaml.safe_load(p.read_text(encoding='utf-8')) or {}; s=yaml.safe_load(b.read_text(encoding='utf-8')) or {}; keep=(d.get('moa') or {}).get('default_preset'); d['moa']=s['moa']; d['moa']['default_preset']=keep or s['moa'].get('default_preset'); bd=(s.get('moa') or {}).get('default_preset'); print('[auto_moa] kept profile default_preset=%s (backup has %s)' % (d['moa'].get('default_preset'), bd)) if keep and keep != bd else None; p.write_text(yaml.safe_dump(d,sort_keys=False,allow_unicode=True),encoding='utf-8')
```

- [ ] **Step 3: Re-run Step 1 against the fixed logic**

Copy a fresh temp copy, run the NEW snippet, print `default_preset`.
Expected: `free_auto_moa` preserved + warning line printed. Then delete both temp files.

---

### Task 9: Docs consistency + final commit

**Files:**
- Modify: recovery `README.md` only if Task 7 changed aggregators; otherwise none.
- Commit: recovery repo.

**Interfaces:**
- Consumes: outputs of Tasks 1–8.
- Produces: clean trees + commit hash quoted in the closing summary.

- [ ] **Step 1: Consistency scan**

Search recovery `README.md` for a standalone `auto_moa` preset reference (excluding `[auto_moa]` log tags, `auto-moa-*.bat` filenames, `auto_moa_router.py`).

Expected: none found. (The `/model moa:auto_moa` instruction was already switched to `free_auto_moa` on 2026-09-07.)

- [ ] **Step 2: Final gates**

```powershell
& "C:\Users\tiki\Documents\Hermes-auto-moa-recovery\hermes-update.bat" --check
git -C "C:\Users\tiki\Documents\Hermes-auto-moa-recovery" status --short
```

Expected: `[auto-moa] HEALTHY`, then commit with exactly the intended files (if README changed; the .bat change from Task 8 always commits):

```powershell
git -C "C:\Users\tiki\Documents\Hermes-auto-moa-recovery" add restore-auto-moa-after-update.bat README.md SHA256SUMS.txt
```

Note: `SHA256SUMS.txt` MUST be refreshed for `restore-auto-moa-after-update.bat` after the Task 8 edit (it is checksummed; stale lines were already bitten once on 2026-09-07):

```powershell
$dir = "C:\Users\tiki\Documents\Hermes-auto-moa-recovery"
$h = (Get-FileHash -LiteralPath (Join-Path $dir "restore-auto-moa-after-update.bat") -Algorithm SHA256).Hash.ToLower()
$sha = Join-Path $dir "SHA256SUMS.txt"
$lines = Get-Content -LiteralPath $sha
$lines = $lines -replace "^[0-9a-f]{64}(\s+\*restore-auto-moa-after-update\.bat)$", ($h + '$1')
$lines | Set-Content -LiteralPath $sha -Encoding Ascii
```

Then verify the whole file (every line must match its artifact — the 2026-09-07 incident was two stale lines at once):

```powershell
$dir = "C:\Users\tiki\Documents\Hermes-auto-moa-recovery"
$bad = 0
Get-Content -LiteralPath (Join-Path $dir "SHA256SUMS.txt") | ForEach-Object { if ($_ -match "^([0-9a-f]{64})\s+\*(.+)$") { $a = (Get-FileHash -LiteralPath (Join-Path $dir $Matches[2]) -Algorithm SHA256).Hash.ToLower(); if ($a -ne $Matches[1]) { Write-Output ("STALE: " + $Matches[2]); $bad++ } } }
if ($bad -eq 0) { Write-Output "ALL FRESH" }
```

Expected: `ALL FRESH`. Commit exactly the intended files.

- [ ] **Step 3: Closing summary**

Report: task verdicts 1–8, commit hash, remaining known issues (FTS trigram warnings pre-existing; gate fix parked/active per Task 6; pay spend after week one per Task 7).
