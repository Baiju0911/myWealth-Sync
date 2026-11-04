# tracker/constants/__init__.py
from typing import List, Set, Tuple, Pattern
from decimal import Decimal

from .ingestion import (
    TxnType,
    StreamSource,
    IngestStatus,
    MatchTier,
    PaymentRail,
    IngestTriggers,
)
from .regexes import ParserRegex, DateFormats
from .classification import TokenCatalog
from .document_inbox import BankNames, DocumentInboxConstants
from .enrichment import (
    SystemDefaults,
    NarrativeLabels,
    PayloadStatus,
    StagingMatchStatus,
    MatchingRules,
    EnrichmentMetadata,
)

# -------------------------------------------------------------------------
# Exported Compatibility Aliases
# -------------------------------------------------------------------------
ACTION_AND_RAIL_NOISE: Set[str] = TokenCatalog.ACTION_AND_RAIL_NOISE
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

VENDOR_CLEAN_STOPWORDS: Set[str] = TokenCatalog.VENDOR_CLEAN_STOPWORDS
INVALID_SUB_TOKENS: Set[str] = TokenCatalog.INVALID_SUB_TOKENS

BLACKLIST_TAGS: Set[str] = (
    TokenCatalog.NOISE_KEYWORDS
    | TokenCatalog.RULE_SAFETY_BLACKLIST
    | TokenCatalog.ABSOLUTE_GREEDY_BLACKLIST
    | TokenCatalog.GENERIC_PATTERNS
    | TokenCatalog.UPI_RAIL_TOKENS
    | TokenCatalog.CORPORATE_NOISE_SUFFIXES
    | {
        "TRANSFER_NACH",
        "TRANSFER",
        "TRANSFER_COLON",
        "SUSPENSE_ACCOUNT",
        "UNCLASSIFIED_OTHER",
        "GENERAL_OPERATING_EXPENSES",
        "OWN_ACCOUNT",
        "NULL",
        "UNKNOWN",
        "GENERAL_SUSPENSE",
        "UNLABELED_BANK_LINE",
    }
) - TokenCatalog.OK_WORD_LIST

ALL_CANDIDATE_BLACKLIST: Set[str] = BLACKLIST_TAGS

TXN_DEBIT_TRIGGERS: Tuple[str, ...] = IngestTriggers.TXN_DEBIT
TXN_CREDIT_TRIGGERS: Tuple[str, ...] = IngestTriggers.TXN_CREDIT
SELF_TRANSFER_TRIGGERS: Tuple[str, ...] = IngestTriggers.SELF_TRANSFER
TERM_DEPOSIT_TRIGGERS: Tuple[str, ...] = IngestTriggers.TERM_DEPOSIT
AMB_NOISE_TRIGGERS: Tuple[str, ...] = IngestTriggers.AMB_NOISE

DEFAULT_FALLBACK_BANK: str = SystemDefaults.BANK.value
DEFAULT_FALLBACK_VENDOR: str = SystemDefaults.VENDOR.value

BANK_SOUTH_INDIAN: str = BankNames.SOUTH_INDIAN.value
BANK_FEDERAL: str = BankNames.FEDERAL.value
BANK_HDFC: str = BankNames.HDFC.value
BANK_ICICI: str = BankNames.ICICI.value
BANK_SBI: str = BankNames.SBI.value

BANK_INBOX_SIGNATURES = DocumentInboxConstants.BANK_SIGNATURES
GMAIL_INBOX_HARVEST_QUERY: str = DocumentInboxConstants.GMAIL_HARVEST_QUERY
TERM_DEPOSIT_KEYWORDS: List[str] = list(DocumentInboxConstants.TERM_DEPOSIT_KEYWORDS)
STATEMENT_KEYWORDS: List[str] = list(DocumentInboxConstants.STATEMENT_KEYWORDS)
ACCOUNT_HINT_PATTERNS: List[Pattern] = list(
    DocumentInboxConstants.ACCOUNT_HINT_PATTERNS
)
PERIOD_DATE_PATTERN: Pattern = DocumentInboxConstants.PERIOD_DATE_PATTERN
SIB_FILENAME_DATE_PATTERN: Pattern = DocumentInboxConstants.SIB_FILENAME_DATE_PATTERN

ACTIVE_STAGED_PAYLOAD_STATUSES: List[str] = PayloadStatus.active_staged_statuses()
PAISE_TOLERANCE_THRESHOLD: Decimal = MatchingRules.PAISE_TOLERANCE_THRESHOLD
HOLIDAY_DAY_OFFSETS: Tuple[int, ...] = MatchingRules.HOLIDAY_DAY_OFFSETS
BULK_UPDATE_BATCH_SIZE: int = MatchingRules.BULK_UPDATE_BATCH_SIZE

__all__ = [
    "TxnType",
    "StreamSource",
    "IngestStatus",
    "MatchTier",
    "PaymentRail",
    "IngestTriggers",
    "ParserRegex",
    "DateFormats",
    "TokenCatalog",
    "BankNames",
    "DocumentInboxConstants",
    "SystemDefaults",
    "NarrativeLabels",
    "PayloadStatus",
    "StagingMatchStatus",
    "MatchingRules",
    "EnrichmentMetadata",
    "ACTION_AND_RAIL_NOISE",
    "UPI_RAIL_TOKENS",
    "CORPORATE_NOISE_SUFFIXES",
    "NOISE_KEYWORD_BLACKLIST",
    "GENERIC_IGNORE_PATTERNS",
    "GENERIC_PATTERNS",
    "KNOWN_MERCHANTS",
    "RULE_SAFETY_BLACKLIST",
    "ABSOLUTE_GREEDY_BLACKLIST",
    "CATASTROPHIC_KEYWORDS",
    "OK_WORD_LIST",
    "TAXONOMY_NOISE_KEYWORDS",
    "TRANSFER_BANK_NOISE",
    "ALL_SYSTEM_BLACKLIST",
    "VENDOR_CLEAN_STOPWORDS",
    "INVALID_SUB_TOKENS",
    "BLACKLIST_TAGS",
    "ALL_CANDIDATE_BLACKLIST",
    "TXN_DEBIT_TRIGGERS",
    "TXN_CREDIT_TRIGGERS",
    "SELF_TRANSFER_TRIGGERS",
    "TERM_DEPOSIT_TRIGGERS",
    "AMB_NOISE_TRIGGERS",
    "DEFAULT_FALLBACK_BANK",
    "DEFAULT_FALLBACK_VENDOR",
    "BANK_SOUTH_INDIAN",
    "BANK_FEDERAL",
    "BANK_HDFC",
    "BANK_ICICI",
    "BANK_SBI",
    "BANK_INBOX_SIGNATURES",
    "GMAIL_INBOX_HARVEST_QUERY",
    "TERM_DEPOSIT_KEYWORDS",
    "STATEMENT_KEYWORDS",
    "ACCOUNT_HINT_PATTERNS",
    "PERIOD_DATE_PATTERN",
    "SIB_FILENAME_DATE_PATTERN",
    "ACTIVE_STAGED_PAYLOAD_STATUSES",
    "PAISE_TOLERANCE_THRESHOLD",
    "HOLIDAY_DAY_OFFSETS",
    "BULK_UPDATE_BATCH_SIZE",
]
