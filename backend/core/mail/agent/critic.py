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

class CriticUtility:

    @staticmethod
    async def critique_email(
        subject: str,
        body: str,
        recipient_context: str,
    ) -> CritiqueResult:
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
            result = await critic.run(prompt)
            return cast(CritiqueResult, result)
        except Exception:
            logger.exception("Critic evaluation failed — treating as unchecked")
            return CritiqueResult(passed=False, violations=["CRITIC_ERROR: Quality reviewer was unavailable — email shipped without review"])