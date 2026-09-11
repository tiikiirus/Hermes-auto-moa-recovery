# Fantrax canary 2/6 — revert notes for 30fb6a4

Commit `30fb6a4` bundles two logical reasons by accident:

- **Hygiene** (unrelated to canary): `.gitattributes` + `tools/probes/moa_trace_toolclaim_scan.py` + `tools/probes/moa_fanout_spend_projection.py` + their two `SHA256SUMS.txt` lines (`f797…`, `00ad…`), plus the `fresh_bytes` fix for `-text` (`text: unset` must not be converted on `autocrlf=true` — without it 12/20 sealed files were false `stale`).
- **Canary**: `auto-moa-moa-section.yaml` (fantrax 6→2) + `profile_overrides_registry.yaml` (12→8, 2×canary) + its one `SHA256SUMS.txt` line (`fbc93bd2…`).

`git revert 30fb6a4` reverts all six files (verified: `git revert --no-commit HEAD` leaves `D profile_overrides_registry.yaml` + revert of hygiene). That is not a trivial canary revert.

## If the hard trigger fires (429 rate >2× baseline sustained 48h)

Do **not** `git revert 30fb6a4` alone. Use a partial revert:

```bash
git revert -n 30fb6a4
# keep hygiene — unstage and restore it
git restore --staged .gitattributes tools/probes/moa_trace_toolclaim_scan.py tools/probes/moa_fanout_spend_projection.py
git restore .gitattributes tools/probes/moa_trace_toolclaim_scan.py tools/probes/moa_fanout_spend_projection.py
# SHA256SUMS.txt is one file with three hunks; keep only the canon hunk reverted
# easiest: restore its hygiene hunks manually
git checkout HEAD -- SHA256SUMS.txt   # restores to post-canary SHA (with hygiene already)
# then re-apply only the canon revert
# (or just edit SHA256SUMS.txt: line for auto-moa-moa-section.yaml 799407a3… vs fbc93bd2…)
# Now commit the partial revert:
git commit -m "revert(moa): fantrax canary 2/6 -> 0 (keep hygiene)"
# and re-sync live:
python tools/moa_sync.py --sync
```

Easier if you have not yet pulled hygiene: `git checkout HEAD~1 -- .gitattributes tools/probes/moa_trace_toolclaim_scan.py tools/probes/moa_fanout_spend_projection.py SHA256SUMS.txt` after `git revert -n` then `git add` only canon+registry.

## Rule for the future

Atomic commit = one logical reason. Do not bundle unrelated `reseal`/`hygiene` with a `canary` even if they are ready at the same time. The canary commit must be trivially revertable with `git revert <sha>` alone. This file exists because `30fb6a4` violates that rule.

Baseline window for this canary: 7 days **before** `30fb6a4` timestamp, normalized as `429 rate = count / requests`, excluding the warm-up hours after the commit. See `profile_overrides_registry.yaml` canary entries.
