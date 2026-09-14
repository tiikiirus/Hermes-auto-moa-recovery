# 0001 — Integrity drift blocks the check, never the repair

- **Status:** accepted
- **Date:** 2026-09-11
- **Deciding context:** architecture review of the recovery kit, candidate *Give integrity one owner*

## Context

`hermes-update.bat` has two branches: `:check`, which reads, and `:repair`, which
applies the recovery patch and re-syncs the MoA graph. The cron watchdog runs the
repair branch **unattended, every 60 minutes**.

Three flavours of drift are detectable:

- **stale seal** — a sealed artifact changed without a reseal;
- **live-tree noise** — a path outside the nine-path patch scope is dirty;
- **patch drift** — the patch no longer reverse-applies, so the live tree and the
  export disagree about the same nine paths.

Today all three only print `WARNING` lines: `:check` exits 0 and still prints
`HEALTHY`. Observed consequence on 2026-09-11: a stale ledger entry survived a whole
session unnoticed, and the stale patch (a test file grew after the last export) was
found only because someone ran `git apply --reverse --check` by hand.

## Decision

`verify()` grades drift by flavour, and the three flavours above **block** — non-zero
exit — on the read-only check. The repair path **consumes the same report and
proceeds**, refusing only when the patch cannot be applied at all.

## Why not the alternatives

- **Repair refusing on any drift.** Fail-safe, but it wedges the unattended watchdog
  exactly when repair is needed. Converging a drifted tree is what repair is for.
- **Warnings only (status quo).** Drift stays something a human must notice — which
  is precisely how both 2026-09-11 failures escaped.

## Consequences

- `:check` can now fail an unattended run. That is the intent: the failure is
  actionable in three specific ways (reseal, clear noise, re-export the patch).
- The block must never be enforced *inside a writer*, or a stale patch could not be
  re-exported by the very tool that detects the staleness.
- Anyone re-proposing "repair should refuse too" should answer the watchdog question
  first: what does the 60-minute unattended run do when the patch is stale?
