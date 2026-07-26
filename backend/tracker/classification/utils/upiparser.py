# tracker/classification/utils/upiparser.py

import re

# Bank handles, system noise, and placeholders to strip out
IGNORED_PAYEE_TOKENS = {
    "NULL",
    "NONE",
    "NA",
    "NO REMARKS",
    "NOREMARKS",
    "UNKNOWN",
    "PAYMENT FROM UPI",
    "PAY TO MERCHANT",
    "PAYMENT TO",
    "TRANSFER",
    "BALANCE",
    "OW N ACCOUNT",
    "OWN ACCOUNT",
    "FDRL",
    "YESB",
    "ICIC",
    "HDFC",
    "SBIN",
    "UTIB",
    "PYTM",
    "PAYTM",
    "KKBK",
    "BARB",
    "CNRB",
    "PUNB",
    "IOBA",
    "CBIN",
    "MAHB",
    "IDIB",
    "SIBL",
    "CSBK",
    "UBIN",
    "SBIP",
    "IPPB",
    "PAYU",
    "AXIS",
    "CITI",
    "SCBL",
}

# Entity keywords (in standard form)
VENDOR_KEYWORDS = [
    "HOSPITAL",
    "PHARMACY",
    "STORES",
    "SUPERMARKET",
    "BAKERY",
    "PETROL",
    "FUELS",
    "SERVICES",
    "CAFE",
    "RESTAURANT",
    "ENTERPRISES",
    "TRADERS",
    "POTTY",
    "JEWELLERS",
    "LABS",
    "CLINIC",
    "MART",
    "AGENCIES",
    "MEDICAL",
    "HOTEL",
    "TEXTILES",
    "AUTO",
    "MOTORS",
    "VEGETABLES",
    "TOLL",
    "CINEMAS",
    "EAGLE",
    "GAS",
    "BAKERY",
    "FASHION",
    "JEWELLERY",
    "RETAIL",
]


def normalize_whitespace(text: str) -> str:
    """Collapses multiple spaces, tabs, and newlines into a single space."""
    return re.sub(r"\s+", " ", text).strip()


def parse_upi_narration(narration: str) -> dict:
    if not narration:
        return {"payee": None, "upi_ref": None}

    # Normalize all spacing upfront
    cleaned = normalize_whitespace(narration)

    # 1. Non-UPI Pattern: Bank Interest Credit / Service Charges
    if re.search(r"\bINT\.?PD\b|\bINTEREST CREDIT\b", cleaned, re.IGNORECASE):
        return {"payee": "Savings Bank Interest", "upi_ref": None}

    if re.search(r"\bRETN CHRG\b|\bBANK CHARGES\b", cleaned, re.IGNORECASE):
        return {"payee": "Bank Service Charges", "upi_ref": None}

    # 2. Non-UPI Pattern: NACH / Mutual Funds
    nach_match = re.search(
        r"NACH DR\s+([A-Z0-9\s]+?)(?=/|\d|\bDATACENTR)", cleaned, re.IGNORECASE
    )
    if nach_match:
        payee = normalize_whitespace(nach_match.group(1))
        payee = re.sub(r"\d+.*$", "", payee).strip()
        return {"payee": f"NACH - {payee}", "upi_ref": None}

    # 3. Non-UPI Pattern: IMPS Transfers
    imps_match = re.search(
        r"IMPS/(?:IFSC/)?(\d{10,12})/([^/]+)", cleaned, re.IGNORECASE
    )
    if imps_match:
        ref_no = imps_match.group(1)
        payee = normalize_whitespace(imps_match.group(2))
        return {"payee": payee, "upi_ref": ref_no}

    # 4. Non-UPI Pattern: MOB Transfers
    if cleaned.startswith("MOB/"):
        parts = [normalize_whitespace(p) for p in cleaned.split("/") if p.strip()]
        mob_ref = next((p for p in parts if re.match(r"^\d{10,12}$", p)), None)
        for p in parts:
            p_upper = p.upper()
            if (
                len(p) > 2
                and p_upper
                not in {
                    "MOB",
                    "RETURN",
                    "IMPS",
                    "TRANSFER",
                    "OW N ACCOUNT",
                    "OWN ACCOUNT",
                }
                and not re.match(r"^\d+$", p)
            ):
                return {"payee": p, "upi_ref": mob_ref}

    # 5. Standard UPI Parsing with Dual-Pass Whitespace Matching
    ref_match = re.search(r"\b(\d{12})\b", cleaned)
    upi_ref = ref_match.group(1) if ref_match else None

    # Sanitize known noise tokens before splitting
    cleaned_delimited = re.sub(
        r"/(NULL|NONE|NA|NO REMARKS?|PAYMENT FROM UPI|PAY TO MERCHANT)\b",
        "/",
        cleaned,
        flags=re.IGNORECASE,
    )
    parts = [normalize_whitespace(p) for p in cleaned_delimited.split("/") if p.strip()]

    candidate_payee = None
    fallback_payee = None

    for p in parts:
        p_clean = normalize_whitespace(p)
        p_upper = p_clean.upper()

        # Condensed version (strips ALL spaces) for Pass 2 keyword check
        p_compressed = re.sub(r"\s+", "", p_upper)

        # Skip technical codes, bank handles, VPAs, references, long hashes
        if (
            len(p_clean) < 3
            or (p_upper.startswith("UPI") and len(p_clean) < 6)
            or "@" in p_clean
            or p_clean == upi_ref
            or p_upper in IGNORED_PAYEE_TOKENS
            or p_compressed in IGNORED_PAYEE_TOKENS
            or re.match(r"^[A-Z0-9]{15,}$", p_upper)
            or re.match(r"^\d{12,}$", p_clean)
        ):
            continue

        # Strip action verb prefixes
        verb_stripped = re.sub(
            r"^(TO|BY|FM|FROM|PAY TO|PAY TO MERCHANT)\s+",
            "",
            p_clean,
            flags=re.IGNORECASE,
        ).strip()

        if verb_stripped and verb_stripped.upper() not in IGNORED_PAYEE_TOKENS:
            p_clean = verb_stripped
            p_upper = p_clean.upper()
            p_compressed = re.sub(r"\s+", "", p_upper)

        # High priority check (Pass 1 & Pass 2): Check normal and compressed keyword match
        has_keyword_match = any(
            kw in p_upper or kw in p_compressed for kw in VENDOR_KEYWORDS
        )

        if has_keyword_match:
            candidate_payee = p_clean
            break

        if not fallback_payee:
            fallback_payee = p_clean

    final_payee = candidate_payee or fallback_payee

    # Final cleanup: Strip trailing app indicators (" B", " UPI") & normalize spaces
    if final_payee:
        final_payee = re.sub(
            r"\s+[B|UPI]$", "", final_payee, flags=re.IGNORECASE
        ).strip()
        final_payee = normalize_whitespace(final_payee)

        if (
            final_payee.upper() in IGNORED_PAYEE_TOKENS
            or re.sub(r"\s+", "", final_payee.upper()) in IGNORED_PAYEE_TOKENS
        ):
            final_payee = None

    return {
        "payee": final_payee,
        "upi_ref": upi_ref,
    }
