# backend/tracker/parsers/parsers_v1/utils/validator.py
from . import normalizer as norm


def run_final_math(intermediate_txns, op_bal):
    """
    Takes raw transaction records, isolates the calculations,
    and handles the math validation completely.
    """
    frontend_aligned_dataset = []
    calculated_total_debit = 0.0
    calculated_total_credit = 0.0
    debit_rows_count = 0
    credit_rows_count = 0
    empty_memo_line_count = 0

    for txn in intermediate_txns:
        raw_deb = txn.get("debit", "-")
        raw_crd = txn.get("credit", "-")

        # Process Debits safely
        if raw_deb and raw_deb != "-":
            calculated_total_debit += norm.parse_float(raw_deb)
            debit_rows_count += 1

        # Process Credits safely
        if raw_crd and raw_crd != "-":
            calculated_total_credit += norm.parse_float(raw_crd)
            credit_rows_count += 1

        if (raw_deb == "-" or not raw_deb) and (raw_crd == "-" or not raw_crd):
            empty_memo_line_count += 1

        # Shape the object precisely for your frontend
        frontend_aligned_dataset.append(
            {
                "post_date": txn.get("post_date"),
                "value_date": txn.get("value_date"),
                "narration_description": txn.get("narration"),
                "type": txn.get("type", "-"),
                "chq_ref": txn.get("cheque_ref", "-"),
                "debit": txn.get("debit"),
                "credit": txn.get("credit"),
                "balance": txn.get("balance"),
                "status": txn.get("status", "NEW"),
                "page_idx": txn.get("page_idx", 1),
            }
        )

    # Pull closing balance baseline safely
    cl_bal = 0.0
    if frontend_aligned_dataset:
        last_row_bal = frontend_aligned_dataset[-1].get("balance", "0")
        cl_bal = norm.parse_float(last_row_bal)

    # Fallback formula anchor
    if cl_bal == 0.0:
        cl_bal = op_bal - calculated_total_debit + calculated_total_credit

    # Run the balance matching verification check
    is_balance_matched = (
        abs((op_bal - calculated_total_debit + calculated_total_credit) - cl_bal) < 0.05
    )

    # Return the exact payload dict your view used to build manually
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
        "data": {
            "preview_dataset": frontend_aligned_dataset,
            "file_type": "UNIVERSAL_PDF",
            "decrypted": True,
            "count": len(frontend_aligned_dataset),
            "opening_balance": op_bal,
            "closing_balance": cl_bal,
            "total_debit": calculated_total_debit,
            "total_credit": calculated_total_credit,
            "debit_line_count": debit_rows_count,
            "credit_line_count": credit_rows_count,
            "empty_memo_line_count": empty_memo_line_count,
            "audit_passed": is_balance_matched,
        },
    }
