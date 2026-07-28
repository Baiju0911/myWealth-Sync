# tracker/classification/engine.py

import re
from typing import List, Dict, Any, Optional
from tracker.models import JournalEntry, StatementStagingLine, ClassificationRule
from tracker.classification.remarks_service import generate_cluster_pattern

# List of broad bucket patterns that MUST be broken down into granular vendor clusters
GENERIC_PATTERNS = {
    "#GENERAL_OPERATING_EXPENSES",
    "#GENERAL_OPERATING_EXPENSE",
    "#SUSPENSE_ACCOUNT",
    "#UNCLASSIFIED_OTHER",
    "#SUSPENSE",
    "GENERAL_OPERATING_EXPENSES",
    "UNCLASSIFIED",
}


def extract_merchant_anchor(narration: str) -> str:
    """
    Extracts cleaner merchant anchors/vendor names from raw bank narrations.
    """
    if not narration:
        return "UNCLUSTERED"

    narration_upper = narration.upper()

    # Match UPI recipient pattern e.g., UPI/FDRL/.../SHABINA R/UPI/...
    upi_match = re.search(r"UPI/[^/]+/[^/]+/([^/]+)", narration_upper)
    if upi_match:
        vendor = upi_match.group(1).strip()
        if vendor and len(vendor) > 2:
            return vendor

    # Match CWDR / Cash Withdrawal
    if "CWDR" in narration_upper or "ATM" in narration_upper:
        return "CASH_WITHDRAWAL"

    # Match MOB / OWN ACCOUNT Transfers
    if "MOB/OWN ACCOUNT" in narration_upper or "OWN ACCOUNT" in narration_upper:
        return "SELF_TRANSFER"

    # Fallback to vendor_cluster or generic pattern
    return "GENERAL_OPERATING_EXPENSES"


def get_suspense_clusters(target_subcategory="Suspense Account", account_id=None):
    """
    Fetches unclassified journal entries and groups them into granular merchant clusters.
    """
    query = JournalEntry.objects.filter(is_reclassified=False)

    if account_id:
        query = query.filter(account_id=account_id)
    else:
        query = query.filter(account_id=99)  # Suspense Node default

    entries = query.order_by("-transaction_date")

    # Fetch raw narrations map from staging to guarantee fallback text
    row_ids = [e.row_identifier for e in entries if e.row_identifier]
    staging_map = {
        s.row_identifier: s.narration
        for s in StatementStagingLine.objects.filter(row_identifier__in=row_ids).only(
            "row_identifier", "narration"
        )
    }

    clusters_map = {}

    for entry in entries:
        remarks = entry.remarks if isinstance(entry.remarks, dict) else {}
        narration = staging_map.get(entry.row_identifier, "")

        # 1. Inspect existing pattern tag
        stored_pattern = remarks.get("pattern")
        target_sub_tag = f"#{target_subcategory.upper().replace(' ', '_')}"

        # 2. Force granular pattern generation if pattern is missing or generic
        if (
            not stored_pattern
            or stored_pattern in GENERIC_PATTERNS
            or stored_pattern == target_sub_tag
        ):
            pattern = generate_cluster_pattern(
                narration=narration, remarks_data=remarks
            )
        else:
            pattern = stored_pattern

        if pattern not in clusters_map:
            clusters_map[pattern] = {
                "pattern": pattern,
                "count": 0,
                "total_amount": 0.0,
                "sample_descriptions": [],
                "items": [],
                "transaction_ids": [],
            }

        debit_val = float(entry.debit or 0)
        credit_val = float(entry.credit or 0)
        amount = debit_val if debit_val > 0 else credit_val

        cluster = clusters_map[pattern]
        cluster["count"] += 1
        cluster["total_amount"] += amount
        cluster["transaction_ids"].append(str(entry.id))

        display_text = remarks.get("display_text") or narration
        if (
            len(cluster["sample_descriptions"]) < 3
            and display_text not in cluster["sample_descriptions"]
        ):
            cluster["sample_descriptions"].append(display_text)

        cluster["items"].append(
            {
                "id": str(entry.id),
                "narration": narration,
                "debit": debit_val,
                "credit": credit_val,
                "amount": amount,
                "transaction_date": str(entry.transaction_date),
                "remarks": remarks,
            }
        )

    # Sort clusters by record count descending
    sorted_clusters = sorted(
        clusters_map.values(), key=lambda c: c["count"], reverse=True
    )
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
    """
    if not transaction_ids:
        return {"status": "success", "reclassified_count": 0, "rules_updated": False}

    entries = list(JournalEntry.objects.filter(id__in=transaction_ids, account_id=99))

    # 1. Update audit trail flags and snapshot
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

    JournalEntry.objects.bulk_update(
        entries,
        ["evaluation_matrix_snapshot", "classification_status", "is_reclassified"],
    )

    # 2. Append patterns into active Classification Rules
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
