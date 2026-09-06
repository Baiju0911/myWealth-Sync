import json
from decimal import Decimal
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from tracker.models.emailModels import RawEmailPayload


class BalanceCheckViewSet(viewsets.ViewSet):
    """Audits running balance continuity and detects missing SMS/Email transaction gaps."""

    @action(detail=False, methods=["get"], url_path="audit")
    def audit_discrepancies(self, request):
        account_number = request.query_params.get("account", "0060")
        bank_name = request.query_params.get("bank", "SOUTH INDIAN BANK")

        records = RawEmailPayload.objects.filter(
            status__in=["PARSED", "STAGED"]
        ).order_by("email_date", "created_at")

        filtered_records = []
        for r in records:
            headers = r.headers_json or {}
            if isinstance(headers, str):
                try:
                    headers = json.loads(headers)
                except Exception:
                    headers = {}

            summary = headers.get("parsed_summary", {})
            acc = r.account_last4 or summary.get("account")
            bal = summary.get("balance")

            if acc == account_number:
                filtered_records.append(
                    {
                        "id": str(r.id),
                        "source": r.source,
                        "bank_name": r.bank_name or summary.get("bank") or bank_name,
                        "account_last4": acc,
                        "merchant": r.merchant or r.subject or "UPI Transfer",
                        "amount": str(r.amount or summary.get("amount") or "0.00"),
                        "txn_type": (r.txn_type or "DEBIT").upper(),
                        "balance": (
                            str(bal) if bal is not None and str(bal) != "None" else None
                        ),
                        "upi_ref": r.upi_ref or summary.get("upi_ref") or "—",
                        "status": r.status,
                        "email_date": (
                            r.email_date.isoformat() if r.email_date else None
                        ),
                        "created_at": (
                            r.created_at.isoformat() if r.created_at else None
                        ),
                    }
                )

        audited_results = []
        gap_count = 0
        last_known_bal_record = None

        for current in filtered_records:
            audited_results.append(current)
            curr_bal_str = current.get("balance")
            if not curr_bal_str:
                continue

            if last_known_bal_record is not None:
                prev_bal = Decimal(str(last_known_bal_record["balance"]))
                curr_bal = Decimal(str(curr_bal_str))
                curr_amt = Decimal(str(current["amount"]))
                txn_type = current["txn_type"].upper()

                expected_bal = (
                    prev_bal - curr_amt if txn_type == "DEBIT" else prev_bal + curr_amt
                )
                delta = curr_bal - expected_bal

                if abs(delta) > Decimal("0.01"):
                    already_staged = RawEmailPayload.objects.filter(
                        source="AUDIT_GAP",
                        account_last4=current["account_last4"],
                        amount=abs(delta),
                        status="STAGED",
                    ).exists()

                    if not already_staged:
                        gap_count += 1
                        gap_type = "CREDIT" if delta > 0 else "DEBIT"
                        gap_dc = "Cr" if delta > 0 else "Dr"
                        intermediate_balance = (
                            prev_bal + delta
                            if gap_type == "CREDIT"
                            else prev_bal - abs(delta)
                        )

                        synthetic_gap = {
                            "id": f"gap_{last_known_bal_record['id'][:8]}_{current['id'][:8]}",
                            "source": "AUDIT_GAP",
                            "bank_name": current["bank_name"],
                            "account_last4": current["account_last4"],
                            "merchant": "⚠️ [UNMATCHED GAP] Pre-Statement Suspense",
                            "amount": str(abs(delta)),
                            "txn_type": gap_type,
                            "dc_type": gap_dc,
                            "balance": str(intermediate_balance),
                            "upi_ref": "PENDING_STATEMENT",
                            "status": "SUSPENSE",
                            "email_date": current["email_date"],
                            "created_at": current["created_at"],
                            "is_synthetic_gap": True,
                            "gap_start_date": last_known_bal_record["email_date"],
                            "gap_end_date": current["email_date"],
                            "delta_amount": str(delta),
                        }
                        audited_results.append(synthetic_gap)

            last_known_bal_record = current

        audited_results.reverse()
        return Response(
            {
                "account": account_number,
                "total_records": len(filtered_records),
                "discrepancies_found": gap_count,
                "results": audited_results,
            },
            status=status.HTTP_200_OK,
        )
