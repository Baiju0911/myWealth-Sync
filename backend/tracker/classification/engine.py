import re
from typing import List, Dict, Any
from tracker.models import JournalEntry, StatementStagingLine, ClassificationRule

# Common corporate / legal entity suffixes to strip for clean grouping
LEGAL_SUFFIXES = (
    r"\b(LIMITED|LTD|PVT|PRIVATE|INCORPORATED|INC|CORP|CORPORATION|SERVICES|SERVICE)\b"
)

# Honorifics & salutation prefixes to strip from payee names
SALUTATIONS = r"^(MR|MRS|MS|DR|SHRI|SMT|M/S|MS)\b\s*"


def extract_merchant_anchor(description: str) -> str:
    if not description or str(description).strip() == "":
        return "UNCLASSIFIED_OTHER"

    raw_str = str(description).strip().upper()

    # 🟢 1. Replace internal slashes in business prefixes like "M/S." or "M/S " -> "MS "
    # This prevents 'M/S.' from breaking the UPI slash index alignment!
    normalized_str = re.sub(r"\bM/S\.?\s*", "MS ", raw_str)

    # 🟢 2. Extract segment between 3rd and 4th slash in UPI narrations
    match = re.search(r"^UPI/[^/]+/[^/]+/([^/]+)/", normalized_str)

    if match:
        vendor_raw = match.group(1).strip()

        # Remove 'MS ' prefix if present
        vendor_clean = re.sub(r"^MS\s+", "", vendor_raw)

        # Strip store/terminal codes like "C194 ", "S102 "
        vendor_clean = re.sub(r"^[A-Z]\d+\s*", "", vendor_clean)

        # Remove non-alphanumeric characters (keep spaces)
        vendor_clean = re.sub(r"[^A-Z0-9\s]", " ", vendor_clean)

        # Strip corporate suffixes (LIMITED, LTD, PVT, etc.)
        legal_suffixes = r"\b(LIMITED|LTD|PVT|PRIVATE|INCORPORATED|INC|CORP|SERVICES)\b"
        vendor_clean = re.sub(legal_suffixes, "", vendor_clean)

        # Strip salutations (MR, MRS, DR, MS, etc.)
        salutations = r"^(MR|MRS|MS|DR|SHRI|SMT)\b\s*"
        vendor_clean = re.sub(salutations, "", vendor_clean).strip()

        # Collapse multiple spaces
        vendor_clean = re.sub(r"\s+", " ", vendor_clean).strip()

        # Specific alias unification
        if "SWIGGY" in vendor_clean:
            return "SWIGGY"
        if "PARKING" in vendor_clean or "PARKINGBOOTH" in vendor_clean:
            return "PARKING BOOTH"

        if len(vendor_clean) >= 3:
            return vendor_clean

    # Fallback for non-UPI or non-standard narrations
    return "UNCLASSIFIED_OTHER"


def get_suspense_clusters1() -> List[Dict[str, Any]]:
    """
    Queries debit entries for Suspense Account, joins raw narrations from
    StatementStagingLine via row_identifier, and groups them into merchant clusters.
    """
    # 1. Fetch Suspense Account debit entries (> 0 to prevent double counting legs)
    suspense_entries = JournalEntry.objects.filter(
        evaluation_matrix_snapshot__resolved_subcategory="Suspense Account", debit__gt=0
    )

    # 2. Extract row_identifiers to do a single efficient bulk lookup in StatementStagingLine
    row_ids = [e.row_identifier for e in suspense_entries if e.row_identifier]

    narration_map = {}
    if row_ids:
        # Build dictionary map: { row_identifier: narration }
        narration_map = dict(
            StatementStagingLine.objects.filter(row_identifier__in=row_ids).values_list(
                "row_identifier", "narration"
            )
        )

    clusters_map: Dict[str, Dict[str, Any]] = {}

    for entry in suspense_entries:
        # Pull raw bank text from the staging line mapping
        raw_narration = narration_map.get(entry.row_identifier, "")

        # Extract merchant pattern anchor
        pattern = extract_merchant_anchor(raw_narration)
        amount = float(entry.debit) if entry.debit else 0.0

        if pattern not in clusters_map:
            clusters_map[pattern] = {
                "pattern": pattern,
                "count": 0,
                "total_amount": 0.0,
                "sample_descriptions": [],
                "transaction_ids": [],
            }

        clusters_map[pattern]["count"] += 1
        clusters_map[pattern]["total_amount"] += amount
        clusters_map[pattern]["transaction_ids"].append(str(entry.id))

        # Keep up to 3 real narration previews
        desc_preview = raw_narration if raw_narration else f"Entry #{str(entry.id)[:8]}"
        if len(clusters_map[pattern]["sample_descriptions"]) < 3:
            if desc_preview not in clusters_map[pattern]["sample_descriptions"]:
                clusters_map[pattern]["sample_descriptions"].append(desc_preview)

    # Sort clusters by volume count (highest transaction count first)
    return sorted(clusters_map.values(), key=lambda x: x["count"], reverse=True)


def get_suspense_clusters2(
    target_subcategory: str = "Suspense Account",
) -> List[Dict[str, Any]]:
    """
    Queries debit entries for any target subcategory (e.g. 'Suspense Account', 'Food & Dining', 'Groceries'),
    joins raw narrations, and groups them into merchant clusters.
    """
    # 🟢 Filter dynamically by target_subcategory
    suspense_entries = JournalEntry.objects.filter(
        evaluation_matrix_snapshot__resolved_subcategory=target_subcategory, debit__gt=0
    )

    row_ids = [e.row_identifier for e in suspense_entries if e.row_identifier]

    narration_map = {}
    if row_ids:
        narration_map = dict(
            StatementStagingLine.objects.filter(row_identifier__in=row_ids).values_list(
                "row_identifier", "narration"
            )
        )

    clusters_map: Dict[str, Dict[str, Any]] = {}

    for entry in suspense_entries:
        raw_narration = narration_map.get(entry.row_identifier, "")
        pattern = extract_merchant_anchor(raw_narration)
        amount = float(entry.debit) if entry.debit else 0.0

        if pattern not in clusters_map:
            clusters_map[pattern] = {
                "pattern": pattern,
                "count": 0,
                "total_amount": 0.0,
                "sample_descriptions": [],
                "transaction_ids": [],
            }

        clusters_map[pattern]["count"] += 1
        clusters_map[pattern]["total_amount"] += amount
        clusters_map[pattern]["transaction_ids"].append(str(entry.id))

        desc_preview = raw_narration if raw_narration else f"Entry #{str(entry.id)[:8]}"
        if len(clusters_map[pattern]["sample_descriptions"]) < 3:
            if desc_preview not in clusters_map[pattern]["sample_descriptions"]:
                clusters_map[pattern]["sample_descriptions"].append(desc_preview)

    return sorted(clusters_map.values(), key=lambda x: x["count"], reverse=True)


def get_suspense_clusters(
    target_subcategory: str = "Suspense Account",
) -> List[Dict[str, Any]]:
    suspense_entries = JournalEntry.objects.filter(
        evaluation_matrix_snapshot__resolved_subcategory=target_subcategory, debit__gt=0
    )

    row_ids = [e.row_identifier for e in suspense_entries if e.row_identifier]

    narration_map = {}
    if row_ids:
        narration_map = dict(
            StatementStagingLine.objects.filter(row_identifier__in=row_ids).values_list(
                "row_identifier", "narration"
            )
        )

    clusters_map: Dict[str, Dict[str, Any]] = {}

    for entry in suspense_entries:
        raw_narration = narration_map.get(entry.row_identifier, "")
        pattern = extract_merchant_anchor(raw_narration)
        amount = float(entry.debit) if entry.debit else 0.0

        if pattern not in clusters_map:
            clusters_map[pattern] = {
                "pattern": pattern,
                "count": 0,
                "total_amount": 0.0,
                "sample_descriptions": [],
                "transaction_ids": [],
                "items": [],  # 🟢 Added structured item array
            }

        clusters_map[pattern]["count"] += 1
        clusters_map[pattern]["total_amount"] += amount
        clusters_map[pattern]["transaction_ids"].append(str(entry.id))

        # Attach item payload for fine-grained selection
        clusters_map[pattern]["items"].append(
            {
                "id": str(entry.id),
                "narration": raw_narration or f"Entry #{str(entry.id)[:8]}",
                "amount": amount,
            }
        )

        if len(clusters_map[pattern]["sample_descriptions"]) < 3:
            if raw_narration not in clusters_map[pattern]["sample_descriptions"]:
                clusters_map[pattern]["sample_descriptions"].append(raw_narration)

    return sorted(clusters_map.values(), key=lambda x: x["count"], reverse=True)


def reclassify_and_learn(
    transaction_ids: List[str],
    target_category: str,
    target_subcategory: str,
    pattern: str = None,
    save_rule: bool = True,
) -> Dict[str, Any]:
    """
    Applies bulk reclassification to specified transaction IDs and optionally
    saves a new rule to the ClassificationRule table.
    """
    entries = JournalEntry.objects.filter(id__in=transaction_ids)
    updated_count = 0

    for entry in entries:
        snapshot = entry.evaluation_matrix_snapshot or {}
        snapshot["resolved_category"] = target_category
        snapshot["resolved_subcategory"] = target_subcategory
        snapshot["is_manual_override"] = True
        if pattern:
            snapshot["applied_pattern"] = pattern

        entry.evaluation_matrix_snapshot = snapshot
        entry.save(update_fields=["evaluation_matrix_snapshot"])
        updated_count += 1

    rule_created = False
    if save_rule and pattern and pattern != "UNCLASSIFIED_OTHER":
        rule, created = ClassificationRule.objects.update_or_create(
            pattern=pattern,
            defaults={
                "target_category": target_category,
                "target_subcategory": target_subcategory,
                "is_active": True,
            },
        )
        rule_created = created

    return {
        "status": "success",
        "reclassified_count": updated_count,
        "rule_created": rule_created,
        "pattern": pattern,
    }
