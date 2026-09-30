import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Tuple

from tracker.constants import (
    ParserRegex,
    EnrichmentMetadata,
    SystemDefaults,
)

logger = logging.getLogger(__name__)


class SmartPayloadEnricher:
    """
    Intelligent entity extraction engine that inspects decrypted and raw payloads
    to harvest missing financial attributes without hardcoded bank-specific rules.
    """

    # Matches true account numbers in subjects (e.g., XXXXXXXXXXXXXX60 or ending in 0060)
    SUBJECT_ACCOUNT_PATTERN = re.compile(
        r"(?:account|a/c)\s*[xX*]*([0-9]{2,16})", re.IGNORECASE
    )

    # Term deposit details table extractor
    TD_TABLE_PATTERN = re.compile(
        r"(?:Account\s+Number\s+Open\s+Date|Account\s+Number)[\s\S]*?(\d{12,18})\s+(\d{2}[-/]\d{2}[-/]\d{4})?\s*(\d{2}[-/]\d{2}[-/]\d{4})?\s*(\d+(?:\.\d{1,2})?)\s*(?:INR|RS\.?)?\s*([0-9]+\s*(?:Months|Days|Years)[^\n\r]*?)?\s*(\d{2}[-/]\d{2}[-/]\d{4})?\s*(\d+(?:\.\d{1,2})?)\s*(\d+(?:\.\d{1,2})?)",
        re.IGNORECASE,
    )

    LOAN_OPENED_PATTERN = re.compile(
        r"loan\s*\(([xX*0-9]+)\)\s*for\s*(?:an\s*amount\s*of)?\s*(?:Rs\.?|INR)?\s*([\d,]+(?:\.\d{1,2})?)",
        re.IGNORECASE,
    )

    BALANCE_PATTERN = re.compile(
        r"(?:Bal|Balance|Final\s*balance|Avl\s*Bal)[:\s]*(?:is\s*)?(?:Rs\.?|INR)?\s*([\d,]+(?:\.\d{1,2})?)",
        re.IGNORECASE,
    )

    # Date pattern: "on 18-03-2025", "on 18/03/2025", "dated 18-03-2025"
    TXN_DATE_PATTERN = re.compile(
        r"\b(?:on|dated)\s+(\d{2}[-/]\d{2}[-/]\d{2,4})",
        re.IGNORECASE,
    )

    # IMPS / MOB pattern: MOB/507710983141/self/IMPS or IMPS/507710983141
    IMPS_MOB_PATTERN = re.compile(
        r"(?:MOB|IMPS|P2A)/(\d{10,12})",
        re.IGNORECASE,
    )

    @classmethod
    def harvest_all(
        cls,
        subject: Optional[str],
        body_text: Optional[str],
        headers_json: Optional[Dict[str, Any]],
        existing_amount: Optional[Decimal],
        existing_account_last4: Optional[str],
        existing_upi_ref: Optional[str],
    ) -> Dict[str, Any]:
        """
        Synthesizes structured payload fields by auditing extracted text against
        the raw payload text and headers.
        """
        body = body_text or ""
        subj = subject or ""
        headers = headers_json if isinstance(headers_json, dict) else {}
        parsed = headers.get("parsed_summary", {}) if isinstance(headers, dict) else {}

        # 1. Resolve true Account Last 4 (avoid password sample footers)
        resolved_account_last4 = existing_account_last4 or parsed.get("account")
        if (
            not resolved_account_last4
            or resolved_account_last4 == "5155"  # Sample footer check
            or len(str(resolved_account_last4).strip()) < 2
        ):
            resolved_account_last4 = cls._extract_true_account(subj, body)

        # 2. Resolve Amount (with hardened Decimal conversion protection)
        resolved_amount = None
        raw_amt_candidate = existing_amount or parsed.get("amount")

        if raw_amt_candidate is not None:
            try:
                cand_dec = Decimal(str(raw_amt_candidate).strip().replace(",", ""))
                if cand_dec != Decimal("0.00"):
                    resolved_amount = cand_dec
            except (InvalidOperation, TypeError, ValueError):
                resolved_amount = None

        if resolved_amount is None:
            extracted_amt = cls._extract_smart_amount(body, subj)
            if extracted_amt is not None:
                resolved_amount = extracted_amt

        # 3. Resolve Reference / Anchor
        resolved_ref = (
            existing_upi_ref
            or headers.get("merge_details", {}).get("matched_rrn")
            or parsed.get("upi_ref")
            or parsed.get("utr_no")
        )
        if not resolved_ref and body:
            resolved_ref = cls._extract_smart_reference(body)

        # 4. Resolve Balance & Term Deposit Metadata
        extracted_balance = cls._extract_balance(body) or parsed.get("balance")
        td_meta = cls._extract_term_deposit_metadata(body)

        # 5. Resolve Bank Transaction Date ("On Date")
        bank_txn_date = cls._extract_bank_txn_date(body)

        # 6. Resolve Merchant / Beneficiary hint
        payee_hint = cls._extract_payee_hint(body)

        return {
            "amount": resolved_amount,
            "account_last4": resolved_account_last4,
            "upi_ref": resolved_ref,
            "balance": extracted_balance,
            "txn_date": bank_txn_date,
            "payee_hint": payee_hint,
            "extra_meta": td_meta,
        }

    @classmethod
    def _extract_true_account(cls, subject: str, body: str) -> Optional[str]:
        # Strip out email password example footers before checking body
        cleaned_body = re.split(
            r"How to open the statement|Example Customer Name:",
            body,
            flags=re.IGNORECASE,
        )[0]

        # Priority A: Email Subject (e.g. Account XXXXXXXXXXXXXX60)
        subj_match = cls.SUBJECT_ACCOUNT_PATTERN.search(subject)
        if subj_match:
            digits = subj_match.group(1)
            return digits[-4:] if len(digits) >= 4 else digits

        # Priority B: Term Deposit Table Account Number (e.g. 0624101000001974 -> 1974)
        td_match = cls.TD_TABLE_PATTERN.search(cleaned_body)
        if td_match:
            acc_num = td_match.group(1)
            return acc_num[-4:]

        # Priority C: Primary masked pattern in cleaned body
        body_match = re.search(ParserRegex.ACCOUNT_MASKED_PRIMARY.value, cleaned_body)
        if body_match:
            return body_match.group(1)[-4:]

        # Priority D: Account XXXXX0081 format in body
        acct_match = re.search(
            r"account\s+[xX*]*([0-9]{4})", cleaned_body, re.IGNORECASE
        )
        if acct_match:
            return acct_match.group(1)

        return None

    @classmethod
    def _extract_smart_amount(cls, body: str, subject: str) -> Optional[Decimal]:
        """
        Safely extracts currency amounts from plain text.
        Guarantees protection against InvalidOperation: [<class 'decimal.ConversionSyntax'>].
        """

        def _safe_to_decimal(val_str: str) -> Optional[Decimal]:
            if not val_str:
                return None
            try:
                # 1. Strip commas, currency marks, whitespace
                cleaned = str(val_str).strip().replace(",", "")
                cleaned = re.sub(r"[^\d.-]", "", cleaned)

                if not cleaned or cleaned in {".", "-", "-.", ".-"}:
                    return None

                # 2. Guard against multiple decimal dots
                if cleaned.count(".") > 1:
                    parts = cleaned.split(".")
                    cleaned = "".join(parts[:-1]) + "." + parts[-1]

                dec = Decimal(cleaned)

                # 3. Handle single-digit decimal notation (e.g., 6283.6 -> 6283.60)
                if "." in cleaned and len(cleaned.split(".")[1]) == 1:
                    dec = Decimal(f"{cleaned}0")

                return dec
            except (InvalidOperation, TypeError, ValueError):
                return None

        # A. Handle Loan Intimation
        loan_match = cls.LOAN_OPENED_PATTERN.search(body)
        if loan_match:
            dec = _safe_to_decimal(loan_match.group(2))
            if dec is not None:
                return dec

        # B. Handle Term Deposit Closure Row
        td_match = cls.TD_TABLE_PATTERN.search(body)
        if td_match and td_match.group(4):
            dec = _safe_to_decimal(td_match.group(4))
            if dec is not None:
                return dec

        # C. Standard INR Amount Regex
        amt_match = re.search(
            r"(?:INR|RS\.?|₹)\s*([0-9,]+(?:\.[0-9]{1,2})?)",
            body,
            re.IGNORECASE,
        )
        if amt_match:
            dec = _safe_to_decimal(amt_match.group(1))
            if dec is not None:
                return dec

        return None

    @classmethod
    def _extract_smart_reference(cls, body: str) -> Optional[str]:
        # Check standard UPI RRN or UTR
        rrn_match = re.search(ParserRegex.UPI_RRN.value, body, re.IGNORECASE)
        if rrn_match:
            return rrn_match.group(1)

        # Check IMPS / MOB pattern (e.g. MOB/507710983141/self/IMPS)
        imps_match = cls.IMPS_MOB_PATTERN.search(body)
        if imps_match:
            return imps_match.group(1)

        # Check Term Deposit synthetic anchor from table (e.g. FD-1974)
        td_match = cls.TD_TABLE_PATTERN.search(body)
        if td_match:
            acc = td_match.group(1)
            return f"FD-{acc[-4:]}"

        return None

    @classmethod
    def _extract_bank_txn_date(cls, body: str) -> Optional[str]:
        """Extracts execution date formatted in body (e.g. 'on 18-03-2025')."""
        match = cls.TXN_DATE_PATTERN.search(body)
        if match:
            raw_date = match.group(1).replace("/", "-")
            # Convert 2-digit years to 4-digit if needed
            parts = raw_date.split("-")
            if len(parts) == 3 and len(parts[2]) == 2:
                raw_date = f"{parts[0]}-{parts[1]}-20{parts[2]}"
            return raw_date
        return None

    @classmethod
    def _extract_payee_hint(cls, body: str) -> Optional[str]:
        """Extracts payee entity or flags self/internal transfers."""
        if re.search(r"/(?:self|own account)/", body, re.IGNORECASE):
            return "Self Transfer"
        return None

    @classmethod
    def _extract_balance(cls, body: str) -> Optional[str]:
        match = cls.BALANCE_PATTERN.search(body)
        return match.group(1).replace(",", "") if match else None

    @classmethod
    def _extract_term_deposit_metadata(cls, body: str) -> Dict[str, Any]:
        match = cls.TD_TABLE_PATTERN.search(body)
        if not match:
            return {}

        return {
            "td_account_number": match.group(1),
            "td_open_date": match.group(2),
            "td_renewal_date": match.group(3),
            "td_principal_amount": match.group(4),
            "td_tenure": match.group(5),
            "td_maturity_date": match.group(6),
            "td_total_interest": match.group(7),
            "td_tds_deducted": match.group(8),
        }
