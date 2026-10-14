"""
tracker/classification/remarks_service.py - Text Enrichment & Pattern Engine
Encapsulates entity extraction, canonicalization, pattern generation,
and noise-free candidate suggestions.
"""

import re
from collections import Counter
from typing import Any, Dict, Optional, Tuple

from tracker.classification.utils.upiparser import parse_upi_narration
from tracker.constants import (
    ALL_CANDIDATE_BLACKLIST,
    BLACKLIST_TAGS,
    CORPORATE_NOISE_SUFFIXES,
    KNOWN_MERCHANTS,
    UPI_RAIL_TOKENS,
)


def canonicalize_merchant_token(token: str) -> str:
    """Dynamically canonicalizes brand variations without in-file hardcoding."""
    if not token:
        return "GENERAL_SUSPENSE"

    raw_upper = str(token).upper().strip()

    # 1. Direct match against dynamic KNOWN_MERCHANTS
    words = [
        w
        for w in re.sub(r"[^A-Z0-9\s]", " ", raw_upper).split()
        if w not in UPI_RAIL_TOKENS and not w.isdigit()
    ]

    for word in words:
        if word in KNOWN_MERCHANTS:
            return word

    # 2. Filter corporate/legal suffixes
    meaningful = [
        w
        for w in words
        if w not in CORPORATE_NOISE_SUFFIXES and w not in BLACKLIST_TAGS
    ]

    if meaningful:
        return "_".join(meaningful[:2])

    return words[0] if words else "GENERAL_SUSPENSE"


clean_and_canonicalize_token = canonicalize_merchant_token


def extract_merchant_from_upi_string(text: str) -> Optional[str]:
    """Extracts vendor tokens by splitting on rail delimiters (/ : - _)."""
    if not text:
        return None

    raw_upper = str(text).upper()
    segments = re.split(r"[/|:\-_]", raw_upper)

    for seg in segments:
        clean_seg = re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9\s]", " ", seg)).strip()
        if (
            not clean_seg
            or clean_seg.isdigit()
            or len(clean_seg) < 3
            or clean_seg in BLACKLIST_TAGS
            or clean_seg in UPI_RAIL_TOKENS
            or sum(c.isdigit() for c in clean_seg) >= 5
        ):
            continue

        return canonicalize_merchant_token(clean_seg)

    return None


def generate_cluster_pattern(narration: str, remarks_data: dict = None) -> str:
    """Generates the primary clustering anchor for a transaction line."""
    remarks_data = remarks_data or {}
    effective_narration = remarks_data.get("universal_narration") or narration or ""

    merchant = extract_merchant_from_upi_string(effective_narration)
    if merchant and merchant != "GENERAL_SUSPENSE":
        return merchant

    parsed = parse_upi_narration(effective_narration) or {}
    payee = parsed.get("payee") or remarks_data.get("payee")

    if payee:
        canonical_payee = canonicalize_merchant_token(str(payee))
        if canonical_payee and canonical_payee not in BLACKLIST_TAGS:
            return canonical_payee

    words = [
        w
        for w in re.sub(r"[^A-Z0-9\s]", " ", effective_narration.upper()).split()
        if len(w) >= 3 and w not in BLACKLIST_TAGS and not w.isdigit()
    ]
    if words:
        return canonicalize_merchant_token(words[0])

    return "GENERAL_SUSPENSE"


def generate_initial_remarks(
    narration: str,
    debit: float,
    credit: float,
    bank_name: str = "Bank A/c",
    target_category: str = "Suspense Account",
    universal_narration: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Builds structured JSON remarks payloads for debit and credit legs."""
    effective_narration = universal_narration or narration
    parsed_meta = parse_upi_narration(effective_narration) or {}
    payee = parsed_meta.get("payee")
    ref_no = parsed_meta.get("upi_ref")

    is_outflow = debit > 0
    amount_val = debit if is_outflow else credit
    amount_str = f"₹{amount_val:,.2f}"

    if payee:
        direction_phrase = (
            f"Paid {amount_str} to {payee}"
            if is_outflow
            else f"Received {amount_str} from {payee}"
        )
    else:
        direction_phrase = (
            f"Outflow of {amount_str}" if is_outflow else f"Inflow of {amount_str}"
        )

    action_str = f"{direction_phrase} [Ref: {ref_no}]" if ref_no else direction_phrase

    base_payload = {
        "payee": payee,
        "upi_ref": ref_no,
        "universal_narration": universal_narration or payee or narration,
        "user_note": None,
        "rule_code": None,
        "source": "STAGING_INGEST",
    }

    target_name = (
        target_category
        if target_category and target_category != "Suspense Account"
        else "Suspense Account"
    )

    debit_json = {
        **base_payload,
        "directional_prefix": "By",
        "target_account_name": target_name if is_outflow else bank_name,
        "display_text": (
            f"By {target_name} | {action_str} | Ingested via Staging"
            if is_outflow
            else f"By {bank_name} | {action_str} | Ingested via Staging"
        ),
    }

    credit_json = {
        **base_payload,
        "directional_prefix": "To",
        "target_account_name": bank_name if is_outflow else target_name,
        "display_text": (
            f"To {bank_name} | {action_str} | Ingested via Staging"
            if is_outflow
            else f"To {target_name} | {action_str} | Ingested via Staging"
        ),
    }

    return debit_json, credit_json


def extract_candidate_patterns_from_narrations(
    narrations: list[str], max_selectable: int = 15
) -> dict:
    """Extracts noise-free candidate patterns from transaction narrations."""
    if not narrations:
        return {"selectable_patterns": [], "disabled_patterns": []}

    candidate_counter = Counter()
    disabled_tokens = set()

    for raw_text in narrations:
        if not raw_text:
            continue

        clean_str = re.sub(
            r"\s+", " ", re.sub(r"[^A-Z0-9\s]", " ", str(raw_text).upper())
        ).strip()
        if not clean_str:
            continue

        tokens = clean_str.split()
        valid_tokens = []

        for token in tokens:
            if token in ALL_CANDIDATE_BLACKLIST:
                disabled_tokens.add(token)
                continue

            if (
                token.isdigit()
                or len(token) > 25
                or sum(c.isdigit() for c in token) >= 4
            ):
                continue

            valid_tokens.append(token)

        # 1. Heavily weight canonical brands
        for token in valid_tokens:
            if token in KNOWN_MERCHANTS:
                candidate_counter[token] += 10

        # 2. Clean compound combinations
        if 2 <= len(valid_tokens) <= 3:
            compound = " ".join(valid_tokens)
            if len(compound) >= 4:
                candidate_counter[compound] += 3

        for i in range(len(valid_tokens) - 1):
            gram_2 = f"{valid_tokens[i]} {valid_tokens[i+1]}"
            candidate_counter[gram_2] += 2

        # 3. Individual candidate tokens
        for token in valid_tokens:
            if len(token) >= 3:
                candidate_counter[token] += 1

    sorted_candidates = sorted(
        candidate_counter.keys(),
        key=lambda p: (-candidate_counter[p], -len(p.split()), -len(p)),
    )

    return {
        "selectable_patterns": sorted_candidates[:max_selectable],
        "disabled_patterns": sorted(list(disabled_tokens))[:12],
    }
