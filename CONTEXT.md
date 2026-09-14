# CONTEXT — Hermes auto_moa recovery kit

The domain language of this repo. Terms here give names to seams; they are not
architecture vocabulary. The architecture words (**module**, **interface**,
**implementation**, **depth**, **seam**, **adapter**, **leverage**, **locality**) come
from the design skill and attach to the things named below.

## The system under repair

**Hermes live tree** — `%LOCALAPPDATA%\hermes\hermes-agent`. A git checkout whose
*working state* is the source of truth for the recovery patch. It is deliberately
never committed: the diff against upstream HEAD **is** the patch source.

**Live profile** — one Hermes configuration root: `%LOCALAPPDATA%\hermes\config.yaml`
(the `default` profile) or `%LOCALAPPDATA%\hermes\profiles\<name>\config.yaml`.

**Fleet** — the live profiles together: `default`, `mxstat`, `fantrax`, `aiqa`,
`auto-moa`, plus `local-llm-lab`, which is a profile but *not* a MoA profile.

**Canon** — `auto-moa-moa-section.yaml`: the canonical MoA graph, twelve presets.
`profile_overrides` inside the canon express per-profile deviations, merged at sync
time. The canon is hand-reviewable data, not generated output.

**auto-MoA layer** — the custom MoA behaviour this kit re-establishes after an
upstream update: the category auto-router, the anti-fabrication scrubber, preset
normalisation, and the per-advisor trace fields.

## The recovery machinery

**Patch scope** — the nine live-tree paths the recovery patch touches. Every other
path in the live tree must stay clean. Declared once, in `recovery_integrity`. It
used to be declared a second time as the allowlist in `tools/live_tree_check.py`;
that module is absorbed and deleted, so the nine paths exist in one place.

**Recovery patch** — `auto-moa-current.patch`: a byte-exact export of the live tree's
diff against upstream HEAD, limited to the patch scope.

**Sealed artifact** (a **seal**) — an artifact whose exact bytes are recorded in
`SHA256SUMS.txt` and whose git treatment is declared in `.gitattributes`. A seal's
unit is *the bytes a fresh checkout produces*, not the bytes currently on disk: the
two differ wherever git normalises line endings, so a seal can look fresh locally
and be broken in a clone.

**The sealed set** — runtime and restore-critical bytes: the recovery patch, the
canon, the wrapper scripts (`.bat` / `.sh`) and the tools. Documentation and meta
files (`README.md`, `USER_GUIDE_RU.txt`, `.gitattributes`, `SHA256SUMS.txt`) sit
deliberately outside the seal, so a docs edit never carries reseal churn.

**Reseal** — recompute and record a seal after an intended change. It only ever
follows an intended change.

**Drift** — reality and intent disagree. Three flavours, each with its own repair:

- **stale seal** — a sealed artifact changed without a reseal;
- **live-tree noise** — a path outside the patch scope is dirty;
- **patch drift** — the patch no longer reverse-applies, so the live tree and the
  export disagree about the same nine paths.

**Verify** — `verify()` reports drift graded by flavour. The three flavours above
**block** (non-zero exit); unknown-but-harmless details warn.

**Check and repair** — `--check` reads and never writes, and it is the flavour that
blocks. `--repair` / `--sync` write. `hermes-update.bat` drives both, and its
`:repair` branch is what the cron watchdog runs unattended — so repair *consumes*
the same report and proceeds, refusing only when the patch cannot be applied at
all. Repairing drift is what repair is for; blocking it would wedge the watchdog.
See [ADR 0001](docs/adr/0001-block-on-check-not-repair.md).

**Two different questions** — integrity asks *are our bytes what we sealed?*
(seals, patch applicability, live-tree noise). Config drift asks *does the live
graph equal the canon?*, which is `moa_sync --check`'s question. They stay separate
modules; `hermes-update.bat` composes both.
