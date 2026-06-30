# backend/tracker/parsers_v1/strategies/strict_matrix_v3.py

import re
import logging
from ..utils import normalizer as norm

logger = logging.getLogger(__name__)


def execute(pages_raw_data, template_obj, account_id, existing_database_hashes):
    """
    GEOMETRIC WRAPPED LINE PARSER (V3 - COMPACT PRODUCTION HARDENED):
    Maps transactions using relative horizontal column boundaries to prevent
    short character formats from shifting across ledger columns.
    """
    DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{2,4}|^\d{2}/\d{2}/\d{2,4}")
    NUMERIC_RE = re.compile(
        r"\b\d{1,3}(?:,\d{3})*(?:\.\d{2})(?:CR|DR|Cr|Dr)?\b|\b\d+(?:\.\d{2})(?:CR|DR|Cr|Dr)?\b"
    )
    BF_RE = re.compile(r"\bB[/\s]?F\b|\bBROUGHT\s+FORWARD\b", re.IGNORECASE)

    # 🎯 BALANCED COLUMN MIDPOINT:
    # Debits (Withdrawals) cluster around x=48%-54%. Credits (Deposits) cluster around x=58%-64%.
    COLUMN_MIDPOINT_X = 56.5

    intermediate_txns = []
    computed_opening_balance = 0.0
    current_txn = None

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
                    # Safe transactional value coordinates boundaries mask check
                    if NUMERIC_RE.search(t["text"]) and t["x"] > 35.0:
                        numeric_tokens.append(t)
                    else:
                        narration_pieces.append(t["text"])

                debit_val = "-"
                credit_val = "-"
                balance_val = "-"

                if len(numeric_tokens) == 1:
                    t_tok = numeric_tokens[0]
                    t_amt = (
                        t_tok["text"]
                        .upper()
                        .replace("CR", "")
                        .replace("DR", "")
                        .replace(",", "")
                        .strip()
                    )
                    if t_tok["x"] <= COLUMN_MIDPOINT_X:
                        debit_val = t_amt
                    elif t_tok["x"] <= 68.0:
                        credit_val = t_amt
                    else:
                        balance_val = t_amt

                elif len(numeric_tokens) >= 2:
                    # Capture running balance string metrics cleanly
                    bal_tok = numeric_tokens[-1]
                    bal_text_upper = bal_tok["text"].upper()
                    balance_val = (
                        bal_text_upper.replace("CR", "")
                        .replace("DR", "")
                        .replace(",", "")
                        .strip()
                    )

                    # Capture true financial magnitude token
                    amt_tok = numeric_tokens[-2]
                    amt_text_raw = amt_tok["text"]
                    amt_val = (
                        amt_text_raw.upper()
                        .replace("CR", "")
                        .replace("DR", "")
                        .replace(",", "")
                        .strip()
                    )

                    # 🎯 ADJUSTED LANE ALLOCATION MATRICES
                    # If the balance or amount string explicitly contains a directional indicator suffix:
                    if (
                        "DR" in bal_text_upper
                        and len(numeric_tokens) == 2
                        and amt_tok["x"] > COLUMN_MIDPOINT_X
                    ):
                        # Fallback case for specific fee lines running near the column edges
                        debit_val = amt_val
                    elif amt_tok["x"] < COLUMN_MIDPOINT_X:
                        debit_val = amt_val
                    else:
                        credit_val = amt_val

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

    # Flatten out arrays safely before return statements execution
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
            "NOMINEE:",
            "MODE OF OPR.:",
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

    # Reverse-engineer opening balance seeds anchors baseline if missing
    if computed_opening_balance == 0.00 and final_txns:
        first_tx = final_txns[0]
        try:
            first_bal = (
                float(first_tx["balance"]) if first_tx["balance"] != "-" else 0.00
            )
            first_dr = float(first_tx["debit"]) if first_tx["debit"] != "-" else 0.00
            first_cr = float(first_tx["credit"]) if first_tx["credit"] != "-" else 0.00
            if first_bal != 0.00:
                computed_opening_balance = first_bal - first_cr + first_dr
        except Exception:
            pass

    return final_txns, computed_opening_balance, []
