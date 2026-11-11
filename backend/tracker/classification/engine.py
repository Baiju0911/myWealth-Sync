# tracker/classification/engine.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from django.apps import apps
from django.db.models import Q
from django.utils import timezone

from tracker.models.models import ClassificationRule, JournalEntry
from tracker.parsers.universal_narration import UniversalNarrationExtractor

from .enginehelpers import (
    TaggingEngine,
    RuleLearningEngine,
    resolve_cross_account_contra_map,
    ConfidenceScorer,
)
from tracker.constants import (
    GENERIC_IGNORE_PATTERNS,
    GENERIC_PATTERNS,
    KNOWN_MERCHANTS,
    NOISE_KEYWORD_BLACKLIST,
    RULE_SAFETY_BLACKLIST,
    ABSOLUTE_GREEDY_BLACKLIST,
    OK_WORD_LIST,
    BLACKLIST_TAGS,
    ALL_SYSTEM_BLACKLIST,
    ACTION_AND_RAIL_NOISE,
)

extract_meaningful_tokens = TaggingEngine.extract_meaningful_tokens
sanitize_user_pattern = RuleLearningEngine.sanitize_user_pattern
extract_clean_payee_pattern = TaggingEngine.extract_clean_payee_pattern
generate_strict_multitoken_pattern = (
    RuleLearningEngine.generate_strict_multitoken_pattern
)
add_or_update_classification_rule = RuleLearningEngine.add_or_update_classification_rule
match_multi_tokens = RuleLearningEngine.match_multi_tokens
get_clean_patterns = RuleLearningEngine.get_clean_patterns
generate_canonical_cluster_tag = TaggingEngine.generate_canonical_cluster_tag


def build_human_readable_narrative(
    rail: str,
    direction: str,
    amount: float,
    payee: str,
    ref_no: str | None,
    branch_or_remark: str | None,
) -> str:
    clean_payee = (
        UniversalNarrationExtractor.repair_kerning_and_splits(payee)
        if payee
        else "Unspecified Entity"
    )
    rail_label = f" via {rail}" if rail and rail != "UNKNOWN" else ""
    ref_label = f" (Ref: {ref_no})" if ref_no else ""

    if direction == "OUTFLOW":
        base = f"Paid ₹{amount:,.2f} to {clean_payee}{rail_label}{ref_label}"
    else:
        upper_payee = clean_payee.upper()
        if "INTEREST" in upper_payee:
            base = f"Interest Credit of ₹{amount:,.2f}{rail_label}"
        elif "OWN" in upper_payee or "SELF" in upper_payee:
            base = f"Self-Transfer / Deposit ₹{amount:,.2f}{rail_label}"
        else:
            base = f"Received ₹{amount:,.2f} from {clean_payee}{rail_label}{ref_label}"

    if branch_or_remark and branch_or_remark.upper() not in [
        "NO REMARKS",
        clean_payee.upper(),
    ]:
        base += f" • {branch_or_remark}"

    return base


def _build_clusters_from_entries(
    entries, target_subcategory, search_query=None, include_items=False
):
    StatementStagingLine = apps.get_model("ledger", "StatementStagingLine")
    MasterNarrationTagRule = apps.get_model("ledger", "MasterNarrationTagRule")

    row_ids = [e.row_identifier for e in entries if e.row_identifier]
    staging_lines = list(
        StatementStagingLine.objects.filter(row_identifier__in=row_ids)
    )
    staging_map = {s.row_identifier: s for s in staging_lines if s.row_identifier}

    # Pre-cached map of active rules: tag -> subgroup
    rule_subgroup_cache = dict(
        MasterNarrationTagRule.objects.filter(is_active=True).values_list(
            "parent_group_tag", "subgroup_tag"
        )
    )
    rule_subgroup_cache = {
        (k or "").strip().upper(): (v or "").strip().upper()
        for k, v in rule_subgroup_cache.items()
        if k
    }

    contra_map = resolve_cross_account_contra_map(row_ids, staging_lines)
    acc_registry = TaggingEngine.get_dynamic_accounts_registry()

    clusters_map = {}

    for entry in entries:
        remarks = entry.remarks if isinstance(entry.remarks, dict) else {}
        stg_line = staging_map.get(entry.row_identifier)
        contra_info = contra_map.get(
            entry.row_identifier,
            {"is_self_transfer": False, "contra_type": "ONE_WAY_EXTERNAL"},
        )

        # 🟢 Initialize loop-scoped variables deterministically
        configured_subgroup: Optional[str] = None
        stg_routing_status: str = ""

        if stg_line:
            parsed_meta = stg_line.parsed_narration or {}
            raw_payee = (
                parsed_meta.get("suggested_payee") or stg_line.display_payee or ""
            )
            payee = TaggingEngine.repair_narration_kerning(raw_payee)
            ref_no = parsed_meta.get("detected_reference")
            rail = parsed_meta.get("detected_rail", "BANK")
            remark = parsed_meta.get("suggested_remark")
            raw_statement_text = getattr(stg_line, "raw_narration", None) or getattr(
                stg_line, "narration", ""
            )
            host_account_id = getattr(stg_line, "account_id", None) or entry.account_id
            stg_routing_status = (
                (getattr(stg_line, "routing_status", "") or "").strip().upper()
            )
        else:
            fallback_text = (
                remarks.get("universal_narration")
                or remarks.get("narration")
                or remarks.get("display_text")
                or ""
            )
            parsed_meta = UniversalNarrationExtractor.decompose_raw_narration(
                fallback_text
            )
            raw_payee = (
                remarks.get("payee") or parsed_meta.get("raw_payee") or fallback_text
            )
            payee = TaggingEngine.repair_narration_kerning(raw_payee)
            ref_no = remarks.get("upi_ref") or parsed_meta.get("reference")
            rail = parsed_meta.get("rail", "BANK")
            remark = parsed_meta.get("raw_remark")
            raw_statement_text = fallback_text
            host_account_id = entry.account_id
            stg_routing_status = ""

        debit_val = float(entry.debit or 0)
        credit_val = float(entry.credit or 0)
        is_outflow = debit_val > 0
        amount = debit_val if is_outflow else credit_val

        # -------------------------------------------------------------
        # Determine Tag, Canonical Title, Confidence & OK to Classify
        # -------------------------------------------------------------
        is_contra = contra_info.get("is_self_transfer", False)
        pair_id = None
        src_name = contra_info.get("from_account_name", "Bank").upper()
        dst_name = contra_info.get("to_account_name", "Bank").upper()

        if is_contra:
            pair_amt = f"{amount:.2f}"
            pair_id = (
                f"PAIR_{min(src_name, dst_name)}_{max(src_name, dst_name)}_{pair_amt}"
            )

        # 🟢 TIER 1: MasterNarrationTagRule Explicit Priority
        if stg_routing_status and stg_routing_status.startswith("#"):
            pattern = stg_routing_status
            configured_subgroup = rule_subgroup_cache.get(pattern)

            if configured_subgroup:
                canonical_title = configured_subgroup
                display_subgroup = configured_subgroup
            elif is_contra:
                canonical_title = f"{src_name} ➔ {dst_name}"
                display_subgroup = canonical_title
                configured_subgroup = canonical_title
            else:
                canonical_title = payee or "Tagged Pattern"
                display_subgroup = canonical_title
                configured_subgroup = canonical_title

            score, label, ok_to_classify = 1.0, "RULE_VERIFIED", True

        # 🟢 TIER 2: Fallback to Self-Transfer / Contra Inference
        elif is_contra:
            pattern = "#CONTRA"
            canonical_title = f"{src_name} ➔ {dst_name}"
            display_subgroup = canonical_title
            configured_subgroup = canonical_title
            score, label, ok_to_classify = ConfidenceScorer.evaluate(
                is_paired_contra=True,
                has_ref_proof=bool(ref_no),
                has_rule_precedent=True,
            )

        # 🟢 TIER 3: Generic Algorithmic Tagging via Regex & Bank Heuristics
        else:
            (
                pattern,
                canonical_title,
                score,
                label,
                ok_to_classify,
            ) = TaggingEngine.generate_canonical_cluster_tag(
                raw_narration=raw_statement_text,
                payee=payee,
                host_account_id=host_account_id,
                registry=acc_registry,
            )
            display_subgroup = canonical_title
            configured_subgroup = canonical_title

        pattern = pattern.upper().strip()

        if pattern not in clusters_map:
            clusters_map[pattern] = {
                "pattern": pattern,
                "display_name": canonical_title,
                "subgroup_tag": configured_subgroup,
                "count": 0,
                "total_amount": 0.0,
                "total_inflow": 0.0,
                "total_outflow": 0.0,
                "confidence_score": score,
                "confidence_label": label,
                "sample_descriptions": [],
                "items": [],
                "transaction_ids": [],
                "is_contra_group": (pattern in ["#CONTRA", "#INTERABANK"]),
            }

        readable_narrative = build_human_readable_narrative(
            rail=rail,
            direction="OUTFLOW" if is_outflow else "INFLOW",
            amount=amount,
            payee=display_subgroup,
            ref_no=ref_no,
            branch_or_remark=remark,
        )

        cluster = clusters_map[pattern]
        cluster["count"] += 1
        cluster["total_amount"] += amount
        if is_outflow:
            cluster["total_outflow"] += amount
        else:
            cluster["total_inflow"] += amount

        cluster["transaction_ids"].append(str(entry.id))
        if (
            len(cluster["sample_descriptions"]) < 2
            and readable_narrative not in cluster["sample_descriptions"]
        ):
            cluster["sample_descriptions"].append(readable_narrative)

        if include_items:
            cluster["items"].append(
                {
                    "id": str(entry.id),
                    "pair_id": pair_id or f"SINGLE_{entry.id}",
                    "ok_to_classify": ok_to_classify,
                    "confidence_score": score,
                    "confidence_label": label,
                    "narration": raw_statement_text,
                    "raw_narration": raw_statement_text,
                    "display_payee": display_subgroup,
                    "subgroup_tag": configured_subgroup,
                    "vendor_name": payee,  # 👈 Fixed: correctly points to local variable payee
                    "universal_narration": readable_narrative,
                    "debit": debit_val,
                    "credit": credit_val,
                    "amount": amount,
                    "direction": "OUTFLOW" if is_outflow else "INFLOW",
                    "transaction_date": str(entry.transaction_date),
                    "contra_meta": contra_info,
                    "routing_status": stg_routing_status,
                }
            )

    # Sort cluster line items so matched pairs sit adjacent:
    if include_items:
        for c in clusters_map.values():
            c["items"].sort(
                key=lambda x: (x["pair_id"], x["transaction_date"], x["direction"])
            )

    sorted_clusters = sorted(
        clusters_map.values(), key=lambda c: c["count"], reverse=True
    )

    if search_query and str(search_query).strip():
        norm_query = search_query.strip().upper()
        return [
            c
            for c in sorted_clusters
            if norm_query in c["pattern"].upper()
            or any(norm_query in s.upper() for s in c.get("sample_descriptions", []))
        ]

    return sorted_clusters


def get_suspense_workbench_clusters(
    account_id=None, search_query=None, include_cleared=False, include_items=False
):
    JournalEntry = apps.get_model("ledger", "JournalEntry")
    query = JournalEntry.objects.filter(account_id=99)
    if not include_cleared:
        query = query.filter(is_reclassified=False)

    if account_id and str(account_id) != "99":
        bank_row_ids = JournalEntry.objects.filter(account_id=account_id).values_list(
            "row_identifier", flat=True
        )
        query = query.filter(row_identifier__in=bank_row_ids)

    entries = list(
        query.only(
            "id", "row_identifier", "debit", "credit", "remarks", "transaction_date"
        ).order_by("-transaction_date")
    )
    return _build_clusters_from_entries(
        entries, "Suspense Account", search_query, include_items
    )


def get_gl_head_workbench_clusters(
    target_subcategory: str, search_query=None, include_items=False
):
    JournalEntry = apps.get_model("ledger", "JournalEntry")
    AssetSubLedger = apps.get_model("ledger", "AssetSubLedger")
    AssetTransactionMapping = apps.get_model("ledger", "AssetTransactionMapping")

    sub_clean = target_subcategory.strip()
    related_asset_ids = AssetSubLedger.objects.filter(
        Q(category__icontains=sub_clean)
        | Q(asset_category__name__icontains=sub_clean)
        | Q(asset_category__default_taxonomy_subcategory__icontains=sub_clean)
    ).values_list("id", flat=True)

    bound_row_ids = list(
        AssetTransactionMapping.objects.filter(
            asset_id__in=related_asset_ids
        ).values_list("row_identifier", flat=True)
    )

    gl_filter = (
        Q(evaluation_matrix_snapshot__resolved_subcategory__iexact=sub_clean)
        | Q(remarks__target_account_name__iexact=sub_clean)
        | Q(remarks__subcategory__iexact=sub_clean)
    )
    if bound_row_ids:
        gl_filter |= Q(row_identifier__in=bound_row_ids)

    query = (
        JournalEntry.objects.filter(gl_filter, debit__gt=0)
        .only("id", "row_identifier", "debit", "credit", "remarks", "transaction_date")
        .order_by("-transaction_date")
    )

    seen_row_ids = set()
    entries = []
    for e in list(query):
        rid = e.row_identifier or str(e.id)
        if rid in seen_row_ids:
            continue
        seen_row_ids.add(rid)
        entries.append(e)

    return _build_clusters_from_entries(entries, sub_clean, search_query, include_items)


def get_suspense_clusters(
    target_subcategory="Suspense Account",
    account_id=None,
    search_query=None,
    include_cleared=False,
    include_items=False,
):
    if not target_subcategory or target_subcategory.strip() in [
        "Suspense Account",
        "All",
    ]:
        return get_suspense_workbench_clusters(
            account_id, search_query, include_cleared, include_items
        )
    return get_gl_head_workbench_clusters(
        target_subcategory, search_query, include_items
    )


def reclassify_and_learn(
    transaction_ids: List[str],
    target_category: str,
    target_subcategory: str,
    patterns: Optional[List[str]] = None,
    save_rule: bool = True,
) -> Dict[str, Any]:
    if not transaction_ids:
        return {"status": "success", "reclassified_count": 0, "rules_updated": False}

    entries = list(JournalEntry.objects.filter(account_id=99, id__in=transaction_ids))
    if not entries:
        entries = list(
            JournalEntry.objects.filter(
                account_id=99, row_identifier__in=transaction_ids
            )
        )

    if not entries:
        return {"status": "success", "reclassified_count": 0, "rules_updated": False}

    total_debit = sum(float(e.debit or 0) for e in entries)
    total_credit = sum(float(e.credit or 0) for e in entries)
    inferred_entry_type = "Credit" if total_credit > total_debit else "Debit"

    payee_groups = {}
    for entry in entries:
        snapshot = entry.evaluation_matrix_snapshot or {}
        snapshot["previous_category"] = snapshot.get("resolved_category")
        snapshot["previous_subcategory"] = snapshot.get("resolved_subcategory")
        snapshot["resolved_category"] = target_category
        snapshot["resolved_subcategory"] = target_subcategory
        snapshot["is_manual_override"] = True

        entry.evaluation_matrix_snapshot = snapshot
        entry.classification_status = "RECLASSIFIED"
        entry.is_reclassified = True

        remarks_dict = entry.remarks if isinstance(entry.remarks, dict) else {}
        narration_text = remarks_dict.get("narration") or str(entry.remarks or "")
        payee = remarks_dict.get("payee") or ""
        clean_payee = (
            TaggingEngine.extract_clean_payee_pattern(payee or narration_text)
            or "GENERIC"
        )

        if clean_payee not in payee_groups:
            payee_groups[clean_payee] = []
        if narration_text:
            payee_groups[clean_payee].append(narration_text)

        entry.remarks = {
            **remarks_dict,
            "target_account_name": target_subcategory,
            "updated_at": timezone.now().isoformat(),
        }

    JournalEntry.objects.bulk_update(
        entries,
        [
            "evaluation_matrix_snapshot",
            "classification_status",
            "is_reclassified",
            "remarks",
        ],
    )

    rules_updated = False
    learned_patterns = []

    if save_rule:
        if patterns and isinstance(patterns, list) and len(patterns) > 0:
            for user_p in patterns:
                clean_user_p = RuleLearningEngine.sanitize_user_pattern(user_p)
                if not clean_user_p:
                    continue
                if len(clean_user_p) >= 3:
                    if RuleLearningEngine.add_or_update_classification_rule(
                        category=target_category,
                        subcategory=target_subcategory,
                        new_pattern=clean_user_p,
                        entry_type=inferred_entry_type,
                    ):
                        rules_updated = True
                        learned_patterns.append(clean_user_p)
        else:
            for payee_key, group_narrations in payee_groups.items():
                common_tokens = RuleLearningEngine.generate_strict_multitoken_pattern(
                    group_narrations
                )
                safe_tokens = [
                    t
                    for t in common_tokens
                    if not TaggingEngine.is_ref_hash_or_noise(t) and len(t) > 2
                ]
                if safe_tokens:
                    compound_pattern = " ".join(safe_tokens[:2])
                    if len(compound_pattern) >= 3:
                        if RuleLearningEngine.add_or_update_classification_rule(
                            category=target_category,
                            subcategory=target_subcategory,
                            new_pattern=compound_pattern,
                            entry_type=inferred_entry_type,
                        ):
                            rules_updated = True
                            learned_patterns.append(compound_pattern)

    return {
        "status": "success",
        "reclassified_count": len(entries),
        "entry_type_bound": inferred_entry_type,
        "rules_updated": rules_updated,
        "patterns_learned": learned_patterns,
    }


def fetch_cluster_line_items(entry_ids: list) -> list:
    if not entry_ids:
        return []

    JournalEntry = apps.get_model("ledger", "JournalEntry")
    StatementStagingLine = apps.get_model("ledger", "StatementStagingLine")
    Account = apps.get_model("ledger", "Account")

    AssetTransactionMapping = None
    for model in apps.get_models():
        if model.__name__ == "AssetTransactionMapping":
            AssetTransactionMapping = model
            break

    entries = list(
        JournalEntry.objects.filter(id__in=entry_ids)
        .only(
            "id",
            "row_identifier",
            "account_id",
            "debit",
            "credit",
            "remarks",
            "transaction_date",
        )
        .order_by("-transaction_date")
    )

    row_ids = [e.row_identifier for e in entries if e.row_identifier]

    mapping_map = {}
    if row_ids and AssetTransactionMapping:
        mappings = AssetTransactionMapping.objects.filter(
            row_identifier__in=row_ids
        ).select_related("asset")
        for m in mappings:
            asset = getattr(m, "asset", None)
            mapping_map[m.row_identifier] = {
                "is_mapped": True,
                "mapping_id": str(m.id),
                "asset_id": str(asset.id) if asset else None,
                "asset_code": getattr(asset, "asset_code", "FLT"),
                "asset_name": getattr(asset, "name", "Petty Cash Float"),
            }

    staging_lines = list(
        StatementStagingLine.objects.filter(row_identifier__in=row_ids)
    )
    staging_map = {s.row_identifier: s for s in staging_lines if s.row_identifier}
    contra_map = resolve_cross_account_contra_map(row_ids, staging_lines)

    pairing_legs = list(
        JournalEntry.objects.filter(row_identifier__in=row_ids)
        .exclude(account_id=99)
        .values("id", "row_identifier", "account_id", "debit", "credit", "remarks")
    )

    row_to_bank_leg = {}
    bank_acc_ids = set()
    for p in pairing_legs:
        acc_id = p["account_id"]
        if acc_id:
            bank_acc_ids.add(int(acc_id))
            if p["row_identifier"] not in row_to_bank_leg:
                row_to_bank_leg[p["row_identifier"]] = p

    account_lookup = {}
    if bank_acc_ids:
        for acc in Account.objects.filter(id__in=bank_acc_ids):
            acc_name = getattr(acc, "name", None) or getattr(acc, "bank_name", "Bank")
            acc_num = str(getattr(acc, "account_number", "") or "")
            last4 = acc_num[-4:] if len(acc_num) >= 4 else acc_num
            account_lookup[acc.id] = {
                "bank_name": acc_name,
                "bank_last4": last4,
            }

    items = []
    for entry in entries:
        remarks = entry.remarks if isinstance(entry.remarks, dict) else {}
        stg = staging_map.get(entry.row_identifier)
        bank_leg = row_to_bank_leg.get(entry.row_identifier) or {}
        mapping_info = mapping_map.get(entry.row_identifier) or {}
        contra_info = contra_map.get(
            entry.row_identifier,
            {"is_self_transfer": False, "contra_type": "ONE_WAY_EXTERNAL"},
        )

        raw_txn_date = (
            getattr(stg, "raw_statement_date", None)
            or remarks.get("raw_statement_date")
            or remarks.get("transaction_date")
            or entry.transaction_date
        )

        if stg:
            raw_narration = getattr(stg, "raw_narration", None) or getattr(
                stg, "narration", ""
            )
            parsed = getattr(stg, "parsed_narration", {}) or {}
            raw_payee = (
                parsed.get("suggested_payee") or parsed.get("statement_payee_raw") or ""
            )
            clean_payee = UniversalNarrationExtractor.repair_kerning_and_splits(
                raw_payee
            )
            ref_no = parsed.get("detected_reference")
            rail = parsed.get("detected_rail", "BANK")
            remark = parsed.get("suggested_remark")
            routing_status = getattr(stg, "routing_status", None)
        else:
            raw_narration = (
                remarks.get("universal_narration")
                or remarks.get("narration")
                or remarks.get("display_text")
                or ""
            )
            parsed = UniversalNarrationExtractor.decompose_raw_narration(raw_narration)
            clean_payee = UniversalNarrationExtractor.repair_kerning_and_splits(
                parsed.get("raw_payee") or remarks.get("payee") or ""
            )
            ref_no = parsed.get("reference") or remarks.get("upi_ref")
            rail = parsed.get("rail", "BANK")
            remark = parsed.get("raw_remark")
            routing_status = None

        debit_val = float(entry.debit or 0)
        credit_val = float(entry.credit or 0)
        is_outflow = debit_val > 0
        amount = debit_val if is_outflow else credit_val

        readable_narrative = build_human_readable_narrative(
            rail=rail,
            direction="OUTFLOW" if is_outflow else "INFLOW",
            amount=amount,
            payee=clean_payee,
            ref_no=ref_no,
            branch_or_remark=remark,
        )

        resolved_acc_id = bank_leg.get("account_id")
        if not resolved_acc_id:
            stg_acc_id = getattr(stg, "account_id", None)
            if stg_acc_id and int(stg_acc_id) != 99:
                resolved_acc_id = int(stg_acc_id)
            elif entry.account_id and int(entry.account_id) != 99:
                resolved_acc_id = int(entry.account_id)

        bank_meta = account_lookup.get(int(resolved_acc_id)) if resolved_acc_id else {}

        items.append(
            {
                "id": str(entry.id),
                "row_identifier": entry.row_identifier,
                "narration": readable_narrative,
                "raw_narration": raw_narration,
                "display_payee": clean_payee,
                "universal_narration": readable_narrative,
                "display_text": readable_narrative,
                "debit": debit_val,
                "credit": credit_val,
                "amount": amount,
                "direction": "OUTFLOW" if is_outflow else "INFLOW",
                "transaction_date": (
                    raw_txn_date.strftime("%Y-%m-%d")
                    if hasattr(raw_txn_date, "strftime")
                    else str(raw_txn_date)
                ),
                "account_id": resolved_acc_id,
                "bank_name": bank_meta.get("bank_name"),
                "bank_last4": bank_meta.get("bank_last4"),
                "is_mapped": bool(mapping_info.get("is_mapped")),
                "mapping_id": mapping_info.get("mapping_id"),
                "asset_id": mapping_info.get("asset_id"),
                "asset_code": mapping_info.get("asset_code"),
                "asset_name": mapping_info.get("asset_name"),
                "contra_meta": contra_info,
                "routing_status": routing_status,
                "remarks": {
                    **remarks,
                    "payee": clean_payee,
                    "universal_narration": readable_narrative,
                    "raw_narration": raw_narration,
                },
            }
        )

    return items


# # tracker/classification/engine.py
# from __future__ import annotations
# from typing import Any, Dict, List, Optional
# from django.apps import apps
# from django.db.models import Q
# from django.utils import timezone

# from tracker.models.models import ClassificationRule, JournalEntry
# from tracker.parsers.universal_narration import UniversalNarrationExtractor

# from .enginehelpers import (
#     TaggingEngine,
#     RuleLearningEngine,
#     resolve_cross_account_contra_map,
#     ConfidenceScorer,
# )
# from tracker.constants import (
#     GENERIC_IGNORE_PATTERNS,
#     GENERIC_PATTERNS,
#     KNOWN_MERCHANTS,
#     NOISE_KEYWORD_BLACKLIST,
#     RULE_SAFETY_BLACKLIST,
#     ABSOLUTE_GREEDY_BLACKLIST,
#     OK_WORD_LIST,
#     BLACKLIST_TAGS,
#     ALL_SYSTEM_BLACKLIST,
#     ACTION_AND_RAIL_NOISE,
# )

# extract_meaningful_tokens = TaggingEngine.extract_meaningful_tokens
# sanitize_user_pattern = RuleLearningEngine.sanitize_user_pattern
# extract_clean_payee_pattern = TaggingEngine.extract_clean_payee_pattern
# generate_strict_multitoken_pattern = (
#     RuleLearningEngine.generate_strict_multitoken_pattern
# )
# add_or_update_classification_rule = RuleLearningEngine.add_or_update_classification_rule
# match_multi_tokens = RuleLearningEngine.match_multi_tokens
# get_clean_patterns = RuleLearningEngine.get_clean_patterns
# generate_canonical_cluster_tag = TaggingEngine.generate_canonical_cluster_tag


# def build_human_readable_narrative(
#     rail: str,
#     direction: str,
#     amount: float,
#     payee: str,
#     ref_no: str | None,
#     branch_or_remark: str | None,
# ) -> str:
#     clean_payee = (
#         UniversalNarrationExtractor.repair_kerning_and_splits(payee)
#         if payee
#         else "Unspecified Entity"
#     )
#     rail_label = f" via {rail}" if rail and rail != "UNKNOWN" else ""
#     ref_label = f" (Ref: {ref_no})" if ref_no else ""

#     if direction == "OUTFLOW":
#         base = f"Paid ₹{amount:,.2f} to {clean_payee}{rail_label}{ref_label}"
#     else:
#         upper_payee = clean_payee.upper()
#         if "INTEREST" in upper_payee:
#             base = f"Interest Credit of ₹{amount:,.2f}{rail_label}"
#         elif "OWN" in upper_payee or "SELF" in upper_payee:
#             base = f"Self-Transfer / Deposit ₹{amount:,.2f}{rail_label}"
#         else:
#             base = f"Received ₹{amount:,.2f} from {clean_payee}{rail_label}{ref_label}"

#     if branch_or_remark and branch_or_remark.upper() not in [
#         "NO REMARKS",
#         clean_payee.upper(),
#     ]:
#         base += f" • {branch_or_remark}"

#     return base


# def _build_clusters_from_entries(
#     entries, target_subcategory, search_query=None, include_items=False
# ):
#     StatementStagingLine = apps.get_model("ledger", "StatementStagingLine")

#     row_ids = [e.row_identifier for e in entries if e.row_identifier]
#     staging_lines = list(
#         StatementStagingLine.objects.filter(row_identifier__in=row_ids)
#     )
#     staging_map = {s.row_identifier: s for s in staging_lines if s.row_identifier}

#     contra_map = resolve_cross_account_contra_map(row_ids, staging_lines)
#     acc_registry = TaggingEngine.get_dynamic_accounts_registry()
#     acc_lookup = {a["id"]: a for a in acc_registry}

#     clusters_map = {}

#     for entry in entries:
#         remarks = entry.remarks if isinstance(entry.remarks, dict) else {}
#         stg_line = staging_map.get(entry.row_identifier)
#         contra_info = contra_map.get(
#             entry.row_identifier,
#             {"is_self_transfer": False, "contra_type": "ONE_WAY_EXTERNAL"},
#         )

#         if stg_line:
#             parsed_meta = stg_line.parsed_narration or {}
#             raw_payee = (
#                 parsed_meta.get("suggested_payee") or stg_line.display_payee or ""
#             )
#             payee = TaggingEngine.repair_narration_kerning(raw_payee)
#             ref_no = parsed_meta.get("detected_reference")
#             rail = parsed_meta.get("detected_rail", "BANK")
#             remark = parsed_meta.get("suggested_remark")
#             raw_statement_text = getattr(stg_line, "raw_narration", None) or getattr(
#                 stg_line, "narration", ""
#             )
#             host_account_id = getattr(stg_line, "account_id", None) or entry.account_id
#         else:
#             fallback_text = (
#                 remarks.get("universal_narration")
#                 or remarks.get("narration")
#                 or remarks.get("display_text")
#                 or ""
#             )
#             parsed_meta = UniversalNarrationExtractor.decompose_raw_narration(
#                 fallback_text
#             )
#             raw_payee = (
#                 remarks.get("payee") or parsed_meta.get("raw_payee") or fallback_text
#             )
#             payee = TaggingEngine.repair_narration_kerning(raw_payee)
#             ref_no = remarks.get("upi_ref") or parsed_meta.get("reference")
#             rail = parsed_meta.get("rail", "BANK")
#             remark = parsed_meta.get("raw_remark")
#             raw_statement_text = fallback_text
#             host_account_id = entry.account_id

#         debit_val = float(entry.debit or 0)
#         credit_val = float(entry.credit or 0)
#         is_outflow = debit_val > 0
#         amount = debit_val if is_outflow else credit_val

#         # -------------------------------------------------------------
#         # Determine Tag, Canonical Title, Confidence & OK to Classify
#         # -------------------------------------------------------------
#         is_contra = contra_info.get("is_self_transfer", False)
#         pair_id = None

#         if is_contra:
#             pattern = "#CONTRA"
#             src_name = contra_info.get("from_account_name", "Bank").upper()
#             dst_name = contra_info.get("to_account_name", "Bank").upper()
#             canonical_title = f"{src_name} ➔ {dst_name}"
#             score, label, ok_to_classify = ConfidenceScorer.evaluate(
#                 is_paired_contra=True,
#                 has_ref_proof=bool(ref_no),
#                 has_rule_precedent=True,
#             )
#             # Normalize amount string for deterministic pair grouping
#             pair_amt = f"{amount:.2f}"
#             pair_id = (
#                 f"PAIR_{min(src_name, dst_name)}_{max(src_name, dst_name)}_{pair_amt}"
#             )
#             display_subgroup = canonical_title
#         else:
#             (
#                 pattern,
#                 canonical_title,
#                 score,
#                 label,
#                 ok_to_classify,
#             ) = TaggingEngine.generate_canonical_cluster_tag(
#                 raw_narration=raw_statement_text,
#                 payee=payee,
#                 host_account_id=host_account_id,
#                 registry=acc_registry,
#             )
#             display_subgroup = canonical_title

#         pattern = pattern.upper().strip()

#         if pattern not in clusters_map:
#             clusters_map[pattern] = {
#                 "pattern": pattern,
#                 "display_name": canonical_title,
#                 "count": 0,
#                 "total_amount": 0.0,
#                 "total_inflow": 0.0,
#                 "total_outflow": 0.0,
#                 "confidence_score": score,
#                 "confidence_label": label,
#                 "sample_descriptions": [],
#                 "items": [],
#                 "transaction_ids": [],
#                 "is_contra_group": (pattern == "#CONTRA"),
#             }

#         readable_narrative = build_human_readable_narrative(
#             rail=rail,
#             direction="OUTFLOW" if is_outflow else "INFLOW",
#             amount=amount,
#             payee=display_subgroup,
#             ref_no=ref_no,
#             branch_or_remark=remark,
#         )

#         cluster = clusters_map[pattern]
#         cluster["count"] += 1
#         cluster["total_amount"] += amount
#         if is_outflow:
#             cluster["total_outflow"] += amount
#         else:
#             cluster["total_inflow"] += amount

#         cluster["transaction_ids"].append(str(entry.id))
#         if (
#             len(cluster["sample_descriptions"]) < 2
#             and readable_narrative not in cluster["sample_descriptions"]
#         ):
#             cluster["sample_descriptions"].append(readable_narrative)

#         if include_items:
#             cluster["items"].append(
#                 {
#                     "id": str(entry.id),
#                     "pair_id": pair_id or f"SINGLE_{entry.id}",
#                     "ok_to_classify": ok_to_classify,
#                     "confidence_score": score,
#                     "confidence_label": label,
#                     "narration": raw_statement_text,
#                     "raw_narration": raw_statement_text,
#                     "display_payee": display_subgroup,
#                     "universal_narration": readable_narrative,
#                     "debit": debit_val,
#                     "credit": credit_val,
#                     "amount": amount,
#                     "direction": "OUTFLOW" if is_outflow else "INFLOW",
#                     "transaction_date": str(entry.transaction_date),
#                     "contra_meta": contra_info,
#                 }
#             )

#     # Sort cluster line items so matched pairs sit adjacent:
#     if include_items:
#         for c in clusters_map.values():
#             c["items"].sort(
#                 key=lambda x: (x["pair_id"], x["transaction_date"], x["direction"])
#             )

#     sorted_clusters = sorted(
#         clusters_map.values(), key=lambda c: c["count"], reverse=True
#     )

#     if search_query and str(search_query).strip():
#         norm_query = search_query.strip().upper()
#         return [
#             c
#             for c in sorted_clusters
#             if norm_query in c["pattern"].upper()
#             or any(norm_query in s.upper() for s in c.get("sample_descriptions", []))
#         ]

#     return sorted_clusters


# # def _build_clusters_from_entries(
# #     entries, target_subcategory, search_query=None, include_items=False
# # ):
# #     StatementStagingLine = apps.get_model("ledger", "StatementStagingLine")

# #     row_ids = [e.row_identifier for e in entries if e.row_identifier]
# #     staging_lines = list(
# #         StatementStagingLine.objects.filter(row_identifier__in=row_ids)
# #     )
# #     staging_map = {s.row_identifier: s for s in staging_lines if s.row_identifier}

# #     contra_map = resolve_cross_account_contra_map(row_ids, staging_lines)
# #     acc_registry = TaggingEngine.get_dynamic_accounts_registry()

# #     clusters_map = {}

# #     for entry in entries:
# #         remarks = entry.remarks if isinstance(entry.remarks, dict) else {}
# #         stg_line = staging_map.get(entry.row_identifier)
# #         contra_info = contra_map.get(
# #             entry.row_identifier,
# #             {"is_self_transfer": False, "contra_type": "ONE_WAY_EXTERNAL"},
# #         )

# #         if stg_line:
# #             parsed_meta = stg_line.parsed_narration or {}
# #             raw_payee = (
# #                 parsed_meta.get("suggested_payee") or stg_line.display_payee or ""
# #             )
# #             ref_no = parsed_meta.get("detected_reference")
# #             rail = parsed_meta.get("detected_rail", "BANK")
# #             remark = parsed_meta.get("suggested_remark")
# #             raw_statement_text = getattr(stg_line, "raw_narration", None) or getattr(
# #                 stg_line, "narration", ""
# #             )
# #             host_account_id = getattr(stg_line, "account_id", None) or entry.account_id
# #         else:
# #             fallback_text = (
# #                 remarks.get("universal_narration")
# #                 or remarks.get("narration")
# #                 or remarks.get("display_text")
# #                 or ""
# #             )
# #             parsed_meta = UniversalNarrationExtractor.decompose_raw_narration(
# #                 fallback_text
# #             )
# #             raw_payee = (
# #                 remarks.get("payee") or parsed_meta.get("raw_payee") or fallback_text
# #             )
# #             ref_no = remarks.get("upi_ref") or parsed_meta.get("reference")
# #             rail = parsed_meta.get("rail", "BANK")
# #             remark = parsed_meta.get("raw_remark")
# #             raw_statement_text = fallback_text
# #             host_account_id = entry.account_id

# #         debit_val = float(entry.debit or 0)
# #         credit_val = float(entry.credit or 0)
# #         is_outflow = debit_val > 0
# #         amount = debit_val if is_outflow else credit_val

# #         # Route tagging, scoring, and pair isolation delegated to TaggingEngine
# #         is_contra = contra_info.get("is_self_transfer", False)
# #         (
# #             pattern,
# #             canonical_title,
# #             display_subgroup,
# #             pair_id,
# #             score,
# #             label,
# #             ok_to_classify,
# #         ) = TaggingEngine.resolve_cluster_envelope(
# #             is_contra=is_contra,
# #             contra_info=contra_info,
# #             raw_narration=raw_statement_text,
# #             payee=raw_payee,
# #             amount=amount,
# #             ref_no=ref_no,
# #             host_account_id=host_account_id,
# #             acc_registry=acc_registry,
# #         )
# #         if (
# #             "BAIJU" in str(raw_payee).upper()
# #             or "FRIEND" in str(raw_statement_text).upper()
# #         ):
# #             print(
# #                 f"\n>>> [CLUSTER DEBUG] Raw: {raw_statement_text[:35]}... | "
# #                 f"Payee: {raw_payee} -> Subgroup: {display_subgroup} | "
# #                 f"Pattern: {pattern} | Score: {score}",
# #                 flush=True,
# #             )

# #         if pattern not in clusters_map:
# #             clusters_map[pattern] = TaggingEngine.create_empty_cluster(
# #                 pattern=pattern,
# #                 display_name=canonical_title,
# #                 score=score,
# #                 label=label,
# #                 is_contra=is_contra,
# #             )

# #         readable_narrative = build_human_readable_narrative(
# #             rail=rail,
# #             direction="OUTFLOW" if is_outflow else "INFLOW",
# #             amount=amount,
# #             payee=display_subgroup,
# #             ref_no=ref_no,
# #             branch_or_remark=remark,
# #         )

# #         cluster = clusters_map[pattern]
# #         cluster["count"] += 1
# #         cluster["total_amount"] += amount
# #         if is_outflow:
# #             cluster["total_outflow"] += amount
# #         else:
# #             cluster["total_inflow"] += amount

# #         cluster["transaction_ids"].append(str(entry.id))
# #         if (
# #             len(cluster["sample_descriptions"]) < 2
# #             and readable_narrative not in cluster["sample_descriptions"]
# #         ):
# #             cluster["sample_descriptions"].append(readable_narrative)

# #         if include_items:
# #             cluster["items"].append(
# #                 {
# #                     "id": str(entry.id),
# #                     "pair_id": pair_id or f"SINGLE_{entry.id}",
# #                     "ok_to_classify": ok_to_classify,
# #                     "confidence_score": score,
# #                     "confidence_label": label,
# #                     "narration": raw_statement_text,
# #                     "raw_narration": raw_statement_text,
# #                     "display_payee": display_subgroup,
# #                     "universal_narration": readable_narrative,
# #                     "debit": debit_val,
# #                     "credit": credit_val,
# #                     "amount": amount,
# #                     "direction": "OUTFLOW" if is_outflow else "INFLOW",
# #                     "transaction_date": str(entry.transaction_date),
# #                     "contra_meta": contra_info,
# #                 }
# #             )

# #     # Sort cluster items so paired transactions sit side-by-side
# #     if include_items:
# #         for c in clusters_map.values():
# #             c["items"].sort(
# #                 key=lambda x: (x["pair_id"], x["transaction_date"], x["direction"])
# #             )

# #     sorted_clusters = sorted(
# #         clusters_map.values(), key=lambda c: c["count"], reverse=True
# #     )

# #     if search_query and str(search_query).strip():
# #         norm_query = search_query.strip().upper()
# #         return [
# #             c
# #             for c in sorted_clusters
# #             if norm_query in c["pattern"].upper()
# #             or any(norm_query in s.upper() for s in c.get("sample_descriptions", []))
# #         ]

# #     return sorted_clusters


# def get_suspense_workbench_clusters(
#     account_id=None, search_query=None, include_cleared=False, include_items=False
# ):
#     JournalEntry = apps.get_model("ledger", "JournalEntry")
#     query = JournalEntry.objects.filter(account_id=99)
#     if not include_cleared:
#         query = query.filter(is_reclassified=False)

#     if account_id and str(account_id) != "99":
#         bank_row_ids = JournalEntry.objects.filter(account_id=account_id).values_list(
#             "row_identifier", flat=True
#         )
#         query = query.filter(row_identifier__in=bank_row_ids)

#     entries = list(
#         query.only(
#             "id", "row_identifier", "debit", "credit", "remarks", "transaction_date"
#         ).order_by("-transaction_date")
#     )
#     return _build_clusters_from_entries(
#         entries, "Suspense Account", search_query, include_items
#     )


# def get_gl_head_workbench_clusters(
#     target_subcategory: str, search_query=None, include_items=False
# ):
#     JournalEntry = apps.get_model("ledger", "JournalEntry")
#     AssetSubLedger = apps.get_model("ledger", "AssetSubLedger")
#     AssetTransactionMapping = apps.get_model("ledger", "AssetTransactionMapping")

#     sub_clean = target_subcategory.strip()
#     related_asset_ids = AssetSubLedger.objects.filter(
#         Q(category__icontains=sub_clean)
#         | Q(asset_category__name__icontains=sub_clean)
#         | Q(asset_category__default_taxonomy_subcategory__icontains=sub_clean)
#     ).values_list("id", flat=True)

#     bound_row_ids = list(
#         AssetTransactionMapping.objects.filter(
#             asset_id__in=related_asset_ids
#         ).values_list("row_identifier", flat=True)
#     )

#     gl_filter = (
#         Q(evaluation_matrix_snapshot__resolved_subcategory__iexact=sub_clean)
#         | Q(remarks__target_account_name__iexact=sub_clean)
#         | Q(remarks__subcategory__iexact=sub_clean)
#     )
#     if bound_row_ids:
#         gl_filter |= Q(row_identifier__in=bound_row_ids)

#     query = (
#         JournalEntry.objects.filter(gl_filter, debit__gt=0)
#         .only("id", "row_identifier", "debit", "credit", "remarks", "transaction_date")
#         .order_by("-transaction_date")
#     )

#     seen_row_ids = set()
#     entries = []
#     for e in list(query):
#         rid = e.row_identifier or str(e.id)
#         if rid in seen_row_ids:
#             continue
#         seen_row_ids.add(rid)
#         entries.append(e)

#     return _build_clusters_from_entries(entries, sub_clean, search_query, include_items)


# def get_suspense_clusters(
#     target_subcategory="Suspense Account",
#     account_id=None,
#     search_query=None,
#     include_cleared=False,
#     include_items=False,
# ):
#     if not target_subcategory or target_subcategory.strip() in [
#         "Suspense Account",
#         "All",
#     ]:
#         return get_suspense_workbench_clusters(
#             account_id, search_query, include_cleared, include_items
#         )
#     return get_gl_head_workbench_clusters(
#         target_subcategory, search_query, include_items
#     )


# def reclassify_and_learn(
#     transaction_ids: List[str],
#     target_category: str,
#     target_subcategory: str,
#     patterns: Optional[List[str]] = None,
#     save_rule: bool = True,
# ) -> Dict[str, Any]:
#     if not transaction_ids:
#         return {"status": "success", "reclassified_count": 0, "rules_updated": False}

#     entries = list(JournalEntry.objects.filter(account_id=99, id__in=transaction_ids))
#     if not entries:
#         entries = list(
#             JournalEntry.objects.filter(
#                 account_id=99, row_identifier__in=transaction_ids
#             )
#         )

#     if not entries:
#         return {"status": "success", "reclassified_count": 0, "rules_updated": False}

#     total_debit = sum(float(e.debit or 0) for e in entries)
#     total_credit = sum(float(e.credit or 0) for e in entries)
#     inferred_entry_type = "Credit" if total_credit > total_debit else "Debit"

#     payee_groups = {}
#     for entry in entries:
#         snapshot = entry.evaluation_matrix_snapshot or {}
#         snapshot["previous_category"] = snapshot.get("resolved_category")
#         snapshot["previous_subcategory"] = snapshot.get("resolved_subcategory")
#         snapshot["resolved_category"] = target_category
#         snapshot["resolved_subcategory"] = target_subcategory
#         snapshot["is_manual_override"] = True

#         entry.evaluation_matrix_snapshot = snapshot
#         entry.classification_status = "RECLASSIFIED"
#         entry.is_reclassified = True

#         remarks_dict = entry.remarks if isinstance(entry.remarks, dict) else {}
#         narration_text = remarks_dict.get("narration") or str(entry.remarks or "")
#         payee = remarks_dict.get("payee") or ""
#         clean_payee = (
#             TaggingEngine.extract_clean_payee_pattern(payee or narration_text)
#             or "GENERIC"
#         )

#         if clean_payee not in payee_groups:
#             payee_groups[clean_payee] = []
#         if narration_text:
#             payee_groups[clean_payee].append(narration_text)

#         entry.remarks = {
#             **remarks_dict,
#             "target_account_name": target_subcategory,
#             "updated_at": timezone.now().isoformat(),
#         }

#     JournalEntry.objects.bulk_update(
#         entries,
#         [
#             "evaluation_matrix_snapshot",
#             "classification_status",
#             "is_reclassified",
#             "remarks",
#         ],
#     )

#     rules_updated = False
#     learned_patterns = []

#     if save_rule:
#         if patterns and isinstance(patterns, list) and len(patterns) > 0:
#             for user_p in patterns:
#                 clean_user_p = RuleLearningEngine.sanitize_user_pattern(user_p)
#                 if not clean_user_p:
#                     continue
#                 if len(clean_user_p) >= 3:
#                     if RuleLearningEngine.add_or_update_classification_rule(
#                         category=target_category,
#                         subcategory=target_subcategory,
#                         new_pattern=clean_user_p,
#                         entry_type=inferred_entry_type,
#                     ):
#                         rules_updated = True
#                         learned_patterns.append(clean_user_p)
#         else:
#             for payee_key, group_narrations in payee_groups.items():
#                 common_tokens = RuleLearningEngine.generate_strict_multitoken_pattern(
#                     group_narrations
#                 )
#                 safe_tokens = [
#                     t
#                     for t in common_tokens
#                     if not TaggingEngine.is_ref_hash_or_noise(t) and len(t) > 2
#                 ]
#                 if safe_tokens:
#                     compound_pattern = " ".join(safe_tokens[:2])
#                     if len(compound_pattern) >= 3:
#                         if RuleLearningEngine.add_or_update_classification_rule(
#                             category=target_category,
#                             subcategory=target_subcategory,
#                             new_pattern=compound_pattern,
#                             entry_type=inferred_entry_type,
#                         ):
#                             rules_updated = True
#                             learned_patterns.append(compound_pattern)

#     return {
#         "status": "success",
#         "reclassified_count": len(entries),
#         "entry_type_bound": inferred_entry_type,
#         "rules_updated": rules_updated,
#         "patterns_learned": learned_patterns,
#     }


# def fetch_cluster_line_items(entry_ids: list) -> list:
#     """
#     Fetches detailed line-item payload for an expanded cluster accordion.
#     Retrieves journal entries, statement staging lines, contra metadata,
#     and existing subledger folio mappings.
#     """
#     if not entry_ids:
#         return []

#     JournalEntry = apps.get_model("ledger", "JournalEntry")
#     StatementStagingLine = apps.get_model("ledger", "StatementStagingLine")
#     Account = apps.get_model("ledger", "Account")

#     AssetTransactionMapping = None
#     for model in apps.get_models():
#         if model.__name__ == "AssetTransactionMapping":
#             AssetTransactionMapping = model
#             break

#     # 1. Fetch journal entries
#     entries = list(
#         JournalEntry.objects.filter(id__in=entry_ids)
#         .only(
#             "id",
#             "row_identifier",
#             "account_id",
#             "debit",
#             "credit",
#             "remarks",
#             "transaction_date",
#         )
#         .order_by("-transaction_date")
#     )

#     row_ids = [e.row_identifier for e in entries if e.row_identifier]

#     # 2. Query Asset mappings by row_identifier
#     mapping_map = {}
#     if row_ids and AssetTransactionMapping:
#         mappings = AssetTransactionMapping.objects.filter(
#             row_identifier__in=row_ids
#         ).select_related("asset")
#         for m in mappings:
#             asset = getattr(m, "asset", None)
#             mapping_map[m.row_identifier] = {
#                 "is_mapped": True,
#                 "mapping_id": str(m.id),
#                 "asset_id": str(asset.id) if asset else None,
#                 "asset_code": getattr(asset, "asset_code", "FLT"),
#                 "asset_name": getattr(asset, "name", "Petty Cash Float"),
#             }

#     # 3. Fetch staging lines
#     staging_lines = list(
#         StatementStagingLine.objects.filter(row_identifier__in=row_ids)
#     )
#     staging_map = {s.row_identifier: s for s in staging_lines if s.row_identifier}

#     # 4. Resolve internal contra transfers
#     contra_map = resolve_cross_account_contra_map(row_ids, staging_lines)

#     # 5. Fetch pairing bank account legs
#     pairing_legs = list(
#         JournalEntry.objects.filter(row_identifier__in=row_ids)
#         .exclude(account_id=99)
#         .values("id", "row_identifier", "account_id", "debit", "credit", "remarks")
#     )

#     row_to_bank_leg = {}
#     bank_acc_ids = set()
#     for p in pairing_legs:
#         acc_id = p["account_id"]
#         if acc_id:
#             bank_acc_ids.add(int(acc_id))
#             if p["row_identifier"] not in row_to_bank_leg:
#                 row_to_bank_leg[p["row_identifier"]] = p

#     account_lookup = {}
#     if bank_acc_ids:
#         for acc in Account.objects.filter(id__in=bank_acc_ids):
#             acc_name = getattr(acc, "name", None) or getattr(acc, "bank_name", "Bank")
#             acc_num = str(getattr(acc, "account_number", "") or "")
#             last4 = acc_num[-4:] if len(acc_num) >= 4 else acc_num
#             account_lookup[acc.id] = {
#                 "bank_name": acc_name,
#                 "bank_last4": last4,
#             }

#     items = []
#     for entry in entries:
#         remarks = entry.remarks if isinstance(entry.remarks, dict) else {}
#         stg = staging_map.get(entry.row_identifier)
#         bank_leg = row_to_bank_leg.get(entry.row_identifier) or {}
#         mapping_info = mapping_map.get(entry.row_identifier) or {}
#         contra_info = contra_map.get(
#             entry.row_identifier,
#             {"is_self_transfer": False, "contra_type": "ONE_WAY_EXTERNAL"},
#         )

#         raw_txn_date = (
#             getattr(stg, "raw_statement_date", None)
#             or remarks.get("raw_statement_date")
#             or remarks.get("transaction_date")
#             or entry.transaction_date
#         )

#         if stg:
#             raw_narration = getattr(stg, "raw_narration", None) or getattr(
#                 stg, "narration", ""
#             )
#             parsed = getattr(stg, "parsed_narration", {}) or {}
#             raw_payee = (
#                 parsed.get("suggested_payee") or parsed.get("statement_payee_raw") or ""
#             )
#             clean_payee = UniversalNarrationExtractor.repair_kerning_and_splits(
#                 raw_payee
#             )
#             ref_no = parsed.get("detected_reference")
#             rail = parsed.get("detected_rail", "BANK")
#             remark = parsed.get("suggested_remark")
#         else:
#             raw_narration = (
#                 remarks.get("universal_narration")
#                 or remarks.get("narration")
#                 or remarks.get("display_text")
#                 or ""
#             )
#             parsed = UniversalNarrationExtractor.decompose_raw_narration(raw_narration)
#             clean_payee = UniversalNarrationExtractor.repair_kerning_and_splits(
#                 parsed.get("raw_payee") or remarks.get("payee") or ""
#             )
#             ref_no = parsed.get("reference") or remarks.get("upi_ref")
#             rail = parsed.get("rail", "BANK")
#             remark = parsed.get("raw_remark")

#         debit_val = float(entry.debit or 0)
#         credit_val = float(entry.credit or 0)
#         is_outflow = debit_val > 0
#         amount = debit_val if is_outflow else credit_val

#         readable_narrative = build_human_readable_narrative(
#             rail=rail,
#             direction="OUTFLOW" if is_outflow else "INFLOW",
#             amount=amount,
#             payee=clean_payee,
#             ref_no=ref_no,
#             branch_or_remark=remark,
#         )

#         resolved_acc_id = bank_leg.get("account_id")
#         if not resolved_acc_id:
#             stg_acc_id = getattr(stg, "account_id", None)
#             if stg_acc_id and int(stg_acc_id) != 99:
#                 resolved_acc_id = int(stg_acc_id)
#             elif entry.account_id and int(entry.account_id) != 99:
#                 resolved_acc_id = int(entry.account_id)

#         bank_meta = account_lookup.get(int(resolved_acc_id)) if resolved_acc_id else {}

#         items.append(
#             {
#                 "id": str(entry.id),
#                 "row_identifier": entry.row_identifier,
#                 "narration": readable_narrative,
#                 "raw_narration": raw_narration,
#                 "display_payee": clean_payee,
#                 "universal_narration": readable_narrative,
#                 "display_text": readable_narrative,
#                 "debit": debit_val,
#                 "credit": credit_val,
#                 "amount": amount,
#                 "direction": "OUTFLOW" if is_outflow else "INFLOW",
#                 "transaction_date": (
#                     raw_txn_date.strftime("%Y-%m-%d")
#                     if hasattr(raw_txn_date, "strftime")
#                     else str(raw_txn_date)
#                 ),
#                 "account_id": resolved_acc_id,
#                 "bank_name": bank_meta.get("bank_name"),
#                 "bank_last4": bank_meta.get("bank_last4"),
#                 "is_mapped": bool(mapping_info.get("is_mapped")),
#                 "mapping_id": mapping_info.get("mapping_id"),
#                 "asset_id": mapping_info.get("asset_id"),
#                 "asset_code": mapping_info.get("asset_code"),
#                 "asset_name": mapping_info.get("asset_name"),
#                 "contra_meta": contra_info,
#                 "remarks": {
#                     **remarks,
#                     "payee": clean_payee,
#                     "universal_narration": readable_narrative,
#                     "raw_narration": raw_narration,
#                 },
#             }
#         )

#     return items


# from __future__ import annotations
# from datetime import datetime, date
# import hashlib
# import json
# import re
# from typing import Any, Dict, List, Optional, Set
# from collections import Counter, defaultdict
# from django.apps import apps

# from django.db.models import Q
# from django.utils import timezone

# from tracker.constants import (
#     ALL_SYSTEM_BLACKLIST,
#     CORPORATE_NOISE_SUFFIXES,
#     KNOWN_MERCHANTS,
#     NOISE_KEYWORD_BLACKLIST,
#     OK_WORD_LIST,
#     RULE_SAFETY_BLACKLIST,
#     TRANSFER_BANK_NOISE,
#     UPI_RAIL_TOKENS,
#     ParserRegex,
#     TokenCatalog,
# )


# from tracker.classification.remarks_service import (
#     generate_cluster_pattern,
#     canonicalize_merchant_token,
#     BLACKLIST_TAGS,
# )
# from tracker.classification.utils.upiparser import parse_upi_narration
# from tracker.parsers.universal_narration import UniversalNarrationExtractor

# from ..models.models import (
#     AccountingRule,
#     ClassificationRule,
#     JournalEntry,
#     StatementStagingLine,
#     TaxonomyTree,
# )
# from tracker.constants import (
#     NOISE_KEYWORD_BLACKLIST,
#     GENERIC_IGNORE_PATTERNS,
#     GENERIC_PATTERNS,
#     KNOWN_MERCHANTS,
#     RULE_SAFETY_BLACKLIST,
#     ABSOLUTE_GREEDY_BLACKLIST,
#     OK_WORD_LIST,
# )

# # At the top of engine.py:
# from tracker.classification.remarks_service import (
#     generate_cluster_pattern,
#     canonicalize_merchant_token,
#     BLACKLIST_TAGS,
# )

# GENERIC_NOISE_TOKENS = NOISE_KEYWORD_BLACKLIST

# _STRUCTURAL_PREFIX_REGEX = re.compile(
#     r"^(?:TO\s+|BY\s+)?(?:ECM|UPIOUT|UPIIN|IMPS|NEFT|RTGS|WDL|INB|MB|FTB|FTO|DEP|BIL|POS)\b",
#     re.IGNORECASE,
# )
# ACTION_AND_RAIL_NOISE: Set[str] = {
#     "TRF",
#     "TRANSFER",
#     "TRANS",
#     "WDL",
#     "DEP",
#     "DEPOSIT",
#     "WITHDRAWAL",
#     "UPI",
#     "UPIOUT",
#     "UPIIN",
#     "IMPS",
#     "NEFT",
#     "RTGS",
#     "ACH",
#     "NACH",
#     "POS",
#     "INB",
#     "MB",
#     "FTB",
#     "FTO",
#     "OPE",
#     "BIL",
#     "CLG",
#     "CHQ",
#     "CHEQUE",
#     "ECM",
#     "CYBSS",
#     "ECOM",
#     "REMARK",
#     "REMARKS",
#     "NO",
#     "NULL",
#     "YES",
#     "ACCOUNT",
#     "A/C",
# }

# _CBS_SESSION_REGEX = re.compile(r"\b[A-Z]\d{6,10}\b", re.IGNORECASE)
# _NUMERIC_ID_REGEX = re.compile(r"\b\d{4,}\b")
# _VPA_REGEX = re.compile(r"([A-Z0-9.\-_]+)@([A-Z]+)", re.IGNORECASE)

# _LONG_DIGIT_REGEX = re.compile(r"\b\d{4,}\b")


# def normalize_for_search(text: str) -> str:
#     """Strips underscores, spaces, dashes, colons, and punctuation for fuzzy matching."""
#     if not text:
#         return ""
#     return re.sub(r"[^A-Z0-9]+", "", str(text).upper())


# def normalize_condensed(text: str) -> str:
#     """Strips all non-alphanumeric characters AND spaces for fuzzy boundary evaluation."""
#     if not text:
#         return ""
#     return re.sub(r"[^A-Z0-9]", "", str(text).upper())


# def is_ref_hash_or_noise(token: str) -> bool:
#     """
#     Detects UPI transaction hashes, reference numbers, and mixed alphanumeric strings.
#     E.g., 'Q672606239', 'PYTM40905', 'YBL123', '9876543210'
#     """
#     if not token or not str(token).strip():
#         return True

#     clean_t = str(token).strip().upper()

#     # Pure numbers (account/ref numbers)
#     if clean_t.isdigit():
#         return True

#     # Alphanumeric reference strings containing BOTH letters and numbers
#     if re.search(r"[A-Z]", clean_t) and re.search(r"[0-9]", clean_t):
#         return True

#     # Ultra long tokens (>20 chars) are usually bank hashes
#     if len(clean_t) > 20:
#         return True

#     return False


# def sanitize_user_pattern(pattern: str) -> str:
#     """
#     Cleans explicit user-selected patterns (e.g. 'APAN DAS', 'MARGIN FREE HYPERMAR')
#     as ATOMIC phrases without splitting multi-word strings into individual tokens,
#     while stripping out UPI reference hashes and numbers.
#     """
#     if not pattern or not str(pattern).strip():
#         return ""

#     # 1. Strip special characters (keep alphanumerics and spaces)
#     clean_str = re.sub(r"[^A-Z0-9\.\s]", " ", str(pattern).upper())

#     # 2. Collapse internal whitespace (e.g. "APAN    DAS" -> "APAN DAS")
#     clean_str = re.sub(r"\s+", " ", clean_str).strip()

#     if not clean_str:
#         return ""

#     # 3. Verify component words against blacklists AND ref hash filters
#     words = clean_str.split()
#     valid_words = [
#         w
#         for w in words
#         if w not in NOISE_KEYWORD_BLACKLIST
#         and w not in RULE_SAFETY_BLACKLIST
#         and not is_ref_hash_or_noise(w)  # 💡 Strips out 'Q672606239', 'PYTM123', etc.
#     ]

#     # If every word in the pattern was noise or ref hash, reject
#     if not valid_words:
#         return ""

#     # Reconstruct intact multi-word phrase
#     return " ".join(valid_words)


# def sanitize_explicit_user_pattern(pattern: str) -> str:
#     """
#     Bypasses standard noise blacklists (allows 'SUMEE', 'INT.PD', etc.),
#     while ensuring string safety and preventing dangerous greedy catch-alls.
#     """
#     if not pattern or not str(pattern).strip():
#         return ""

#     raw = str(pattern).upper().strip()

#     # 1. Reject universal system catch-alls
#     if raw in ABSOLUTE_GREEDY_BLACKLIST or len(raw) < 2:
#         return ""

#     # 2. Convert non-alphanumerics to spaces (or preserve dots depending on matcher strategy)
#     clean = re.sub(r"[^A-Z0-9\s]", " ", raw)
#     clean = re.sub(r"\s+", " ", clean).strip()

#     return clean


# def extract_meaningful_tokens(text: str) -> list[str]:
#     """
#     Cleans raw statement narrations and extracts candidate words
#     for auto-rule generation, filtering out blacklisted noise and ref hashes.
#     """
#     if not text:
#         return []

#     clean_str = re.sub(r"[^A-Z0-9\s]", " ", str(text).upper())
#     clean_str = re.sub(r"\s+", " ", clean_str).strip()

#     raw_tokens = clean_str.split()

#     filtered_tokens = []
#     for token in raw_tokens:
#         if token in NOISE_KEYWORD_BLACKLIST or token in RULE_SAFETY_BLACKLIST:
#             continue

#         if is_ref_hash_or_noise(token):
#             continue

#         filtered_tokens.append(token)

#     return filtered_tokens


# def match_multi_tokens(
#     narration: str, pattern: str, min_required_tokens: int = 2
# ) -> bool:
#     """
#     Validates if narration matches rule pattern tokens.
#     Requires at least `min_required_tokens` AND all pattern tokens to be present.
#     """
#     if not narration or not pattern:
#         return False

#     narration_tokens = set(extract_meaningful_tokens(narration))
#     pattern_tokens = set(extract_meaningful_tokens(pattern))

#     if not pattern_tokens:
#         return False

#     if len(pattern_tokens) < min_required_tokens:
#         condensed_narration = normalize_condensed(narration)
#         condensed_pattern = normalize_condensed(pattern)
#         return len(condensed_pattern) >= 6 and condensed_pattern in condensed_narration

#     if pattern_tokens.issubset(narration_tokens):
#         return True

#     condensed_narration = normalize_condensed(narration)
#     condensed_pattern = normalize_condensed(pattern)

#     return len(condensed_pattern) >= 6 and condensed_pattern in condensed_narration


# def extract_clean_payee_pattern(narration: str) -> str:
#     """Extracts true merchant/person payee name, stripping reference noise and slashes."""
#     if not narration or not str(narration).strip():
#         return ""

#     text = str(narration).strip().upper()

#     pos_match = re.search(r"\(([^)]+)\)", text)
#     if pos_match:
#         candidate = pos_match.group(1).strip()
#         if len(candidate) >= 3 and not candidate.startswith("CIAL"):
#             return candidate

#     tokens = extract_meaningful_tokens(text)
#     if not tokens:
#         return text[:30]

#     for token in tokens:
#         if token in KNOWN_MERCHANTS:
#             return token

#     clean_tokens = tokens[:2] if len(tokens) >= 2 else tokens
#     return " ".join(clean_tokens)


# def normalize_for_search(text: str) -> str:
#     """Strips underscores, spaces, dashes, colons, and punctuation for fuzzy matching."""
#     if not text:
#         return ""
#     return re.sub(r"[^A-Z0-9]+", "", str(text).upper())


# def extract_canonical_entity_tokens(raw_name: str) -> List[str]:
#     """
#     Extracts authentic entity anchors without letting transaction noise (like TRF,
#     UPIOUT, session IDs, or generic account words) form clusters.
#     """
#     if not raw_name:
#         return []

#     repaired = UniversalNarrationExtractor.repair_kerning_and_splits(raw_name).upper()

#     # 1. Check for UPI VPA patterns (e.g. '78883165@PAYTM' or 'merchant@ybl')
#     # If the VPA contains a recognizable name/merchant, give it priority
#     vpa_match = _VPA_REGEX.search(repaired)
#     vpa_entity = None
#     if vpa_match:
#         handle, psp = vpa_match.group(1), vpa_match.group(2)
#         # If handle is not pure digits/phone number, it's a merchant identifier
#         if not handle.isdigit() and len(handle) > 2:
#             vpa_entity = handle

#     # 2. Strip CBS Session numbers (e.g. S40173293, S63277424, S30180487)
#     cleaned = _CBS_SESSION_REGEX.sub(" ", repaired)

#     # 3. Strip long numeric reference sequences, mobile numbers, and RRNs
#     cleaned = _NUMERIC_ID_REGEX.sub(" ", cleaned)

#     # 4. Tokenize
#     raw_tokens = re.findall(r"[A-Z0-9]+", cleaned)

#     # 5. Combined master blacklist
#     filter_blacklist: Set[str] = (
#         ACTION_AND_RAIL_NOISE
#         | UPI_RAIL_TOKENS
#         | NOISE_KEYWORD_BLACKLIST
#         | RULE_SAFETY_BLACKLIST
#         | TRANSFER_BANK_NOISE
#         | CORPORATE_NOISE_SUFFIXES
#         | TokenCatalog.GENERIC_MERCHANT_NOISE_WORDS
#     ) - OK_WORD_LIST

#     meaningful_tokens: List[str] = []

#     # If a clear merchant VPA handle was found, prepend it
#     if vpa_entity and vpa_entity not in filter_blacklist:
#         meaningful_tokens.append(vpa_entity)

#     for token in raw_tokens:
#         if token.isdigit():
#             continue

#         # Prioritize known merchants
#         if token in KNOWN_MERCHANTS:
#             meaningful_tokens.append(token)
#             continue

#         # Keep clean alphabetic tokens that are not noise
#         if (token in OK_WORD_LIST) or (
#             len(token) > 1 and token not in filter_blacklist
#         ):
#             meaningful_tokens.append(token)

#     # Deduplicate while preserving order
#     seen = set()
#     deduped = []
#     for t in meaningful_tokens:
#         if t not in seen:
#             seen.add(t)
#             deduped.append(t)

#     return deduped


# def generate_canonical_cluster_tag(raw_name: str) -> str:
#     """
#     Deterministic clustering hash. Prevents '#TRF' from swallowing lines.
#     """
#     if not raw_name:
#         return "#SUSPENSE"

#     tokens = extract_canonical_entity_tokens(raw_name)

#     if not tokens:
#         return "#UNRESOLVED_VENDOR"

#     # Ensure 'TRF' or standalone rail noise NEVER becomes the tag
#     valid_tokens = [t for t in tokens if t not in ACTION_AND_RAIL_NOISE]
#     if not valid_tokens:
#         return "#UNRESOLVED_TRANSFER"

#     # Up to 2 meaningful entity words form the anchor
#     cluster_slug = "_".join(valid_tokens[:2])
#     return f"#{cluster_slug}"


# def build_human_readable_narrative(
#     rail: str,
#     direction: str,
#     amount: float,
#     payee: str,
#     ref_no: str | None,
#     branch_or_remark: str | None,
# ) -> str:
#     # 🟢 Single location for space repair
#     clean_payee = (
#         UniversalNarrationExtractor.repair_kerning_and_splits(payee)
#         if payee
#         else "Unspecified Entity"
#     )
#     rail_label = f" via {rail}" if rail and rail != "UNKNOWN" else ""
#     ref_label = f" (Ref: {ref_no})" if ref_no else ""

#     if direction == "OUTFLOW":
#         base = f"Paid ₹{amount:,.2f} to {clean_payee}{rail_label}{ref_label}"
#     else:
#         upper_payee = clean_payee.upper()
#         if "INTEREST" in upper_payee:
#             base = f"Interest Credit of ₹{amount:,.2f}{rail_label}"
#         elif "OWN" in upper_payee or "SELF" in upper_payee:
#             base = f"Self-Transfer / Deposit ₹{amount:,.2f}{rail_label}"
#         else:
#             base = f"Received ₹{amount:,.2f} from {clean_payee}{rail_label}{ref_label}"

#     if branch_or_remark and branch_or_remark.upper() not in [
#         "NO REMARKS",
#         clean_payee.upper(),
#     ]:
#         base += f" • {branch_or_remark}"

#     return base


# # -------------------------------------------------------------------
# # 🧩 HELPER: RESOLVE INTERNAL CONTRA TRANSFERS
# # -------------------------------------------------------------------
# def extract_candidate_ref_tokens(narration: str) -> set:
#     """
#     Extracts all candidate reference anchors from raw statement narrations:
#       1. Standard 12-digit UPI / IMPS RRNs: (\b\d{12}\b)
#       2. Bank session & internal transfer codes: (\b[A-Z]\d{7,10}\b), e.g., 'S70501784'
#       3. Core CBS FT / Ref numbers: (\bFT[A-Z0-9]{8,14}\b)
#       4. Standard 6-digit cheque / transfer refs: (\b\d{6}\b) if prefixed with MB/TRF
#     """
#     if not narration:
#         return set()

#     tokens = set()
#     upper = narration.upper()

#     # 1. 12-digit standard RRN / UTR
#     for m in re.finditer(r"\b(\d{12})\b", upper):
#         tokens.add(m.group(1))

#     # 2. Bank internal transfer IDs like S70501784 (Letter followed by 7-10 digits)
#     for m in re.finditer(r"\b([A-Z]\d{7,10})\b", upper):
#         tokens.add(m.group(1))

#     # 3. CBS transaction references like FTB..., SIB..., TXN...
#     for m in re.finditer(r"\b(FT[A-Z0-9]{8,14})\b", upper):
#         tokens.add(m.group(1))

#     return tokens


# def parse_txn_date(val) -> Optional[date]:
#     if not val:
#         return None
#     if hasattr(val, "date"):
#         return val.date()
#     if isinstance(val, datetime):
#         return val.date()
#     try:
#         return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
#     except Exception:
#         return None


# def resolve_cross_account_contra_map(row_ids: list, staging_lines: list) -> dict:
#     """
#     Multi-field self-transfer matcher enforcing:
#       - Amount equality
#       - Opposite direction (Debit <-> Credit)
#       - Date window (within 2 days)
#       - Shared reference anchor (12-digit RRN OR internal token like 'S70501784')
#       - Two distinct internal accounts
#     """
#     if not staging_lines:
#         return {}

#     Account = apps.get_model("ledger", "Account")
#     StatementStagingLine = apps.get_model("ledger", "StatementStagingLine")

#     # 1. Map all internal accounts (Accounts 1-7)
#     accounts_map = {}
#     for acc in Account.objects.exclude(id=99):
#         acc_name = getattr(acc, "name", None) or getattr(acc, "bank_name", "Bank")
#         acc_num = str(getattr(acc, "account_number", "") or "")
#         last4 = acc_num[-4:] if len(acc_num) >= 4 else str(acc.id)
#         accounts_map[acc.id] = {
#             "name": acc_name,
#             "last4": last4,
#         }

#     # 2. Scan active batch and collect candidate reference anchors & amounts
#     active_tokens = set()
#     active_amounts = set()
#     active_dates = set()

#     for stg in staging_lines:
#         narr = getattr(stg, "raw_narration", "") or ""
#         tokens = extract_candidate_ref_tokens(narr)
#         if getattr(stg, "live_upi_rrn", None):
#             tokens.add(str(stg.live_upi_rrn).strip())
#         if getattr(stg, "cheque_ref_number", None):
#             tokens.add(str(stg.cheque_ref_number).strip())

#         amt = float(
#             getattr(stg, "amount", 0)
#             or getattr(stg, "debit", 0)
#             or getattr(stg, "credit", 0)
#             or 0.0
#         )
#         dt = parse_txn_date(getattr(stg, "raw_statement_date", None))

#         active_tokens.update(tokens)
#         if amt > 0:
#             active_amounts.add(amt)
#         if dt:
#             active_dates.add(dt)

#     if not active_amounts:
#         return {}

#     # 3. Fetch candidate matching counterpart lines from database across all internal accounts
#     counterpart_lines = list(
#         StatementStagingLine.objects.filter(
#             account_id__in=accounts_map.keys(),
#             amount__in=active_amounts,
#         ).values(
#             "id",
#             "row_identifier",
#             "account_id",
#             "raw_narration",
#             "amount",
#             "debit",
#             "credit",
#             "raw_statement_date",
#             "cheque_ref_number",
#             "live_upi_rrn",
#         )
#     )

#     # 4. Group lines strictly by: amount
#     amount_groups = defaultdict(list)
#     for line in counterpart_lines:
#         narr = line.get("raw_narration") or ""
#         line_tokens = extract_candidate_ref_tokens(narr)
#         if line.get("live_upi_rrn"):
#             line_tokens.add(str(line["live_upi_rrn"]).strip())
#         if line.get("cheque_ref_number"):
#             line_tokens.add(str(line["cheque_ref_number"]).strip())

#         line["tokens"] = line_tokens
#         line["parsed_date"] = parse_txn_date(line.get("raw_statement_date"))
#         amt = float(
#             line.get("amount") or line.get("debit") or line.get("credit") or 0.0
#         )
#         line["num_amt"] = amt

#         amount_groups[amt].append(line)

#     # 5. Pair rows using Multi-Field Rules:
#     #    (Amount Match) + (Dr <-> Cr Inversion) + (Shared Token) + (Date Diff <= 2) + (Diff Account)
#     contra_map = {}
#     paired_row_ids = set()

#     for amt, group in amount_groups.items():
#         if len(group) < 2:
#             continue

#         debit_candidates = [
#             l
#             for l in group
#             if float(l.get("debit") or 0) > 0
#             and l["row_identifier"] not in paired_row_ids
#         ]
#         credit_candidates = [
#             l
#             for l in group
#             if float(l.get("credit") or 0) > 0
#             and l["row_identifier"] not in paired_row_ids
#         ]

#         for deb in debit_candidates:
#             if deb["row_identifier"] in paired_row_ids:
#                 continue

#             for cred in credit_candidates:
#                 if cred["row_identifier"] in paired_row_ids:
#                     continue

#                 # Condition 1: Must be two different internal bank accounts
#                 if deb["account_id"] == cred["account_id"]:
#                     continue

#                 # Condition 2: Date window must be within 2 days
#                 if deb["parsed_date"] and cred["parsed_date"]:
#                     date_diff = abs((deb["parsed_date"] - cred["parsed_date"]).days)
#                     if date_diff > 2:
#                         continue

#                 # Condition 3: Must share at least one reference token (e.g., 'S70501784' or '429016755275')
#                 shared_tokens = deb["tokens"].intersection(cred["tokens"])

#                 # Fallback: If both narrations contain 'BAIJU' / 'OWN' / 'SELF' and date + amount match
#                 name_match = (
#                     "BAIJU" in (deb.get("raw_narration") or "").upper()
#                     or "SELF" in (deb.get("raw_narration") or "").upper()
#                 ) and (
#                     "BAIJU" in (cred.get("raw_narration") or "").upper()
#                     or "SELF" in (cred.get("raw_narration") or "").upper()
#                 )

#                 if shared_tokens or name_match:
#                     ref_anchor = (
#                         next(iter(shared_tokens)) if shared_tokens else "SELF_TRANSFER"
#                     )

#                     src = accounts_map.get(
#                         deb["account_id"], {"name": "Account", "last4": "XXXX"}
#                     )
#                     dst = accounts_map.get(
#                         cred["account_id"], {"name": "Account", "last4": "XXXX"}
#                     )

#                     badge_text = f"{src['name']} (..{src['last4']}) ➔ {dst['name']} (..{dst['last4']})"

#                     meta_outflow = {
#                         "is_self_transfer": True,
#                         "contra_type": "INTERNAL_TRANSFER",
#                         "ref_id": ref_anchor,
#                         "direction_leg": "OUTFLOW",
#                         "from_account_name": src["name"],
#                         "from_account_last4": src["last4"],
#                         "to_account_name": dst["name"],
#                         "to_account_last4": dst["last4"],
#                         "display_badge": badge_text,
#                     }
#                     meta_inflow = {
#                         "is_self_transfer": True,
#                         "contra_type": "INTERNAL_TRANSFER",
#                         "ref_id": ref_anchor,
#                         "direction_leg": "INFLOW",
#                         "from_account_name": src["name"],
#                         "from_account_last4": src["last4"],
#                         "to_account_name": dst["name"],
#                         "to_account_last4": dst["last4"],
#                         "display_badge": badge_text,
#                     }

#                     if deb.get("row_identifier"):
#                         contra_map[deb["row_identifier"]] = meta_outflow
#                         paired_row_ids.add(deb["row_identifier"])

#                     if cred.get("row_identifier"):
#                         contra_map[cred["row_identifier"]] = meta_inflow
#                         paired_row_ids.add(cred["row_identifier"])

#                     break  # Matched this debit leg; proceed to next

#     return contra_map


# # -------------------------------------------------------------------
# # 🧩 ROUTINE A: STRICT NODE 99 SUSPENSE WORKBENCH
# # -------------------------------------------------------------------
# def get_suspense_workbench_clusters(
#     account_id=None,
#     search_query=None,
#     include_cleared=False,
#     include_items=False,
# ):
#     """
#     Dedicated high-speed triage engine strictly for Account 99 (Suspense).
#     Pulls pending/unclassified statement entries awaiting first-time classification.
#     """
#     JournalEntry = apps.get_model("ledger", "JournalEntry")

#     query = JournalEntry.objects.filter(account_id=99)
#     if not include_cleared:
#         query = query.filter(is_reclassified=False)

#     if account_id and str(account_id) != "99":
#         bank_row_ids = JournalEntry.objects.filter(account_id=account_id).values_list(
#             "row_identifier", flat=True
#         )
#         query = query.filter(row_identifier__in=bank_row_ids)

#     entries = list(
#         query.only(
#             "id", "row_identifier", "debit", "credit", "remarks", "transaction_date"
#         ).order_by("-transaction_date")
#     )
#     print(f"[engine:Suspense] Total Node 99 entries fetched: {len(entries)}")

#     return _build_clusters_from_entries(
#         entries=entries,
#         target_subcategory="Suspense Account",
#         search_query=search_query,
#         include_items=include_items,
#     )


# def _build_clusters_from_entries(
#     entries, target_subcategory, search_query=None, include_items=False
# ):
#     StatementStagingLine = apps.get_model("ledger", "StatementStagingLine")

#     row_ids = [e.row_identifier for e in entries if e.row_identifier]

#     staging_lines = list(
#         StatementStagingLine.objects.filter(row_identifier__in=row_ids)
#     )
#     staging_map = {s.row_identifier: s for s in staging_lines if s.row_identifier}

#     contra_map = resolve_cross_account_contra_map(row_ids, staging_lines)

#     clusters_map = {}

#     for entry in entries:
#         remarks = entry.remarks if isinstance(entry.remarks, dict) else {}
#         stg_line = staging_map.get(entry.row_identifier)
#         contra_info = contra_map.get(
#             entry.row_identifier,
#             {"is_self_transfer": False, "contra_type": "ONE_WAY_EXTERNAL"},
#         )

#         if stg_line:
#             parsed_meta = stg_line.parsed_narration
#             raw_payee = parsed_meta.get("suggested_payee") or stg_line.display_payee
#             payee = UniversalNarrationExtractor.repair_kerning_and_splits(raw_payee)
#             ref_no = parsed_meta.get("detected_reference")
#             rail = parsed_meta.get("detected_rail", "BANK")
#             remark = parsed_meta.get("suggested_remark")
#             raw_statement_text = getattr(stg_line, "raw_narration", None) or getattr(
#                 stg_line, "narration", ""
#             )
#         else:
#             fallback_text = (
#                 remarks.get("universal_narration")
#                 or remarks.get("narration")
#                 or remarks.get("display_text")
#                 or ""
#             )
#             parsed_meta = UniversalNarrationExtractor.decompose_raw_narration(
#                 fallback_text
#             )
#             raw_payee = (
#                 remarks.get("payee") or parsed_meta.get("raw_payee") or fallback_text
#             )
#             payee = UniversalNarrationExtractor.repair_kerning_and_splits(raw_payee)
#             ref_no = remarks.get("upi_ref") or parsed_meta.get("reference")
#             rail = parsed_meta.get("rail", "BANK")
#             remark = parsed_meta.get("raw_remark")
#             raw_statement_text = fallback_text

#         debit_val = float(entry.debit or 0)
#         credit_val = float(entry.credit or 0)

#         if credit_val > 0 and debit_val == 0:
#             is_outflow = False
#             amount = credit_val
#         elif debit_val > 0 and credit_val == 0:
#             is_outflow = True
#             amount = debit_val
#         else:
#             amount = debit_val if debit_val > 0 else credit_val
#             is_outflow = debit_val > 0

#         if contra_info.get("is_self_transfer"):
#             src_name = contra_info.get("from_account_name", "Bank")
#             dst_name = contra_info.get("to_account_name", "Bank")
#             payee = f"Transfer: {src_name} ➔ {dst_name}"
#             pattern = "#SELF_TRANSFER"
#         else:
#             pattern = generate_canonical_cluster_tag(payee)

#         if pattern not in clusters_map:
#             clusters_map[pattern] = {
#                 "pattern": pattern,
#                 "display_name": (
#                     "Self Transfers" if pattern == "#SELF_TRANSFER" else payee
#                 ),
#                 "count": 0,
#                 "total_amount": 0.0,
#                 "total_inflow": 0.0,
#                 "total_outflow": 0.0,
#                 "sample_descriptions": [],
#                 "items": [],
#                 "transaction_ids": [],
#                 "is_contra_group": (pattern == "#SELF_TRANSFER"),
#             }

#         readable_narrative = build_human_readable_narrative(
#             rail=rail,
#             direction="OUTFLOW" if is_outflow else "INFLOW",
#             amount=amount,
#             payee=payee,
#             ref_no=ref_no,
#             branch_or_remark=remark,
#         )

#         cluster = clusters_map[pattern]
#         cluster["count"] += 1
#         cluster["total_amount"] += amount

#         if is_outflow:
#             cluster["total_outflow"] += amount
#         else:
#             cluster["total_inflow"] += amount

#         cluster["transaction_ids"].append(str(entry.id))

#         if (
#             len(cluster["sample_descriptions"]) < 2
#             and readable_narrative not in cluster["sample_descriptions"]
#         ):
#             cluster["sample_descriptions"].append(readable_narrative)

#         if include_items:
#             cluster["items"].append(
#                 {
#                     "id": str(entry.id),
#                     "narration": raw_statement_text,
#                     "raw_narration": raw_statement_text,
#                     "display_payee": payee,
#                     "universal_narration": readable_narrative,
#                     "debit": debit_val,
#                     "credit": credit_val,
#                     "amount": amount,
#                     "direction": "OUTFLOW" if is_outflow else "INFLOW",
#                     "transaction_date": str(entry.transaction_date),
#                     "remarks": {
#                         **remarks,
#                         "payee": payee,
#                         "upi_ref": ref_no,
#                         "universal_narration": readable_narrative,
#                         "raw_narration": raw_statement_text,
#                         "display_text": readable_narrative,
#                         "target_account_name": target_subcategory,
#                     },
#                     "contra_meta": contra_info,
#                 }
#             )

#     sorted_clusters = sorted(
#         clusters_map.values(), key=lambda c: c["count"], reverse=True
#     )

#     if search_query and str(search_query).strip():
#         norm_query = search_query.strip().upper()
#         return [
#             c
#             for c in sorted_clusters
#             if norm_query in c["pattern"].upper()
#             or any(norm_query in s.upper() for s in c.get("sample_descriptions", []))
#         ]

#     print(f"[engine] Total distinct clusters generated: {len(sorted_clusters)}")
#     return sorted_clusters


# def get_dynamic_bank_account_ids():
#     Account = apps.get_model("ledger", "Account")
#     return list(
#         Account.objects.filter(
#             Q(bank__isnull=False)
#             | (~Q(account_number="") & Q(account_number__isnull=False))
#             | (~Q(ifsc_code="") & Q(ifsc_code__isnull=False))
#         ).values_list("id", flat=True)
#     )


# # -------------------------------------------------------------------
# # 🧩 ROUTINE B: CLASSIFIED GL HEAD & SUBLEDGER WORKBENCH
# # -------------------------------------------------------------------
# def get_gl_head_workbench_clusters(
#     target_subcategory: str,
#     search_query=None,
#     include_items=False,
# ):
#     """
#     Audit & Re-drill engine for legitimate GL Account Heads (e.g., 'Real Estate').
#     Fetches all debit transaction legs classified under this head or bound to its assets.
#     """
#     JournalEntry = apps.get_model("ledger", "JournalEntry")
#     AssetSubLedger = apps.get_model("ledger", "AssetSubLedger")
#     AssetTransactionMapping = apps.get_model("ledger", "AssetTransactionMapping")

#     sub_clean = target_subcategory.strip()

#     # 1. Fetch asset IDs for this category
#     related_asset_ids = AssetSubLedger.objects.filter(
#         Q(category__icontains=sub_clean)
#         | Q(category__iexact=sub_clean)
#         | Q(asset_category__name__icontains=sub_clean)
#         | Q(asset_category__name__iexact=sub_clean)
#         | Q(asset_category__default_taxonomy_subcategory__icontains=sub_clean)
#         | Q(asset_category__default_taxonomy_subcategory__iexact=sub_clean)
#     ).values_list("id", flat=True)

#     # 2. Get all row identifiers bound to these assets
#     bound_row_ids = list(
#         AssetTransactionMapping.objects.filter(
#             asset_id__in=related_asset_ids
#         ).values_list("row_identifier", flat=True)
#     )

#     # 3. Construct unified filter across snapshots, remarks, and folio mappings
#     gl_filter = (
#         Q(evaluation_matrix_snapshot__resolved_subcategory__iexact=sub_clean)
#         | Q(remarks__target_account_name__iexact=sub_clean)
#         | Q(remarks__subcategory__iexact=sub_clean)
#     )

#     if bound_row_ids:
#         gl_filter |= Q(row_identifier__in=bound_row_ids)

#     # 4. Filter strictly on DEBIT legs (money applied towards Real Estate)
#     query = (
#         JournalEntry.objects.filter(gl_filter, debit__gt=0)
#         .only("id", "row_identifier", "debit", "credit", "remarks", "transaction_date")
#         .order_by("-transaction_date")
#     )

#     all_entries = list(query)

#     # Deduplicate by row_identifier so each transaction has exactly 1 debit leg
#     seen_row_ids = set()
#     entries = []
#     for e in all_entries:
#         rid = e.row_identifier or str(e.id)
#         if rid in seen_row_ids:
#             continue
#         seen_row_ids.add(rid)
#         entries.append(e)

#     print(
#         f"[engine:GL-Head '{sub_clean}'] Clean unique debit entries fetched: {len(entries)}"
#     )

#     return _build_clusters_from_entries(
#         entries=entries,
#         target_subcategory=sub_clean,
#         search_query=search_query,
#         include_items=include_items,
#     )


# # -------------------------------------------------------------------
# # 🧩 2. MAIN DISPATCHER ROUTER
# # -------------------------------------------------------------------
# def get_suspense_clusters(
#     target_subcategory="Suspense Account",
#     account_id=None,
#     search_query=None,
#     include_cleared=False,
#     include_items=False,
# ):
#     print("\n" + "=" * 80)
#     print(
#         f"[engine] ROUTING get_suspense_clusters(sub='{target_subcategory}',"
#         f" account_id={account_id}, query='{search_query}', include_cleared={include_cleared})"
#     )
#     print("=" * 80)

#     # If clicked on Suspense Account or default workbench -> Routine A
#     if not target_subcategory or target_subcategory.strip() in [
#         "Suspense Account",
#         "All",
#     ]:
#         return get_suspense_workbench_clusters(
#             account_id=account_id,
#             search_query=search_query,
#             include_cleared=include_cleared,
#             include_items=include_items,
#         )

#     # If clicked on a specific GL head (Real Estate, Fixed Deposits, etc.) -> Routine B
#     return get_gl_head_workbench_clusters(
#         target_subcategory=target_subcategory,
#         search_query=search_query,
#         include_items=include_items,
#     )


# # -------------------------------------------------------------------
# # 🧩 3. ACCORDION EXPANSION LINE ITEMS FETCHER (UPDATED)
# # -------------------------------------------------------------------
# def fetch_cluster_line_items(entry_ids: list) -> list:
#     if not entry_ids:
#         return []

#     JournalEntry = apps.get_model("ledger", "JournalEntry")
#     StatementStagingLine = apps.get_model("ledger", "StatementStagingLine")
#     Account = apps.get_model("ledger", "Account")

#     AssetTransactionMapping = None
#     for model in apps.get_models():
#         if model.__name__ == "AssetTransactionMapping":
#             AssetTransactionMapping = model
#             break

#     # 1. Fetch journal entries
#     entries = list(
#         JournalEntry.objects.filter(id__in=entry_ids)
#         .only(
#             "id",
#             "row_identifier",
#             "account_id",
#             "debit",
#             "credit",
#             "remarks",
#             "transaction_date",
#         )
#         .order_by("-transaction_date")
#     )

#     row_ids = [e.row_identifier for e in entries if e.row_identifier]

#     # 2. Query Asset mappings by row_identifier
#     mapping_map = {}
#     if row_ids and AssetTransactionMapping:
#         mappings = AssetTransactionMapping.objects.filter(
#             row_identifier__in=row_ids
#         ).select_related("asset")
#         for m in mappings:
#             asset = getattr(m, "asset", None)
#             mapping_map[m.row_identifier] = {
#                 "is_mapped": True,
#                 "mapping_id": str(m.id),
#                 "asset_id": str(asset.id) if asset else None,
#                 "asset_code": getattr(asset, "asset_code", "FLT"),
#                 "asset_name": getattr(asset, "name", "Petty Cash Float"),
#             }

#     # 3. Fetch staging lines as model instances
#     staging_lines = list(
#         StatementStagingLine.objects.filter(row_identifier__in=row_ids)
#     )
#     staging_map = {s.row_identifier: s for s in staging_lines if s.row_identifier}

#     # 🔗 DETECT CONTRA TRANSFERS
#     contra_map = resolve_cross_account_contra_map(row_ids, staging_lines)

#     # 4. Fetch pairing bank account legs
#     pairing_legs = list(
#         JournalEntry.objects.filter(row_identifier__in=row_ids)
#         .exclude(account_id=99)
#         .values("id", "row_identifier", "account_id", "debit", "credit", "remarks")
#     )

#     row_to_bank_leg = {}
#     bank_acc_ids = set()
#     for p in pairing_legs:
#         acc_id = p["account_id"]
#         if acc_id:
#             bank_acc_ids.add(int(acc_id))
#             if p["row_identifier"] not in row_to_bank_leg:
#                 row_to_bank_leg[p["row_identifier"]] = p

#     # 5. Account metadata lookup
#     account_lookup = {}
#     if bank_acc_ids:
#         for acc in Account.objects.filter(id__in=bank_acc_ids):
#             acc_name = getattr(acc, "name", None) or getattr(acc, "bank_name", "Bank")
#             acc_num = str(getattr(acc, "account_number", "") or "")
#             last4 = acc_num[-4:] if len(acc_num) >= 4 else acc_num
#             account_lookup[acc.id] = {
#                 "bank_name": acc_name,
#                 "bank_last4": last4,
#             }

#     items = []
#     for entry in entries:
#         remarks = entry.remarks if isinstance(entry.remarks, dict) else {}
#         stg = staging_map.get(entry.row_identifier)
#         bank_leg = row_to_bank_leg.get(entry.row_identifier) or {}
#         mapping_info = mapping_map.get(entry.row_identifier) or {}
#         contra_info = contra_map.get(
#             entry.row_identifier,
#             {"is_self_transfer": False, "contra_type": "ONE_WAY_EXTERNAL"},
#         )

#         raw_txn_date = (
#             getattr(stg, "raw_statement_date", None)
#             or remarks.get("raw_statement_date")
#             or remarks.get("transaction_date")
#             or entry.transaction_date
#         )

#         if stg:
#             raw_narration = getattr(stg, "raw_narration", None) or getattr(
#                 stg, "narration", ""
#             )
#             parsed = stg.parsed_narration
#             raw_payee = (
#                 parsed.get("suggested_payee") or parsed.get("statement_payee_raw") or ""
#             )
#             clean_payee = UniversalNarrationExtractor.repair_kerning_and_splits(
#                 raw_payee
#             )
#             ref_no = parsed.get("detected_reference")
#             rail = parsed.get("detected_rail", "BANK")
#             remark = parsed.get("suggested_remark")
#         else:
#             raw_narration = (
#                 remarks.get("universal_narration") or remarks.get("narration") or ""
#             )
#             parsed = UniversalNarrationExtractor.decompose_raw_narration(raw_narration)
#             clean_payee = UniversalNarrationExtractor.repair_kerning_and_splits(
#                 parsed.get("raw_payee") or remarks.get("payee") or ""
#             )
#             ref_no = parsed.get("reference") or remarks.get("upi_ref")
#             rail = parsed.get("rail", "BANK")
#             remark = parsed.get("raw_remark")

#         debit_val = float(entry.debit or 0)
#         credit_val = float(entry.credit or 0)
#         is_outflow = debit_val > 0
#         amount = debit_val if is_outflow else credit_val

#         readable_narrative = build_human_readable_narrative(
#             rail=rail,
#             direction="OUTFLOW" if is_outflow else "INFLOW",
#             amount=amount,
#             payee=clean_payee,
#             ref_no=ref_no,
#             branch_or_remark=remark,
#         )

#         resolved_acc_id = bank_leg.get("account_id")
#         if not resolved_acc_id:
#             stg_acc_id = getattr(stg, "account_id", None)
#             if stg_acc_id and int(stg_acc_id) != 99:
#                 resolved_acc_id = int(stg_acc_id)
#             elif entry.account_id and int(entry.account_id) != 99:
#                 resolved_acc_id = int(entry.account_id)

#         bank_meta = account_lookup.get(int(resolved_acc_id)) if resolved_acc_id else {}

#         items.append(
#             {
#                 "id": str(entry.id),
#                 "row_identifier": entry.row_identifier,
#                 "narration": readable_narrative,
#                 "raw_narration": raw_narration,
#                 "display_payee": clean_payee,
#                 "universal_narration": readable_narrative,
#                 "display_text": readable_narrative,
#                 "debit": debit_val,
#                 "credit": credit_val,
#                 "amount": amount,
#                 "direction": "OUTFLOW" if is_outflow else "INFLOW",
#                 "transaction_date": (
#                     raw_txn_date.strftime("%Y-%m-%d")
#                     if hasattr(raw_txn_date, "strftime")
#                     else str(raw_txn_date)
#                 ),
#                 "account_id": resolved_acc_id,
#                 "bank_name": bank_meta.get("bank_name"),
#                 "bank_last4": bank_meta.get("bank_last4"),
#                 "is_mapped": bool(mapping_info.get("is_mapped")),
#                 "mapping_id": mapping_info.get("mapping_id"),
#                 "asset_id": mapping_info.get("asset_id"),
#                 "asset_code": mapping_info.get("asset_code"),
#                 "asset_name": mapping_info.get("asset_name"),
#                 "contra_meta": contra_info,  # 🎯 Populated on line item
#                 "remarks": {
#                     **remarks,
#                     "payee": clean_payee,
#                     "universal_narration": readable_narrative,
#                     "raw_narration": raw_narration,
#                 },
#             }
#         )

#     return items


# def get_clean_patterns(rule) -> list[str]:
#     """Retrieves clean pattern list directly from model or dict representation."""
#     if hasattr(rule, "get_patterns") and callable(rule.get_patterns):
#         return rule.get_patterns()

#     patterns = (
#         rule.get("patterns", [])
#         if isinstance(rule, dict)
#         else getattr(rule, "patterns", [])
#     )

#     if isinstance(patterns, list):
#         return [str(p).strip() for p in patterns if p and str(p).strip()]

#     if isinstance(patterns, str):
#         try:
#             parsed = json.loads(patterns)
#             if isinstance(parsed, list):
#                 return [str(p).strip() for p in parsed if p and str(p).strip()]
#         except json.JSONDecodeError:
#             return [patterns.strip()]

#     return []


# def classify_via_rules(
#     raw_narration: str, is_debit: bool = True
# ) -> Optional[Dict[str, str]]:
#     """
#     Evaluates raw narration text against active ClassificationRule patterns
#     using model pattern retrieval and strict multi-token matching.
#     """
#     if not raw_narration or not str(raw_narration).strip():
#         return None

#     target_rule_type = "Debit" if is_debit else "Credit"

#     active_rules = ClassificationRule.objects.filter(
#         is_active=True, rule_type=target_rule_type
#     ).order_by("-priority")

#     for rule in active_rules:
#         patterns_list = (
#             rule.get_patterns()
#             if hasattr(rule, "get_patterns")
#             else get_clean_patterns(rule)
#         )

#         for pattern in patterns_list:
#             if match_multi_tokens(raw_narration, pattern):
#                 rule.match_count = (rule.match_count or 0) + 1
#                 rule.save(update_fields=["match_count", "updated_at"])

#                 return {
#                     "category": rule.target_category,
#                     "subcategory": rule.target_subcategory,
#                     "matched_pattern": pattern,
#                     "rule_code": rule.rule_code,
#                     "rule_type": rule.rule_type,
#                 }
#     return None


# def generate_strict_multitoken_pattern(narration_list: list[str]) -> list[str]:
#     """
#     Extracts tokens present in the majority (>= 80%) of selected narrations,
#     filtering out noise words and preserving natural word order.
#     """
#     if not narration_list:
#         return []

#     token_sequences = [extract_meaningful_tokens(n) for n in narration_list if n]
#     if not token_sequences:
#         return []

#     token_counts = Counter()
#     for seq in token_sequences:
#         for token in set(seq):
#             if token not in NOISE_KEYWORD_BLACKLIST:
#                 token_counts[token] += 1

#     total_rows = len(token_sequences)
#     threshold = max(1, int(total_rows * 0.8))

#     majority_tokens_set = {
#         token for token, count in token_counts.items() if count >= threshold
#     }

#     ordered_tokens = []
#     first_sample_tokens = token_sequences[0]

#     for token in first_sample_tokens:
#         if token in majority_tokens_set and token not in ordered_tokens:
#             ordered_tokens.append(token)

#     for token in majority_tokens_set:
#         if token not in ordered_tokens:
#             ordered_tokens.append(token)

#     return ordered_tokens


# def add_or_update_classification_rule(
#     category: str,
#     subcategory: str,
#     new_pattern: str,
#     entry_type: str = "Debit",
# ) -> bool:
#     """Appends an explicit pattern into an existing ClassificationRule or creates a new active rule.

#     Protects canonical merchant brands from being pruned, eliminates redundant
#     compound phrases when a universal anchor exists, and maintains clean pattern arrays.
#     """
#     if not new_pattern or not str(new_pattern).strip():
#         return False

#     # 1. Clean explicit user selection as an ATOMIC unit (NO word splitting)
#     clean_pattern = sanitize_user_pattern(new_pattern)
#     if not clean_pattern:
#         return False

#     clean_pattern = clean_pattern.upper().strip()

#     # 2. Single token safety validation (only applies if pattern is a single word)
#     if " " not in clean_pattern:
#         if (
#             clean_pattern in NOISE_KEYWORD_BLACKLIST
#             or clean_pattern in RULE_SAFETY_BLACKLIST
#             or is_ref_hash_or_noise(clean_pattern)
#         ):
#             print(
#                 f"⚠️ Rejected unsafe single-token pattern from blacklist: '{clean_pattern}'"
#             )
#             return False

#         if len(clean_pattern) < 4:
#             if clean_pattern in OK_WORD_LIST:
#                 print(f"✅ Approved short whitelist pattern: '{clean_pattern}'")
#             else:
#                 print(
#                     f"⚠️ Rejected short single-token pattern (<4 chars): '{clean_pattern}'"
#                 )
#                 return False

#     clean_entry_type = (
#         "Credit" if str(entry_type).strip().lower() == "credit" else "Debit"
#     )

#     taxonomy_node = TaxonomyTree.objects.filter(
#         category__iexact=category, subcategory__iexact=subcategory
#     ).first()
#     resolved_taxonomy = taxonomy_node if taxonomy_node else None

#     existing_rule = ClassificationRule.objects.filter(
#         target_category=category,
#         target_subcategory=subcategory,
#         rule_type=clean_entry_type,
#         is_active=True,
#     ).first()

#     if existing_rule:
#         patterns = {p.upper().strip() for p in get_clean_patterns(existing_rule) if p}
#         updated_fields = ["patterns", "match_count", "updated_at"]

#         if clean_pattern not in patterns:
#             # -------------------------------------------------------------
#             # 🟢 SAFE PRUNING LOGIC:
#             # 1. Guard Canonical Brands: NEVER prune single-word merchant anchors.
#             # -------------------------------------------------------------
#             all_compound_words = set()
#             for p in patterns:
#                 if " " in p:
#                     all_compound_words.update(p.split())
#             if " " in clean_pattern:
#                 all_compound_words.update(clean_pattern.split())

#             # Only prune loose tokens if they are NOT in KNOWN_MERCHANTS or OK_WORD_LIST
#             pruned_tokens = {
#                 p
#                 for p in patterns
#                 if " " not in p
#                 and p in all_compound_words
#                 and p not in KNOWN_MERCHANTS
#                 and p not in OK_WORD_LIST
#             }

#             if pruned_tokens:
#                 patterns = patterns - pruned_tokens
#                 print(
#                     f"🧹 Pruned loose sub-tokens {pruned_tokens} from rule {existing_rule.rule_code} in favor of compound phrases"
#                 )

#             # -------------------------------------------------------------
#             # 2. Reverse Pruning: If a universal brand anchor is added
#             # (e.g. 'SWIGGY' or 'ZOMATO'), prune noisy compound phrases that
#             # contain it (e.g. 'WDL SWIGGY', 'HDFC ZOMATO').
#             # -------------------------------------------------------------
#             active_brand_anchors = {
#                 p
#                 for p in patterns | {clean_pattern}
#                 if " " not in p and p in KNOWN_MERCHANTS
#             }

#             redundant_compounds = {
#                 p
#                 for p in patterns
#                 if " " in p
#                 and any(brand in p.split() for brand in active_brand_anchors)
#             }

#             if redundant_compounds:
#                 patterns = patterns - redundant_compounds
#                 print(
#                     f"✨ Pruned redundant compound phrases {redundant_compounds} covered by standalone brand anchors"
#                 )

#             patterns.add(clean_pattern)

#             # Sort array compound-first, then alphabetically
#             sorted_patterns = sorted(
#                 list(patterns), key=lambda x: (-len(x.split()), -len(x), x)
#             )

#             existing_rule.patterns = sorted_patterns
#             existing_rule.match_count = (existing_rule.match_count or 0) + 1

#             if not existing_rule.taxonomy and resolved_taxonomy:
#                 existing_rule.taxonomy = resolved_taxonomy
#                 updated_fields.append("taxonomy")

#             existing_rule.save(update_fields=updated_fields)
#             print(
#                 f"✅ Appended clean pattern '{clean_pattern}' to existing rule {existing_rule.rule_code}"
#             )
#             return True
#         return False

#     else:
#         vector_prefix = "DE" if clean_entry_type == "Debit" else "CR"
#         hash_input = f"{subcategory}_{clean_pattern}_{clean_entry_type}".upper()
#         short_code = hashlib.md5(hash_input.encode()).hexdigest()[:6].upper()
#         rule_code = f"CR_{vector_prefix}_{short_code}"

#         ClassificationRule.objects.create(
#             name=f"Learned ({clean_entry_type}): {subcategory} ({clean_pattern})",
#             rule_code=rule_code,
#             rule_type=clean_entry_type,
#             target_category=category,
#             target_subcategory=subcategory,
#             patterns=[clean_pattern],
#             priority=1,
#             is_active=True,
#             created_from_manual_override=True,
#             match_count=1,
#             taxonomy=resolved_taxonomy,
#         )
#         print(
#             f"✅ Created new distinct rule {rule_code} with clean pattern '{clean_pattern}'"
#         )
#         return True


# def reclassify_and_learn(
#     transaction_ids: List[str],
#     target_category: str,
#     target_subcategory: str,
#     patterns: Optional[List[str]] = None,
#     save_rule: bool = True,
# ) -> Dict[str, Any]:
#     """
#     Executes bulk reclassification for Node 99 records and learns clean,
#     multi-crore-safe matching rules without token pollution.
#     """
#     if not transaction_ids:
#         return {"status": "success", "reclassified_count": 0, "rules_updated": False}

#     entries = list(JournalEntry.objects.filter(account_id=99, id__in=transaction_ids))
#     if not entries:
#         entries = list(
#             JournalEntry.objects.filter(
#                 account_id=99, row_identifier__in=transaction_ids
#             )
#         )

#     if not entries:
#         return {"status": "success", "reclassified_count": 0, "rules_updated": False}

#     total_debit = sum(float(e.debit or 0) for e in entries)
#     total_credit = sum(float(e.credit or 0) for e in entries)
#     inferred_entry_type = "Credit" if total_credit > total_debit else "Debit"

#     payee_groups = {}

#     for entry in entries:
#         snapshot = entry.evaluation_matrix_snapshot or {}
#         snapshot["previous_category"] = snapshot.get("resolved_category")
#         snapshot["previous_subcategory"] = snapshot.get("resolved_subcategory")
#         snapshot["resolved_category"] = target_category
#         snapshot["resolved_subcategory"] = target_subcategory
#         snapshot["is_manual_override"] = True

#         entry.evaluation_matrix_snapshot = snapshot
#         entry.classification_status = "RECLASSIFIED"
#         entry.is_reclassified = True

#         remarks_dict = entry.remarks if isinstance(entry.remarks, dict) else {}
#         narration_text = remarks_dict.get("narration") or str(entry.remarks or "")

#         direction_word = remarks_dict.get("directional_prefix", "By")
#         payee = remarks_dict.get("payee") or ""
#         upi_ref = remarks_dict.get("upi_ref") or ""
#         user_note = remarks_dict.get("user_note") or ""

#         clean_payee = extract_clean_payee_pattern(payee or narration_text) or "GENERIC"
#         if clean_payee not in payee_groups:
#             payee_groups[clean_payee] = []
#         if narration_text:
#             payee_groups[clean_payee].append(narration_text)

#         amt = float(entry.debit or entry.credit or 0)
#         ref_str = f" [Ref: {upi_ref}]" if upi_ref else ""
#         action_word = f"Paid ₹{amt:,.2f} to {payee}" if payee else f"Amount ₹{amt:,.2f}"
#         note_str = f" | Note: {user_note.strip()}" if user_note else ""

#         updated_display_text = (
#             f"{direction_word} {target_subcategory} |"
#             f" {action_word}{ref_str}{note_str} | Reclassified via Workbench"
#         )

#         entry.remarks = {
#             **remarks_dict,
#             "target_account_name": target_subcategory,
#             "display_text": updated_display_text,
#             "updated_at": timezone.now().isoformat(),
#         }

#     JournalEntry.objects.bulk_update(
#         entries,
#         [
#             "evaluation_matrix_snapshot",
#             "classification_status",
#             "is_reclassified",
#             "remarks",
#         ],
#     )

#     rules_updated = False
#     learned_patterns = []

#     if save_rule:
#         print("\n" + "_" * 40)
#         print(f"[ENGINE DEBUG] Learning Rules for Subcategory: '{target_subcategory}'")

#         if patterns and isinstance(patterns, list) and len(patterns) > 0:
#             print(f"[ENGINE DEBUG] Using Explicit User Patterns ONLY: {patterns}")
#             for user_p in patterns:
#                 clean_user_p = sanitize_user_pattern(user_p)
#                 if not clean_user_p:
#                     continue

#                 is_compound = " " in clean_user_p
#                 if len(clean_user_p) >= 3 and (
#                     is_compound or clean_user_p not in RULE_SAFETY_BLACKLIST
#                 ):
#                     updated = add_or_update_classification_rule(
#                         category=target_category,
#                         subcategory=target_subcategory,
#                         new_pattern=clean_user_p,
#                         entry_type=inferred_entry_type,
#                     )
#                     if updated:
#                         rules_updated = True
#                         learned_patterns.append(clean_user_p)

#         else:
#             print(
#                 f"[ENGINE DEBUG] No explicit patterns passed. Grouped {len(entries)} items into {len(payee_groups)} distinct payee clusters:"
#             )

#             for payee_key, group_narrations in payee_groups.items():
#                 common_tokens = generate_strict_multitoken_pattern(group_narrations)

#                 safe_tokens = [
#                     t
#                     for t in common_tokens
#                     if not is_ref_hash_or_noise(t)
#                     and t.upper() not in NOISE_KEYWORD_BLACKLIST
#                     and t.upper() not in RULE_SAFETY_BLACKLIST
#                     and len(t) > 2
#                 ]

#                 print(
#                     f"    --> Cluster '{payee_key}': Extracted Safe Tokens = {safe_tokens}"
#                 )

#                 if safe_tokens:
#                     capped_tokens = safe_tokens[:2]
#                     compound_pattern = " ".join(capped_tokens)

#                     if len(compound_pattern) >= 3:
#                         updated = add_or_update_classification_rule(
#                             category=target_category,
#                             subcategory=target_subcategory,
#                             new_pattern=compound_pattern,
#                             entry_type=inferred_entry_type,
#                         )
#                         if updated:
#                             rules_updated = True
#                             learned_patterns.append(compound_pattern)

#         print("_" * 40 + "\n")

#     return {
#         "status": "success",
#         "reclassified_count": len(entries),
#         "entry_type_bound": inferred_entry_type,
#         "rules_updated": rules_updated,
#         "patterns_learned": learned_patterns,
#     }


# # region older

# # from datetime import datetime
# # import hashlib
# # import json
# # import re
# # from typing import Any, Dict, List, Optional
# # from collections import Counter

# # from django.db.models import Q
# # from django.utils import timezone

# # from tracker.classification.remarks_service import generate_cluster_pattern
# # from tracker.classification.utils.upiparser import parse_upi_narration
# # from tracker.models import (
# #     AccountingRule,
# #     ClassificationRule,
# #     JournalEntry,
# #     StatementStagingLine,
# #     TaxonomyTree,
# # )
# # from tracker.constants import (
# #     NOISE_KEYWORD_BLACKLIST,
# #     GENERIC_IGNORE_PATTERNS,
# #     GENERIC_PATTERNS,
# #     KNOWN_MERCHANTS,
# #     RULE_SAFETY_BLACKLIST,
# # )

# # GENERIC_NOISE_TOKENS = NOISE_KEYWORD_BLACKLIST


# # def normalize_for_search(text: str) -> str:
# #     """Strips underscores, spaces, dashes, colons, and punctuation for fuzzy matching."""
# #     if not text:
# #         return ""
# #     return re.sub(r"[^A-Z0-9]+", "", str(text).upper())


# # def normalize_condensed(text: str) -> str:
# #     """Strips all non-alphanumeric characters AND spaces for fuzzy boundary evaluation."""
# #     if not text:
# #         return ""
# #     return re.sub(r"[^A-Z0-9]", "", str(text).upper())


# # def sanitize_user_pattern(pattern: str) -> str:
# #     """
# #     Cleans explicit user-selected patterns (e.g. 'APAN DAS', 'MARGIN FREE HYPERMAR')
# #     as ATOMIC phrases without splitting multi-word strings into individual tokens.
# #     """
# #     if not pattern or not str(pattern).strip():
# #         return ""

# #     # 1. Strip special characters (keep alphanumerics and spaces)
# #     clean_str = re.sub(r"[^A-Z0-9\s]", " ", str(pattern).upper())

# #     # 2. Collapse internal whitespace (e.g. "APAN    DAS" -> "APAN DAS")
# #     clean_str = re.sub(r"\s+", " ", clean_str).strip()

# #     if not clean_str:
# #         return ""

# #     # 3. Verify component words against blacklists
# #     words = clean_str.split()
# #     valid_words = [
# #         w
# #         for w in words
# #         if w not in NOISE_KEYWORD_BLACKLIST and w not in RULE_SAFETY_BLACKLIST
# #     ]

# #     # If every word in the pattern was blacklisted noise, reject
# #     if not valid_words:
# #         return ""

# #     # Reconstruct intact multi-word phrase
# #     return " ".join(valid_words)


# # def extract_meaningful_tokens(text: str) -> list[str]:
# #     """
# #     Cleans raw statement narrations and extracts candidate words
# #     for auto-rule generation, filtering out blacklisted noise.
# #     """
# #     if not text:
# #         return []

# #     # 1. Clean special characters and normalize whitespace
# #     clean_str = re.sub(r"[^A-Z0-9\s]", " ", str(text).upper())
# #     clean_str = re.sub(r"\s+", " ", clean_str).strip()

# #     # 2. Split into individual words
# #     raw_tokens = clean_str.split()

# #     filtered_tokens = []
# #     for token in raw_tokens:
# #         # Check against centralized constants
# #         if token in NOISE_KEYWORD_BLACKLIST or token in RULE_SAFETY_BLACKLIST:
# #             continue

# #         # Filter out pure numbers and ultra-long ref hashes
# #         if token.isdigit() or len(token) > 25:
# #             continue

# #         filtered_tokens.append(token)

# #     return filtered_tokens


# # def match_multi_tokens(
# #     narration: str, pattern: str, min_required_tokens: int = 2
# # ) -> bool:
# #     """
# #     Validates if narration matches rule pattern tokens.
# #     Requires at least `min_required_tokens` AND all pattern tokens to be present.
# #     """
# #     if not narration or not pattern:
# #         return False

# #     narration_tokens = set(extract_meaningful_tokens(narration))
# #     pattern_tokens = set(extract_meaningful_tokens(pattern))

# #     if not pattern_tokens:
# #         return False

# #     if len(pattern_tokens) < min_required_tokens:
# #         condensed_narration = normalize_condensed(narration)
# #         condensed_pattern = normalize_condensed(pattern)
# #         return len(condensed_pattern) >= 6 and condensed_pattern in condensed_narration

# #     if pattern_tokens.issubset(narration_tokens):
# #         return True

# #     condensed_narration = normalize_condensed(narration)
# #     condensed_pattern = normalize_condensed(pattern)

# #     return len(condensed_pattern) >= 6 and condensed_pattern in condensed_narration


# # def extract_clean_payee_pattern(narration: str) -> str:
# #     """Extracts true merchant/person payee name, stripping reference noise and slashes."""
# #     if not narration or not str(narration).strip():
# #         return ""

# #     text = str(narration).strip().upper()

# #     # 1. POS bracket extraction e.g. POS TRN/ ID NO. (AZAD GROUP HOTELS TR)
# #     pos_match = re.search(r"\(([^)]+)\)", text)
# #     if pos_match:
# #         candidate = pos_match.group(1).strip()
# #         if len(candidate) >= 3 and not candidate.startswith("CIAL"):
# #             return candidate

# #     tokens = extract_meaningful_tokens(text)
# #     if not tokens:
# #         return text[:30]

# #     for token in tokens:
# #         if token in KNOWN_MERCHANTS:
# #             return token  # 🎯 Returns clean "ZOMATO" or "BLINKIT" immediately!

# #     # 3. Fallback: Take top tokens but ignore trailing person names/noise if merchant/action word present
# #     clean_tokens = tokens[:2] if len(tokens) >= 2 else tokens
# #     return " ".join(clean_tokens)


# # def get_suspense_clusters(
# #     target_subcategory="Suspense Account",
# #     account_id=None,
# #     search_query=None,
# #     include_cleared=False,
# # ):
# #     print("\n" + "=" * 80)
# #     print(
# #         f"[engine] START get_suspense_clusters(sub='{target_subcategory}',"
# #         f" account_id={account_id}, query='{search_query}', include_cleared={include_cleared})"
# #     )
# #     print("=" * 80)

# #     if not include_cleared:
# #         query = JournalEntry.objects.filter(account_id=99, is_reclassified=False)
# #         if target_subcategory and target_subcategory.strip() not in [
# #             "Suspense Account",
# #             "All",
# #         ]:
# #             query = query.filter(
# #                 evaluation_matrix_snapshot__resolved_subcategory=target_subcategory
# #             )
# #     else:
# #         query = JournalEntry.objects.filter(account_id=99)
# #         if target_subcategory and target_subcategory.strip() not in [
# #             "Suspense Account",
# #             "All",
# #         ]:
# #             query = query.filter(
# #                 evaluation_matrix_snapshot__resolved_subcategory=target_subcategory
# #             )

# #     if account_id and str(account_id) != "99":
# #         bank_row_ids = JournalEntry.objects.filter(account_id=account_id).values_list(
# #             "row_identifier", flat=True
# #         )
# #         query = query.filter(row_identifier__in=bank_row_ids)

# #     entries = list(query.order_by("-transaction_date"))
# #     print(f"[engine] Total entries fetched: {len(entries)}")

# #     row_ids = [e.row_identifier for e in entries if e.row_identifier]
# #     staging_map = {
# #         s.row_identifier: s.narration
# #         for s in StatementStagingLine.objects.filter(row_identifier__in=row_ids).only(
# #             "row_identifier", "narration"
# #         )
# #     }

# #     clusters_map = {}

# #     for idx, entry in enumerate(entries, 1):
# #         remarks = entry.remarks if isinstance(entry.remarks, dict) else {}
# #         narration = staging_map.get(entry.row_identifier, "")
# #         stored_pattern = remarks.get("pattern")

# #         debit_val = float(entry.debit or 0)
# #         credit_val = float(entry.credit or 0)

# #         if credit_val > 0 and debit_val == 0:
# #             is_outflow = False
# #             amount = credit_val
# #         elif debit_val > 0 and credit_val == 0:
# #             is_outflow = True
# #             amount = debit_val
# #         else:
# #             amount = debit_val if debit_val > 0 else credit_val
# #             is_outflow = debit_val > 0

# #         parsed_meta = parse_upi_narration(narration) or {}
# #         payee = parsed_meta.get("payee") or remarks.get("payee")
# #         ref_no = parsed_meta.get("upi_ref") or remarks.get("upi_ref")

# #         if not stored_pattern or stored_pattern in GENERIC_PATTERNS:
# #             pattern = generate_cluster_pattern(
# #                 narration=narration, remarks_data={"payee": payee}
# #             )
# #         else:
# #             pattern = stored_pattern

# #         if pattern not in clusters_map:
# #             clusters_map[pattern] = {
# #                 "pattern": pattern,
# #                 "count": 0,
# #                 "total_amount": 0.0,
# #                 "total_inflow": 0.0,
# #                 "total_outflow": 0.0,
# #                 "sample_descriptions": [],
# #                 "items": [],
# #                 "transaction_ids": [],
# #             }

# #         direction_word = "By" if is_outflow else "To"

# #         if is_outflow:
# #             action_word = (
# #                 f"Paid ₹{amount:,.2f} to {payee}"
# #                 if payee
# #                 else f"Outflow of ₹{amount:,.2f}"
# #             )
# #         else:
# #             if pattern == "BANK_INTEREST" or (payee and "INTEREST" in payee.upper()):
# #                 action_word = f"Received ₹{amount:,.2f} interest credit"
# #             else:
# #                 action_word = f"Received ₹{amount:,.2f} from {payee or 'Payee'}"

# #         ref_str = f" [Ref: {ref_no}]" if ref_no else ""
# #         dynamic_display_text = (
# #             f"{direction_word} {target_subcategory} | {action_word}{ref_str} |"
# #             " Ingested via Staging"
# #         )

# #         item_remarks = {
# #             **remarks,
# #             "payee": payee,
# #             "upi_ref": ref_no,
# #             "display_text": dynamic_display_text,
# #             "target_account_name": target_subcategory,
# #             "directional_prefix": direction_word,
# #         }

# #         cluster = clusters_map[pattern]
# #         cluster["count"] += 1
# #         cluster["total_amount"] += amount

# #         if is_outflow:
# #             cluster["total_outflow"] += amount
# #         else:
# #             cluster["total_inflow"] += amount

# #         cluster["transaction_ids"].append(str(entry.id))

# #         if (
# #             len(cluster["sample_descriptions"]) < 3
# #             and dynamic_display_text not in cluster["sample_descriptions"]
# #         ):
# #             cluster["sample_descriptions"].append(dynamic_display_text)

# #         cluster["items"].append(
# #             {
# #                 "id": str(entry.id),
# #                 "narration": narration,
# #                 "debit": debit_val,
# #                 "credit": credit_val,
# #                 "amount": amount,
# #                 "direction": "OUTFLOW" if is_outflow else "INFLOW",
# #                 "transaction_date": str(entry.transaction_date),
# #                 "remarks": item_remarks,
# #             }
# #         )

# #     sorted_clusters = sorted(
# #         clusters_map.values(), key=lambda c: c["count"], reverse=True
# #     )

# #     if search_query and str(search_query).strip():
# #         norm_query = normalize_for_search(search_query)
# #         filtered_clusters = []

# #         for cluster in sorted_clusters:
# #             norm_pattern = normalize_for_search(cluster["pattern"])
# #             norm_samples = " ".join(
# #                 [
# #                     normalize_for_search(s)
# #                     for s in cluster.get("sample_descriptions", [])
# #                 ]
# #             )

# #             matches_pattern = norm_query in norm_pattern or norm_query in norm_samples
# #             matches_item = any(
# #                 norm_query in normalize_for_search(item.get("narration", ""))
# #                 or norm_query
# #                 in normalize_for_search(item.get("remarks", {}).get("payee", ""))
# #                 for item in cluster.get("items", [])
# #             )

# #             if matches_pattern or matches_item:
# #                 filtered_clusters.append(cluster)

# #         return filtered_clusters

# #     print(f"[engine] Total distinct clusters created: {len(sorted_clusters)}")
# #     return sorted_clusters


# # def get_clean_patterns(rule) -> list[str]:
# #     """Retrieves clean pattern list directly from model or dict representation."""
# #     if hasattr(rule, "get_patterns") and callable(rule.get_patterns):
# #         return rule.get_patterns()

# #     patterns = (
# #         rule.get("patterns", [])
# #         if isinstance(rule, dict)
# #         else getattr(rule, "patterns", [])
# #     )

# #     if isinstance(patterns, list):
# #         return [str(p).strip() for p in patterns if p and str(p).strip()]

# #     if isinstance(patterns, str):
# #         try:
# #             parsed = json.loads(patterns)
# #             if isinstance(parsed, list):
# #                 return [str(p).strip() for p in parsed if p and str(p).strip()]
# #         except json.JSONDecodeError:
# #             return [patterns.strip()]

# #     return []


# # def classify_via_rules(
# #     raw_narration: str, is_debit: bool = True
# # ) -> Optional[Dict[str, str]]:
# #     """
# #     Evaluates raw narration text against active ClassificationRule patterns
# #     using model pattern retrieval and strict multi-token matching.
# #     """
# #     if not raw_narration or not str(raw_narration).strip():
# #         return None

# #     target_rule_type = "Debit" if is_debit else "Credit"

# #     active_rules = ClassificationRule.objects.filter(
# #         is_active=True, rule_type=target_rule_type
# #     ).order_by("-priority")

# #     for rule in active_rules:
# #         patterns_list = (
# #             rule.get_patterns()
# #             if hasattr(rule, "get_patterns")
# #             else get_clean_patterns(rule)
# #         )

# #         for pattern in patterns_list:
# #             if match_multi_tokens(raw_narration, pattern):
# #                 rule.match_count = (rule.match_count or 0) + 1
# #                 rule.save(update_fields=["match_count", "updated_at"])

# #                 return {
# #                     "category": rule.target_category,
# #                     "subcategory": rule.target_subcategory,
# #                     "matched_pattern": pattern,
# #                     "rule_code": rule.rule_code,
# #                     "rule_type": rule.rule_type,
# #                 }
# #     return None


# # def generate_strict_multitoken_pattern(narration_list: list[str]) -> list[str]:
# #     """
# #     Extracts tokens present in the majority (>= 80%) of selected narrations,
# #     filtering out noise words and preserving natural word order.
# #     """
# #     if not narration_list:
# #         return []

# #     token_sequences = [extract_meaningful_tokens(n) for n in narration_list if n]
# #     if not token_sequences:
# #         return []

# #     token_counts = Counter()
# #     for seq in token_sequences:
# #         for token in set(seq):
# #             if token not in NOISE_KEYWORD_BLACKLIST:
# #                 token_counts[token] += 1

# #     total_rows = len(token_sequences)
# #     threshold = max(1, int(total_rows * 0.8))

# #     majority_tokens_set = {
# #         token for token, count in token_counts.items() if count >= threshold
# #     }

# #     ordered_tokens = []
# #     first_sample_tokens = token_sequences[0]

# #     for token in first_sample_tokens:
# #         if token in majority_tokens_set and token not in ordered_tokens:
# #             ordered_tokens.append(token)

# #     for token in majority_tokens_set:
# #         if token not in ordered_tokens:
# #             ordered_tokens.append(token)

# #     return ordered_tokens

# # def add_or_update_classification_rule(
# #     category: str,
# #     subcategory: str,
# #     new_pattern: str,
# #     entry_type: str = "Debit",
# # ) -> bool:
# #     """
# #     Appends an explicit pattern into an existing ClassificationRule or creates a new active rule.
# #     Protects multi-word phrases from token-splitting, prunes loose single sub-tokens when
# #     compounds are learned, and keeps patterns sorted compound-first.
# #     """
# #     if not new_pattern or not str(new_pattern).strip():
# #         return False

# #     # 1. Clean explicit user selection as an ATOMIC unit (NO word splitting)
# #     clean_pattern = sanitize_user_pattern(new_pattern)
# #     if not clean_pattern:
# #         return False

# #     # 2. Single token safety validation (only applies if pattern is a single word)
# #     if " " not in clean_pattern:
# #         if (
# #             clean_pattern in NOISE_KEYWORD_BLACKLIST
# #             or clean_pattern in RULE_SAFETY_BLACKLIST
# #         ):
# #             print(
# #                 f"⚠️ Rejected unsafe single-token pattern from blacklist: '{clean_pattern}'"
# #             )
# #             return False

# #         if len(clean_pattern) < 4:
# #             print(
# #                 f"⚠️ Rejected short single-token pattern (<4 chars): '{clean_pattern}'"
# #             )
# #             return False

# #     clean_entry_type = (
# #         "Credit" if str(entry_type).strip().lower() == "credit" else "Debit"
# #     )

# #     taxonomy_node = TaxonomyTree.objects.filter(
# #         category__iexact=category, subcategory__iexact=subcategory
# #     ).first()
# #     resolved_taxonomy = taxonomy_node if taxonomy_node else None

# #     existing_rule = ClassificationRule.objects.filter(
# #         target_category=category,
# #         target_subcategory=subcategory,
# #         rule_type=clean_entry_type,
# #         is_active=True,
# #     ).first()

# #     if existing_rule:
# #         patterns = set(get_clean_patterns(existing_rule))
# #         updated_fields = ["patterns", "match_count", "updated_at"]

# #         if clean_pattern not in patterns:
# #             # 💡 REVERSE PRUNING: When adding a multi-word compound (e.g. "APAN DAS" or "MARGIN FREE"),
# #             # automatically prune loose single sub-tokens ("APAN", "DAS", "MARGIN", "FREE") from the rule.
# #             if " " in clean_pattern:
# #                 sub_words = set(clean_pattern.split())
# #                 pruned_tokens = {p for p in patterns if p in sub_words}
# #                 if pruned_tokens:
# #                     patterns = patterns - pruned_tokens
# #                     print(
# #                         f"🧹 Pruned loose sub-tokens {pruned_tokens} from rule {existing_rule.rule_code} in favor of compound '{clean_pattern}'"
# #                     )

# #             patterns.add(clean_pattern)

# #             # Sort array so multi-word compound phrases ALWAYS appear first
# #             sorted_patterns = sorted(
# #                 list(patterns), key=lambda x: (-len(x.split()), -len(x))
# #             )

# #             existing_rule.patterns = sorted_patterns
# #             existing_rule.match_count = (existing_rule.match_count or 0) + 1

# #             if not existing_rule.taxonomy and resolved_taxonomy:
# #                 existing_rule.taxonomy = resolved_taxonomy
# #                 updated_fields.append("taxonomy")

# #             existing_rule.save(update_fields=updated_fields)
# #             print(
# #                 f"✅ Appended clean pattern '{clean_pattern}' to existing rule {existing_rule.rule_code}"
# #             )
# #             return True
# #         return False

# #     else:
# #         vector_prefix = "DE" if clean_entry_type == "Debit" else "CR"
# #         hash_input = f"{subcategory}_{clean_pattern}_{clean_entry_type}".upper()
# #         short_code = hashlib.md5(hash_input.encode()).hexdigest()[:6].upper()
# #         rule_code = f"CR_{vector_prefix}_{short_code}"

# #         ClassificationRule.objects.create(
# #             name=f"Learned ({clean_entry_type}): {subcategory} ({clean_pattern})",
# #             rule_code=rule_code,
# #             rule_type=clean_entry_type,
# #             target_category=category,
# #             target_subcategory=subcategory,
# #             patterns=[clean_pattern],
# #             priority=1,
# #             is_active=True,
# #             created_from_manual_override=True,
# #             match_count=1,
# #             taxonomy=resolved_taxonomy,
# #         )
# #         print(
# #             f"✅ Created new distinct rule {rule_code} with clean pattern '{clean_pattern}'"
# #         )
# #         return True


# # def reclassify_and_learn(
# #     transaction_ids: List[str],
# #     target_category: str,
# #     target_subcategory: str,
# #     patterns: Optional[List[str]] = None,
# #     save_rule: bool = True,
# # ) -> Dict[str, Any]:
# #     """
# #     Executes bulk reclassification for Node 99 records and learns clean,
# #     multi-crore-safe matching rules without token pollution.
# #     """
# #     if not transaction_ids:
# #         return {"status": "success", "reclassified_count": 0, "rules_updated": False}

# #     entries = list(JournalEntry.objects.filter(account_id=99, id__in=transaction_ids))
# #     if not entries:
# #         entries = list(
# #             JournalEntry.objects.filter(
# #                 account_id=99, row_identifier__in=transaction_ids
# #             )
# #         )

# #     if not entries:
# #         return {"status": "success", "reclassified_count": 0, "rules_updated": False}

# #     total_debit = sum(float(e.debit or 0) for e in entries)
# #     total_credit = sum(float(e.credit or 0) for e in entries)
# #     inferred_entry_type = "Credit" if total_credit > total_debit else "Debit"

# #     payee_groups = {}

# #     for entry in entries:
# #         snapshot = entry.evaluation_matrix_snapshot or {}
# #         snapshot["previous_category"] = snapshot.get("resolved_category")
# #         snapshot["previous_subcategory"] = snapshot.get("resolved_subcategory")
# #         snapshot["resolved_category"] = target_category
# #         snapshot["resolved_subcategory"] = target_subcategory
# #         snapshot["is_manual_override"] = True

# #         entry.evaluation_matrix_snapshot = snapshot
# #         entry.classification_status = "RECLASSIFIED"
# #         entry.is_reclassified = True

# #         remarks_dict = entry.remarks if isinstance(entry.remarks, dict) else {}
# #         narration_text = remarks_dict.get("narration") or str(entry.remarks or "")

# #         direction_word = remarks_dict.get("directional_prefix", "By")
# #         payee = remarks_dict.get("payee") or ""
# #         upi_ref = remarks_dict.get("upi_ref") or ""
# #         user_note = remarks_dict.get("user_note") or ""

# #         clean_payee = extract_clean_payee_pattern(payee or narration_text) or "GENERIC"
# #         if clean_payee not in payee_groups:
# #             payee_groups[clean_payee] = []
# #         if narration_text:
# #             payee_groups[clean_payee].append(narration_text)

# #         amt = float(entry.debit or entry.credit or 0)
# #         ref_str = f" [Ref: {upi_ref}]" if upi_ref else ""
# #         action_word = f"Paid ₹{amt:,.2f} to {payee}" if payee else f"Amount ₹{amt:,.2f}"
# #         note_str = f" | Note: {user_note.strip()}" if user_note else ""

# #         updated_display_text = (
# #             f"{direction_word} {target_subcategory} |"
# #             f" {action_word}{ref_str}{note_str} | Reclassified via Workbench"
# #         )

# #         entry.remarks = {
# #             **remarks_dict,
# #             "target_account_name": target_subcategory,
# #             "display_text": updated_display_text,
# #             "updated_at": timezone.now().isoformat(),
# #         }

# #     JournalEntry.objects.bulk_update(
# #         entries,
# #         [
# #             "evaluation_matrix_snapshot",
# #             "classification_status",
# #             "is_reclassified",
# #             "remarks",
# #         ],
# #     )

# #     rules_updated = False
# #     learned_patterns = []

# #     if save_rule:
# #         print("\n" + "🔍" * 40)
# #         print(f"[ENGINE DEBUG] Learning Rules for Subcategory: '{target_subcategory}'")

# #         # -------------------------------------------------------------------------
# #         # PATH A: Explicit User Patterns Passed from Frontend UI (Highest Priority)
# #         # ONLY runs when user manually selects tokens in the modal.
# #         # -------------------------------------------------------------------------
# #         if patterns and isinstance(patterns, list) and len(patterns) > 0:
# #             print(f"[ENGINE DEBUG] Using Explicit User Patterns ONLY: {patterns}")
# #             for user_p in patterns:
# #                 clean_user_p = str(user_p).strip().upper()

# #                 # Check for length and skip direct single-token blacklist hits
# #                 # (Allows compound phrases like 'AMAZON INDIA' or 'MARGIN FREE')
# #                 is_compound = " " in clean_user_p
# #                 if len(clean_user_p) >= 3 and (
# #                     is_compound or clean_user_p not in RULE_SAFETY_BLACKLIST
# #                 ):
# #                     updated = add_or_update_classification_rule(
# #                         category=target_category,
# #                         subcategory=target_subcategory,
# #                         new_pattern=clean_user_p,
# #                         entry_type=inferred_entry_type,
# #                     )
# #                     if updated:
# #                         rules_updated = True
# #                         learned_patterns.append(clean_user_p)

# #         # -------------------------------------------------------------------------
# #         # PATH B: Controlled Auto-Extraction with Strict Safety Guardrails
# #         # Fallback path ONLY when frontend provides ZERO explicit user choices.
# #         # -------------------------------------------------------------------------
# #         else:
# #             print(
# #                 f"[ENGINE DEBUG] No explicit patterns passed. Grouped {len(entries)} items into {len(payee_groups)} distinct payee clusters:"
# #             )

# #             for payee_key, group_narrations in payee_groups.items():
# #                 common_tokens = generate_strict_multitoken_pattern(group_narrations)

# #                 # Filter out numbers, blacklist words, and generic city/store names
# #                 safe_tokens = [
# #                     t
# #                     for t in common_tokens
# #                     if not re.search(r"\d", t)
# #                     and t.upper() not in NOISE_KEYWORD_BLACKLIST
# #                     and t.upper() not in RULE_SAFETY_BLACKLIST
# #                     and len(t) > 2
# #                 ]

# #                 print(
# #                     f"    --> Cluster '{payee_key}': Extracted Safe Tokens = {safe_tokens}"
# #                 )

# #                 if safe_tokens:
# #                     # Cap at max 2 anchor tokens (e.g. "SKECHERS", "LULU PARKING")
# #                     capped_tokens = safe_tokens[:2]
# #                     compound_pattern = " ".join(capped_tokens)

# #                     # Only proceed if pattern meets minimum length requirement
# #                     if len(compound_pattern) >= 3:
# #                         updated = add_or_update_classification_rule(
# #                             category=target_category,
# #                             subcategory=target_subcategory,
# #                             new_pattern=compound_pattern,
# #                             entry_type=inferred_entry_type,
# #                         )
# #                         if updated:
# #                             rules_updated = True
# #                             learned_patterns.append(compound_pattern)

# #         print("🔍" * 40 + "\n")

# #     return {
# #         "status": "success",
# #         "reclassified_count": len(entries),
# #         "entry_type_bound": inferred_entry_type,
# #         "rules_updated": rules_updated,
# #         "patterns_learned": learned_patterns,
# #     }

# # end region
