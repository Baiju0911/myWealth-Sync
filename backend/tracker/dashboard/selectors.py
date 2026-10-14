from decimal import Decimal
from collections import defaultdict
from django.db.models import Count, Sum, Min, Max
from django.db.models.expressions import RawSQL
from ..models.models import JournalEntry


class DashboardSelectors:
    @staticmethod
    def get_date_bounds(bank_account_id=3):
        """
        Retrieves the overall minimum and maximum transaction dates for the specified account.
        """
        bounds = JournalEntry.objects.filter(account_id=bank_account_id).aggregate(
            min_date=Min("transaction_date"), max_date=Max("transaction_date")
        )
        return {
            "min_date": (
                bounds["min_date"].strftime("%Y-%m-%d") if bounds["min_date"] else None
            ),
            "max_date": (
                bounds["max_date"].strftime("%Y-%m-%d") if bounds["max_date"] else None
            ),
        }

    @staticmethod
    def get_category_breakdowns(
        bank_account_id=3, taxonomy_account_id=99, from_date=None, to_date=None
    ):
        """
        Aggregates Taxonomy Breakdown Matrix adhering strictly to the 3-Stage Pipeline:
        Stage 1: Raw Bank Ingestion
        Stage 2: Category & Rule Normalization (AssetCategory / TaxonomyTree)
        Stage 3: Double-Entry Balancing & Reclassification (Node 99 -> Headers -> Subledger Folios)

        Total transaction count and volume are conserved:
        - Unmapped transactions sit under their resolved GL head or Suspense Account.
        - Mapped transactions are credited to their target asset folio's canonical GL subcategory.
        - Transactions never disappear, duplicate, or desync across statements.
        """
        from decimal import Decimal
        from collections import defaultdict
        from django.db.models import Count, Sum
        from django.db.models.expressions import RawSQL
        from tracker.models.subledger import AssetCategory, AssetTransactionMapping

        def resolve_subcat_name(val):
            if not val:
                return ""
            if isinstance(val, str):
                return val.strip()
            return (
                getattr(val, "subcategory", None)
                or getattr(val, "name", None)
                or getattr(val, "title", None)
                or str(val)
            ).strip()

        # -------------------------------------------------------------
        # 1. Base Node 99 Query (Conserving Bank Leg vs Node 99 Balance)
        # -------------------------------------------------------------
        qs = JournalEntry.objects.filter(account_id=taxonomy_account_id)

        if int(bank_account_id) != int(taxonomy_account_id):
            bank_row_ids = JournalEntry.objects.filter(
                account_id=bank_account_id
            ).values_list("row_identifier", flat=True)
            qs = qs.filter(row_identifier__in=bank_row_ids)

        if from_date:
            qs = qs.filter(transaction_date__gte=from_date)
        if to_date:
            qs = qs.filter(transaction_date__lte=to_date)

        # -------------------------------------------------------------
        # 2. Stage 2 Canonical Reference Lookup (AssetCategory Engine)
        # -------------------------------------------------------------
        category_meta = {
            cat.code: {
                "root_category": cat.default_taxonomy_category or "Asset",
                "default_subcategory": cat.default_taxonomy_subcategory
                or "Uncategorized Asset",
            }
            for cat in AssetCategory.objects.filter(is_active=True)
        }

        # -------------------------------------------------------------
        # 3. Subledger Mappings Resolution
        # -------------------------------------------------------------
        mapped_mappings = AssetTransactionMapping.objects.select_related(
            "asset"
        ).exclude(row_identifier__isnull=True)

        subledger_map = {}
        for m in mapped_mappings:
            if m.row_identifier and m.asset:
                raw_cat_code = resolve_subcat_name(getattr(m.asset, "category", None))
                meta = category_meta.get(raw_cat_code, {})

                # Resolve Root Class: Always 'Asset' / 'Income' / 'Expense'
                resolved_root = meta.get("root_category", "Asset")

                # Resolve Subcategory Head (Folio override -> Category Default fallback)
                raw_sub = getattr(m.asset, "subcategory", None) or getattr(
                    m.asset, "linked_gl_account", None
                )
                clean_sub = resolve_subcat_name(raw_sub) or meta.get(
                    "default_subcategory", "Uncategorized Asset"
                )

                subledger_map[str(m.row_identifier)] = {
                    "category": resolved_root,
                    "subcategory": clean_sub,
                }

        mapped_row_ids = set(subledger_map.keys())

        # -------------------------------------------------------------
        # 4. Aggregation Matrix Construction
        # -------------------------------------------------------------
        matrix_dict = defaultdict(
            lambda: {
                "category": "",
                "subcategory": "",
                "transaction_count": 0,
                "total_debit": Decimal("0.00"),
                "total_credit": Decimal("0.00"),
            }
        )

        # Part A: Unmapped Node 99 Transactions (Historical classification / Suspense)
        unmapped_qs = qs.exclude(row_identifier__in=mapped_row_ids)

        unmapped_aggregated = (
            unmapped_qs.annotate(
                resolved_cat=RawSQL(
                    "COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(evaluation_matrix_snapshot, '$.resolved_category')), ''), 'Suspense')",
                    [],
                ),
                resolved_subcat=RawSQL(
                    "COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(evaluation_matrix_snapshot, '$.resolved_subcategory')), ''), 'Suspense Account')",
                    [],
                ),
            )
            .values("resolved_cat", "resolved_subcat")
            .annotate(
                transaction_count=Count("id"),
                total_debit=Sum("debit"),
                total_credit=Sum("credit"),
            )
        )

        for row in unmapped_aggregated:
            cat = row["resolved_cat"] or "Suspense"
            subcat = row["resolved_subcat"] or "Suspense Account"
            key = (cat, subcat)
            matrix_dict[key]["category"] = cat
            matrix_dict[key]["subcategory"] = subcat
            matrix_dict[key]["transaction_count"] += int(row["transaction_count"] or 0)
            matrix_dict[key]["total_debit"] += Decimal(str(row["total_debit"] or 0))
            matrix_dict[key]["total_credit"] += Decimal(str(row["total_credit"] or 0))

        # Part B: Subledger-Bound Transactions (Reclassified to Folio Heads)
        # Queried directly from Node 99 scope to preserve exact bank/date period conservation
        mapped_journal_entries = qs.filter(row_identifier__in=mapped_row_ids).values(
            "row_identifier", "debit", "credit"
        )

        for entry in mapped_journal_entries:
            row_id = str(entry["row_identifier"])
            dest = subledger_map.get(row_id)
            if not dest:
                continue

            key = (dest["category"], dest["subcategory"])
            matrix_dict[key]["category"] = dest["category"]
            matrix_dict[key]["subcategory"] = dest["subcategory"]
            matrix_dict[key]["transaction_count"] += 1
            matrix_dict[key]["total_debit"] += Decimal(str(entry["debit"] or 0))
            matrix_dict[key]["total_credit"] += Decimal(str(entry["credit"] or 0))

        # -------------------------------------------------------------
        # 5. Format Ledger Presentation
        # -------------------------------------------------------------
        results = []
        for (cat, subcat), data in matrix_dict.items():
            dr = data["total_debit"].quantize(Decimal("0.01"))
            cr = data["total_credit"].quantize(Decimal("0.01"))
            net = (dr - cr).quantize(Decimal("0.01"))
            results.append(
                {
                    "category": cat,
                    "subcategory": subcat,
                    "transaction_count": data["transaction_count"],
                    "total_debit": f"{dr:.2f}",
                    "total_credit": f"{cr:.2f}",
                    "net_balance": f"{net:.2f}",
                }
            )

        results.sort(key=lambda x: (x["category"], x["subcategory"]))
        return results

    @staticmethod
    def get_ledger_symmetry(
        bank_account_id, taxonomy_account_id=99, from_date=None, to_date=None
    ):
        """
        Calculates double-entry symmetry proof:
        - If a specific bank account is selected, scopes to that bank account's row_identifiers.
        - If Node 99 (Master Node) is selected, aggregates ALL bank legs vs ALL Node 99 counter-legs.
        """
        is_global_master = int(bank_account_id) == int(taxonomy_account_id)

        if is_global_master:
            bank_qs = JournalEntry.objects.exclude(account_id=taxonomy_account_id)
            tax_qs = JournalEntry.objects.filter(account_id=taxonomy_account_id)
        else:
            bank_qs = JournalEntry.objects.filter(account_id=bank_account_id)

            if from_date:
                bank_qs = bank_qs.filter(transaction_date__gte=from_date)
            if to_date:
                bank_qs = bank_qs.filter(transaction_date__lte=to_date)

            target_row_ids = bank_qs.values_list("row_identifier", flat=True)
            tax_qs = JournalEntry.objects.filter(
                account_id=taxonomy_account_id, row_identifier__in=target_row_ids
            )

        if is_global_master and from_date:
            bank_qs = bank_qs.filter(transaction_date__gte=from_date)
            tax_qs = tax_qs.filter(transaction_date__gte=from_date)
        if is_global_master and to_date:
            bank_qs = bank_qs.filter(transaction_date__lte=to_date)
            tax_qs = tax_qs.filter(transaction_date__lte=to_date)

        # 1. Aggregate Bank Legs
        bank_totals = bank_qs.aggregate(dr=Sum("debit"), cr=Sum("credit"))
        bank_dr = float(bank_totals["dr"] or 0.0)
        bank_cr = float(bank_totals["cr"] or 0.0)
        acc_bank_net = round(bank_dr - bank_cr, 2)

        # 2. Aggregate Taxonomy Counter-Legs
        tax_totals = tax_qs.aggregate(dr=Sum("debit"), cr=Sum("credit"))
        tax_dr = float(tax_totals["dr"] or 0.0)
        tax_cr = float(tax_totals["cr"] or 0.0)
        acc_tax_net = round(tax_dr - tax_cr, 2)

        # 3. Double-Entry Symmetry
        variance = round(acc_bank_net + acc_tax_net, 2)

        return {
            "bank_account_id": bank_account_id,
            "taxonomy_account_id": taxonomy_account_id,
            "bank_net": acc_bank_net,
            "taxonomy_net": acc_tax_net,
            "variance": variance,
            "is_balanced": abs(variance) < 0.01,
        }
