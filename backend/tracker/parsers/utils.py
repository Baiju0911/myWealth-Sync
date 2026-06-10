# tracker/utils.py
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


def generate_row_fingerprint1(
    bank_id,
    account_id,
    narration,
    cheque_ref,
    amount,
    running_balance,
    debit,
    credit,
    date_str,
):
    """
    🔒 CENTRAL SSOT HASH GUARDIAN (STRICT BALANCE ANCHOR CONTRACT):
    Enforces absolute tracking stability by linking to purified financial metrics.
    Guarantees that both Amount and Running Balance are stripped of commas, spaces,
    and currency symbols, forcing a uniform string format with exactly 2 decimal values.
    """

    # 1. 🧼 ADVANCED DE-SPACING & TEXT FLATTENING
    clean_narration = str(narration or "").strip().upper()
    clean_narration = (
        clean_narration.replace("\n", " ")
        .replace("\r", " ")
        .replace("\t", " ")
        .replace('"', "")
        .replace("'", "")
    )

    # Split words, strip structural display tags ([TFR], Ref:)
    fragments = clean_narration.split(" ")
    clean_fragments = [
        f
        for f in fragments
        if not (f.startswith("[") and f.endswith("]")) and not f.startswith("REF:")
    ]

    # Force single-space character uniformity
    clean_narration = " ".join(" ".join(clean_fragments).split()).strip()

    # 2. 🔢 HARDENED FINANCIAL NUMBER HYDRATOR (NO COMMAS, FORCE 2 DECIMALS)
    def force_pure_numeric_str(v):
        if v is None:
            return "0.00"
        try:
            # 🧼 Strip away commas, spaces, raw rupee characters, or brackets
            clean_v = (
                str(v)
                .replace(",", "")
                .replace("₹", "")
                .replace(" ", "")
                .replace("(", "")
                .replace(")", "")
                .strip()
            )
            # Remove trailing string indicators sometimes appended by parsers
            if clean_v.lower().endswith("cr") or clean_v.lower().endswith("dr"):
                clean_v = clean_v[:-2].strip()

            if clean_v.startswith("-"):
                clean_v = clean_v.replace("-", "")

            if not clean_v or clean_v.lower() in ["none", "null", "-", "cr", "dr"]:
                return "0.00"

            # 🎯 Round and output exactly to a clean '0.00' precision string
            return f"{float(clean_v):.2f}"
        except (ValueError, TypeError):
            return "0.00"

    # Strict casting for both critical financial columns
    fmt_amount = force_pure_numeric_str(amount)
    fmt_balance = force_pure_numeric_str(running_balance)

    # 3. 📅 DATE EXTRACTION STANDARD (YYYY-MM-DD)
    clean_date = str(date_str).strip().split("T")[0].split(" ")[0].strip()

    # 4. 🔗 ASSEMBLE IMMUTABLE RECORD PAYLOAD WITH RUNNING BALANCE
    # By feeding the highly sanitized fmt_balance here, identical rows on the same
    # day will split uniquely because their running balances differ naturally.
    payload = (
        f"DATE:{clean_date}||"
        f"BANK:{str(bank_id).strip()}||"
        f"ACC:{str(account_id).strip()}||"
        f"NARR:{clean_narration}||"
        f"AMT:{fmt_amount}||"
        f"BAL:{fmt_balance}"
    )
    if (
        "AMAZON" in clean_narration
        or "NEFT" in clean_narration
        or "BAIJU" in clean_narration
        or "NFT/BAIJU S/SBIN422256225077/SBI TRF" in clean_narration
    ):
        row_hex = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        print("\n📡 ─── [SSOT CORE PAYLOAD GENERATOR RADAR] ───")
        print(f" 🗓️  Raw Date Str Input : {date_str} -> Processed: {clean_date}")
        print(
            f" 🏦 IDs Context          : Bank ID: {bank_id} | Account ID: {account_id}"
        )
        print(f" 📝 Clean Narration     : '{clean_narration}'")
        print(
            f" 💰 Financial Metrics   : Amount: {fmt_amount} | Balance: {fmt_balance}"
        )
        print(f' 📦 RAW STR PAYLOAD     : "{payload}"')
        print(f" 🔒 CALCULATED OUTPUT HEX: {row_hex}")
        print("───────────────────────────────────────────────\n")

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def generate_row_fingerprint(
    bank_id,
    account_id,
    narration,
    cheque_ref,
    amount,
    running_balance,
    debit,
    credit,
    date_str,
):
    """
    🔒 CENTRAL SSOT HASH GUARDIAN (STRICT STRING ANCHOR CONTRACT):
    Normalizes parsing variants by formatting raw fields into standardized,
    un-mutated string components.
    """

    # 1. 🧼 TEXT DE-SPACING
    clean_narration = str(narration or "").strip().upper()
    clean_narration = (
        clean_narration.replace("\n", " ")
        .replace("\r", " ")
        .replace("\t", " ")
        .replace('"', "")
        .replace("'", "")
    )
    fragments = clean_narration.split(" ")
    clean_fragments = [
        f
        for f in fragments
        if not (f.startswith("[") and f.endswith("]")) and not f.startswith("REF:")
    ]
    clean_narration = " ".join(" ".join(clean_fragments).split()).strip()

    # 2. 🔢 METRIC NORMALIZER
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
            if not clean_v or clean_v.lower() in ["none", "null", "-", "cr", "dr"]:
                return "0.00"
            return f"{float(clean_v):.2f}"
        except (ValueError, TypeError):
            return "0.00"

    fmt_amount = force_pure_numeric_str(amount)
    fmt_balance = force_pure_numeric_str(running_balance)

    # 3. 📅 DATE FOUNDATION
    clean_date = str(date_str).strip().split("T")[0].split(" ")[0].strip()

    # 4. 🔗 PAYLOAD ASSEMBLE
    payload = (
        f"DATE:{clean_date}||"
        f"BANK:{str(bank_id).strip()}||"
        f"ACC:{str(account_id).strip()}||"
        f"NARR:{clean_narration}||"
        f"AMT:{fmt_amount}||"
        f"BAL:{fmt_balance}"
    )

    row_hex = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    # if "BAIJU" in clean_narration or "NFT" in clean_narration:
    #     print("\n📡 ─── [SSOT CORE PAYLOAD GENERATOR RADAR] ───")
    #     print(f' 📦 RAW STR PAYLOAD      : "{payload}"')
    #     print(f" 🔒 CALCULATED OUTPUT HEX: {row_hex}")
    #     print("───────────────────────────────────────────────\n")

    return row_hex
