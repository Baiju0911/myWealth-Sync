from django.core.management.base import BaseCommand
from tracker.models import JournalEntry, StatementStagingLine
from tracker.classification.utils.upiparser import parse_upi_narration


class Command(BaseCommand):
    help = "Re-parses raw narrations from StatementStagingLine for suspense entries."

    def handle(self, *args, **options):
        entries = JournalEntry.objects.filter(account_id=99, is_reclassified=False)
        total_count = entries.count()
        self.stdout.write(f"Scanning {total_count} unclassified suspense entries...")

        row_ids = entries.values_list("row_identifier", flat=True).distinct()
        staging_map = dict(
            StatementStagingLine.objects.filter(row_identifier__in=row_ids).values_list(
                "row_identifier", "narration"
            )
        )

        entries_to_update = []
        batch_size = 1000

        for entry in entries:
            raw_narration = staging_map.get(entry.row_identifier, "")

            if raw_narration:
                parsed = parse_upi_narration(raw_narration)
                payee = parsed.get("payee")
                upi_ref = parsed.get("upi_ref")

                if payee:
                    current_remarks = (
                        entry.remarks if isinstance(entry.remarks, dict) else {}
                    )
                    current_remarks["payee"] = payee
                    if upi_ref:
                        current_remarks["upi_ref"] = upi_ref

                    amt = float(entry.debit if entry.debit > 0 else entry.credit)
                    is_outflow = entry.debit > 0
                    prefix = "By" if is_outflow else "To"

                    # Fix "to" vs "from" dynamically based on direction
                    direction_phrase = (
                        f"Paid ₹{amt:.2f} to {payee}"
                        if is_outflow
                        else f"Received ₹{amt:.2f} from {payee}"
                    )
                    ref_str = f" [Ref: {upi_ref}]" if upi_ref else ""

                    current_remarks["display_text"] = (
                        f"{prefix} Suspense Account | {direction_phrase}{ref_str} | Ingested via Staging"
                    )

                    entry.remarks = current_remarks
                    entries_to_update.append(entry)

                    if len(entries_to_update) >= batch_size:
                        JournalEntry.objects.bulk_update(entries_to_update, ["remarks"])
                        entries_to_update = []

        if entries_to_update:
            JournalEntry.objects.bulk_update(entries_to_update, ["remarks"])

        self.stdout.write(
            self.style.SUCCESS(f"Successfully re-parsed and updated entries!")
        )
