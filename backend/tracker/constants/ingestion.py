# tracker/constants/ingestion.py
from enum import StrEnum
from typing import Set, Tuple


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
