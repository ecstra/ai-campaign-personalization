import re
import logging
from pathlib import Path
from typing import cast

from pydantic import BaseModel, Field
from moonlight import Agent, Content

from .provider import LLM_PROVIDER, LLM_MODEL

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent / "prompts"
CRITIC_ROLE = (_PROMPT_DIR / "critic_role.md").read_text()
CRITIC_PROMPT = (_PROMPT_DIR / "critic_prompt.md").read_text()

class CritiqueResult(BaseModel):
    passed: bool = Field(
        ...,
        description="True when the draft passes every check. False if any violation was found.",
    )
    violations: list[str] = Field(
        default_factory=list,
        description="Named violation codes plus a short offending quote, one per line. Empty list when passed=True.",
    )

# ── Deterministic pre-pass ───────────────────────────────────────────────────
# EM_DASH and NAME_FORMALITY_MISMATCH are rule-expressible, so they are checked
# with a regex that catches them 100% of the time regardless of the model. An
# eval over a labeled golden set showed deepseek-v4-flash missing em-dashes ~27%
# and "Dear [Name]" ~35% of the time, while handling the judgment-based checks
# fine. The LLM still runs for the fuzzy patterns; the results are merged below.

_EM_DASH = "—"  # — (not a hyphen "-" or en dash "–")
_DEAR_RE = re.compile(r"\bDear\s+[A-Z]")


def _deterministic_violations(subject: str, body: str) -> list[str]:
    text = f"{subject}\n{body}"
    found: list[str] = []
    if _EM_DASH in text:
        found.append("EM_DASH: em dash character present")
    match = _DEAR_RE.search(text)
    if match:
        found.append(f'NAME_FORMALITY_MISMATCH: "{match.group(0)}"')
    return found


def _merge_violations(deterministic: list[str], llm: list[str]) -> list[str]:
    """Deterministic findings are authoritative for their codes; add only the
    LLM findings whose code is not already covered (dedup by leading code)."""
    merged = list(deterministic)
    seen = {v.split(":", 1)[0].strip() for v in deterministic}
    for v in llm:
        code = v.split(":", 1)[0].strip()
        if code not in seen:
            merged.append(v)
            seen.add(code)
    return merged


class CriticUtility:

    @staticmethod
    async def critique_email(
        subject: str,
        body: str,
        recipient_context: str,
    ) -> CritiqueResult:
        deterministic = _deterministic_violations(subject, body)
        try:
            critic = Agent(
                provider=LLM_PROVIDER,
                model=LLM_MODEL,
                output_schema=CritiqueResult,
                system_role=CRITIC_ROLE,
                persistence=False,
            )
            prompt = Content(CRITIC_PROMPT.format(
                subject=subject,
                body=body,
                recipient_context=recipient_context,
            ))
            result = cast(CritiqueResult, await critic.run(prompt))
        except Exception:
            logger.exception("Critic evaluation failed — treating as unchecked")
            # The LLM is unavailable, but the deterministic checks still stand.
            return CritiqueResult(
                passed=False,
                violations=deterministic + ["CRITIC_ERROR: Quality reviewer was unavailable — email shipped without full review"],
            )

        violations = _merge_violations(deterministic, result.violations)
        return CritiqueResult(passed=not violations, violations=violations)