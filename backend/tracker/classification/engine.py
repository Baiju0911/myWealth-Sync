# tracker/classification/engine.py

import re
from typing import List, Dict, Any, Optional
from tracker.models import JournalEntry, StatementStagingLine, ClassificationRule
from tracker.classification.remarks_service import generate_cluster_pattern
from tracker.classification.utils.upiparser import parse_upi_narration
from tracker.models import TaxonomyTree
from datetime import datetime
from django.utils import timezone

GENERIC_PATTERNS = {
    "#GENERAL_OPERATING_EXPENSES",
    "#GENERAL_OPERATING_EXPENSE",
    "#SUSPENSE_ACCOUNT",
    "#UNCLASSIFIED_OTHER",
    "#SUSPENSE",
    "#TRANSFER_NACH",
    "GENERAL_OPERATING_EXPENSES",
    "UNCLASSIFIED",
    "TRANSFER_NACH",
    "UNCLASSIFIED_OTHER",
    "SUSPENSE_ACCOUNT",
    "NACH",
    "IMPS",
    "KALLAMBALAM",
    "POSTRN",
}


def normalize_for_search(text: str) -> str:
    """
    Strips underscores, spaces, dashes, colons, and punctuation for fuzzy matching.
    e.g., 'B_AIJU' -> 'BAIJU', 'PRAVEE N P' -> 'PRAVEENP'
    """
    if not text:
        return ""
    return re.sub(r"[^A-Z0-9]+", "", str(text).upper())


def get_suspense_clusters(
    target_subcategory="Suspense Account", account_id=None, search_query=None
):
    print(f"\n" + "=" * 80)
    print(
        f"[engine] START get_suspense_clusters(sub='{target_subcategory}', account_id={account_id}, query='{search_query}')"
    )
    print("=" * 80)

    query = JournalEntry.objects.filter(is_reclassified=False)
    if account_id:
        query = query.filter(account_id=account_id)
    else:
        query = query.filter(account_id=99)

    entries = list(query.order_by("-transaction_date"))
    print(f"[engine] Total unclassified entries fetched: {len(entries)}")

    row_ids = [e.row_identifier for e in entries if e.row_identifier]
    staging_map = {
        s.row_identifier: s.narration
        for s in StatementStagingLine.objects.filter(row_identifier__in=row_ids).only(
            "row_identifier", "narration"
        )
    }

    clusters_map = {}

    for idx, entry in enumerate(entries, 1):
        remarks = entry.remarks if isinstance(entry.remarks, dict) else {}
        narration = staging_map.get(entry.row_identifier, "")
        stored_pattern = remarks.get("pattern")

        # 🟢 STRICT DIRECTION RESOLUTION based on credit vs debit values
        debit_val = float(entry.debit or 0)
        credit_val = float(entry.credit or 0)

        if credit_val > 0 and debit_val == 0:
            is_outflow = False
            amount = credit_val
        elif debit_val > 0 and credit_val == 0:
            is_outflow = True
            amount = debit_val
        else:
            amount = debit_val if debit_val > 0 else credit_val
            is_outflow = debit_val > 0

        parsed_meta = parse_upi_narration(narration) or {}
        payee = parsed_meta.get("payee") or remarks.get("payee")
        ref_no = parsed_meta.get("upi_ref") or remarks.get("upi_ref")

        # Force live re-parsing if pattern is missing or generic
        if not stored_pattern or stored_pattern in GENERIC_PATTERNS:
            pattern = generate_cluster_pattern(
                narration=narration, remarks_data={"payee": payee}
            )
        else:
            pattern = stored_pattern

        if pattern not in clusters_map:
            clusters_map[pattern] = {
                "pattern": pattern,
                "count": 0,
                "total_amount": 0.0,
                "total_inflow": 0.0,
                "total_outflow": 0.0,
                "sample_descriptions": [],
                "items": [],
                "transaction_ids": [],
            }

        # 🟢 DIRECTIONAL WORDING GUARDRAILS
        direction_word = "By" if is_outflow else "To"

        if is_outflow:
            action_word = (
                f"Paid ₹{amount:,.2f} to {payee}"
                if payee
                else f"Outflow of ₹{amount:,.2f}"
            )
        else:
            if pattern == "BANK_INTEREST" or (payee and "INTEREST" in payee.upper()):
                action_word = f"Received ₹{amount:,.2f} interest credit"
            else:
                action_word = f"Received ₹{amount:,.2f} from {payee or 'Payee'}"

        ref_str = f" [Ref: {ref_no}]" if ref_no else ""
        dynamic_display_text = f"{direction_word} {target_subcategory} | {action_word}{ref_str} | Ingested via Staging"

        item_remarks = {
            **remarks,
            "payee": payee,
            "upi_ref": ref_no,
            "display_text": dynamic_display_text,
            "target_account_name": target_subcategory,
            "directional_prefix": direction_word,
        }

        cluster = clusters_map[pattern]
        cluster["count"] += 1
        cluster["total_amount"] += amount

        if is_outflow:
            cluster["total_outflow"] += amount
        else:
            cluster["total_inflow"] += amount

        cluster["transaction_ids"].append(str(entry.id))

        if (
            len(cluster["sample_descriptions"]) < 3
            and dynamic_display_text not in cluster["sample_descriptions"]
        ):
            cluster["sample_descriptions"].append(dynamic_display_text)

        cluster["items"].append(
            {
                "id": str(entry.id),
                "narration": narration,
                "debit": debit_val,
                "credit": credit_val,
                "amount": amount,
                "direction": (
                    "OUTFLOW" if is_outflow else "INFLOW"
                ),  # 🟢 Strict direction
                "transaction_date": str(entry.transaction_date),
                "remarks": item_remarks,
            }
        )

    sorted_clusters = sorted(
        clusters_map.values(), key=lambda c: c["count"], reverse=True
    )

    # 🟢 FUZZY NORMALIZED SEARCH FILTER
    if search_query and str(search_query).strip():
        norm_query = normalize_for_search(search_query)
        filtered_clusters = []

        for cluster in sorted_clusters:
            norm_pattern = normalize_for_search(cluster["pattern"])
            norm_samples = " ".join(
                [
                    normalize_for_search(s)
                    for s in cluster.get("sample_descriptions", [])
                ]
            )

            # Check pattern key, samples, or individual items inside cluster
            matches_pattern = norm_query in norm_pattern or norm_query in norm_samples
            matches_item = any(
                norm_query in normalize_for_search(item.get("narration", ""))
                or norm_query
                in normalize_for_search(item.get("remarks", {}).get("payee", ""))
                for item in cluster.get("items", [])
            )

            if matches_pattern or matches_item:
                filtered_clusters.append(cluster)

        print(
            f"[engine] Search query '{search_query}' (normalized: '{norm_query}') filtered {len(sorted_clusters)} -> {len(filtered_clusters)} clusters"
        )
        return filtered_clusters

    print(f"[engine] Total distinct clusters created: {len(sorted_clusters)}")
    return sorted_clusters


def classify_via_rules(raw_narration: str) -> Optional[Dict[str, str]]:
    """
    Evaluates raw narration text against active ClassificationRule patterns JSON lists.
    """
    if not raw_narration:
        return None

    narration_upper = raw_narration.upper()
    active_rules = ClassificationRule.objects.filter(is_active=True).order_by(
        "-priority"
    )

    for rule in active_rules:
        patterns_list = rule.patterns if isinstance(rule.patterns, list) else []

        for pattern in patterns_list:
            if pattern and str(pattern).strip().upper() in narration_upper:
                rule.match_count += 1
                rule.save(update_fields=["match_count"])

                return {
                    "category": rule.target_category,
                    "subcategory": rule.target_subcategory,
                    "matched_pattern": pattern,
                }
    return None


def add_or_update_classification_rule(
    category: str, subcategory: str, new_pattern: str
) -> bool:
    """
    Appends a pattern into an existing Taxonomy rule JSON list or creates a new active rule.
    """
    if (
        not new_pattern
        or not str(new_pattern).strip()
        or str(new_pattern).strip().upper() in ["NONE", "UNDEFINED"]
    ):
        return False

    clean_pattern = str(new_pattern).strip().upper()

    rule = ClassificationRule.objects.filter(
        target_category=category, target_subcategory=subcategory, is_active=True
    ).first()

    if rule:
        existing_patterns = rule.patterns if isinstance(rule.patterns, list) else []
        if clean_pattern not in existing_patterns:
            existing_patterns.append(clean_pattern)
            rule.patterns = existing_patterns
            rule.save(update_fields=["patterns", "updated_at"])
            return True
        return False
    else:
        rule_name = f"{subcategory} ({clean_pattern})"
        ClassificationRule.objects.create(
            name=rule_name,
            patterns=[clean_pattern],
            rule_type="CONTAINS",
            target_category=category,
            target_subcategory=subcategory,
            priority=10,
            is_active=True,
            created_from_manual_override=True,
        )
        return True


def reclassify_and_learn(
    transaction_ids: List[str],
    target_category: str,
    target_subcategory: str,
    patterns: Optional[List[str]] = None,
    save_rule: bool = True,
) -> Dict[str, Any]:
    """
    Executes bulk reclassification for Node 99 records and learns new matching rules.
    Preserves payee metadata while updating target account names in remarks.
    """
    if not transaction_ids:
        return {"status": "success", "reclassified_count": 0, "rules_updated": False}

    # Fetch entries sitting in Node 99
    entries = list(JournalEntry.objects.filter(id__in=transaction_ids, account_id=99))

    target_label = f"{target_category} > {target_subcategory}"

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

        # Update structured JSON remarks
        if isinstance(entry.remarks, dict):
            existing_remarks = entry.remarks
            direction_word = existing_remarks.get("directional_prefix", "By")
            payee = existing_remarks.get("payee") or ""
            upi_ref = existing_remarks.get("upi_ref") or ""
            user_note = existing_remarks.get("user_note") or ""

            amt = float(entry.debit or entry.credit or 0)
            ref_str = f" [Ref: {upi_ref}]" if upi_ref else ""
            action_word = (
                f"Paid ₹{amt:,.2f} to {payee}" if payee else f"Amount ₹{amt:,.2f}"
            )
            note_str = f" | Note: {user_note.strip()}" if user_note else ""

            updated_display_text = f"{direction_word} {target_subcategory} | {action_word}{ref_str}{note_str} | Reclassified via Workbench"

            entry.remarks = {
                **existing_remarks,
                "target_account_name": target_subcategory,
                "display_text": updated_display_text,
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

    # Append patterns into active Classification Rules
    rules_updated = False
    if save_rule and patterns:
        for p in patterns:
            if (
                p
                and str(p).strip()
                and str(p).strip().upper() not in ["NONE", "UNDEFINED"]
            ):
                updated = add_or_update_classification_rule(
                    category=target_category,
                    subcategory=target_subcategory,
                    new_pattern=str(p).strip().upper(),
                )
                if updated:
                    rules_updated = True

    return {
        "status": "success",
        "reclassified_count": len(entries),
        "rules_updated": rules_updated,
        "patterns_learned": patterns or [],
    }


# def reclassify_and_learn_older(
#     transaction_ids: List[str],
#     target_category: str,
#     target_subcategory: str,
#     patterns: Optional[List[str]] = None,
#     save_rule: bool = True,
# ) -> Dict[str, Any]:
#     """
#     Executes bulk reclassification for Node 99 records and learns new matching rules.
#     """
#     if not transaction_ids:
#         return {"status": "success", "reclassified_count": 0, "rules_updated": False}

#     entries = list(JournalEntry.objects.filter(id__in=transaction_ids, account_id=99))
#     target_node = TaxonomyTree.objects.filter(
#         category__iexact=target_category, subcategory__iexact=target_subcategory
#     ).first()

#     target_account_id = target_node.id if target_node else 99

#     # 1. Update audit trail flags and snapshot
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
#         if target_node:
#             entry.account_id = target_account_id

#         if isinstance(entry.remarks, dict):
#             direction_word = entry.remarks.get("directional_prefix", "By")
#             payee = entry.remarks.get("payee", "")
#             upi_ref = entry.remarks.get("upi_ref", "")
#             ref_str = f" [Ref: {upi_ref}]" if upi_ref else ""
#             amt = float(entry.debit or entry.credit or 0)

#             entry.remarks["target_account_name"] = target_subcategory
#             entry.remarks["display_text"] = (
#                 f"{direction_word} {target_subcategory} | Paid ₹{amt:,.2f} to {payee}{ref_str} | Reclassified via Workbench"
#             )

#     JournalEntry.objects.bulk_update(
#         entries,
#         [
#             "evaluation_matrix_snapshot",
#             "classification_status",
#             "is_reclassified",
#             "account_id",
#             "remarks",
#         ],
#     )

#     # 2. Append patterns into active Classification Rules
#     rules_updated = False
#     if save_rule and patterns:
#         for p in patterns:
#             if (
#                 p
#                 and str(p).strip()
#                 and str(p).strip().upper() not in ["NONE", "UNDEFINED"]
#             ):
#                 updated = add_or_update_classification_rule(
#                     category=target_category,
#                     subcategory=target_subcategory,
#                     new_pattern=str(p).strip().upper(),
#                 )
#                 if updated:
#                     rules_updated = True

#     return {
#         "status": "success",
#         "reclassified_count": len(entries),
#         "rules_updated": rules_updated,
#         "patterns_learned": patterns or [],
#     }
