# tracker/classification/engine/contra_helpers.py
from __future__ import annotations
import re
from collections import defaultdict
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Set
from django.apps import apps


def parse_txn_date(val: Any) -> Optional[date]:
    if not val:
        return None
    if hasattr(val, "date"):
        return val.date()
    if isinstance(val, datetime):
        return val.date()
    try:
        return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def extract_candidate_ref_tokens(narration: str) -> Set[str]:
    """Extracts RRNs, bank CBS transfer tokens, and cheque references."""
    if not narration:
        return set()

    tokens = set()
    upper = narration.upper()

    # 1. 12-digit standard RRN / UTR
    for m in re.finditer(r"\b(\d{12})\b", upper):
        tokens.add(m.group(1))

    # 2. Bank internal transfer IDs like S70501784
    for m in re.finditer(r"\b([A-Z]\d{7,10})\b", upper):
        tokens.add(m.group(1))

    # 3. CBS transaction references like FTB..., SIB...
    for m in re.finditer(r"\b(FT[A-Z0-9]{8,14})\b", upper):
        tokens.add(m.group(1))

    return tokens


def resolve_cross_account_contra_map(
    row_ids: List[str], staging_lines: List[Any]
) -> Dict[str, Any]:
    """Matches self-transfers between internal accounts."""
    if not staging_lines:
        return {}

    Account = apps.get_model("ledger", "Account")
    StatementStagingLine = apps.get_model("ledger", "StatementStagingLine")

    accounts_map = {}
    for acc in Account.objects.exclude(id=99):
        acc_name = getattr(acc, "name", None) or getattr(acc, "bank_name", "Bank")
        acc_num = str(getattr(acc, "account_number", "") or "")
        last4 = acc_num[-4:] if len(acc_num) >= 4 else str(acc.id)
        accounts_map[acc.id] = {"name": acc_name, "last4": last4}

    active_amounts = set()
    for stg in staging_lines:
        amt = float(
            getattr(stg, "amount", 0)
            or getattr(stg, "debit", 0)
            or getattr(stg, "credit", 0)
            or 0.0
        )
        if amt > 0:
            active_amounts.add(amt)

    if not active_amounts:
        return {}

    counterpart_lines = list(
        StatementStagingLine.objects.filter(
            account_id__in=accounts_map.keys(),
            amount__in=active_amounts,
        ).values(
            "id",
            "row_identifier",
            "account_id",
            "raw_narration",
            "amount",
            "debit",
            "credit",
            "raw_statement_date",
            "cheque_ref_number",
            "live_upi_rrn",
        )
    )

    amount_groups = defaultdict(list)
    for line in counterpart_lines:
        narr = line.get("raw_narration") or ""
        tokens = extract_candidate_ref_tokens(narr)
        if line.get("live_upi_rrn"):
            tokens.add(str(line["live_upi_rrn"]).strip())
        if line.get("cheque_ref_number"):
            tokens.add(str(line["cheque_ref_number"]).strip())

        line["tokens"] = tokens
        line["parsed_date"] = parse_txn_date(line.get("raw_statement_date"))
        amount_groups[float(line.get("amount") or 0.0)].append(line)

    contra_map = {}
    paired_row_ids = set()

    for amt, group in amount_groups.items():
        if len(group) < 2:
            continue

        debit_candidates = [
            l
            for l in group
            if float(l.get("debit") or 0) > 0
            and l["row_identifier"] not in paired_row_ids
        ]
        credit_candidates = [
            l
            for l in group
            if float(l.get("credit") or 0) > 0
            and l["row_identifier"] not in paired_row_ids
        ]

        for deb in debit_candidates:
            if deb["row_identifier"] in paired_row_ids:
                continue

            for cred in credit_candidates:
                if cred["row_identifier"] in paired_row_ids:
                    continue

                if deb["account_id"] == cred["account_id"]:
                    continue

                if deb["parsed_date"] and cred["parsed_date"]:
                    if abs((deb["parsed_date"] - cred["parsed_date"]).days) > 2:
                        continue

                shared_tokens = deb["tokens"].intersection(cred["tokens"])
                name_match = (
                    "BAIJU" in (deb.get("raw_narration") or "").upper()
                    or "SELF" in (deb.get("raw_narration") or "").upper()
                ) and (
                    "BAIJU" in (cred.get("raw_narration") or "").upper()
                    or "SELF" in (cred.get("raw_narration") or "").upper()
                )

                if shared_tokens or name_match:
                    ref_anchor = (
                        next(iter(shared_tokens)) if shared_tokens else "SELF_TRANSFER"
                    )
                    src = accounts_map.get(
                        deb["account_id"], {"name": "Account", "last4": "XXXX"}
                    )
                    dst = accounts_map.get(
                        cred["account_id"], {"name": "Account", "last4": "XXXX"}
                    )
                    badge_text = f"{src['name']} (..{src['last4']}) ➔ {dst['name']} (..{dst['last4']})"

                    contra_map[deb["row_identifier"]] = {
                        "is_self_transfer": True,
                        "contra_type": "INTERNAL_TRANSFER",
                        "ref_id": ref_anchor,
                        "direction_leg": "OUTFLOW",
                        "from_account_name": src["name"],
                        "from_account_last4": src["last4"],
                        "to_account_name": dst["name"],
                        "to_account_last4": dst["last4"],
                        "display_badge": badge_text,
                    }
                    contra_map[cred["row_identifier"]] = {
                        "is_self_transfer": True,
                        "contra_type": "INTERNAL_TRANSFER",
                        "ref_id": ref_anchor,
                        "direction_leg": "INFLOW",
                        "from_account_name": src["name"],
                        "from_account_last4": src["last4"],
                        "to_account_name": dst["name"],
                        "to_account_last4": dst["last4"],
                        "display_badge": badge_text,
                    }
                    paired_row_ids.add(deb["row_identifier"])
                    paired_row_ids.add(cred["row_identifier"])
                    break

    return contra_map
