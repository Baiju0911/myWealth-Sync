# backend/tracker/parsers/parsers_v1/utils/normalizer.py
import re
import decimal
from datetime import datetime
import json

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


def format_to_two_digits(val_str) -> str:
    if not val_str or str(val_str).strip() in ["", "-", "₹", "None"]:
        return ""

    # 🎯 Robust Number Extraction: Remove anything that isn't a digit, period, or minus sign
    clean = re.sub(r"[^\d.-]", "", str(val_str)).strip()

    try:
        # Enforces exactly 2 decimal places (e.g., 5000 -> 5000.00, 171.1 -> 171.10)
        return f"{float(clean):.2f}"
    except ValueError:
        # Final safety net fallback
        return str(val_str).strip()


def parse_meta_decimal(meta_summary, camel_key, snake_key):
    """Safely extracts and formats metadata numerical values."""
    extracted_val = meta_summary.get(camel_key)
    if extracted_val is None:
        extracted_val = meta_summary.get(snake_key, 0.00)
    return decimal.Decimal(str(extracted_val if extracted_val is not None else 0.00))


def normalize_row_date(raw_date, index):
    """Processes pipeline date formats to strict database signatures."""
    if not raw_date:
        raise ValueError(f"Missing date signature at row dataset index {index}")

    # Standardize string isolation across ISO format parameters
    clean_date_str = str(raw_date).split("T")[0].strip()

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(clean_date_str, fmt).date()
        except ValueError:
            continue

    raise ValueError(
        f"Row date signature structure '{raw_date}' could not be parsed to database schema specs."
    )


def sanitize_transaction_dates_via_template(intermediate_txns, template_obj):
    """
    🔒 TEMPLATE-DRIVEN DATE SANITIZATION & STANDARDIZATION:
    Extracts the first valid matching date signature pattern from a string,
    truncates duplicated layout overlaps, and transforms variations straight
    into a uniform DD-MM-YYYY format to ensure stable hashing and frontend grids.
    """
    date_regex_str = None

    if template_obj and template_obj.signature_json:
        try:
            sig_data = (
                json.loads(template_obj.signature_json)
                if isinstance(template_obj.signature_json, str)
                else template_obj.signature_json
            )
            date_regex_str = sig_data.get("regex_patterns", {}).get("DATE_MATCH")
        except Exception:
            pass

    if not date_regex_str:
        date_regex_str = r"\b\d{2}-\d{2}-\d{4}\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{4}/\d{2}/\d{2}\b|\b\d{2}/\\d{2}/\d{4}\b"
    else:
        if (
            r"\b\d{4}/\d{2}/\d{2}\b" not in date_regex_str
            and "YYYY/MM/DD" not in date_regex_str
        ):
            date_regex_str += r"|\b\d{4}/\d{2}/\d{2}\b"

    compiled_date_finder = re.compile(date_regex_str)

    print(f"\n🚀 [DATE SANITIZER RUN] Using Regex: {date_regex_str}")

    for idx, txn in enumerate(intermediate_txns):
        for date_key in ["post_date", "date", "value_date", "Txn Date"]:
            if date_key in txn and txn[date_key]:
                raw_val = str(txn[date_key]).strip()
                found_match = compiled_date_finder.search(raw_val)

                if found_match:
                    cleaned_val = found_match.group(0)
                    finalized_display_val = cleaned_val

                    # 🎯 THE TRANSFORMATION: Standardize all captured variants to DD-MM-YYYY
                    try:
                        if (
                            "/" in cleaned_val and cleaned_val.index("/") == 4
                        ):  # YYYY/MM/DD
                            dt_obj = datetime.strptime(cleaned_val, "%Y/%m/%d")
                            finalized_display_val = dt_obj.strftime("%d-%m-%Y")
                        elif (
                            "-" in cleaned_val and cleaned_val.index("-") == 4
                        ):  # YYYY-MM-DD
                            dt_obj = datetime.strptime(cleaned_val, "%Y-%m-%d")
                            finalized_display_val = dt_obj.strftime("%d-%m-%Y")
                        elif "/" in cleaned_val:  # DD/MM/YYYY -> Standardize to hyphens
                            dt_obj = datetime.strptime(cleaned_val, "%d/%m/%Y")
                            finalized_display_val = dt_obj.strftime("%d-%m-%Y")
                    except (ValueError, IndexError):
                        pass

                    # Only print if it actually changed or standardized the formatting layout
                    if raw_val != finalized_display_val:
                        # print(
                        #     f"🛠️ Row [{idx}] Key [{date_key}]: Format Adjusted to Hyphens!"
                        # )
                        # print(f"   ↳ 🔴 BEFORE: '{raw_val}'")
                        # print(f"   ↳ 🟢 AFTER:  '{finalized_display_val}'")

                        txn[date_key] = finalized_display_val
                else:
                    print(
                        f"⚠️ Row [{idx}] Key [{date_key}]: No pattern match found for '{raw_val}'"
                    )

    # print("🏁 [DATE SANITIZER END]\n")
    return intermediate_txns
