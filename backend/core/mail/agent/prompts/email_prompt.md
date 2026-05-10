# PROMPT

Generate a personalized email.

## RECIPIENT

{user_info}

## CAMPAIGN

{campaign_info}

## PRODUCT / COMPANY BRIEF

(May be empty. When present, this is a structured brief distilled from a
document the campaign owner uploaded. Treat every fact, number, customer
name, certification, and spec in it as authoritative source material you
may draw on. Do not invent anything beyond it.)

{product_context}

## PREVIOUS EMAILS IN SEQUENCE

{previous_emails}

---

Before writing, extract from the campaign goal:

1. The tone (explicit or implied from audience).
2. The CTA — the exact action the sender wants the recipient to take.
3. Any concrete substance (credentials, customer names, numbers, capability specs) the campaign owner has provided for you to draw on.
4. Any named triggers or scenarios the goal tells you to hint at.

Then extract from the recipient data:
5. The most specific fact about this person or their company that you can use (usually from notes, but also role, company, and title).

Now write:

- If this is the first email, open with something tied to (5) or a concrete trigger from (4). Do not open with a weather-report pleasantry.
- If this is a follow-up, read the prior emails carefully. Identify which hooks, proof points, and phrasings have already been used. Your follow-up must lead with a DIFFERENT angle and cite DIFFERENT proof points (if any are cited at all). It must be measurably shorter than the prior email. Generate a fresh subject — the system handles "Re: " threading automatically at send time.
- Keep the body tight. Hit the CTA from (2) verbatim in intent — do not improvise a different ask. A follow-up may offer a softer alternative path to the same goal (e.g. a one-pager instead of a call), but must not substitute a new goal.
- Subject line must be specific to this recipient, not a template.

## Self-check before returning

Walk through this checklist IN ORDER. If any answer is "no" or triggers a rewrite, fix it before returning the output.

**High-priority filler checks (do these FIRST before the content checks):**

- Does any sentence contain the word "exact", "precise", "custom", "tailored", "unique", or "bespoke"? For each one found, is a CONCRETE claim (a number, a named process, a specific spec) immediately qualifying it? If not, DELETE the adjective and its surrounding noun phrase entirely. Generic nouns like "component mix", "volume", "requirements", "needs", "specifications" do NOT qualify as concrete claims.
- Do any of these exact phrase patterns appear: "sized to your [...]", "tailored to your [...]", "built to your [...]", "engineered to your [...]", "matched to your [...]"? For each match, is the bracketed content a specific measurable spec (e.g. "500 kg throughput", "1300°C cycles")? If not, delete the entire phrase. In doubt, delete it — the sentence is almost always stronger without.
- Does the body contain ANY em-dash character (—)? If yes, rewrite that sentence using a comma, colon, period, or sentence break. Do not leave a single em-dash.

**Content checks:**

- Does my subject reference something specific to this recipient?
- Have I drawn on the concrete substance the campaign goal gave me (if any)?
- If the recipient's notes had specific facts, have I referenced at least one concretely?
- Is my CTA a faithful match for what the goal asked for?
- Would this email survive copy-paste to a different recipient? If yes, it's too generic. Rewrite.
- Did I open by stating a public fact about the recipient and then INFERRING what they must therefore be doing? If yes, that's inference-from-fact flattery. Remove the inference, state the fact and stop.
- Did I list three or more capabilities, products, or processes in one sentence when only one or two are relevant to this recipient's situation? If yes, cut to the one or two that match.
- Did I use any universally banned pattern from the role instructions? If yes, rewrite.

If this is a follow-up, also check:

- Is my opening angle genuinely different from the prior email's opening angle? (Not the same hook rephrased.)
- Did I cite DIFFERENT proof points than the prior email, or none at all?
- Is my email measurably shorter than the prior email?
- Read my draft side-by-side with the prior email. Would a reader immediately see that this one adds something new? If it reads like a paraphrase, rewrite.

Generate the email now.
