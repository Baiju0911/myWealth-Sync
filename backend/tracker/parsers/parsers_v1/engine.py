# backend/tracker/parsers/parsers_v1/engine.py
import fitz
import json
import logging

logger = logging.getLogger(__name__)


def extract_raw_tokens(uploaded_file, password_vault_raw=None):
    """
    Step 1: Raw extraction of words with accurate coordinates.
    Dynamically decrypts protected PDFs using a pool of available keys.
    """
    uploaded_file.seek(0)
    pdf_bytes = uploaded_file.read()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    # 🔑 Handle Document Encryption Safely
    if doc.is_encrypted:
        logger.info("🔒 Document is encrypted. Parsing decryption vault keys...")
        passwords = []

        # Parse out the password strings from the DB structure safely
        if password_vault_raw:
            try:
                if isinstance(password_vault_raw, str):
                    passwords = json.loads(password_vault_raw)
                elif isinstance(password_vault_raw, list):
                    passwords = password_vault_raw
            except Exception as e:
                logger.warning(
                    f"⚠️ Failed parsing password_vault json payload: {str(e)}"
                )

        # Ensure we always attempt a blank string fallback
        if "" not in passwords:
            passwords.append("")

        authenticated = False
        for pwd in passwords:
            # If passwords inside json list are dicts, extract the value string
            pwd_str = pwd.get("password", "") if isinstance(pwd, dict) else str(pwd)

            if doc.authenticate(pwd_str.strip()):
                logger.info("🔓 PDF Document successfully decrypted and opened!")
                authenticated = True
                break

        if not authenticated:
            raise ValueError(
                "❌ Ingestion Stopped: Document is encrypted and no matching key was found in password_vault."
            )

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
