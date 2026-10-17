# subledger/services/candidate_matcher_helpers.py
from datetime import date, timedelta
from decimal import Decimal
import re
from django.apps import apps
from django.db.models import Q


def resolve_bank_hint(asset_obj, bank_account_hint, is_cash_domain):
    """
    Extracts account number digits (e.g. '0060') from metadata for cash folios.
    """
    if (
        is_cash_domain
        and not bank_account_hint
        and isinstance(asset_obj.metadata_payload, dict)
    ):
        raw_hint = str(asset_obj.metadata_payload.get("bank_account_hint", "")).strip()
        digits = re.findall(r"\d+", raw_hint)
        if digits:
            return digits[-1]
        elif raw_hint:
            return raw_hint
    return bank_account_hint


def build_date_range_filter(doc_date, to_date, day_window):
    """
    Builds the Q filter for transaction date windowing.
    """
    if not doc_date:
        return Q()

    start_date = doc_date - timedelta(days=day_window)
    if to_date:
        end_date = to_date
    elif day_window >= 1825:
        end_date = date.today()
    else:
        end_date = doc_date + timedelta(days=day_window)

    return Q(transaction_date__gte=start_date, transaction_date__lte=end_date)


def get_bank_paired_row_identifiers(bank_account_hint):
    """
    Finds row_identifiers where the pairing bank leg belongs to the target account.
    Eliminates reliance on staging table account_id mismatches.
    """
    if not bank_account_hint:
        return None

    Account = apps.get_model("ledger", "Account")
    JournalEntry = apps.get_model("ledger", "JournalEntry")
    clean_hint = str(bank_account_hint).strip()

    acc_query = Q(account_number__icontains=clean_hint) | Q(name__icontains=clean_hint)
    if clean_hint.isdigit():
        acc_query |= Q(id=int(clean_hint))

    target_acc_ids = list(
        Account.objects.filter(acc_query).values_list("id", flat=True)
    )

    if not target_acc_ids:
        return []

    # Find row_identifiers where the real bank leg matches this account
    return list(
        JournalEntry.objects.filter(account_id__in=target_acc_ids)
        .exclude(account_id=99)
        .values_list("row_identifier", flat=True)
    )
