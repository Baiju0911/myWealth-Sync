import re
import json
from ..utils import normalizer as norm


def execute(pages_raw_data, template_obj, account_id, existing_database_hashes):
    """
    UNIVERSAL DYNAMIC RELATIVE MATRIX ENGINE: Driven entirely by database configurations.
    Bypasses structural drifting via a layout-agnostic Right-to-Left context router.
    """
    # ─── 📦 DYNAMIC DATABASE OVERRIDES UNPACKING ───
    try:
        signature = template_obj.signature_json
        if isinstance(signature, str):
            signature = json.loads(signature)
    except Exception:
        signature = {}

    regex_config = signature.get("regex_patterns", {})

    # 🎯 DATABASE DRIVEN REGEX: Load and clean pattern classes dynamically
    DATE_MATCH_RAW = regex_config.get(
        "DATE_MATCH", r"\d{2}-\d{2}-\d{4}|\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}"
    )
    NUMERIC_FINDER_RAW = regex_config.get("NUMERIC_FINDER", r"\d+(?:\.\d{2})")
    BALANCE_SIGN_RAW = regex_config.get("BALANCE_SIGN", r"(CR|DR)$")

    DATE_MATCH_RAW = DATE_MATCH_RAW.replace(r"\b", "")
    NUMERIC_FINDER_RAW = NUMERIC_FINDER_RAW.replace(r"\b", "")

    DATE_MATCH_REGEX = re.compile(DATE_MATCH_RAW)
    NUMERIC_FINDER_REGEX = re.compile(NUMERIC_FINDER_RAW, re.I)
    BALANCE_SIGN_REGEX = re.compile(BALANCE_SIGN_RAW, re.I)

    SYSTEM_NOISE_REGEX = [
        re.compile(p, re.I) for p in signature.get("system_noise_patterns", [])
    ]
    opening_balance_markers = signature.get("opening_balance_markers", [])
    db_table_headers_noise = signature.get("table_headers_noise") or []

    is_absolute_mode = signature.get("absolute_pixel_lanes") is not None
    debit_target_x = float(getattr(template_obj, "debit_x", 375.0))
    credit_target_x = float(getattr(template_obj, "credit_x", 445.0))
    balance_target_x = float(getattr(template_obj, "balance_x", 510.0))

    mid_point = (debit_target_x + credit_target_x) / 2
    y_tolerance = (
        float(getattr(template_obj, "y_tolerance", 3.0))
        if not is_absolute_mode
        else 8.5
    )
    header_skip_target = int(getattr(template_obj, "header_lines_to_skip", 0))

    raw_rows = []
    extracted_opening_balance = 0.0

    def auto_clean_date(date_str):
        try:
            if "-" in date_str and len(date_str.split("-")[0]) == 4:
                return date_str
            if "-" in date_str:
                p = date_str.split("-")
                return f"{p[2]}-{p[1]}-{p[0]}"
            return norm.normalize_date(date_str, template_obj.date_format)
        except Exception:
            return date_str

    # ─── 🧹 STEP 1: SPATIAL LINE BUILDER ───
    for page_data in pages_raw_data:
        page_idx = page_data["page_idx"]
        page_width = float(page_data["page_width"])

        page_text_dump = " ".join(
            [
                str(w[4]).upper() if len(w) > 4 else str(w[2]).upper()
                for w in page_data["words"]
            ]
        )
        if "STATEMENT SUMMARY" in page_text_dump and not any(
            h in page_text_dump for h in ["NARRATION", "DEBIT", "CREDIT", "PARTICULARS"]
        ):
            continue

        sorted_tokens = sorted(
            page_data["words"], key=lambda w: (float(w[1]), float(w[0]))
        )
        if not sorted_tokens:
            continue

        page_lines = []
        current_row_tokens = []
        first_tok = sorted_tokens[0]
        current_y_anchor = float(first_tok[1])
        init_x_val = (
            float(first_tok[0])
            if is_absolute_mode
            else round((float(first_tok[0]) / page_width) * 100, 2)
        )

        current_row_tokens.append(
            {
                "text": (
                    str(first_tok[4]).strip()
                    if len(first_tok) > 4
                    else str(first_tok[2])
                ),
                "x": init_x_val,
                "y": current_y_anchor,
            }
        )

        for tok in sorted_tokens[1:]:
            x0, y0 = float(tok[0]), float(tok[1])
            text_val = str(tok[4]).strip() if len(tok) > 4 else str(tok[2])
            x_val = x0 if is_absolute_mode else round((x0 / page_width) * 100, 2)

            if abs(y0 - current_y_anchor) <= y_tolerance:
                current_row_tokens.append({"text": text_val, "x": x_val, "y": y0})
            else:
                if current_row_tokens:
                    current_row_tokens.sort(key=lambda t: t["x"])
                    page_lines.append(
                        {
                            "full_line_text": " ".join(
                                [str(t["text"]) for t in current_row_tokens]
                            ),
                            "tokens": current_row_tokens,
                            "page_source": page_idx,
                        }
                    )
                current_y_anchor = y0
                current_row_tokens = [{"text": text_val, "x": x_val, "y": y0}]

        if current_row_tokens:
            current_row_tokens.sort(key=lambda t: t["x"])
            page_lines.append(
                {
                    "full_line_text": " ".join(
                        [str(t["text"]) for t in current_row_tokens]
                    ),
                    "tokens": current_row_tokens,
                    "page_source": page_idx,
                }
            )

        start_idx = header_skip_target if page_idx == 1 else 0
        if start_idx < len(page_lines):
            raw_rows.extend(page_lines[start_idx:])
        else:
            raw_rows.extend(page_lines)

    # ─── 🔍 STEP 2: HISTORICAL OPENING BALANCE PARSER ───
    for r in raw_rows:
        if any(
            re.search(marker, r["full_line_text"].upper())
            for marker in opening_balance_markers
        ):
            nums = [
                t["text"]
                for t in r["tokens"]
                if NUMERIC_FINDER_REGEX.search(t["text"].strip())
            ]
            if nums:
                extracted_opening_balance = norm.parse_float(nums[-1])
                break

    # ─── 🟢 STEP 3: TRANSACTION PARSER ENGINE ───
    intermediate_txns = []
    system_noise_records = []

    STANDALONE_NOISE_SIGNALS = [
        "STATEMENT SUMMARY",
        "BROUGHT FORWARD",
        "DR COUNT",
        "CR COUNT",
        "TOTAL DEBITS",
        "TOTAL CREDITS",
        "CLOSING BALANCE",
    ]

    filtered_rows = []
    for row in raw_rows:
        text_upper = str(row["full_line_text"]).upper()
        max_date_x = 95.0 if is_absolute_mode else 24.0

        has_date_anchor = any(
            DATE_MATCH_REGEX.search(str(t["text"]).strip())
            and float(t["x"]) < max_date_x
            for t in row["tokens"]
        )

        if any(thn.upper() in text_upper for thn in db_table_headers_noise):
            continue

        if not has_date_anchor and (
            any(sig in text_upper for sig in STANDALONE_NOISE_SIGNALS)
            or any(r.search(text_upper) for r in SYSTEM_NOISE_REGEX)
        ):
            system_noise_records.append(
                {
                    "id": f"noise_{row['page_source']}",
                    "narration_description": row["full_line_text"],
                    "status": "SYSTEM_NOISE",
                }
            )
        else:
            filtered_rows.append(row)

    for row in filtered_rows:
        page_idx = row["page_source"]
        max_date_x = 95.0 if is_absolute_mode else 24.0

        line_dates = [
            str(t["text"]).strip()
            for t in row["tokens"]
            if DATE_MATCH_REGEX.search(str(t["text"]).strip())
            and float(t["x"]) < max_date_x
        ]

        # ─── CASE A: PARENT ANCHOR DETECTED ───
        if len(line_dates) > 0:
            active_post_date = line_dates[0]
            active_value_date = (
                line_dates[1] if len(line_dates) >= 2 else active_post_date
            )

            sub_words = []
            detected_numbers = []

            # Pre-evaluate row description tokens for structural sign signals
            full_line_upper = str(row["full_line_text"]).upper()
            has_inline_debit_keyword = any(
                kw in full_line_upper
                for kw in ["WDL", "DIRECT", "DR", "CHARGES", "DEBIT", "FEE"]
            )
            has_inline_credit_keyword = any(
                kw in full_line_upper
                for kw in ["DEP", "CR", "CREDIT", "INTEREST", "INT", "RTGS"]
            )

            for token in row["tokens"]:
                t_text = str(token["text"]).strip()
                x0 = float(token["x"])

                if DATE_MATCH_REGEX.search(t_text) and x0 < max_date_x:
                    continue

                if NUMERIC_FINDER_REGEX.search(t_text) or BALANCE_SIGN_REGEX.search(
                    t_text.upper()
                ):
                    clean_num = (
                        t_text.replace("CR", "")
                        .replace("DR", "")
                        .replace("Cr", "")
                        .replace("Dr", "")
                        .strip()
                    )
                    if clean_num:
                        detected_numbers.append({"val": clean_num, "x": x0})
                else:
                    if not any(n in t_text.upper() for n in ("CR", "DR", "₹", "INR")):
                        sub_words.append(t_text)

            # ─── 🎯 RIGHT-TO-LEFT SORTING ROUTER ───
            debit_val = "-"
            credit_val = "-"
            balance_val = "-"

            detected_numbers = sorted(
                detected_numbers, key=lambda n: n["x"], reverse=True
            )

            if len(detected_numbers) >= 1:
                # Far-right token captures the actual running Balance
                balance_val = detected_numbers[0]["val"]
                remaining_tx_amts = detected_numbers[1:]

                if len(remaining_tx_amts) >= 1:
                    target_amt = remaining_tx_amts[0]
                    t_x_val = target_amt["x"]

                    # Compute normalized horizontal percentage bounds if layout is spatial
                    date_cutoff = 24.0 if not is_absolute_mode else (page_width * 0.24)

                    # Contextual Routing pass for items embedded left inside narration
                    if t_x_val <= date_cutoff + 25.0:
                        if has_inline_debit_keyword and not has_inline_credit_keyword:
                            debit_val = target_amt["val"]
                        elif has_inline_credit_keyword and not has_inline_debit_keyword:
                            credit_val = target_amt["val"]
                        else:
                            if t_x_val <= mid_point:
                                debit_val = target_amt["val"]
                            else:
                                credit_val = target_amt["val"]
                    else:
                        if t_x_val <= mid_point:
                            debit_val = target_amt["val"]
                        else:
                            credit_val = target_amt["val"]

            raw_narration = " ".join(sub_words).strip()

            intermediate_txns.append(
                {
                    "id": f"row_{page_idx}_{len(intermediate_txns)}",
                    "internal_sequence_idx": len(intermediate_txns),
                    "post_date": auto_clean_date(active_post_date),
                    "value_date": auto_clean_date(active_value_date),
                    "narration": re.sub(r"\s+", " ", raw_narration).strip(),
                    "debit": debit_val,
                    "credit": credit_val,
                    "balance": balance_val,
                    "page_idx": page_idx,
                }
            )

        # ─── CASE B: CHILD WRAP CONTENT DETECTED ───
        elif intermediate_txns:
            text_upper = str(row["full_line_text"]).upper()

            FOOTER_TERMINATORS = [
                "LAST TRANSACTION DATE",
                "IN CASE YOUR ACCOUNT",
                "*---END OF STATEMENT---*",
                "END OF STATEMENT",
            ]
            if any(term in text_upper for term in FOOTER_TERMINATORS):
                continue

            append_words = []
            for token in row["tokens"]:
                t_text = str(token["text"]).strip()
                if (
                    not any(n in t_text.upper() for n in ("CR", "DR", "₹", "INR"))
                    and "PAGE" not in t_text.upper()
                ):
                    append_words.append(t_text)

            extra_text = " ".join(append_words).strip()
            if extra_text:
                intermediate_txns[-1]["narration"] = re.sub(
                    r"\s+",
                    " ",
                    (intermediate_txns[-1]["narration"] + " " + extra_text).strip(),
                )

    final_clean_txns = [
        tx
        for tx in intermediate_txns
        if not (tx["debit"] == "-" and tx["credit"] == "-" and tx["balance"] == "-")
    ]
    final_clean_txns.sort(key=lambda x: (x["page_idx"], x["internal_sequence_idx"]))

    return final_clean_txns, extracted_opening_balance, system_noise_records
