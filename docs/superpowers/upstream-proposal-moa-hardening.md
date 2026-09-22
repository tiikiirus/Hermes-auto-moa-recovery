# Upstream proposal: MoA hardening (fan-out ceiling + XML tool-call scrub)

Two small, generic, independently landable changes for the native MoA loop,
motivated by production incidents. No product-specific logic, no new config
surface in v1 (both use module constants + existing hooks).

## 1. Spend ceiling for `every_n` fan-out cadence

**Problem.** `fanout: every_n:N` bounds cost per turn only when the turn is
short. A 58-iteration tool loop ran 58 advisor fan-outs (measured in trace:
zero cache HITs across the turn is not required for the damage — the cadence
formula itself allows `floor((T-1)/N)+1`, i.e. 20 fan-outs at T=58, N=3, and
unbounded as T grows). Advisor spend is `O(T)` with no upper bound.

**Proposal.** Cap advisor fan-outs per user turn at `_MAX_FANOUTS_PER_TURN = 4`.
Past the ceiling every further iteration reuses the last guidance (the same
cache-HIT mechanism off-cadence iterations already use). Turns with T<=10 are
bit-identical; `user_turn`/`per_iteration` untouched; the counter resets on a
new user turn. Three regression tests: 13-iteration turn runs 4x, capped
iterations still carry guidance, per-turn reset.

**Effect on the measured fleet.** Profiles on `every_n:3` with median T=3 see
no change (2 fan-outs max); only extreme tails (T>10, previously up to
38 fan-outs at T=112) are cut to 4.

## 2. XML tool-call shape in the anti-fabrication scrubber

**Problem.** Advisors whose native tool syntax is XML echo fabricated calls
(`<longcat_tool_call>…<longcat_arg_key>…</longcat_tool_call>`). A blacklist of
bracket shapes (`[called tool:`, `[tool result:`, …) misses the XML family
entirely (measured: 0 hits on 3 fabricated blocks that reached the
aggregator).

**Proposal.** Add an opener pattern (`<\w*tool_call\b`) to the claim regexes
plus whole-block consumption through the closing tag for naked blocks
(multiline-fabrication rule already used for JSON payloads). Quoted blocks
keep the existing mark-not-cut path; prose lines starting with `<` outside a
block are untouched (verified: `<b>1 493</b> subscribers` passes through).
Four regression tests.

## Compatibility

Both changes are additive and fail-open. The ceiling only narrows an existing
cadence; the scrubber addition only extends an existing blocklist with a new
shape family. Neither changes trace schemas (the per-advisor counts ride the
existing accounting object), config keys, or CLI surface.

## Patches

Available on request as `git apply`-ready diffs against `agent/moa_loop.py`
(+ tests in `tests/agent/test_moa_auto_runtime.py`): the ceiling (~15 lines +
3 tests), the XML shape (~20 lines + 4 tests). Test evidence: full MoA suite
green (200 passed) on the proposer's tree.
