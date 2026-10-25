import re
import logging
from rest_framework import serializers

try:
    from .smart_enricher import SmartPayloadEnricher
except ImportError:
    try:
        from tracker.backendViewModel.InboxHelper.smart_enricher import (
            SmartPayloadEnricher,
        )
    except ImportError:
        SmartPayloadEnricher = None

try:
    from tracker.constants import EnrichmentMetadata
except ImportError:

    class EnrichmentMetadata:
        DEFAULT_SOURCE = "MERGED_STREAM"
        DEFAULT_MERCHANT = "Direct Payment"


logger = logging.getLogger(__name__)

GENERIC_PAYEE_BLACKLIST = {
    "DIRECT PAYMENT",
    "DIRECT_PAYMENT",
    "UNKNOWN",
    "PAYMENT",
    "UPI",
    "TRANSFER",
    "INFO",
    "UNCLASSIFIED",
    "NO REMARK",
    "NO REMAR",
}


class LiveStreamPayloadSerializer(serializers.Serializer):
    id = serializers.CharField()
    source = serializers.CharField()
    sender = serializers.CharField(allow_blank=True, allow_null=True)
    subject = serializers.CharField(allow_blank=True, allow_null=True)
    raw_body = serializers.CharField(allow_blank=True, allow_null=True)
    amount = serializers.DecimalField(max_digits=15, decimal_places=2, allow_null=True)
    balance = serializers.DecimalField(max_digits=15, decimal_places=2, allow_null=True)
    account_last4 = serializers.CharField(allow_blank=True, allow_null=True)
    bank_name = serializers.CharField(allow_blank=True, allow_null=True)
    upi_ref = serializers.CharField(allow_blank=True, allow_null=True)
    status = serializers.CharField()
    created_at = serializers.CharField(allow_null=True)
    txn_date = serializers.CharField(allow_blank=True, allow_null=True)
    full_narration = serializers.CharField(allow_blank=True, allow_null=True)
    merchant = serializers.CharField(allow_blank=True, allow_null=True)
    smart_meta = serializers.DictField(default=dict)

    # 🎯 Authoritative Backend Classification Fields
    direction = serializers.CharField()
    payment_protocol = serializers.CharField()
    amount_label = serializers.CharField()
    clean_beneficiary = serializers.CharField()

    @staticmethod
    def detect_direction(body: str, subject: str = "") -> str:
        """Determines whether transaction is DEBIT or CREDIT."""
        combined = f"{subject} {body}".upper()
        if any(
            word in combined for word in ["CREDIT", "RECEIVED", "DEPOSITED", "REFUND"]
        ):
            return "CREDIT"
        return "DEBIT"

    @staticmethod
    def detect_protocol(body: str, upi_ref: str = None) -> str:
        """Identifies transfer channel."""
        body_upper = body.upper()
        if "IMPS" in body_upper:
            return "IMPS"
        if "UPI" in body_upper or (upi_ref and len(str(upi_ref)) >= 6):
            return "UPI"
        if "NEFT" in body_upper:
            return "NEFT"
        if "RTGS" in body_upper:
            return "RTGS"
        if "ATM" in body_upper:
            return "ATM"
        if "POS" in body_upper or "CARD" in body_upper:
            return "POS"
        return "TRANSFER"

    @classmethod
    def clean_payee_entity(cls, narration: str) -> str:
        """Extracts the true entity name and strips prefixes/suffixes."""
        if not narration:
            return "Direct Payment"

        text = narration.strip()

        # Check self transfer pattern in info streams
        if re.search(r"/(?:self|own account)/", text, re.IGNORECASE):
            return "Self Transfer"

        # Handle slash streams: UPI/SBIN/625522137653/SUMEE -> SUMEE
        parts = [p.strip() for p in text.split("/") if p.strip()]
        if len(parts) >= 4 and parts[0].upper() == "UPI":
            candidate = parts[3]
            candidate = re.sub(r"\s*NO REMAR.*$", "", candidate, flags=re.I).strip()
            if candidate.upper() not in GENERIC_PAYEE_BLACKLIST and len(candidate) > 1:
                return candidate
        elif len(parts) >= 3 and parts[0].upper() == "IMPS":
            candidate = parts[2]
            candidate = re.sub(r"\s*NO REMAR.*$", "", candidate, flags=re.I).strip()
            if candidate.upper() not in GENERIC_PAYEE_BLACKLIST and len(candidate) > 1:
                return candidate

        # Fallback regex strip
        cleaned = re.sub(r"^(UPI|IMPS|NEFT)/(\d+|REF)/", "", text, flags=re.I)
        cleaned = re.sub(r"/(NO REMAR.*|NO REMARK.*)$", "", cleaned, flags=re.I)
        cleaned = cleaned.strip()

        if cleaned.upper() in GENERIC_PAYEE_BLACKLIST or not cleaned:
            return "Direct Payment"
        return cleaned

    @classmethod
    def serialize_record(cls, record) -> dict:
        """Transforms a raw RawEmailPayload into normalized payload dictionary."""
        headers = record.headers_json or {}
        parsed = headers.get("parsed_summary", {}) if isinstance(headers, dict) else {}

        # 🛡️ Authentic Body Content Priority: Decrypted body -> body_text -> raw snippet
        body_content = (
            getattr(record, "decrypted_body", None)
            or getattr(record, "body_text", None)
            or getattr(record, "body", None)
            or getattr(record, "snippet", None)
            or (
                parsed.get("full_narration")
                if parsed.get("full_narration") != "UPI/REF/Direct Payment"
                else None
            )
            or ""
        )

        harvested = {}
        if SmartPayloadEnricher:
            try:
                harvested = SmartPayloadEnricher.harvest_all(
                    subject=record.subject,
                    body_text=body_content,
                    headers_json=headers,
                    existing_amount=record.amount,
                    existing_account_last4=record.account_last4,
                    existing_upi_ref=record.upi_ref,
                )
            except Exception as e:
                logger.warning(
                    f"SmartPayloadEnricher harvest failed on record {record.id}: {e}"
                )

        direction = cls.detect_direction(body_content, record.subject or "")
        upi_ref_candidate = (
            harvested.get("upi_ref")
            or record.upi_ref
            or headers.get("merge_details", {}).get("matched_rrn")
            or parsed.get("upi_ref")
            or parsed.get("utr_no")
        )
        protocol = cls.detect_protocol(body_content, upi_ref_candidate)

        raw_merchant = (
            getattr(record, "merchant", None)
            or parsed.get("merchant")
            or headers.get("merge_details", {}).get("resolved_narration")
            or record.subject
            or ""
        )

        clean_name = harvested.get("payee_hint") or cls.clean_payee_entity(
            raw_merchant or body_content
        )

        default_source = getattr(EnrichmentMetadata, "DEFAULT_SOURCE", "MERGED_STREAM")
        bank_label = (
            parsed.get("bank")
            or getattr(record, "bank_name", None)
            or "SOUTH INDIAN BANK"
        )

        clean_full_narration = parsed.get("full_narration")
        if not clean_full_narration or clean_full_narration.strip().startswith(
            "Dear Customer"
        ):
            # Check if harvested payee or remark exists
            if harvested.get("payee_hint"):
                clean_full_narration = (
                    f"{harvested.get('payee_hint')} ({harvested.get('remark_hint')})"
                    if harvested.get("remark_hint")
                    else harvested.get("payee_hint")
                )
            else:
                clean_full_narration = body_content

        return {
            "id": str(record.id),
            "source": record.source or headers.get("source", default_source),
            "sender": record.sender
            or getattr(record, "email_from", None)
            or "SMS Gateway",
            "subject": record.subject or "NO_SUBJECT",
            "raw_body": body_content,
            "full_narration": clean_full_narration
            or "No raw body preserved."
            or parsed.get("full_narration")
            or "No raw body preserved.",
            "amount": (
                float(record.amount)
                if record.amount is not None
                else parsed.get("amount")
            ),
            "balance": harvested.get("balance") or parsed.get("balance"),
            "account_last4": (
                harvested.get("account_last4")
                or record.account_last4
                or parsed.get("account")
            ),
            "bank_name": bank_label,
            "upi_ref": upi_ref_candidate,
            "status": record.status,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "txn_date": harvested.get("txn_date")
            or (
                record.email_date.isoformat()
                if getattr(record, "email_date", None)
                else None
            ),
            "merchant": raw_merchant,
            "txn_fingerprint": getattr(record, "txn_fingerprint", None),
            "smart_meta": harvested.get("extra_meta", {}),
            # 🎯 Authoritative Backend Logic
            "direction": direction,
            "payment_protocol": f"{protocol} {direction}",
            "amount_label": f"Target {direction.capitalize()} Amount",
            "clean_beneficiary": clean_name,
        }
