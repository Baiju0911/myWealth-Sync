import re
import json
from ..utils import normalizer as norm


def execute(pages_raw_data, template_obj, account_id, existing_database_hashes):
    """
    UNIVERSAL DYNAMIC MATRIX ENGINE: Loads tracking metrics, boundary coordinates,
    and extraction filters directly from database template schema objects.
    """
    # ─── 📦 DYNAMIC DATABASE OVERRIDES UNPACKING ───
    try:
        config_payload = template_obj.signature_json
        if isinstance(config_payload, str):
            config_payload = json.loads(config_payload)
    except Exception:
        config_payload = {}

    db_regex_patterns = config_payload.get("regex_patterns", {})

    # 🎯 DYNAMIC DATABASE REGEX FETCHING
    DATE_MATCH_RAW = db_regex_patterns.get(
        "DATE_MATCH", r"\d{2}-\d{2}-\d{4}|\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}"
    )
    NUMERIC_FINDER_RAW = db_regex_patterns.get("NUMERIC_FINDER", r"\d+(?:\.\d{2})")

    # Clean off strict word boundary tokens (\b) to avoid truncation inside lookaheads
    DATE_MATCH_RAW = DATE_MATCH_RAW.replace(r"\b", "")
    NUMERIC_FINDER_RAW = NUMERIC_FINDER_RAW.replace(r"\b", "")

    DATE_RE = re.compile(DATE_MATCH_RAW)
    NUMERIC_RE = re.compile(NUMERIC_FINDER_RAW, re.I)

    db_summary_markers = config_payload.get("summary_markers") or []
    db_noise = config_payload.get("system_noise_patterns") or []
    db_table_headers_noise = config_payload.get("table_headers_noise") or []

    SYSTEM_NOISE_REGEX = [re.compile(p, re.I) for p in db_noise]

    base_y_tolerance = float(getattr(template_obj, "y_tolerance", 3.0))
    is_fed = getattr(template_obj, "template_name", "SBI") == "FED"
    active_delta = 7.5 if is_fed else base_y_tolerance

    # Dynamic column parameters mapped directly from database table properties
    date_bound_x = float(getattr(template_obj, "date_x", 12.0))
    debit_bound_x = float(getattr(template_obj, "debit_x", 65.0))
    credit_bound_x = float(getattr(template_obj, "credit_x", 76.0))
    balance_bound_x = float(getattr(template_obj, "balance_x", 86.0))
    mid_point = (debit_bound_x + credit_bound_x) / 2

    raw_rows = []

    # ─── 🔍 STEP 1: SPATIAL AGGREGATION LOOP ───
    for page_data in pages_raw_data:
        page_idx = page_data["page_idx"]
        page_width = page_data["page_width"]
        words = page_data["words"]

        filtered_words = []
        for w in words:
            w_text_upper = w[4].strip().upper()
            HEADER_NOISE_WORDS = (
                "ACCOUNT OPEN DATE",
                "REGD. MOBILE",
                "MODE OF OPERATION",
                "SCHEME :",
                "SWIFT CODE",
                "EFFECTIVE AVAILABLE",
                "STATEMENT OF ACCOUNT",
                "LAST UPDATED ON",
                "SINGLE EMAIL ID",
                "JOINT HOLDERS",
            )
            if any(hnw in w_text_upper for hnw in HEADER_NOISE_WORDS):
                continue
            filtered_words.append(w)

        date_baselines = []
        for w in filtered_words:
            x0, y0, text = w[0], w[1], w[4].strip()
            x_pct = (x0 / page_width) * 100

            if (DATE_RE.search(text) and x_pct <= 24.0) or (
                text.upper() in ("CR", "DR") and x_pct >= 85.0
            ):
                if not any(abs(y0 - d_y) <= active_delta for d_y in date_baselines):
                    date_baselines.append(y0)

        lines_pool = []
        for w in filtered_words:
            x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4].strip()
            if not text:
                continue
            x_pct = round((x0 / page_width) * 100, 2)

            matched = False
            for line in lines_pool:
                if abs(y0 - line["base_y"]) <= active_delta:
                    line["tokens"].append({"text": text, "x": x_pct, "y": y0})
                    matched = True
                    break

            if not matched:
                lines_pool.append(
                    {
                        "base_y": y0,
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

    # ─── 📊 STEP 2: FIXED POSITION FIELD LANES ───
    intermediate_txns = []
    system_noise_records = []

    idx = 0
    while idx < len(raw_rows):
        row = raw_rows[idx]
        text = row["full_line_text"].strip()
        text_upper = text.upper()
        page_idx = row.get("page_source", 1)

        if any(thn.upper() in text_upper for thn in db_table_headers_noise):
            idx += 1
            continue

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
            if DATE_RE.search(t["text"].strip())
        ]

        primary_anchor_found = False
        for dt in line_dates:
            dt_x = float(dt["x"])
            if dt_x > 100.0:
                dt_x = (dt_x / page_width) * 100
            if dt_x <= (date_bound_x + 20.0):
                primary_anchor_found = True
                break

        if not primary_anchor_found:
            idx += 1
            continue

        active_post_date = None
        found_dts = []
        for dt in line_dates:
            dt_x = float(dt["x"])
            if dt_x > 100.0:
                dt_x = (dt_x / page_width) * 100
            if dt_x <= 24.0:
                found_dts.append(dt["text"])

        if found_dts:
            active_post_date = found_dts[0]

        row_tokens_pool = list(row["tokens"])
        k = idx + 1
        while k < len(raw_rows):
            next_row = raw_rows[k]
            next_text_upper = next_row["full_line_text"].upper()

            has_true_date_anchor = False
            for t in next_row["tokens"]:
                if DATE_RE.search(t["text"].strip()):
                    t_x = float(t["x"])
                    if t_x > 100.0:
                        t_x = (t_x / page_width) * 100
                    if t_x <= 24.0:
                        has_true_date_anchor = True
                        break

            # Added newly uncovered SIB/FED block boundaries
            STRICT_BLOCK_TERMINATORS = [
                "PAGE",
                "THE FEDERAL BANK",
                "BRANCH:",
                "ABBREVIATIONS",
                "DISCLAIMER",
                "COMPUTER GENERATED",
                "TRAN CHEQUE BALANCE",
                "STATEMENT PERIOD",
                "SBINT:",
            ]
            if (
                has_true_date_anchor
                or any(m in next_text_upper for m in db_summary_markers)
                or any(term in next_text_upper for term in STRICT_BLOCK_TERMINATORS)
            ):
                break
            row_tokens_pool.extend(next_row["tokens"])
            k += 1
        idx = k

        all_balances = []
        for t in row_tokens_pool:
            if NUMERIC_RE.search(t["text"].strip()):
                t_x = float(t["x"])
                if t_x > 100.0:
                    t_x = (t_x / page_width) * 100
                if t_x >= balance_bound_x:
                    all_balances.append(t)

        if len(all_balances) >= 2:
            split_y = (all_balances[0]["y"] + all_balances[1]["y"]) / 2
            sub_pools = [
                [t for t in row_tokens_pool if t["y"] < split_y],
                [t for t in row_tokens_pool if t["y"] >= split_y],
            ]
        else:
            sub_pools = [row_tokens_pool]

        for active_pool in sub_pools:
            dates_found = []
            narration_pieces = []
            detected_numbers = []

            for token in active_pool:
                t_text = token["text"].strip()
                x_loc = float(token["x"])

                if x_loc > 100.0:
                    x_loc = (x_loc / page_width) * 100

                # 🎯 REFINE ACCURACY FILTER PASS
                is_date_string = bool(DATE_RE.match(t_text))

                if is_date_string:
                    # Captures chronological structural coordinates
                    if x_loc <= date_bound_x + 20.0:
                        dates_found.append(t_text)
                    # Dropping internal duplicate layout track columns, ignoring random injection strings
                    continue

                if date_bound_x < x_loc < debit_bound_x:
                    narration_pieces.append(t_text)
                elif x_loc >= debit_bound_x and NUMERIC_RE.search(t_text):
                    clean_val = (
                        t_text.replace("CR", "")
                        .replace("DR", "")
                        .replace("Cr", "")
                        .replace("Dr", "")
                        .strip()
                    )
                    detected_numbers.append({"val": clean_val, "x": x_loc})

            debit_val = "-"
            credit_val = "-"
            balance_val = "-"

            detected_numbers = sorted(
                detected_numbers, key=lambda n: n["x"], reverse=True
            )

            if len(detected_numbers) >= 1:
                balance_val = detected_numbers[0]["val"]
                remaining_tx_amts = detected_numbers[1:]
                if len(remaining_tx_amts) >= 1:
                    target_amt = remaining_tx_amts[0]
                    if target_amt["x"] <= mid_point:
                        debit_val = target_amt["val"]
                    else:
                        credit_val = target_amt["val"]

            if debit_val == "-" and credit_val == "-" and balance_val == "-":
                continue

            raw_narration = " ".join(narration_pieces).strip()
            raw_narration = raw_narration.replace("/", " ").replace("\\", " ")
            final_narration = re.sub(r"\s+", " ", raw_narration).strip()

            post_date = dates_found[0] if dates_found else None
            if not post_date:
                # Safe execution pass for embedded narrative transaction records
                inline_dates = DATE_RE.findall(final_narration)
                if inline_dates:
                    post_date = inline_dates[0]

            if not post_date and len(intermediate_txns) > 0:
                post_date = intermediate_txns[-1]["post_date"]
            else:
                post_date = (
                    norm.normalize_date(str(post_date), template_obj.date_format)
                    if post_date
                    else "-"
                )

            intermediate_txns.append(
                {
                    "id": f"row_{page_idx}_{len(intermediate_txns)}",
                    "post_date": post_date,
                    "value_date": post_date,
                    "narration": final_narration,
                    "debit": debit_val,
                    "credit": credit_val,
                    "balance": balance_val,
                    "page_idx": page_idx,
                }
            )

    # ─── ⚖️ PRINT BALANCES MAP ───
    print("\n🚨 UNFILTERED VALUE STREAM SHEET:")
    print("─" * 120)
    for tx in intermediate_txns:
        print(
            f"Pg {tx['page_idx']} | Date: {tx['post_date']:<10} | Dr: {tx['debit']:<10} | Cr: {tx['credit']:<10} | Bal: {tx['balance']:<12}"
        )
        print(f"   ↳ Narration: \"{tx['narration']}\"")
        print("─" * 120)

    return intermediate_txns, 0.0, system_noise_records
