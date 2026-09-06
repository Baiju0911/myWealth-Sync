from datetime import datetime
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from tracker.emailIngest.parser import parse_rfc_or_iso_date


def safe_parse_datetime(date_val):
    """
    Parses SMS/Email timestamp strings and returns timezone-aware datetimes
    to eliminate Django Naive DateTime warnings.
    """
    current_tz = timezone.get_current_timezone()

    if not date_val:
        return timezone.now()

    if isinstance(date_val, datetime):
        return (
            timezone.make_aware(date_val, current_tz)
            if timezone.is_naive(date_val)
            else date_val
        )

    if isinstance(date_val, str):
        for fmt in (
            "%d-%m-%y %H:%M:%S",
            "%d-%m-%Y %H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                dt = datetime.strptime(date_val.strip(), fmt)
                return (
                    timezone.make_aware(dt, current_tz) if timezone.is_naive(dt) else dt
                )
            except ValueError:
                continue

        parsed = parse_datetime(date_val)
        if parsed:
            return (
                timezone.make_aware(parsed, current_tz)
                if timezone.is_naive(parsed)
                else parsed
            )

        parsed_custom = parse_rfc_or_iso_date(date_val)
        if isinstance(parsed_custom, datetime):
            return (
                timezone.make_aware(parsed_custom, current_tz)
                if timezone.is_naive(parsed_custom)
                else parsed_custom
            )

    return timezone.now()
