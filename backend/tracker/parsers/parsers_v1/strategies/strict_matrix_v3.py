# backend/tracker/parsers_v1/strategies/strict_matrix_v3.py

# backend/tracker/parsers_v1/strategies/strict_matrix_v3.py

import re
import logging
from ..utils import normalizer as norm

logger = logging.getLogger(__name__)


def execute(pages_raw_data, template_obj, account_id, existing_database_hashes):
    """
    GEOMETRIC WRAPPED LINE PARSER (V3 - COMPACT PRODUCTION HARDENED)
    Handles multi-line wrapped narration rows, excludes page totals, and calculates
    implicit opening balances dynamically when no physical B/F row is present.
    """
    DATE_RE = re.compile(r"^\d{2}[-/\.]\d{2}[-/\.]\d{2,4}")
    MONEY_RE = re.compile(
        r"^\d{1,3}(?:,\d{3})*(?:\.\d{2})(?:CR|DR|Cr|Dr)?$|^\d+(?:\.\d{2})(?:CR|DR|Cr|Dr)?$"
    )
    BF_RE = re.compile(r"\bB[/\s]?F\b|\bBROUGHT\s+FORWARD\b", re.IGNORECASE)

    intermediate_txns = []
    computed_opening_balance = 0.0

    # 🎯 FOOTER NOISE SIGNATURES TO STRICTLY IGNORE
    NOISE_SIGNATURES = [
        "PAGE TOTAL",
        "GRAND TOTAL",
        "VISIT US AT",
        "CUSTOMER CARE",
        "BR. MAIL ID",
        "THIS IS AN AUTHENTICATED",
        "SOUTHINDIANBANK",
        "EFF AVL AMT",
        "STATEMENT OF ACCOUNT",
    ]

    for page_data in pages_raw_data:
        page_idx = page_data["page_idx"]
        page_width = float(page_data.get("page_width", 595.0))
        page_height = float(page_data.get("page_height", 842.0))
        words = page_data["words"]

        # ─── STEP 1: HORIZONTAL LINE CLUSTERING ───
        sorted_words = sorted(words, key=lambda w: (w[1], w[0]))
        lines_map = {}

        for w in sorted_words:
            x0, y0, text = w[0], w[1], w[4].strip()
            if not text:
                continue

            # Filter out footer noise text at individual token level
            if any(
                sig in text.upper()
                for sig in ["SOUTHINDIANBANK", "1-800-425-1809", "BR0624@SIB"]
            ):
                continue

            line_key = round(y0 / 2.0) * 2.0
            if line_key not in lines_map:
                lines_map[line_key] = []

            lines_map[line_key].append(
                {
                    "text": text,
                    "x": round((x0 / page_width) * 100, 2),
                    "y": round((y0 / page_height) * 100, 2),
                    "raw_y": y0,
                }
            )

        # ─── STEP 2: BUILD CLEAN LOGICAL BLOCKS ───
        sorted_y_keys = sorted(lines_map.keys())
        logical_blocks = []
        current_block = None

        for line_y in sorted_y_keys:
            row_tokens = sorted(lines_map[line_y], key=lambda t: t["x"])
            line_text = " ".join([t["text"] for t in row_tokens]).strip()
            line_upper = line_text.upper()

            # Check explicit Brought Forward (B/F) line
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

            # Ignore entire lines matching footer or table header noise signatures
            if any(sig in line_upper for sig in NOISE_SIGNATURES):
                continue
            if (
                "--------" in line_text
                or "PARTICULARS" in line_upper
                or "WITHDRAWALS" in line_upper
            ):
                continue

            first_token_x = row_tokens[0]["x"] if row_tokens else 100.0
            is_new_txn_anchor = bool(DATE_RE.match(line_text)) and first_token_x < 20.0

            if is_new_txn_anchor:
                if current_block:
                    logical_blocks.append(current_block)
                current_block = {
                    "page_idx": page_idx,
                    "line_y": line_y,
                    "date": DATE_RE.match(line_text).group(0),
                    "all_tokens": list(row_tokens),
                }
            else:
                # Only append as continuation line if spatial Y-gap is under 15pt
                if current_block:
                    last_token_y = current_block["all_tokens"][-1]["raw_y"]
                    if abs(line_y - last_token_y) <= 15.0:
                        current_block["all_tokens"].extend(row_tokens)
                    else:
                        logical_blocks.append(current_block)
                        current_block = None

        if current_block:
            logical_blocks.append(current_block)

        # ─── STEP 3: EXTRACT COLUMNS FROM LOGICAL BLOCK ───
        for block in logical_blocks:
            numeric_tokens = []
            narration_pieces = []

            for t in block["all_tokens"]:
                raw_text = t["text"].strip()
                if DATE_RE.match(raw_text):
                    continue

                # Token must be in numeric column region (x > 50%) and match monetary format
                if t["x"] > 50.0 and MONEY_RE.match(raw_text):
                    numeric_tokens.append(t)
                else:
                    if not any(
                        sig in raw_text.upper()
                        for sig in ["PAGE", "TOTAL", "VISIT", "GRAND"]
                    ):
                        narration_pieces.append(raw_text)

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
                if t_tok["x"] <= 68.0:
                    debit_val = t_amt
                elif t_tok["x"] <= 82.0:
                    credit_val = t_amt
                else:
                    balance_val = t_amt

            elif len(numeric_tokens) >= 2:
                bal_tok = numeric_tokens[-1]
                balance_val = (
                    bal_tok["text"]
                    .upper()
                    .replace("CR", "")
                    .replace("DR", "")
                    .replace(",", "")
                    .strip()
                )

                amt_tok = numeric_tokens[-2]
                amt_val = (
                    amt_tok["text"]
                    .upper()
                    .replace("CR", "")
                    .replace("DR", "")
                    .replace(",", "")
                    .strip()
                )

                if amt_tok["x"] <= 68.0:
                    debit_val = amt_val
                else:
                    credit_val = amt_val

            combined_narration = " ".join(narration_pieces).strip()
            combined_narration = re.sub(r"\s+", " ", combined_narration)

            try:
                norm_date = norm.normalize_date(block["date"], template_obj.date_format)
            except Exception:
                norm_date = block["date"]

            intermediate_txns.append(
                {
                    "id": f"row_geo_{block['page_idx']}_{int(block['line_y'])}",
                    "post_date": norm_date,
                    "value_date": norm_date,
                    "narration": combined_narration,
                    "debit": debit_val,
                    "credit": credit_val,
                    "balance": balance_val,
                    "page_idx": block["page_idx"],
                }
            )

    # ─── STEP 4: FINAL FILTER ───
    final_txns = []
    for tx in intermediate_txns:
        if tx["debit"] == "-" and tx["credit"] == "-":
            continue
        if len(tx["narration"]) < 3 or any(
            sig in tx["narration"].upper() for sig in ["PAGE TOTAL", "GRAND TOTAL"]
        ):
            continue

        final_txns.append(tx)

    # ─── STEP 5: AUTOMATIC REVERSE-ENGINEERING OF OPENING BALANCE ───
    # If no explicit B/F text line was present on Page 1, derive opening balance from Row 1
    if computed_opening_balance == 0.00 and final_txns:
        first_tx = final_txns[0]
        try:
            first_bal = (
                float(
                    first_tx["balance"]
                    .upper()
                    .replace("CR", "")
                    .replace("DR", "")
                    .replace(",", "")
                )
                if first_tx["balance"] != "-"
                else 0.00
            )
            first_dr = (
                float(first_tx["debit"].replace(",", ""))
                if first_tx["debit"] != "-"
                else 0.00
            )
            first_cr = (
                float(first_tx["credit"].replace(",", ""))
                if first_tx["credit"] != "-"
                else 0.00
            )

            if first_bal != 0.00:
                # Math: Opening = First_Row_Balance + First_Row_Withdrawal - First_Row_Deposit
                computed_opening_balance = round(first_bal + first_dr - first_cr, 2)
        except Exception as err:
            logger.warning(
                f"Failed to reverse-engineer baseline opening balance: {err}"
            )

    return final_txns, computed_opening_balance, []


# this is the second vesrion working one SIB
# # backend/tracker/parsers_v1/strategies/strict_matrix_v3.py

# import re
# import logging
# from ..utils import normalizer as norm

# logger = logging.getLogger(__name__)


# def execute(pages_raw_data, template_obj, account_id, existing_database_hashes):
#     DATE_RE = re.compile(r"^\d{2}[-/\.]\d{2}[-/\.]\d{2,4}")
#     MONEY_RE = re.compile(
#         r"^\d{1,3}(?:,\d{3})*(?:\.\d{2})(?:CR|DR|Cr|Dr)?$|^\d+(?:\.\d{2})(?:CR|DR|Cr|Dr)?$"
#     )
#     BF_RE = re.compile(r"\bB[/\s]?F\b|\bBROUGHT\s+FORWARD\b", re.IGNORECASE)

#     COLUMN_MIDPOINT_X = (
#         65.0  # Withdrawals: ~55%-68%, Deposits: ~68%-82%, Balance: ~82%-100%
#     )

#     intermediate_txns = []
#     computed_opening_balance = 0.0

#     for page_data in pages_raw_data:
#         page_idx = page_data["page_idx"]
#         page_width = float(page_data.get("page_width", 595.0))
#         page_height = float(page_data.get("page_height", 842.0))
#         words = page_data["words"]

#         # ─── STEP 1: HORIZONTAL LINE CLUSTERING ───
#         sorted_words = sorted(words, key=lambda w: (w[1], w[0]))
#         lines_map = {}

#         for w in sorted_words:
#             x0, y0, text = w[0], w[1], w[4].strip()
#             if not text:
#                 continue

#             line_key = round(y0 / 2.5) * 2.5
#             if line_key not in lines_map:
#                 lines_map[line_key] = []

#             lines_map[line_key].append(
#                 {
#                     "text": text,
#                     "x": round((x0 / page_width) * 100, 2),
#                     "y": round((y0 / page_height) * 100, 2),
#                 }
#             )

#         # ─── STEP 2: GROUP MULTILINE VISUAL ROWS INTO LOGICAL BLOCKS ───
#         sorted_y_keys = sorted(lines_map.keys())
#         logical_blocks = []
#         current_block = None

#         for line_y in sorted_y_keys:
#             row_tokens = sorted(lines_map[line_y], key=lambda t: t["x"])
#             line_text = " ".join([t["text"] for t in row_tokens]).strip()
#             line_upper = line_text.upper()

#             # Ignore Table Header and Footer Noise
#             if (
#                 "STATEMENT OF ACCOUNT" in line_upper
#                 or "PARTICULARS" in line_upper
#                 or "WITHDRAWALS" in line_upper
#             ):
#                 continue
#             if (
#                 "--------" in line_text
#                 or "PAGE TOTAL:" in line_upper
#                 or "GRAND TOTAL:" in line_upper
#             ):
#                 continue

#             # Check if this visual line starts with a Date Anchor (New Transaction)
#             first_token_x = row_tokens[0]["x"] if row_tokens else 100.0
#             is_new_txn_anchor = bool(DATE_RE.match(line_text)) and first_token_x < 20.0

#             if is_new_txn_anchor:
#                 if current_block:
#                     logical_blocks.append(current_block)
#                 current_block = {
#                     "page_idx": page_idx,
#                     "line_y": line_y,
#                     "date": DATE_RE.match(line_text).group(0),
#                     "all_tokens": list(row_tokens),
#                 }
#             else:
#                 if current_block:
#                     current_block["all_tokens"].extend(row_tokens)

#         if current_block:
#             logical_blocks.append(current_block)

#         # ─── STEP 3: EXTRACT COLUMNS FROM ENTIRE LOGICAL BLOCK ───
#         for block in logical_blocks:
#             numeric_tokens = []
#             narration_pieces = []

#             for t in block["all_tokens"]:
#                 raw_text = t["text"].strip()

#                 # Skip date tokens
#                 if DATE_RE.match(raw_text):
#                     continue

#                 clean_val = raw_text.replace(",", "").upper()

#                 # If token is in numeric column region (x > 50%) and matches currency format
#                 if t["x"] > 50.0 and MONEY_RE.match(raw_text):
#                     numeric_tokens.append(t)
#                 else:
#                     narration_pieces.append(raw_text)

#             debit_val = "-"
#             credit_val = "-"
#             balance_val = "-"

#             if len(numeric_tokens) == 1:
#                 t_tok = numeric_tokens[0]
#                 t_amt = (
#                     t_tok["text"]
#                     .upper()
#                     .replace("CR", "")
#                     .replace("DR", "")
#                     .replace(",", "")
#                     .strip()
#                 )
#                 if t_tok["x"] <= 68.0:
#                     debit_val = t_amt
#                 elif t_tok["x"] <= 82.0:
#                     credit_val = t_amt
#                 else:
#                     balance_val = t_amt

#             elif len(numeric_tokens) >= 2:
#                 # Last token in block is Balance
#                 bal_tok = numeric_tokens[-1]
#                 balance_val = (
#                     bal_tok["text"]
#                     .upper()
#                     .replace("CR", "")
#                     .replace("DR", "")
#                     .replace(",", "")
#                     .strip()
#                 )

#                 # Second to last token is Debit or Credit
#                 amt_tok = numeric_tokens[-2]
#                 amt_val = (
#                     amt_tok["text"]
#                     .upper()
#                     .replace("CR", "")
#                     .replace("DR", "")
#                     .replace(",", "")
#                     .strip()
#                 )

#                 if amt_tok["x"] <= 68.0:
#                     debit_val = amt_val
#                 else:
#                     credit_val = amt_val

#             combined_narration = " ".join(narration_pieces).strip()
#             combined_narration = re.sub(r"\s+", " ", combined_narration)

#             try:
#                 norm_date = norm.normalize_date(block["date"], template_obj.date_format)
#             except Exception:
#                 norm_date = block["date"]

#             intermediate_txns.append(
#                 {
#                     "id": f"row_geo_{block['page_idx']}_{int(block['line_y'])}",
#                     "post_date": norm_date,
#                     "value_date": norm_date,
#                     "narration": combined_narration,
#                     "debit": debit_val,
#                     "credit": credit_val,
#                     "balance": balance_val,
#                     "page_idx": block["page_idx"],
#                 }
#             )

#     # Filter out empty rows
#     final_txns = [
#         tx
#         for tx in intermediate_txns
#         if not (tx["debit"] == "-" and tx["credit"] == "-")
#         and len(tx["narration"]) >= 3
#     ]

#     return final_txns, computed_opening_balance, []


# this is our older working South Indian Bank......
# # backend/tracker/parsers_v1/strategies/strict_matrix_v3.py

# import re
# import logging
# from ..utils import normalizer as norm

# logger = logging.getLogger(__name__)


# def execute(pages_raw_data, template_obj, account_id, existing_database_hashes):
#     """
#     GEOMETRIC WRAPPED LINE PARSER (V3 - COMPACT PRODUCTION HARDENED):
#     Maps transactions using relative horizontal column boundaries to prevent
#     short character formats from shifting across ledger columns.
#     """
#     DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{2,4}|^\d{2}/\d{2}/\d{2,4}")
#     NUMERIC_RE = re.compile(
#         r"\b\d{1,3}(?:,\d{3})*(?:\.\d{2})(?:CR|DR|Cr|Dr)?\b|\b\d+(?:\.\d{2})(?:CR|DR|Cr|Dr)?\b"
#     )
#     BF_RE = re.compile(r"\bB[/\s]?F\b|\bBROUGHT\s+FORWARD\b", re.IGNORECASE)

#     # 🎯 BALANCED COLUMN MIDPOINT:
#     # Debits (Withdrawals) cluster around x=48%-54%. Credits (Deposits) cluster around x=58%-64%.
#     COLUMN_MIDPOINT_X = 56.5

#     intermediate_txns = []
#     computed_opening_balance = 0.0
#     current_txn = None

#     for page_data in pages_raw_data:
#         page_idx = page_data["page_idx"]
#         page_width = page_data["page_width"]
#         words = page_data["words"]

#         # ─── STEP 1: HORIZONTAL ROW CLUSTERING ───
#         sorted_words = sorted(words, key=lambda w: (w[1], w[0]))
#         lines_map = {}

#         for w in sorted_words:
#             x0, y0, text = w[0], w[1], w[4].strip()
#             if not text:
#                 continue

#             line_key = round(y0 / 1.5) * 1.5
#             if line_key not in lines_map:
#                 lines_map[line_key] = []

#             lines_map[line_key].append(
#                 {
#                     "text": text,
#                     "x": round((x0 / page_width) * 100, 2),
#                     "y": round((y0 / 842.0) * 100, 2),
#                 }
#             )

#         if current_txn:
#             intermediate_txns.append(current_txn)
#             current_txn = None

#         # ─── STEP 2: ROWS PROCESSING LOOP ───
#         sorted_y_keys = sorted(lines_map.keys())

#         for idx, line_y in enumerate(sorted_y_keys):
#             row_tokens = sorted(lines_map[line_y], key=lambda t: t["x"])
#             if not row_tokens:
#                 continue

#             line_text = " ".join([t["text"] for t in row_tokens]).strip()
#             line_upper = line_text.upper()

#             FOOTER_NOISE = [
#                 "PAGE TOTAL:",
#                 "GRAND TOTAL:",
#                 "EFF AVL AMT",
#                 "THIS IS AN AUTHENTICATED STATEMENT",
#                 "ACCOUNT HOLDERS ARE REQUESTED",
#                 "THE BANK OF ANY DISCREPANCY",
#                 "DATE STAMP",
#                 "PRINTED BY:",
#                 "SIB EXPRESS",
#                 "FOR SPEEDY REMITTANCE",
#                 "AVAIL SIB EXPRESS",
#                 "HADI EXPRESS",
#                 "BR0624@SIB.CO.IN",
#             ]

#             if "--------" in line_text or any(
#                 f_sig in line_upper for f_sig in FOOTER_NOISE
#             ):
#                 if current_txn:
#                     intermediate_txns.append(current_txn)
#                     current_txn = None
#                 continue

#             if BF_RE.search(line_text):
#                 for t in reversed(row_tokens):
#                     clean_t = (
#                         t["text"]
#                         .upper()
#                         .replace("CR", "")
#                         .replace("DR", "")
#                         .replace(",", "")
#                         .strip()
#                     )
#                     if re.match(r"^\d+(?:\.\d{2})?$", clean_t):
#                         try:
#                             computed_opening_balance = float(clean_t)
#                             break
#                         except ValueError:
#                             pass
#                 continue

#             date_match = DATE_RE.match(line_text)
#             is_valid_row_anchor = False
#             extracted_date = None

#             if date_match and row_tokens[0]["x"] < 25.0:
#                 is_valid_row_anchor = True
#                 extracted_date = date_match.group(0)

#             if is_valid_row_anchor and extracted_date:
#                 if current_txn:
#                     intermediate_txns.append(current_txn)

#                 numeric_tokens = []
#                 narration_pieces = []

#                 for t in row_tokens:
#                     if DATE_RE.match(t["text"]):
#                         continue
#                     # Safe transactional value coordinates boundaries mask check
#                     if NUMERIC_RE.search(t["text"]) and t["x"] > 35.0:
#                         numeric_tokens.append(t)
#                     else:
#                         narration_pieces.append(t["text"])

#                 debit_val = "-"
#                 credit_val = "-"
#                 balance_val = "-"

#                 if len(numeric_tokens) == 1:
#                     t_tok = numeric_tokens[0]
#                     t_amt = (
#                         t_tok["text"]
#                         .upper()
#                         .replace("CR", "")
#                         .replace("DR", "")
#                         .replace(",", "")
#                         .strip()
#                     )
#                     if t_tok["x"] <= COLUMN_MIDPOINT_X:
#                         debit_val = t_amt
#                     elif t_tok["x"] <= 68.0:
#                         credit_val = t_amt
#                     else:
#                         balance_val = t_amt

#                 elif len(numeric_tokens) >= 2:
#                     # Capture running balance string metrics cleanly
#                     bal_tok = numeric_tokens[-1]
#                     bal_text_upper = bal_tok["text"].upper()
#                     balance_val = (
#                         bal_text_upper.replace("CR", "")
#                         .replace("DR", "")
#                         .replace(",", "")
#                         .strip()
#                     )

#                     # Capture true financial magnitude token
#                     amt_tok = numeric_tokens[-2]
#                     amt_text_raw = amt_tok["text"]
#                     amt_val = (
#                         amt_text_raw.upper()
#                         .replace("CR", "")
#                         .replace("DR", "")
#                         .replace(",", "")
#                         .strip()
#                     )

#                     # 🎯 ADJUSTED LANE ALLOCATION MATRICES
#                     # If the balance or amount string explicitly contains a directional indicator suffix:
#                     if (
#                         "DR" in bal_text_upper
#                         and len(numeric_tokens) == 2
#                         and amt_tok["x"] > COLUMN_MIDPOINT_X
#                     ):
#                         # Fallback case for specific fee lines running near the column edges
#                         debit_val = amt_val
#                     elif amt_tok["x"] < COLUMN_MIDPOINT_X:
#                         debit_val = amt_val
#                     else:
#                         credit_val = amt_val

#                 try:
#                     norm_date = norm.normalize_date(
#                         extracted_date, template_obj.date_format
#                     )
#                 except Exception:
#                     norm_date = extracted_date

#                 current_txn = {
#                     "id": f"row_geo_{page_idx}_{int(line_y)}",
#                     "post_date": norm_date,
#                     "value_date": norm_date,
#                     "narration_lines": [" ".join(narration_pieces)],
#                     "debit": debit_val,
#                     "credit": credit_val,
#                     "balance": balance_val,
#                     "page_idx": page_idx,
#                 }
#             else:
#                 if current_txn:
#                     current_txn["narration_lines"].append(line_text)

#     if current_txn:
#         intermediate_txns.append(current_txn)

#     # Flatten out arrays safely before return statements execution
#     final_txns = []
#     for tx in intermediate_txns:
#         combined_narration = " ".join(tx["narration_lines"]).strip()
#         combined_narration = re.sub(r"\s+", " ", combined_narration)
#         payload_upper = combined_narration.upper()

#         HEADER_LEAK_SIGNATURES = (
#             "IFSC :",
#             "A/C NO:",
#             "CUSTOMER ID:",
#             "CURRENCY CODE:",
#             "BU.SUSEELAN@GMAIL.COM",
#             "NOMINEE:",
#             "MODE OF OPR.:",
#         )
#         if any(h_sig in payload_upper for h_sig in HEADER_LEAK_SIGNATURES):
#             continue
#         if tx["debit"] == "-" and tx["credit"] == "-":
#             continue
#         if not combined_narration or len(combined_narration) < 3:
#             continue

#         tx["narration"] = combined_narration
#         del tx["narration_lines"]
#         final_txns.append(tx)

#     # Reverse-engineer opening balance seeds anchors baseline if missing
#     if computed_opening_balance == 0.00 and final_txns:
#         first_tx = final_txns[0]
#         try:
#             first_bal = (
#                 float(first_tx["balance"]) if first_tx["balance"] != "-" else 0.00
#             )
#             first_dr = float(first_tx["debit"]) if first_tx["debit"] != "-" else 0.00
#             first_cr = float(first_tx["credit"]) if first_tx["credit"] != "-" else 0.00
#             if first_bal != 0.00:
#                 computed_opening_balance = first_bal - first_cr + first_dr
#         except Exception:
#             pass

#     return final_txns, computed_opening_balance, []
