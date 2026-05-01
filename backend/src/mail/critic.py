"""
Post-generation critique: a second LLM call that scores a draft email
against a strict banned-pattern checklist. If the critic finds
violations, the caller can regenerate with the violations injected as
extra context.

Why this exists: four rounds of prompt-level tightening on the generator
still produced intermittent rule violations ("sized to your exact
component mix", "suggests you're regularly evaluating"). These phrases
have enough training-data gravity that a single-pass prompt cannot
reliably suppress them. A two-pass generator (generate + critique +
regenerate) trades ~2x cost and ~+3s latency for a hard quality gate.
"""

import os
from textwrap import dedent
from typing import List

from pydantic import BaseModel, Field
from moonlight import Agent, Content

from ..logger import logger
from .agent import PROVIDER


class CritiqueResult(BaseModel):
    """Output of the critic. `passed=True` means the draft is shippable."""

    passed: bool = Field(
        ...,
        description="True when the draft passes every check. False if any violation was found.",
    )
    violations: List[str] = Field(
        default_factory=list,
        description=(
            "Named violation codes plus a short offending quote, one per line. "
            "Empty list when passed=True."
        ),
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
  VIOLATION: "Hanomag's position as one of the largest contract heat
  treaters suggests you're regularly evaluating capacity additions"
  VIOLATION: "RÜBIG's public focus on vacuum hardening and your
  Slovakia site suggest a Central European operation where furnace
  engineering is a regular consideration"
  OK: "Hanomag runs a dedicated nitriding department in Hannover."

### CAPABILITY_MENU_DUMP
Three or more products, processes, or capabilities listed in one
sentence, when the campaign notes focus on only one or two.
  VIOLATION: "We build vacuum furnaces for hardening, carburizing,
  and nitriding" (when notes point only to nitriding)
  OK: "We build vacuum nitriding furnaces."

### FILLER_PHRASE_PATTERN
These exact phrase shapes are always filler when the bracketed content
is an abstract adjective followed by a generic noun (not a measurable
spec):
  - "sized to your [...]"
  - "tailored to your [...]"
  - "built to your [...]"
  - "engineered to your [...]"
  - "matched to your [...]"
The bracketed content MUST contain a concrete measurable spec (a number,
a temperature, a tonnage, a named process). If it contains generic nouns
like "requirements", "needs", "operation", "component mix", "volume",
"specifications", that is a violation.
  VIOLATION: "sized to your exact component mix and volume"
  VIOLATION: "tailored to your internal process control requirements"
  VIOLATION: "engineered to your specific needs"
  OK: "sized for 500 kg batch throughput"
  OK: "engineered for 1300°C vacuum hardening cycles"

### BARE_FILLER_ADJECTIVE
The words "exact", "precise", "custom", "tailored", "unique", "bespoke"
appear WITHOUT a specific claim immediately qualifying them. In
custom-manufacturing contexts these words mean nothing.
  VIOLATION: "custom vacuum furnaces"
  VIOLATION: "tailored solutions"
  OK: "vacuum furnaces with custom hot-zone dimensions from 400 to
  1200 mm"

### EM_DASH
Any em-dash character (—) anywhere in the subject or body.
  VIOLATION: "caught my eye — one of the largest"

### CORPORATE_FILLER
Generic business-speak with no specific content behind it. Examples:
"leverage synergies", "unlock value", "drive growth", "take X to the
next level", "move the needle", "I hope this email finds you well",
"world-class", "industry-leading", "cutting-edge", "revolutionary"
when used without a concrete claim.

### NAME_FORMALITY_MISMATCH
"Dear [Name]" is too formal for a peer-to-peer business register.
  VIOLATION: "Dear Klaas"
  OK: "Klaas,"

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


async def critique_email(
    subject: str,
    body: str,
    recipient_context: str,
) -> CritiqueResult:
    """
    Run the draft through the critic. Returns CritiqueResult.

    On critic failure (network error, malformed response, etc.), logs a
    warning and returns passed=True so the original draft ships. The
    critic is a quality gate, not a blocker.
    """
    try:
        critic = Agent(
            provider=PROVIDER,
            model=os.getenv("LLM_MODEL"),  # type: ignore
            output_schema=CritiqueResult,
            system_role=CRITIC_SYSTEM,
            persistence=False,
        )
        prompt = Content(CRITIC_PROMPT.format(
            subject=subject,
            body=body,
            recipient_context=recipient_context,
        ))
        result: CritiqueResult = await critic.run(prompt)  # type: ignore
        return result
    except Exception as e:
        logger.warning(
            f"Critic call failed, accepting draft as-is: {e}"
        )
        return CritiqueResult(passed=True, violations=[])
