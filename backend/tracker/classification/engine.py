import re
from typing import List, Dict, Any, Optional
from tracker.models import JournalEntry, StatementStagingLine, ClassificationRule

# Common corporate / legal entity suffixes to strip for clean grouping
LEGAL_SUFFIXES = (
    r"\b(LIMITED|LTD|PVT|PRIVATE|INCORPORATED|INC|CORP|CORPORATION|SERVICES|SERVICE)\b"
)

# Honorifics & salutation prefixes to strip from payee names
SALUTATIONS = r"^(MR|MRS|MS|DR|SHRI|SMT|M/S|MS)\b\s*"


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


def get_suspense_clusters(
    target_subcategory: str = "Suspense Account", account_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    print(f"\n=================== [DEBUG: GET SUSPENSE CLUSTERS] ===================")
    print(f"--> Received target_subcategory: '{target_subcategory}'")
    print(f"--> Received account_id: {account_id} (Type: {type(account_id).__name__})")

    # 1. Base filter for Node 99 suspense entries
    query_filters = {
        "account_id": 99,
        "evaluation_matrix_snapshot__resolved_subcategory": target_subcategory,
    }

    # 🟢 If frontend provides account_id (e.g. 3), filter snapshot source
    if account_id:
        query_filters["evaluation_matrix_snapshot__source_account_id"] = account_id

    print(f"--> Initial JournalEntry query_filters: {query_filters}")
    entries = list(JournalEntry.objects.filter(**query_filters))
    print(f"--> Matched JournalEntry count (Node 99): {len(entries)}")

    # 🟢 FALLBACK CHECK: If no entries found with source_account_id, query via row_identifiers from staging
    if not entries and account_id:
        print(
            "--> ⚠️ Initial query returned 0 rows. Attempting fallback via StatementStagingLine row_identifiers..."
        )

        staging_row_ids = list(
            StatementStagingLine.objects.filter(account_id=account_id).values_list(
                "row_identifier", flat=True
            )
        )
        print(
            f"--> Found {len(staging_row_ids)} staging row_identifiers for account_id={account_id}"
        )

        fallback_filters = {
            "account_id": 99,
            "row_identifier__in": staging_row_ids,
            "evaluation_matrix_snapshot__resolved_subcategory": target_subcategory,
        }
        entries = list(JournalEntry.objects.filter(**fallback_filters))
        print(f"--> Matched JournalEntry count via fallback query: {len(entries)}")

    if not entries:
        print(
            "--> ❌ No entries found for target_subcategory and account_id. Inspecting 1 sample Node 99 entry:"
        )
        sample = JournalEntry.objects.filter(account_id=99).first()
        if sample:
            print(
                f"    * Sample Snapshot Keys: {list((sample.evaluation_matrix_snapshot or {}).keys())}"
            )
            print(f"    * Sample Snapshot Content: {sample.evaluation_matrix_snapshot}")
        else:
            print(
                "    * No Node 99 (account_id=99) records exist in JournalEntry database at all!"
            )
        print(
            "======================================================================\n"
        )
        return []

    # 2. Build staging lookup map strictly scoped to account_id
    row_ids = [e.row_identifier for e in entries if e.row_identifier]
    staging_filters = {"row_identifier__in": row_ids}
    if account_id:
        staging_filters["account_id"] = account_id  # 🟢 Strictly scope to account 3

    print(f"--> Querying StatementStagingLine with filters: {staging_filters}")
    staging_qs = StatementStagingLine.objects.filter(**staging_filters)
    print(
        f"--> Matched StatementStagingLine count: {staging_qs.count()} / {len(row_ids)} total row_ids"
    )

    staging_map = {s.row_identifier: s.narration for s in staging_qs}

    clusters_dict = {}

    for entry in entries:
        snapshot = entry.evaluation_matrix_snapshot or {}

        raw_narration = (
            staging_map.get(entry.row_identifier)
            or snapshot.get("narration")
            or snapshot.get("description")
            or f"Txn #{entry.row_identifier[:8]}"
        )

        vendor_cluster = snapshot.get("vendor_cluster")
        if not vendor_cluster or str(vendor_cluster).startswith("GR"):
            cluster_key = extract_merchant_anchor(raw_narration)
        else:
            cluster_key = str(vendor_cluster).strip().upper()

        if cluster_key not in clusters_dict:
            clusters_dict[cluster_key] = {
                "pattern": cluster_key,
                "count": 0,
                "total_amount": 0.0,
                "total_outflow": 0.0,
                "total_inflow": 0.0,
                "transaction_ids": [],
                "items": [],
            }

        is_outflow = entry.debit > 0
        amount = float(entry.debit if is_outflow else entry.credit)
        direction = "OUTFLOW" if is_outflow else "INFLOW"
        flag_color = "rose" if is_outflow else "green"

        cluster = clusters_dict[cluster_key]
        cluster["count"] += 1
        cluster["total_amount"] += amount

        if is_outflow:
            cluster["total_outflow"] += amount
        else:
            cluster["total_inflow"] += amount

        entry_id_str = str(entry.id)
        cluster["transaction_ids"].append(entry_id_str)

        cluster["items"].append(
            {
                "id": entry_id_str,
                "row_identifier": entry.row_identifier,
                "transaction_date": str(entry.transaction_date),
                "narration": raw_narration,
                "amount": amount,
                "direction": direction,
                "flag_color": flag_color,
                "debit": float(entry.debit),
                "credit": float(entry.credit),
            }
        )

    result_clusters = list(clusters_dict.values())
    print(
        f"--> Successfully generated {len(result_clusters)} clusters containing {len(entries)} total items."
    )
    print("======================================================================\n")

    return result_clusters


# def extract_merchant_anchor(description: str) -> str:
#     if not description or str(description).strip() == "":
#         return "UNCLASSIFIED_OTHER"

#     raw_str = str(description).strip().upper()

#     # 1. Replace internal slashes in business prefixes like "M/S." or "M/S " -> "MS "
#     normalized_str = re.sub(r"\bM/S\.?\s*", "MS ", raw_str)

#     # 2. Extract segment between 3rd and 4th slash in UPI narrations
#     match = re.search(r"^UPI/[^/]+/[^/]+/([^/]+)/", normalized_str)

#     if match:
#         vendor_raw = match.group(1).strip()

#         # Remove 'MS ' prefix if present
#         vendor_clean = re.sub(r"^MS\s+", "", vendor_raw)

#         # Strip store/terminal codes like "C194 ", "S102 "
#         vendor_clean = re.sub(r"^[A-Z]\d+\s*", "", vendor_clean)

#         # Remove non-alphanumeric characters (keep spaces)
#         vendor_clean = re.sub(r"[^A-Z0-9\s]", " ", vendor_clean)

#         # Strip corporate suffixes (LIMITED, LTD, PVT, etc.)
#         vendor_clean = re.sub(LEGAL_SUFFIXES, "", vendor_clean)

#         # Strip salutations (MR, MRS, DR, MS, etc.)
#         vendor_clean = re.sub(SALUTATIONS, "", vendor_clean).strip()

#         # Collapse multiple spaces
#         vendor_clean = re.sub(r"\s+", " ", vendor_clean).strip()

#         # Specific alias unification
#         if "SWIGGY" in vendor_clean:
#             return "SWIGGY"
#         if "PARKING" in vendor_clean or "PARKINGBOOTH" in vendor_clean:
#             return "PARKING BOOTH"

#         if len(vendor_clean) >= 3:
#             return vendor_clean

#     # Fallback for non-UPI or non-standard narrations
#     return "UNCLASSIFIED_OTHER"


# def get_suspense_clusters(
#     target_subcategory: str = "Suspense Account",
# ) -> List[Dict[str, Any]]:
#     """
#     Groups Node 99 journal entries matching a target subcategory into merchant/vendor clusters.
#     Enriches each line item with raw bank narrations from StatementStagingLine.
#     """
#     # 1. Query Node 99 entries matching the subcategory
#     entries = list(
#         JournalEntry.objects.filter(
#             account_id=99,
#             evaluation_matrix_snapshot__resolved_subcategory=target_subcategory,
#         )
#     )

#     if not entries:
#         return []

#     # 2. Bulk fetch raw narrations from staging table via row_identifier lookup
#     row_ids = [e.row_identifier for e in entries if e.row_identifier]
#     staging_map = {
#         s.row_identifier: s.narration
#         for s in StatementStagingLine.objects.filter(row_identifier__in=row_ids)
#     }

#     clusters_dict = {}

#     for entry in entries:
#         snapshot = entry.evaluation_matrix_snapshot or {}

#         # 🟢 Resolve raw bank narration text
#         raw_narration = (
#             staging_map.get(entry.row_identifier)
#             or snapshot.get("narration")
#             or snapshot.get("raw_narration")
#             or snapshot.get("description")
#             or f"Txn #{entry.row_identifier[:8]}"
#         )

#         # 🟢 Determine Cluster Anchor Key
#         raw_pattern = (
#             snapshot.get("vendor_cluster")
#             or snapshot.get("matched_pattern")
#             or snapshot.get("applied_rule_code")
#             or "GENERAL_SUSPENSE"
#         )
#         cluster_key = str(raw_pattern).strip().upper() or "GENERAL_SUSPENSE"

#         if cluster_key not in clusters_dict:
#             clusters_dict[cluster_key] = {
#                 "pattern": cluster_key,
#                 "count": 0,
#                 "total_amount": 0.0,
#                 "total_outflow": 0.0,
#                 "total_inflow": 0.0,
#                 "transaction_ids": [],
#                 "items": [],
#             }

#         # 🟢 Direction & Amounts
#         is_outflow = entry.debit > 0
#         amount = float(entry.debit if is_outflow else entry.credit)
#         direction = "OUTFLOW" if is_outflow else "INFLOW"
#         flag_color = "rose" if is_outflow else "green"

#         cluster = clusters_dict[cluster_key]
#         cluster["count"] += 1
#         cluster["total_amount"] += amount

#         if is_outflow:
#             cluster["total_outflow"] += amount
#         else:
#             cluster["total_inflow"] += amount

#         entry_id_str = str(entry.id)
#         cluster["transaction_ids"].append(entry_id_str)

#         cluster["items"].append(
#             {
#                 "id": entry_id_str,
#                 "row_identifier": entry.row_identifier,
#                 "transaction_date": str(entry.transaction_date),
#                 "narration": raw_narration,
#                 "amount": amount,
#                 "direction": direction,
#                 "flag_color": flag_color,
#                 "debit": float(entry.debit),
#                 "credit": float(entry.credit),
#             }
#         )

#     return list(clusters_dict.values())


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


# def get_suspense_clusters1(
#     target_subcategory: str = "Suspense Account",
# ) -> List[Dict[str, Any]]:
#     """
#     Queries debit entries for any target subcategory, joins raw narrations from
#     StatementStagingLine via row_identifier, and groups them into merchant clusters with line item arrays.
#     """
#     suspense_entries = JournalEntry.objects.filter(
#         evaluation_matrix_snapshot__resolved_subcategory=target_subcategory, debit__gt=0
#     )

#     row_ids = [e.row_identifier for e in suspense_entries if e.row_identifier]

#     narration_map = {}
#     if row_ids:
#         narration_map = dict(
#             StatementStagingLine.objects.filter(row_identifier__in=row_ids).values_list(
#                 "row_identifier", "narration"
#             )
#         )

#     clusters_map: Dict[str, Dict[str, Any]] = {}

#     for entry in suspense_entries:
#         raw_narration = narration_map.get(entry.row_identifier, "")
#         pattern = extract_merchant_anchor(raw_narration)
#         amount = float(entry.debit) if entry.debit else 0.0

#         if pattern not in clusters_map:
#             clusters_map[pattern] = {
#                 "pattern": pattern,
#                 "count": 0,
#                 "total_amount": 0.0,
#                 "sample_descriptions": [],
#                 "transaction_ids": [],
#                 "items": [],
#             }

#         clusters_map[pattern]["count"] += 1
#         clusters_map[pattern]["total_amount"] += amount
#         clusters_map[pattern]["transaction_ids"].append(str(entry.id))

#         # Attach item payload for fine-grained selection in UI
#         clusters_map[pattern]["items"].append(
#             {
#                 "id": str(entry.id),
#                 "narration": raw_narration or f"Entry #{str(entry.id)[:8]}",
#                 "amount": amount,
#             }
#         )

#         if len(clusters_map[pattern]["sample_descriptions"]) < 3:
#             if (
#                 raw_narration
#                 and raw_narration not in clusters_map[pattern]["sample_descriptions"]
#             ):
#                 clusters_map[pattern]["sample_descriptions"].append(raw_narration)

#     return sorted(clusters_map.values(), key=lambda x: x["count"], reverse=True)


# def get_suspense_clusters2(target_subcategory="Suspense Account"):
#     # Fetch Node 99 entries matching target subcategory
#     entries = JournalEntry.objects.filter(
#         account_id=99,
#         evaluation_matrix_snapshot__resolved_subcategory=target_subcategory,
#     )

#     clusters_dict = {}

#     for entry in entries:
#         snapshot = entry.evaluation_matrix_snapshot or {}
#         # Extract vendor cluster key or fall back to narration/pattern
#         cluster_key = (
#             snapshot.get("vendor_cluster")
#             or snapshot.get("matched_pattern")
#             or "#UNCLUSTERED"
#         )

#         if cluster_key not in clusters_dict:
#             clusters_dict[cluster_key] = {
#                 "cluster_name": cluster_key,
#                 "total_outflow": 0.0,
#                 "total_inflow": 0.0,
#                 "total_selected_count": 0,
#                 "line_items": [],
#             }

#         # Determine flow direction based on Debit vs Credit
#         is_outflow = entry.debit > 0
#         amount = float(entry.debit if is_outflow else entry.credit)
#         direction = "OUTFLOW" if is_outflow else "INFLOW"
#         flag_color = "rose" if is_outflow else "green"

#         # Update cluster totals
#         if is_outflow:
#             clusters_dict[cluster_key]["total_outflow"] += amount
#         else:
#             clusters_dict[cluster_key]["total_inflow"] += amount

#         clusters_dict[cluster_key]["total_selected_count"] += 1

#         # Append enriched line item
#         clusters_dict[cluster_key]["line_items"].append(
#             {
#                 "id": str(entry.id),
#                 "row_identifier": entry.row_identifier,
#                 "transaction_date": str(entry.transaction_date),
#                 "narration": snapshot.get("narration", "N/A"),
#                 "amount": amount,
#                 "direction": direction,  # 'OUTFLOW' or 'INFLOW'
#                 "flag_color": flag_color,  # 'rose' or 'green'
#                 "debit": float(entry.debit),
#                 "credit": float(entry.credit),
#             }
#         )

#     return list(clusters_dict.values())


# def get_suspense_clusters(target_subcategory="Suspense Account"):
#     entries = JournalEntry.objects.filter(
#         account_id=99,
#         evaluation_matrix_snapshot__resolved_subcategory=target_subcategory,
#     )

#     clusters_dict = {}

#     for entry in entries:
#         snapshot = entry.evaluation_matrix_snapshot or {}

#         # 🟢 Guarantee a non-empty cluster pattern key
#         raw_pattern = (
#             snapshot.get("vendor_cluster")
#             or snapshot.get("matched_pattern")
#             or snapshot.get("narration")
#             or "GENERAL_SUSPENSE"
#         )
#         cluster_key = str(raw_pattern).strip().upper() or "GENERAL_SUSPENSE"

#         if cluster_key not in clusters_dict:
#             clusters_dict[cluster_key] = {
#                 "pattern": cluster_key,  # 👈 Crucial: Front-end looks for 'pattern'
#                 "count": 0,
#                 "total_amount": 0.0,
#                 "total_outflow": 0.0,
#                 "total_inflow": 0.0,
#                 "transaction_ids": [],  # 👈 Array of IDs
#                 "items": [],  # 👈 Detailed items list
#             }

#         is_outflow = entry.debit > 0
#         amount = float(entry.debit if is_outflow else entry.credit)
#         direction = "OUTFLOW" if is_outflow else "INFLOW"

#         cluster = clusters_dict[cluster_key]
#         cluster["count"] += 1
#         cluster["total_amount"] += amount
#         if is_outflow:
#             cluster["total_outflow"] += amount
#         else:
#             cluster["total_inflow"] += amount

#         entry_id_str = str(entry.id)
#         cluster["transaction_ids"].append(entry_id_str)

#         # Extract narration from snapshot or default string
#         narration_text = snapshot.get("narration") or f"Txn #{entry.row_identifier[:8]}"

#         cluster["items"].append(
#             {
#                 "id": entry_id_str,
#                 "row_identifier": entry.row_identifier,
#                 "narration": narration_text,
#                 "amount": amount,
#                 "direction": direction,
#                 "debit": float(entry.debit),
#                 "credit": float(entry.credit),
#             }
#         )

#     return list(clusters_dict.values())


# def classify_via_rules(raw_narration: str):
#     """
#     Evaluates raw narration text against active ClassificationRule patterns JSON lists.
#     """
#     if not raw_narration:
#         return None

#     narration_upper = raw_narration.upper()
#     active_rules = ClassificationRule.objects.filter(is_active=True).order_by(
#         "-priority"
#     )

#     for rule in active_rules:
#         # Handle empty/missing patterns gracefully
#         patterns_list = rule.patterns if isinstance(rule.patterns, list) else []

#         for pattern in patterns_list:
#             if pattern and pattern.strip().upper() in narration_upper:
#                 # Increment match count metric
#                 rule.match_count += 1
#                 rule.save(update_fields=["match_count"])

#                 return {
#                     "category": rule.target_category,
#                     "subcategory": rule.target_subcategory,
#                     "matched_pattern": pattern,
#                 }
#     return None


# def add_or_update_classification_rule(
#     category: str, subcategory: str, new_pattern: str
# ) -> bool:
#     # 🟢 Add guard for stringified None / UNDEFINED
#     if (
#         not new_pattern
#         or not str(new_pattern).strip()
#         or str(new_pattern).strip().upper() in ["NONE", "UNDEFINED"]
#     ):
#         return False

#     clean_pattern = str(new_pattern).strip().upper()

#     # Find existing active rule matching target taxonomy
#     rule = ClassificationRule.objects.filter(
#         target_category=category, target_subcategory=subcategory, is_active=True
#     ).first()

#     if rule:
#         # Append pattern into JSONField array if not present
#         existing_patterns = rule.patterns if isinstance(rule.patterns, list) else []
#         if clean_pattern not in existing_patterns:
#             existing_patterns.append(clean_pattern)
#             rule.patterns = existing_patterns
#             rule.save(update_fields=["patterns", "updated_at"])
#             return True
#         return False
#     else:
#         # Create new rule with clean JSON array
#         rule_name = f"{subcategory} ({clean_pattern})"
#         ClassificationRule.objects.create(
#             name=rule_name,
#             patterns=[clean_pattern],
#             rule_type="CONTAINS",
#             target_category=category,
#             target_subcategory=subcategory,
#             priority=10,
#             is_active=True,
#             created_from_manual_override=True,
#         )
#         return True


# def reclassify_and_learn_older(
#     transaction_ids: List[str],
#     target_category: str,
#     target_subcategory: str,
#     pattern: str = None,
#     save_rule: bool = True,
# ) -> Dict[str, Any]:
#     """
#     Applies bulk reclassification to specified transaction IDs and optionally
#     appends the pattern to the target ClassificationRule JSON pattern list.
#     """
#     if not transaction_ids:
#         return {
#             "status": "success",
#             "reclassified_count": 0,
#             "rule_created": False,
#             "pattern": pattern,
#         }

#     entries = list(JournalEntry.objects.filter(id__in=transaction_ids))

#     for entry in entries:
#         snapshot = entry.evaluation_matrix_snapshot or {}
#         snapshot["resolved_category"] = target_category
#         snapshot["resolved_subcategory"] = target_subcategory
#         snapshot["is_manual_override"] = True
#         if pattern:
#             snapshot["applied_pattern"] = pattern

#         entry.evaluation_matrix_snapshot = snapshot

#     # Bulk update for performance
#     JournalEntry.objects.bulk_update(entries, ["evaluation_matrix_snapshot"])

#     rule_saved = False
#     if save_rule and pattern:
#         rule_saved = add_or_update_classification_rule(
#             category=target_category,
#             subcategory=target_subcategory,
#             new_pattern=pattern,
#         )

#     return {
#         "status": "success",
#         "reclassified_count": len(entries),
#         "rule_created": rule_saved,
#         "pattern": pattern,
#     }


# def reclassify_and_learn(
#     transaction_ids: List[str],
#     target_category: str,
#     target_subcategory: str,
#     patterns: List[str] = None,
#     save_rule: bool = True,
# ) -> Dict[str, Any]:
#     if not transaction_ids:
#         return {"status": "success", "reclassified_count": 0, "rules_updated": False}

#     entries = list(JournalEntry.objects.filter(id__in=transaction_ids))

#     # 1. Bulk update evaluation matrix snapshot
#     for entry in entries:
#         snapshot = entry.evaluation_matrix_snapshot or {}
#         snapshot["resolved_category"] = target_category
#         snapshot["resolved_subcategory"] = target_subcategory
#         snapshot["is_manual_override"] = True
#         entry.evaluation_matrix_snapshot = snapshot

#     JournalEntry.objects.bulk_update(entries, ["evaluation_matrix_snapshot"])

#     # 2. Append ALL distinct patterns into ClassificationRule JSON array
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
