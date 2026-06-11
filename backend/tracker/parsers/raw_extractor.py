# backend/tracker/raw_extractor.py

import json
import io
import re
import pdfplumber
from pypdf import PdfReader
import os
from django.shortcuts import get_object_or_404
from ..models import UserStatementTemplate, Account, BankCredential
import csv


def extract_spatial_preview(uploaded_file, password_pool, max_rows=15):
    """
    Unified PDF Engine: Decrypts document layer streams using database key vaults,
    extracts words along with normalized spatial layout percentages (0-100%),
    and filters out master header/footer noise by verifying transaction row patterns.
    """
    spatial_matrix = []
    if password_pool is None:
        password_pool = []

    # 🔬 Regex compile to match common date structures starting a ledger transaction line
    # Matches patterns like: DD-MM-YYYY, DD/MM/YYYY, DD-MM-YY, DD MMM YYYY, etc.
    DATE_LEAD_PATTERN = re.compile(
        r"^\d{1,2}[-/\s](?:[A-Za-z]{3}|\d{1,2})[-/\s]\d{2,4}"
    )

    try:
        uploaded_file.seek(0)
        file_bytes = io.BytesIO(uploaded_file.read())

        # 1. 🔐 Find the working password using PyPDF
        working_password = None
        reader = PdfReader(file_bytes)

        if reader.is_encrypted:
            if not password_pool:
                return [
                    [
                        {
                            "text": "🔒 LOCKED: PDF encrypted, no pool configured.",
                            "x_pct": 0,
                        }
                    ]
                ]

            for pwd in password_pool:
                try:
                    file_bytes.seek(0)
                    if reader.decrypt(str(pwd).strip()):
                        working_password = str(pwd).strip()
                        print(
                            "🔓 [SPATIAL ENGINE] Decryption verified using vault passphrase."
                        )
                        break
                except:
                    continue

            if not working_password:
                return [
                    [
                        {
                            "text": "❌ DECRYPTION FAILURE: Historical vault keys rejected.",
                            "x_pct": 0,
                        }
                    ]
                ]

        # 2. 🗺️ Extract layout matrices using pdfplumber
        file_bytes.seek(0)
        with pdfplumber.open(file_bytes, password=working_password) as pdf:
            if not pdf.pages:
                return [
                    [
                        {
                            "text": "⚠️ EMPTY: PDF contains no valid canvas layers.",
                            "x_pct": 0,
                        }
                    ]
                ]

            page = pdf.pages[0]
            page_width = float(page.width)

            # Extract absolute tracking boxes for word tokens
            words = page.extract_words(keep_blank_chars=False, y_tolerance=3)

            # Group text blocks vertically into matching line clusters
            lines_dict = {}
            for w in words:
                line_top = round(float(w["top"]), 1)

                matched_top = None
                for existing_top in lines_dict.keys():
                    if abs(existing_top - line_top) <= 3:
                        matched_top = existing_top
                        break

                x_pct = round((float(w["x0"]) / page_width) * 100, 2)
                word_node = {"text": w["text"], "x_pct": x_pct}

                if matched_top is not None:
                    lines_dict[matched_top].append(word_node)
                else:
                    lines_dict[line_top] = [word_node]

            # 3. 🏁 Filter Noise and Sort Records
            sorted_tops = sorted(lines_dict.keys())
            for top in sorted_tops:
                # Sort line elements horizontally from left to right
                line_words = sorted(lines_dict[top], key=lambda item: item["x_pct"])

                # Assemble line summary to test strings accurately
                line_text_summary = " ".join([w["text"] for w in line_words]).strip()

                # 🚫 GUARD 1: Drop empty rows or single floating artifacts
                if len(line_words) < 2:
                    continue

                # 🚫 GUARD 2: Explicitly skip known static table headers or branding parameters
                if any(
                    noise in line_text_summary.upper()
                    for noise in [
                        "TECHNOPARK",
                        "CUSTOMER ID",
                        "CKYC",
                        "TC100/",
                        "GROUND FLOOR",
                        "STATEMENT OF ACCOUNT",
                        "MODE OF OPR",
                        "NOMINEE",
                        "SWIFT CODE",
                    ]
                ):
                    continue

                # 🎯 GUARD 3: Ensure the row actually begins with a Transaction Date signature!
                # This drops the customer profiling summaries and catches the true core ledger items.
                if not DATE_LEAD_PATTERN.match(line_text_summary):
                    continue

                spatial_matrix.append(line_words)
                if len(spatial_matrix) >= max_rows:
                    break

    except Exception as e:
        print(f"Spatial parsing failure: {str(e)}")
        return [[{"text": f"❌ EXCEPTION RUNTIME ERROR: {str(e)}", "x_pct": 0}]]

    return spatial_matrix


def match_statement_template(uploaded_file, account_id):
    """
    Robust Account-Aware Routing Engine.
    Falls back to Account profile indicators if text matching fails on image/JPEG PDFs.
    """
    try:
        file_extension = os.path.splitext(uploaded_file.name)[1].lower()
    except IndexError:
        file_extension = ""

    file_name_upper = uploaded_file.name.upper()

    # Fetch the target Bank Account entity directly
    account = get_object_or_404(Account, id=account_id)
    account_name_upper = account.name.upper()

    available_templates = UserStatementTemplate.objects.all()

    if file_extension == ".pdf":
        file_text_sample = ""

        # Fetch the password pool inside the router safely
        credential = BankCredential.objects.filter(account=account).first()
        password_pool = (
            credential.password_vault
            if credential and isinstance(credential.password_vault, list)
            else []
        )

        # Test default unencrypted stream variant first, then parse pool array values
        keys_to_test = [""] + password_pool

        for current_key in keys_to_test:
            uploaded_file.seek(0)
            try:
                with pdfplumber.open(
                    uploaded_file, password=current_key if current_key else None
                ) as pdf:
                    if pdf.pages:
                        file_text_sample = (pdf.pages[0].extract_text() or "").upper()
                        # 🟢 SAVE THE WINNER KEY
                        unlocked_password = current_key
                        break
            except Exception:
                continue

        # 🔍 PHASE 1: Scan for template blueprint matches via distinct string contexts
        for template in available_templates:
            sig = template.header_signature or ""
            if "UNIVERSAL_GEOMETRY" in sig:
                try:
                    meta = json.loads(sig)
                except Exception:
                    continue

                kw = meta.get("matching_keyword", "").strip().upper()
                if not kw:
                    continue

                if (
                    (kw in file_text_sample)
                    or (kw in file_name_upper)
                    or (kw in account_name_upper)
                ):
                    print(
                        f"--- [ROUTER MATCH SECURED] -> Linked Blueprint: {template.template_name} via context marker '{kw}' ---"
                    )
                    # 🟢 FIXED: Wrapped database indexes inside explicit integer fallback bounds checks
                    return {
                        "type": "UNIVERSAL_PDF",
                        "template": template,
                        "unlocked_password": unlocked_password,
                        "bounds": {
                            "date_max": int(template.date_index or 0),
                            "value_date_max": int(template.narration_index or 0),
                            "particulars_max": int(template.amount_index or 0),
                            "trantype_max": int(template.debit_index or 0),
                            "cheque_max": int(template.credit_index or 0),
                            "withdrawals_max": int(meta.get("withdrawals_max") or 0),
                            "deposits_max": int(meta.get("deposits_max") or 0),
                            "balance_max": int(meta.get("balance_max") or 0),
                            "indicator_max": int(meta.get("indicator_max") or 100),
                        },
                    }

        # 🔍 PHASE 2: Fallback scan for empty keyword fields
        for template in available_templates:
            sig = template.header_signature or ""
            if "UNIVERSAL_GEOMETRY" in sig:
                try:
                    meta = json.loads(sig)
                except:
                    continue
                if not meta.get("matching_keyword"):
                    # 🟢 FIXED: Safe integer cast fallback configuration blocks
                    return {
                        "type": "UNIVERSAL_PDF",
                        "template": template,
                        "bounds": {
                            "date_max": int(template.date_index or 0),
                            "value_date_max": int(template.narration_index or 0),
                            "particulars_max": int(template.amount_index or 0),
                            "trantype_max": int(template.debit_index or 0),
                            "cheque_max": int(template.credit_index or 0),
                            "withdrawals_max": int(meta.get("withdrawals_max") or 0),
                            "deposits_max": int(meta.get("deposits_max") or 0),
                            "balance_max": int(meta.get("balance_max") or 0),
                            "indicator_max": int(meta.get("indicator_max") or 100),
                        },
                    }

    # Global recovery fail-safe match node layout layer
    first_fallback = available_templates.first()
    if first_fallback:
        meta = {}
        if first_fallback.header_signature:
            try:
                meta = json.loads(first_fallback.header_signature)
            except:
                pass
        # 🟢 FIXED: Enforced type boundaries mapping protection layout
        return {
            "type": "UNIVERSAL_PDF",
            "template": first_fallback,
            "bounds": {
                "date_max": int(first_fallback.date_index or 0),
                "value_date_max": int(first_fallback.narration_index or 0),
                "particulars_max": int(first_fallback.amount_index or 0),
                "trantype_max": int(first_fallback.debit_index or 0),
                "cheque_max": int(first_fallback.credit_index or 0),
                "withdrawals_max": int(meta.get("withdrawals_max") or 72),
                "deposits_max": int(meta.get("deposits_max") or 84),
                "balance_max": int(meta.get("balance_max") or 94),
                "indicator_max": int(meta.get("indicator_max") or 100),
            },
        }

    return {"type": "UNKNOWN", "template": None, "bounds": None}


# ─── 🟢 INJECTED SERVICE HELPER METHOD CORE ───
def extract_raw_text_stream(uploaded_file, filename, password_pool, account_name):
    was_encrypted = False
    raw_text_stream = ""
    uploaded_file.seek(0)

    if filename.lower().endswith(".pdf"):
        # Try without password first
        try:
            with pdfplumber.open(uploaded_file) as pdf:
                raw_text_stream = "\n".join(
                    [page.extract_text() or "" for page in pdf.pages]
                )
        except Exception:
            # If it fails, try the password vault
            was_encrypted = True
            if not password_pool:
                raise PermissionError(
                    f"PDF encrypted for {account_name}, no vault keys."
                )

            decryption_successful = False
            for key in password_pool:
                try:
                    with pdfplumber.open(uploaded_file, password=str(key)) as pdf:
                        raw_text_stream = "\n".join(
                            [page.extract_text() or "" for page in pdf.pages]
                        )
                        decryption_successful = True
                        break
                except:
                    continue

            if not decryption_successful:
                raise LookupError("All provided keys failed decryption.")
    else:
        # CSV Handling
        raw_text_stream = uploaded_file.read().decode("utf-8")

    uploaded_file.seek(0)
    return raw_text_stream, was_encrypted
