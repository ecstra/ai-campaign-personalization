import os
import asyncio
import logging
from pathlib import Path
from typing import Any, cast

from moonlight import Agent, Content

from ..base import PersonalizedMessage
from .critic import CriticUtility
from .provider import LLM_PROVIDER, LLM_MODEL

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent / "prompts"
ROLE = (_PROMPT_DIR / "email_role.md").read_text()
PROMPT = (_PROMPT_DIR / "email_prompt.md").read_text()

MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]

if len(RETRY_DELAYS) != MAX_RETRIES:
    raise ValueError("RETRY_DELAYS must be of length MAX_RETRIES")

class MailAgentUtility:

    @staticmethod
    async def _generate_draft(
        user_info: dict[str, Any],
        campaign_info: dict[str, Any],
        previous_emails: list[dict[str, Any]],
        extra_instructions: str = "",
    ) -> PersonalizedMessage:
        email_agent = Agent(
            provider=LLM_PROVIDER,
            model=LLM_MODEL,
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
                response = await email_agent.run(email_agent_prompt)
                return cast(PersonalizedMessage, response)
            except Exception as e:
                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])

        if last_exception:
            raise last_exception
        raise RuntimeError("Email generation failed without a captured exception")

    @staticmethod
    def _recipient_context_for_critic(
        user_info: dict[str, Any],
    ) -> str:
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

    @staticmethod
    async def generate_mail(
        user_info: dict[str, Any],
        campaign_info: dict[str, Any],
        previous_emails: list[dict[str, Any]],
    ) -> PersonalizedMessage:
        critique_enabled = os.getenv("CRITIQUE_ENABLED", "true").lower() in ("1", "true", "yes", "on")

        draft = await MailAgentUtility._generate_draft(
            user_info=user_info,
            campaign_info=campaign_info,
            previous_emails=previous_emails,
        )

        if not critique_enabled:
            return draft

        recipient_context = MailAgentUtility._recipient_context_for_critic(user_info)

        critique = await CriticUtility.critique_email(
            subject=draft.subject,
            body=draft.body,
            recipient_context=recipient_context,
        )
        if critique.passed:
            return draft

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
            draft_v2 = await MailAgentUtility._generate_draft(
                user_info=user_info,
                campaign_info=campaign_info,
                previous_emails=previous_emails,
                extra_instructions=violation_block,
            )
        except Exception:
            logger.exception("Regeneration after critic rejection failed — returning original draft with violations")
            return draft

        return draft_v2