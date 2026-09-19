# Pattern reference

Load this when you rewrite. Every example here obeys the rules it teaches, so you
can copy the shape of the fixes.

Contents: [Structural templates](#structural-templates) ·
[Sentence-level tells](#sentence-level-tells) ·
[Abstraction](#abstraction) · [Rhythm and format](#rhythm-and-format) ·
[Judgment calls](#judgment-calls) · [Worked examples](#worked-examples)

---

## Structural templates

These matter more than vocabulary. A model reaches for them structurally, so they
repeat, and repetition is what a reader registers.

### Negative parallelism

Setting up a negation to knock it down. The most reliable tell in the set.

| Shape | Example |
|---|---|
| "It's not X, it's Y." | "This isn't a tooling problem. It's a trust problem." |
| "The question isn't X, it's Y." | "The question isn't which model. It's which eval." |
| "Not just X, but Y." | "Not just faster, but cheaper." |
| "Not because X. Because Y." | "Not because it's hard. Because nobody owns it." |
| "X stops being A and starts being B." | "Review stops being a gate and starts being a habit." |

Fix: state the positive claim once. "Teams distrust the tool, so they route around
it." The negation was scaffolding, and the reader never needed it.

Keep it when the thing being negated is a real position someone holds and you are
answering it. "Reviewers assume the linter catches this. It does not." That is an
argument, not a template.

### Throat-clearing

Announcing that a point is coming instead of making it.

"Here's the thing," "Here's what I mean," "Here's why that matters," "Let me be
clear," "I'll be honest," "The uncomfortable truth is," "It turns out that,"
"Look," "Can we talk about."

Fix: delete the phrase and start with the point. Nothing else changes.

### Faux-insight

Positioning the writer as the only one who sees it.

"What nobody tells you," "What most people get wrong," "The part everyone skips,"
"The dirty little secret," "Most people think X. They're wrong."

Fix: cut the setup and let the claim carry itself. "The part everyone misses:
distribution is the moat" becomes "Distribution is the moat." If the claim cannot
stand alone, the setup was doing the persuading, and the claim needs support
instead.

### Colon reveals

A noun phrase, a colon, then a lowercase dramatic payoff.

"The best part: it learns." "The detail that makes it work: a second agent grades
the output."

Fix: write the plain sentence. "A second agent grades the output, which is what
makes it work." Colons are for lists, labels, and quotations.

### Trailing -ing analysis

A participial clause that gestures at meaning without adding any.

"The launch adds file search, highlighting the team's commitment to workflow."

Fix: name the consequence. "The launch adds file search, so users can find old
drafts without leaving the editor." When no consequence is available in the draft,
cut the clause.

Offenders: highlighting, underscoring, reflecting, showcasing, demonstrating,
signaling, marking, cementing, solidifying, reinforcing, illustrating, emphasizing.

### Importance puffery

Telling the reader something matters instead of showing why.

"Stands as a testament to," "marks a pivotal moment," "plays a vital role,"
"solidifies its position," "underscores its significance," "cannot be overstated,"
"this matters more than it sounds."

Fix: give the fact and let the reader judge. "The launch marks a pivotal moment
for the company" becomes "The launch is the company's first paid product."

### Interpretive metadiscourse

Stepping outside the subject to tell the reader how to read.

"The key point is," "As you can see," "In other words," "What this means is,"
"The rest of this essay explains," "In this section we'll," "As we'll see."

Fix: if the point is clear, delete the aside. If it is not, the fix is support,
not narration.

### Fake-profound kickers

The closing line that reaches for an aphorism.

"The future isn't coming. It's already here." "That's the whole game." "The rest
is just details." "We're only getting started."

Fix: delete it. Do not write a better one, do not preserve its rhythm, do not
replace it with a different metaphor. End on the last concrete sentence the draft
already has. If the ending needs closure, use a plain takeaway or the next action.

### Summary recaps

"In conclusion," "To sum up," "All in all," "So there you have it," or a final
paragraph that restates the piece.

Fix: cut it. The reader was just there. Long, genuinely complex pieces can keep a
summary, but it has to add structure the body did not already give.

### Rhetorical setups

"What if I told you," "Think about it:", "Plot twist:", "Sound familiar?", and
questions the writer answers in the next sentence.

Fix: make the claim. A question is worth keeping only when the piece actually
leaves it open.

---

## Sentence-level tells

### Weasel attribution

"Studies show," "research suggests," "experts agree," "many argue," "data
suggests," "it is widely believed," "most companies."

Fix: name the source if the draft names one. If it does not, cut the claim or
bracket it as `[source needed]`. Never attach a citation the input did not contain.
This is the single most common route to fabrication.

### Invented consensus and proximity

"We all know," "you've probably seen," "nobody talks about," "in my experience,"
"when I tested this," a customer quote, a dialogue, an anecdote.

Fix: if it is not in the original, it does not go in the rewrite. Not as color,
not as an example, not as a hypothetical dressed as a memory.

### False agency

Inanimate subjects doing human things, which conveniently avoids naming anyone.

"The decision emerged." "The culture shifts." "The conversation moves toward."
"The data tells us." "The market rewards." "A complaint becomes a fix."

Fix: name the human. "The team fixed it that week." When no specific person fits,
address the reader directly.

Keep the inanimate subject when it describes real causation. "The cache expires
after an hour" is a fact about a cache, not a dodge.

### Fake-strong verbs

"Serves as a centralized hub," "acts as a unified layer," "functions as,"
"represents a significant," "has the ability to," "made the decision to."

Fix: prefer is, has, can, and decided. "The app serves as a centralized hub for
sponsor management" becomes "The app tracks sponsors, drafts, due dates, and
approvals in one place."

### Promotional adjectives

"Powerful and intuitive," "comprehensive and flexible," "innovative," "robust,"
"seamless," "world-class," "cutting-edge."

Fix: give the number, the mechanism, or the name. If none exists in the draft, cut
the adjective and keep the noun.

### Hedge stacking

"This might potentially," "it could be argued that perhaps," "tends to generally."

Fix: one hedge at most. Stacked hedges mean the claim was never made. Keep a single
hedge when the uncertainty is real and the domain requires it.

### Synonym cycling

Rotating terms for the same thing to avoid repeating a word.

"The agent reviews the draft. The assistant scores the piece. The tool suggests
fixes."

Fix: repeat the right word. "The agent reviews the draft, scores it, and suggests
fixes."

---

## Abstraction

The rule that does the most work, and the only one with no shortcut.

Abstraction is where AI writing hides. It is also where the linter is blindest,
because a generic sentence can contain no flagged vocabulary at all.

**The portability test.** If a sentence could move to another company, product,
country, or year unchanged, it is filler. Three responses, in order of preference:

1. Replace it with a specific the draft already contains.
2. Cut it.
3. Bracket what is missing: `[which quarter?]`.

Never respond by inventing the specific.

| Generic | Specific |
|---|---|
| "The integration improved efficiency." | "The integration cut deploy time from 40 minutes to 4." |
| "The tool boosts engineering productivity." | "The tool cut review time from 30 minutes to 8." |
| "Adoption has been strong." | "Six of the eight teams moved over in the first month." |
| "The implications are significant." | "Every team on the old API has to migrate before March." |

When the whole draft is abstraction and nothing concrete is available, say so.
Report it as the finding: the piece has no facts in it, and no amount of editing
adds any. That is information the user needs.

---

## Rhythm and format

**Vary sentence length.** Speech does. Do not enforce a quota, do not chase a
grade level, and do not replace long uniform sentences with short uniform ones.

**Break the tricolon.** Three parallel items, paragraph after paragraph, is the
rhythm tell readers notice without being able to name. Use two items, or one.

**Do not stack fragments.** Four short sentences in a row reads as manufactured
punch, not confidence.

**Vary paragraph shape.** Claim, explanation, punchline, repeated ten times, is a
template even when every individual paragraph is fine.

**Format follows content.** Bullets for genuinely parallel items. Headings over
sections worth navigating to, not over two sentences. No emoji as structure. No
bold mid-sentence for emphasis. Sentence case in headings.

**Em dashes.** Use a period, a comma, or parentheses.

**Three parallel items in prose usually want a list. A sequence of steps wants
numbers. A comparison across two or more dimensions wants a table.** Match the
shape of the page to the shape of the information.

---

## Judgment calls

Rules applied without judgment produce their own kind of slop.

**Adverbs.** Cut the empty ones: very, really, quite, truly, simply, actually,
basically. Keep the ones carrying contrast, degree, or real qualification.
"Deliberately," "briefly," "twice weekly" are load-bearing.

**Passive voice.** Valid when the actor is unknown, irrelevant, deliberately
withheld, or when the receiver is the subject of the sentence. "The records were
destroyed in the 1977 fire" is correct. Flag passive that dodges a known actor.

**Repetition.** Deliberate repetition is a device. Accidental repetition is a tic.
The difference is whether it lands on the same beat.

**Contractions.** Keep them. Formal prose without contractions reads synthetic.

**Technical terms.** A term that is the subject of the sentence stays. Gloss it
once if the audience needs it. "Simplifying" a real term into a vague one is
damage, not editing.

**Jargon inside a field.** A term of art among practitioners is precision. The
same term aimed at a general audience is a wall. The audience decides.

**One instance is not a pattern.** A single em dash means nothing. A single
rhetorical question means nothing. Count the device across the whole piece before
deciding it is a template.

---

## Worked examples

### 1. Template stack

**Before**

> Here's the thing: most teams think their deploy problems are technical. They're
> wrong. At its core, it's a trust problem, highlighting a deeper cultural issue.
> The implications are significant.

**After**

> Deploy problems usually look technical. In the four teams we reviewed, the
> blocker was that nobody would approve a release they had not personally tested.
> [What did that cost? The draft does not say.]

Removed: throat-clearing, faux-insight, negative parallelism, "at its core,"
trailing -ing analysis, vague declarative. The bracket marks a fact the original
never supplied.

### 2. Feature copy

**Before**

> Our robust platform empowers teams to seamlessly streamline their workflows,
> leveraging cutting-edge AI to unlock unprecedented productivity gains.

**After**

> The platform routes each request to whoever owns that queue, so nothing waits on
> a manager to triage it.

Six slop words gone. The claim narrowed to what the draft could actually support.
Every number the original implied but never gave stays out.

### 3. Over-correction

**Before** (the AI original)

> The migration presented several challenges. Teams needed to coordinate across
> time zones, and the legacy schema had accumulated years of undocumented
> constraints that surfaced only under production load.

**After, wrong**

> The migration was hard. Teams span time zones. The schema was a mess. Things
> broke.

**After, right**

> The migration was hard for two reasons. Teams span eleven time zones, so a
> schema change took a full day to agree on. And the legacy schema carried
> undocumented constraints that only appeared under production load.

The first rewrite scores well on the linter and loses the argument. Short is not
the goal. The second keeps every claim, names the mechanism, and still reads like
a person wrote it.

### 4. Fabrication

**Before**

> Studies show that developers lose significant time to context switching.

**After, wrong**

> A 2023 UC Irvine study found developers lose 23 minutes per interruption.

**After, right**

> Developers lose time to context switching. [Source needed: the draft cites
> "studies" without naming one.]

The wrong version is specific, readable, and passes every linter rule. It is also
a citation nobody in this conversation has verified. Bracket it instead.
