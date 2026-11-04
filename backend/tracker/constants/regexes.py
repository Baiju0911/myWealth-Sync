# tracker/constants/regexes.py
from enum import StrEnum


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
