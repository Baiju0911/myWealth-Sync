# tracker/constants/document_inbox.py
import re
from enum import StrEnum
from typing import Dict, List, Pattern, Tuple


class BankNames(StrEnum):
    SOUTH_INDIAN = "SOUTH INDIAN BANK"
    FEDERAL = "FEDERAL BANK"
    HDFC = "HDFC BANK"
    ICICI = "ICICI BANK"
    SBI = "STATE BANK OF INDIA"


class DocumentInboxConstants:
    """Master signatures and queries for automated PDF attachment ingestion."""

    BANK_SIGNATURES: Dict[str, Dict[str, List[str]]] = {
        BankNames.SOUTH_INDIAN.value: {
            "senders": [
                "alerts@sib.co.in",
                "alerts@sib.bank.in",
                "customercare@sib.bank.in",
                "sibmirror@sib.bank.in",
                "sib-alerts",
            ],
            "keywords": [
                "south indian bank",
                "sib statement",
                "sib-alerts",
                "sib",
                "sibmirror",
            ],
        },
        BankNames.FEDERAL.value: {
            "senders": ["fednetmail@federalbank.co.in", "alerts@federalbank.co.in"],
            "keywords": ["federal bank", "fednet", "fedmobile"],
        },
        BankNames.HDFC.value: {
            "senders": ["alerts@hdfcbank.net", "statements@hdfcbank.com"],
            "keywords": ["hdfc bank", "hdfc"],
        },
        BankNames.ICICI.value: {
            "senders": ["estatements@icicibank.com"],
            "keywords": ["icici bank", "icici"],
        },
        BankNames.SBI.value: {
            "senders": ["estatement@sbi.co.in"],
            "keywords": ["state bank of india", "sbi"],
        },
    }

    STATEMENT_NOTICE_PATTERN = re.compile(
        r"(?:"
        r"e-?statement|"
        r"monthly\s+statement|"
        r"account\s+statement|"
        r"password-protected|"
        r"to\s+view\s+your\s+(?:e-?)?statement|"
        r"password\s+to\s+view|"
        r"salutations\s+to\s+be\s+used"
        r")",
        re.IGNORECASE,
    )

    GMAIL_HARVEST_QUERY: str = (
        "has:attachment filename:pdf ("
        "from:alerts@sib.co.in OR from:alerts@sib.bank.in OR from:sibmirror@sib.bank.in OR "
        'from:fednetmail@federalbank.co.in OR "e-statement" OR "Deposit Advice" OR "Account Statement"'
        ")"
    )

    SIB_ALERT_SENDERS = [
        "alerts@sib.bank.in",
        "alerts@sib.co.in",
    ]

    TERM_DEPOSIT_KEYWORDS: Tuple[str, ...] = (
        "fixed deposit",
        "term deposit",
        "deposit advice",
        "fd advice",
        "deposit receipt",
        "rd advice",
    )

    STATEMENT_KEYWORDS: Tuple[str, ...] = (
        "statement",
        "e-statement",
        "account statement",
        "stmt",
    )

    ACCOUNT_HINT_PATTERNS: Tuple[Pattern, ...] = (
        re.compile(r"(?:account|a\/c|acct)?\s*[xX*]+(\d{2,6})", re.IGNORECASE),
        re.compile(r"[xX*]+(\d{2,6})", re.IGNORECASE),
        re.compile(
            r"(?:ending\s+(?:in|with)|a\/c\s+no\.?)\s*:?\s*(\d{4,})", re.IGNORECASE
        ),
    )
    PERIOD_DATE_PATTERN: Pattern = re.compile(
        r"(?:(?:for\s+the\s+)?period|(?:from))\s*[:\s]*(\d{2}[-/]\d{2}[-/]\d{4})\s*(?:to|-)\s*(\d{2}[-/]\d{2}[-/]\d{4})",
        re.IGNORECASE,
    )

    SIB_FILENAME_DATE_PATTERN = re.compile(
        r"_(\d{2})(\d{2})(\d{4})\.pdf$",
        re.IGNORECASE,
    )
