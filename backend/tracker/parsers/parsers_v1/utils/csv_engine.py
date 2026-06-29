import csv
import io
import re
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def parse_universal_csv_stream(raw_csv_content, template_obj=None):
    """
    🚀 UNIVERSAL TABULAR STREAM ENGINE (V5)
    Dynamically routes formatting structures across delimiters (\t, ,, ;, ~)
    and transparently parses Excel binaries (.xlsx, .xls) safely in-stream.
    """
    all_rows = []

    # ─── EXTRACTION GATEWAY: DETECT AND UNPACK EXCEL BINARIES FIRST ───
    # If it is bytes, check the file magic signature header for Excel formats
    if isinstance(raw_csv_content, bytes):
        # Peak at the first 4 bytes to check signatures
        # PK.. (0x50 0x4B 0x03 0x04) is standard for zip-based files (.xlsx)
        # 0xD0 0xCF 0x11 0xE0 is standard for legacy Compound File Binary Format (.xls)
        is_excel_xml = raw_csv_content.startswith(b"\x50\x4b\x03\x04")
        is_excel_legacy = raw_csv_content.startswith(b"\xd0\xcf\x11\xe0")

        if is_excel_xml or is_excel_legacy:
            logger.info(
                "Excel binary signature detected. Slicing rows via spreadsheet engines..."
            )
            try:
                import openpyxl

                # Read modern XML .xlsx via openpyxl buffer streams
                wb = openpyxl.load_workbook(io.BytesIO(raw_csv_content), data_only=True)
                sheet = wb.active
                for r in sheet.iter_rows(values_only=True):
                    if r and any(cell is not None for cell in r):
                        # Normalize cell values to safe text representations
                        all_rows.append(
                            [str(c).strip() if c is not None else "" for c in r]
                        )
            except Exception as excel_err:
                logger.warning(
                    f"Native openpyxl engine bypassed: {str(excel_err)}. Attempting pandas pipeline..."
                )
                try:
                    import pandas as pd

                    df = pd.read_excel(io.BytesIO(raw_csv_content), header=None)
                    df = df.fillna("")
                    all_rows = df.astype(str).values.tolist()
                except Exception as pd_err:
                    raise ValueError(
                        f"❌ Spreadsheet Extraction Crash: Failed to decode binary array: {str(pd_err)}"
                    )

        if not all_rows:
            # If it's not Excel binary, decode bytes safely to clear text lines
            raw_csv_text = raw_csv_content.decode("utf-8", errors="ignore")
        else:
            raw_csv_text = ""
    else:
        raw_csv_text = str(raw_csv_content)

    # ─── CSV TEXT ROUTING: AUTO-SNIFF DELIMITERS FOR FLAT CHARACTERS ───
    if not all_rows and raw_csv_text.strip():
        csv_file = io.StringIO(raw_csv_text.strip())

        # Default fallback dialect rules
        target_delimiter = ","
        sample_chunk = raw_csv_text[:4096]

        # Intelligent Character Density Scoring Router
        delimiters_to_test = ["\t", ",", ";", "~", "|"]
        highest_score = 0

        for delim in delimiters_to_test:
            count = sample_chunk.count(delim)
            if count > highest_score:
                highest_score = count
                target_delimiter = delim

        logger.info(
            f"📋 Tabular Engine routed execution path to delimiter: repr('{target_delimiter}')"
        )

        # Parse using the detected delimiter
        reader = csv.reader(csv_file, delimiter=target_delimiter)
        all_rows = list(reader)

    if not all_rows:
        return []

    # ─── STEP 1: RESOLVE THE MAPPING DICTIONARY VIA DYNAMIC DATABASE FIELD ───
    active_landmarks = None
    if (
        template_obj
        and hasattr(template_obj, "header_mapping_json")
        and template_obj.header_mapping_json
    ):
        try:
            active_landmarks = (
                json.loads(template_obj.header_mapping_json)
                if isinstance(template_obj.header_mapping_json, str)
                else template_obj.header_mapping_json
            )
        except Exception as e:
            print(f"⚠️ Failed reading custom header_mapping_json field: {str(e)}")

    if not active_landmarks or not isinstance(active_landmarks, dict):
        active_landmarks = {
            "date": ["date", "txn date", "transaction date", "value date", "val date"],
            "narration": [
                "particulars",
                "description",
                "narration description",
                "narration",
                "remarks",
            ],
            "debit": [
                "withdrawals",
                "debit",
                "debit (-)",
                "withdrawal amount",
                "payment",
            ],
            "credit": ["deposits", "credit", "credit (+)", "deposit amount", "receipt"],
            "balance": [
                "balance amount",
                "balance",
                "running bal",
                "running balance",
                "closing balance",
            ],
            "chq_ref": [
                "cheque number",
                "ref no./cheque no.",
                "chq/ref",
                "reference number",
                "chq no",
            ],
        }

    field_map_rules = {
        "post_date": active_landmarks.get("date")
        or active_landmarks.get("post_date")
        or ["date"],
        "narration": active_landmarks.get("narration") or ["narration"],
        "debit": active_landmarks.get("debit") or ["debit"],
        "credit": active_landmarks.get("credit") or ["credit"],
        "balance": active_landmarks.get("balance") or ["balance"],
        "chq_ref": active_landmarks.get("chq_ref")
        or active_landmarks.get("ref_no")
        or ["cheque"],
    }

    detected_headers = None
    header_index_map = {}
    intermediate_txns = []
    header_row_idx = -1

    # ─── STEP 2: LOCATE TARGET HEADER INDEX ───
    for idx, row in enumerate(all_rows):
        cleaned_cells = [str(cell).strip().lower() for cell in row]

        has_date = any(
            any(str(d).lower().strip() in cell for d in field_map_rules["post_date"])
            for cell in cleaned_cells
        )
        has_narr = any(
            any(str(n).lower().strip() in cell for n in field_map_rules["narration"])
            for cell in cleaned_cells
        )

        if has_date and has_narr:
            detected_headers = [str(cell).strip().lower() for cell in row]
            header_row_idx = idx
            break

    if header_row_idx == -1:
        raise ValueError(
            "❌ Layout Exception: Could not map header landmarks from active template context configuration."
        )

    # ─── STEP 3: MAP RUNTIME COLUMN CELL INDICES ───
    for field_key, fallback_labels in field_map_rules.items():
        for label in fallback_labels:
            clean_label = str(label).lower().strip()
            for idx, header in enumerate(detected_headers):
                if clean_label == header or clean_label in header:
                    header_index_map[field_key] = idx
                    break
            if field_key in header_index_map:
                break

    # ─── STEP 4: SINGLE-PASS DATA PROCESSING AND DATE NORMALIZATION ───
    current_txn = None
    date_sentinel = re.compile(r"\d{1,2}|[A-Za-z]{3}")

    # 🎯 Define common system noise keywords to completely ignore trailing system footnotes
    FOOTER_NOISE_KEYWORDS = [
        "computer generated statement",
        "does not require a signature",
        "page total",
        "brought forward",
        "carried forward",
        "end of statement",
    ]

    for row in all_rows[header_row_idx + 1 :]:
        if not row or not any(row):
            continue

        # Combine the entire row into a flat string to check for trailing footnotes up front
        full_row_text = " ".join([str(cell) for cell in row]).lower()
        if any(keyword in full_row_text for keyword in FOOTER_NOISE_KEYWORDS):
            logger.info(
                f"🧼 Tabular Engine dropped trailing system footnote line: '{full_row_text[:40]}...'"
            )
            continue  # 🎯 Bypasses the line completely!

        row_date = (
            row[header_index_map["post_date"]].strip()
            if "post_date" in header_index_map
            and header_index_map["post_date"] < len(row)
            else ""
        )
        row_narr = (
            row[header_index_map["narration"]].strip()
            if "narration" in header_index_map
            and header_index_map["narration"] < len(row)
            else ""
        )
        row_deb = (
            row[header_index_map["debit"]].strip()
            if "debit" in header_index_map and header_index_map["debit"] < len(row)
            else ""
        )
        row_crd = (
            row[header_index_map["credit"]].strip()
            if "credit" in header_index_map and header_index_map["credit"] < len(row)
            else ""
        )
        row_bal = (
            row[header_index_map["balance"]].strip()
            if "balance" in header_index_map and header_index_map["balance"] < len(row)
            else ""
        )
        row_ref = (
            row[header_index_map["chq_ref"]].strip()
            if "chq_ref" in header_index_map and header_index_map["chq_ref"] < len(row)
            else "-"
        )

        # 🎯 FIX: Remove ALL internal spaces, tabs, and line breaks to unify the identifier string
        if row_ref and row_ref not in ["", "None", "-"]:
            # Re-join all non-empty characters with no spacing at all
            row_ref = "".join(row_ref.split())
        else:
            row_ref = "-"

        has_valid_date = bool(date_sentinel.search(row_date)) and len(row_date) >= 6

        if has_valid_date:
            if current_txn:
                intermediate_txns.append(current_txn)

            # 🎯 INLINE DATE STANDARDIZATION HANDLER FOR MULTIPLE FORMATS
            normalized_date = row_date
            cleaned_date_str = re.sub(r"\s+", " ", row_date.strip())

            date_formats = [
                "%d-%b-%Y",
                "%d-%b-%y",
                "%d-%m-%Y",
                "%d-%m-%y",
                "%d/%m/%Y",
                "%d/%m/%y",
                "%Y-%m-%d",
                "%d %b %Y",
            ]

            for fmt in date_formats:
                try:
                    normalized_date = datetime.strptime(cleaned_date_str, fmt).strftime(
                        "%d-%m-%Y"
                    )
                    break
                except ValueError:
                    continue

            current_txn = {
                "post_date": normalized_date,
                "value_date": normalized_date,
                "narration": row_narr,
                "cheque_ref": row_ref,
                "debit": row_deb if row_deb and row_deb != "nan" else "-",
                "credit": row_crd if row_crd and row_crd != "nan" else "-",
                "balance": row_bal if row_bal and row_bal != "nan" else "0.00",
            }
        else:
            if current_txn and row_narr:
                # Extra guard: Make sure the appended multiline description isn't noise either
                if not any(
                    keyword in row_narr.lower() for keyword in FOOTER_NOISE_KEYWORDS
                ):
                    current_txn["narration"] += f" {row_narr}"
                if (
                    row_deb
                    and row_deb != "-"
                    and row_deb != "nan"
                    and current_txn["debit"] == "-"
                ):
                    current_txn["debit"] = row_deb
                if (
                    row_crd
                    and row_crd != "-"
                    and row_crd != "nan"
                    and current_txn["credit"] == "-"
                ):
                    current_txn["credit"] = row_crd
                if row_bal and row_bal != "0.00" and row_bal != "" and row_bal != "nan":
                    current_txn["balance"] = row_bal

    if current_txn:
        intermediate_txns.append(current_txn)

    return intermediate_txns
