from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from tracker.models.emailModels import RawEmailPayload
from tracker.emailIngest.serializers import RawEmailPayloadSerializer
from .emailViewhelper import safe_parse_datetime


class RawEmailPayloadVaultViewSet(viewsets.ReadOnlyModelViewSet):
    """Manages committed records in MySQL, serving queries for Tab 2 DataTables."""

    queryset = RawEmailPayload.objects.all().order_by("-email_date", "-created_at")
    serializer_class = RawEmailPayloadSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = super().get_queryset()
        staged_only = self.request.query_params.get("staged_only")
        if staged_only == "true":
            queryset = queryset.filter(is_staged_for_matching=True)
        elif staged_only == "false":
            queryset = queryset.filter(is_staged_for_matching=False)

        # 🎯 Filter by Account Last 4 (From Dropdown)
        account = self.request.query_params.get(
            "account"
        ) or self.request.query_params.get("account_last4")
        if account and account != "ALL":
            queryset = queryset.filter(account_last4=account)

        search = self.request.query_params.get("search")
        status_param = self.request.query_params.get("status")
        date_preset = self.request.query_params.get("date_preset")
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")

        if search:
            queryset = queryset.filter(
                Q(bank_name__icontains=search)
                | Q(merchant__icontains=search)
                | Q(subject__icontains=search)
            )

        if status_param and status_param != "ALL":
            queryset = queryset.filter(status=status_param)

        now = timezone.now()
        local_now = timezone.localtime(now)
        today = local_now.date()

        if date_preset == "THIS_WEEK":
            monday = today - timedelta(days=today.weekday())
            start_of_week = timezone.make_aware(
                datetime.combine(monday, datetime.min.time())
            )
            queryset = queryset.filter(
                Q(created_at__gte=start_of_week) | Q(email_date__gte=start_of_week)
            )
        elif date_preset == "THIS_MONTH":
            first_day = today.replace(day=1)
            start_of_month = timezone.make_aware(
                datetime.combine(first_day, datetime.min.time())
            )
            queryset = queryset.filter(
                Q(created_at__gte=start_of_month) | Q(email_date__gte=start_of_month)
            )
        elif date_preset == "LAST_MONTH":
            first_day_this_month = today.replace(day=1)
            last_month_end = first_day_this_month - timedelta(days=1)
            first_day_last_month = last_month_end.replace(day=1)

            start_dt = timezone.make_aware(
                datetime.combine(first_day_last_month, datetime.min.time())
            )
            end_dt = timezone.make_aware(
                datetime.combine(first_day_this_month, datetime.min.time())
            )
            queryset = queryset.filter(
                Q(email_date__gte=start_dt, email_date__lt=end_dt)
                | Q(created_at__gte=start_dt, created_at__lt=end_dt)
            )
        elif date_preset == "LAST_6_MONTHS":
            six_months_ago = today - timedelta(days=180)
            start_dt = timezone.make_aware(
                datetime.combine(six_months_ago, datetime.min.time())
            )
            queryset = queryset.filter(
                Q(created_at__gte=start_dt) | Q(email_date__gte=start_dt)
            )
        elif date_preset == "CUSTOM":
            if start_date and end_date:
                try:
                    s_d = datetime.strptime(start_date, "%Y-%m-%d").date()
                    e_d = datetime.strptime(end_date, "%Y-%m-%d").date()
                    s_dt = timezone.make_aware(
                        datetime.combine(s_d, datetime.min.time())
                    )
                    e_dt = timezone.make_aware(
                        datetime.combine(e_d, datetime.max.time())
                    )
                    queryset = queryset.filter(
                        Q(email_date__range=(s_dt, e_dt))
                        | Q(created_at__range=(s_dt, e_dt))
                    )
                except ValueError:
                    queryset = queryset.none()
            else:
                queryset = queryset.none()

        return queryset

    @action(detail=False, methods=["get"], url_path="stats")
    def get_stats(self, request):
        filtered_qs = self.get_queryset()
        return Response(
            {
                "total": filtered_qs.count(),
                "parsed": filtered_qs.filter(
                    status=RawEmailPayload.ProcessingStatus.PARSED
                ).count(),
                "duplicate": filtered_qs.filter(
                    status=RawEmailPayload.ProcessingStatus.DUPLICATE
                ).count(),
                "failed": filtered_qs.filter(
                    status__in=[
                        RawEmailPayload.ProcessingStatus.FAILED,
                        RawEmailPayload.ProcessingStatus.DECRYPTED,
                    ]
                ).count(),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["patch"], url_path="taxonomy")
    def update_taxonomy(self, request, pk=None):
        payload = self.get_object()
        category_id = request.data.get("category_id")
        category_name = request.data.get("category_name")
        subcategory_id = request.data.get("subcategory_id")
        subcategory_name = request.data.get("subcategory_name")

        if not payload.taxonomy_payload:
            payload.taxonomy_payload = {}
        if "taxonomy" not in payload.taxonomy_payload:
            payload.taxonomy_payload["taxonomy"] = {}

        if category_id is not None:
            payload.taxonomy_payload["taxonomy"]["category_id"] = category_id
        if category_name is not None:
            payload.taxonomy_payload["taxonomy"]["category_name"] = category_name
        if subcategory_id is not None:
            payload.taxonomy_payload["taxonomy"]["subcategory_id"] = subcategory_id
        if subcategory_name is not None:
            payload.taxonomy_payload["taxonomy"]["subcategory_name"] = subcategory_name

        payload.save(update_fields=["taxonomy_payload"])
        return Response(
            {
                "status": "success",
                "message": "Taxonomy updated successfully",
                "taxonomy_payload": payload.taxonomy_payload,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="batch-taxonomy")
    def batch_update_taxonomy(self, request):
        updates = request.data.get("updates", [])
        updated_count = 0

        for item in updates:
            payload_id = item.get("payloadId")
            try:
                payload = RawEmailPayload.objects.get(pk=payload_id)
                if not payload.taxonomy_payload:
                    payload.taxonomy_payload = {}
                if "taxonomy" not in payload.taxonomy_payload:
                    payload.taxonomy_payload["taxonomy"] = {}

                payload.taxonomy_payload["taxonomy"]["category_name"] = item.get(
                    "categoryName"
                )
                payload.taxonomy_payload["taxonomy"]["subcategory_name"] = item.get(
                    "subcategoryName"
                )
                payload.save(update_fields=["taxonomy_payload"])
                updated_count += 1
            except RawEmailPayload.DoesNotExist:
                continue

        return Response(
            {
                "status": "success",
                "message": f"Successfully updated taxonomy for {updated_count} record(s).",
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="stage-for-matching")
    def stage_for_matching(self, request):
        payload_ids = request.data.get("payload_ids", [])
        synthetic_gaps = request.data.get("synthetic_gaps", [])

        if not payload_ids and not synthetic_gaps:
            return Response(
                {"error": "No items provided to stage."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        staged_db_ids = []
        now_dt = timezone.now()

        for gap in synthetic_gaps:
            try:
                amt_str = str(gap.get("amount") or "0.00").replace(",", "")
                amt_val = Decimal(amt_str)
                email_dt = safe_parse_datetime(gap.get("email_date"))

                record = RawEmailPayload.objects.create(
                    source="AUDIT_GAP",
                    bank_name=gap.get("bank_name") or "SOUTH INDIAN BANK",
                    account_last4=gap.get("account_last4") or "0060",
                    merchant=gap.get("merchant")
                    or "⚠️ [UNMATCHED GAP] Pre-Statement Suspense",
                    amount=amt_val,
                    txn_type=gap.get("txn_type", "DEBIT").upper(),
                    upi_ref="PENDING_STATEMENT",
                    status="STAGED",
                    is_staged_for_matching=True,
                    staged_at=now_dt,
                    email_date=email_dt,
                    subject="Synthetic Statement Audit Gap",
                    decrypted_body="Auto-created synthetic gap row generated from Balance Audit.",
                    headers_json={
                        "is_synthetic_gap": True,
                        "gap_start_date": gap.get("gap_start_date"),
                        "gap_end_date": gap.get("gap_end_date"),
                        "delta_amount": gap.get("delta_amount"),
                        "parsed_summary": {
                            "bank": gap.get("bank_name") or "SOUTH INDIAN BANK",
                            "account": gap.get("account_last4") or "0060",
                            "amount": str(amt_val),
                            "balance": str(gap.get("balance") or "0.00"),
                            "upi_ref": "PENDING_STATEMENT",
                            "full_narration": "Synthetic Statement Audit Gap",
                        },
                    },
                )
                record.mark_as_staged()
                staged_db_ids.append(str(record.id))
            except Exception as e:
                print(f"❌ Failed to commit synthetic gap: {e}")

        real_uuid_ids = [pid for pid in payload_ids if not str(pid).startswith("gap_")]
        if real_uuid_ids:
            records = RawEmailPayload.objects.filter(pk__in=real_uuid_ids)
            for record in records:
                record.mark_as_staged()
                staged_db_ids.append(str(record.id))

        return Response(
            {
                "status": "success",
                "message": f"Successfully staged {len(staged_db_ids)} item(s) for statement matching.",
                "staged_ids": staged_db_ids,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="unstage-from-matching")
    def unstage_from_matching(self, request):
        payload_ids = request.data.get("payload_ids", [])
        if not payload_ids:
            return Response(
                {"error": "No payload IDs provided to unstage."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        records = RawEmailPayload.objects.filter(pk__in=payload_ids)
        unstaged_count = 0
        for record in records:
            record.mark_as_unstaged()
            unstaged_count += 1

        return Response(
            {
                "status": "success",
                "message": f"Successfully unstaged {unstaged_count} item(s).",
                "unstaged_count": unstaged_count,
            },
            status=status.HTTP_200_OK,
        )
