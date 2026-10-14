"""
tracker/constants.py - Master Financial Ingest & Classification Constants

Encapsulates all keywords, token blacklists, payment rails, regex patterns,
and narrative system strings into structured classes with typed accessors.
"""

import re
from decimal import Decimal
from enum import StrEnum
from typing import Dict, List, Pattern, Set, Tuple

# =============================================================================
# 1. TRANSACTION TYPES & INGEST STATUSES
# =============================================================================


class TxnType(StrEnum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"
    NOISE = "NOISE"

    @classmethod
    def as_set(cls) -> Set[str]:
        return {cls.DEBIT.value, cls.CREDIT.value, cls.NOISE.value}


class StreamSource(StrEnum):
    IOS_SMS = "IOS_SMS"
    GMAIL_API = "GMAIL_API"
    BANK_STATEMENT = "BANK_STATEMENT"
    MERGED_STREAM = "MERGED_STREAM"

    @classmethod
    def as_set(cls) -> Set[str]:
        return {
            cls.IOS_SMS.value,
            cls.GMAIL_API.value,
            cls.BANK_STATEMENT.value,
            cls.MERGED_STREAM.value,
        }


class IngestStatus(StrEnum):
    PARSED = "PARSED"
    UNPARSED = "UNPARSED"
    DUPLICATE = "DUPLICATE"
    MATCHED_2_WAY = "MATCHED_2_WAY"
    RECONCILED_3_WAY = "RECONCILED_3_WAY"

    @classmethod
    def as_set(cls) -> Set[str]:
        return {
            cls.PARSED.value,
            cls.UNPARSED.value,
            cls.DUPLICATE.value,
            cls.MATCHED_2_WAY.value,
            cls.RECONCILED_3_WAY.value,
        }


class MatchTier(StrEnum):
    TIER_1_REFERENCE = "TIER_1_REFERENCE"
    TIER_2_AUTH_CODE = "TIER_2_AUTH_CODE"
    TIER_3_TIME_PROXIMITY = "TIER_3_TIME_PROXIMITY"


class PaymentRail(StrEnum):
    UPI = "UPI"
    IMPS = "IMPS"
    NEFT = "NEFT"
    RTGS = "RTGS"
    NACH = "NACH"
    POS = "POS"
    ATM = "ATM"
    INTERNAL_TRANSFER = "INTERNAL_TRANSFER"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def as_set(cls) -> Set[str]:
        return {member.value for member in cls}

    @classmethod
    def contains(cls, token: str) -> bool:
        return str(token).upper() in cls.as_set()


# =============================================================================
# 2. INGESTION & TRIGGER REGEX PATTERNS
# =============================================================================


class IngestTriggers:
    TXN_DEBIT: Tuple[str, ...] = (
        "was spent",
        "debited from",
        "debited for",
        "debited",
        "spent",
        "paid",
        "withdrawn",
        "outward",
        "sent",
        "dr",
    )

    TXN_CREDIT: Tuple[str, ...] = (
        "has been credited",
        "credited to",
        "credited with",
        "credited",
        "received",
        "deposited",
        "inward",
        "cr",
    )

    SELF_TRANSFER: Tuple[str, ...] = (
        "own account",
        "self",
        "internal transfer",
        "to own",
        "own a/c",
        "funds transfer",
    )

    TERM_DEPOSIT: Tuple[str, ...] = (
        "term deposit",
        "fixed deposit",
        "details of the term deposits",
        "deposit maturity",
        "deposit closure",
        "deposit advice",
        "fd closure",
        "fd proceeds",
    )

    AMB_NOISE: Tuple[str, ...] = (
        "average monthly balance",
        "below the required minimum balance",
        "minimum balance in the month",
        "non maintenance charges",
        "welcome to",
        "kyc update",
    )


# =============================================================================
# 3. REGEX BLUEPRINTS & PARSER DELIMITERS
# =============================================================================


class ParserRegex(StrEnum):
    """Compiled pattern expressions for deterministic entity extraction."""

    # HTML Parsing
    HTML_COMMENTS = r"<!--.*?-->"
    HTML_HEAD_SCRIPT_STYLE = r"<(head|title|script|style)[^>]*>.*?</\1>"
    HTML_BLOCK_BREAKS = (
        r"<(br|p|div|tr|th|td|li|h[1-6])[^>]*>|</(p|div|tr|h[1-6]|li)>|<br\s*/?>"
    )
    HTML_TAGS = r"<[^>]+>"
    MULTIPLE_SPACES = r"\s+"

    # Numbers and Cleaners
    NON_ALPHANUMERIC = r"[^A-Z0-9\s]"
    NON_DIGITS = r"\D"
    ALL_DIGITS_MATCH = r"^\d+$"
    TWELVE_DIGIT_MATCH = r"^\d{12}$"
    FOURTEEN_DIGIT_MATCH = r"^\d{14}$"
    CODE_TOKEN_MATCH = r"^[A-Z0-9]{3,8}$"

    # Banking Entities & Accounts
    DOMAIN_EXTRACTOR = r"@(?:[a-zA-Z0-9-]+\.)*([a-zA-Z0-9-]+)\."
    BANK_SIGN_OFF = r"(?:with|at|from|team)\s+([A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*){0,3}\s+Bank)\b"
    ACCOUNT_NUMBER_STRICT = r"\b(\d{16})\b"
    ACCOUNT_MASKED_PRIMARY = r"\b[xX*]{2,}(\d{4,16})\b"
    ACCOUNT_MASKED_SECONDARY = (
        r"(?:account|a/c|card|ac|ending)\s*(?:no\.?|number)?\s*[:\s]*[xX*]*(\d{4,16})\b"
    )

    # Financial Values
    AMOUNT_INR = r"(?:INR\s*|RS\.?|₹)\s*(?:RS\.?\s*)?([\d,]+(?:\.\d{1,2})?)"
    AMOUNT_INR_CAPTURE = r"(?:INR|RS\.?|INR\.|₹)\s*([\d,]+(?:\.\d{2})?)"
    BALANCE_INR = (
        r"\bBal(?:ance)?\s*[:\s]*\s*(?:INR\s*|RS\.?|₹)?\s*([\d,]+(?:\.\d{1,2})?)"
    )
    BALANCE_CAPTURE = r"(?:Bal|Balance|Avl\s*Bal|Available\s*Balance)[:\s]*(?:INR|RS\.?|INR\.|₹)?\s*([\d,]+(?:\.\d{2})?)"
    DATE_GENERAL = r"\b(\d{2}[-/]\d{2}[-/]\d{2,4})\b"

    # Rails, Streams & References
    INFO_SLASH_STREAM = (
        r"(?:Info[:\s-]+)+\s*([A-Za-z0-9]+)/([^/]+)/([0-9]{8,18})/([^/\n]+)"
    )
    STREAM_STRIP_TAIL = r"\s+(?:on\s+\d{2}[-/]\d{2}[-/]\d{2,4}|If\s+the\s+above|Block\s+A/c|Call\s*1800|\.|$).*"
    INFO_PREFIX_STRIP = r"^(?:Info[:\s-]+)+"
    MERCHANT_NOISE_PHRASES = (
        r"\b(?:Collect\s+Transaction|Payment\s+for|You\s+are\s+paying|NO\s+REMAR.*)\b"
    )
    UPI_SLASH = r"UPI/([A-Za-z0-9]+)/(\d{12})/([^/\n\.]+)"
    UPI_RRN = r"(?:UPI\s*(?:Ref|RRN|No\.?)|Ref\s*(?:No\.?)?|RRN)[:\s\-]*(\d{12})"
    NEFT_UTR = r"(?:NEFT\s*(?:Ref|UTR|No\.?)|UTR\s*(?:No\.?)?|RTGS)[:\s\-]*([A-Za-z0-9]{12,22})"
    POS_AUTH = r"\b(?:Auth(?:\s*Code)?|Appr(?:\s*Code)?)[:\s]*([A-Z0-9]{6})\b"

    # SMS Entity Tokenizers
    SMS_BENEFICIARY_VIA = r"via\s+(UPI|IMPS|NEFT|RTGS)\s+to\s+([A-Za-z0-9\s\.\-_]+?)(?:\.\s*Ref|\s+Ref|\s+RRN|$)"
    SMS_PAYEE_EXPLICIT = (
        r"(?:to|at|info\s*[-:]?)\s+([A-Za-z0-9\s\.\-_&]+?)(?:\s+on|\s+Ref|\s+RRN|\.|$)"
    )
    SMS_DEBIT_ALERT_RAW_NOISE = r"^(?:UPI\s+)?DEBIT\s+RS|SPENT\s+FROM|WAS\s+SPENT"
    SMS_PREFIX_DEBIT_AMOUNT = (
        r"^(?:UPI\s+)?(?:DEBIT|CREDIT)?\s*(?:RS\.?|INR)?\s*[\d\s\.,]+\s*(?:A|TO)?\s*"
    )
    DANGLING_SINGLE_CHAR_SUFFIX = r"\s+[A-Za-z]$"

    # Term Deposit Extraction
    TD_ACCOUNT = r"(?:Account Number|Deposit A/c|A/c No\.?|Deposit No\.?)[:\s]*([0-9]{8,18}|\d{4,18})"
    TD_ACCOUNT_FALLBACK = r"\b(\d{12,18})\b"
    TD_DATE_CLOSED = r"closed\s+on\s+(\d{2}[-/]\d{2}[-/]\d{4})"
    TD_DATE_MATURITY = r"maturity date[:\s]+(\d{2}[-/]\d{2}[-/]\d{4})"
    TD_DATE_VALUE = r"value date[:\s]+(\d{2}[-/]\d{2}[-/]\d{4})"
    TD_AMOUNT_SECONDARY = r"(?:Amount|Maturity Proceeds|Principal)[:\s]+(?:INR|Rs\.?|₹)?\s*([\d,]+(?:\.\d{1,2})?)"
    TD_AMOUNT_MONTHS = r"\b(\d{4,10}(?:\.\d{2})?)\s*(?:INR)?\s+\d+\s+Months"
    TD_TENURE = r"(?:Period|Tenure)[:\s]*(\d+\s*(?:Months|Years|Days)[^\n\r,]*)"
    TD_PRINCIPAL_IN_TABLE = r"\b(\d{4,9})\s+INR\b"

    # Salutations, email preambles & system sign-offs
    GREETING_PREAMBLE = (
        r"^(?:Dear\s+(?:Sir/Madam|Customer|User)[,\s]*"
        r"(?:This\s+is\s+to\s+inform\s+you\s+that[,\s]*)?|"
        r"Hello|Dear\s+User|Hi)[,\.\s]*"
    )
    SIGN_OFF_FOOTER = (
        r"(?:If\s+the\s+above-mentioned\s+transaction\s+has\s+not\s+been\s+done.*|"
        r"For\s+any\s+clarifications.*|"
        r"Assuring\s+our\s+best\s+service.*|"
        r"Sincerely,.*|"
        r"\*\*\*Please\s+do\s+not\s+reply.*)"
    )


class DateFormats(StrEnum):
    ISO_DATE = "%Y-%m-%d"
    ISO_DATETIME = "%Y-%m-%d %H:%M:%S"
    TIME_ZERO = " 00:00:00"
    DMY_FOUR = "%d-%m-%Y"
    DMY_TWO = "%d-%m-%y"
    DBY_FOUR = "%d-%b-%Y"
    DBY_TWO = "%d-%b-%y"


# =============================================================================
# 4. BANKING TOKENS & SYSTEM BLACKLISTS
# =============================================================================


# =============================================================================
# 4. BANKING TOKENS & SYSTEM BLACKLISTS
# =============================================================================


class TokenCatalog:
    """Master registry of payment tokens, blacklist identifiers, and protected words."""

    YEAR_PREFIXES_TIMESTAMP: Tuple[str, ...] = ("2024", "2025", "2026", "2027")
    INTERMEDIARY_RAIL_CODES: Set[str] = {"MOB", "INB", "FTB"}

    GENERIC_MERCHANT_NOISE_WORDS: Set[str] = {
        "A",
        "TO",
        "INFO",
        "UNKNOWN",
        "DEBIT",
        "CREDIT",
        "DIRECT PAYMENT",
        "UNKNOWN VENDOR",
    }

    # Consolidated Rail & Gateway Network Tokens
    UPI_RAIL_TOKENS: Set[str] = {
        "RRN", "UPI", "REV", "REF", "TXN", "CR", "DR", "INB", "WDLTFR",
        "DEPTFR", "MOB", "IMPS", "NEFT", "RTGS", "NACH", "ACH", "POS",
        "YESB", "SBIN", "HDFC", "ICIC", "ICICI", "FDRL", "CNRB", "BARB",
        "PUNB", "UTIB", "AIRP", "AIRTEL", "PAYTM", "PYTM", "YBL", "IBL",
        "AXIS", "KKBK", "RAZORPAY", "BIL", "TPV", "ECOM", "NAT", "OFMR",
        "TRANSACTION", "COLLECT", "UPIINTENT", "TRANSFER",
    }

    # Corporate & Legal Suffixes to Strip from Merchant Counterparties
    CORPORATE_NOISE_SUFFIXES: Set[str] = {
        "LTD", "LIMITED", "PVT", "PRIVATE", "ONLINE", "ORDER", "ONLINE_ORDER",
        "INDIA", "PAYMENTS", "SOLUTIONS", "SERVICES", "ENTERPRISES", "STORE",
        "RESTAURANT", "FOOD", "FOODS", "CAFE", "BAKERY", "SUPERMARKET",
    }

    # Clean Anchor Brands for Direct Canonical Clustering
    KNOWN_MERCHANTS: Set[str] = {
        "ZOMATO",
        "SWIGGY",
        "BLINKIT",
        "ZEPTO",
        "INSTAMART",
        "UBER",
        "OLA",
        "AMAZON",
        "FLIPKART",
        "BIGBASKET",
        "NETFLIX",
        "SPOTIFY",
        "MAKEMYTRIP",
        "IRCTC",
        "AIRTEL",
        "JIO",
        "TATA",
        "POTHY",
        "LULU",
        "PVR",
        "INOX",
        "CINEPOLIS",
        "BHIMA",
        "KALYAN",
        "JOYALUKKAS",
        "THANGAMAYIL",
        "SKECHERS",
    }

    NOISE_KEYWORDS: Set[str] = {
        "UPI", "NEFT", "RTGS", "IMPS", "POS", "ACH", "NFT", "TFR", "TRANSFER",
        "PAYMENT", "DR", "CR", "BANK", "INB", "INF", "BIL", "CLG", "CHQ",
        "CHEQUE", "CASH", "ATM", "DEBIT", "CREDIT", "NONE", "UNDEFINED",
        "GENERAL_OPERATING_EXPENSES", "UNCLASSIFIED", "SUSPENSE_ACCOUNT",
        "INTENT", "INTEN", "UPIINTENT", "MERCHANT", "YESPAY", "RAZORPAY",
        "PAYU", "RZP", "COLLECT", "EXPRESS", "LIMITED", "LTD", "PVTLTD",
        "PRIVATE", "PAY", "PAYING", "PAYVIA", "PAYFOR", "PAYMENTFOR",
        "INTENTPAY", "SWIGGYPAY", "SETTLEMENT", "REFUND", "BILL", "FUND",
        "DICT", "ACCOUNT", "CENTRE", "UTIB", "YESB", "BARB", "IBKL", "PUNB",
        "MAHB", "IDIB", "IOBA", "UBIN", "KKBK", "RATN", "PYTM", "PAYTM",
        "YBL", "PTYBL", "IBL", "AXL", "APL", "IPL", "OBL", "OKHDFCB",
        "OKSBI", "OKAXIS", "OKICICI", "BARODAMPAY", "ALLBANK", "MAHBANK",
        "IDFCBANK", "IDBI", "INDUS", "RBL", "UCO", "UNIONBANK", "REMARKS",
        "REMARK", "NOREMARKS", "NOREMARK", "NO_REMARKS", "NO_REMARK",
        "PAYMENT_FOR", "YOU_ARE_PAYING", "INGESTED_VIA_STAGING", "PAYTMQR",
        "PI", "CMN", "PRCR", "POSTRN", "TRN", "TXN", "REF", "NO", "ID",
        "ORDER", "BRANCH", "TVM",
    }

    GENERIC_IGNORE_PATTERNS: Set[str] = {
        "MOB", "UPI", "PYTM", "IMPS", "NEFT", "RTGS", "TRANSFER", "BY",
        "TO", "PAID", "RECEIVED", "INB", "INB/IMPS", "OTHERS",
    }

    GENERIC_PATTERNS: Set[str] = {
        "#GENERAL_OPERATING_EXPENSES",
        "#GENERAL_OPERATING_EXPENSE",
        "#SUSPENSE_ACCOUNT",
        "#UNCLASSIFIED_OTHER",
        "#SUSPENSE",
        "#TRANSFER_NACH",
        "GENERAL_OPERATING_EXPENSES",
        "UNCLASSIFIED",
        "TRANSFER_NACH",
        "UNCLASSIFIED_OTHER",
        "SUSPENSE_ACCOUNT",
        "IMPS",
        "POSTRN",
    }

    RULE_SAFETY_BLACKLIST: Set[str] = {
        "YBL", "PTYBL", "IBL", "AXL", "APL", "IPL", "OBL", "OKICICI",
        "OKHDFCBANK", "OKAXIS", "OKSBI", "BARODAMPAY", "ALLBANK", "MAHBANK",
        "IDFCBANK", "YESB", "PAYMENT", "ORDER", "TRANSFER", "UPI", "INTENT",
        "FOR", "THE", "BY", "TO", "PAID", "RECEIVED", "BRANCH",
    }

    ABSOLUTE_GREEDY_BLACKLIST: Set[str] = {
        "UPI", "TRANSFER", "PAYMENT", "BANK", "PAID", "RECEIVED", "CARD",
    }

    CATASTROPHIC_KEYWORDS: Set[str] = {
        "UPI", "PAYMENT", "TRANSFER", "BANK", "PAID", "RECEIVED", "CARD",
        "CASH", "DEBIT", "CREDIT", "REMARKS", "INTENT",
    }

    OK_WORD_LIST: Set[str] = {
        "LIC", "SIP", "EMI", "ATM", "TAX", "GST", "POS", "PF", "FD", "RD",
        "NEFT", "RTGS", "UPI", "AMAZON", "SIBL", "KSEB", "KSFE", "MILK",
        "TEA", "SBI", "SIB", "TO SBI", "TO SIB", "FED", "TO FED",
        "NACH CR", "NACH",
    }

    TAXONOMY_NOISE_KEYWORDS: Tuple[str, ...] = (
        "TRANSFER", "TRANSFERS", "MB FT", "MB FTO", "MB FTB", "SBI", "SIB",
        "SIBL", "SBONR", "FED-NRO", "FED-NRO-1050", "FED-NRE",
    )

    TRANSFER_BANK_NOISE: Set[str] = {
        "TRANSFER", "TRANSFERS", "MB FT", "MB FTO", "MB FTB", "SBI", "SIB",
        "SIBL", "SBONR", "FED-NRO", "FED-NRE",
    }

    VENDOR_CLEAN_STOPWORDS: Set[str] = {
        "PVT", "LTD", "LIMITED", "INC", "PAY", "INFO", "PRIVATE", "NO REMARK",
        "REMARK", "CARD", "ON", "FROM", "YOUR", "ACCOUNT", "A/C", "A C", "TRV",
        "BANGALORE", "MUMBAI", "CHENNAI", "DEAR", "CUSTOMER", "THIS", "IS",
        "TO", "INFORM", "YOU", "THAT", "NO", "REMAR", "NOREMAR", "NOREMARKS",
    }

    INVALID_SUB_TOKENS: Set[str] = {
        "suspense account", "none", "null", "unclassified", "unknown", "ai unclassified",
    }

    IGNORE_SLASH_TOKENS: Set[str] = {
        "OWN", "SELF", "INFO", "CARD", "FROM", "YOUR", "ACCT", "DR", "CR",
        "MOB", "REF", "NARRATION", "NA", "NULL", "NONE",
    }

    @classmethod
    def get_all_system_blacklist(cls) -> Set[str]:
        combined = (
            cls.RULE_SAFETY_BLACKLIST
            | cls.NOISE_KEYWORDS
            | cls.CATASTROPHIC_KEYWORDS
            | cls.UPI_RAIL_TOKENS
            | cls.CORPORATE_NOISE_SUFFIXES
        )
        return combined - cls.OK_WORD_LIST


# =============================================================================
# 7. EXPORTED COMPATIBILITY ALIASES
# =============================================================================
UPI_RAIL_TOKENS: Set[str] = TokenCatalog.UPI_RAIL_TOKENS
CORPORATE_NOISE_SUFFIXES: Set[str] = TokenCatalog.CORPORATE_NOISE_SUFFIXES
NOISE_KEYWORD_BLACKLIST: Set[str] = TokenCatalog.NOISE_KEYWORDS
GENERIC_IGNORE_PATTERNS: Set[str] = TokenCatalog.GENERIC_IGNORE_PATTERNS
GENERIC_PATTERNS: Set[str] = TokenCatalog.GENERIC_PATTERNS
KNOWN_MERCHANTS: Set[str] = TokenCatalog.KNOWN_MERCHANTS
RULE_SAFETY_BLACKLIST: Set[str] = TokenCatalog.RULE_SAFETY_BLACKLIST
ABSOLUTE_GREEDY_BLACKLIST: Set[str] = TokenCatalog.ABSOLUTE_GREEDY_BLACKLIST
CATASTROPHIC_KEYWORDS: Set[str] = TokenCatalog.CATASTROPHIC_KEYWORDS
OK_WORD_LIST: Set[str] = TokenCatalog.OK_WORD_LIST
TAXONOMY_NOISE_KEYWORDS: Tuple[str, ...] = TokenCatalog.TAXONOMY_NOISE_KEYWORDS
TRANSFER_BANK_NOISE: Set[str] = TokenCatalog.TRANSFER_BANK_NOISE
ALL_SYSTEM_BLACKLIST: Set[str] = TokenCatalog.get_all_system_blacklist()

# Unified blacklist set for direct consumption by clustering & candidates
BLACKLIST_TAGS: Set[str] = (
    TokenCatalog.NOISE_KEYWORDS
    | TokenCatalog.RULE_SAFETY_BLACKLIST
    | TokenCatalog.ABSOLUTE_GREEDY_BLACKLIST
    | TokenCatalog.GENERIC_PATTERNS
    | TokenCatalog.UPI_RAIL_TOKENS
    | TokenCatalog.CORPORATE_NOISE_SUFFIXES
    | {
        "TRANSFER_NACH", "TRANSFER", "TRANSFER_COLON", "SUSPENSE_ACCOUNT",
        "UNCLASSIFIED_OTHER", "GENERAL_OPERATING_EXPENSES", "OWN_ACCOUNT",
        "NULL", "UNKNOWN", "GENERAL_SUSPENSE", "UNLABELED_BANK_LINE",
    }
) - TokenCatalog.OK_WORD_LIST

ALL_CANDIDATE_BLACKLIST: Set[str] = BLACKLIST_TAGS


# =============================================================================
# 5. SYSTEM NARRATIVES, LABELS & DEFAULTS
# =============================================================================


class SystemDefaults(StrEnum):
    BANK = "UNKNOWN BANK"
    VENDOR = "Unclassified"
    SUSPENSE_CATEGORY = "Expense"
    SUSPENSE_SUBCATEGORY = "Suspense Account"
    ACCOUNT_FALLBACK_LAST4 = "0000"
    UNREGISTERED = "UNREGISTERED"
    NODATE = "NODATE"
    ZERO_AMOUNT = "0.00"
    NOT_AVAILABLE = "N/A"
    EMPTY_STRING = ""
    SPACE = " "
    SLASH = "/"
    DASH = "-"
    COMMA = ","
    PIPE = "|"


class NarrativeLabels(StrEnum):
    AMB_NOTICE_MERCHANT = "⚠️ [SYSTEM ALERT] Minimum Balance Notice"
    AMB_NOTICE_NARRATION = "Non-transactional AMB alert notice"
    FD_PROCEEDS_SUFFIX = "(FD PROCEEDS)"
    INWARD_TRANSFER = "INWARD TRANSFER"
    TRANSFER_SUFFIX = "Transfer"
    OWN_ACCOUNT = "Own Account"
    OWN_ACCOUNT_TRANSFER = "Own Account Transfer"
    UPI_REF_PREFIX = "FD-"
    PROCEEDS = "PROCEEDS"
    FALLBACK_REF = "REF"
    FALLBACK_DIRECT_PAYMENT = "Direct Payment"
    TD_NARRATION_TEMPLATE = "TERM DEPOSIT CLOSURE - A/C {} | PROCEEDS"
    TD_FINGERPRINT_PREFIX = "{}_TD_CLOSURE|{}|{}|{}"
    STANDARD_FINGERPRINT_PREFIX = "{}|{}|{}|{}"
    REF_NARRATION_TEMPLATE = "{} REF: {} | {}"
    SLASH_NARRATION_TEMPLATE = "{}/{}/{}"
    ACCOUNT_NOT_FOUND = "Account Not Found"


# =============================================================================
# 6. DOCUMENT INBOX & ATTACHMENT HARVESTING
# =============================================================================


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

    GMAIL_HARVEST_QUERY: str = (
        "has:attachment filename:pdf ("
        "from:alerts@sib.co.in OR from:alerts@sib.bank.in OR from:sibmirror@sib.bank.in OR "
        'from:fednetmail@federalbank.co.in OR "e-statement" OR "Deposit Advice" OR "Account Statement"'
        ")"
    )

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

    # SIB filename date pattern: RET_OG37127253_31032026.pdf -> DDMMYYYY
    SIB_FILENAME_DATE_PATTERN = re.compile(
        r"_(\d{2})(\d{2})(\d{4})\.pdf$",
        re.IGNORECASE,
    )


# =============================================================================
# 7. EXPORTED COMPATIBILITY ALIASES
# =============================================================================
NOISE_KEYWORD_BLACKLIST: Set[str] = TokenCatalog.NOISE_KEYWORDS
GENERIC_IGNORE_PATTERNS: Set[str] = TokenCatalog.GENERIC_IGNORE_PATTERNS
GENERIC_PATTERNS: Set[str] = TokenCatalog.GENERIC_PATTERNS
KNOWN_MERCHANTS: Set[str] = TokenCatalog.KNOWN_MERCHANTS
RULE_SAFETY_BLACKLIST: Set[str] = TokenCatalog.RULE_SAFETY_BLACKLIST
ABSOLUTE_GREEDY_BLACKLIST: Set[str] = TokenCatalog.ABSOLUTE_GREEDY_BLACKLIST
CATASTROPHIC_KEYWORDS: Set[str] = TokenCatalog.CATASTROPHIC_KEYWORDS
OK_WORD_LIST: Set[str] = TokenCatalog.OK_WORD_LIST
TAXONOMY_NOISE_KEYWORDS: Tuple[str, ...] = TokenCatalog.TAXONOMY_NOISE_KEYWORDS
TRANSFER_BANK_NOISE: Set[str] = TokenCatalog.TRANSFER_BANK_NOISE
ALL_SYSTEM_BLACKLIST: Set[str] = TokenCatalog.get_all_system_blacklist()

TXN_DEBIT_TRIGGERS: Tuple[str, ...] = IngestTriggers.TXN_DEBIT
TXN_CREDIT_TRIGGERS: Tuple[str, ...] = IngestTriggers.TXN_CREDIT
SELF_TRANSFER_TRIGGERS: Tuple[str, ...] = IngestTriggers.SELF_TRANSFER
TERM_DEPOSIT_TRIGGERS: Tuple[str, ...] = IngestTriggers.TERM_DEPOSIT
AMB_NOISE_TRIGGERS: Tuple[str, ...] = IngestTriggers.AMB_NOISE
VENDOR_CLEAN_STOPWORDS: Set[str] = TokenCatalog.VENDOR_CLEAN_STOPWORDS
INVALID_SUB_TOKENS: Set[str] = TokenCatalog.INVALID_SUB_TOKENS

DEFAULT_FALLBACK_BANK: str = SystemDefaults.BANK.value
DEFAULT_FALLBACK_VENDOR: str = SystemDefaults.VENDOR.value

# Canonical Bank Display Names
BANK_SOUTH_INDIAN = BankNames.SOUTH_INDIAN.value
BANK_FEDERAL = BankNames.FEDERAL.value
BANK_HDFC = BankNames.HDFC.value
BANK_ICICI = BankNames.ICICI.value
BANK_SBI = BankNames.SBI.value

# Attachment Ingestion Aliases
BANK_INBOX_SIGNATURES = DocumentInboxConstants.BANK_SIGNATURES
GMAIL_INBOX_HARVEST_QUERY = DocumentInboxConstants.GMAIL_HARVEST_QUERY
TERM_DEPOSIT_KEYWORDS = list(DocumentInboxConstants.TERM_DEPOSIT_KEYWORDS)
STATEMENT_KEYWORDS = list(DocumentInboxConstants.STATEMENT_KEYWORDS)
ACCOUNT_HINT_PATTERNS = list(DocumentInboxConstants.ACCOUNT_HINT_PATTERNS)
PERIOD_DATE_PATTERN = DocumentInboxConstants.PERIOD_DATE_PATTERN
SIB_FILENAME_DATE_PATTERN = DocumentInboxConstants.SIB_FILENAME_DATE_PATTERN


# =============================================================================
# 8. LIVE STREAM COMMIT & ENRICHMENT PIPELINE CONSTANTS
# =============================================================================


class PayloadStatus(StrEnum):
    """Lifecycle statuses for raw stream alert records (RawEmailPayload)."""

    STAGED = "STAGED"
    PENDING = "PENDING"
    ENRICHED = "ENRICHED"
    ENRICHED_WITH_WARNING = "ENRICHED_WITH_WARNING"
    DUPLICATE_RETIRED = "DUPLICATE_RETIRED"
    PARSED = "PARSED"
    FAILED = "FAILED"

    @classmethod
    def active_staged_statuses(cls) -> List[str]:
        return [cls.STAGED.value, cls.PENDING.value]


class StagingMatchStatus(StrEnum):
    """Match state recorded within staging_payload JSON and audit metadata."""

    COMPLETED = "Completed"
    COMPLETED_WITH_WARNING = "Completed With Warning"
    DUPLICATE_COMPANION_RETIRED = "Duplicate Companion Retired"
    STAGED = "STAGED"
    PENDING = "PENDING"


class MatchingRules:
    """Master numerical thresholds, batch boundaries, and heuristic windows."""

    PAISE_TOLERANCE_THRESHOLD: Decimal = Decimal("1.00")
    HOLIDAY_BUFFER_DAYS: int = 3
    HOLIDAY_DAY_OFFSETS: Tuple[int, ...] = (0, -1, 1, -2, 2, -3, 3)
    MIN_RRN_ANCHOR_LENGTH: int = 6
    BULK_UPDATE_BATCH_SIZE: int = 500


class EnrichmentMetadata:
    """Central registry of payload metadata strings, reasons, and reflection keys."""

    WARNING_TYPE_PAISE_DELTA: str = "PAISE_TRUNCATION_DELTA"
    DEFAULT_MERCHANT: str = "DIRECT_PAYMENT"
    DEFAULT_SOURCE: str = "STREAM"
    DEFAULT_BANK_NAME: str = SystemDefaults.BANK.value

    COMPANION_RETIREMENT_REASON: str = (
        "Twin alert already enriched statement line via identical RRN"
    )

    # Dynamic attribute fallback order for bank ID / name resolution
    BANK_LOOKUP_ATTRIBUTES: Tuple[str, ...] = (
        "display_name",
        "bank_name",
        "name",
        "title",
        "code",
        "slug",
    )


# Exported Pipeline Aliases
ACTIVE_STAGED_PAYLOAD_STATUSES: List[str] = PayloadStatus.active_staged_statuses()
PAISE_TOLERANCE_THRESHOLD: Decimal = MatchingRules.PAISE_TOLERANCE_THRESHOLD
HOLIDAY_DAY_OFFSETS: Tuple[int, ...] = MatchingRules.HOLIDAY_DAY_OFFSETS
BULK_UPDATE_BATCH_SIZE: int = MatchingRules.BULK_UPDATE_BATCH_SIZE
