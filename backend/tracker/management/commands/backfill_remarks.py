from django.core.management.base import BaseCommand
from django.db.models import Q
from backend.tracker.models.models import JournalEntry, StatementStagingLine
from tracker.classification.remarks_service import generate_initial_remarks


class Command(BaseCommand):
    help = "Repairs or re-parses remarks on journal entries."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Forces re-parsing of ALL unclassified suspense entries regardless of current remarks.",
        )

    def handle(self, *args, **options):
        force = options["force"]

        if force:
            # Target all unclassified suspense entries
            target_entries = JournalEntry.objects.filter(
                account_id=99, is_reclassified=False
            )
            self.stdout.write(
                "FORCE MODE: Re-parsing all unclassified suspense entries..."
            )
        else:
            # Target missing, empty, dirty bank codes, OR leftover TRANSFER payees
            bank_tokens = [
                "YESB",
                "SBIN",
                "FDRL",
                "IDIB",
                "CNRB",
                "UBIN",
                "CSBK",
                "UTIB",
                "HDFC",
                "ICIC",
                "PYTM",
                "PAYTM",
                "SIBL",
                "NULL",
                "IMPS",
                "TRANSFER:",
                "TRANSFER",
            ]
            query = Q(remarks__isnull=True) | Q(remarks="") | Q(remarks={})
            for token in bank_tokens:
                query |= Q(remarks__payee=token)
                query |= Q(remarks__display_text__icontains=f"from {token}")
                query |= Q(remarks__display_text__icontains=f"to {token}")

            target_entries = JournalEntry.objects.filter(query)

        count = target_entries.count()

        if count == 0:
            self.stdout.write(
                self.style.SUCCESS("All rows have clean remarks! Nothing to update.")
            )
            return

        self.stdout.write(f"Processing {count} entries...")

        row_ids = target_entries.values_list("row_identifier", flat=True).distinct()
        staging_map = {
            s.row_identifier: s.narration
            for s in StatementStagingLine.objects.filter(
                row_identifier__in=row_ids
            ).only("row_identifier", "narration")
        }

        entries_to_update = []
        batch_size = 1000

        for entry in target_entries.iterator():
            narration = staging_map.get(entry.row_identifier, "")
            debit_val = float(entry.debit or 0.0)
            credit_val = float(entry.credit or 0.0)

            # Determine leg direction for double-entry balance assignment
            debit_rem, credit_rem = generate_initial_remarks(
                narration, debit_val, credit_val
            )

            # Assign appropriate leg payload based on entry side
            if entry.account_id == 5:
                # Bank account leg
                entry.remarks = credit_rem if debit_val > 0 else debit_rem
            else:
                # Category / Counter leg
                entry.remarks = debit_rem if debit_val > 0 else credit_rem

            entries_to_update.append(entry)

            if len(entries_to_update) >= batch_size:
                JournalEntry.objects.bulk_update(entries_to_update, ["remarks"])
                self.stdout.write(f"Updated batch of {len(entries_to_update)} rows...")
                entries_to_update = []

        if entries_to_update:
            JournalEntry.objects.bulk_update(entries_to_update, ["remarks"])

        self.stdout.write(self.style.SUCCESS(f"Successfully processed {count} rows!"))
