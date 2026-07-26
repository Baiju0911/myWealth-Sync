from tracker.classification.utils.upiparser import parse_upi_narration


def generate_initial_remarks(
    narration: str, debit: float, credit: float, bank_name: str = "Bank A/c"
) -> tuple[dict, dict]:
    """
    Generates structured JSON remarks for both legs at ingestion.
    Returns: (debit_leg_json, credit_leg_json)
    """
    parsed_meta = parse_upi_narration(narration)
    payee = parsed_meta.get("payee")
    ref_no = parsed_meta.get("upi_ref")

    is_outflow = debit > 0
    amount_val = debit if is_outflow else credit
    amount_str = f"₹{amount_val:,.2f}"

    if payee:
        direction_phrase = (
            f"Paid {amount_str} to {payee}"
            if is_outflow
            else f"Received {amount_str} from {payee}"
        )
    else:
        direction_phrase = (
            f"Outflow of {amount_str}" if is_outflow else f"Inflow of {amount_str}"
        )

    action_str = f"{direction_phrase} [Ref: {ref_no}]" if ref_no else direction_phrase

    base_payload = {
        "payee": payee,
        "upi_ref": ref_no,
        "user_note": None,
        "rule_code": None,
        "source": "STAGING_INGEST",
    }

    debit_json = {
        **base_payload,
        "directional_prefix": "By",
        "target_account_name": "Suspense Account" if is_outflow else bank_name,
        "display_text": (
            f"By Suspense Account | {action_str} | Ingested via Staging"
            if is_outflow
            else f"By {bank_name} | {action_str} | Ingested via Staging"
        ),
    }

    credit_json = {
        **base_payload,
        "directional_prefix": "To",
        "target_account_name": bank_name if is_outflow else "Suspense Account",
        "display_text": (
            f"To {bank_name} | {action_str} | Ingested via Staging"
            if is_outflow
            else f"To Suspense Account | {action_str} | Ingested via Staging"
        ),
    }

    return debit_json, credit_json
