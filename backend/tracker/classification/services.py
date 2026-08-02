# tracker/classification/services.py

from tracker.classification.remarks_service import generate_initial_remarks
from tracker.models import JournalEntry


def create_journal_entry_from_staging(
    staging_row, evaluation_result=None
):  # Added evaluation_result
    debit_amt = staging_row.debit
    credit_amt = staging_row.credit

    # 🟢 1. Generate core remarks payload
    debit_json, credit_json = generate_initial_remarks(
        narration=staging_row.narration, debit=debit_amt, credit=credit_amt
    )
    remarks_payload = debit_json if debit_amt > 0 else credit_json

    # 🟢 2. Fallback check: Ensure narration and payee exist inside remarks
    if isinstance(remarks_payload, dict):
        if "narration" not in remarks_payload or not remarks_payload["narration"]:
            remarks_payload["narration"] = staging_row.narration
        if "payee" not in remarks_payload or not remarks_payload["payee"]:
            remarks_payload["payee"] = getattr(
                staging_row, "payee", staging_row.narration
            )

    # 🟢 3. Extract evaluation snapshot from Sync-Shield matcher
    target_cat = "Expense"
    target_sub = "Suspense Account"
    rule_code = "MANUAL"

    if evaluation_result:
        target_cat = getattr(evaluation_result, "target_category", "Expense")
        target_sub = getattr(
            evaluation_result, "target_subcategory", "Suspense Account"
        )
        rule_code = getattr(evaluation_result, "applied_rule_code", "MANUAL")

    snapshot_payload = {
        "t1_category": target_cat,
        "t1_subcategory": target_sub,
        "resolved_category": target_cat,
        "resolved_subcategory": target_sub,
        "applied_rule_code": rule_code,
    }

    # 🟢 4. Persist Journal Entry with full remarks and rule snapshot
    entry = JournalEntry.objects.create(
        account_id=99,  # Suspense Account Node
        debit=debit_amt,
        credit=credit_amt,
        transaction_date=staging_row.transaction_date,
        remarks=remarks_payload,
        evaluation_matrix_snapshot=snapshot_payload,
        row_identifier=staging_row.row_identifier,
        classification_status="PENDING",
    )
    return entry


# # tracker/classification/services.py

# from tracker.models import JournalEntry
# from tracker.classification.remarks_service import generate_initial_remarks


# def create_journal_entry_from_staging(staging_row):
#     debit_amt = staging_row.debit
#     credit_amt = staging_row.credit

#     # Delegate 100% of remark generation to remarks_service
#     debit_json, credit_json = generate_initial_remarks(
#         narration=staging_row.narration, debit=debit_amt, credit=credit_amt
#     )

#     # Use the debit or credit payload depending on which leg this entry represents
#     remarks_payload = debit_json if debit_amt > 0 else credit_json

#     entry = JournalEntry.objects.create(
#         account_id=99,  # Suspense Account Node
#         debit=debit_amt,
#         credit=credit_amt,
#         transaction_date=staging_row.transaction_date,
#         remarks=remarks_payload,
#         row_identifier=staging_row.row_identifier,
#     )
#     return entry
