# tracker/classification/services.py

from tracker.models import JournalEntry
from tracker.classification.remarks_service import generate_initial_remarks


def create_journal_entry_from_staging(staging_row):
    debit_amt = staging_row.debit
    credit_amt = staging_row.credit

    # Delegate 100% of remark generation to remarks_service
    debit_json, credit_json = generate_initial_remarks(
        narration=staging_row.narration, debit=debit_amt, credit=credit_amt
    )

    # Use the debit or credit payload depending on which leg this entry represents
    remarks_payload = debit_json if debit_amt > 0 else credit_json

    entry = JournalEntry.objects.create(
        account_id=99,  # Suspense Account Node
        debit=debit_amt,
        credit=credit_amt,
        transaction_date=staging_row.transaction_date,
        remarks=remarks_payload,
        row_identifier=staging_row.row_identifier,
    )
    return entry
