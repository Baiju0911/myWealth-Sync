# tracker/emailIngest/parser.py
import hashlib
import html
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from ..models.models import Account as LedgerAccount


def clean_html_to_text(raw_html: str) -> str:
    """Strips HTML tags, unescapes entities, and normalizes space."""
    if not raw_html:
        return ""
    text = html.unescape(raw_html)
    text = re.sub(r"<(br|p|div|tr|td|th)[^>]*>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\r", " ").replace("\n", " ")
    return " ".join(text.split())


def clean_narration(raw_text: str) -> str:
    """Cleans raw bank narration strings into readable vendor names."""
    if not raw_text:
        return "UNKNOWN VENDOR"
    text = raw_text.upper().strip()
    text = re.sub(
        r"\b(PVT|LTD|LIMITED|INC|PAY|INFO|PRIVATE|NO REMARK|REMARK|CARD|ON|FROM|YOUR|ACCOUNT|A/C)\b",
        "",
        text,
    )
    text = re.sub(r"[^A-Z0-9\s]", " ", text)
    cleaned = " ".join(text.split())
    return cleaned if cleaned else "UNKNOWN VENDOR"


def parse_rfc_or_iso_date(raw_date_str: str):
    """
    Parses RFC 2822 or ISO 8601 date strings into naive or aware Datetime objects.
    """
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


def resolve_account_and_bank(last4: str, body_text: str, sender: str = "") -> tuple:
    """Queries Django ORM for an account matching account_number=last4."""
    account_id = None
    account_name = None
    bank_name = "UNKNOWN BANK"
    account_meta = {}

    if last4 and LedgerAccount is not None:
        try:
            acc = LedgerAccount.objects.filter(account_number__endswith=last4).first()
            if acc:
                account_id = str(acc.id)
                account_name = getattr(acc, "name", None)

                account_meta = {
                    "account_id": account_id,
                    "account_name": account_name,
                    "account_type": getattr(acc, "account_type", None),
                    "account_number": getattr(acc, "account_number", last4),
                    "ifsc_code": getattr(acc, "ifsc_code", None),
                    "branch_name": getattr(acc, "branch_name", None),
                    "address": getattr(acc, "address", None),
                    "bank_id": str(getattr(acc, "bank_id", "")),
                }

                if hasattr(acc, "bank") and acc.bank:
                    bank_obj = acc.bank
                    resolved_name = getattr(
                        bank_obj,
                        "bank_name",
                        getattr(bank_obj, "name", getattr(bank_obj, "title", None)),
                    )
                    if resolved_name:
                        bank_name = str(resolved_name).upper()

                if bank_name == "UNKNOWN BANK":
                    acc_num = getattr(acc, "account_number", "")
                    if "SIB" in (account_name or "").upper() or acc_num in [
                        "0060",
                        "0081",
                        "0049",
                    ]:
                        bank_name = "SOUTH INDIAN BANK"
                    elif "SBI" in (account_name or "").upper() or acc_num in [
                        "9418",
                        "4250",
                    ]:
                        bank_name = "STATE BANK OF INDIA"

        except Exception as e:
            print(f"⚠️ Account ORM Query Error: {e}")

    if bank_name == "UNKNOWN BANK":
        combined_text = f"{sender} {body_text}"
        bank_signoff_match = re.search(
            r"[-–—\s]+([A-Za-z\s]+Bank)\b", body_text, re.IGNORECASE
        )
        if bank_signoff_match:
            bank_name = bank_signoff_match.group(1).strip().upper()
        elif re.search(r"SOUTH\s+INDIAN\s+BANK|\bSIB\b", combined_text, re.IGNORECASE):
            bank_name = "SOUTH INDIAN BANK"
        elif re.search(
            r"STATE\s+BANK\s+OF\s+INDIA|\bSBI\b", combined_text, re.IGNORECASE
        ):
            bank_name = "STATE BANK OF INDIA"
        elif re.search(r"\bHDFC\b", combined_text, re.IGNORECASE):
            bank_name = "HDFC BANK"
        elif re.search(r"\bYES\s+BANK\b|\bYESB\b", combined_text, re.IGNORECASE):
            bank_name = "YES BANK"

    return account_id, account_name, bank_name, account_meta


def parse_bank_email_body(body_text: str, sender: str = "") -> dict:
    """Parses bank email/SMS body text and queries account tables cleanly."""
    result = {
        "bank_name": "UNKNOWN BANK",
        "amount": None,
        "balance": None,
        "txn_type": "DEBIT",
        "merchant": "UNKNOWN VENDOR",
        "account_last4": None,
        "upi_ref": None,
        "date": None,
        "full_datetime": None,
        "full_narration": None,
        "txn_fingerprint": None,
        "is_parsed": False,
        "metadata_json": {},
    }

    print("\n" + "=" * 60)
    print("DEBUG RAW BODY RECEIVED:")
    print(repr(body_text[:300]) if body_text else "EMPTY")

    if not body_text:
        print("❌ Body text is EMPTY!")
        print("=" * 60 + "\n")
        return result

    clean_body = (
        clean_html_to_text(body_text)
        if "clean_html_to_text" in globals()
        else body_text.strip()
    )

    print("\nDEBUG CLEAN BODY TEXT:")
    print(clean_body[:300])

    # 1. Txn Type Extraction (Credit vs Debit)
    if re.search(
        r"\b(credited|credit|received|deposited|inward)\b", clean_body, re.IGNORECASE
    ):
        result["txn_type"] = "CREDIT"
    elif re.search(
        r"\b(spent|debited|debit|paid|withdrawn|outward)\b", clean_body, re.IGNORECASE
    ):
        result["txn_type"] = "DEBIT"

    # 2. Amount Extraction
    amt_match = re.search(
        r"(?:INR\s*|RS\.?|₹)\s*(?:RS\.?\s*)?([\d,]+(?:\.\d{1,2})?)",
        clean_body,
        re.IGNORECASE,
    )
    if amt_match:
        try:
            raw_amt = amt_match.group(1).replace(",", "")
            result["amount"] = f"{float(raw_amt):.2f}"
        except ValueError:
            pass

    # 3. Balance Extraction (Matches: "Bal:Rs.6214.09", "Bal: 6214.09", "Balance Rs 5000.00")
    bal_match = re.search(
        r"\bBal(?:ance)?\s*[:\s]*\s*(?:INR\s*|RS\.?|₹)?\s*([\d,]+(?:\.\d{1,2})?)",
        clean_body,
        re.IGNORECASE,
    )
    if bal_match:
        try:
            raw_bal = bal_match.group(1).replace(",", "")
            result["balance"] = f"{float(raw_bal):.2f}"
        except ValueError:
            pass

    # 4. Account Last 4 Digits Extraction
    acc_match = re.search(
        r"(?:account|a/c|card|ac|ending|[xX*]{1,})\s*(?:no\.?|number)?\s*[:\s]*([xX*]*\d{4}|\d{4})",
        clean_body,
        re.IGNORECASE,
    )
    if acc_match:
        digits = re.sub(r"\D", "", acc_match.group(1))
        if len(digits) >= 4:
            result["account_last4"] = digits[-4:]

    # 5. DB Account Lookup & Dynamic Bank Resolution
    acc_id, acc_name, resolved_bank, meta = resolve_account_and_bank(
        result["account_last4"], clean_body, sender
    )
    result["bank_name"] = resolved_bank
    if meta:
        result["metadata_json"]["account_match"] = meta

    # 6. Merchant & UPI RRN Extraction
    upi_slash_match = re.search(
        r"UPI/([A-Za-z0-9]+)/(\d{12})/([^/\n\.]+)", clean_body, re.IGNORECASE
    )
    rrn_match = re.search(
        r"(?:RRN[:\s]*|Ref[:\s]*|UPI[:\s]*|Ref\s+No[:\s]*)(\d{12})",
        clean_body,
        re.IGNORECASE,
    )
    at_merchant_match = re.search(
        r"\bat\s+([A-Za-z0-9\s\.\&\-]+?)(?=\s+on|\s+ref|\s+info|\.|$)",
        clean_body,
        re.IGNORECASE,
    )
    vpa_match = re.search(
        r"(?:by|to)\s+(?:VPA\s+)?([A-Za-z0-9\.\-_]+@[A-Za-z0-9]+)",
        clean_body,
        re.IGNORECASE,
    )

    if upi_slash_match:
        result["upi_ref"] = upi_slash_match.group(2)
        raw_vendor = upi_slash_match.group(3)
        raw_vendor = re.sub(
            r"\s+on\s+\d{2}-\d{2}-\d{2,4}.*", "", raw_vendor, flags=re.IGNORECASE
        ).strip()
        result["merchant"] = clean_narration(raw_vendor)
        result["full_narration"] = (
            f"UPI/{upi_slash_match.group(1)}/{result['upi_ref']}/{result['merchant']}"
        )
    elif rrn_match:
        result["upi_ref"] = rrn_match.group(1)
        if at_merchant_match:
            raw_vendor = at_merchant_match.group(1).strip()
            result["merchant"] = clean_narration(raw_vendor)
        elif result["txn_type"] == "CREDIT":
            result["merchant"] = "INWARD UPI TRANSFER"
        else:
            result["merchant"] = "UPI Transfer"

        result["full_narration"] = (
            f"UPI RRN: {result['upi_ref']} | {result['merchant']}"
        )
    elif vpa_match:
        extracted_vpa = vpa_match.group(1).lower()
        result["merchant"] = extracted_vpa
        result["full_narration"] = f"VPA: {extracted_vpa}"
    else:
        if "UPI" in clean_body.upper():
            result["merchant"] = "UPI Transfer"
        elif result["bank_name"] != "UNKNOWN BANK":
            result["merchant"] = result["bank_name"]

        result["full_narration"] = clean_body[:255]

    # 7. Extract Full Datetime vs Date Only
    dt_match = re.search(r"\b(\d{2}-\d{2}-\d{2,4}\s+\d{2}:\d{2}:\d{2})\b", clean_body)
    if dt_match:
        result["full_datetime"] = dt_match.group(1)
        date_part = dt_match.group(1).split()[0]
        try:
            parts = date_part.split("-")
            fmt = "%d-%m-%Y" if len(parts[2]) == 4 else "%d-%m-%y"
            result["date"] = datetime.strptime(date_part, fmt).strftime("%Y-%m-%d")
        except ValueError:
            result["date"] = datetime.now().strftime("%Y-%m-%d")
    else:
        date_match = re.search(
            r"\b(\d{2}-\d{2}-\d{2,4}|\d{1,2}-[\w]{3}-\d{2,4}|\d{4}-\d{2}-\d{2})\b",
            clean_body,
        )
        if date_match:
            raw_date_str = date_match.group(1)
            try:
                parts = raw_date_str.split("-")
                if len(parts[0]) == 4:
                    result["date"] = raw_date_str
                elif len(parts[0]) == 2 and parts[1].isdigit():
                    fmt = "%d-%m-%Y" if len(parts[2]) == 4 else "%d-%m-%y"
                    result["date"] = datetime.strptime(raw_date_str, fmt).strftime(
                        "%Y-%m-%d"
                    )
                elif len(parts[0]) in (1, 2) and parts[1].isalpha():
                    fmt = "%d-%b-%Y" if len(parts[2]) == 4 else "%d-%b-%y"
                    result["date"] = datetime.strptime(raw_date_str, fmt).strftime(
                        "%Y-%m-%d"
                    )
            except ValueError:
                result["date"] = datetime.now().strftime("%Y-%m-%d")
        else:
            result["date"] = datetime.now().strftime("%Y-%m-%d")

    # 8. Generate Fingerprint
    if result["amount"]:
        result["is_parsed"] = True
        acc = result["account_last4"] or "0000"
        ref = result["upi_ref"] or result["merchant"] or "NARRATION"
        raw_key = f"{result['bank_name']}|{acc}|{result['amount']}|{ref}".upper()
        result["txn_fingerprint"] = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    print("\nDEBUG PARSED RESULT DICT:")
    print(result)
    print("=" * 60 + "\n")

    return result
