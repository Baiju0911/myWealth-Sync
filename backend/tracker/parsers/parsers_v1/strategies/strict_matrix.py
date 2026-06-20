import re
import json
from ..utils import normalizer as norm


def execute(pages_raw_data, template_obj, account_id, existing_database_hashes):
    """
    Executes 2D structural analysis using database parameters.
    """
    # ─── 📦 DYNAMIC DATABASE OVERRIDES UNPACKING ───
    try:
        # Since your DB uses a real JSONField, it might already arrive as a dict
        config_payload = template_obj.signature_json
        if isinstance(config_payload, str):
            config_payload = json.loads(config_payload)
    except Exception:
        config_payload = {}

    db_regex_patterns = config_payload.get("regex_patterns", {})

    # Compile dynamic regexes from your structural database payload with a safe hardcoded fallback
    DATE_MATCH_RAW = db_regex_patterns.get(
        "DATE_MATCH", r"\b\d{2}-\d{2}-\d{4}\b|\b\d{4}-\d{2}-\d{2}\b"
    )
    NUMERIC_FINDER_RAW = db_regex_patterns.get(
        "NUMERIC_FINDER", r"\b\d{1,3}(?:,\d{2,3})*(?:\.\d{2})(?:CR|DR)?\b"
    )
    ACCOUNT_REF_RAW = db_regex_patterns.get("ACCOUNT_REF", r"\b\d{9,18}\b")
    BALANCE_SIGN_RAW = db_regex_patterns.get("BALANCE_SIGN", r"(CR|DR)$")

    # Compiled Engines
    DATE_MATCH_REGEX = re.compile(DATE_MATCH_RAW)
    NUMERIC_FINDER_REGEX = re.compile(NUMERIC_FINDER_RAW, re.I)
    ACCOUNT_REF_REGEX = re.compile(ACCOUNT_REF_RAW)
    BALANCE_SIGN_REGEX = re.compile(BALANCE_SIGN_RAW, re.I)

    db_summary_markers = config_payload.get("summary_markers") or [
        "STATEMENT SUMMARY",
        "TOTAL DEBITS",
        "TOTAL CREDITS",
        "CLOSING BALANCE",
        "GRAND TOTAL",
    ]
    db_opening = config_payload.get("opening_balance_markers") or [
        r"\bOPENING\s+BALANCE\b"
    ]
    db_noise = config_payload.get("system_noise_patterns") or []

    OPENING_BALANCE_REGEX = [re.compile(p, re.I) for p in db_opening]
    SYSTEM_NOISE_REGEX = [re.compile(p, re.I) for p in db_noise]

    # Extract line processing attributes directly from the database template columns
    base_y_tolerance = float(getattr(template_obj, "y_tolerance", 3.0))
    is_fed = getattr(template_obj, "template_name", "SBI") == "FED"
    active_delta = 4.2 if is_fed else base_y_tolerance

    raw_rows = []

    # ─── 🔍 STEP 1: SPATIAL AGGREGATION LOOP ───
    for page_data in pages_raw_data:
        page_idx = page_data["page_idx"]
        page_width = page_data["page_width"]
        words = page_data["words"]

        date_baselines = []
        for w in words:
            x0, y0, text = w[0], w[1], w[4].strip()
            x_pct = (x0 / page_width) * 100
            if DATE_MATCH_REGEX.match(text) and x_pct <= 10.0:
                date_baselines.append(y0)

        lines_pool = []
        for w in words:
            x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4].strip()
            if not text:
                continue
            x_pct = round((x0 / page_width) * 100, 2)
            belongs_to_date_row = any(
                abs(y0 - d_y) <= active_delta for d_y in date_baselines
            )

            matched = False
            for line in lines_pool:
                if belongs_to_date_row != line["belongs_to_date_row"]:
                    continue
                if abs(y0 - line["base_y"]) <= active_delta:
                    line["tokens"].append({"text": text, "x": x_pct, "y": y0})
                    matched = True
                    break

            if not matched:
                lines_pool.append(
                    {
                        "base_y": y0,
                        "belongs_to_date_row": belongs_to_date_row,
                        "tokens": [{"text": text, "x": x_pct, "y": y0}],
                    }
                )

        for line in sorted(lines_pool, key=lambda l: l["base_y"]):
            sorted_tokens = sorted(
                line["tokens"], key=lambda t: (t.get("y", 0), t.get("x", 0))
            )
            raw_rows.append(
                {
                    "tokens": sorted_tokens,
                    "full_line_text": " ".join(t["text"] for t in sorted_tokens),
                    "page_source": page_idx,
                }
            )

    # ─── 📊 STEP 2: FIELD BOUNDS ANCHOR MAPPING ───
    detected_header_indices = {
        "date": float(getattr(template_obj, "date_x", 4.5)),
        "narration": float(getattr(template_obj, "narration_x", 23.0)),
        "debit": float(getattr(template_obj, "debit_x", 66.0)),
        "credit": float(getattr(template_obj, "credit_x", 78.5)),
        "balance": float(getattr(template_obj, "balance_x", 87.5)),
    }

    # ─── 🟢 STEP 3: INITIAL OPENING BALANCE SCANNER ───
    extracted_opening_balance = 0.0
    for row in raw_rows[:15]:
        text_upper = row["full_line_text"].upper()
        if any(regex.search(text_upper) for regex in OPENING_BALANCE_REGEX):
            decimal_candidates = NUMERIC_FINDER_REGEX.findall(row["full_line_text"])
            if decimal_candidates:
                extracted_opening_balance = norm.parse_float(decimal_candidates[-1])
                break

    # ─── 🟢 STEP 4: PROCESSING STREAM BUFFER ───
    intermediate_txns = []
    system_noise_records = []

    debit_target_x = detected_header_indices["debit"]
    credit_target_x = detected_header_indices["credit"]
    balance_target_x = detected_header_indices["balance"]
    date_bound_x = detected_header_indices["date"]

    mid_point = (debit_target_x + credit_target_x) / 2

    idx = 0
    while idx < len(raw_rows):
        row = raw_rows[idx]
        text = row["full_line_text"].strip()
        text_upper = text.upper()
        page_idx = row.get("page_source", 1)

        if any(m in text_upper for m in db_summary_markers) or any(
            regex.search(text_upper) for regex in SYSTEM_NOISE_REGEX
        ):
            system_noise_records.append(
                {
                    "id": f"noise_{page_idx}_{idx}",
                    "narration_description": text,
                    "status": "SYSTEM_NOISE",
                }
            )
            idx += 1
            continue

        line_dates = [
            {"text": t["text"], "x": t["x"]}
            for t in row["tokens"]
            if DATE_MATCH_REGEX.match(t["text"].strip())
        ]
        primary_anchor_found = any(dt["x"] <= (date_bound_x + 8.0) for dt in line_dates)

        if not primary_anchor_found:
            idx += 1
            continue

        active_post_date = None
        active_value_date = None
        found_dts = [dt["text"] for dt in line_dates if dt["x"] <= 24.0]
        if len(found_dts) >= 2:
            active_post_date, active_value_date = found_dts[0], found_dts[1]
        elif len(found_dts) == 1:
            active_post_date = active_value_date = found_dts[0]

        row_tokens_pool = list(row["tokens"])
        k = idx + 1
        while k < len(raw_rows):
            next_row = raw_rows[k]
            has_true_date_anchor = any(
                DATE_MATCH_REGEX.match(t["text"].strip()) and float(t["x"]) <= 24.0
                for t in next_row["tokens"]
            )
            if has_true_date_anchor or any(
                m in next_row["full_line_text"].upper() for m in db_summary_markers
            ):
                break
            row_tokens_pool.extend(next_row["tokens"])
            k += 1
        idx = k

        row_numbers = []
        active_refs = []
        for token in row_tokens_pool:
            t_text = token["text"].strip()
            if ACCOUNT_REF_REGEX.match(t_text):
                if t_text not in active_refs:
                    active_refs.append(t_text)
                continue
            if NUMERIC_FINDER_REGEX.match(t_text) and not DATE_MATCH_REGEX.match(
                t_text
            ):
                row_numbers.append(
                    {"val": t_text, "x": float(token["x"]), "y": float(token["y"])}
                )
        print(f"🔍 DEBUG ROW tokens: {[t['text'] for t in row_tokens_pool]}")
        row_numbers = sorted(row_numbers, key=lambda n: n["x"])

        balances = [
            n
            for n in row_numbers
            if abs(n["x"] - balance_target_x) <= 5.0
            or BALANCE_SIGN_REGEX.search(n["val"])
        ]
        tx_amounts = [n for n in row_numbers if n not in balances]

        sub_words = []
        for t in row_tokens_pool:
            t_text = t["text"].strip()
            if (
                not DATE_MATCH_REGEX.match(t_text)
                and not NUMERIC_FINDER_REGEX.match(t_text)
                and not ACCOUNT_REF_REGEX.match(t_text)
            ):
                if not any(
                    noise in t_text.upper() for noise in ("CR", "DR", "₹", "INR")
                ):
                    sub_words.append(t_text)

        active_debit = None
        active_credit = None
        active_balance = None

        if len(tx_amounts) >= 1 and balances:
            active_balance = balances[0]["val"]
            target_amt = tx_amounts[0]

            if target_amt["x"] <= mid_point:
                active_debit = target_amt["val"]
            elif abs(target_amt["x"] - debit_target_x) < abs(
                target_amt["x"] - credit_target_x
            ):
                active_debit = target_amt["val"]
            else:
                active_credit = target_amt["val"]

        raw_narration = " ".join(sub_words).strip()

        # ─── 🎯 SURGICAL FOOTER & NOISE STRIPPER FOR INLINE BLEED ───
        INLINE_TRUNCATION_PATTERNS = [
            r"\bPage\s+\d+\s+of\s+\d+\b.*$",
            r"\bTHE\s+FEDERAL\s+BANK\s+LTD\b.*$",
            r"\bBRANCH\s*:\s*THIRUVANANTHAPURAM\b.*$",
            r"\bTran\s+Cheque\s+Balance\b.*$",
            r"\bWebsite\s*:\s*www\b.*$",
            r"\bCIN\s*:\s*[A-Z0-9]+\b.*$",
        ]
        for pattern in INLINE_TRUNCATION_PATTERNS:
            raw_narration = re.sub(pattern, "", raw_narration, flags=re.IGNORECASE)

        final_narration = re.sub(r"\s+", " ", raw_narration).strip()

        intermediate_txns.append(
            {
                "id": f"row_{page_idx}_{len(intermediate_txns)}",
                "post_date": norm.normalize_date(
                    active_post_date, template_obj.date_format
                ),
                "value_date": norm.normalize_date(
                    active_value_date or active_post_date, template_obj.date_format
                ),
                "narration": final_narration,
                "debit": active_debit if active_debit else "-",
                "credit": active_credit if active_credit else "-",
                "balance": active_balance if active_balance else "-",
                "page_idx": page_idx,
            }
        )

    return intermediate_txns, extracted_opening_balance, system_noise_records
