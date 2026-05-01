"""
LlamaParse wrapper: upload a user-provided document and return the parsed
markdown. Uses the Agentic tier for best quality on visual-heavy decks
(our primary use case is PowerPoint-exported PDFs with complex layouts).
"""

import os
import tempfile
from typing import Optional

from llama_cloud import AsyncLlamaCloud

from ..logger import logger


class DocumentParseError(Exception):
    """Raised when the upstream parser fails or returns empty content."""


# Minimum character count we consider meaningful. Anything below suggests
# the upstream parser returned an empty or near-empty document, typically
# because the file was corrupt, password-protected, or entirely image-only.
MIN_USEFUL_CHARS = 200


def _get_client() -> AsyncLlamaCloud:
    api_key = os.getenv("LLAMA_CLOUD_API_KEY")
    if not api_key:
        raise DocumentParseError(
            "LLAMA_CLOUD_API_KEY not configured on the server. "
            "Document upload is unavailable until this is set."
        )
    return AsyncLlamaCloud(api_key=api_key)


async def parse_document(
    file_bytes: bytes,
    filename: str,
    *,
    tier: str = "agentic",
) -> str:
    """
    Upload the file to LlamaParse and return its markdown representation.

    Args:
        file_bytes: Raw file contents.
        filename: Original filename (used for MIME type inference by LlamaParse).
        tier: Parsing tier. "agentic" costs 10 credits/page but handles
              visual-heavy decks correctly. "cost-effective" is 3 credits/page,
              adequate for simple text-heavy PDFs.

    Raises:
        DocumentParseError: on upstream failure or empty output.
    """
    client = _get_client()

    # LlamaParse's client expects a file path or file-like object. Write to a
    # named temp file so the SDK can infer extension/mime type from the name.
    # We clean up immediately after the upload completes.
    suffix = os.path.splitext(filename)[1] or ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        try:
            file_obj = await client.files.create(file=tmp_path, purpose="parse")
        except Exception as e:
            logger.error(f"LlamaParse upload failed for {filename}: {e}")
            raise DocumentParseError(
                "Could not upload the document to the parser service. "
                "Please try again in a moment."
            ) from e

        try:
            # llama-cloud SDK v2.x made `version` a required kwarg.
            # "latest" pins to whatever the API currently considers stable.
            result = await client.parsing.parse(
                file_id=file_obj.id,
                tier=tier,
                version="latest",
                expand=["markdown_full"],
            )
        except Exception as e:
            logger.error(f"LlamaParse parse failed for file {file_obj.id}: {e}")
            raise DocumentParseError(
                "The parser service failed to process this document. "
                "It may be corrupt or in an unsupported format."
            ) from e

        markdown = _extract_markdown(result)
        if not markdown or len(markdown.strip()) < MIN_USEFUL_CHARS:
            raise DocumentParseError(
                "No usable text was extracted. The document may be empty, "
                "password-protected, or entirely image-based without OCR-recognizable text."
            )

        logger.info(
            f"Parsed {filename}: {len(markdown):,} chars, file_id={file_obj.id}"
        )
        return markdown

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _extract_markdown(result) -> Optional[str]:
    """LlamaParse result shape varies across SDK versions; be permissive."""
    # v1: result.markdown_full (string)
    md = getattr(result, "markdown_full", None)
    if isinstance(md, str):
        return md
    # v2: result.pages is a list with .markdown per page
    pages = getattr(result, "pages", None)
    if pages:
        parts = [getattr(p, "markdown", "") or "" for p in pages]
        return "\n\n".join(p for p in parts if p)
    # v3: dict-like with .get
    if hasattr(result, "get"):
        v = result.get("markdown_full") or result.get("markdown")
        if isinstance(v, str):
            return v
    return None
