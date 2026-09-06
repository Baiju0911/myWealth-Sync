"""
tracker/emailIngest/parser.py - Production Bank Signal & Stream Tokenizer

Processes incoming bank alerts (Gmail API & iOS SMS) across payment rails.
Uses typed constants from tracker.constants without inline hardcoded literals.
"""

import hashlib
import html
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Dict, Any, Tuple, Optional

from ..models.models import Account as LedgerAccount
from tracker.constants import (
    TxnType,
    PaymentRail,
    IngestTriggers,
    ParserRegex,
    DateFormats,
    TokenCatalog,
    SystemDefaults,
    NarrativeLabels,
)


def parse_rfc_or_iso_date(raw_date_str: str) -> Optional[datetime]:
    """Parses RFC 2822 or ISO 8601 date strings into Datetime objects."""
    if not raw_date_str:
        return None

    if isinstance(raw_date_str, datetime):
        return raw_date_str

    try:
        return parsedate_to_datetime(raw_date_str)
    except Exception:
        pass

    try:
        return datetime.fromisoformat(raw_date_str.replace("Z", "+00:00"))
    except Exception:
        pass

    return None


def clean_html_to_text(raw_html: str) -> str:
    """Strips comments, script/style blocks, unescapes entities, and cleans whitespace."""
    if not raw_html:
        return SystemDefaults.EMPTY_STRING.value

    text = re.sub(
        ParserRegex.HTML_COMMENTS, SystemDefaults.SPACE.value, raw_html, flags=re.DOTALL
    )
    text = re.sub(
        ParserRegex.HTML_HEAD_SCRIPT_STYLE,
        SystemDefaults.SPACE.value,
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = html.unescape(text)
    text = re.sub(
        ParserRegex.HTML_BLOCK_BREAKS,
        "\n",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(ParserRegex.HTML_TAGS, SystemDefaults.SPACE.value, text)

    lines = [line.strip() for line in text.splitlines()]
    non_empty_lines = [
        re.sub(ParserRegex.MULTIPLE_SPACES, SystemDefaults.SPACE.value, line)
        for line in lines
        if line.strip()
    ]
    full_text = SystemDefaults.SPACE.value.join(non_empty_lines)

    # 1. Strip disclaimers, sign-off footers, and SMS block instructions safely
    full_text = re.sub(
        ParserRegex.SIGN_OFF_FOOTER,
        SystemDefaults.EMPTY_STRING.value,
        full_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    full_text = re.sub(
        r"(?:Block\s*A/c\?.*|-?\s*South\s+Indian\s+Bank\s*$)",
        SystemDefaults.EMPTY_STRING.value,
        full_text,
        flags=re.IGNORECASE,
    )

    # 2. Strip salutations
    full_text = re.sub(
        ParserRegex.GREETING_PREAMBLE,
        SystemDefaults.EMPTY_STRING.value,
        full_text.strip(),
        flags=re.IGNORECASE,
    ).strip()

    return full_text


def clean_narration(raw_text: str) -> str:
    """Cleans raw bank narration strings into readable vendor names using stopword set."""
    if not raw_text:
        return SystemDefaults.VENDOR.value

    text = re.sub(
        ParserRegex.GREETING_PREAMBLE,
        SystemDefaults.EMPTY_STRING.value,
        raw_text.strip(),
        flags=re.IGNORECASE,
    )
    text = text.upper().strip()

    words = text.split()
    filtered = [w for w in words if w not in TokenCatalog.VENDOR_CLEAN_STOPWORDS]
    cleaned = SystemDefaults.SPACE.value.join(filtered)
    cleaned = re.sub(ParserRegex.NON_ALPHANUMERIC, SystemDefaults.SPACE.value, cleaned)
    cleaned = SystemDefaults.SPACE.value.join(cleaned.split())
    return cleaned if cleaned else SystemDefaults.VENDOR.value


def resolve_account_and_bank(
    raw_account: Optional[str], body_text: str, sender: str = "", default_bank: str = ""
) -> Tuple[Optional[str], str, str, dict]:
    account_id = None
    account_display_name = NarrativeLabels.ACCOUNT_NOT_FOUND.value
    bank_name = default_bank or SystemDefaults.BANK.value
    account_meta = {}

    # 1. Primary Lookup via Backend Accounts Database
    if raw_account and LedgerAccount is not None:
        raw_digits = re.sub(
            ParserRegex.NON_DIGITS, SystemDefaults.EMPTY_STRING.value, str(raw_account)
        )
        try:
            acc = None
            if len(raw_digits) > 4:
                acc = LedgerAccount.objects.filter(account_number=raw_digits).first()
            if not acc and len(raw_digits) >= 4:
                acc = LedgerAccount.objects.filter(
                    account_number__endswith=raw_digits[-4:]
                ).first()

            if acc:
                account_id = str(acc.id)
                account_display_name = (
                    getattr(acc, "name", None)
                    or getattr(acc, "account_name", None)
                    or f"A/c {raw_digits[-4:]}"
                )

                resolved_bank_from_db = None
                if hasattr(acc, "bank") and acc.bank:
                    bank_obj = acc.bank
                    resolved_bank_from_db = getattr(
                        bank_obj,
                        "bank_name",
                        getattr(bank_obj, "name", getattr(bank_obj, "title", None)),
                    )

                if (
                    not resolved_bank_from_db
                    and hasattr(acc, "bank_id")
                    and acc.bank_id
                ):
                    try:
                        from ..models.models import Bank

                        bank_record = Bank.objects.filter(id=acc.bank_id).first()
                        if bank_record:
                            resolved_bank_from_db = getattr(
                                bank_record,
                                "bank_name",
                                getattr(
                                    bank_record,
                                    "name",
                                    getattr(bank_record, "title", None),
                                ),
                            )
                    except Exception:
                        pass

                if not resolved_bank_from_db:
                    resolved_bank_from_db = getattr(acc, "bank_name", None) or getattr(
                        acc, "institution_name", None
                    )

                if not resolved_bank_from_db and account_display_name:
                    acc_name_upper = account_display_name.upper()
                    if "SIB" in acc_name_upper or "SOUTH INDIAN" in acc_name_upper:
                        resolved_bank_from_db = "SOUTH INDIAN BANK"
                    elif "SBI" in acc_name_upper or "STATE BANK" in acc_name_upper:
                        resolved_bank_from_db = "STATE BANK OF INDIA"
                    elif "FED" in acc_name_upper or "FEDERAL" in acc_name_upper:
                        resolved_bank_from_db = "FEDERAL BANK"
                    elif "HDFC" in acc_name_upper:
                        resolved_bank_from_db = "HDFC BANK"
                    elif "ICICI" in acc_name_upper:
                        resolved_bank_from_db = "ICICI BANK"

                if resolved_bank_from_db:
                    bank_name = str(resolved_bank_from_db).strip().upper()

                account_meta = {
                    "account_id": account_id,
                    "account_name": account_display_name,
                    "account_number": getattr(acc, "account_number", raw_digits),
                    "bank_name": bank_name,
                }
            else:
                account_meta = {
                    "unlinked_account": raw_digits,
                    "status": "ACCOUNT_NOT_FOUND",
                }
        except Exception as e:
            print(f"⚠️ Account ORM Query Error: {e}")

    # 2. Sender Identification
    if bank_name == SystemDefaults.BANK.value or not bank_name:
        sender_upper = str(sender).upper()
        if "SIB" in sender_upper or "SOUTH INDIAN BANK" in sender_upper:
            bank_name = "SOUTH INDIAN BANK"
        elif "SBI" in sender_upper or "STATE BANK" in sender_upper:
            bank_name = "STATE BANK OF INDIA"
        elif "HDFC" in sender_upper:
            bank_name = "HDFC BANK"
        elif "ICICI" in sender_upper:
            bank_name = "ICICI BANK"
        elif "FED" in sender_upper or "FEDERAL" in sender_upper:
            bank_name = "FEDERAL BANK"

    # 3. Body Text Fallback
    if bank_name == SystemDefaults.BANK.value or not bank_name:
        body_upper = body_text.upper()
        if "SOUTH INDIAN BANK" in body_upper or re.search(r"\bSIB\b", body_upper):
            bank_name = "SOUTH INDIAN BANK"
        elif "STATE BANK OF INDIA" in body_upper or re.search(r"\bSBI\b", body_upper):
            bank_name = "STATE BANK OF INDIA"

    return account_id, account_display_name, bank_name, account_meta


def clean_sms_merchant(
    raw_merchant: str,
    upi_ref: Optional[str] = None,
    payment_rail: str = PaymentRail.UPI.value,
) -> str:
    """Strips noisy SMS debit notifications and returns clean beneficiary or fallback ID."""
    fallback_ref = upi_ref or NarrativeLabels.FALLBACK_REF.value
    default_direct = NarrativeLabels.SLASH_NARRATION_TEMPLATE.value.format(
        payment_rail, fallback_ref, NarrativeLabels.FALLBACK_DIRECT_PAYMENT.value
    )

    if not raw_merchant:
        return default_direct

    cleaned = raw_merchant.strip()

    # Detect if the merchant string is purely raw alert notification noise
    if re.search(ParserRegex.SMS_DEBIT_ALERT_RAW_NOISE, cleaned, re.IGNORECASE):
        return default_direct

    # Strip amount prefix and trailing single character artifacts
    cleaned = re.sub(
        ParserRegex.SMS_PREFIX_DEBIT_AMOUNT,
        SystemDefaults.EMPTY_STRING.value,
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    cleaned = re.sub(
        ParserRegex.DANGLING_SINGLE_CHAR_SUFFIX,
        SystemDefaults.EMPTY_STRING.value,
        cleaned,
    ).strip()

    cleaned_upper = cleaned.upper()
    if (
        not cleaned
        or cleaned_upper in TokenCatalog.GENERIC_MERCHANT_NOISE_WORDS
        or cleaned_upper
        in [
            "SOUTH INDIAN BANK",
            "STATE BANK OF INDIA",
            "FEDERAL BANK",
            "HDFC BANK",
            "ICICI BANK",
            "SIB",
            "SBI",
        ]
    ):
        return default_direct

    return clean_narration(cleaned)


def extract_stream_identifiers(raw_text: str) -> Dict[str, Any]:
    """
    Extracts payment rail, reference numbers, auth codes, and counterparty tokens.
    Guards against false-positive slash splitting caused by 'A/c' or contact numbers.
    """
    if not raw_text:
        return {
            "rail": PaymentRail.UNKNOWN.value,
            "reference_id": None,
            "auth_code": None,
            "extracted_merchant": None,
            "is_self_transfer": False,
        }

    text = SystemDefaults.SPACE.value.join(
        str(raw_text).replace("\n", SystemDefaults.SPACE.value).split()
    )
    text_upper = text.upper()

    meta = {
        "rail": PaymentRail.UNKNOWN.value,
        "reference_id": None,
        "auth_code": None,
        "extracted_merchant": None,
        "is_self_transfer": any(
            trigger.upper() in text_upper for trigger in IngestTriggers.SELF_TRANSFER
        ),
    }

    # 1. Direct Pattern Match: Info - UPI/BANK_OR_HANDLE/REF_OR_RRN/MERCHANT...
    info_slash_match = re.search(ParserRegex.INFO_SLASH_STREAM, text, re.IGNORECASE)
    if info_slash_match:
        rail_tok, _, ref_tok, merchant_tok = info_slash_match.groups()
        meta["rail"] = rail_tok.strip().upper()
        meta["reference_id"] = ref_tok.strip()

        clean_m = re.sub(
            ParserRegex.STREAM_STRIP_TAIL,
            SystemDefaults.EMPTY_STRING.value,
            merchant_tok,
            flags=re.IGNORECASE,
        ).strip()
        meta["extracted_merchant"] = clean_m
        return meta

    # 2. Delimited Slash Streams (Only if an actual stream context exists, ignoring 'A/c' and 'Call/SMS')
    normalized_for_stream = re.sub(r"\bA/C\b", "ACCT", text, flags=re.IGNORECASE)
    normalized_for_stream = re.sub(
        r"Call\w*/SMS\w*", "CONTACT", normalized_for_stream, flags=re.IGNORECASE
    )

    # Must contain at least 2 slashes to qualify as a structured banking stream (e.g. MOB/REF/MERCHANT)
    if normalized_for_stream.count(SystemDefaults.SLASH.value) >= 2:
        tokens = [
            t.strip()
            for t in normalized_for_stream.split(SystemDefaults.SLASH.value)
            if t.strip()
        ]

        # Check NACH mandates
        if any(PaymentRail.NACH.value in t.upper() for t in tokens):
            meta["rail"] = PaymentRail.NACH.value
            for idx, tok in enumerate(tokens):
                if PaymentRail.NACH.value in tok.upper():
                    if len(tokens) > idx + 1:
                        meta["reference_id"] = tokens[idx + 1]
                    if len(tokens) > idx + 2:
                        meta["extracted_merchant"] = tokens[idx + 2]
                    break
            return meta

        # Detect Rail and Reference IDs
        for t in tokens:
            t_u = t.upper()
            if re.fullmatch(ParserRegex.TWELVE_DIGIT_MATCH, t):
                meta["reference_id"] = t
            elif PaymentRail.contains(t_u):
                meta["rail"] = t_u
            elif "OWN ACCOUNT" in t_u or "SELF" in t_u:
                meta["is_self_transfer"] = True
            elif (
                re.fullmatch(ParserRegex.CODE_TOKEN_MATCH, t_u)
                and t_u not in TokenCatalog.IGNORE_SLASH_TOKENS
                and meta["rail"] == PaymentRail.UNKNOWN.value
            ):
                meta["rail"] = t_u

        # Extract merchant only if it is not alert noise
        for t in tokens:
            clean_t = re.sub(
                ParserRegex.STREAM_STRIP_TAIL,
                SystemDefaults.EMPTY_STRING.value,
                t,
                flags=re.IGNORECASE,
            ).strip()

            clean_t_upper = clean_t.upper()
            is_alert_noise = bool(
                re.search(r"^(?:UPI\s+)?DEBIT|BAL:|CONTACT|ACCT", clean_t_upper)
                or any(
                    noise in clean_t_upper
                    for noise in ["SOUTH INDIAN BANK", "BLOCK A/C"]
                )
            )

            if (
                len(clean_t) > 3
                and not is_alert_noise
                and not re.fullmatch(ParserRegex.ALL_DIGITS_MATCH, clean_t)
                and not PaymentRail.contains(clean_t_upper)
                and clean_t_upper not in TokenCatalog.IGNORE_SLASH_TOKENS
                and not meta["extracted_merchant"]
            ):
                meta["extracted_merchant"] = clean_t

        if meta["reference_id"] or meta["rail"] != PaymentRail.UNKNOWN.value:
            return meta

    # 3. UPI Reference (12 digits)
    if not meta["reference_id"]:
        upi_match = re.search(ParserRegex.UPI_RRN, text, re.IGNORECASE)
        if upi_match:
            meta["rail"] = PaymentRail.UPI.value
            meta["reference_id"] = upi_match.group(1)

    # 4. NEFT / RTGS (UTR Numbers)
    if not meta["reference_id"]:
        neft_match = re.search(ParserRegex.NEFT_UTR, text, re.IGNORECASE)
        if neft_match:
            meta["rail"] = (
                PaymentRail.NEFT.value
                if PaymentRail.NEFT.value in neft_match.group(0).upper()
                else PaymentRail.RTGS.value
            )
            meta["reference_id"] = neft_match.group(1)

    # 5. POS / Card Swipes (Auth Code)
    auth_match = re.search(ParserRegex.POS_AUTH, text, re.IGNORECASE)
    if auth_match:
        meta["rail"] = PaymentRail.POS.value
        meta["auth_code"] = auth_match.group(1)
        if not meta["reference_id"]:
            meta["reference_id"] = meta["auth_code"]

    return meta


def parse_term_deposit_advice(
    clean_body: str, sender: str = "", inherited_bank: str = ""
) -> Optional[dict]:
    clean_lower = clean_body.lower()

    if not any(
        trigger.lower() in clean_lower for trigger in IngestTriggers.TERM_DEPOSIT
    ):
        return None

    # 1. Resolve Bank & Full Account Number
    acct_match = re.search(ParserRegex.ACCOUNT_NUMBER_STRICT, clean_body)
    full_acct = acct_match.group(1) if acct_match else None
    last4 = full_acct[-4:] if full_acct else None

    acc_id, acc_name, resolved_bank, meta = resolve_account_and_bank(
        full_acct, clean_body, sender=sender, default_bank=inherited_bank
    )

    result = {
        "bank_name": resolved_bank,
        "amount": None,
        "balance": None,
        "txn_type": TxnType.CREDIT.value,
        "merchant": f"{resolved_bank} {NarrativeLabels.FD_PROCEEDS_SUFFIX.value}".strip(),
        "account_last4": last4 or (full_acct[-4:] if full_acct else None),
        "account_display_name": acc_name,
        "account_id": acc_id,
        "upi_ref": f"{NarrativeLabels.UPI_REF_PREFIX.value}{last4 or NarrativeLabels.PROCEEDS.value}",
        "date": None,
        "full_datetime": None,
        "full_narration": NarrativeLabels.TD_NARRATION_TEMPLATE.value.format(
            full_acct or SystemDefaults.NOT_AVAILABLE.value
        ),
        "txn_fingerprint": None,
        "is_parsed": False,
        "is_noise": False,
        "payment_rail": PaymentRail.INTERNAL_TRANSFER.value,
        "is_self_transfer": True,
        "metadata_json": {
            "is_term_deposit": True,
            "full_account_number": full_acct,
            "account_match": meta,
        },
    }

    # 2. Extract Date
    date_match = re.search(ParserRegex.TD_DATE_CLOSED, clean_body, re.IGNORECASE)
    if not date_match:
        date_match = re.search(ParserRegex.DATE_GENERAL, clean_body)

    if date_match:
        raw_cdate = date_match.group(1).replace("/", "-")
        try:
            result["date"] = datetime.strptime(
                raw_cdate, DateFormats.DMY_FOUR.value
            ).strftime(DateFormats.ISO_DATE.value)
            result["full_datetime"] = f"{result['date']}{DateFormats.TIME_ZERO.value}"
        except ValueError:
            result["date"] = datetime.now().strftime(DateFormats.ISO_DATE.value)
    else:
        result["date"] = datetime.now().strftime(DateFormats.ISO_DATE.value)

    # 3. Extract Principal Amount
    amt_match = re.search(ParserRegex.TD_PRINCIPAL_IN_TABLE, clean_body, re.IGNORECASE)
    if not amt_match:
        amt_match = re.search(r"\b(\d{5,8})\b", clean_body)

    if amt_match:
        try:
            raw_amt = amt_match.group(1).replace(SystemDefaults.COMMA.value, "")
            parsed_amt = float(raw_amt)
            if parsed_amt > 0:
                result["amount"] = f"{parsed_amt:.2f}"
                result["is_parsed"] = True
        except ValueError:
            pass

    # 4. Fingerprint
    b_key = result["bank_name"]
    acct_key = full_acct or SystemDefaults.UNREGISTERED.value
    amt_key = result["amount"] or SystemDefaults.ZERO_AMOUNT.value
    dt_key = result["date"] or SystemDefaults.NODATE.value
    raw_key = NarrativeLabels.TD_FINGERPRINT_PREFIX.value.format(
        b_key, acct_key, amt_key, dt_key
    ).upper()
    result["txn_fingerprint"] = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    return result


def parse_bank_email_body(
    body_text: str, sender: str = "", inherited_bank: str = ""
) -> dict:
    """
    Parses bank transaction emails and SMS alerts across institutions.
    Extracts debit/credit, amounts, masked account numbers, dynamic slash streams,
    SMS text patterns, RRN/reference codes, and resolves ledger accounts.
    """
    result = {
        "bank_name": inherited_bank or SystemDefaults.BANK.value,
        "amount": None,
        "balance": None,
        "txn_type": TxnType.DEBIT.value,
        "merchant": SystemDefaults.VENDOR.value,
        "account_last4": None,
        "account_id": None,
        "account_display_name": NarrativeLabels.ACCOUNT_NOT_FOUND.value,
        "upi_ref": None,
        "date": None,
        "full_datetime": None,
        "full_narration": None,
        "txn_fingerprint": None,
        "is_parsed": False,
        "is_noise": False,
        "payment_rail": PaymentRail.UNKNOWN.value,
        "is_self_transfer": False,
        "metadata_json": {},
    }

    if not body_text:
        return result

    clean_body = clean_html_to_text(body_text)

    # 0. Term Deposit Check
    td_result = parse_term_deposit_advice(
        clean_body, sender=sender, inherited_bank=inherited_bank
    )
    if td_result and td_result.get("is_parsed"):
        return td_result

    # 1. Non-Transactional Noise Filter
    clean_lower = clean_body.lower()
    if any(kw in clean_lower for kw in IngestTriggers.AMB_NOISE):
        result["txn_type"] = TxnType.NOISE.value
        result["merchant"] = NarrativeLabels.AMB_NOTICE_MERCHANT.value
        result["full_narration"] = NarrativeLabels.AMB_NOTICE_NARRATION.value
        result["is_noise"] = True
        result["is_parsed"] = False
        return result

    # 2. Transaction Direction
    if any(trig in clean_lower for trig in IngestTriggers.TXN_CREDIT):
        result["txn_type"] = TxnType.CREDIT.value
    elif any(trig in clean_lower for trig in IngestTriggers.TXN_DEBIT):
        result["txn_type"] = TxnType.DEBIT.value

    # 3. Amount Extraction
    amt_match = re.search(ParserRegex.AMOUNT_INR_CAPTURE, clean_body, re.IGNORECASE)
    if amt_match:
        try:
            raw_amt = amt_match.group(1).replace(SystemDefaults.COMMA.value, "").strip()
            result["amount"] = f"{float(raw_amt):.2f}"
        except ValueError:
            pass

    # 4. Running Balance Extraction
    bal_match = re.search(ParserRegex.BALANCE_CAPTURE, clean_body, re.IGNORECASE)
    if bal_match:
        try:
            raw_bal = bal_match.group(1).replace(SystemDefaults.COMMA.value, "").strip()
            result["balance"] = f"{float(raw_bal):.2f}"
        except ValueError:
            pass

    # 5. Masked Account Extraction
    acc_match = re.search(ParserRegex.ACCOUNT_MASKED_PRIMARY, clean_body)
    if not acc_match:
        acc_match = re.search(
            ParserRegex.ACCOUNT_MASKED_SECONDARY, clean_body, re.IGNORECASE
        )

    raw_account_captured = None
    if acc_match:
        raw_account_captured = acc_match.group(1)
        result["account_last4"] = raw_account_captured[-4:]

    # 6. Resolve Account & Bank
    acc_id, acc_name, resolved_bank, meta = resolve_account_and_bank(
        raw_account_captured or result["account_last4"],
        clean_body,
        sender=sender,
        default_bank=inherited_bank,
    )
    result["bank_name"] = resolved_bank
    result["account_id"] = acc_id
    result["account_display_name"] = acc_name
    if meta:
        result["metadata_json"]["account_match"] = meta

    # 7. Date Parsing
    date_match = re.search(ParserRegex.DATE_GENERAL, clean_body)
    if date_match:
        raw_date_str = date_match.group(1)
        try:
            parts = raw_date_str.replace("/", "-").split("-")
            if len(parts) == 3:
                day, month, year = parts[0], parts[1], parts[2]
                if len(year) == 2:
                    year = f"20{year}"
                result["date"] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        except Exception:
            result["date"] = datetime.now().strftime(DateFormats.ISO_DATE.value)
    else:
        result["date"] = datetime.now().strftime(DateFormats.ISO_DATE.value)

    # 8. Universal Stream Tokenizer (Handles Beneficiary Pattern & SIB Slash Stream)
    sms_upi_match = re.search(
        ParserRegex.SMS_BENEFICIARY_VIA, clean_body, re.IGNORECASE
    )

    if sms_upi_match:
        result["payment_rail"] = sms_upi_match.group(1).upper()
        raw_merchant_cand = sms_upi_match.group(2).strip()

        ref_match = re.search(ParserRegex.UPI_RRN, clean_body, re.IGNORECASE)
        if ref_match:
            result["upi_ref"] = ref_match.group(1)

        result["merchant"] = clean_sms_merchant(
            raw_merchant_cand,
            upi_ref=result["upi_ref"],
            payment_rail=result["payment_rail"],
        )

        result["full_narration"] = (
            NarrativeLabels.SLASH_NARRATION_TEMPLATE.value.format(
                result["payment_rail"],
                result["upi_ref"] or NarrativeLabels.FALLBACK_REF.value,
                result["merchant"],
            )
        )
    else:
        info_idx = clean_body.lower().find("info")
        if info_idx != -1 and SystemDefaults.SLASH.value in clean_body[info_idx:]:
            stream_snippet = clean_body[info_idx:]
            stream_snippet = re.sub(
                ParserRegex.STREAM_STRIP_TAIL,
                SystemDefaults.EMPTY_STRING.value,
                stream_snippet,
                flags=re.IGNORECASE,
            ).strip()

            after_prefix = re.sub(
                ParserRegex.INFO_PREFIX_STRIP,
                SystemDefaults.EMPTY_STRING.value,
                stream_snippet,
                flags=re.IGNORECASE,
            ).strip()
            tokens = [
                t.strip()
                for t in after_prefix.split(SystemDefaults.SLASH.value)
                if t.strip()
            ]

            if len(tokens) >= 1:
                cand_rail = tokens[0].upper()
                if (
                    PaymentRail.contains(cand_rail)
                    or cand_rail in TokenCatalog.INTERMEDIARY_RAIL_CODES
                ):
                    result["payment_rail"] = (
                        PaymentRail.IMPS.value if cand_rail == "MOB" else cand_rail
                    )

            # Filter tokens: timestamp vs 12-digit UPI RRN vs IMPS/NEFT
            for t in tokens:
                if len(t) == 14 and t.startswith(TokenCatalog.YEAR_PREFIXES_TIMESTAMP):
                    result["metadata_json"]["bank_txn_timestamp"] = t
                    continue

                if re.fullmatch(ParserRegex.TWELVE_DIGIT_MATCH, t):
                    result["upi_ref"] = t
                    break
                elif re.fullmatch(r"[A-Za-z0-9]{8,16}", t) and not t.isalpha():
                    result["upi_ref"] = t
                    break

            is_own_account = any(
                "OWN ACCOUNT" in t.upper() or "SELF" in t.upper() for t in tokens
            )
            if is_own_account:
                result["is_self_transfer"] = True
                result["merchant"] = NarrativeLabels.OWN_ACCOUNT_TRANSFER.value
            elif result["upi_ref"] and result["upi_ref"] in tokens:
                ref_idx = tokens.index(result["upi_ref"])
                if len(tokens) > ref_idx + 1:
                    cand_m = tokens[ref_idx + 1]
                    if PaymentRail.contains(cand_m.upper()):
                        cand_m = tokens[ref_idx - 1] if ref_idx > 0 else cand_m
                    cand_m = re.sub(
                        ParserRegex.MERCHANT_NOISE_PHRASES,
                        SystemDefaults.EMPTY_STRING.value,
                        cand_m,
                        flags=re.IGNORECASE,
                    ).strip()
                    if cand_m:
                        result["merchant"] = clean_sms_merchant(
                            cand_m,
                            upi_ref=result["upi_ref"],
                            payment_rail=result["payment_rail"],
                        )
            elif len(tokens) >= 3:
                if not tokens[2].isdigit():
                    result["merchant"] = clean_sms_merchant(
                        tokens[2],
                        upi_ref=result["upi_ref"],
                        payment_rail=result["payment_rail"],
                    )

            result["full_narration"] = (
                NarrativeLabels.SLASH_NARRATION_TEMPLATE.value.format(
                    result["payment_rail"],
                    result["upi_ref"] or NarrativeLabels.FALLBACK_REF.value,
                    result["merchant"],
                )
            )

    # 9. Fallback for SMS alerts without standard stream formats (Handles SIB debit micro-alerts)
    if (
        result["merchant"]
        in [
            SystemDefaults.VENDOR.value,
            "SOUTH INDIAN BANK",
            result["bank_name"],
        ]
        or "UPI DEBIT" in (result["merchant"] or "").upper()
    ):
        # Look for explicit payee markers in SMS (e.g., "to <Merchant>", "at <Merchant>")
        sms_merchant_match = re.search(
            r"\b(?:to|at)\s+([A-Za-z][A-Za-z0-9\s\.\-_&]{2,30}?)(?:\s+on|\s+Ref|\s+RRN|\.|$)",
            clean_body,
            re.IGNORECASE,
        )
        if sms_merchant_match:
            cand = sms_merchant_match.group(1).strip()
            if not any(
                b in cand.upper() for b in ["SOUTH INDIAN", "BANK", "CALL", "SMS"]
            ):
                result["merchant"] = clean_sms_merchant(
                    cand,
                    upi_ref=result["upi_ref"],
                    payment_rail=result["payment_rail"],
                )
            else:
                result["merchant"] = NarrativeLabels.FALLBACK_DIRECT_PAYMENT.value
        else:
            result["merchant"] = NarrativeLabels.FALLBACK_DIRECT_PAYMENT.value

        # Re-sync full narration
        result["full_narration"] = (
            NarrativeLabels.SLASH_NARRATION_TEMPLATE.value.format(
                (
                    result["payment_rail"]
                    if result["payment_rail"] != PaymentRail.UNKNOWN.value
                    else PaymentRail.UPI.value
                ),
                result["upi_ref"] or NarrativeLabels.FALLBACK_REF.value,
                result["merchant"],
            )
        )

    # 10. Fallback to generic stream identifiers if rail or upi_ref is missing
    if result["payment_rail"] == PaymentRail.UNKNOWN.value or not result["upi_ref"]:
        stream_meta = extract_stream_identifiers(clean_body)
        if result["payment_rail"] == PaymentRail.UNKNOWN.value:
            result["payment_rail"] = stream_meta.get("rail", PaymentRail.UNKNOWN.value)
        result["is_self_transfer"] = result["is_self_transfer"] or stream_meta.get(
            "is_self_transfer", False
        )

        if not result["upi_ref"] and stream_meta.get("reference_id"):
            ref_val = stream_meta["reference_id"]
            if not (
                len(ref_val) == 14
                and ref_val.startswith(TokenCatalog.YEAR_PREFIXES_TIMESTAMP)
            ):
                result["upi_ref"] = ref_val

        if result["merchant"] in [
            SystemDefaults.VENDOR.value,
            NarrativeLabels.FALLBACK_DIRECT_PAYMENT.value,
        ] and stream_meta.get("extracted_merchant"):
            result["merchant"] = clean_sms_merchant(
                stream_meta["extracted_merchant"],
                upi_ref=result["upi_ref"],
                payment_rail=result["payment_rail"],
            )

    # 11. Deterministic Transaction Fingerprint
    if result["amount"]:
        result["is_parsed"] = True
        acc = result["account_last4"] or SystemDefaults.ACCOUNT_FALLBACK_LAST4.value
        ref = result["upi_ref"] or f"TXN_{result['date']}_{result['amount']}"

        raw_key = NarrativeLabels.STANDARD_FINGERPRINT_PREFIX.value.format(
            result["bank_name"], acc, result["amount"], ref
        ).upper()
        result["txn_fingerprint"] = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    return result
