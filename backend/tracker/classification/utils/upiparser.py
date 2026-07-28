# tracker/classification/utils/upiparser.py

import re

# Standard banking handles, system noise, and structural placeholders to strip out
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
    "KALLAMBALAM",  # Branch location token
    "TRIVANDRUM",
    "NRI",
}


def normalize_whitespace(text: str) -> str:
    """Collapses multiple spaces, tabs, and newlines into a single space."""
    return re.sub(r"\s+", " ", text).strip()


def clean_payee_name(raw_name: str) -> str:
    """
    Performs purely structural sanitization:
    - Strips action/system prefixes (TRANSFER:, NEFT TO, POS TRN, etc.)
    - Strips legal entity suffixes (PVT LTD, LIMITED, INC, LLP)
    - Strips leading amounts or attached digits (e.g., "50.54DHANYA" -> "DHANYA")
    - Strips trailing reference numbers or sequence IDs
    - Normalizes space-mangled words (e.g., "GA TEWAY" -> "GATEWAY")
    """
    if not raw_name:
        return ""

    # 1. Strip verb and system prefixes
    cleaned = re.sub(
        r"^(TRANSFER:|NEFT\s+TO\s+|NEFT\s+|MOB/|IMPS/|POS\s+TRN/?|ID\s+NO\.?\s*|TO\s+|FM\s+|FROM\s+|BY\s+)",
        "",
        raw_name,
        flags=re.IGNORECASE,
    ).strip()

    # 2. Fix known space-mangled words
    cleaned = re.sub(r"\bGA\s+TEWAY\b", "GATEWAY", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bTRANS\s+FER\b", "TRANSFER", cleaned, flags=re.IGNORECASE)

    # 3. Strip trailing legal corporate suffixes
    cleaned = re.sub(
        r"\b(PVT\.?\s*LTD\.?|PRIVATE\s+LIMITED|LIMITED|LTD\.?|INC\.?|LLP)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    # 4. Strip leading numbers attached to names (e.g. "50.54DHANYA" -> "DHANYA")
    cleaned = re.sub(r"^\d+[\.\d]*\s*", "", cleaned).strip()

    # 5. Strip trailing reference codes or numeric sequence IDs (5+ digits)
    cleaned = re.sub(r"\b\d{5,}\b", "", cleaned).strip()

    return normalize_whitespace(cleaned)


def parse_upi_narration(narration: str) -> dict:
    """
    Extracts raw structural metadata (payee string & reference ID) from bank narrations.
    Categorization and rule learning are delegated to the ClassificationRule engine.
    """
    if not narration:
        return {"payee": None, "upi_ref": None}

    cleaned = normalize_whitespace(narration)

    # ------------------------------------------------------------------
    # 1. Bank Interest & Service Charges / Tax (Standard Bank Transactions)
    # ------------------------------------------------------------------
    if re.search(r"\bINT\.?PD\b|\bINTEREST CREDIT\b", cleaned, re.IGNORECASE):
        return {"payee": "Savings Bank Interest", "upi_ref": None}

    if re.search(
        r"\bRETN CHRG\b|\bBANK CHARGES\b|\bS\.?\s*TAX\b|\bACCOUNT\s*TRANS\s*FER\s*CHARGES\b",
        cleaned,
        re.IGNORECASE,
    ):
        return {"payee": "Bank Service Charges", "upi_ref": None}

    # ------------------------------------------------------------------
    # 2. NACH / Direct Debits (Generic Segment Extraction)
    # ------------------------------------------------------------------
    if "NACH" in cleaned.upper() or "DATACENTR" in cleaned.upper():
        nach_ref = next(
            (
                p.strip()
                for p in cleaned.split("/")
                if re.match(r"^\d{10,12}$", p.strip())
            ),
            None,
        )

        parts = [p.strip() for p in cleaned.split("/") if p.strip()]
        for p in parts:
            p_clean = clean_payee_name(p)
            if len(p_clean) > 3 and not re.match(
                r"^(TRANSFER|NACH|SIBL\d+|DATACENTR|\d+)$", p_clean, re.IGNORECASE
            ):
                return {"payee": p_clean, "upi_ref": nach_ref}

        return {"payee": "NACH Direct Debit", "upi_ref": nach_ref}

    # ------------------------------------------------------------------
    # 3. IMPS Transfers
    # ------------------------------------------------------------------
    imps_match = re.search(
        r"IMPS/(?:IFSC/)?(\d{10,12})/([^/]+)", cleaned, re.IGNORECASE
    )
    if imps_match:
        ref_no = imps_match.group(1)
        payee = clean_payee_name(imps_match.group(2))
        return {"payee": payee, "upi_ref": ref_no}

    # ------------------------------------------------------------------
    # 4. NEFT Transfers
    # ------------------------------------------------------------------
    if "NEFT" in cleaned.upper():
        neft_match = re.search(
            r"NEFT\s+(?:UTR:?\s*\w+\s*//)?(?:[^/]+/)*NEFT\s+TO\s+([^/]+)",
            cleaned,
            re.IGNORECASE,
        )
        if neft_match:
            payee = clean_payee_name(neft_match.group(1))
            return {"payee": payee, "upi_ref": None}

    # ------------------------------------------------------------------
    # 5. POS Card Terminal Debits
    # ------------------------------------------------------------------
    if cleaned.startswith("POS TRN"):
        raw_pos = re.sub(
            r"POS\s+TRN/?|ID\s+NO\.?\s*|\(?|\)?|PRCR/.*|CMN/.*|\d{10,}.*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        parts = [p.strip() for p in raw_pos.split("/") if p.strip()]
        if parts:
            vendor_name = clean_payee_name(parts[0])
            return {"payee": vendor_name, "upi_ref": None}

    # ------------------------------------------------------------------
    # 6. MOB & TRANSFER Direct Bank Narrations
    # ------------------------------------------------------------------
    if cleaned.startswith("MOB/") or cleaned.startswith("TRANSFER:"):
        raw_clean = re.sub(r"^TRANSFER:\s*", "", cleaned, flags=re.IGNORECASE)
        parts = [normalize_whitespace(p) for p in raw_clean.split("/") if p.strip()]

        mob_ref = next((p for p in parts if re.match(r"^\d{10,12}$", p)), None)

        for p in parts:
            p_cleaned_name = clean_payee_name(p)
            p_upper = p_cleaned_name.upper()
            p_compressed = re.sub(r"\s+", "", p_upper)

            if (
                len(p_cleaned_name) > 2
                and p_upper not in IGNORED_PAYEE_TOKENS
                and p_compressed not in IGNORED_PAYEE_TOKENS
                and not re.match(r"^\d+$", p_cleaned_name)
            ):
                return {"payee": p_cleaned_name, "upi_ref": mob_ref}

    # ------------------------------------------------------------------
    # 7. Standard UPI Delimited Parsing
    # ------------------------------------------------------------------
    ref_match = re.search(r"\b(\d{12})\b", cleaned)
    upi_ref = ref_match.group(1) if ref_match else None

    # Sanitize known noise placeholders before splitting by slashes
    cleaned_delimited = re.sub(
        r"/(NULL|NONE|NA|NO REMARKS?|PAYMENT FROM UPI|PAY TO MERCHANT)\b",
        "/",
        cleaned,
        flags=re.IGNORECASE,
    )
    parts = [normalize_whitespace(p) for p in cleaned_delimited.split("/") if p.strip()]

    fallback_payee = None

    for p in parts:
        p_clean = clean_payee_name(p)
        p_upper = p_clean.upper()
        p_compressed = re.sub(r"\s+", "", p_upper)

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

        if not fallback_payee:
            fallback_payee = p_clean

    final_payee = fallback_payee

    if final_payee:
        final_payee = re.sub(
            r"\s+[B|UPI]$", "", final_payee, flags=re.IGNORECASE
        ).strip()
        final_payee = clean_payee_name(final_payee)

        if (
            final_payee.upper() in IGNORED_PAYEE_TOKENS
            or re.sub(r"\s+", "", final_payee.upper()) in IGNORED_PAYEE_TOKENS
        ):
            final_payee = None

    return {
        "payee": final_payee,
        "upi_ref": upi_ref,
    }
