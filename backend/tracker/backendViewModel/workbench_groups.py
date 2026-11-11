import json
import re
from django.db.models import Q
from rest_framework import serializers, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from tracker.models import (
    WorkbenchGroupHierarchy,
    MasterNarrationTagRule,
    StatementStagingLine,
)


class WorkbenchGroupHierarchySerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkbenchGroupHierarchy
        fields = [
            "id",
            "header_scope",
            "group_tag",
            "subgroup_tag",
            "display_order",
        ]


class WorkbenchGroupHierarchyViewSet(viewsets.ModelViewSet):
    """
    CRUD viewset for intra-header Group <-> Subgroup hierarchies.
    """

    queryset = WorkbenchGroupHierarchy.objects.all().order_by(
        "display_order", "group_tag"
    )
    serializer_class = WorkbenchGroupHierarchySerializer

    def get_queryset(self):
        qs = super().get_queryset()
        header_scope = self.request.query_params.get("header_scope")
        if header_scope:
            qs = qs.filter(header_scope__iexact=header_scope.strip())
        return qs

    def create(self, request, *args, **kwargs):
        header_scope = request.data.get("header_scope", "").strip()
        group_tag = request.data.get("group_tag", "").strip().upper()
        subgroup_tag = request.data.get("subgroup_tag")

        if subgroup_tag:
            subgroup_tag = subgroup_tag.strip().upper()
        else:
            subgroup_tag = ""

        if not header_scope or not group_tag:
            return Response(
                {"detail": "header_scope and group_tag are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        exists = WorkbenchGroupHierarchy.objects.filter(
            header_scope__iexact=header_scope,
            group_tag=group_tag,
            subgroup_tag=subgroup_tag,
        ).exists()

        if exists:
            return Response(
                {
                    "detail": f"Group '{group_tag}' already exists under '{header_scope}'."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        item = WorkbenchGroupHierarchy.objects.create(
            header_scope=header_scope,
            group_tag=group_tag,
            subgroup_tag=subgroup_tag,
        )
        serializer = self.get_serializer(item)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="move-subgroup")
    def move_subgroup(self, request):
        header_scope = request.data.get("header_scope", "").strip()
        subgroup_tag = request.data.get("subgroup_tag", "").strip().upper()
        target_group_tag = request.data.get("target_group_tag", "").strip().upper()

        if not header_scope or not subgroup_tag or not target_group_tag:
            return Response(
                {
                    "detail": "header_scope, subgroup_tag, and target_group_tag are required."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated = WorkbenchGroupHierarchy.objects.filter(
            header_scope__iexact=header_scope,
            subgroup_tag=subgroup_tag,
        ).update(group_tag=target_group_tag)

        return Response({"status": "SUCCESS", "updated_rows": updated})


class MasterNarrationTagRuleSerializer(serializers.ModelSerializer):
    match_tokens = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )

    class Meta:
        model = MasterNarrationTagRule
        fields = [
            "id",
            "keyword_pattern",
            "match_tokens",
            "match_type",
            "allowed_vector",
            "header_scope",
            "parent_group_tag",
            "subgroup_tag",
            "require_internal_contra",
            "source_account_id",  # Only source_account_id in fields
            "priority",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def to_internal_value(self, data):
        # Allow input mutation
        data = data.copy() if hasattr(data, "copy") else dict(data)

        # Map legacy or frontend 'source_account' key to model column 'source_account_id'
        if "source_account" in data and not data.get("source_account_id"):
            data["source_account_id"] = data.pop("source_account")

        # Auto-serialize keyword_pattern if frontend sends raw array string or tokens
        tokens = data.get("match_tokens")
        pattern = data.get("keyword_pattern", "")

        if (
            isinstance(pattern, str)
            and pattern.startswith("[")
            and pattern.endswith("]")
        ):
            try:
                parsed_list = json.loads(pattern)
                if isinstance(parsed_list, list):
                    if not tokens:
                        data["match_tokens"] = parsed_list
                    data["keyword_pattern"] = parsed_list[0] if parsed_list else ""
            except Exception:
                pass

        if not data.get("keyword_pattern") and data.get("match_tokens"):
            tks = data.get("match_tokens")
            if isinstance(tks, list) and len(tks) > 0:
                data["keyword_pattern"] = str(tks[0])

        return super().to_internal_value(data)


class MasterNarrationTagRuleViewSet(viewsets.ModelViewSet):
    queryset = MasterNarrationTagRule.objects.all().order_by("-priority", "id")
    serializer_class = MasterNarrationTagRuleSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        header_scope = self.request.query_params.get("header_scope")
        if header_scope:
            qs = qs.filter(header_scope__iexact=header_scope.strip())
        return qs

    @action(detail=False, methods=["post"], url_path="apply-rule")
    def apply_rule_to_stream(self, request):
        rule_id = request.data.get("rule_id")
        rule = MasterNarrationTagRule.objects.filter(id=rule_id).first()
        if not rule:
            return Response(
                {"detail": "Rule not found"}, status=status.HTTP_404_NOT_FOUND
            )

        qs = StatementStagingLine.objects.all()
        print(
            f"\n🔍 [RULE EVALUATION START] Rule #{rule.id} -> {rule.parent_group_tag}"
        )
        print(f"   [STAGE 0] Total lines in StatementStagingLine: {qs.count()}")

        # 1. Vector filter
        if rule.allowed_vector == "OUTFLOW":
            qs = qs.filter(Q(amount__lt=0) | Q(debit__gt=0))
        elif rule.allowed_vector == "INFLOW":
            qs = qs.filter(Q(amount__gt=0) | Q(credit__gt=0))
        print(f"   [STAGE 1] After vector ({rule.allowed_vector}): {qs.count()}")

        # 2. Account filter (check account_id vs source_account_id)
        if rule.source_account_id:
            acc_q = Q()
            for acc_field in ["account_id", "source_account_id", "bank_account_id"]:
                if hasattr(StatementStagingLine, acc_field):
                    acc_q |= Q(**{acc_field: rule.source_account_id})
            if acc_q:
                qs = qs.filter(acc_q)
            print(
                f"   [STAGE 2] After account filter (ID {rule.source_account_id}): {qs.count()}"
            )

        # 3. Internal Contra filter - only enforce if the staging model tracks it
        if rule.require_internal_contra:
            contra_q = Q()
            if hasattr(StatementStagingLine, "suggested_contra_account"):
                contra_q |= Q(suggested_contra_account__isnull=False)
            if hasattr(StatementStagingLine, "is_contra"):
                contra_q |= Q(is_contra=True)
            if hasattr(StatementStagingLine, "suggested_contra_id"):
                contra_q |= Q(suggested_contra_id__isnull=False)
            if hasattr(StatementStagingLine, "destination_account_id"):
                contra_q |= Q(destination_account_id__isnull=False)

            # Only apply if at least one contra column actually matched on the model
            if contra_q:
                # Test count before filtering; if 0, do not strangle the rule
                contra_matches = qs.filter(contra_q).count()
                print(f"   [STAGE 3] Potential contra rows: {contra_matches}")
                if contra_matches > 0:
                    qs = qs.filter(contra_q)
                else:
                    print(
                        "   [STAGE 3 WARNING] No rows have explicit contra FK flag set, skipping contra strict filter."
                    )
            else:
                print("   [STAGE 3] No contra field on model, skipping.")

        # 4. Narration & Match Tokens filter (OR logic across all tokens on raw_narration)
        tokens = list(rule.match_tokens or [])
        if rule.keyword_pattern and rule.keyword_pattern not in tokens:
            tokens.append(rule.keyword_pattern)

        if tokens:
            token_q = Q()
            for tk in tokens:
                tk_clean = str(tk).strip()
                if not tk_clean:
                    continue
                if "*" in tk_clean:
                    sub_parts = [p.strip() for p in tk_clean.split("*") if p.strip()]
                    compound_q = Q()
                    for sp in sub_parts:
                        compound_q &= Q(raw_narration__icontains=sp)
                    token_q |= compound_q
                elif rule.match_type == "EXACT":
                    token_q |= Q(raw_narration__iexact=tk_clean)
                else:
                    token_q |= Q(raw_narration__icontains=tk_clean)

            if token_q:
                qs = qs.filter(token_q)
            print(f"   [STAGE 4] After matching tokens {tokens}: {qs.count()}")

        # 5. Apply the tag update strictly to valid model columns
        updated_count = qs.update(routing_status=rule.parent_group_tag)
        print(
            f"   [STAGE 5] Final tagged rows updated in StatementStagingLine: {updated_count}\n"
        )

        return Response(
            {
                "status": "SUCCESS",
                "matched_rows": updated_count,
                "applied_tag": rule.parent_group_tag,
                "subgroup_tag": rule.subgroup_tag,
            }
        )

    @action(detail=False, methods=["post"], url_path="synthesize-context")
    def synthesize_context(self, request):
        txn_ids = request.data.get("transaction_ids", [])
        cluster_pattern = request.data.get("cluster_pattern", "")
        vendor_name = request.data.get("vendor_name", "")

        line = None
        if txn_ids:
            first_id = txn_ids[0]
            query = Q(row_identifier=first_id)
            try:
                import uuid

                query |= Q(id=uuid.UUID(str(first_id)))
            except (ValueError, TypeError):
                pass

            line = (
                StatementStagingLine.objects.filter(query)
                .select_related("account", "bank", "suggested_contra_account")
                .first()
            )

        raw_narration = ""
        source_account = ""
        dest_account = ""
        source_account_id = None
        is_contra = True
        rail = "ANY"

        if line:
            raw_narration = line.raw_narration or ""
            source_account = line.account.name if line.account else ""
            source_account_id = line.account_id
            dest_account = (
                line.suggested_contra_account.name
                if line.suggested_contra_account
                else ""
            )
            is_contra = bool(line.suggested_contra_account)
            rail = getattr(line, "detected_rail", "ANY")

        if not raw_narration and cluster_pattern:
            raw_narration = cluster_pattern

        upper_raw = raw_narration.upper()

        if rail in ["ANY", "BANK_TRANSFER", None]:
            if "UPI/" in upper_raw or "/UPI/" in upper_raw or "@" in upper_raw:
                rail = "UPI"
            elif "NEFT" in upper_raw:
                rail = "NEFT"
            elif "IMPS" in upper_raw:
                rail = "IMPS"
            elif "RTGS" in upper_raw:
                rail = "RTGS"
            elif "ATM" in upper_raw or "CASH WDL" in upper_raw:
                rail = "ATM"
            elif "NACH" in upper_raw or "ACH" in upper_raw:
                rail = "NACH"

        tokens = []

        clean_vendor = re.sub(r"\(OUT\)|\(IN\)|#\w+", "", vendor_name).strip()
        if clean_vendor and clean_vendor not in tokens:
            tokens.append(clean_vendor)

        if line and hasattr(line, "display_payee") and line.display_payee:
            if line.display_payee not in tokens:
                tokens.append(line.display_payee)

        if "/" in raw_narration:
            parts = [p.strip() for p in raw_narration.split("/") if p.strip()]
            if len(parts) >= 4:
                payee_segment = parts[3].strip()
                if (
                    payee_segment
                    and len(payee_segment) > 2
                    and not payee_segment.isdigit()
                ):
                    if payee_segment not in tokens:
                        tokens.append(payee_segment)
            if len(parts) >= 2 and len(parts[1]) <= 6 and parts[1].isalpha():
                bank_code = parts[1]
                if bank_code not in tokens:
                    tokens.append(bank_code)

        vpa_match = re.search(r"([A-Za-z0-9._-]+@[A-Za-z0-9]+)", raw_narration)
        if vpa_match:
            full_vpa = vpa_match.group(1).upper()
            handle = full_vpa.split("@")[0]
            if full_vpa not in tokens:
                tokens.append(full_vpa)
            if handle not in tokens:
                tokens.append(handle)
        else:
            dot_match = re.search(r"([A-Z]+(?:\.[A-Z]+)+)", upper_raw)
            if dot_match and dot_match.group(1) not in tokens:
                tokens.append(dot_match.group(1))

        if clean_vendor:
            for w in clean_vendor.split():
                if len(w) > 3 and w not in tokens:
                    tokens.append(w)

        tokens = [
            t
            for t in tokens
            if t.upper() not in ["#CONTRA", "CONTRA", "BALANCE", "NOTRF"]
        ]

        return Response(
            {
                "status": "SUCCESS",
                "raw_narration": raw_narration,
                "tokens": tokens,
                "detected_rail": rail,
                "source_account": source_account,
                "source_account_id": source_account_id,
                "destination_account": dest_account,
                "is_contra": is_contra,
            }
        )
