import re
from tracker.classification.utils.upiparser import parse_upi_narration

BLACKLIST_TAGS = {
    "TRANSFER_NACH",
    "TRANSFER",
    "TRANSFER_COLON",  # Handles regex-sanitized TRANSFER:
    "NACH",
    "IMPS",
    "UPI",
    "MOB",
    "SUSPENSE_ACCOUNT",
    "UNCLASSIFIED_OTHER",
    "GENERAL_OPERATING_EXPENSES",
    "OWN_ACCOUNT",
    "NULL",
    "UNKNOWN",
}


def generate_cluster_pattern(narration: str, remarks_data: dict = None) -> str:
    remarks_data = remarks_data or {}
    payee = remarks_data.get("payee")

    # If payee is missing or blacklisted, parse directly from raw narration
    if (
        not payee
        or re.sub(r"[^A-Z0-9]+", "_", str(payee).upper()).strip("_") in BLACKLIST_TAGS
        or str(payee).upper().startswith("TRANSFER")
    ):
        parsed = parse_upi_narration(narration) or {}
        payee = parsed.get("payee")

    if payee:
        payee_upper = payee.upper().strip()
        sanitized = re.sub(r"[^A-Z0-9]+", "_", payee_upper).strip("_")

        if len(sanitized) > 2 and sanitized not in BLACKLIST_TAGS:
            return sanitized

    return "UNCLASSIFIED_OTHER"


def generate_initial_remarks(
    narration: str,
    debit: float,
    credit: float,
    bank_name: str = "Bank A/c",
    target_category: str = "Suspense Account",
) -> tuple[dict, dict]:
    """
    Builds structured JSON payload for debit and credit legs of a journal entry during staging ingestion.
    Guarantees clean payee extraction, directional text ('By' vs 'To'), and reference numbers.
    """
    parsed_meta = parse_upi_narration(narration) or {}
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

    target_name = (
        target_category
        if target_category and target_category != "Suspense Account"
        else "Suspense Account"
    )

    debit_json = {
        **base_payload,
        "directional_prefix": "By",
        "target_account_name": target_name if is_outflow else bank_name,
        "display_text": (
            f"By {target_name} | {action_str} | Ingested via Staging"
            if is_outflow
            else f"By {bank_name} | {action_str} | Ingested via Staging"
        ),
    }

    credit_json = {
        **base_payload,
        "directional_prefix": "To",
        "target_account_name": bank_name if is_outflow else target_name,
        "display_text": (
            f"To {bank_name} | {action_str} | Ingested via Staging"
            if is_outflow
            else f"To {target_name} | {action_str} | Ingested via Staging"
        ),
    }

    return debit_json, credit_json
