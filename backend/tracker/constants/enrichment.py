# tracker/constants/enrichment.py
from decimal import Decimal
from enum import StrEnum
from typing import List, Tuple


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

    BANK_LOOKUP_ATTRIBUTES: Tuple[str, ...] = (
        "display_name",
        "bank_name",
        "name",
        "title",
        "code",
        "slug",
    )
