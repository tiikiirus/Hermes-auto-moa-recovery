# 0002 — Sealing the sealer: threat model for tooling integrity

- **Status:** accepted
- **Date:** 2026-09-25
- **Deciding context:** handoff 2026-09-25 open item — "`tooling_integrity`
  (sealing `recovery_integrity.py` itself): deferred, no threat model — needs
  one before building."

## Context

The byte-integrity zone is a self-referential loop: `verify()` reads
`SHA256SUMS.txt`, `SHA256SUMS.txt` seals `verify()`. Examining the loop produced
three facts:

1. `tools/recovery_integrity.py` **is** sealed — and so are `repair.py`,
   `doctor.py` and the gate scripts. The open item's literal ask was already true.
2. `_verify_seals` walks the *ledger*, so the ledger itself was the weak joint:
   delete (or mangle) a `SHA256SUMS.txt` line and the file it named became
   silently unsealed. Nothing checked that the sealed set was *complete*.
   `missing_seal` covers a missing *file*, not a missing *seal*.
3. No artifact inside the working tree can authenticate the ledger against a
   coherent two-sided edit (file changed **and** its digest re-sealed).
   `SHA256SUMS.txt` cannot contain its own digest, and `.gitattributes` —
   which defines the seal unit consumed by `fresh_bytes()` — sat outside the seal.

### Assets

- the recovery patch and the canon (what the kit exists to restore);
- the sealed tooling: verifier, sync, doctor, repair, the gate scripts;
- the ledger — the integrity root of the zone;
- the live tree's nine patch-scope paths (ADR 0001's territory).

### Adversaries

- **A1 — accidental drift**: edit without reseal, lost ledger line, EOL
  mangling, deleted file. The dominant and *observed* class (2026-09-11: a stale
  ledger entry survived a whole session unnoticed).
- **A2 — unattended machinery writing what it shouldn't.** Verified for this
  decision: nothing unattended touches the ledger — `repair.py` is reachable
  only from tests, and `hermes-update.bat --repair` = watchdog + `moa_sync --sync`.
- **A3 — deliberate local tamper**: an actor with repo write access edits a
  sealed file *and* its ledger line coherently.
- **A4 — upstream / supply chain** (`hermes update` reset): the patch re-apply
  and watchdog's job, out of scope here.

## Decision

**Build the cheap half; defer the expensive half.**

1. **Seal-set manifest.** `SEALED_SET` compiled into `recovery_integrity.py`,
   cross-checked against the ledger in `verify()` — both directions:
   - manifest entry without a ledger line → `unsealed_path` (block) — closes
     A1's silent hole; the auditor's own seal line is in the manifest, so the
     seal of the sealer cannot vanish quietly either;
   - ledger line without a manifest entry → `undeclared_seal` (block) — the
     trust base changed without a code change to review.
   The invariant `SEALED_SET == {ledger paths}` is pinned by
   `test_kit_manifest_matches_ledger`.
2. **Seal `.gitattributes`** — the definition of the seal unit enters the trust
   base; its tamper/stale shows up as a first-class `stale_seal` instead of
   silently changing what "fresh" means for every other file.
3. **No signing, no embedded digests, no HEAD comparison.** A3 is unreachable
   *from inside the tree by construction*: a coherent file+ledger edit is
   indistinguishable from a legitimate change to anything in that same tree.
   The anchor for A3 already exists and is process, not code: atomic commits,
   `git diff` review at commit time, ff-only push to `origin/main`.

## Why not the alternatives

- **Signing the ledger (GPG/minisign).** The verification code lives in the
  same tree — an attacker who edits the verifier deletes the check — and the
  key would sit next to the thing it authenticates. Only buys something when a
  second trust domain exists (another machine, CI verification).
- **Embedding the ledger digest inside the verifier (cross-seal).** Every
  reseal becomes reseal-ledger → edit-verifier → reseal-verifier: churn on each
  seal, protecting against exactly the coherent-edit case it cannot see (the
  embedded digest is as editable as the ledger line it mirrors).
- **Blocking when `SHA256SUMS.txt` differs from `git show HEAD:`.** The normal
  flow — edit → reseal → gates → commit — leaves the ledger differing from HEAD
  *by design*; the check would block the workflow it protects.
- **Do nothing.** The gap was real, in the observed threat class (A1), and
  fixable in one cross-check; deferring it would defer forever.

## Consequences

- The sealed set now has three coordinated sources — ledger, manifest,
  `.gitattributes` — so changing it costs three deliberate edits (ledger line,
  manifest entry, reseal). The friction is intentional: the trust base should
  not change by accident, and every change lands in `git diff` where review
  (the A3 anchor) actually happens.
- `repair()` maps `unsealed_path` → reseal and `undeclared_seal` → refused: a
  ledger-only writer must never fix a manifest gap.
- **Triggers to revisit the deferred half** — build it when one fires:
  - a second machine/clone becomes a primary writer (then sign commits, with
    the key outside the repo — not the ledger inside it);
  - repair gets wired into an unattended path (A2 reopens);
  - `origin` history rewriting becomes a concern.
