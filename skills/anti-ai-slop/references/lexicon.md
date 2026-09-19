# Lexicon

The complete word and phrase lists live in `../scripts/rules.json`, which is the
single source of truth for both the linter and this skill. Read it directly when
you need the full set:

```bash
python3 -c "import json;d=json.load(open('scripts/rules.json'));[print(r['id'],r['severity'],r['name'],len(r.get('items',r.get('patterns',[])))) for r in d['rules']]"
```

This file covers what a list cannot: which category a word belongs to, and when
an entry on the list is the right word anyway.

## The categories

**W1 Slop vocabulary** (minor). Words whose frequency spiked after 2022. Delve,
leverage, foster, robust, seamless, tapestry, realm, transformative, meticulous,
myriad, pivotal, underscore, showcase, harness, elevate, embark. Readers who use
models daily register them as a signature.

**W2 Slop phrases** (major). Whole clauses carrying no information. "At its core,"
"in today's fast-paced world," "it's worth noting," "when it comes to," "the
bottom line is." Major severity because a phrase is a deliberate construction,
where a single word can be an accident.

**W3 Canned openers** (minor). Transition words reached for when there is nothing
to transition from. Additionally, moreover, furthermore, notably, importantly,
ultimately, in conclusion.

**W4 Assistant voice** (major). Chat-window residue in published text. "Great
question," "hope this helps," "feel free to," "excited to share," "as an AI."
Always cut, with no judgment call to make.

**W5 Filler intensifiers** (note). Very, really, truly, simply, actually,
basically, significantly. Note severity because context decides.

**W6 Weasel attribution** (major). "Studies show," "experts agree," "research
suggests," "most companies." Major because this is the most common route to
fabrication: the next step after accepting one is inventing the citation.

**W7 Lazy extremes** (note). Everyone, nobody, always, never. False authority.

## When a listed word is correct

The lists are aimed at prose written for people. They are wrong in several places,
and knowing where matters more than knowing the list.

**The word names a real thing.** "Leverage" in finance is a specific term. "Robust"
in statistics means insensitive to outliers. "Harness" is a physical object. If the
word is the subject rather than decoration, keep it.

**The draft quotes someone.** Quoted material is untouchable, including quoted
slop. The linter masks blockquotes and inline code for this reason.

**The user requires it.** Legal language, regulated disclosures, a client's style
guide, a product name. Ask before cutting, or suppress it and say so.

**A genuine hedge.** "Studies show" fabricates. "This may reduce latency in some
workloads" is a calibrated claim, and deleting "may" makes the sentence false.
Cut empty hedges, keep warranted ones.

Suppress a finding you have decided to keep:

```markdown
Our leverage ratio fell to 2.1x. <!-- slop-ignore W1 -->
```

The directive covers its own line and the line below it. Use `ALL` to suppress
every rule on a line. Say in your summary which rules you suppressed and why, so
the user can disagree.

## Density rules

Most rules fire on a match. A few fire on a rate, because the thing they catch is
correct English in isolation and a habit in bulk. A density rule needs
`"kind": "density"`, a `min_count`, and a `threshold_per_1000`, and it reports once
with the count, the rate, and the lines involved.

Calibrate a new one against real prose before setting the threshold. Measure the
rate across a corpus you trust, find where the outlier sits, and put the threshold
below it and above everything else. A threshold guessed rather than measured will
fire on good writing, and a linter that cries wolf gets ignored.

## Adding entries

Edit `scripts/rules.json` and nothing else. The linter reads it at runtime, so no
build step is involved. Word entries match on word boundaries and are
case-insensitive. Phrase entries tolerate any whitespace run, so a phrase split
across a line break still matches. Regex entries compile with `IGNORECASE` and
`MULTILINE`, and `^` anchors to a line, so use `[ \t]*` rather than `\s*` after it
or the match will be attributed to the previous line.

Re-run the fixtures after any change:

```bash
python3 scripts/slopcheck.py tests/fixtures/slop.md
python3 scripts/slopcheck.py tests/fixtures/clean.md
```

The first should score near zero and the second at or near 100. A change that
moves the clean fixture below 95 has added a false positive.
