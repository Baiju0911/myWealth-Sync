import re

IGNORE_TOKENS = {
    "TRANSFER: NACH",
    "TRANSFER:",
    "TRANSFER",
    "NACH",
    "UPI",
    "IMPS",
    "NEFT",
    "POS",
    "MOB",
    "POSTRN",
    "POS TRN",
    "ATMTRN",
    "ATM TRN",
    "ATMREV",
    "ATM REV",
    "IBNTR",
    "CWD R",
    "CWDR",
    "PRCR",
    "CMN",
    "HO RTGS CELL",
    "RTGS",
    "DATACENTR",
    "DATACENTRE",
    "DATACENTR E",
    "MUMBAI SERVICE BRANCH",
    "SERVICE BRANCH",
    "BRANCH",
    "OWN ACCOUNT",
    "NULL",
    "UNKNOWN",
    "SELF",
    "NO REMARKS",
    "NOREMARKS",
    "KALLAMBALAM",
    "TRIVANDRUM",
    "THIRUVANANTHAPURAM",
    "KOCHIN",
    "MUMBAI",
    "FORT BRANCH",
}

# Trailing location / branch noise to strip off the end of payee names
BRANCH_SUFFIX_REGEX = r"\s+(?:MUMBAI|SERVICE BRANCH|BRANCH|FORT BRANCH|DATACENTRE|THIRUVANANTHAPURAM|TRIVANDRUM|KOCHIN|KALLAMBALAM)+$"


# def clean_payee_name_older(raw_name: str) -> str:
#     if not raw_name:
#         return ""

#     cleaned = re.sub(r"\s+", " ", str(raw_name)).strip()

#     # 1. Strip parenthetical prefix noise like "ID NO. (" -> "("
#     cleaned = re.sub(r"^ID\s+NO\.?\s*\(?", "", cleaned, flags=re.IGNORECASE).strip()
#     cleaned = cleaned.rstrip(")").strip()

#     # 2. Strip standard operation prefixes (including NACH DR, ACH DR, etc.)
#     cleaned = re.sub(
#         r"^(?:TRANSFER:?\s*NACH|NEFT\s+UTR:?|DEP\s+INT:?|INT\.?PD:?|TRANSFER:?\s*TO|NACH\s+DR:?|ACH\s+DR:?|DR:?|CR:?)\s*",
#         "",
#         cleaned,
#         flags=re.IGNORECASE,
#     ).strip()

#     # 3. Strip IFSC bank codes
#     cleaned = re.sub(r"\b[A-Z]{4}0+\d*\b", "", cleaned, flags=re.IGNORECASE).strip()

#     # 4. Strip embedded date stamps & standalone reference numbers (6+ digits)
#     cleaned = re.sub(r"\b\d{6,}\b", "", cleaned).strip()

#     # 5. Strip trailing branch/location noise (e.g., "BD CANARA ROBECO MF MUMBAI SERVICE BRANCH" -> "BD CANARA ROBECO MF")
#     cleaned = re.sub(BRANCH_SUFFIX_REGEX, "", cleaned, flags=re.IGNORECASE).strip()

#     # 6. Fix space-mangled words (e.g., "ZAM ZA M" -> "ZAM ZAM")
#     cleaned = re.sub(r"\b([A-Z]{1,3})\s+([A-Z]{1,3})\b", r"\1\2", cleaned)

#     return re.sub(r"\s+", " ", cleaned).strip()


def clean_payee_name(raw_name: str) -> str:
    if not raw_name:
        return ""

    cleaned = re.sub(r"\s+", " ", str(raw_name)).strip()

    # 1. Strip parenthetical prefix noise like "ID NO. (" -> "("
    cleaned = re.sub(r"^ID\s+NO\.?\s*\(?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = cleaned.rstrip(")").strip()

    # 2. Strip standard operation prefixes (including TRANSFER:, NACH DR:, etc.)
    cleaned = re.sub(
        r"^(?:TRANSFER:?\s*NACH:?|TRANSFER:?|NEFT\s+UTR:?|DEP\s+INT:?|INT\.?PD:?|NACH\s+DR:?|ACH\s+DR:?|DR:?|CR:?)\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    # 3. Strip IFSC bank codes
    cleaned = re.sub(r"\b[A-Z]{4}0+\d*\b", "", cleaned, flags=re.IGNORECASE).strip()

    # 4. Strip standalone 6+ digit reference numbers/dates
    cleaned = re.sub(r"\b\d{6,}\b", "", cleaned).strip()

    # 5. Strip trailing branch/location noise
    cleaned = re.sub(BRANCH_SUFFIX_REGEX, "", cleaned, flags=re.IGNORECASE).strip()

    # 6. Fix space-mangled words (e.g., "ZAM ZA M" -> "ZAM ZAM")
    cleaned = re.sub(r"\b([A-Z]{1,3})\s+([A-Z]{1,3})\b", r"\1\2", cleaned)

    return re.sub(r"\s+", " ", cleaned).strip()


def parse_upi_narration(narration: str) -> dict:
    if not narration or not str(narration).strip():
        return {"payee": None, "upi_ref": None}

    cleaned = re.sub(r"\s+", " ", str(narration)).strip()
    cleaned_upper = cleaned.upper()

    # 🟢 RULE 1: Direct structural match for Bank Interest
    if re.search(r"\bINT\.?PD\b|\bDEP\s*INT\b|\bINTEREST\s*CREDIT\b", cleaned_upper):
        return {
            "payee": "Bank Interest",
            "upi_ref": None,
        }

    # Extract Ref Number (10-12 digits)
    ref_match = re.search(r"\b(\d{10,12})\b", cleaned)
    extracted_ref = ref_match.group(1) if ref_match else None

    # 🟢 RULE 2: Extract Merchant inside Parentheses if available
    paren_match = re.search(r"\(([^)]+)\)", cleaned)
    if paren_match:
        cand_inside_paren = clean_payee_name(paren_match.group(1))
        if (
            len(cand_inside_paren) > 2
            and cand_inside_paren.upper() not in IGNORE_TOKENS
        ):
            return {
                "payee": cand_inside_paren,
                "upi_ref": extracted_ref,
            }

    # 🟢 RULE 3: Split by / for standard segment scanning
    parts = [p.strip() for p in cleaned.split("/") if p.strip()]

    for p in parts:
        candidate = clean_payee_name(p)
        cand_upper = candidate.upper().replace("_", " ")

        if (
            len(candidate) > 2
            and cand_upper not in IGNORE_TOKENS
            and not re.match(r"^\d+$", candidate)
        ):
            return {
                "payee": candidate,
                "upi_ref": extracted_ref,
            }

    return {"payee": None, "upi_ref": extracted_ref}
