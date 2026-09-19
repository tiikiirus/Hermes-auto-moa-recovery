---
name: anti-ai-slop
description: >-
  Strip AI-generated writing of every tell that marks it as machine-written, then
  verify the result through a deterministic linter and an independent reviewer
  before returning it. Use this whenever the user wants text de-slopped,
  humanized, de-AI'd, or made to sound like a person wrote it, and whenever they
  hand over a draft that ChatGPT, Claude, Gemini, or any model wrote and ask
  you to clean it, sharpen it, fix it, or make it publishable. Use it for blog
  posts, essays, emails, newsletters, LinkedIn and X posts, READMEs, docs,
  landing page copy, and release notes. Also use it when the user asks whether a
  piece reads as AI-written, or asks you to audit, score, or flag AI patterns
  without rewriting.
license: MIT
metadata:
  version: "1.0.0"
---

# Anti AI slop

Machine-written prose has a signature. Not one tell, a stack of them: a vocabulary
that spiked after 2022, a handful of rhetorical templates repeated until they form
a rhythm, and abstraction where a specific fact belongs. Readers who use models
daily recognize it in a sentence or two.

This skill removes that signature and then proves it is gone. The proof matters
more than the edit, because a model that rewrites its own text and grades its own
rewrite will pass itself almost every time.

## What you are usually given

The input is text a model wrote. Treat it as raw material, not as someone's voice
to protect. Cut hard, restructure freely, and rebuild sentences from the fact up.

Two things stay fixed no matter how hard you cut.

**Never invent.** No statistic, source, date, name, quote, anecdote, or first-hand
experience that is not in the input. A fabricated specific is worse than the
abstraction it replaced, because it is wrong and it is convincing. When a sentence
needs a fact that the draft does not supply, cut the claim or leave a bracketed
placeholder such as `[number needed]` and say so in your summary.

**Never change what it says.** Every factual claim, number, condition, hedge that
carries real uncertainty, and technical term in the output must mean what the
input meant. De-slopping is not summarizing. A 900-word draft usually comes back
around 600 words, not 200.

If the user says the draft is theirs rather than a model's, switch to a lighter
touch: make the minimum effective edit, and keep their vocabulary, humor,
bluntness, digressions, and uneven polish. See `references/voice.md`.

## Two modes

**Scrub.** The default. Rewrite, verify, return the clean draft plus a short
summary of what changed.

**Audit.** The user asks whether something reads as AI, or asks to flag patterns
without rewriting. Name each pattern, quote the line, give the fix in a few words,
and stop. Do not rewrite unless asked.

Audit carries one hard boundary. Report observable patterns, never authorship.
Say "this uses four throat-clearing openers and a tricolon in every paragraph,"
never "this was written by AI." Style is evidence about quality. It is not
evidence about who typed it, and humans write this way too. Detectors guess.
Named patterns are something the user can check for themselves.

## The loop

Run all five steps. The verification steps are the reason this skill exists, so
do not stop after the rewrite looks good to you.

### 1. Read and mark

Read the whole draft. Note the core claim, the concrete facts worth protecting,
and the exclusion zones: quoted material, code, proper names, titles, legal or
technical language the user must keep. Nothing in an exclusion zone gets edited.

### 2. Rewrite

Apply the rules below and in `references/patterns.md`. Work claim by claim rather
than sentence by sentence, so the output gets its shape from the argument instead
of inheriting the template the model used.

### 3. Sanitize, then lint

```bash
python3 scripts/sanitize.py DRAFT.md --fix
python3 scripts/slopcheck.py DRAFT.md
```

The sanitizer strips invisible characters that survive a copy-paste out of a chat
window: zero-width spaces, bidi controls, tag characters, noncharacters, and the
odd spacing characters. None of them render, and all of them break grep, diffs,
word counts, and search indexing. It also normalizes curly quotes and ellipses. It
leaves zero-width joiners and variation selectors alone when they sit next to
emoji or non-Latin script, where they are load-bearing. Run it first, because the
linter treats a leftover invisible character as a blocking finding.

The linter reads `scripts/rules.json`, masks code blocks, inline code, quotes,
frontmatter, and URLs, and reports every hit with a line number, the matched text,
and the fix. It starts at 100 and deducts on fixed arithmetic, so the same
findings always produce the same score. It passes at 90 with nothing above minor
severity. Add `--json` when you want to process findings programmatically, and
`<!-- slop-ignore W1 -->` above a line you can justify keeping.

Fix what it flags, then run it again. A finding you disagree with is fine to
suppress, but say why in your summary rather than leaving it unexplained.

Some rules score on frequency rather than on a match, because the device they
catch is ordinary English once and a tic three times. The finding reports the
count, the rate, and every line involved, so you can see the pattern the way a
reader would: as a habit, not as an error.

**The score is a floor, not the goal.** You can reach 100 by writing prose so
bland it contains nothing worth flagging. The linter cannot read for meaning, so
it cannot catch that, and it cannot catch a number you invented. Step 4 can.

### 4. Verify with a fresh reader

Spawn a subagent and give it `references/reviewer.md`, the original draft, and
your rewrite. Do not give it your reasoning or tell it what you fixed. Context
about your intentions is exactly what makes a reviewer agreeable, and an
agreeable reviewer is worth nothing here.

It returns blocking findings in two directions: slop you left behind, and damage
you caused. If no subagent tool is available, do the review yourself, but reread
the output cold as a stranger first and be harder on it than feels fair.

#### Optional: a cross-provider panel

A second opinion from other models, run through the LiteLLM SDK. Use it when the
user asks for one, or when the review has to run where no subagent tool exists.
Run it for the user. Do not hand them a command to paste into a terminal.

**1. Check setup first.**

```bash
python3 scripts/grade.py --check-setup
```

`Ready.` means go to step 3. `Not ready:` means ask.

**2. Ask where the key lives, never for the key.** A key pasted into chat stays
in the transcript. Ask one question: do they call models through a LiteLLM
gateway (and its URL), or with a provider key directly? And where is the key kept:

- a macOS Keychain item, such as `keychain:my-llm-key`
- an environment variable, such as `env:GEMINI_API_KEY`
- a file, such as `file:~/.config/litellm/key`
- a 1Password reference, such as `op://Private/LiteLLM/credential`

Then save the location. The script reads the key itself, confirms it works, and
stores only where it lives, never the value:

```bash
python3 scripts/grade.py --setup --gateway https://your-litellm-gateway.example --key-from keychain:my-llm-key
python3 scripts/grade.py --setup --key-from env:GEMINI_API_KEY
```

With a gateway, setup also asks it which models it serves and picks Gemini 3.8
Flash, or the newest Gemini Flash it has. Without one, the grader calls Gemini 3.8
Flash directly. If the user has nowhere to keep a key yet, suggest their password
manager or Keychain and wait. If the agent tool blocks reading the key, tell the user
which permission it needs and stop there.

**3. Run the panel and report in plain words.**

```bash
python3 scripts/grade.py ORIGINAL.md REWRITE.md
```

Add `--models` to bring in more providers, such as
`--models litellm_proxy/gemini-3.8-flash,litellm_proxy/claude-opus-5`. Graders from
the family that did the editing share its blind spots, so mix providers when you
can. The panel fails if any grader fails the draft or the mean human score is under
80, and it reports cost per grader. Tell the user the verdict, each finding that
matters, and the cost. Do not paste the raw output.

#### Optional: an outside detector

`scripts/detect.py` sends the draft to a third-party AI detector. It takes the
same `--setup --key-from` flow for its own key and lists the
sentences it scores highest. It sends text off the machine, so ask before running it
on anything unpublished. Treat its number as a hint about which lines to reread.
Detectors disagree with each other and flag human writing, and tuning a draft until
one of them goes quiet makes it read worse to people. Never make it the gate.

### 5. Fix and re-verify

Apply the blocking findings and rerun steps 3 and 4. Stop after the second
verification pass. If findings remain after two passes, return the draft anyway
and list what is unresolved. A draft at 88 with an honest note beats a third pass
that sands the content down to hit a number.

## The rules

Detail and before/after examples live in `references/patterns.md`. Load it when
you rewrite. The full word lists live in `scripts/rules.json`.

<!-- slop-ignore W1 -->
**Cut the vocabulary.** Delve, leverage, foster, robust, seamless, tapestry,
realm, transformative, ever-evolving, and the other hundred-odd words the linter
carries. Say the specific thing the word stood in for. If nothing specific is
behind it, the sentence goes.

**Delete the phrases.** "At its core," "in today's fast-paced world," "it's worth
noting," "when it comes to." If the sentence dies without the phrase, the sentence
was the phrase.

**Break the templates.** These are the strongest tells, stronger than any word,
because AI reaches for them structurally rather than occasionally.

- Negative parallelism. "It's not X, it's Y." State Y.
- Throat-clearing. "Here's the thing," "Let me be clear." State the point.
- Faux-insight. "What nobody tells you," "the part everyone misses." Make the claim.
- Colon reveals. "The best part: it learns." Write the plain sentence.
- Trailing -ing analysis. "..., highlighting the team's commitment." Name the consequence.
- Importance puffery. "Marks a pivotal moment." Give the fact, let the reader judge.
- Partition templates. "Routing is half the strategy. The other half is..." State both.
- Fake-profound kickers. Delete the closing aphorism. Do not write a better one.
- Summary recaps. "In conclusion." The reader was just there.
- The tricolon. Three parallel items, over and over. Use two, or one.

**Replace abstraction with specifics.** This is the rule that does the most work.
"The integration improved efficiency" tells the reader nothing; "the integration
cut deploy time from 40 minutes to 4" tells them everything. Use the portability
test: if a sentence could move to another company's blog unchanged, it is filler.
Cut it, or replace it with a fact the draft already contains.

When the draft has no specifics anywhere, do not manufacture them. Say so. A
draft with nothing concrete in it usually needs the user, not an editor.

**Name the actor.** "The decision emerged" hides who decided. "The culture shifts"
hides who changed their behavior. Passive voice is fine when the actor is genuinely
unknown or beside the point, and an inanimate subject is fine when it describes
real causation. Flag it when it is dodging.

**Cite or cut.** "Studies show," "experts agree," "research suggests." Name the
source if the draft names one. If it does not, cut the claim or bracket it. Never
attach a citation the input did not contain.

**Drop the foil.** Not every claim needs an alternative it is being preferred
over. "The fix was a settings change rather than a code change" says the same
thing as "the fix was a settings change."
One contrast is emphasis. Three in a short piece is a writer who cannot state
anything without something to define it against. The linter tracks the rate for
this and flags it at 7.5 per thousand words.

**Vary the rhythm.** Mix sentence lengths the way speech does. Do not enforce a
length quota, and do not chase a readability target. Uniformity is the problem,
in either direction.

**Let format follow content.** Bullets only for genuinely parallel items, headings
only over sections a reader would jump to, no emoji as structure, no bold
sprinkled mid-sentence. Sentence case for headings.

**Em dashes.** Use a period, a comma, or parentheses instead.

**Invisible characters.** Handled by the sanitizer in step 3 rather than by hand.

## How this goes wrong

Three failure modes, all of them scoring well on the linter.

**Scrubbed slop.** Every sentence short, every paragraph the same shape, the whole
piece hammered into flat declaratives. This is what happens when a model treats
"remove AI patterns" as "make it terse." It reads as machine-written for exactly
the reason the original did: mechanical uniformity. Trade rhythm for directness
only where directness wins.

**Hollowing out.** Cutting so much that the argument no longer holds, the caveats
that made a claim true are gone, or the reader can no longer follow why one point
leads to the next. Length is not the target. Density is.

**Stripping the diplomacy.** A slop phrase is sometimes carrying tact. "Acme had
the problem most companies have and few write about" is a faux-insight frame, and
it also tells the reader that Acme's mess was normal. Cut the frame without
replacing that function and the draft now opens on a list of a named company's
failings. When the text is about a real customer, partner, or person, check who
looks worse after each cut. Fix it with structure rather than a cushioning phrase:
lead with what they built, and put the problem behind it in past tense.

**Confident fabrication.** Filling an abstraction with a specific the draft never
contained. This is the worst outcome the skill can produce, and the reviewer
treats it as blocking every time.

Watch the connective tissue especially. Invented numbers and sources are easy to
notice and easy to resist. What slips through is the small joining material added
while smoothing a sentence: a duration ("over several quarters"), a causal link ("the new
dashboard is what cut support tickets"), or an attributed reaction ("the feature
customers ask about most"). Each one reads as a detail the
original must have supplied. None of them contains a flagged word, so the linter
scores them at 100. Before you write any connector, check that the original
asserts the relationship, not just the two things being connected.

## Output

For a scrub, return the full edited draft first, then a short **What changed**
section: the patterns you removed, anything you cut for lack of support, any
bracketed placeholder you left, and the final linter score with any suppressed
rule and your reason.

For an audit, return the findings and stop. Offer to scrub it.

Write the summary in the same plain prose the skill asks for everywhere else.
A summary full of the patterns you just removed undermines the work.
