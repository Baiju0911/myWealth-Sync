import re
from ..utils import normalizer as norm


def execute(pages_raw_data, template_obj, account_id, existing_database_hashes):
    # ─── 🛠️ REGEX CONFIGURATIONS FROM DB ───
    signature = (
        template_obj.signature_json
        if isinstance(template_obj.signature_json, dict)
        else {}
    )
    regex_config = signature.get("regex_patterns", {})

    UNIVERSAL_DATE_PATTERN = (
        r"\b\d{2}-\d{2}-\d{4}\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{2}/\d{2}/\d{4}\b"
    )
    DATE_MATCH_REGEX = re.compile(
        regex_config.get("DATE_MATCH", UNIVERSAL_DATE_PATTERN)
    )
    NUMERIC_FINDER_REGEX = re.compile(
        regex_config.get(
            "NUMERIC_FINDER", r"\b\d{1,3}(?:,\d{2,3})*(?:\.\d{2})(?:CR|DR)?\b"
        )
    )
    BALANCE_SIGN_REGEX = re.compile(
        regex_config.get("BALANCE_SIGN", r"^(CR|DR)$|^(CR|DR)\b|\b(CR|DR)$")
    )

    SYSTEM_NOISE_REGEX = [
        re.compile(p) for p in signature.get("system_noise_patterns", [])
    ]
    opening_balance_markers = signature.get("opening_balance_markers", [])

    is_absolute_mode = signature.get("absolute_pixel_lanes") is not None
    debit_target_x = getattr(template_obj, "debit_x", 375.0)
    credit_target_x = getattr(template_obj, "credit_x", 445.0)
    balance_target_x = getattr(template_obj, "balance_x", 510.0)

    mid_point = (debit_target_x + credit_target_x) / 2 if is_absolute_mode else 45.0
    y_tolerance = (
        8.5 if is_absolute_mode else float(getattr(template_obj, "y_tolerance", 3.0))
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
            h in page_text_dump for h in ["NARRATION", "DEBIT", "CREDIT"]
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
                if NUMERIC_FINDER_REGEX.match(t["text"].strip())
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
        max_date_x = 95.0 if is_absolute_mode else 15.0
        has_date_anchor = any(
            DATE_MATCH_REGEX.match(str(t["text"]).strip())
            and float(t["x"]) < max_date_x
            for t in row["tokens"]
        )

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
        max_date_x = 95.0 if is_absolute_mode else 15.0
        line_dates = [
            str(t["text"]).strip()
            for t in row["tokens"]
            if DATE_MATCH_REGEX.match(str(t["text"]).strip())
            and float(t["x"]) < max_date_x
        ]

        # ─── CASE A: PARENT ANCHOR DETECTED ───
        if len(line_dates) > 0:
            active_post_date = line_dates[0]
            active_value_date = (
                line_dates[1] if len(line_dates) >= 2 else active_post_date
            )

            sub_words, sbi_dr, sbi_cr, sbi_bal = [], [], [], []

            # Detect whether summary digits are present inline in the parent text string
            line_text_upper = str(row["full_line_text"]).upper()
            has_inline_footer_summary = (
                "IN CASE YOUR ACCOUNT" in line_text_upper
                or "*---END OF STATEMENT---*" in line_text_upper
            )

            for token in row["tokens"]:
                t_text = str(token["text"]).strip()
                x0 = float(token["x"])

                if DATE_MATCH_REGEX.match(t_text) and x0 < max_date_x:
                    continue

                if BALANCE_SIGN_REGEX.search(t_text.upper()):
                    if t_text.upper() in ("DR", "CR") and x0 < 500.0:
                        continue
                    sbi_bal.append(t_text)
                elif NUMERIC_FINDER_REGEX.search(t_text):
                    if is_absolute_mode:
                        if 500.0 <= x0 < 650.0:
                            sbi_bal.append(t_text)
                        elif 300.0 <= x0 < 445.0:
                            sbi_dr.append(t_text)
                        elif 445.0 <= x0 < 500.0:
                            sbi_cr.append(t_text)
                    else:
                        if abs(x0 - balance_target_x) <= 9.5:
                            sbi_bal.append(t_text)
                        elif x0 <= mid_point:
                            sbi_dr.append(t_text)
                        else:
                            sbi_cr.append(t_text)
                else:
                    # 🎯 CRITICAL REPAIR: If inline summary tokens bleed into narration tokens, drop them immediately
                    if has_inline_footer_summary and (
                        t_text.isdigit()
                        or "," in t_text
                        or t_text.upper()
                        in ("DR", "CR", "COUNT", "TOTAL", "DEBITS", "CREDITS")
                    ):
                        continue
                    if not any(n in t_text.upper() for n in ("CR", "DR", "₹", "INR")):
                        sub_words.append(t_text)

            raw_narration = " ".join(sub_words).strip()

            # Flush any trailing inline sentences out cleanly
            INLINE_TRUNCATION_PATTERNS = [
                r"\b682\s+387\b.*$",
                r"\bIN\s+CASE\s+YOUR\s+ACCOUNT\b.*$",
                r"\bLAST\s+TRANSACTION\s+DATE\b.*$",
                r"\*---END OF STATEMENT---\*.*$",
            ]
            for pattern in INLINE_TRUNCATION_PATTERNS:
                raw_narration = re.sub(pattern, "", raw_narration, flags=re.IGNORECASE)

            intermediate_txns.append(
                {
                    "id": f"row_{page_idx}_{len(intermediate_txns)}",
                    "internal_sequence_idx": len(intermediate_txns),
                    "post_date": auto_clean_date(active_post_date),
                    "value_date": auto_clean_date(active_value_date),
                    "narration": re.sub(r"\s+", " ", raw_narration).strip(),
                    "debit": " ".join(sbi_dr).strip() if sbi_dr else "-",
                    "credit": " ".join(sbi_cr).strip() if sbi_cr else "-",
                    "balance": " ".join(sbi_bal).strip() if sbi_bal else "-",
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
                "682 387",
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
                INLINE_TRUNCATION_PATTERNS = [
                    r"\bLAST\s+TRANSACTION\s+DATE\b.*$",
                    r"\bIN\s+CASE\s+YOUR\s+ACCOUNT\b.*$",
                    r"\*---END OF STATEMENT---\*",
                ]
                for pattern in INLINE_TRUNCATION_PATTERNS:
                    extra_text = re.sub(pattern, "", extra_text, flags=re.IGNORECASE)

                extra_text = extra_text.strip()
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

    # ─── ⚖️ HIGH-VISIBILITY MISMATCH DETECTOR ───
    running_balance = extracted_opening_balance
    mismatch_counter = 0

    print("\n🚨 DETECTED LEDGER BALANCE SHEET MISMATCHES:")
    print("─" * 110)

    for tx in final_clean_txns:
        dr = norm.parse_float(tx["debit"])
        cr = norm.parse_float(tx["credit"])

        running_balance = running_balance + cr - dr
        parsed_bal = norm.parse_float(tx["balance"])

        if parsed_bal != round(running_balance, 2):
            mismatch_counter += 1
            if mismatch_counter <= 15:
                print(
                    f"❌ Pg: {tx['page_idx']:<4} | Date: {tx['post_date']} | Dr: {tx['debit']:<11} | Cr: {tx['credit']:<11} | StmtBal: {tx['balance']:<13} | Calc: {running_balance:.2f}"
                )
                print(f"     ↳ Narration: \"{tx['narration'][:90]}\"")
                print("─" * 110)

    print(f"\n📊 Extracted Rows Count: {len(final_clean_txns)}")
    print(
        f"📊 Total Row Mismatches Logged: {mismatch_counter} / {len(final_clean_txns)}"
    )
    print("─" * 110 + "\n")

    print("⚠️" * 10)
    print(f"Calculated Final Balance: {running_balance:.2f}")
    print(f"Statement Target Balance: {extracted_opening_balance:.2f}")
    print("⚠️" * 10 + "\n")

    return final_clean_txns, extracted_opening_balance, system_noise_records
