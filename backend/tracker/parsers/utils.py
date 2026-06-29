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
