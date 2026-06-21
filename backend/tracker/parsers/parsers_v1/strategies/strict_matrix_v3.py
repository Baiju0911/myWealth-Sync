# backend/tracker/parsers_v1/strategies/strict_matrix_v3.py

import re
import logging
from ..utils import normalizer as norm

logger = logging.getLogger(__name__)


def execute(pages_raw_data, template_obj, account_id, existing_database_hashes):
    """
    GEOMETRIC WRAPPED LINE PARSER (V3): Maps transactions using strict coordinate tracking.
    Includes automated initial balance back-calculation fallbacks for statements lacking
    explicit B/F descriptor rows.
    """
    DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{2,4}|^\d{2}/\d{2}/\d{2,4}")
    NUMERIC_RE = re.compile(
        r"\b\d{1,3}(?:,\d{2,3})*(?:\.\d{2})(?:CR|DR|Cr|Dr)?\b|\b\d{1,3}(?:,\d{3})*(?:\.\d{2})(?:CR|DR|Cr|Dr)?\b|\b\d+(?:\.\d{2})\b"
    )
    BF_RE = re.compile(r"\bB[/\s]?F\b|\bBROUGHT\s+FORWARD\b", re.IGNORECASE)

    CREDIT_ZONE_X_START = 56.0

    intermediate_txns = []
    computed_opening_balance = 0.0
    current_txn = None

    total_pages = len(pages_raw_data) if pages_raw_data else 0

    for page_data in pages_raw_data:
        page_idx = page_data["page_idx"]
        page_width = page_data["page_width"]
        words = page_data["words"]

        # ─── STEP 1: HORIZONTAL ROW CLUSTERING ───
        sorted_words = sorted(words, key=lambda w: (w[1], w[0]))
        lines_map = {}

        for w in sorted_words:
            x0, y0, text = w[0], w[1], w[4].strip()
            if not text:
                continue

            line_key = round(y0 / 1.5) * 1.5
            if line_key not in lines_map:
                lines_map[line_key] = []

            lines_map[line_key].append(
                {
                    "text": text,
                    "x": round((x0 / page_width) * 100, 2),
                    "y": round((y0 / 842.0) * 100, 2),
                }
            )

        if current_txn:
            intermediate_txns.append(current_txn)
            current_txn = None

        # ─── STEP 2: ROWS PROCESSING LOOP ───
        sorted_y_keys = sorted(lines_map.keys())

        for idx, line_y in enumerate(sorted_y_keys):
            row_tokens = sorted(lines_map[line_y], key=lambda t: t["x"])
            if not row_tokens:
                continue

            line_text = " ".join([t["text"] for t in row_tokens]).strip()
            line_upper = line_text.upper()

            FOOTER_NOISE = [
                "PAGE TOTAL:",
                "GRAND TOTAL:",
                "EFF AVL AMT",
                "THIS IS AN AUTHENTICATED STATEMENT",
                "ACCOUNT HOLDERS ARE REQUESTED",
                "THE BANK OF ANY DISCREPANCY",
                "DATE STAMP",
                "PRINTED BY:",
                "SIB EXPRESS",
                "FOR SPEEDY REMITTANCE",
                "AVAIL SIB EXPRESS",
                "HADI EXPRESS",
                "BR0624@SIB.CO.IN",
            ]

            if "--------" in line_text or any(
                f_sig in line_upper for f_sig in FOOTER_NOISE
            ):
                if current_txn:
                    intermediate_txns.append(current_txn)
                    current_txn = None
                continue

            # 💰 EXTRACATION HARVESTER: Look backward on B/F rows to grab opening numbers before continuing
            if BF_RE.search(line_text):
                for t in reversed(row_tokens):
                    clean_t = (
                        t["text"]
                        .upper()
                        .replace("CR", "")
                        .replace("DR", "")
                        .replace(",", "")
                        .strip()
                    )
                    if re.match(r"^\d+(?:\.\d{2})?$", clean_t):
                        try:
                            computed_opening_balance = float(clean_t)
                            break
                        except ValueError:
                            pass
                continue

            date_match = DATE_RE.match(line_text)
            is_valid_row_anchor = False
            extracted_date = None

            if date_match and row_tokens[0]["x"] < 25.0:
                is_valid_row_anchor = True
                extracted_date = date_match.group(0)

            if is_valid_row_anchor and extracted_date:
                if current_txn:
                    intermediate_txns.append(current_txn)

                numeric_tokens = []
                narration_pieces = []
                for t in row_tokens:
                    if DATE_RE.match(t["text"]):
                        continue
                    if NUMERIC_RE.search(t["text"]):
                        numeric_tokens.append(t)
                    else:
                        narration_pieces.append(t["text"])

                debit_val = "-"
                credit_val = "-"
                balance_val = "-"

                if len(numeric_tokens) == 1:
                    tx_token = numeric_tokens[0]
                    tx_amt_clean = (
                        tx_token["text"]
                        .upper()
                        .replace("CR", "")
                        .replace("DR", "")
                        .replace(",", "")
                        .strip()
                    )
                    if tx_token["x"] < CREDIT_ZONE_X_START:
                        debit_val = tx_amt_clean
                    else:
                        credit_val = tx_amt_clean
                    balance_val = "-"

                elif len(numeric_tokens) >= 2:
                    balance_val = (
                        numeric_tokens[-1]["text"]
                        .upper()
                        .replace("CR", "")
                        .replace("DR", "")
                        .replace(",", "")
                        .strip()
                    )
                    tx_token = numeric_tokens[-2]
                    tx_amt_clean = (
                        tx_token["text"]
                        .upper()
                        .replace("CR", "")
                        .replace("DR", "")
                        .replace(",", "")
                        .strip()
                    )
                    if tx_token["x"] < CREDIT_ZONE_X_START:
                        debit_val = tx_amt_clean
                    else:
                        credit_val = tx_amt_clean

                try:
                    norm_date = norm.normalize_date(
                        extracted_date, template_obj.date_format
                    )
                except Exception:
                    norm_date = extracted_date

                current_txn = {
                    "id": f"row_geo_{page_idx}_{int(line_y)}",
                    "post_date": norm_date,
                    "value_date": norm_date,
                    "narration_lines": [" ".join(narration_pieces)],
                    "debit": debit_val,
                    "credit": credit_val,
                    "balance": balance_val,
                    "page_idx": page_idx,
                }
            else:
                if current_txn:
                    current_txn["narration_lines"].append(line_text)

    if current_txn:
        intermediate_txns.append(current_txn)
        current_txn = None

    # ─── STEP 3: FLATTEN AND SANITIZE OUTPUTS FOR STORAGE ───
    final_txns = []
    for tx in intermediate_txns:
        combined_narration = " ".join(tx["narration_lines"]).strip()
        combined_narration = re.sub(r"\s+", " ", combined_narration)
        payload_upper = combined_narration.upper()

        HEADER_LEAK_SIGNATURES = (
            "IFSC :",
            "A/C NO:",
            "CUSTOMER ID:",
            "CURRENCY CODE:",
            "BU.SUSEELAN@GMAIL.COM",
        )
        if any(h_sig in payload_upper for h_sig in HEADER_LEAK_SIGNATURES):
            continue

        if tx["debit"] == "-" and tx["credit"] == "-":
            continue

        if not combined_narration or len(combined_narration) < 3:
            continue

        tx["narration"] = combined_narration
        del tx["narration_lines"]
        final_txns.append(tx)

    # ─── 🎯 BACK-CALCULATION FALLBACK ENGINE ───
    # If no explicit opening balance row was scraped, deduce it using the first parsed entry's math
    if computed_opening_balance == 0.00 and final_txns:
        first_tx = final_txns[0]
        try:
            first_bal = (
                float(first_tx["balance"]) if first_tx["balance"] != "-" else 0.00
            )
            first_dr = float(first_tx["debit"]) if first_tx["debit"] != "-" else 0.00
            first_cr = float(first_tx["credit"]) if first_tx["credit"] != "-" else 0.00

            if first_bal != 0.00:
                # Reverse the action of the first transaction to find the true starting balance
                computed_opening_balance = first_bal - first_cr + first_dr
                logger.info(
                    f"🔮 [Fallback Engine] Deduced initial balance using first row entry: {computed_opening_balance}"
                )
        except (ValueError, KeyError):
            pass

    return final_txns, computed_opening_balance, []
