# tracker/parsers/utils.py
import hashlib
import re


class MatchWrapper:
    """
    ⚓ Standardizes layout variant regex groups to perfectly mirror
    core math engine loops, preventing index out of range breakdowns.
    """

    def __init__(self, date_str, narration, amount, balance, direction):
        self._data = (date_str, date_str, narration, amount, balance, direction)

    def group(self, idx):
        if idx < 1 or idx > len(self._data):
            return ""
        return self._data[idx - 1]


# ─── 🔒 CENTRAL SSOT HASH GUARDIAN ───
def generate_row_fingerprint(
    bank_id,
    account_id,
    debit,
    credit,
    running_balance,
    date_str,
    intraday_index=0,
):
    """
    🔒 UNIVERSAL LEDGER HASH GUARDIAN (BACKWARD COMPATIBLE):
    Accepts bank_id and account_id to maintain system compatibility, but anchors
    uniqueness strictly on core financial facts (Date, DR, CR, BAL, IDX).
    """

    # 1. 🔢 METRIC NORMALIZER
    def force_pure_numeric_str(v):
        if v is None:
            return "0.00"
        try:
            clean_v = (
                str(v)
                .replace(",", "")
                .replace("₹", "")
                .replace(" ", "")
                .replace("(", "")
                .replace(")", "")
                .strip()
            )
            if clean_v.lower().endswith("cr") or clean_v.lower().endswith("dr"):
                clean_v = clean_v[:-2].strip()
            if clean_v.startswith("-"):
                clean_v = clean_v.replace("-", "")

            # Defensive structural rescue
            clean_v = re.sub(r"[^0-9.]", "", clean_v)

            if not clean_v or clean_v.lower() in [
                "none",
                "null",
                "-",
                "cr",
                "dr",
                "nan",
            ]:
                return "0.00"
            return f"{float(clean_v):.2f}"
        except (ValueError, TypeError):
            return "0.00"

    fmt_debit = force_pure_numeric_str(debit)
    fmt_credit = force_pure_numeric_str(credit)
    fmt_balance = force_pure_numeric_str(running_balance)

    # 2. 📅 DATE FOUNDATION
    clean_date = str(date_str).strip().split("T")[0].split(" ")[0].strip()

    # 3. 🔗 UNIVERSAL PAYLOAD ASSEMBLE
    # 🎯 Removed bank_id and account_id from the text block to make it format-agnostic!
    payload = (
        f"DATE:{clean_date}||"
        f"DR:{fmt_debit}||"
        f"CR:{fmt_credit}||"
        f"BAL:{fmt_balance}||"
        f"IDX:{intraday_index}"
    )

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def generate_live_collision_hash(
    date_val,
    bank_val,
    account_last4,
    amount_val,
) -> str:
    """
    🔗 CROSS-STREAM COLLISION HASH (Statement PDF <-> iOS SMS <-> Gmail API)
    Deterministic hash using only universal common denominators:
    Date (YYYY-MM-DD) + Bank Identifier + Account Last 4 + Pure Signed Amount.
    """
    # 1. Normalize Date to YYYY-MM-DD
    if not date_val:
        clean_date = "NO_DATE"
    elif hasattr(date_val, "strftime"):
        clean_date = date_val.strftime("%Y-%m-%d")
    else:
        clean_date = str(date_val).strip().split("T")[0].split(" ")[0].strip()

    # 2. Normalize Bank (Support bank ID or bank Name/Code)
    clean_bank = re.sub(r"[^A-Za-z0-9]", "", str(bank_val or "DEFAULT_BANK")).upper()

    # 3. Normalize Account Last 4
    raw_acc = str(account_last4 or "").strip()
    clean_last4 = raw_acc[-4:] if len(raw_acc) >= 4 else raw_acc.zfill(4)

    # 4. Normalize Amount to strict 2-decimal string
    if amount_val is None:
        clean_amt = "0.00"
    else:
        try:
            amt_str = (
                str(amount_val)
                .replace(",", "")
                .replace("₹", "")
                .replace(" ", "")
                .strip()
            )
            clean_amt = f"{float(amt_str):.2f}"
        except (ValueError, TypeError):
            clean_amt = "0.00"

    composite_key = (
        f"DATE:{clean_date}||BANK:{clean_bank}||ACC:{clean_last4}||AMT:{clean_amt}"
    )
    return hashlib.sha256(composite_key.encode("utf-8")).hexdigest()


# ─── 🔍 DETERMINISTIC RAIL REFERENCE EXTRACTOR ───
def extract_rail_reference(text: str) -> dict:
    """
    Extracts deterministic rail anchors across all three ingestion streams:
    - 12-digit UPI RRN (e.g., 154857554492, 034955091376)
    - 16+ alphanumeric NEFT/RTGS UTR (e.g., CCIL250826107286)
    """
    if not text:
        return {"rrn": None, "utr": None, "anchor": None}

    clean_text = str(text).strip()

    # 1. 12-digit UPI Reference / RRN
    # Looks for 12 digits preceded by 'RRN', slashes, or word boundaries
    rrn_pattern = r"(?:RRN\s*[:\s]*|/|^|\b)(\d{12})(?:/|\b|$)"
    rrn_match = re.search(rrn_pattern, clean_text, re.IGNORECASE)
    rrn = rrn_match.group(1) if rrn_match else None

    # 2. NEFT / RTGS UTR (e.g., CCIL250826107286 or standard 16-character bank UTRs)
    utr_pattern = (
        r"(?:UTR(?:\s*No\.?)?[:\s]*|/|^|\b)([A-Z]{4}[0-9A-Z]{12,18})(?:/|\b|$)"
    )
    utr_match = re.search(utr_pattern, clean_text, re.IGNORECASE)
    utr = utr_match.group(1) if utr_match else None

    anchor = rrn or utr
    return {"rrn": rrn, "utr": utr, "anchor": anchor}


# ─── ⚖️ MULTI-TIER COLLISION DISAMBIGUATOR ───
def resolve_statement_collision(candidate_lines, payload):
    """
    Resolves identical same-day amount collisions using a strict hierarchy:
    Tier 1: Explicit Rail Anchor (RRN or UTR contained in narration)
    Tier 2: Mathematical Running Balance Match (Available Balance in iOS SMS)
    Tier 3: Substring Merchant Token Overlap (Gmail merchant string in statement)
    Tier 4: Chronological FIFO Fallback
    """
    if not candidate_lines:
        return None

    if len(candidate_lines) == 1:
        return candidate_lines[0]

    headers = payload.headers_json if isinstance(payload.headers_json, dict) else {}
    parsed = headers.get("parsed_summary", {}) if isinstance(headers, dict) else {}

    # Extract any explicit anchor from the payload
    donor_ref = (
        payload.upi_ref
        or headers.get("merge_details", {}).get("matched_rrn")
        or parsed.get("upi_ref")
        or parsed.get("utr_no")
    )
    if not donor_ref and getattr(payload, "raw_body_text", None):
        donor_ref = extract_rail_reference(payload.raw_body_text).get("anchor")

    # ── Tier 1: Deterministic Rail Anchor (RRN / UTR) ──
    if donor_ref:
        for candidate in candidate_lines:
            target_str = (
                f"{candidate.narration} "
                f"{candidate.cheque_ref_number or ''} "
                f"{candidate.bank_transaction_id or ''}"
            )
            if donor_ref in target_str:
                return candidate

    # ── Tier 2: Mathematical Running Balance Anchor (SMS Stream) ──
    # Safely retrieve balance across model attributes, parsed JSON, and headers
    donor_balance = (
        getattr(payload, "available_balance", None)
        or getattr(payload, "balance", None)
        or parsed.get("balance")
        or parsed.get("available_balance")
        or headers.get("balance")
    )

    if donor_balance is not None:
        try:
            d_bal = float(donor_balance)
            for candidate in candidate_lines:
                if candidate.running_balance is not None:
                    if abs(float(candidate.running_balance) - d_bal) < 0.05:
                        return candidate
        except (ValueError, TypeError):
            pass

    # ── Tier 3: Semantic Merchant Token Overlap (Gmail API Stream) ──
    merchant_raw = getattr(payload, "merchant", None) or parsed.get("merchant") or ""
    tokens = [
        t.lower()
        for t in re.findall(r"[A-Za-z0-9]+", str(merchant_raw))
        if len(t) > 3 and t.lower() not in ["bank", "payment", "direct", "india"]
    ]
    if tokens:
        best_candidate = None
        max_matches = 0
        for candidate in candidate_lines:
            c_text = (candidate.narration or "").lower()
            matches = sum(1 for tok in tokens if tok in c_text)
            if matches > max_matches:
                max_matches = matches
                best_candidate = candidate
        if best_candidate and max_matches > 0:
            return best_candidate

    # ── Tier 4: FIFO Fallback ──
    return candidate_lines[0]
