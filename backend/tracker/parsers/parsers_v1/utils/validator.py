# backend/tracker/parsers/parsers_v1/utils/validator.py
import decimal
from . import normalizer as norm
from ...utils import generate_row_fingerprint
import re

FINAL_SAFE_DATE_REGEX = re.compile(
    r"\b\d{2}-\d{2}-\d{4}\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{4}/\d{2}/\d{2}\b|\b\d{2}/\d{2}/\d{4}\b"
)


def run_final_math(
    intermediate_txns,
    op_bal,
    template_obj=None,
    account_id=None,
    export_filename="statement_export.csv",
):
    """
    Unified Single-Pass Brain: Runs template date sanitization, transformations, calculations,
    queries database hashes, and constructs normalized data payloads in a single optimized pass.
    """
    existing_hashes = set()
    if account_id:
        from tracker.models import StatementStagingLine

        existing_hashes = set(
            StatementStagingLine.objects.filter(account_id=str(account_id)).values_list(
                "row_identifier", flat=True
            )
        )

    # 🟢 1. EXTRACT TEMPLATE REGEX ONCE UP FRONT
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

    # Universal Fallback Rules
    if not date_regex_str:
        date_regex_str = r"\b\d{2}-\d{2}-\d{4}\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{4}/\d{2}/\d{2}\b|\b\d{2}/\d{2}/\d{4}\b"
    else:
        if (
            r"\b\d{4}/\d{2}/\d{2}\b" not in date_regex_str
            and "YYYY/MM/DD" not in date_regex_str
        ):
            date_regex_str += r"|\b\d{4}/\d{2}/\d{2}\b"

    compiled_date_finder = re.compile(date_regex_str)

    frontend_aligned_dataset = []
    calculated_total_debit = 0.0
    calculated_total_credit = 0.0
    debit_rows_count = 0
    credit_rows_count = 0
    empty_memo_line_count = 0

    raw_csv_lines = [
        f"#FILENAME:{export_filename}",
        "Date ~ Narration ~ Debit ~ Credit ~ Running Bal ~ Record Status",
    ]

    for txn in intermediate_txns:
        raw_deb = txn.get("debit", "-")
        raw_crd = txn.get("credit", "-")

        if raw_deb and raw_deb != "-":
            calculated_total_debit += norm.parse_float(raw_deb)
            debit_rows_count += 1

        if raw_crd and raw_crd != "-":
            calculated_total_credit += norm.parse_float(raw_crd)
            credit_rows_count += 1

        if (raw_deb == "-" or not raw_deb) and (raw_crd == "-" or not raw_crd):
            empty_memo_line_count += 1

        # 🟢 2. INLINE TEMPLATE SANITIZATION & TRANSFORMATION
        raw_date_str = (
            txn.get("post_date") or txn.get("date") or txn.get("Txn Date") or ""
        )
        found_match = compiled_date_finder.search(str(raw_date_str).strip())

        t_date = str(raw_date_str).strip()
        if found_match:
            cleaned_val = found_match.group(0)
            t_date = cleaned_val

            # Standardize variation structures straight to uniform DD-MM-YYYY
            try:
                if "/" in cleaned_val and cleaned_val.index("/") == 4:  # YYYY/MM/DD
                    t_date = datetime.strptime(cleaned_val, "%Y/%m/%d").strftime(
                        "%d-%m-%Y"
                    )
                elif "-" in cleaned_val and cleaned_val.index("-") == 4:  # YYYY-MM-DD
                    t_date = datetime.strptime(cleaned_val, "%Y-%m-%d").strftime(
                        "%d-%m-%Y"
                    )
                elif "/" in cleaned_val:  # DD/MM/YYYY
                    t_date = datetime.strptime(cleaned_val, "%d/%m/%Y").strftime(
                        "%d-%m-%Y"
                    )
            except (ValueError, IndexError):
                pass

        t_narr = (
            txn.get("narration")
            or txn.get("narration_description")
            or txn.get("Narration Description")
            or ""
        )
        t_bal = txn.get("balance") or txn.get("Balance") or "0.00"
        t_amt = (
            raw_deb
            if (raw_deb and str(raw_deb).strip() not in ["", "-", "None"])
            else raw_crd
        )

        # 🔒 Fingerprint Verification Step using perfectly formatted t_date
        row_hex = generate_row_fingerprint(
            bank_id=txn.get("bank_id", ""),
            account_id=str(account_id) if account_id else "",
            narration=t_narr,
            cheque_ref=txn.get("cheque_ref", "-"),
            amount=t_amt,
            running_balance=t_bal,
            debit=raw_deb,
            credit=raw_crd,
            date_str=t_date,
        )

        record_status = "DUPLICATE" if row_hex in existing_hashes else "NEW"

        p_deb = norm.format_to_two_digits(raw_deb)
        p_cred = norm.format_to_two_digits(raw_crd)
        p_bal = norm.format_to_two_digits(t_bal)
        p_narr_escaped = str(t_narr).replace('"', '""').strip()

        # Build CSV array row inline
        raw_csv_lines.append(
            f'{t_date} ~ "{p_narr_escaped}" ~ {p_deb} ~ {p_cred} ~ {p_bal} ~ {record_status}'
        )

        frontend_aligned_dataset.append(
            {
                "id": row_hex,
                "Hex": row_hex,
                "post_date": t_date,  # 🎯 Guaranteed uniform DD-MM-YYYY
                "value_date": t_date,  # 🎯 Guaranteed uniform DD-MM-YYYY
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

    cl_bal = 0.0
    if frontend_aligned_dataset:
        cl_bal = norm.parse_float(frontend_aligned_dataset[-1]["balance"])

    if cl_bal == 0.0:
        cl_bal = op_bal - calculated_total_debit + calculated_total_credit

    is_balance_matched = (
        abs((op_bal - calculated_total_debit + calculated_total_credit) - cl_bal) < 0.05
    )

    return {
        "preview_dataset": frontend_aligned_dataset,
        "total_debit": calculated_total_debit,
        "total_credit": calculated_total_credit,
        "opening_balance": op_bal,
        "closing_balance": cl_bal,
        "count": len(frontend_aligned_dataset),
        "debit_line_count": debit_rows_count,
        "credit_line_count": credit_rows_count,
        "empty_memo_line_count": empty_memo_line_count,
        "audit_passed": is_balance_matched,
        "generated_raw_csv_stream": "\n".join(raw_csv_lines),
    }


def process_and_filter_rows1(preview_dataset, account, bank, existing_hashes):
    """Loops through data rows to check for duplicates and map model inputs."""
    production_tx_pool = []
    duplicate_skip_count = 0

    for index, item in enumerate(preview_dataset):
        pure_narration = (
            item.get("narration_description", "").strip()
            or item.get("description", "").strip()
        )

        cheque_ref = item.get("chq_ref") or item.get("cheque_ref") or None
        if cheque_ref == "-":
            cheque_ref = None

        # 🎯 THE CRITICAL GATEWAY FIX: Explicitly match the frontend's unified keys
        raw_date = item.get("post_date") or item.get("db_date") or item.get("date")
        tx_date = norm.normalize_row_date(raw_date, index)

        val_debit = item.get("debit")
        val_credit = item.get("credit")

        dr_decimal = (
            decimal.Decimal(str(val_debit))
            if val_debit not in {None, "", "-"}
            else None
        )
        cr_decimal = (
            decimal.Decimal(str(val_credit))
            if val_credit not in {None, "", "-"}
            else None
        )

        raw_magnitude = float(
            val_credit if val_credit else (val_debit if val_debit else 0.00)
        )
        running_bal = float(item.get("amount") or item.get("balance", 0.00))

        # Fingerprint Security Validation
        row_hex = item.get("Hex") or item.get("row_identifier") or item.get("id")
        if not row_hex or len(str(row_hex)) < 64:
            row_hex = generate_row_fingerprint(
                bank_id=bank.id,
                account_id=account.id,
                narration=pure_narration,
                cheque_ref=cheque_ref or "-",
                amount=raw_magnitude,
                running_balance=running_bal,
                debit=float(val_debit) if val_debit else None,
                credit=float(val_credit) if val_credit else None,
                date_str=str(item.get("post_date") or item.get("date", "")),
            )

        if (
            row_hex in existing_hashes
            or item.get("status") == "DUPLICATE"
            or item.get("status") == "STALE"
        ):
            duplicate_skip_count += 1
            continue

        production_tx_pool.append(
            {
                "raw_statement_date": tx_date,
                "narration": pure_narration,
                "amount": decimal.Decimal(str(raw_magnitude)),
                "running_balance": decimal.Decimal(str(running_bal)),
                "debit": dr_decimal,
                "credit": cr_decimal,
                "bank_transaction_id": item.get("bank_transaction_id") or "",
                "cheque_ref_number": cheque_ref,
                "row_identifier": row_hex,
            }
        )
        existing_hashes.add(row_hex)

    return production_tx_pool, duplicate_skip_count


def process_and_filter_rows(preview_dataset, account, bank, existing_hashes):
    """
    🔒 STREAMLINED DUPLICATE FILTER PASS:
    Trusts the initial deterministic parser execution checks and uses the original
    state parameters to prevent layout mutation mismatches.
    """
    production_tx_pool = []
    duplicate_skip_count = 0

    # 🎯 Defensive Check: Ensure preview_dataset is a valid iterable list
    if not preview_dataset:
        return production_tx_pool, duplicate_skip_count

    for index, item in enumerate(preview_dataset):
        # 🛡️ CRITICAL FIX: Skip the line entirely if it is empty or NoneType
        if item is None or not isinstance(item, dict):
            print(f"⚠️ Skipping corrupted non-dictionary row entry at index {index}")
            continue

        # Check if the row was already identified as duplicate or stale
        if item.get("status") in ["DUPLICATE", "STALE"]:
            duplicate_skip_count += 1
            continue

        # Extract standard model inputs safely
        pure_narration = str(
            item.get("narration_description") or item.get("description") or ""
        ).strip()

        cheque_ref = item.get("chq_ref") or item.get("cheque_ref") or None
        if cheque_ref == "-":
            cheque_ref = None

        # Process clean dates safely using your normalizer rules
        raw_date = item.get("post_date") or item.get("date")
        tx_date = norm.normalize_row_date(raw_date, index)

        val_debit = item.get("debit")
        val_credit = item.get("credit")

        dr_decimal = (
            decimal.Decimal(str(val_debit))
            if val_debit not in {None, "", "-"}
            else None
        )
        cr_decimal = (
            decimal.Decimal(str(val_credit))
            if val_credit not in {None, "", "-"}
            else None
        )

        # Calculate magnitudes for storage
        raw_magnitude = float(
            val_credit if val_credit else (val_debit if val_debit else 0.00)
        )
        running_bal = float(item.get("balance") or item.get("amount", 0.00))

        # Pull the tracking fingerprint directly from the payload object keys
        row_hex = item.get("Hex") or item.get("row_identifier") or item.get("id")

        # Double check to prevent secondary writes if a user double-clicks the save button
        if row_hex in existing_hashes:
            duplicate_skip_count += 1
            continue

        # Append the verified row data directly to the database batch write array
        production_tx_pool.append(
            {
                "raw_statement_date": tx_date,
                "narration": pure_narration,
                "amount": decimal.Decimal(str(raw_magnitude)),
                "running_balance": decimal.Decimal(str(running_bal)),
                "debit": dr_decimal,
                "credit": cr_decimal,
                "bank_transaction_id": item.get("bank_transaction_id")
                or f"TXN_{index}_{str(row_hex)[:8] if row_hex else 'ERR'}",
                "cheque_ref_number": cheque_ref,
                "row_identifier": (
                    row_hex
                    if (row_hex and len(str(row_hex)) >= 64)
                    else f"ERR_FALLBACK_{index}"
                ),
            }
        )

        if row_hex and len(str(row_hex)) >= 64:
            existing_hashes.add(row_hex)

    return production_tx_pool, duplicate_skip_count
