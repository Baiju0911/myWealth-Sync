# tracker/emailIngest/watermark.py

from datetime import datetime, date, timezone as dt_timezone
from django.db.models import Max
from django.utils import timezone
from tracker.models.emailModels import RawEmailPayload
from tracker.models.models import StatementStagingLine, StatementIngestRegistry, Account


def get_latest_transaction_watermark(account_last4: str = None) -> datetime | None:
    """
    Finds the latest available watermark date across:
    1. RawEmailPayload where source='GMAIL_API' (email_date)
    2. StatementStagingLine (raw_statement_date)
    3. StatementIngestRegistry (report_to_date)

    Normalizes all datetimes to offset-naive UTC objects before comparison.
    """
    resolved_account_id = None
    if account_last4:
        acc_obj = Account.objects.filter(account_number=account_last4).first()
        if not acc_obj:
            acc_obj = Account.objects.filter(
                account_number__endswith=account_last4
            ).first()
        if acc_obj:
            resolved_account_id = acc_obj.id

    # Tier 1: Vault (RawEmailPayload)
    email_qs = RawEmailPayload.objects.filter(source="GMAIL_API")
    if account_last4:
        email_qs = email_qs.filter(account_last4=account_last4)
    latest_email = email_qs.aggregate(Max("email_date"))["email_date__max"]

    # Tier 2: Staging Lines (StatementStagingLine)
    staging_qs = StatementStagingLine.objects.all()
    if resolved_account_id:
        staging_qs = staging_qs.filter(account_id=resolved_account_id)
    latest_staging = staging_qs.aggregate(Max("raw_statement_date"))[
        "raw_statement_date__max"
    ]

    # Tier 3: Ingest Registry (StatementIngestRegistry)
    registry_qs = StatementIngestRegistry.objects.all()
    if resolved_account_id:
        registry_qs = registry_qs.filter(account_id=resolved_account_id)
    latest_registry = registry_qs.aggregate(Max("report_to_date"))[
        "report_to_date__max"
    ]

    print("\n" + "=" * 60)
    print("💧 [Multi-Tier Watermark Resolution Debug]:")
    print(f"  • Target Account Last4        : {account_last4 or 'ALL'}")
    print(f"  • Resolved Account ID         : {resolved_account_id or 'N/A'}")
    print(f"  • Tier 1 (RawEmailPayload Max): {latest_email}")
    print(f"  • Tier 2 (StagingLine Max)    : {latest_staging}")
    print(f"  • Tier 3 (Registry Report To) : {latest_registry}")

    candidate_dates = []

    for d in [latest_email, latest_staging, latest_registry]:
        if d is not None:
            # Standardize to timezone-naive datetimes in UTC
            if isinstance(d, datetime):
                if timezone.is_aware(d):
                    d = timezone.make_naive(d, dt_timezone.utc)
                candidate_dates.append(d)
            elif isinstance(d, date):
                candidate_dates.append(datetime.combine(d, datetime.min.time()))

    if not candidate_dates:
        print("  • Result                      : No DB dates found (Full Fetch)")
        print("=" * 60 + "\n")
        return None

    # Pick the LATEST (MAX) transaction date across all sources
    resolved_max = max(candidate_dates)

    print(f"  • Final Selected Watermark (MAX) : {resolved_max}")
    print("=" * 60 + "\n")

    return resolved_max
