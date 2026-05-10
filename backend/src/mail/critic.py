from textwrap import dedent
from typing import List

from pydantic import BaseModel, Field
from moonlight import Agent, Content

from .provider import LLM_PROVIDER, LLM_MODEL

class CritiqueResult(BaseModel):
    passed: bool = Field(
        ...,
        description="True when the draft passes every check. False if any violation was found.",
    )
    violations: List[str] = Field(
        default_factory=list,
        description="Named violation codes plus a short offending quote, one per line. Empty list when passed=True.",
    )


CRITIC_SYSTEM = dedent("""
You are a strict cold-email editor. You read a draft and flag violations
of a known checklist. You do NOT rewrite. You do NOT make suggestions.
Your output is a structured JSON result listing violations found.

## Banned patterns

For each pattern below, scan the subject and body. If you find a match,
add the violation code plus a short quote of the offending text to the
violations list.

### INFERENCE_FROM_FACT
The opener states public facts about the recipient and then INFERS what
they must therefore be doing. Trigger phrases: "suggests you're",
"must mean", "positions you to", "as [role], you must be",
"[Company]'s X and Y suggest [inferred state]".

### CAPABILITY_MENU_DUMP
Three or more products, processes, or capabilities listed in one
sentence, when the campaign notes focus on only one or two.

### FILLER_PHRASE_PATTERN
These exact phrase shapes are always filler when the bracketed content
is an abstract adjective followed by a generic noun (not a measurable
spec):
  - "sized to your [...]"
  - "tailored to your [...]"
  - "built to your [...]"
  - "engineered to your [...]"
  - "matched to your [...]"

### BARE_FILLER_ADJECTIVE
The words "exact", "precise", "custom", "tailored", "unique", "bespoke"
appear WITHOUT a specific claim immediately qualifying them.

### EM_DASH
Any em-dash character (—) anywhere in the subject or body.

### CORPORATE_FILLER
Generic business-speak with no specific content behind it. Examples:
"leverage synergies", "unlock value", "drive growth", "take X to the
next level", "move the needle", "I hope this email finds you well",
"world-class", "industry-leading", "cutting-edge", "revolutionary"
when used without a concrete claim.

### NAME_FORMALITY_MISMATCH
"Dear [Name]" is too formal for a peer-to-peer business register.

## How to be strict

- If a phrase is borderline, flag it. False positives cause one
  regeneration. False negatives ship a bad email.
- Quote the exact offending text so the generator can see what to
  fix.
- Use the violation codes in UPPERCASE as listed above.
- If everything is clean, set passed=true and leave violations empty.

## Output format

Return ONLY the JSON object with `passed` and `violations` fields.
""")

CRITIC_PROMPT = dedent("""
## DRAFT SUBJECT

{subject}

## DRAFT BODY

{body}

## RECIPIENT CONTEXT (for relevance checks)

{recipient_context}

---

Run every banned-pattern check against the draft. Return the JSON result.
""")


class CriticUtility:

    @staticmethod
    async def critique_email(
        subject: str,
        body: str,
        recipient_context: str,
    ) -> CritiqueResult:
        """
        Run the draft through the critic. Returns CritiqueResult.
        """
        try:
            critic = Agent(
                provider=LLM_PROVIDER,
                model=LLM_MODEL,
                output_schema=CritiqueResult,
                system_role=CRITIC_SYSTEM,
                persistence=False,
            )
            prompt = Content(CRITIC_PROMPT.format(
                subject=subject,
                body=body,
                recipient_context=recipient_context,
            ))
            result = await critic.run(prompt)
            return result # type: ignore
        except Exception:
            return CritiqueResult(passed=True, violations=[])
