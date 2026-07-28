# tracker/classification/remarks_service.py

import re
from tracker.classification.utils.upiparser import parse_upi_narration


def generate_cluster_pattern(narration: str, remarks_data: dict = None) -> str:
    """
    Generates granular #tags based on parsed payee names or narration keywords.
    Prevents thousands of rows from collapsing into a generic #GENERAL_OPERATING_EXPENSES.
    """
    remarks_data = remarks_data or {}
    payee = remarks_data.get("payee")

    # If payee was not in remarks, attempt to parse it from narration directly
    if not payee and narration:
        parsed = parse_upi_narration(narration)
        payee = parsed.get("payee")

    # 1. Primary Tag: Clean extracted payee name
    if payee and payee.upper() not in {
        "BANK TRANSACTION",
        "SUSPENSE ACCOUNT",
        "MOB",
        "TRANSFER",
        "NULL",
        "UNKNOWN",
    }:
        # Sanitize payee into a valid #TAG string (e.g., "DHANYA B AIJU" -> "#DHANYA_B_AIJU")
        sanitized_payee = re.sub(r"[^A-Z0-9]+", "_", payee.upper()).strip("_")
        if len(sanitized_payee) > 2:
            return f"{sanitized_payee}"

    # 2. Secondary Tag: Non-UPI / System Patterns
    narration_upper = (narration or "").upper()
    if "INT.PD" in narration_upper or "INTEREST CREDIT" in narration_upper:
        return "#BANK_INTEREST"
    if "RETN CHRG" in narration_upper or "BANK CHARGES" in narration_upper:
        return "#BANK_CHARGES"
    if "NACH" in narration_upper:
        return "#NACH_DIRECT_DEBIT"

    # 3. Fallback for completely ambiguous rows
    return "#UNCLASSIFIED_OTHER"


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

    # Compute cluster pattern dynamically at initial remarks creation
    pattern_tag = generate_cluster_pattern(narration, {"payee": payee})

    base_payload = {
        "payee": payee,
        "upi_ref": ref_no,
        "pattern": pattern_tag,  # 👈 Store the granular pattern tag!
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


# from tracker.classification.utils.upiparser import parse_upi_narration


# def generate_initial_remarks(
#     narration: str, debit: float, credit: float, bank_name: str = "Bank A/c"
# ) -> tuple[dict, dict]:
#     """
#     Generates structured JSON remarks for both legs at ingestion.
#     Returns: (debit_leg_json, credit_leg_json)
#     """
#     parsed_meta = parse_upi_narration(narration)
#     payee = parsed_meta.get("payee")
#     ref_no = parsed_meta.get("upi_ref")

#     is_outflow = debit > 0
#     amount_val = debit if is_outflow else credit
#     amount_str = f"₹{amount_val:,.2f}"

#     if payee:
#         direction_phrase = (
#             f"Paid {amount_str} to {payee}"
#             if is_outflow
#             else f"Received {amount_str} from {payee}"
#         )
#     else:
#         direction_phrase = (
#             f"Outflow of {amount_str}" if is_outflow else f"Inflow of {amount_str}"
#         )

#     action_str = f"{direction_phrase} [Ref: {ref_no}]" if ref_no else direction_phrase

#     base_payload = {
#         "payee": payee,
#         "upi_ref": ref_no,
#         "user_note": None,
#         "rule_code": None,
#         "source": "STAGING_INGEST",
#     }

#     debit_json = {
#         **base_payload,
#         "directional_prefix": "By",
#         "target_account_name": "Suspense Account" if is_outflow else bank_name,
#         "display_text": (
#             f"By Suspense Account | {action_str} | Ingested via Staging"
#             if is_outflow
#             else f"By {bank_name} | {action_str} | Ingested via Staging"
#         ),
#     }

#     credit_json = {
#         **base_payload,
#         "directional_prefix": "To",
#         "target_account_name": bank_name if is_outflow else "Suspense Account",
#         "display_text": (
#             f"To {bank_name} | {action_str} | Ingested via Staging"
#             if is_outflow
#             else f"To Suspense Account | {action_str} | Ingested via Staging"
#         ),
#     }

#     return debit_json, credit_json
