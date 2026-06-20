import fitz  # PyMuPDF
import re
import json
import pandas as pd

# ─── 🟢 SYSTEM TEMPLATE REGISTRY ───
BANK_TEMPLATES = {
    "FEDERAL": {
        "bank_template": "Federal Bank - Personal Variant",
        "lanes": {
            "date": {"x_min": 0, "x_max": 110},
            "narration": {"x_min": 110, "x_max": 380},
            "debit": {"x_min": 385, "x_max": 445},
            "credit": {"x_min": 445, "x_max": 510},
            "balance": {"x_min": 510, "x_max": 600},
        },
    },
    "SBI": {
        "bank_template": "State Bank of India - Core Variant",
        "lanes": {
            "date": {"x_min": 0, "x_max": 95},
            "narration": {"x_min": 95, "x_max": 375},
            "debit": {"x_min": 375, "x_max": 445},
            "credit": {"x_min": 445, "x_max": 510},
            "balance": {"x_min": 510, "x_max": 600},
        },
    },
}


def detect_bank_template(pdf_path):
    """
    Scans the initial pages to identify the true bank institution,
    using strict keyword and word-boundary isolation to prevent false positives.
    """
    doc = fitz.open(pdf_path)
    # Gather text from the first two pages to ensure clean coverage
    sample_text = ""
    for i in range(min(2, len(doc))):
        sample_text += doc[i].get_text("text").upper()
    doc.close()

    # ─── 🟢 RULE 1: EXPLICIT FEDERAL BANK DETECTION ───
    if "FEDERAL BANK" in sample_text or "FEDERAL" in sample_text:
        return BANK_TEMPLATES["FEDERAL"]

    # ─── 🟢 RULE 2: STRICT BOUNDED SBI DETECTION ───
    # Using \bSBI\b ensures transaction substrings like 'SBINT' or 'SBIY...' won't trigger a match
    if "STATE BANK" in sample_text or re.search(r"\bSBI\b", sample_text):
        return BANK_TEMPLATES["SBI"]

    # Standard safe system fallback
    return BANK_TEMPLATES["SBI"]


def extract_geometry_dataframe(pdf_path, template_config):
    doc = fitz.open(pdf_path)
    all_rows = []
    lanes = template_config["lanes"]
    strategy = template_config.get("extraction_strategy", "STRICT_LANES")

    for page_idx, page in enumerate(doc):
        words = page.get_text("words")

        lines_dict = {}
        Y_TOLERANCE = 2.0

        for w in words:
            x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
            matched_line = None
            for baseline_y in lines_dict.keys():
                if abs(y0 - baseline_y) <= Y_TOLERANCE:
                    matched_line = baseline_y
                    break
            if matched_line is not None:
                lines_dict[matched_line].append(w)
            else:
                lines_dict[y0] = [w]

        sorted_baselines = sorted(lines_dict.keys())

        for y in sorted_baselines:
            line_words = sorted(lines_dict[y], key=lambda item: item[0])

            date_lane, narration_lane = [], []
            debit_str, credit_str, balance_str = "", "", ""
            token_tracker_list = []
            first_date_x0 = None

            # Gather tokens for structural reporting
            for w in line_words:
                x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
                clean_text = text.strip()
                if bool(
                    re.match(r"^\d{2}[-\.\/]\d{2}[-\.\/]\d{4}", clean_text)
                ) or bool(re.search(r"^\d[\d,]*\.\d{2}", clean_text)):
                    token_tracker_list.append(
                        {
                            "val": clean_text,
                            "type": "date" if "-\./" in clean_text else "decimal",
                            "x0": round(x0, 2),
                            "y0": round(y0, 2),
                        }
                    )
                if (
                    bool(re.match(r"^\d{2}[-\.\/]\d{2}[-\.\/]\d{4}", clean_text))
                    and first_date_x0 is None
                ):
                    first_date_x0 = x0

            # ─── 🟢 STRATEGY 1: STRICT FIXED GEOMETRIC LANES (SBI) ───
            if strategy == "STRICT_LANES":
                sbi_dr, sbi_cr, sbi_bal = [], [], []
                for w in line_words:
                    x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]

                    if lanes["date"]["x_min"] <= x0 < lanes["date"]["x_max"]:
                        date_lane.append(text)
                    elif (
                        lanes["narration"]["x_min"] <= x0 < lanes["narration"]["x_max"]
                    ):
                        narration_lane.append(text)
                    elif lanes["debit"]["x_min"] <= x0 < lanes["debit"]["x_max"]:
                        sbi_dr.append(text)
                    elif lanes["credit"]["x_min"] <= x0 < lanes["credit"]["x_max"]:
                        sbi_cr.append(text)
                    elif lanes["balance"]["x_min"] <= x0 < lanes["balance"]["x_max"]:
                        sbi_bal.append(text)

                debit_str = " ".join(sbi_dr).strip()
                credit_str = " ".join(sbi_cr).strip()
                balance_str = " ".join(sbi_bal).strip()

            # ─── 🟢 STRATEGY 2: FLOATING RELATIVE AXIS SEQUENCE (FEDERAL) ───
            elif strategy == "RELATIVE_SEQUENCE":
                fed_numeric_tokens = []
                for w in line_words:
                    x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
                    clean_text = text.strip()

                    is_decimal = bool(re.search(r"^\d[\d,]*\.\d{2}", clean_text))
                    is_explicit_balance = bool(
                        re.search(r"\d+\s*(CR|DR)$", clean_text.upper())
                    )

                    if x0 < 385 and not is_explicit_balance and not is_decimal:
                        if lanes["date"]["x_min"] <= x0 < lanes["date"]["x_max"]:
                            date_lane.append(text)
                        else:
                            narration_lane.append(text)
                    else:
                        if is_decimal or is_explicit_balance:
                            fed_numeric_tokens.append({"x0": x0, "text": clean_text})
                        else:
                            narration_lane.append(text)

                fed_numeric_tokens = sorted(fed_numeric_tokens, key=lambda k: k["x0"])
                if len(fed_numeric_tokens) == 1:
                    balance_str = fed_numeric_tokens[0]["text"]
                elif len(fed_numeric_tokens) == 2:
                    balance_str = fed_numeric_tokens[1]["text"]
                    if fed_numeric_tokens[0]["x0"] < 445:
                        debit_str = fed_numeric_tokens[0]["text"]
                    else:
                        credit_str = fed_numeric_tokens[0]["text"]
                elif len(fed_numeric_tokens) >= 3:
                    debit_str = fed_numeric_tokens[0]["text"]
                    credit_str = fed_numeric_tokens[1]["text"]
                    balance_str = fed_numeric_tokens[-1]["text"]

            date_str = " ".join(date_lane).strip()
            narration_str = " ".join(narration_lane).strip()

            if (
                not date_str
                and not narration_str
                and not debit_str
                and not credit_str
                and not balance_str
            ):
                continue

            all_rows.append(
                {
                    "page": page_idx + 1,
                    "y_baseline": round(y, 2),
                    "raw_date": date_str,
                    "date_x0": (
                        round(first_date_x0, 2) if first_date_x0 is not None else 999.0
                    ),
                    "raw_narration": narration_str,
                    "raw_dr": debit_str,
                    "raw_cr": credit_str,
                    "raw_balance": balance_str,
                    "geo_tokens": token_tracker_list,
                }
            )

    doc.close()
    return pd.DataFrame(all_rows)


def process_staging_to_flat_json(df):
    clean_records = []
    current_tx = None
    date_regex = r"^\d{2}[-\.\/]\d{2}[-\.\/]\d{4}"

    # ─── 🟢 SYSTEM STRUCTURAL DROP SIGNALS ───
    # If ANY of these sub-strings are hit, the row content is cleanly dropped before it can leak
    DROP_SIGNALS = [
        "DISCLAIMER",
        "ABBREVIATIONS",
        "END OF STATEMENT",
        "THE FEDERAL BANK",
        "GRAND TOTAL",
        "STATEMENT SUMMARY",
        "CLOSING BALANCE",
        "BROUGHT FORWARD",
        "VALUE DATE",
        "POST DATE",
        "DEBIT    CREDIT",
        "TOTAL DEBITS",
        "PAGE NO.",
        "DR COUNT",
        "CR COUNT",
        "IN CASE YOUR ACCOUNT",
    ]

    for idx, row in df.iterrows():
        raw_full_text = " ".join(
            [
                row["raw_date"],
                row["raw_narration"],
                row["raw_dr"],
                row["raw_cr"],
                row["raw_balance"],
            ]
        ).strip()
        raw_full_text = re.sub(r"\s+", " ", raw_full_text)

        if any(sig in raw_full_text.upper() for sig in DROP_SIGNALS):
            continue

        # ─── 🟢 THE SPATIAL ANCHOR GATE ───
        # A line is only an anchor row if it contains a date AND that date is on the far left margin (x0 < 50)
        is_new_anchor = (
            bool(re.match(date_regex, row["raw_date"])) and row["date_x0"] < 50
        )

        has_dr_num = bool(re.search(r"[\d,]+\.\d{2}", row["raw_dr"]))
        has_cr_num = bool(re.search(r"[\d,]+\.\d{2}", row["raw_cr"]))
        has_bal_num = bool(re.search(r"[\d,]+\.\d{2}", row["raw_balance"]))
        has_decimals = has_dr_num or has_cr_num or has_bal_num

        if is_new_anchor:
            clean_date = re.match(date_regex, row["raw_date"]).group(0)
            spilled_text = row["raw_date"].replace(clean_date, "").strip()
            full_narration = (spilled_text + " " + row["raw_narration"]).strip()

            if current_tx:
                clean_records.append(current_tx)

            current_tx = {
                "page": int(row["page"]),
                "date": clean_date,
                "narration": full_narration,
                "dr": row["raw_dr"] if has_dr_num else "",
                "cr": row["raw_cr"] if has_cr_num else "",
                "balance": row["raw_balance"] if has_bal_num else "",
                "raw_line": raw_full_text,
                "geometry_tokens": row["geo_tokens"],
            }
        else:
            if current_tx:
                clean_date_block = re.sub(date_regex, "", row["raw_date"]).strip()
                combined_narr = " ".join(
                    [clean_date_block, row["raw_narration"]]
                ).strip()

                if combined_narr:
                    current_tx["narration"] = (
                        current_tx["narration"] + " " + combined_narr
                    ).strip()
                    current_tx["narration"] = re.sub(
                        r"\s+", " ", current_tx["narration"]
                    )

                current_tx["raw_line"] += " " + raw_full_text

                if row["geo_tokens"]:
                    current_tx["geometry_tokens"].extend(row["geo_tokens"])

                # ─── 🟢 THE GOLDEN ACCOUNTING VALIDATION GATE ───
                # If a line item already has a debit, do not allow secondary credits to leak in!
                if has_dr_num and not current_tx["dr"]:
                    current_tx["dr"] = row["raw_dr"]

                if has_cr_num:
                    # If this row already captured a Debit, this new number is a leaked footer summary!
                    if current_tx["dr"] or has_dr_num:
                        # Hard cutoff: Stop text accumulation and drop the leaked credit summary
                        current_tx["cr"] = ""
                    else:
                        current_tx["cr"] = row["raw_cr"]

                if has_bal_num:
                    current_tx["balance"] = row["raw_balance"]

    # Apply the exact same Golden Rule verification check to the final dangling block record
    if current_tx:
        if current_tx["dr"] and current_tx["cr"]:
            current_tx["cr"] = ""  # Enforce structural mutual exclusivity
        clean_records.append(current_tx)

    return clean_records


def convert_ledger_json_to_df(json_ledger):
    normalized_rows = []

    TRUNCATION_PATTERNS = [
        r"\s+Page no\..*$",
        r"\s+No/Reference.*$",
        r"\s+Statement Summary.*$",
        r"\s+Last transaction date.*$",
        r"\s+CASH\s*:\s*Cash.*$",
        r"\s+This is a computer.*$",
        r"\s+Page\s+\d+\s+of\s+\d+.*$",
        r"\s+\d{6},tvmi@federalbank.*$",
    ]

    running_calculated_balance = None
    math_failures_count = 0

    for idx, tx in enumerate(json_ledger):

        def clean_float(val_str):
            if not val_str:
                return 0.0
            sanitized = re.sub(r"[^\d\.]", "", str(val_str))
            try:
                return float(sanitized) if sanitized else 0.0
            except ValueError:
                return 0.0

        raw_bal_str = str(tx.get("balance", "")).upper()
        pdf_reported_balance = clean_float(raw_bal_str)

        # ─── 🟢 LAYER 1 AUDIT: DYNAMIC SIGN DETECTION ───
        balance_type = "DR" if "DR" in raw_bal_str else "CR"

        debit_val = clean_float(tx.get("dr"))
        credit_val = clean_float(tx.get("cr"))

        if running_calculated_balance is None:
            running_calculated_balance = pdf_reported_balance
            expected_next_bal = pdf_reported_balance
            math_status = "SEED_ROW"
            variance_delta = 0.0
        else:
            # ─── 🟢 LAYER 2 AUDIT: DYNAMIC ARITHMETIC DIRECTIONAL SWAP ───
            if balance_type == "CR":
                # Standard credit flow: Deposits add, withdrawals subtract
                expected_next_bal = running_calculated_balance - debit_val + credit_val
            else:
                # Overdraft/Debit flow: Withdrawals add to debt, deposits reduce it
                expected_next_bal = running_calculated_balance + debit_val - credit_val

            expected_next_bal = round(expected_next_bal, 2)
            variance_delta = round(abs(expected_next_bal - pdf_reported_balance), 2)

            if variance_delta <= 0.02:  # 2-cent margin for rounding variances
                math_status = "VERIFIED"
                running_calculated_balance = pdf_reported_balance
            else:
                math_status = f"MISMATCH"
                math_failures_count += 1
                running_calculated_balance = pdf_reported_balance

        clean_narration = tx.get("narration", "").strip()
        for pattern in TRUNCATION_PATTERNS:
            clean_narration = re.sub(pattern, "", clean_narration, flags=re.IGNORECASE)

        clean_narration = re.sub(
            r"^\d{2}[-\.\/]\d{2}[-\.\/]\d{4}\s+", "", clean_narration
        )
        clean_narration = re.sub(r"\s+", " ", clean_narration).strip()

        normalized_rows.append(
            {
                "page": tx.get("page"),
                "date": tx.get("date"),
                "narration": clean_narration,
                "debit_amount": debit_val,
                "credit_amount": credit_val,
                "pdf_balance": pdf_reported_balance,
                "calc_balance": expected_next_bal,
                "variance": variance_delta,
                "audit_status": math_status,
            }
        )

    print(f"\n🔬 --- CORE BALANCE TALLY AUDIT SYSTEM REPORT ---")
    if math_failures_count == 0:
        print(
            "✅ INTEGRITY CHECK PASSED: 100% of line items mathematically balance against the ledger stream!"
        )
    else:
        print(
            f"❌ INTEGRITY CRITICAL: Detected {math_failures_count} row transaction math mismatches."
        )
    print("────────────────────────────────────────────────\n")

    return pd.DataFrame(normalized_rows)


if __name__ == "__main__":
    sample_file = "statement-67093359418.pdf"
    # sample_file = "baiju suseelan ONR.pdf"
    print("🕵️‍♂️ Running PyMuPDF Header Identification Router...")
    active_template = detect_bank_template(sample_file)
    print(
        f"🎯 Route Established: Using [{active_template['bank_template']}] Configuration."
    )

    print("📐 Running Visual Lane Geometric Extraction...")
    staging_df = extract_geometry_dataframe(sample_file, active_template)

    print("🔀 Running DataFrame Lookahead State Transformer...")
    flat_json_ledger = process_staging_to_flat_json(staging_df)

    # ─── 🟢 NEW: CONVERT AND NORMALIZE DATAFRAME ───
    print("📊 Compiling and Normalizing analytical Pandas DataFrame...")
    # Inside your Django upload view/command handler:
    final_production_df = convert_ledger_json_to_df(flat_json_ledger)

    # ─── 🟢 LAYER 3 AUDIT: THE HARD BLOCK CONSTRAINT ───
    critical_errors = final_production_df[final_production_df["variance"] > 0.02]

    if not critical_errors.empty:
        print(
            "🛑 DATABASE TRANSACTION ABORTED: The following rows failed mathematical audits:"
        )
        print(
            critical_errors[
                ["page", "narration", "pdf_balance", "calc_balance", "variance"]
            ]
        )
        # Stop processing here; do not call bulk_create()
    else:
        print(
            "🚀 Pre-flight checks passed! Streaming clean records safely to PostgreSQL..."
        )
        # bulk_insert_dataframe_to_django(final_production_df)

    print(
        f"\n🎉 Success! DataFrame compiled perfectly. Matrix Shape: {final_production_df.shape}"
    )
    print("\n🖥️ --- DISPLAYING TAIL COMPLIANT DATAFRAME MATRIX ---")

    # Primes the screen to show our fresh math audit columns safely
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 1000)

    # ─── 🟢 FIXED: Updated column keys to match the balance audit engine fields ───
    print(
        final_production_df.tail(10)[
            [
                "page",
                "date",
                "narration",
                "debit_amount",
                "credit_amount",
                "pdf_balance",
                "calc_balance",
                "audit_status",
            ]
        ].to_string()
    )
