from datetime import datetime
import hashlib
import json
import re
from typing import Any, Dict, List, Optional
from django.db.models import Q
from django.utils import timezone

from tracker.classification.remarks_service import generate_cluster_pattern
from tracker.classification.utils.upiparser import parse_upi_narration
from tracker.models import (
    AccountingRule,
    ClassificationRule,
    JournalEntry,
    StatementStagingLine,
    TaxonomyTree,
)

# 🛡️ Centralized Banking & System Noise Keyword Blacklist
NOISE_KEYWORD_BLACKLIST = {
    "UPI",
    "NEFT",
    "RTGS",
    "IMPS",
    "POS",
    "ACH",
    "NFT",
    "TFR",
    "TRANSFER",
    "PAYMENT",
    "DR",
    "CR",
    "BANK",
    "INB",
    "INF",
    "BIL",
    "CLG",
    "CHQ",
    "CHEQUE",
    "CASH",
    "ATM",
    "DEBIT",
    "CREDIT",
    "NONE",
    "UNDEFINED",
    "GENERAL_OPERATING_EXPENSES",
    "UNCLASSIFIED",
    "SUSPENSE_ACCOUNT",
    # Bank Identifier Tokens (Prevent Over-Matching)
    "UTIB",
    "YESB",
    "FDRL",
    "ICIC",
    "HDFC",
    "SBIN",
    "BARB",
    "SIBL",
    "CNRB",
    "IBKL",
    "PUNB",
    "MAHB",
    "IDIB",
    "IOBA",
    "UBIN",
    "KKBK",
    # Location & Generic Noise
    "TECHNOPARK",
    "TRIVANDRUM",
    "KERALA",
    "INDIA",
    "BRANCH",
}

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

BANK_TOKENS = {
    "UPI",
    "YESB",
    "UTIB",
    "SIBL",
    "FDRL",
    "ICIC",
    "HDFC",
    "SBIN",
    "BARB",
    "CNRB",
    "IBKL",
    "PUNB",
    "MAHB",
    "PAYTMQR",
}


def normalize_for_search(text: str) -> str:
    """Strips underscores, spaces, dashes, colons, and punctuation for fuzzy matching.

    e.g., 'B_AIJU' -> 'BAIJU', 'PRAVEE N P' -> 'PRAVEENP'
    """
    if not text:
        return ""
    return re.sub(r"[^A-Z0-9]+", "", str(text).upper())


def extract_clean_payee_pattern(narration: str) -> str:
    """Extracts the true merchant/person payee name from raw bank narrations, bypassing bank handle prefixes, numeric reference codes, and location noise.

    Examples:
      - "UPI/YESB/09 1313127631/BINI RAJ N/GROCERIES" -> "BINI RAJ N"
      - "UPI/UTIB/50 3613972551/PADHAYAM FISH MART/UPI" -> "PADHAYAM FISH MART"
      - "POS TRN/ ID NO. (AZAD GROUP HOTELS TR)/PRCR/..." -> "AZAD GROUP HOTELS TR"
    """
    if not narration or not str(narration).strip():
        return ""

    text = str(narration).strip().upper()

    # 1. POS / ID NO bracket extraction e.g. POS TRN/ ID NO. (AZAD GROUP HOTELS TR)
    pos_match = re.search(r"\(([^)]+)\)", text)
    if pos_match:
        candidate = pos_match.group(1).strip()
        if len(candidate) >= 3 and not candidate.startswith("CIAL"):
            return candidate

    # 2. UPI slash-delimited token parsing
    if "UPI" in text or "/" in text:
        parts = [p.strip() for p in text.split("/") if p.strip()]

        candidates = []
        for part in parts:
            # Skip known bank handles and location noise
            if part in BANK_TOKENS or any(
                b in part
                for b in [
                    "TECHNOPARK",
                    "TRIVANDRUM",
                    "KERALA",
                    "INDIA",
                    "BRANCH",
                    "UPI",
                ]
            ):
                continue
            # Skip pure numeric strings or reference codes (e.g. "09 1313127631" or "50 3613972551")
            if re.match(r"^[\d\s]+$", part):
                continue
            # Skip short garbage tokens
            if len(part) < 3:
                continue
            candidates.append(part)

        if candidates:
            return candidates[0]

    return text[:30]


def get_suspense_clusters(
    target_subcategory="Suspense Account", account_id=None, search_query=None
):
    print("\n" + "=" * 80)
    print(
        f"[engine] START get_suspense_clusters(sub='{target_subcategory}',"
        f" account_id={account_id}, query='{search_query}')"
    )
    print("=" * 80)

    # 1. Base Query: Unclassified entries on Taxonomy Integration Node 99
    query = JournalEntry.objects.filter(account_id=99, is_reclassified=False)

    if target_subcategory == "Suspense Account":
        query = query.filter(is_reclassified=False)

    # Filter strictly by target_subcategory (e.g. General Operating Expenses)
    if (
        target_subcategory
        and target_subcategory.strip()
        and target_subcategory != "All"
    ):
        query = query.filter(
            evaluation_matrix_snapshot__resolved_subcategory=target_subcategory
        )

    # Scope Node 99 entries via matching row_identifiers if a specific bank account is provided
    if account_id and str(account_id) != "99":
        bank_row_ids = JournalEntry.objects.filter(account_id=account_id).values_list(
            "row_identifier", flat=True
        )
        query = query.filter(row_identifier__in=bank_row_ids)

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

        # Direction resolution based on credit vs debit values
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
        dynamic_display_text = (
            f"{direction_word} {target_subcategory} | {action_word}{ref_str} |"
            " Ingested via Staging"
        )

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
                "direction": "OUTFLOW" if is_outflow else "INFLOW",
                "transaction_date": str(entry.transaction_date),
                "remarks": item_remarks,
            }
        )

    sorted_clusters = sorted(
        clusters_map.values(), key=lambda c: c["count"], reverse=True
    )

    # Fuzzy normalized search filter
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
            f"[engine] Search query '{search_query}' (normalized:"
            f" '{norm_query}') filtered {len(sorted_clusters)} ->"
            f" {len(filtered_clusters)} clusters"
        )
        return filtered_clusters

    print(f"[engine] Total distinct clusters created: {len(sorted_clusters)}")
    return sorted_clusters


def classify_via_rules(raw_narration: str) -> Optional[Dict[str, str]]:
    """Evaluates raw narration text against active ClassificationRule patterns JSON lists."""
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


# def add_or_update_classification_rule(
#     category: str,
#     subcategory: str,
#     new_pattern: str,
#     entry_type: str = "Debit",
# ) -> bool:
#     """Appends a pattern into an existing ClassificationRule (read by Workbench / Tier 5) or creates a new active rule, enforcing noise blacklists and directional cash flow vectors."""
#     if not new_pattern or not str(new_pattern).strip():
#         return False

#     clean_pattern = str(new_pattern).strip().upper()

#     # 🛡️ GUARD 1: Noise Keyword & Short Pattern Blacklist Check
#     if clean_pattern in NOISE_KEYWORD_BLACKLIST or len(clean_pattern) < 3:
#         print(
#             "⚠️ Rejected unsafe/noise keyword for auto-learning:" f" '{clean_pattern}'"
#         )
#         return False

#     clean_entry_type = (
#         "Credit" if str(entry_type).strip().lower() == "credit" else "Debit"
#     )

#     # 🛡️ GUARD 2: Search existing active ClassificationRule matching target subcategory
#     existing_rule = ClassificationRule.objects.filter(
#         target_category=category,
#         target_subcategory=subcategory,
#         is_active=True,
#     ).first()

#     if existing_rule:
#         # Ensure patterns are parsed as a Python list (handles JSON string or list)
#         patterns = existing_rule.patterns or []
#         if isinstance(patterns, str):
#             try:
#                 patterns = json.loads(patterns)
#             except Exception:
#                 patterns = [patterns]

#         if clean_pattern not in patterns:
#             patterns.append(clean_pattern)
#             existing_rule.patterns = patterns
#             existing_rule.match_count = (existing_rule.match_count or 0) + 1
#             existing_rule.save(update_fields=["patterns", "match_count", "updated_at"])
#             return True
#         return False

#     else:
#         # 🛡️ GUARD 3: Create new active ClassificationRule entry
#         short_code = (
#             hashlib.md5(f"{subcategory}_{clean_pattern}".encode())
#             .hexdigest()[:6]
#             .upper()
#         )
#         rule_code = f"CR_{short_code}"

#         ClassificationRule.objects.create(
#             name=f"Learned: {subcategory} ({clean_pattern})",
#             rule_code=rule_code,
#             rule_type=clean_entry_type,
#             target_category=category,
#             target_subcategory=subcategory,
#             patterns=[clean_pattern],
#             priority=1,
#             is_active=True,
#             created_from_manual_override=True,
#             match_count=1,
#         )
#         return True


def add_or_update_classification_rule(
    category: str,
    subcategory: str,
    new_pattern: str,
    entry_type: str = "Debit",
) -> bool:
    """Appends a pattern into an existing ClassificationRule (read by Workbench / Tier 5)

    or creates a new active rule, enforcing noise blacklists and resolving the
    taxonomy foreign key.
    """
    if not new_pattern or not str(new_pattern).strip():
        return False

    clean_pattern = str(new_pattern).strip().upper()

    # 🛡️ GUARD 1: Noise Keyword & Short Pattern Blacklist Check
    if clean_pattern in NOISE_KEYWORD_BLACKLIST or len(clean_pattern) < 3:
        print(
            "⚠️ Rejected unsafe/noise keyword for auto-learning:" f" '{clean_pattern}'"
        )
        return False

    clean_entry_type = (
        "Credit" if str(entry_type).strip().lower() == "credit" else "Debit"
    )

    # 🔍 TAXONOMY RESOLUTION: Look up matching TaxonomyTree record using category & subcategory
    taxonomy_node = TaxonomyTree.objects.filter(
        category__iexact=category, subcategory__iexact=subcategory
    ).first()
    resolved_taxonomy = taxonomy_node if taxonomy_node else None

    # 🛡️ GUARD 2: Search existing active ClassificationRule matching target subcategory
    existing_rule = ClassificationRule.objects.filter(
        target_category=category,
        target_subcategory=subcategory,
        is_active=True,
    ).first()

    if existing_rule:
        patterns = existing_rule.patterns or []
        if isinstance(patterns, str):
            try:
                patterns = json.loads(patterns)
            except Exception:
                patterns = [patterns]

        updated_fields = ["patterns", "match_count", "updated_at"]

        if clean_pattern not in patterns:
            patterns.append(clean_pattern)
            existing_rule.patterns = patterns
            existing_rule.match_count = (existing_rule.match_count or 0) + 1

            # Backfill taxonomy if missing
            if not existing_rule.taxonomy and resolved_taxonomy:
                existing_rule.taxonomy = resolved_taxonomy
                updated_fields.append("taxonomy")

            existing_rule.save(update_fields=updated_fields)
            return True
        return False

    else:
        # 🛡️ GUARD 3: Create new active ClassificationRule entry with taxonomy populated
        short_code = (
            hashlib.md5(f"{subcategory}_{clean_pattern}".encode())
            .hexdigest()[:6]
            .upper()
        )
        rule_code = f"CR_{short_code}"

        ClassificationRule.objects.create(
            name=f"Learned: {subcategory} ({clean_pattern})",
            rule_code=rule_code,
            rule_type=clean_entry_type,
            target_category=category,
            target_subcategory=subcategory,
            patterns=[clean_pattern],
            priority=1,
            is_active=True,
            created_from_manual_override=True,
            match_count=1,
            taxonomy=resolved_taxonomy,  # Assigns the resolved TaxonomyTree instance
        )
        return True


def reclassify_and_learn(
    transaction_ids: List[str],
    target_category: str,
    target_subcategory: str,
    patterns: Optional[List[str]] = None,
    save_rule: bool = True,
) -> Dict[str, Any]:
    """Executes bulk reclassification for Node 99 records and learns new matching rules in ClassificationRule.

    Preserves payee metadata while updating target account names in remarks and
    enforcing directional cash flow vectors.
    """
    if not transaction_ids:
        return {"status": "success", "reclassified_count": 0, "rules_updated": False}

    # 1. Resolve row_identifiers from passed transaction_ids or row_identifiers
    target_row_ids = list(
        JournalEntry.objects.filter(
            Q(id__in=transaction_ids) | Q(row_identifier__in=transaction_ids)
        )
        .values_list("row_identifier", flat=True)
        .distinct()
    )

    if not target_row_ids:
        return {"status": "success", "reclassified_count": 0, "rules_updated": False}

    # 2. Fetch all target entries sitting in Node 99 matching those row_identifiers
    entries = list(
        JournalEntry.objects.filter(account_id=99, row_identifier__in=target_row_ids)
    )

    # 🛡️ VECTOR INFERENCE: Infer cash flow direction (Debit vs Credit)
    total_debit = sum(float(e.debit or 0) for e in entries)
    total_credit = sum(float(e.credit or 0) for e in entries)
    inferred_entry_type = "Credit" if total_credit > total_debit else "Debit"

    # Collect payee hints directly from entries in case raw patterns contain bank rail noise
    extracted_payees = []

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

            if payee and payee.strip():
                extracted_payees.append(payee.strip())

            amt = float(entry.debit or entry.credit or 0)
            ref_str = f" [Ref: {upi_ref}]" if upi_ref else ""
            action_word = (
                f"Paid ₹{amt:,.2f} to {payee}" if payee else f"Amount ₹{amt:,.2f}"
            )
            note_str = f" | Note: {user_note.strip()}" if user_note else ""

            updated_display_text = (
                f"{direction_word} {target_subcategory} |"
                f" {action_word}{ref_str}{note_str} | Reclassified via Workbench"
            )

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

    # 3. Save learned patterns into ClassificationRule
    rules_updated = False
    learned_patterns = []

    if save_rule:
        # Combine passed patterns with extracted payee metadata from entries
        candidates_to_process = list(patterns or [])
        for p_hint in extracted_payees:
            if p_hint not in candidates_to_process:
                candidates_to_process.append(p_hint)

        for p in candidates_to_process:
            if p and str(p).strip():
                # Sanitize pattern string using extractor to bypass bank rail noise
                clean_p = extract_clean_payee_pattern(p)

                if clean_p and clean_p not in learned_patterns:
                    updated = add_or_update_classification_rule(
                        category=target_category,
                        subcategory=target_subcategory,
                        new_pattern=clean_p,
                        entry_type=inferred_entry_type,
                    )
                    if updated:
                        rules_updated = True
                        learned_patterns.append(clean_p)

    return {
        "status": "success",
        "reclassified_count": len(entries),
        "entry_type_bound": inferred_entry_type,
        "rules_updated": rules_updated,
        "patterns_learned": learned_patterns,
    }


# # tracker/classification/engine.py

# import re
# from typing import List, Dict, Any, Optional
# from tracker.models import JournalEntry, StatementStagingLine, ClassificationRule
# from tracker.classification.remarks_service import generate_cluster_pattern
# from tracker.classification.utils.upiparser import parse_upi_narration
# from tracker.models import TaxonomyTree
# from datetime import datetime
# from django.utils import timezone
# from django.db.models import Q

# GENERIC_PATTERNS = {
#     "#GENERAL_OPERATING_EXPENSES",
#     "#GENERAL_OPERATING_EXPENSE",
#     "#SUSPENSE_ACCOUNT",
#     "#UNCLASSIFIED_OTHER",
#     "#SUSPENSE",
#     "#TRANSFER_NACH",
#     "GENERAL_OPERATING_EXPENSES",
#     "UNCLASSIFIED",
#     "TRANSFER_NACH",
#     "UNCLASSIFIED_OTHER",
#     "SUSPENSE_ACCOUNT",
#     "NACH",
#     "IMPS",
#     "KALLAMBALAM",
#     "POSTRN",
# }


# def normalize_for_search(text: str) -> str:
#     """
#     Strips underscores, spaces, dashes, colons, and punctuation for fuzzy matching.
#     e.g., 'B_AIJU' -> 'BAIJU', 'PRAVEE N P' -> 'PRAVEENP'
#     """
#     if not text:
#         return ""
#     return re.sub(r"[^A-Z0-9]+", "", str(text).upper())


# # def get_suspense_clusters(
# #     target_subcategory="Suspense Account", account_id=None, search_query=None
# # ):
# #     print(f"\n" + "=" * 80)
# #     print(
# #         f"[engine] START get_suspense_clusters(sub='{target_subcategory}', account_id={account_id}, query='{search_query}')"
# #     )
# #     print("=" * 80)

# #     query = JournalEntry.objects.filter(is_reclassified=False)
# #     if account_id:
# #         query = query.filter(account_id=account_id)
# #     else:
# #         query = query.filter(account_id=99)

# #     entries = list(query.order_by("-transaction_date"))
# #     print(f"[engine] Total unclassified entries fetched: {len(entries)}")

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

# #         # 🟢 STRICT DIRECTION RESOLUTION based on credit vs debit values
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

# #         # Force live re-parsing if pattern is missing or generic
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

# #         # 🟢 DIRECTIONAL WORDING GUARDRAILS
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
# #         dynamic_display_text = f"{direction_word} {target_subcategory} | {action_word}{ref_str} | Ingested via Staging"

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
# #                 "direction": (
# #                     "OUTFLOW" if is_outflow else "INFLOW"
# #                 ),  # 🟢 Strict direction
# #                 "transaction_date": str(entry.transaction_date),
# #                 "remarks": item_remarks,
# #             }
# #         )

# #     sorted_clusters = sorted(
# #         clusters_map.values(), key=lambda c: c["count"], reverse=True
# #     )

# #     # 🟢 FUZZY NORMALIZED SEARCH FILTER
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

# #             # Check pattern key, samples, or individual items inside cluster
# #             matches_pattern = norm_query in norm_pattern or norm_query in norm_samples
# #             matches_item = any(
# #                 norm_query in normalize_for_search(item.get("narration", ""))
# #                 or norm_query
# #                 in normalize_for_search(item.get("remarks", {}).get("payee", ""))
# #                 for item in cluster.get("items", [])
# #             )

# #             if matches_pattern or matches_item:
# #                 filtered_clusters.append(cluster)

# #         print(
# #             f"[engine] Search query '{search_query}' (normalized: '{norm_query}') filtered {len(sorted_clusters)} -> {len(filtered_clusters)} clusters"
# #         )
# #         return filtered_clusters

# #     print(f"[engine] Total distinct clusters created: {len(sorted_clusters)}")
# #     return sorted_clusters


# def get_suspense_clusters(
#     target_subcategory="Suspense Account", account_id=None, search_query=None
# ):
#     print(f"\n" + "=" * 80)
#     print(
#         f"[engine] START get_suspense_clusters(sub='{target_subcategory}', account_id={account_id}, query='{search_query}')"
#     )
#     print("=" * 80)

#     # 1. Base Query: Unclassified entries on Taxonomy Integration Node 99
#     query = JournalEntry.objects.filter(account_id=99, is_reclassified=False)

#     if target_subcategory == "Suspense Account":
#         query = query.filter(is_reclassified=False)

#         # 🟢 FIX 1: Filter strictly by target_subcategory
#     # if (
#     #     target_subcategory
#     #     and target_subcategory.strip()
#     #     and target_subcategory != "All"
#     # ):
#     #     query = query.filter(
#     #         evaluation_matrix_snapshot__resolved_subcategory=target_subcategory
#     #     )

#     # 🟢 FIX 1: Filter strictly by target_subcategory (e.g. General Operating Expenses)
#     # Checks JSON snapshot for resolved_subcategory matching target_subcategory
#     if (
#         target_subcategory
#         and target_subcategory.strip()
#         and target_subcategory != "All"
#     ):
#         query = query.filter(
#             evaluation_matrix_snapshot__resolved_subcategory=target_subcategory
#         )

#     # 🟢 FIX 2: If a specific Bank Account (e.g. account_id=5) is selected,
#     # scope Node 99 entries via matching row_identifiers from that bank account
#     if account_id and str(account_id) != "99":
#         bank_row_ids = JournalEntry.objects.filter(account_id=account_id).values_list(
#             "row_identifier", flat=True
#         )
#         query = query.filter(row_identifier__in=bank_row_ids)

#     entries = list(query.order_by("-transaction_date"))
#     print(f"[engine] Total unclassified entries fetched: {len(entries)}")

#     row_ids = [e.row_identifier for e in entries if e.row_identifier]
#     staging_map = {
#         s.row_identifier: s.narration
#         for s in StatementStagingLine.objects.filter(row_identifier__in=row_ids).only(
#             "row_identifier", "narration"
#         )
#     }

#     clusters_map = {}

#     for idx, entry in enumerate(entries, 1):
#         remarks = entry.remarks if isinstance(entry.remarks, dict) else {}
#         narration = staging_map.get(entry.row_identifier, "")
#         stored_pattern = remarks.get("pattern")

#         # 🟢 STRICT DIRECTION RESOLUTION based on credit vs debit values
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

#         parsed_meta = parse_upi_narration(narration) or {}
#         payee = parsed_meta.get("payee") or remarks.get("payee")
#         ref_no = parsed_meta.get("upi_ref") or remarks.get("upi_ref")

#         # Force live re-parsing if pattern is missing or generic
#         if not stored_pattern or stored_pattern in GENERIC_PATTERNS:
#             pattern = generate_cluster_pattern(
#                 narration=narration, remarks_data={"payee": payee}
#             )
#         else:
#             pattern = stored_pattern

#         if pattern not in clusters_map:
#             clusters_map[pattern] = {
#                 "pattern": pattern,
#                 "count": 0,
#                 "total_amount": 0.0,
#                 "total_inflow": 0.0,
#                 "total_outflow": 0.0,
#                 "sample_descriptions": [],
#                 "items": [],
#                 "transaction_ids": [],
#             }

#         # 🟢 DIRECTIONAL WORDING GUARDRAILS
#         direction_word = "By" if is_outflow else "To"

#         if is_outflow:
#             action_word = (
#                 f"Paid ₹{amount:,.2f} to {payee}"
#                 if payee
#                 else f"Outflow of ₹{amount:,.2f}"
#             )
#         else:
#             if pattern == "BANK_INTEREST" or (payee and "INTEREST" in payee.upper()):
#                 action_word = f"Received ₹{amount:,.2f} interest credit"
#             else:
#                 action_word = f"Received ₹{amount:,.2f} from {payee or 'Payee'}"

#         ref_str = f" [Ref: {ref_no}]" if ref_no else ""
#         dynamic_display_text = f"{direction_word} {target_subcategory} | {action_word}{ref_str} | Ingested via Staging"

#         item_remarks = {
#             **remarks,
#             "payee": payee,
#             "upi_ref": ref_no,
#             "display_text": dynamic_display_text,
#             "target_account_name": target_subcategory,
#             "directional_prefix": direction_word,
#         }

#         cluster = clusters_map[pattern]
#         cluster["count"] += 1
#         cluster["total_amount"] += amount

#         if is_outflow:
#             cluster["total_outflow"] += amount
#         else:
#             cluster["total_inflow"] += amount

#         cluster["transaction_ids"].append(str(entry.id))

#         if (
#             len(cluster["sample_descriptions"]) < 3
#             and dynamic_display_text not in cluster["sample_descriptions"]
#         ):
#             cluster["sample_descriptions"].append(dynamic_display_text)

#         cluster["items"].append(
#             {
#                 "id": str(entry.id),
#                 "narration": narration,
#                 "debit": debit_val,
#                 "credit": credit_val,
#                 "amount": amount,
#                 "direction": (
#                     "OUTFLOW" if is_outflow else "INFLOW"
#                 ),  # 🟢 Strict direction
#                 "transaction_date": str(entry.transaction_date),
#                 "remarks": item_remarks,
#             }
#         )

#     sorted_clusters = sorted(
#         clusters_map.values(), key=lambda c: c["count"], reverse=True
#     )

#     # 🟢 FUZZY NORMALIZED SEARCH FILTER
#     if search_query and str(search_query).strip():
#         norm_query = normalize_for_search(search_query)
#         filtered_clusters = []

#         for cluster in sorted_clusters:
#             norm_pattern = normalize_for_search(cluster["pattern"])
#             norm_samples = " ".join(
#                 [
#                     normalize_for_search(s)
#                     for s in cluster.get("sample_descriptions", [])
#                 ]
#             )

#             # Check pattern key, samples, or individual items inside cluster
#             matches_pattern = norm_query in norm_pattern or norm_query in norm_samples
#             matches_item = any(
#                 norm_query in normalize_for_search(item.get("narration", ""))
#                 or norm_query
#                 in normalize_for_search(item.get("remarks", {}).get("payee", ""))
#                 for item in cluster.get("items", [])
#             )

#             if matches_pattern or matches_item:
#                 filtered_clusters.append(cluster)

#         print(
#             f"[engine] Search query '{search_query}' (normalized: '{norm_query}') filtered {len(sorted_clusters)} -> {len(filtered_clusters)} clusters"
#         )
#         return filtered_clusters

#     print(f"[engine] Total distinct clusters created: {len(sorted_clusters)}")
#     return sorted_clusters


# def classify_via_rules(raw_narration: str) -> Optional[Dict[str, str]]:
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
#         patterns_list = rule.patterns if isinstance(rule.patterns, list) else []

#         for pattern in patterns_list:
#             if pattern and str(pattern).strip().upper() in narration_upper:
#                 rule.match_count += 1
#                 rule.save(update_fields=["match_count"])

#                 return {
#                     "category": rule.target_category,
#                     "subcategory": rule.target_subcategory,
#                     "matched_pattern": pattern,
#                 }
#     return None


# # def add_or_update_classification_rule(
# #     category: str, subcategory: str, new_pattern: str
# # ) -> bool:
# #     """
# #     Appends a pattern into an existing Taxonomy rule JSON list or creates a new active rule.
# #     """
# #     if (
# #         not new_pattern
# #         or not str(new_pattern).strip()
# #         or str(new_pattern).strip().upper() in ["NONE", "UNDEFINED"]
# #     ):
# #         return False

# #     clean_pattern = str(new_pattern).strip().upper()

# #     rule = ClassificationRule.objects.filter(
# #         target_category=category, target_subcategory=subcategory, is_active=True
# #     ).first()

# #     if rule:
# #         existing_patterns = rule.patterns if isinstance(rule.patterns, list) else []
# #         if clean_pattern not in existing_patterns:
# #             existing_patterns.append(clean_pattern)
# #             rule.patterns = existing_patterns
# #             rule.save(update_fields=["patterns", "updated_at"])
# #             return True
# #         return False
# #     else:
# #         rule_name = f"{subcategory} ({clean_pattern})"
# #         ClassificationRule.objects.create(
# #             name=rule_name,
# #             patterns=[clean_pattern],
# #             rule_type="CONTAINS",
# #             target_category=category,
# #             target_subcategory=subcategory,
# #             priority=10,
# #             is_active=True,
# #             created_from_manual_override=True,
# #         )
# #         return True

# def add_or_update_classification_rule(
#     category: str, subcategory: str, new_pattern: str, entry_type: str = "Debit"
# ) -> bool:
#   """Appends a pattern into an existing AccountingRule or creates a new active rule,

#   enforcing noise blacklists and directional cash flow vectors (Debit vs
#   Credit).
#   """
#   if not new_pattern or not str(new_pattern).strip():
#     return False

#   clean_pattern = str(new_pattern).strip().upper()

#   # 🛡️ GUARD 1: Noise Keyword Blacklist Check
#   if (
#       clean_pattern in NOISE_KEYWORD_BLACKLIST
#       or len(clean_pattern) < 3  # Prevent overly short 1-2 character tokens
#   ):
#     print(
#         f"⚠️ Rejected unsafe/noise keyword for auto-learning: '{clean_pattern}'"
#     )
#     return False

#   # Clean direction type
#   clean_entry_type = (
#       "Credit" if str(entry_type).strip().lower() == "credit" else "Debit"
#   )

#   # 🛡️ GUARD 2: Query AccountingRule (which Tiers 1-4 WIP Engine actually reads!)
#   existing_rule = AccountingRule.objects.filter(
#       entry_type=clean_entry_type,
#       rule_metadata__category=category,
#       rule_metadata__subcategory=subcategory,
#       is_active=True,
#   ).first()

#   if existing_rule:
#     tags = existing_rule.description_tags or []
#     if clean_pattern not in tags:
#       tags.append(clean_pattern)
#       existing_rule.description_tags = tags
#       existing_rule.save(update_fields=["description_tags", "updated_at"])
#       return True
#     return False
#   else:
#     # 🛡️ GUARD 3: Create new AccountingRule entry bound to vector
#     short_code = (
#         hashlib.md5(f"{subcategory}_{clean_pattern}".encode()).hexdigest()[:6].upper()
#     )
#     rule_code = f"LRN_{short_code}"  # Learned Rule prefix

#     AccountingRule.objects.create(
#         rule_code=rule_code,
#         rule_title=f"Learned: {subcategory} ({clean_pattern})",
#         entry_type=clean_entry_type,
#         rule_priority=5,  # High priority for user-learned rules
#         description_tags=[clean_pattern],
#         examples=[clean_pattern],
#         rule_metadata={"category": category, "subcategory": subcategory},
#         is_active=True,
#         notes="Auto-generated via Workbench Reclassification",
#     )
#     return True

# # def reclassify_and_learn(
# #     transaction_ids: List[str],
# #     target_category: str,
# #     target_subcategory: str,
# #     patterns: Optional[List[str]] = None,
# #     save_rule: bool = True,
# # ) -> Dict[str, Any]:
# #     """
# #     Executes bulk reclassification for Node 99 records and learns new matching rules.
# #     Preserves payee metadata while updating target account names in remarks.
# #     """
# #     if not transaction_ids:
# #         return {"status": "success", "reclassified_count": 0, "rules_updated": False}

# #     # 🟢 1. Resolve row_identifiers from passed transaction_ids or row_identifiers
# #     target_row_ids = list(
# #         JournalEntry.objects.filter(
# #             Q(id__in=transaction_ids) | Q(row_identifier__in=transaction_ids)
# #         )
# #         .values_list("row_identifier", flat=True)
# #         .distinct()
# #     )

# #     if not target_row_ids:
# #         return {"status": "success", "reclassified_count": 0, "rules_updated": False}

# #     # 🟢 2. Fetch all target entries sitting in Node 99 matching those row_identifiers
# #     entries = list(
# #         JournalEntry.objects.filter(account_id=99, row_identifier__in=target_row_ids)
# #     )

# #     target_label = f"{target_category} > {target_subcategory}"

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

# #         # Update structured JSON remarks
# #         if isinstance(entry.remarks, dict):
# #             existing_remarks = entry.remarks
# #             direction_word = existing_remarks.get("directional_prefix", "By")
# #             payee = existing_remarks.get("payee") or ""
# #             upi_ref = existing_remarks.get("upi_ref") or ""
# #             user_note = existing_remarks.get("user_note") or ""

# #             amt = float(entry.debit or entry.credit or 0)
# #             ref_str = f" [Ref: {upi_ref}]" if upi_ref else ""
# #             action_word = (
# #                 f"Paid ₹{amt:,.2f} to {payee}" if payee else f"Amount ₹{amt:,.2f}"
# #             )
# #             note_str = f" | Note: {user_note.strip()}" if user_note else ""

# #             updated_display_text = f"{direction_word} {target_subcategory} | {action_word}{ref_str}{note_str} | Reclassified via Workbench"

# #             entry.remarks = {
# #                 **existing_remarks,
# #                 "target_account_name": target_subcategory,
# #                 "display_text": updated_display_text,
# #                 "updated_at": timezone.now().isoformat(),
# #             }

# #     JournalEntry.objects.bulk_update(
# #         entries,
# #         [
# #             "evaluation_matrix_snapshot",
# #             "classification_status",
# #             "is_reclassified",
# #             "remarks",
# #         ],
# #     )

# #     # Append patterns into active Classification Rules
# #     rules_updated = False
# #     if save_rule and patterns:
# #         for p in patterns:
# #             if (
# #                 p
# #                 and str(p).strip()
# #                 and str(p).strip().upper() not in ["NONE", "UNDEFINED"]
# #             ):
# #                 updated = add_or_update_classification_rule(
# #                     category=target_category,
# #                     subcategory=target_subcategory,
# #                     new_pattern=str(p).strip().upper(),
# #                 )
# #                 if updated:
# #                     rules_updated = True

# #     return {
# #         "status": "success",
# #         "reclassified_count": len(entries),
# #         "rules_updated": rules_updated,
# #         "patterns_learned": patterns or [],
# #     }
