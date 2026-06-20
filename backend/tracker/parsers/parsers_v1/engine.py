# backend/tracker/parsers_v1/engine.py
import fitz


def extract_raw_tokens(uploaded_file):
    """
    Step 1: Raw extraction of words with accurate coordinates.
    Returns a clean array of pages containing geometric objects.
    """
    uploaded_file.seek(0)
    pdf_bytes = uploaded_file.read()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    pages_raw_data = []
    for page_idx, page in enumerate(doc, start=1):
        page_width = float(page.rect.width or 1)
        words = page.get_text("words")

        if not words:
            continue

        pages_raw_data.append(
            {"page_idx": page_idx, "page_width": page_width, "words": words}
        )
    return pages_raw_data
