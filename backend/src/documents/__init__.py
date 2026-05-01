"""Document ingestion: parse uploaded product briefs into a text context."""

from .parser import parse_document, DocumentParseError
from .summarizer import summarize_to_brief, BriefSummarizationError

__all__ = [
    "parse_document",
    "DocumentParseError",
    "summarize_to_brief",
    "BriefSummarizationError",
]
