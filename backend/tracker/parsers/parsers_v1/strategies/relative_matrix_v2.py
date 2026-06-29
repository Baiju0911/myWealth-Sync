import re
import json
from ..utils import normalizer as norm


def execute_v2(pages_raw_data, template_obj, account_id, existing_database_hashes):
    """
    UNIVERSAL DYNAMIC RELATIVE MATRIX ENGINE (V2 - STREAM INTERCEPTOR)
    Designed to extract data while executing a full data-dump of Row 1 tracking metrics.
    """
    print(
        "\n🚀 [V2 ENGINE INIT] Spinning up Stream Interceptor Bounding Box Debugger..."
    )
    try:
        signature = template_obj.signature_json
        if isinstance(signature, str):
            signature = json.loads(signature)
    except Exception:
        signature = {}

    regex_config = signature.get("regex_patterns", {})

    DATE_MATCH_RAW = regex_config.get("DATE_MATCH", r"\d{2}[-/\.]\d{2}[-/\.]\d{2,4}")
    NUMERIC_FINDER_RAW = regex_config.get("NUMERIC_FINDER", r"\d+(?:\.\d{2})")
    BALANCE_SIGN_RAW = regex_config.get("BALANCE_SIGN", r"(CR|DR)$")

    DATE_MATCH_REGEX = re.compile(DATE_MATCH_RAW.replace(r"\b", ""))
    NUMERIC_FINDER_REGEX = re.compile(NUMERIC_FINDER_RAW.replace(r"\b", ""), re.I)
    BALANCE_SIGN_REGEX = re.compile(BALANCE_SIGN_RAW, re.I)
    LEGACY_SHORT_DATE_REGEX = re.compile(r"\b\d{2}/\d{2}/\d{2}\b|\d{2}/\d{2}/\d{2}")

    db_table_headers_noise = signature.get("table_headers_noise") or []
    is_absolute_mode = signature.get("absolute_pixel_lanes") is not None
    debit_target_x = float(getattr(template_obj, "debit_x", 375.0))
    credit_target_x = float(getattr(template_obj, "credit_x", 445.0))
    mid_point = (debit_target_x + credit_target_x) / 2

    LINE_BINDING_THRESHOLD_Y = 3.5
    header_skip_target = int(getattr(template_obj, "header_lines_to_skip", 0))

    raw_rows = []
    extracted_opening_balance = 0.0

    def auto_clean_date(date_str):
        try:
            date_clean = str(date_str).strip()
            if "-" in date_clean and len(date_clean.split("-")[0]) == 4:
                return date_clean
            if "/" in date_clean:
                parts = date_clean.split("/")
                if len(parts) == 3:
                    day = parts[0].zfill(2)
                    month = parts[1].zfill(2)
                    year = f"20{parts[2]}" if len(parts[2]) == 2 else parts[2]
                    return f"{day}-{month}-{year}"
            return norm.normalize_date(date_clean, template_obj.date_format)
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
            page_data["words"], key=lambda w: (round(float(w[1]), 1), float(w[0]))
        )
        if not sorted_tokens:
            continue

        page_lines = []
        current_row_tokens = []
        current_y_anchor = float(sorted_tokens[0][1])

        for tok in sorted_tokens:
            x0, y0 = float(tok[0]), float(tok[1])
            text_val = str(tok[4]).strip() if len(tok) > 4 else str(tok[2])
            x_val = x0 if is_absolute_mode else round((x0 / page_width) * 100, 2)

            if ("---" in text_val or "___" in text_val) and any(
                c.isdigit() for c in text_val
            ):
                cleaned_nums = re.findall(r"\d+(?:,\d+)*(?:\.\d+)?", text_val)
                for parsed_num in cleaned_nums:
                    current_row_tokens.append({"text": parsed_num, "x": x_val, "y": y0})
                continue

            if abs(y0 - current_y_anchor) <= LINE_BINDING_THRESHOLD_Y:
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
        raw_rows.extend(
            page_lines[start_idx:] if start_idx < len(page_lines) else page_lines
        )

    # ─── 🔍 STEP 2: MULTI-PAGE OPENING BALANCE REGISTER MAP ───
    for r in raw_rows:
        p_source = r["page_source"]
        if any(
            re.search(marker, r["full_line_text"].upper())
            for marker in signature.get("opening_balance_markers", [])
        ):
            nums = [
                t["text"]
                for t in r["tokens"]
                if NUMERIC_FINDER_REGEX.search(t["text"].strip())
            ]
            if nums and p_source == 1 and extracted_opening_balance == 0.0:
                extracted_opening_balance = norm.parse_float(nums[-1])

    # ─── 🟢 STEP 3: TRANSACTION PARSER ───
    intermediate_txns = []
    inside_summary_zone = False
    current_page_tracking = None
    document_flow_sequence = 0

    ledger_state = {"last_balance": None, "resynced_pages_pool": set()}

    SUMMARY_TERMINATORS = [
        "STATEMENT SUMMARY",
        "DR COUNT",
        "CR COUNT",
        "TOTAL DEBITS",
        "TOTAL CREDITS",
        "CLOSING BALANCE",
    ]
    STRICT_PAGE_NO_REGEX = re.compile(r"\bPAGE\s*N[O0]\s*[:\.]*\s*\d+\b", re.I)
    LEAK_FILTER_REGEX = re.compile(r"^3\.50*$")

    for row_idx, row in enumerate(raw_rows):
        page_idx = row["page_source"]
        text_upper = str(row["full_line_text"]).upper()

        if current_page_tracking != page_idx:
            current_page_tracking = page_idx
            inside_summary_zone = False

        if any(
            term in text_upper for term in SUMMARY_TERMINATORS
        ) or STRICT_PAGE_NO_REGEX.search(text_upper):
            if len(intermediate_txns) > 0:
                inside_summary_zone = True
            continue

        if inside_summary_zone or any(
            thn.upper() in text_upper for thn in db_table_headers_noise
        ):
            continue

        if any(
            token in text_upper
            for token in [
                "TIME :",
                "E-MAIL :",
                "CLEARED BALANCE :",
                "STATEMENT FROM :",
                "POST DATE",
                "VALUE DATE",
            ]
        ):
            continue

        if any(
            kw in text_upper
            for kw in [
                "CARRIED FORWARD",
                "BROUGHT FORWARD",
                "C/F",
                "B/F",
                "__________",
                "----------",
            ]
        ):
            continue

        line_dates = []
        for t in row["tokens"]:
            t_clean = str(t["text"]).strip()
            if (
                DATE_MATCH_REGEX.search(t_clean)
                or LEGACY_SHORT_DATE_REGEX.search(t_clean)
            ) and float(t["x"]) < (95.0 if is_absolute_mode else 24.0):
                line_dates.append(t)

        is_protected_txn = len(line_dates) >= 1

        if not is_protected_txn:
            if intermediate_txns and not inside_summary_zone:
                if intermediate_txns[-1]["page_idx"] == page_idx:
                    append_words = [
                        t["text"]
                        for t in row["tokens"]
                        if not any(
                            n in t["text"].upper()
                            for n in ("CR", "DR", "₹", "INR", "--")
                        )
                        and "PAGE" not in t["text"].upper()
                    ]
                    extra_text = " ".join(append_words).strip()
                    if extra_text:
                        intermediate_txns[-1]["narration"] = re.sub(
                            r"\s+",
                            " ",
                            (
                                intermediate_txns[-1]["narration"] + " " + extra_text
                            ).strip(),
                        )
            continue

        document_flow_sequence += 1
        active_post_date = line_dates[0]["text"]
        clean_date_payload = auto_clean_date(active_post_date)

        sub_words = []
        detected_numbers = []

        for token in row["tokens"]:
            t_text = str(token["text"]).strip().replace("%", "")
            if (
                DATE_MATCH_REGEX.search(t_text)
                or LEGACY_SHORT_DATE_REGEX.search(t_text)
            ) and float(token["x"]) < (95.0 if is_absolute_mode else 24.0):
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
                if clean_num and not LEAK_FILTER_REGEX.match(clean_num):
                    detected_numbers.append({"val": clean_num, "x": float(token["x"])})
            else:
                if t_text.upper() not in ("CR", "DR", "₹", "INR", "--"):
                    sub_words.append(t_text)

        debit_val, credit_val, balance_val = "-", "-", "-"
        detected_numbers = sorted(detected_numbers, key=lambda n: n["x"], reverse=True)

        if len(detected_numbers) >= 1:
            balance_val = detected_numbers[0]["val"]
            balance_val_float = norm.parse_float(balance_val)
        else:
            balance_val_float = (
                ledger_state["last_balance"]
                if ledger_state["last_balance"] is not None
                else 0.0
            )
            balance_val = f"{balance_val_float:.2f}"

        if ledger_state["last_balance"] is None:
            prev_anchor_val = (
                extracted_opening_balance
                if extracted_opening_balance != 0.0
                else balance_val_float
            )
            extracted_opening_balance = prev_anchor_val
        else:
            prev_anchor_val = ledger_state["last_balance"]

        computed_delta = balance_val_float - prev_anchor_val
        absolute_delta_str = f"{abs(computed_delta):.2f}"

        if abs(computed_delta) > 0.005:
            if computed_delta > 0:
                credit_val = absolute_delta_str
            else:
                debit_val = absolute_delta_str
        else:
            if len(detected_numbers) >= 2:
                target_amt = detected_numbers[1]
                if target_amt["x"] <= mid_point:
                    debit_val = target_amt["val"]
                else:
                    credit_val = target_amt["val"]

        payload = {
            "id": f"row_{page_idx}_{len(intermediate_txns)}",
            "internal_sequence_idx": len(intermediate_txns),
            "post_date": clean_date_payload,
            "value_date": clean_date_payload,
            "narration": re.sub(r"\s+", " ", " ".join(sub_words)).strip(),
            "debit": debit_val,
            "credit": credit_val,
            "balance": balance_val,
            "page_idx": page_idx,
            "debug_raw_text": row["full_line_text"],
        }

        ledger_state["last_balance"] = balance_val_float
        intermediate_txns.append(payload)

    final_clean_txns = [
        tx
        for tx in intermediate_txns
        if not (tx["debit"] == "-" and tx["credit"] == "-" and tx["balance"] == "-")
    ]
    final_clean_txns.sort(key=lambda x: (x["page_idx"], x["internal_sequence_idx"]))

    # ─── 🕵️‍♂️ CRITICAL TERMINAL STREAM DATA DEPLOYMENT ───
    print(
        "\n🖥️ [STREAM DECONSTRUCTION DUMP] Displaying exactly what fields are inside the output list array:"
    )
    for i in range(min(5, len(final_clean_txns))):
        tx = final_clean_txns[i]
        print(
            f"  👉 Array Position [{i}] -> Date='{tx['post_date']}' | Narr='{tx['narration'][:30]}' | Dr='{tx['debit']}' | Cr='{tx['credit']}' | Bal='{tx['balance']}' | RawLine='{tx.get('debug_raw_text')}'"
        )
    print("=" * 95)

    return final_clean_txns, extracted_opening_balance, []
