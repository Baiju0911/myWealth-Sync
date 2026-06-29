# backend/tracker/parsers/parsers_v1/strategies/csv_parser_strategy.py
from ..utils.csv_engine import parse_universal_csv_stream
from ..utils.validator import run_final_math


def execute_csv_ingest_strategy(raw_file_bytes, template_obj, account_id):
    # Define landmarks to match your configuration rules
    column_mappings = {
        "post_date": ["Txn Date", "Transaction Date", "Date"],
        "narration": ["Narration Description", "Narration", "Description"],
        "debit": ["Debit (-)", "Debit"],
        "credit": ["Credit (+)", "Credit"],
        "balance": ["Balance", "Running Bal"],
    }

    # 1. Parse structural multiline rows into intermediate objects
    intermediate_txns = parse_universal_csv_stream(raw_file_bytes, column_mappings)

    # 2. Pass straight into the unified calculation brain we optimized
    payload = run_final_math(
        intermediate_txns=intermediate_txns,
        op_bal=0.00,  # or extract dynamically
        template_obj=template_obj,
        account_id=account_id,
    )

    return payload
