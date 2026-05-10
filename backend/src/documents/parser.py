import os
import tempfile
from typing import Literal, Optional, Any

from llama_cloud import AsyncLlamaCloud


class DocumentParseError(Exception):
    """Raised when the upstream parser fails or returns empty content."""


MIN_USEFUL_CHARS = 200


class DocumentParserUtility:

    @staticmethod
    def _get_client() -> AsyncLlamaCloud:
        api_key = os.getenv("LLAMA_CLOUD_API_KEY")
        if not api_key:
            raise DocumentParseError(
                "LLAMA_CLOUD_API_KEY not configured on the server. "
                "Document upload is unavailable until this is set."
            )
        return AsyncLlamaCloud(api_key=api_key)

    @staticmethod
    def _extract_markdown(
        result: Any,
    ) -> Optional[str]:
        """LlamaParse result shape varies across SDK versions; be permissive."""
        md = getattr(result, "markdown_full", None)
        if isinstance(md, str):
            return md
        
        pages = getattr(result, "pages", None)
        if pages:
            parts = [getattr(p, "markdown", "") or "" for p in pages]
            return "\n\n".join(p for p in parts if p)
            
        if hasattr(result, "get"):
            v = result.get("markdown_full") or result.get("markdown")
            if isinstance(v, str):
                return v
                
        return None

    @staticmethod
    async def parse_document(
        file_bytes: bytes,
        filename: str,
        tier: Literal["agentic", "agentic_plus", "cost_effective", "fast"] = "agentic",
    ) -> str:
        """
        Upload the file to LlamaParse and return its markdown representation.
        Raises DocumentParseError on upstream failure or empty output.
        """
        client = DocumentParserUtility._get_client()

        suffix = os.path.splitext(filename)[1] or ""
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            try:
                file_obj = await client.files.create(file=tmp_path, purpose="parse")
            except Exception as e:
                raise DocumentParseError(
                    "Could not upload the document to the parser service. "
                    "Please try again in a moment."
                ) from e

            try:
                result = await client.parsing.parse(
                    file_id=file_obj.id,
                    tier=tier,
                    version="latest",
                    expand=["markdown_full"],
                )
            except Exception as e:
                raise DocumentParseError(
                    "The parser service failed to process this document. "
                    "It may be corrupt or in an unsupported format."
                ) from e

            markdown = DocumentParserUtility._extract_markdown(result)
            if not markdown or len(markdown.strip()) < MIN_USEFUL_CHARS:
                raise DocumentParseError(
                    "No usable text was extracted. The document may be empty, "
                    "password-protected, or entirely image-based without OCR-recognizable text."
                )

            return markdown

        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
