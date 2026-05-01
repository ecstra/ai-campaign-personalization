"""
Test script for PDF extraction quality.
Run manually: python test_pdf_extraction.py <path_to_pdf>

Extraction strategy:
1. Try pymupdf4llm (fast, free, works on native PDFs with selectable text)
2. If output is sparse (<100 chars/page), fall back to Google Document AI OCR
   (handles scanned/image PDFs, costs ~$1.50/1000 pages)

Options:
  --summarize    Also test LLM summarization (needs LLM_API_KEY in .env)
  --force-ocr    Skip pymupdf4llm and go straight to Document AI
  --no-ocr       Never fall back to Document AI, even on sparse output

Document AI env vars (only needed if OCR path is used):
  GCP_PROJECT_ID               Google Cloud project ID
  GCP_DOCAI_LOCATION           Region (e.g. "us" or "eu")
  GCP_DOCAI_PROCESSOR_ID       Enterprise Document OCR processor ID
  GOOGLE_APPLICATION_CREDENTIALS  Path to service account JSON key
"""

import sys
import os
import time

# Threshold: if pymupdf4llm returns fewer than this many chars per page,
# assume the PDF is scanned/image-based and trigger OCR fallback.
OCR_FALLBACK_CHARS_PER_PAGE = 100


def get_page_count(pdf_path: str) -> int:
    """Count pages in the PDF using PyMuPDF (already a pymupdf4llm dep)."""
    import pymupdf
    doc = pymupdf.open(pdf_path)
    count = doc.page_count
    doc.close()
    return count


def extract_with_pymupdf4llm(pdf_path: str) -> tuple[str, float]:
    """Extract PDF to markdown using pymupdf4llm. Returns (text, elapsed_seconds)."""
    import pymupdf4llm

    start = time.time()
    md_text = pymupdf4llm.to_markdown(pdf_path)
    elapsed = time.time() - start
    return md_text, elapsed


def extract_with_document_ai(pdf_path: str) -> tuple[str, float]:
    """
    Extract PDF text using Google Document AI Enterprise OCR.
    Returns (text, elapsed_seconds).
    Raises on missing config or API errors.
    """
    project_id = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("GCP_DOCAI_LOCATION", "us")
    processor_id = os.getenv("GCP_DOCAI_PROCESSOR_ID")
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    missing = [
        name for name, val in [
            ("GCP_PROJECT_ID", project_id),
            ("GCP_DOCAI_PROCESSOR_ID", processor_id),
            ("GOOGLE_APPLICATION_CREDENTIALS", credentials_path),
        ] if not val
    ]
    if missing:
        raise RuntimeError(
            f"Document AI config missing env vars: {', '.join(missing)}. "
            "Set these in .env or your shell. See script docstring for details."
        )

    try:
        from google.cloud import documentai
    except ImportError:
        raise RuntimeError(
            "google-cloud-documentai not installed. Run: pip install google-cloud-documentai"
        )

    start = time.time()

    client = documentai.DocumentProcessorServiceClient(
        client_options={"api_endpoint": f"{location}-documentai.googleapis.com"}
    )
    processor_name = client.processor_path(project_id, location, processor_id)

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    raw_document = documentai.RawDocument(
        content=pdf_bytes,
        mime_type="application/pdf",
    )
    request = documentai.ProcessRequest(
        name=processor_name,
        raw_document=raw_document,
    )

    result = client.process_document(request=request)
    elapsed = time.time() - start

    return result.document.text, elapsed


def extract_pdf(pdf_path: str, force_ocr: bool = False, no_ocr: bool = False) -> tuple[str, str]:
    """
    Extract PDF to text. Returns (text, method_used).
    method_used is either "pymupdf4llm" or "document_ai".
    """
    page_count = get_page_count(pdf_path)
    print(f"\n{'='*60}")
    print(f"PDF: {os.path.basename(pdf_path)} ({page_count} pages)")
    print(f"{'='*60}")

    if force_ocr:
        print("\n[--force-ocr] Skipping pymupdf4llm, using Document AI")
        text, elapsed = extract_with_document_ai(pdf_path)
        _print_result("Document AI", text, elapsed, page_count)
        return text, "document_ai"

    # Try pymupdf4llm first
    print("\n[1/2] Trying pymupdf4llm...")
    text, elapsed = extract_with_pymupdf4llm(pdf_path)
    chars_per_page = len(text) / page_count if page_count else 0
    _print_result("pymupdf4llm", text, elapsed, page_count)

    if no_ocr:
        return text, "pymupdf4llm"

    if chars_per_page < OCR_FALLBACK_CHARS_PER_PAGE:
        print(
            f"\n[2/2] Output is sparse ({chars_per_page:.0f} chars/page < "
            f"{OCR_FALLBACK_CHARS_PER_PAGE}). Falling back to Document AI OCR..."
        )
        try:
            ocr_text, ocr_elapsed = extract_with_document_ai(pdf_path)
            _print_result("Document AI", ocr_text, ocr_elapsed, page_count)
            return ocr_text, "document_ai"
        except RuntimeError as e:
            print(f"\nOCR fallback skipped: {e}")
            print("Returning pymupdf4llm output (likely sparse).")
            return text, "pymupdf4llm"

    print(f"\n[2/2] Output looks dense ({chars_per_page:.0f} chars/page). Skipping OCR.")
    return text, "pymupdf4llm"


def _print_result(method: str, text: str, elapsed: float, page_count: int) -> None:
    chars_per_page = len(text) / page_count if page_count else 0
    print(f"  Method: {method}")
    print(f"  Time:   {elapsed:.2f}s")
    print(f"  Chars:  {len(text):,} ({chars_per_page:.0f}/page)")
    print(f"  Tokens: ~{len(text) // 4:,}")


def show_preview(text: str, lines: int = 80) -> None:
    """Print first N lines of extracted text."""
    preview = "\n".join(text.splitlines()[:lines])
    print(f"\n── EXTRACTED TEXT (first {lines} lines) ──\n")
    print(preview)
    print(f"\n── END PREVIEW ({len(text.splitlines())} total lines) ──\n")


def save_output(text: str, pdf_path: str, method: str) -> str:
    """Save extracted text to a file next to the PDF."""
    suffix = "_extracted.md" if method == "pymupdf4llm" else "_extracted_ocr.txt"
    output_path = os.path.splitext(pdf_path)[0] + suffix
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Full extraction saved to: {output_path}")
    return output_path


def test_summarization(text: str) -> None:
    """Test LLM summarization of the extracted text (requires .env with Groq key)."""
    try:
        from dotenv import load_dotenv
        load_dotenv()

        api_key = os.getenv("LLM_API_KEY")
        if not api_key:
            print("Skipping summarization: LLM_API_KEY not set in .env")
            return

        import httpx

        max_chars = 32000
        text_for_summary = text[:max_chars]
        if len(text) > max_chars:
            text_for_summary += f"\n\n[... truncated, {len(text) - max_chars:,} more characters ...]"

        prompt = f"""Summarize this product/company document into a concise brief (300-500 words)
that an email copywriter could use to write personalized outreach emails.
Focus on: what the product/service is, key features and benefits, target audience,
and any specific details that would be useful for personalization.

DOCUMENT:
{text_for_summary}

SUMMARY:"""

        print("\n── LLM SUMMARY ──\n")
        print("Generating summary via Groq...")

        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 1000,
            },
            timeout=30,
        )

        if response.status_code == 200:
            summary = response.json()["choices"][0]["message"]["content"]
            print(summary)
            print(f"\n── END SUMMARY ({len(summary)} chars, ~{len(summary)//4} tokens) ──")
        else:
            print(f"Groq API error: {response.status_code} {response.text}")

    except ImportError as e:
        print(f"Skipping summarization: missing dependency ({e})")
    except Exception as e:
        print(f"Summarization failed: {e}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python test_pdf_extraction.py <path_to_pdf> [options]")
        print("\nOptions:")
        print("  --summarize    Also test LLM summarization (needs LLM_API_KEY in .env)")
        print("  --force-ocr    Skip pymupdf4llm and go straight to Document AI")
        print("  --no-ocr       Never fall back to Document AI, even on sparse output")
        sys.exit(1)

    pdf_path = sys.argv[1]
    do_summarize = "--summarize" in sys.argv
    force_ocr = "--force-ocr" in sys.argv
    no_ocr = "--no-ocr" in sys.argv

    if force_ocr and no_ocr:
        print("Error: --force-ocr and --no-ocr are mutually exclusive")
        sys.exit(1)

    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    text, method = extract_pdf(pdf_path, force_ocr=force_ocr, no_ocr=no_ocr)
    show_preview(text)
    save_output(text, pdf_path, method)

    if do_summarize:
        test_summarization(text)
    else:
        print("\nTip: Add --summarize flag to test LLM summarization")


if __name__ == "__main__":
    main()
