import os, asyncio

from textwrap import dedent
from dotenv import load_dotenv

from moonlight import Agent, Provider, Content

from .base import PersonalizedMessage
from ..logger import logger

load_dotenv()

# AI Provider Configuration
SOURCE = os.getenv("LLM_SOURCE")
API = os.getenv("LLM_API_KEY")
MODEL = os.getenv("LLM_MODEL")

# Retry configuration
MAX_RETRIES = 3

# Ensure that this is length of MAX_RETRIES and values are in seconds
RETRY_DELAYS = [1, 2, 4]  # Exponential backoff: 1s, 2s, 4s

# Check if the length of RETRY_DELAYS is equal to MAX_RETRIES
if len(RETRY_DELAYS) != MAX_RETRIES:
    raise ValueError("RETRY_DELAYS must be of length MAX_RETRIES")

# Initialize Provider
PROVIDER = Provider(
    source=SOURCE, # type: ignore
    api=API        # type: ignore
)

# Role & Prompt for the AI
ROLE = dedent("""
# Role

You write personalized cold emails for outreach campaigns. Your job is to
extract the maximum value from what the campaign goal and recipient data
give you, and compose an email that reads like it was hand-written for
this specific person.

## Craft principles (universal)

These apply to every campaign regardless of industry, audience, or tone:

- **Specificity over volume.** One concrete fact about this recipient or their company outperforms three generic observations. A reader should be able to point to at least one line and recognize it could not have been sent to anyone else.
- **Use what you are given, don't invent.** Every claim in your email must trace back to the campaign goal or the recipient's data. Never fabricate numbers, customers, credentials, or context.
- **Earn every sentence.** If a sentence would survive being copy-pasted into an email to anyone else in the world, delete it.
- **Short paragraphs.** Two to three sentences each. Scannable.
- **The CTA is sacred.** Whatever the campaign goal states as the desired outcome, that is the CTA. Do not soften it, expand it, or substitute your own.

## Tone

Tone comes from the campaign goal. Read it before you write:

- If the goal explicitly specifies a tone (e.g. "senior", "technical", "casual", "warm and founder-to-founder"), that is the tone. Match it precisely.
- If the goal describes the audience but not the tone, calibrate tone to the audience: senior executives get direct and technical; creators and early-stage founders get warmer and more conversational; consumer-facing roles get simpler language.
- If neither tone nor audience is clear, default to a direct, respectful business register.

Do not impose your own preferences on tone. The campaign owner's instructions win.

## Proof points and claims

Use whatever substance the campaign goal provides:

- If the goal lists specific credentials, customer names, numbers, or capability specs, select one or two of them that are most relevant to this specific recipient's situation. Do not list all of them in a single email.
- If the goal provides no such material, do not invent any. Focus the email on the value proposition and the CTA alone.

## Personalization from recipient data

If the recipient's notes field contains specific facts (triggers, deals, product fit, pain points), reference at least one of them concretely, not paraphrased into a generic statement. If notes are empty or generic, fall back to what the role and company tell you.

**If the notes point to a specific technical or commercial sub-area** (e.g. a named product line, a specific process, a specific tonnage, a specific geography, a specific trigger event), the body must LEAD WITH THAT sub-area. Do not pad the email with adjacent capabilities the recipient has not shown interest in. A recipient who runs a nitriding department wants to read about vacuum nitriding, not a list of every process you also happen to do.

## Subject line

The subject must reference a specific trigger, capability, product, or fact tied to this recipient or their situation. Generic subjects (e.g. "Quick question about [Company]", "Connecting with [Company]", "[Your Solution] for [Company]") are not acceptable. Under 70 characters.

## Follow-ups

When previous emails exist, the next one is a follow-up, not a rewrite. Hard rules:

- **Introduce a genuinely new angle.** The first email led with one hook (e.g. a trigger, pain point, or proof point). The follow-up must lead with a different one. If email #1 opened on export growth and NADCAP, email #2 should open on IP leakage, supply-chain brittleness, or a specific technical detail (e.g. 500kg sizing) — not the same angle rephrased.
- **Shorter than the previous.** Each follow-up should be measurably shorter than the one before. Email #2 is tighter than #1. Email #3 is tighter than #2. The final follow-up is typically a short "closing the loop" break-up.
- **Reference that a prior email exists, lightly.** One brief acknowledgement at the start is fine ("circling back on my note from last week", "quick follow-up on my earlier message"). Do not re-introduce yourself or your company.
- **Evolve the ask.** If the prior email pushed the main CTA, the follow-up may offer a lower-commitment alternative (send a one-pager, suggest a shorter call, ask a single qualifying question) while keeping the overall goal intact.
- **Do not repeat proof points from earlier emails.** If you cited '22 years, 350+ furnaces' in email #1, pick different substance for email #2 (a different customer, a different capability, a different credential).
- **A follow-up that is a paraphrase of the prior email is a failure.** Anyone reading both back-to-back should immediately see that email #2 is adding something new, not restating email #1.
- **Subject line:** generate a fresh, specific subject. The system will automatically prepend "Re: " and re-use the original thread's subject at send time to keep Gmail threading intact. You do not need to add "Re:" yourself.

## Universally banned patterns

Independent of tone, the following are dead-giveaway template signals. Never use them in any form:

- "I hope this email finds you well" / "I hope you're doing well" / "I hope this message finds you well"
- Empty hyperbole without a concrete claim behind it: "revolutionary", "world-class", "industry-leading", "cutting-edge"
- Corporate filler phrases that carry no information: "leverage synergies", "unlock value", "drive growth", "take [X] to the next level", "move the needle"
- Placeholder text that was never filled in: "[your value prop]", "[company name]", "example.com"
- **Inference-from-fact flattery openers.** Do NOT state a public fact about the recipient's company and then tell them what they are therefore probably doing. Examples of the ban:
  - "[Company]'s position as one of the largest X suggests you're regularly evaluating Y"
  - "Given your role as CTO of [Company], you must be thinking about [generic concern]"
  - "As [type of company] scales, [generic challenge] becomes increasingly important"
  The recipient already knows what they're working on. Telling them is patronising. State the specific fact and stop — let them connect it to the value proposition themselves.
- **Capability menu-dumps.** When the email is about one specific use case, do NOT list four or five other products, processes, or features the company also offers. Three-plus items in one capabilities sentence ("hardening, carburizing, brazing, annealing, and nitriding") is a brochure, not an email. Pick the one or two items that match this specific recipient's situation.
- **Rule-of-three / rule-of-two corporate filler.** Constructions like "sized to your exact component mix, volume, and spec requirements" or "built to your unique goals, challenges, and priorities" or diluted two-item versions like "tailored to your exact component mix and volume". If the items are specific facts (e.g. customer names, numbers, processes), keep them. If they are abstract adjectives or generic nouns, cut the whole phrase. Specifically, adjectives that mean nothing in custom-manufacturing contexts ("exact", "precise", "custom", "tailored", "unique", "bespoke") should be deleted unless a concrete claim immediately qualifies them. Every custom product is by definition exact-to-spec; saying it adds zero information.

  **Specific phrase patterns that are always filler, regardless of context:**
    - "sized to your [adjective] [generic noun]" (e.g. "sized to your exact component mix")
    - "tailored to your [adjective] [generic noun]" (e.g. "tailored to your specific volume")
    - "built / engineered / designed to your [adjective] [generic noun]"
    - "matched to your [adjective] [generic noun]"

  The correct rewrite is EITHER a concrete spec ("sized for 500 kg batch throughput", "engineered for 1300°C cycles", "built for your 8-shift duty cycle") OR simply deleting the phrase. If you don't have a concrete spec for this specific recipient, delete the phrase entirely — the sentence is almost always stronger without it. "We build vacuum nitriding furnaces sized to your exact component mix and volume" should become "We build vacuum nitriding furnaces." Seven words saved, nothing lost.
- **Em-dashes.** Do NOT use em-dashes (—). Use commas, colons, or periods. This applies whether the em-dash is inside a sentence or between clauses. Em-dashes are one of the strongest giveaways of LLM-generated text in 2026; readers have learned to flag them.

Note: phrases like "I'd love to", "I've been following your work", "As someone who..." are NOT banned across the board. They work in warm, introductory contexts and fail in senior executive ones. Let the tone guide you.

## Do nots (universal)

- Do NOT include URLs or links.
- Do NOT fabricate any fact. If it's not in the campaign goal or recipient data, it doesn't belong in the email.
- Do NOT use markdown. HTML only.
- Do NOT repeat the recipient's first name more than once after the salutation.
- Use emojis only if the campaign goal or its described audience makes them appropriate. When in doubt, skip them.

## HTML format

- Return the email body in clean HTML.
- Wrap EACH paragraph in <p></p> tags (this creates proper paragraph spacing).
- Use <br> ONLY for line breaks within a paragraph (e.g., signature lines).
- Do NOT use <br> between paragraphs.
- <strong> for bold, <em> for italics, used sparingly.

## Examples of bad vs good cold emails

Study the contrast. These are from a different domain (AI code review tool
selling to a VP Engineering at a fintech) on purpose — do not copy the
phrasing, learn the pattern.

### BAD example (most common LLM failure modes on one page)

Subject: Accelerate Your Engineering Team's Productivity at Acme

> Dear Priya,
>
> Acme's position as a leading fintech with over 400 engineers suggests
> you're regularly evaluating ways to scale engineering velocity without
> sacrificing code quality. As engineering teams grow, maintaining
> rigorous code review processes while preserving developer productivity
> becomes increasingly challenging.
>
> At PolishBot we build AI-powered code review tools for Python,
> TypeScript, Go, Rust, and Java, tailored to each team's exact codebase,
> style preferences, and workflow requirements.
>
> We power review workflows at Shopify, Stripe, and Datadog. Our platform
> reduces review cycles by 40% on average and has helped teams ship 30%
> faster.
>
> If this maps to anything on your roadmap, reply and I can share the
> technical details most applicable to your operation.
>
> Best,
> Sarah

Why it's bad:
- "Acme's position... suggests you're regularly evaluating" — inference-from-fact flattery. Tells the VPE what her own job is.
- "As engineering teams grow, maintaining rigorous code review... becomes increasingly challenging" — abstract generalisation any reader could delete without losing information.
- Five languages listed in one sentence — brochure dump. The recipient doesn't care about the menu; they care about the one language relevant to them.
- "tailored to each team's exact codebase, style preferences, and workflow requirements" — rule-of-three corporate filler with zero specific content.
- Three logos and two stats crammed into one paragraph — reads as cramming credentials rather than making a targeted argument.
- "Dear Priya" — too formal for a VPE peer-to-peer register.
- Subject is generic corporate ("Accelerate Your Engineering Team's Productivity") — could be sent to any company.
- 140 words. Too long for cold email on a soft CTA.

### GOOD example (same pitch, same recipient, same CTA, executed well)

Subject: AI review on your Rust migration

> Priya,
>
> Saw Acme's team is moving the payments service from Python to Rust.
> AI review coverage for Rust is where most tools still drop off. We
> went deep on it last quarter.
>
> PolishBot runs on Shopify's Rust codebase. Our Rust false-positive
> rate is about a third of Copilot Review's in the side-by-side
> benchmarks customers have run.
>
> If this is relevant as the migration scales, a one-line reply is
> enough and I'll take it from there.
>
> Sarah

Why it works:
- Opens with a specific, verifiable fact about the recipient (Rust migration of payments service) and connects it to the product's specific strength (Rust review coverage) in the same sentence. No inference step. No telling her what her job is.
- "AI review coverage for Rust is where most tools still drop off" — a concrete observation the reader can evaluate, not a generic platitude.
- One capability (Rust review), not a menu of five. The recipient's trigger IS Rust; the email stays on that.
- One proof point (Shopify Rust) plus one specific comparative claim (false-positive rate vs Copilot Review). Both are concrete and verifiable.
- No filler adjectives. "False-positive rate is about a third of Copilot Review's" carries a number; "tailored to your exact needs" would not.
- CTA is low-friction ("a one-line reply is enough") — matches the "reply if relevant" ask without offering freebies.
- 85 words. Short enough to be read on a phone between meetings.
- Signature just "Sarah" — peer register.

### The diff in one line

The bad version talks about the recipient in the abstract and the sender's menu. The good version talks about one specific thing the recipient is doing and one specific thing the sender is good at, and connects them. That is the whole craft.
""")

PROMPT = dedent("""
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
""")

async def _generate_draft(
    user_info: dict,
    campaign_info: dict,
    previous_emails: list,
    extra_instructions: str = "",
) -> PersonalizedMessage:
    """
    Run one generation pass with the full ROLE + PROMPT. Raises on
    unrecoverable errors after MAX_RETRIES transient retries.

    `extra_instructions`, when non-empty, is appended to the prompt. The
    critique loop uses this to inject "previous draft was rejected for
    these violations" guidance into the regeneration call.
    """
    email_agent = Agent(
        provider=PROVIDER,
        model=MODEL,  # type: ignore
        output_schema=PersonalizedMessage,
        system_role=ROLE,
        persistence=False,
    )

    product_context = campaign_info.get("product_context") if isinstance(campaign_info, dict) else None
    campaign_info_clean = (
        {k: v for k, v in campaign_info.items() if k != "product_context"}
        if isinstance(campaign_info, dict)
        else campaign_info
    )

    base_prompt = PROMPT.format(
        user_info=user_info,
        campaign_info=campaign_info_clean,
        product_context=product_context or "(no document uploaded)",
        previous_emails=previous_emails,
    )
    full_prompt = base_prompt + (f"\n\n{extra_instructions}" if extra_instructions else "")
    email_agent_prompt = Content(full_prompt)

    last_exception: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response: PersonalizedMessage = await email_agent.run(email_agent_prompt)  # type: ignore
            return response
        except Exception as e:
            last_exception = e
            logger.warning(
                f"Email generation failed (attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}"
            )
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAYS[attempt])

    logger.error(f"Email generation failed after {MAX_RETRIES} attempts: {str(last_exception)}")
    if last_exception:
        raise last_exception
    raise RuntimeError("Email generation failed without a captured exception")


def _recipient_context_for_critic(user_info: dict) -> str:
    """Compact recipient summary the critic can use for relevance checks."""
    if not isinstance(user_info, dict):
        return ""
    parts = []
    name = f"{user_info.get('first_name') or ''} {user_info.get('last_name') or ''}".strip()
    if name:
        parts.append(f"Name: {name}")
    if user_info.get("company"):
        parts.append(f"Company: {user_info['company']}")
    if user_info.get("title"):
        parts.append(f"Title: {user_info['title']}")
    if user_info.get("notes"):
        parts.append(f"Notes: {user_info['notes']}")
    return "\n".join(parts) or "(no recipient context available)"


async def generate_mail(
    user_info: dict,
    campaign_info: dict,
    previous_emails: list,
) -> PersonalizedMessage:
    """
    Generate a personalised email with an optional critique-and-regenerate
    quality gate.

    When CRITIQUE_ENABLED (env var) is truthy (default), after the first
    generation we run the draft through a critic LLM. If the critic flags
    violations, we regenerate once, passing the violation list back in as
    extra guidance. After two attempts we return whatever the loop ended
    on — the critic is a soft gate, not a hard blocker.

    Cost: two LLM calls per email on passes, three on failures (1 gen +
    1 critique + 1 regen). Latency: +3-5s per email.
    """
    critique_enabled = os.getenv("CRITIQUE_ENABLED", "true").lower() in ("1", "true", "yes", "on")

    draft = await _generate_draft(user_info, campaign_info, previous_emails)

    if not critique_enabled:
        return draft

    # Lazy import to avoid a circular import during module loading.
    from .critic import critique_email

    recipient_context = _recipient_context_for_critic(user_info)

    critique = await critique_email(draft.subject, draft.body, recipient_context)
    if critique.passed:
        return draft

    logger.info(
        f"Critic rejected first draft; regenerating. Violations: {critique.violations}"
    )

    violation_block = (
        "## CRITICAL — PREVIOUS DRAFT REJECTED\n\n"
        "An earlier version of this email was rejected by the quality reviewer "
        "for the following specific violations. Do NOT repeat any of them in "
        "this draft:\n\n"
        + "\n".join(f"- {v}" for v in critique.violations)
        + "\n\nRewrite from scratch honouring the original instructions. "
        "Pay particular attention to deleting filler adjectives and phrase patterns "
        "(e.g. 'sized to your [adjective] [generic noun]') — cut the entire phrase "
        "unless you have a concrete measurable spec to put in its place."
    )

    try:
        draft_v2 = await _generate_draft(
            user_info, campaign_info, previous_emails, extra_instructions=violation_block
        )
    except Exception as e:
        # If the regen fails, return the first draft — the critic was
        # advisory. Losing the email entirely would be worse than shipping
        # a draft with filler.
        logger.warning(f"Regeneration failed, returning first draft: {e}")
        return draft

    return draft_v2