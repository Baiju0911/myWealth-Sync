# backend/tracker/parsers/parsers_v1/utils/validator.py
import decimal
import re
import json
from datetime import datetime
from . import normalizer as norm
from ...utils import generate_row_fingerprint

FINAL_SAFE_DATE_REGEX = re.compile(
    r"\b\d{2}-\d{2}-\d{4}\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{4}/\d{2}/\d{2}\b|\b\d{2}/\d{2}/\d{4}\b"
)


def force_clean_float(value):
    """🔒 CENTRALIZED MONETARY CLEANER: Coerces variant data types into a clean float."""
    if value in [None, "", "-", "NULL", "None"]:
        return 0.0
    try:
        if isinstance(value, decimal.Decimal):
            return float(value)
        cleaned_str = str(value).replace(",", "").replace("₹", "").strip()
        if cleaned_str.lower().endswith("cr") or cleaned_str.lower().endswith("dr"):
            cleaned_str = cleaned_str[:-2].strip()
        return float(cleaned_str)
    except (ValueError, TypeError):
        return 0.0


def normalize_narration_text(raw_text):
    """🧠 AI-FORWARD TEXT SANITIZER: Collapses whitespace, preserves all words."""
    if not raw_text:
        return ""
    clean = str(raw_text).replace("\n", " ").replace("\t", " ").replace("\xa0", " ")
    clean = clean.replace("-", " ")
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip().upper()


def calculate_narration_merge(old_str, incoming_str, old_chq=None, new_chq=None):
    """
    🔒 DUAL-ENRICHMENT AGGREGATOR ENGINE:
    Ensures zero text data loss from PDF or Excel statement sources.
    Combines distinct text layers and prevents cross-column data duplication.
    Returns: (final_merged_narration, final_merged_cheque, was_changed_flag)
    """
    old_clean = str(old_str or "").strip()
    incoming_clean = str(incoming_str or "").strip()

    # ─── 🏛️ STEP 1: RESOLVE THE CHEQUE REFERENCE NUMBER ───
    final_chq = old_chq
    has_new_cheque = False

    # Normalize cheque tokens to identify if a real value was gained
    clean_old_chq = str(old_chq or "").strip()
    clean_new_chq = str(new_chq or "").strip()

    if clean_old_chq in ["", "-", "None", "NULL"]:
        clean_old_chq = None
    if clean_new_chq in ["", "-", "None", "NULL"]:
        clean_new_chq = None

    if clean_new_chq and not clean_old_chq:
        final_chq = clean_new_chq
        has_new_cheque = True
    elif clean_old_chq:
        final_chq = clean_old_chq

    # ─── 🏛️ STEP 2: NARRATION TOKENS ALIGNMENT ───
    def tokenize(text):
        return [w for w in re.findall(r"[A-Z0-9]+", text.upper()) if w]

    tokens_old = tokenize(old_clean)
    tokens_inc = tokenize(incoming_clean)

    # Gather any active cheque references to prevent repeating them in the text field
    chq_tokens = set()
    if final_chq:
        chq_tokens.update(tokenize(str(final_chq)))

    # Filter out common punctuation noise indicators or pure tracking headers
    set_old = {w for w in tokens_old if w not in chq_tokens}

    # Isolate tokens that are completely unique to the incoming sheet narration
    # 1. It calculates if the incoming file brings new unique words:
    delta_words = [
        word for word in tokens_inc if word not in set_old and word not in chq_tokens
    ]

    # 2. If delta_words is empty, it means the incoming file has no new descriptive information:
    if not delta_words:
        if set(tokens_inc).issubset(set(tokens_old)):
            return old_clean, final_chq, has_new_cheque  # 💤 Stale Duplicate

    # If the strings are word-for-word twins or structural subsets, no text merge is required
    if old_clean == incoming_clean or set(tokens_inc).issubset(set(tokens_old)):
        return old_clean, final_chq, has_new_cheque

    # ─── 🏛️ STEP 3: CONSOLIDATE BOTH STRINGS SAFELY ───
    # We strip out messy trailing hyphens or pipes before joining them
    base_old = old_clean.rstrip("|- ").strip()
    extension_new = incoming_clean.lstrip("|- ").strip()

    # Stitches both narratives together completely so future AI models get all words!
    final_merged_narration = f"{base_old} | {extension_new}"

    return final_merged_narration, final_chq, True


def process_and_filter_rows(
    preview_dataset, account, bank, existing_hashes, database_lookup_dict=None
):
    """
    🔒 UNIVERSAL SYNCHRONIZER ENGINE:
    Tracks intraday duplicate occurrences dynamically to calculate identical key spaces.
    """
    production_tx_pool = []
    duplicate_skip_count = 0

    if database_lookup_dict is None:
        database_lookup_dict = {}

    if not preview_dataset:
        return production_tx_pool, duplicate_skip_count

    # 🎯 DYNAMIC FILE ENGINES TRACKER: Counts recurring math signatures on the fly
    file_occurrence_tracker = {}

    for item in preview_dataset:
        if item is None or not isinstance(item, dict):
            continue

        pure_narration = normalize_narration_text(
            item.get("narration_description") or item.get("narration") or ""
        )
        cheque_ref = item.get("chq_ref") or item.get("cheque_ref_number") or None
        if cheque_ref in ["-", "", "NULL", "None"]:
            cheque_ref = None

        tx_date = (
            str(item.get("post_date") or item.get("date"))
            .split("T")[0]
            .split(" ")[0]
            .strip()
        )
        val_debit = item.get("debit")
        val_credit = item.get("credit")
        val_balance = item.get("balance") or item.get("running_balance") or "0.00"

        # Construct a strict fingerprint context key
        math_footprint = f"{tx_date}_{force_clean_float(val_debit):.2f}_{force_clean_float(val_credit):.2f}_{force_clean_float(val_balance):.2f}"

        # Increment sequence count dynamically
        current_idx = file_occurrence_tracker.get(math_footprint, 0)
        file_occurrence_tracker[math_footprint] = current_idx + 1

        # 🎯 PASS THE DYNAMIC INDEX GENERATOR
        row_hex = generate_row_fingerprint(
            bank_id="UNIVERSAL_CSV",
            account_id="STREAM_CONTEXT",
            debit=val_debit,
            credit=val_credit,
            running_balance=val_balance,
            date_str=tx_date,
            intraday_index=current_idx,  # 🚀 Unlocks identical twins!
        )

        cleaned_credit = force_clean_float(val_credit)
        cleaned_debit = force_clean_float(val_debit)

        dr_decimal = (
            decimal.Decimal(f"{cleaned_debit:.2f}")
            if val_debit not in {None, "", "-"}
            else None
        )
        cr_decimal = (
            decimal.Decimal(f"{cleaned_credit:.2f}")
            if val_credit not in {None, "", "-"}
            else None
        )
        raw_magnitude = decimal.Decimal(
            f"{(cleaned_credit if cleaned_credit > 0.0 else cleaned_debit):.2f}"
        )
        running_bal = decimal.Decimal(f"{force_clean_float(val_balance):.2f}")

        txn_payload = {
            "raw_statement_date": tx_date,
            "narration": pure_narration,
            "amount": raw_magnitude,
            "running_balance": running_bal,
            "debit": dr_decimal,
            "credit": cr_decimal,
            "bank_transaction_id": item.get("bank_transaction_id")
            or f"TXN_{str(row_hex)[:12]}",
            "cheque_ref_number": cheque_ref,
            "row_identifier": row_hex,
            "pipeline_action": "INSERT",
            "is_edited": False,
            "status": "NEW",
        }

        if row_hex in existing_hashes:
            existing_record = database_lookup_dict.get(row_hex)
            if existing_record:
                old_narration = normalize_narration_text(
                    existing_record.get("narration") or ""
                )
                old_chq = existing_record.get("cheque_ref_number")
                if old_chq in ["", "-", "None", "NULL"]:
                    old_chq = None

                merged_narr, merged_chq, is_narration_changed = (
                    calculate_narration_merge(
                        old_str=old_narration,
                        incoming_str=pure_narration,
                        old_chq=old_chq,
                        new_chq=cheque_ref,
                    )
                )
                has_new_cheque = (old_chq is None) and (cheque_ref is not None)

                if is_narration_changed or has_new_cheque:
                    txn_payload["pipeline_action"] = "UPDATE_ENRICHMENT"
                    txn_payload["is_edited"] = True
                    txn_payload["status"] = "ENRICHMENT_PENDING"
                    txn_payload["narration"] = merged_narr
                    txn_payload["cheque_ref_number"] = (
                        cheque_ref if has_new_cheque else old_chq
                    )

                    item["narration_description"] = merged_narr
                    item["chq_ref"] = merged_chq if merged_chq else "-"
                    item["status"] = "ENRI"
                    production_tx_pool.append(txn_payload)
                    continue

            item["status"] = "DUPLICATE"
            duplicate_skip_count += 1
            continue

        production_tx_pool.append(txn_payload)
        existing_hashes.add(row_hex)

    return production_tx_pool, duplicate_skip_count


def run_final_math(
    intermediate_txns,
    op_bal,
    template_obj=None,
    account_id=None,
    export_filename="statement_export.csv",
):
    """
    Unified Balance Ledger Parser Pass.
    Applies identical sequence trackers to align hashes across loops perfectly.
    """
    existing_hashes = set()
    if account_id:
        from ....models.models import StatementStagingLine

        existing_hashes = set(
            StatementStagingLine.objects.filter(account_id=str(account_id)).values_list(
                "row_identifier", flat=True
            )
        )

    date_regex_str = None
    if template_obj and template_obj.signature_json:
        try:
            sig_data = (
                json.loads(template_obj.signature_json)
                if isinstance(template_obj.signature_json, str)
                else template_obj.signature_json
            )
            date_regex_str = sig_data.get("regex_patterns", {}).get("DATE_MATCH")
        except Exception:
            pass

    if not date_regex_str:
        date_regex_str = r"\b\d{2}-\d{2}-\d{4}\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{4}/\d{2}/\d{2}\b|\b\d{2}/\d{2}/\d{4}\b"

    compiled_date_finder = re.compile(date_regex_str)

    calculated_total_debit = 0.0
    calculated_total_credit = 0.0
    debit_rows_count = 0
    credit_rows_count = 0
    empty_memo_line_count = 0
    detected_inline_op_bal = None

    frontend_aligned_dataset = []

    # 🎯 MATCHING SEQUENCE TRACKER
    file_occurrence_tracker = {}

    for txn in intermediate_txns:
        raw_deb = txn.get("debit", "-")
        raw_crd = txn.get("credit", "-")
        t_narr = normalize_narration_text(
            txn.get("narration") or txn.get("narration_description") or ""
        )
        t_bal = txn.get("balance") or txn.get("Balance") or "0.00"

        if any(
            kw in str(t_narr).lower() for kw in ["opening balance", "brought forward"]
        ):
            detected_inline_op_bal = force_clean_float(t_bal)
            continue

        if raw_deb and raw_deb != "-":
            calculated_total_debit += force_clean_float(raw_deb)
            debit_rows_count += 1

        if raw_crd and raw_crd != "-":
            calculated_total_credit += force_clean_float(raw_crd)
            credit_rows_count += 1

        if (raw_deb == "-" or not raw_deb) and (raw_crd == "-" or not raw_crd):
            empty_memo_line_count += 1

        raw_date_str = txn.get("post_date") or txn.get("date") or ""
        found_match = compiled_date_finder.search(str(raw_date_str).strip())
        t_date = str(raw_date_str).strip()

        if found_match:
            cleaned_val = found_match.group(0)
            t_date = cleaned_val
            try:
                if "/" in cleaned_val and cleaned_val.index("/") == 4:
                    t_date = datetime.strptime(cleaned_val, "%Y/%m/%d").strftime(
                        "%d-%m-%Y"
                    )
                elif "-" in cleaned_val and cleaned_val.index("-") == 4:
                    t_date = datetime.strptime(cleaned_val, "%Y-%m-%d").strftime(
                        "%d-%m-%Y"
                    )
                elif "/" in cleaned_val:
                    fmt_token = (
                        "%d/%m/%y"
                        if len(cleaned_val.split("/")[2]) == 2
                        else "%d/%m/%Y"
                    )
                    t_date = datetime.strptime(cleaned_val, fmt_token).strftime(
                        "%d-%m-%Y"
                    )
            except Exception:
                pass

        # Calculate matching sequence tracking keys
        math_footprint = f"{t_date}_{force_clean_float(raw_deb):.2f}_{force_clean_float(raw_crd):.2f}_{force_clean_float(t_bal):.2f}"
        current_idx = file_occurrence_tracker.get(math_footprint, 0)
        file_occurrence_tracker[math_footprint] = current_idx + 1

        # Synchronize fingerprint hashing using the dynamic sequence index
        row_hex = generate_row_fingerprint(
            bank_id="UNIVERSAL_CSV",
            account_id="STREAM_CONTEXT",
            debit=raw_deb,
            credit=raw_crd,
            running_balance=t_bal,
            date_str=t_date,
            intraday_index=current_idx,
        )

        record_status = "DUPLICATE" if row_hex in existing_hashes else "NEW"

        p_deb = norm.format_to_two_digits(raw_deb)
        p_cred = norm.format_to_two_digits(raw_crd)
        p_bal = norm.format_to_two_digits(t_bal)

        frontend_aligned_dataset.append(
            {
                "id": row_hex,
                "Hex": row_hex,
                "post_date": t_date,
                "value_date": t_date,
                "narration_description": t_narr,
                "type": txn.get("type", "-"),
                "chq_ref": txn.get("cheque_ref", "-"),
                "debit": p_deb,
                "credit": p_cred,
                "balance": p_bal,
                "status": record_status,
                "page_idx": txn.get("page_idx", 1),
            }
        )

    parsed_op_bal = force_clean_float(op_bal) if op_bal else 0.0
    if parsed_op_bal == 0.0 and detected_inline_op_bal is not None:
        parsed_op_bal = detected_inline_op_bal

    cl_bal = (
        force_clean_float(frontend_aligned_dataset[-1]["balance"])
        if frontend_aligned_dataset
        else 0.0
    )
    is_balance_matched = (
        abs((parsed_op_bal - calculated_total_debit + calculated_total_credit) - cl_bal)
        < 0.05
    )

    raw_csv_lines = [
        f"#FILENAME:{export_filename}",
        "Date ~ Narration ~ Debit ~ Credit ~ Running Bal ~ Record Status",
    ]
    for row in frontend_aligned_dataset:
        p_narr_escaped = str(row["narration_description"]).replace('"', '""').strip()
        raw_csv_lines.append(
            f'{row["post_date"]} ~ "{p_narr_escaped}" ~ {row["debit"]} ~ {row["credit"]} ~ {row["balance"]} ~ {row["status"]}'
        )

    return {
        "preview_dataset": frontend_aligned_dataset,
        "total_debit": calculated_total_debit,
        "total_credit": calculated_total_credit,
        "opening_balance": parsed_op_bal,
        "closing_balance": cl_bal,
        "count": len(frontend_aligned_dataset),
        "debit_line_count": debit_rows_count,
        "credit_line_count": credit_rows_count,
        "empty_memo_line_count": empty_memo_line_count,
        "audit_passed": is_balance_matched,
        "generated_raw_csv_stream": "\n".join(raw_csv_lines),
    }
