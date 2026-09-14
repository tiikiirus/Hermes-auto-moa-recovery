# Spike: auto-MoA as a plugin — skeleton

**Not installable. Do not copy into the live tree.**

This is the artifact behind the time-boxed spike in
[`docs/superpowers/plans/2026-09-11-moa-plugin-spike.md`](../../docs/superpowers/plans/2026-09-11-moa-plugin-spike.md).
Verdict in one line: auto-MoA cannot become a plugin today — MoA is a native virtual
provider that core special-cases, and the hook surface has no seam inside its fan-out or
guidance assembly. About 3% of the 715-line patch (the CLI additions) is plugin-shaped
today; the rest needs *generic* hook widenings proposed upstream.

## What each file is

| File | Purpose |
|---|---|
| `plugin.yaml` | Manifest in the shape `plugins/disk-cleanup/plugin.yaml` uses (`name`, `version`, `description`, `author`, `hooks`). |
| `__init__.py` | `register(ctx)` + the two registered hooks + the one working slice (`hermes automoa` CLI status). Stages that need a missing seam raise instead of pretending. |

## What works today, what is blocked

| Piece | Status | Blocked on |
|---|---|---|
| `hermes automoa` status subcommand | **Works** via `ctx.register_cli_command` | — |
| Anti-fabrication scrubber (patch Stage A) | Blocked | **W1**: needs `advisory_context` (the quote corpus) in the payload |
| Provenance quote schema (proposed Stage B) | Blocked | **W1** (same corpus) and **W2** (right to rewrite the guidance block) |
| Auto-router | Blocked | **W3**: no variant-selection point before fan-out |
| Preset normalization / config schema | Blocked, permanently | Core config schema — not plugin-extensible by design |
| MoA trace record shape | Blocked | Core record; only per-advisor *metrics* are plugin-visible today |

The skeleton makes the boundary observable rather than silent: on every `post_llm_call`
it checks for `role` / `advisory_context` in the payload and logs **one** warning per
missing field per process (`hermes-automoa spike: blocked, missing plugin surface [...]`).

## Install target, when it is real

```
~/.hermes/plugins/hermes-automoa/
```

That is the documented user-plugin directory, discovered by `PluginManager` alongside the
in-tree `plugins/`. It is deliberately outside the live tree: `tools/live_tree_check.py`
allowlists exactly the 9 patch files and reports every other path — including untracked
ones — as NOISE with exit code 1. Dropping this directory into
`hermes-agent/plugins/` would break the `CLEAN` gate and would start leaking into the next
patch export.

## Rejected alternative

Re-implementing MoA as a `plugins/model-providers/` provider (technical path exists:
`register_provider(ProviderProfile(...))` plus `ProviderProfile.create_client()`). Rejected
because it would be a duplicate of the native `provider: moa` rather than the same layer,
it would not inherit core's MoA special-cases (`should_use_direct_api_call`,
`_moa_client_consumes_prepared_request`, `_moa_reference_metrics_for_hook`), and it would
add a permanent public provider slug to inventory / model-switch / doctor / validate.
Details in §5 of the spike report.
