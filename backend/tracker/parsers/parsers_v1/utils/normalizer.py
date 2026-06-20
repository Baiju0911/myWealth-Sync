# backend/tracker/parsers/parsers_v1/utils/normalizer.py
import re
from datetime import datetime

# Centralized RegEx compilation
DATE_MATCH_REGEX = re.compile(
    r"\b\d{2}-\d{2}-\d{4}\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{2}/\d{2}/\d{4}\b"
)
NUMERIC_FINDER_REGEX = re.compile(
    r"\b\d{1,3}(?:,\d{2,3})*(?:\.\d{2})(?:CR|DR)?\b", re.I
)
RAW_DECIMAL_REGEX = re.compile(r"\b\d{1,3}(?:,\d{2,3})*(?:\.\d{2})\b")
BALANCE_SIGN_REGEX = re.compile(r"(CR|DR)$", re.I)
ACCOUNT_REF_REGEX = re.compile(
    r"\b(?:[Ss]\d+|IFN\d+|ifn\d+|[Ff][Bb]\d+|[A-Za-z0-9]{8,25}|\d{6})\b"
)
INLINE_CREDIT_REGEX = re.compile(r"\b([\d,]+\.\d{2})CR\b", re.I)
CLEAN_NUM_REGEX = re.compile(r"[^\d.]")


def parse_float(value):
    if not value:
        return 0.0
    clean = CLEAN_NUM_REGEX.sub("", str(value))
    try:
        if clean and clean != ".":
            return float(clean)
    except (TypeError, ValueError):
        pass
    return 0.0


def clean_numeric_string(value):
    """
    Alias wrapper matching the core extraction strategy naming convention.
    Safely routes to parse_float.
    """
    return parse_float(value)


def normalize_date(date_str, target_fmt="%d-%m-%Y"):
    for fmt in (target_fmt, "%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return date_str
