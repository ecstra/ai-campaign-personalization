"""
LLM summarization of parsed document markdown into a product brief
used as context during email generation.
"""

from textwrap import dedent
from typing import Optional

from pydantic import BaseModel, Field
from moonlight import Agent, Content

from ..logger import logger
from ..mail.agent import PROVIDER  # Reuse the configured LLM provider
import os


class BriefSummarizationError(Exception):
    """Raised when the LLM fails to produce a usable brief."""


class ProductBrief(BaseModel):
    """Structured output for the summarizer."""

    brief: str = Field(
        ...,
        description=(
            "A 300-500 word product brief suitable for cold-email personalization. "
            "Preserve specific numbers, customer names, certifications, and "
            "capability specs verbatim. No hype, no marketing fluff."
        ),
    )


BRIEF_SYSTEM_PROMPT = dedent("""
You distill company / product documentation into a compact brief that a
cold-email writer will consult when personalizing outreach.

## Quality bar

- **Preserve every specific fact.** Numbers, customer names, certifications,
  capacity specs, size ranges, process names, temperatures, standards
  references — all stay verbatim. These are the hooks an email writer will
  use. Losing them defeats the purpose.
- **Cut all marketing filler.** Drop hype like "revolutionary", "world-class",
  "cutting-edge", mission statements, vision statements, vague claims without
  a number behind them.
- **Organize by what a seller would reach for.** Identity (who, where, since
  when). Proof points (customers, certifications, scale). Capabilities
  (products, services, specs). Differentiators (what they do that others
  don't). Use short sections and bullet lists so an email writer can scan
  and pick relevant items.
- **300-500 words total.** If the source is short, write a shorter brief.
  Do not pad.
- **No invention.** Every claim must trace back to the source. If something
  is unclear, omit it — do not guess.

## Format

Return a single Markdown document with short sections. Use headings
(##) for each section. Use bullets generously. Do not write long
flowing paragraphs.
""")


async def summarize_to_brief(markdown: str) -> str:
    """
    Take parsed document markdown, return a 300-500 word product brief.

    Raises:
        BriefSummarizationError: on LLM failure or empty output.
    """
    if not markdown or not markdown.strip():
        raise BriefSummarizationError("Empty document markdown")

    # Truncate aggressively to stay inside the context window for cheaper
    # models. 32k chars ≈ 8k tokens. Plenty to capture a product deck.
    max_chars = 32_000
    source = markdown[:max_chars]
    if len(markdown) > max_chars:
        source += f"\n\n[... truncated, {len(markdown) - max_chars:,} more characters ...]"

    prompt = dedent(f"""
    ## SOURCE DOCUMENT

    {source}

    ---

    Produce the product brief now, following the quality bar and format
    above. Return ONLY the JSON object with the `brief` field.
    """)

    agent = Agent(
        provider=PROVIDER,
        model=os.getenv("LLM_MODEL"),  # type: ignore
        output_schema=ProductBrief,
        system_role=BRIEF_SYSTEM_PROMPT,
        persistence=False,
    )

    try:
        response: ProductBrief = await agent.run(Content(prompt))  # type: ignore
    except Exception as e:
        logger.error(f"Brief summarization failed: {e}")
        raise BriefSummarizationError(
            "The model failed to summarize the document. Please try again."
        ) from e

    brief = response.brief.strip()
    if len(brief) < 200:
        raise BriefSummarizationError(
            "The generated brief was too short to be useful. "
            "The source document may not have contained enough substance."
        )
    return brief
