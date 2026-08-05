from datetime import datetime
import hashlib
import json
import re
from typing import Any, Dict, List, Optional
from collections import Counter

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
from tracker.constants import (
    NOISE_KEYWORD_BLACKLIST,
    GENERIC_IGNORE_PATTERNS,
    GENERIC_PATTERNS,
    KNOWN_MERCHANTS,
    RULE_SAFETY_BLACKLIST,
)

GENERIC_NOISE_TOKENS = NOISE_KEYWORD_BLACKLIST


def normalize_for_search(text: str) -> str:
    """Strips underscores, spaces, dashes, colons, and punctuation for fuzzy matching."""
    if not text:
        return ""
    return re.sub(r"[^A-Z0-9]+", "", str(text).upper())


def normalize_condensed(text: str) -> str:
    """Strips all non-alphanumeric characters AND spaces for fuzzy boundary evaluation."""
    if not text:
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(text).upper())


def extract_meaningful_tokens(text: str) -> list[str]:
    """
    Cleans raw narration, respects slashes/delimiters, strips bank noise/UPI hashes,
    and filters out blacklisted UPI/Intent keywords.
    """
    if not text:
        return []

    raw_str = str(text).upper().strip()

    # 1. Clean out known UPI noise patterns explicitly before splitting
    raw_str = re.sub(r"\bNO\s+REMARKS?\b", "", raw_str)
    raw_str = re.sub(r"\bPAYTMQR[A-Z0-9]*\b", "", raw_str)
    raw_str = re.sub(r"\bUPI[A-Z0-9]{10,}\b", "", raw_str)

    # 2. Treat slashes, dashes, @, and non-alphanumerics as strict delimiters
    delimiters_cleaned = re.sub(r"[^A-Z0-9]", " ", raw_str)
    raw_tokens = delimiters_cleaned.split()

    filtered_tokens = []
    for token in raw_tokens:
        # Filter out numbers, long hashes, and blacklisted noise keywords
        if token.isdigit() or len(token) > 25:
            continue
        if token in NOISE_KEYWORD_BLACKLIST:
            continue
        filtered_tokens.append(token)

    return filtered_tokens


def match_multi_tokens(
    narration: str, pattern: str, min_required_tokens: int = 2
) -> bool:
    """
    Validates if narration matches rule pattern tokens.
    Requires at least `min_required_tokens` AND all pattern tokens to be present.
    """
    if not narration or not pattern:
        return False

    narration_tokens = set(extract_meaningful_tokens(narration))
    pattern_tokens = set(extract_meaningful_tokens(pattern))

    if not pattern_tokens:
        return False

    if len(pattern_tokens) < min_required_tokens:
        condensed_narration = normalize_condensed(narration)
        condensed_pattern = normalize_condensed(pattern)
        return len(condensed_pattern) >= 6 and condensed_pattern in condensed_narration

    if pattern_tokens.issubset(narration_tokens):
        return True

    condensed_narration = normalize_condensed(narration)
    condensed_pattern = normalize_condensed(pattern)

    return len(condensed_pattern) >= 6 and condensed_pattern in condensed_narration


# def extract_clean_payee_pattern(narration: str) -> str:
#     """Extracts true merchant/person payee name, stripping reference noise and slashes."""
#     if not narration or not str(narration).strip():
#         return ""

#     text = str(narration).strip().upper()

#     # POS bracket extraction e.g. POS TRN/ ID NO. (AZAD GROUP HOTELS TR)
#     pos_match = re.search(r"\(([^)]+)\)", text)
#     if pos_match:
#         candidate = pos_match.group(1).strip()
#         if len(candidate) >= 3 and not candidate.startswith("CIAL"):
#             return candidate

#     tokens = extract_meaningful_tokens(text)
#     if tokens:
#         return " ".join(tokens[:3])  # Top 3 meaningful tokens form clean payee name

#     return text[:30]


def extract_clean_payee_pattern(narration: str) -> str:
    """Extracts true merchant/person payee name, stripping reference noise and slashes."""
    if not narration or not str(narration).strip():
        return ""

    text = str(narration).strip().upper()

    # 1. POS bracket extraction e.g. POS TRN/ ID NO. (AZAD GROUP HOTELS TR)
    pos_match = re.search(r"\(([^)]+)\)", text)
    if pos_match:
        candidate = pos_match.group(1).strip()
        if len(candidate) >= 3 and not candidate.startswith("CIAL"):
            return candidate

    tokens = extract_meaningful_tokens(text)
    if not tokens:
        return text[:30]

    for token in tokens:
        if token in KNOWN_MERCHANTS:
            return token  # 🎯 Returns clean "ZOMATO" or "BLINKIT" immediately!

    # 3. Fallback: Take top tokens but ignore trailing person names/noise if merchant/action word present
    clean_tokens = tokens[:2] if len(tokens) >= 2 else tokens
    return " ".join(clean_tokens)


def get_suspense_clusters(
    target_subcategory="Suspense Account",
    account_id=None,
    search_query=None,
    include_cleared=False,
):
    print("\n" + "=" * 80)
    print(
        f"[engine] START get_suspense_clusters(sub='{target_subcategory}',"
        f" account_id={account_id}, query='{search_query}', include_cleared={include_cleared})"
    )
    print("=" * 80)

    if not include_cleared:
        query = JournalEntry.objects.filter(account_id=99, is_reclassified=False)
        if target_subcategory and target_subcategory.strip() not in [
            "Suspense Account",
            "All",
        ]:
            query = query.filter(
                evaluation_matrix_snapshot__resolved_subcategory=target_subcategory
            )
    else:
        query = JournalEntry.objects.filter(account_id=99)
        if target_subcategory and target_subcategory.strip() not in [
            "Suspense Account",
            "All",
        ]:
            query = query.filter(
                evaluation_matrix_snapshot__resolved_subcategory=target_subcategory
            )

    if account_id and str(account_id) != "99":
        bank_row_ids = JournalEntry.objects.filter(account_id=account_id).values_list(
            "row_identifier", flat=True
        )
        query = query.filter(row_identifier__in=bank_row_ids)

    entries = list(query.order_by("-transaction_date"))
    print(f"[engine] Total entries fetched: {len(entries)}")

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

        return filtered_clusters

    print(f"[engine] Total distinct clusters created: {len(sorted_clusters)}")
    return sorted_clusters


def get_clean_patterns(rule) -> list[str]:
    """Retrieves clean pattern list directly from model or dict representation."""
    if hasattr(rule, "get_patterns") and callable(rule.get_patterns):
        return rule.get_patterns()

    patterns = (
        rule.get("patterns", [])
        if isinstance(rule, dict)
        else getattr(rule, "patterns", [])
    )

    if isinstance(patterns, list):
        return [str(p).strip() for p in patterns if p and str(p).strip()]

    if isinstance(patterns, str):
        try:
            parsed = json.loads(patterns)
            if isinstance(parsed, list):
                return [str(p).strip() for p in parsed if p and str(p).strip()]
        except json.JSONDecodeError:
            return [patterns.strip()]

    return []


def classify_via_rules(
    raw_narration: str, is_debit: bool = True
) -> Optional[Dict[str, str]]:
    """
    Evaluates raw narration text against active ClassificationRule patterns
    using model pattern retrieval and strict multi-token matching.
    """
    if not raw_narration or not str(raw_narration).strip():
        return None

    target_rule_type = "Debit" if is_debit else "Credit"

    active_rules = ClassificationRule.objects.filter(
        is_active=True, rule_type=target_rule_type
    ).order_by("-priority")

    for rule in active_rules:
        patterns_list = (
            rule.get_patterns()
            if hasattr(rule, "get_patterns")
            else get_clean_patterns(rule)
        )

        for pattern in patterns_list:
            if match_multi_tokens(raw_narration, pattern):
                rule.match_count = (rule.match_count or 0) + 1
                rule.save(update_fields=["match_count", "updated_at"])

                return {
                    "category": rule.target_category,
                    "subcategory": rule.target_subcategory,
                    "matched_pattern": pattern,
                    "rule_code": rule.rule_code,
                    "rule_type": rule.rule_type,
                }
    return None


def generate_strict_multitoken_pattern(narration_list: list[str]) -> list[str]:
    """
    Extracts tokens present in the majority (>= 80%) of selected narrations,
    filtering out noise words and preserving natural word order.
    """
    if not narration_list:
        return []

    token_sequences = [extract_meaningful_tokens(n) for n in narration_list if n]
    if not token_sequences:
        return []

    token_counts = Counter()
    for seq in token_sequences:
        for token in set(seq):
            if token not in NOISE_KEYWORD_BLACKLIST:
                token_counts[token] += 1

    total_rows = len(token_sequences)
    threshold = max(1, int(total_rows * 0.8))

    majority_tokens_set = {
        token for token, count in token_counts.items() if count >= threshold
    }

    ordered_tokens = []
    first_sample_tokens = token_sequences[0]

    for token in first_sample_tokens:
        if token in majority_tokens_set and token not in ordered_tokens:
            ordered_tokens.append(token)

    for token in majority_tokens_set:
        if token not in ordered_tokens:
            ordered_tokens.append(token)

    return ordered_tokens


# def add_or_update_classification_rule(
#     category: str,
#     subcategory: str,
#     new_pattern: str,
#     entry_type: str = "Debit",
# ) -> bool:
#     """Appends pattern into an existing ClassificationRule or creates a new active rule."""
#     if not new_pattern or not str(new_pattern).strip():
#         return False

#     # Clean multi-word string into pure meaningful tokens
#     raw_tokens = extract_meaningful_tokens(new_pattern)
#     clean_tokens = [t for t in raw_tokens if t not in NOISE_KEYWORD_BLACKLIST]

#     if not clean_tokens:
#         print(f"⚠️ Rejected unsafe/noise pattern for auto-learning: '{new_pattern}'")
#         return False

#     clean_pattern = " ".join(clean_tokens).upper()

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
#         patterns = get_clean_patterns(existing_rule)
#         updated_fields = ["patterns", "match_count", "updated_at"]

#         if clean_pattern not in patterns:
#             patterns.append(clean_pattern)
#             existing_rule.patterns = patterns
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


def add_or_update_classification_rule(
    category: str,
    subcategory: str,
    new_pattern: str,
    entry_type: str = "Debit",
) -> bool:
    """
    Appends pattern into an existing ClassificationRule or creates a new active rule.
    Guards against generic single-word wildcards using centralized NOISE_KEYWORD_BLACKLIST.
    """
    if not new_pattern or not str(new_pattern).strip():
        return False

    # 1. Clean multi-word string into pure meaningful tokens
    raw_tokens = extract_meaningful_tokens(new_pattern)
    clean_tokens = [t for t in raw_tokens if t not in NOISE_KEYWORD_BLACKLIST]

    if not clean_tokens:
        print(f"⚠️ Rejected noise pattern: '{new_pattern}'")
        return False

    # 2. Generic Structural Protection (No hardcoded names!)
    if len(clean_tokens) == 1:
        single_token = clean_tokens[0].upper()
        # Single words MUST be at least 7 chars long to avoid general wildcard leaks
        if len(single_token) < 7:
            print(f"⚠️ Rejected unsafe short single-token pattern: '{single_token}'")
            return False

    clean_pattern = " ".join(clean_tokens).upper()
    clean_entry_type = (
        "Credit" if str(entry_type).strip().lower() == "credit" else "Debit"
    )

    taxonomy_node = TaxonomyTree.objects.filter(
        category__iexact=category, subcategory__iexact=subcategory
    ).first()
    resolved_taxonomy = taxonomy_node if taxonomy_node else None

    existing_rule = ClassificationRule.objects.filter(
        target_category=category,
        target_subcategory=subcategory,
        rule_type=clean_entry_type,
        is_active=True,
    ).first()

    if existing_rule:
        patterns = get_clean_patterns(existing_rule)
        updated_fields = ["patterns", "match_count", "updated_at"]

        if clean_pattern not in patterns:
            patterns.append(clean_pattern)
            existing_rule.patterns = patterns
            existing_rule.match_count = (existing_rule.match_count or 0) + 1

            if not existing_rule.taxonomy and resolved_taxonomy:
                existing_rule.taxonomy = resolved_taxonomy
                updated_fields.append("taxonomy")

            existing_rule.save(update_fields=updated_fields)
            print(
                f"✅ Appended clean pattern '{clean_pattern}' to existing rule {existing_rule.rule_code}"
            )
            return True
        return False

    else:
        vector_prefix = "DE" if clean_entry_type == "Debit" else "CR"
        hash_input = f"{subcategory}_{clean_pattern}_{clean_entry_type}".upper()
        short_code = hashlib.md5(hash_input.encode()).hexdigest()[:6].upper()
        rule_code = f"CR_{vector_prefix}_{short_code}"

        ClassificationRule.objects.create(
            name=f"Learned ({clean_entry_type}): {subcategory} ({clean_pattern})",
            rule_code=rule_code,
            rule_type=clean_entry_type,
            target_category=category,
            target_subcategory=subcategory,
            patterns=[clean_pattern],
            priority=1,
            is_active=True,
            created_from_manual_override=True,
            match_count=1,
            taxonomy=resolved_taxonomy,
        )
        print(
            f"✅ Created new distinct rule {rule_code} with clean pattern '{clean_pattern}'"
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
    Executes bulk reclassification for Node 99 records and learns clean,
    multi-crore-safe matching rules without token pollution.
    """
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

        direction_word = remarks_dict.get("directional_prefix", "By")
        payee = remarks_dict.get("payee") or ""
        upi_ref = remarks_dict.get("upi_ref") or ""
        user_note = remarks_dict.get("user_note") or ""

        clean_payee = extract_clean_payee_pattern(payee or narration_text) or "GENERIC"
        if clean_payee not in payee_groups:
            payee_groups[clean_payee] = []
        if narration_text:
            payee_groups[clean_payee].append(narration_text)

        amt = float(entry.debit or entry.credit or 0)
        ref_str = f" [Ref: {upi_ref}]" if upi_ref else ""
        action_word = f"Paid ₹{amt:,.2f} to {payee}" if payee else f"Amount ₹{amt:,.2f}"
        note_str = f" | Note: {user_note.strip()}" if user_note else ""

        updated_display_text = (
            f"{direction_word} {target_subcategory} |"
            f" {action_word}{ref_str}{note_str} | Reclassified via Workbench"
        )

        entry.remarks = {
            **remarks_dict,
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

    rules_updated = False
    learned_patterns = []

    if save_rule:
        print("\n" + "🔍" * 40)
        print(f"[ENGINE DEBUG] Learning Rules for Subcategory: '{target_subcategory}'")

        # -------------------------------------------------------------------------
        # PATH A: Explicit User Patterns Passed from Frontend UI (Highest Priority)
        # -------------------------------------------------------------------------
        if patterns and isinstance(patterns, list) and len(patterns) > 0:
            print(f"[ENGINE DEBUG] Using Explicit User Patterns: {patterns}")
            for user_p in patterns:
                clean_user_p = str(user_p).strip().upper()
                if len(clean_user_p) >= 3 and clean_user_p not in RULE_SAFETY_BLACKLIST:
                    updated = add_or_update_classification_rule(
                        category=target_category,
                        subcategory=target_subcategory,
                        new_pattern=clean_user_p,
                        entry_type=inferred_entry_type,
                    )
                    if updated:
                        rules_updated = True
                        learned_patterns.append(clean_user_p)

        # -------------------------------------------------------------------------
        # PATH B: Controlled Auto-Extraction with Strict Safety Guardrails
        # -------------------------------------------------------------------------
        else:
            print(
                f"[ENGINE DEBUG] Grouped {len(entries)} items into {len(payee_groups)} distinct payee clusters:"
            )

            for payee_key, group_narrations in payee_groups.items():
                common_tokens = generate_strict_multitoken_pattern(group_narrations)

                # Filter out numbers, blacklist words, and generic city/store names
                safe_tokens = [
                    t
                    for t in common_tokens
                    if not re.search(r"\d", t)
                    and t.upper() not in NOISE_KEYWORD_BLACKLIST
                    and t.upper() not in RULE_SAFETY_BLACKLIST
                    and len(t) > 2
                ]

                print(
                    f"   --> Cluster '{payee_key}': Extracted Safe Tokens = {safe_tokens}"
                )

                if safe_tokens:
                    # Cap at max 2 anchor tokens (e.g. "SKECHERS", "LULU PARKING")
                    # Never allow 8-word concatenated blobs!
                    capped_tokens = safe_tokens[:2]
                    compound_pattern = " ".join(capped_tokens)

                    # Only proceed if pattern contains at least one non-generic merchant word
                    if len(compound_pattern) >= 3:
                        updated = add_or_update_classification_rule(
                            category=target_category,
                            subcategory=target_subcategory,
                            new_pattern=compound_pattern,
                            entry_type=inferred_entry_type,
                        )
                        if updated:
                            rules_updated = True
                            learned_patterns.append(compound_pattern)

        print("🔍" * 40 + "\n")

    return {
        "status": "success",
        "reclassified_count": len(entries),
        "entry_type_bound": inferred_entry_type,
        "rules_updated": rules_updated,
        "patterns_learned": learned_patterns,
    }


# def reclassify_and_learn(
#     transaction_ids: List[str],
#     target_category: str,
#     target_subcategory: str,
#     patterns: Optional[List[str]] = None,
#     save_rule: bool = True,
# ) -> Dict[str, Any]:
#     """
#     Executes bulk reclassification for Node 99 records and learns new distinct matching rules
#     by auto-grouping selected narrations into individual payee clusters.
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
#         print("\n" + "🔍" * 40)
#         print(f"[ENGINE DEBUG] Learning Rules for Subcategory: '{target_subcategory}'")
#         print(
#             f"[ENGINE DEBUG] Grouped {len(entries)} items into {len(payee_groups)} distinct payee clusters:"
#         )

#         for payee_key, group_narrations in payee_groups.items():
#             common_tokens = generate_strict_multitoken_pattern(group_narrations)
#             common_tokens = [
#                 t
#                 for t in common_tokens
#                 if not re.search(r"\d", t) and t not in NOISE_KEYWORD_BLACKLIST
#             ]

#             if len(common_tokens) >= 3:
#                 filtered_tokens = [t for t in common_tokens if len(t) > 1]
#                 if len(filtered_tokens) >= 2:
#                     common_tokens = filtered_tokens

#             print(f"  --> Cluster '{payee_key}': Extracted Tokens = {common_tokens}")

#             if len(common_tokens) >= 2:
#                 compound_pattern = " ".join(common_tokens)
#                 updated = add_or_update_classification_rule(
#                     category=target_category,
#                     subcategory=target_subcategory,
#                     new_pattern=compound_pattern,
#                     entry_type=inferred_entry_type,
#                 )
#                 if updated:
#                     rules_updated = True
#                     learned_patterns.append(compound_pattern)
#             else:
#                 clean_p = extract_clean_payee_pattern(payee_key)
#                 clean_p_tokens = [
#                     t
#                     for t in extract_meaningful_tokens(clean_p)
#                     if t not in NOISE_KEYWORD_BLACKLIST
#                 ]
#                 if clean_p_tokens and clean_p != "GENERIC":
#                     final_clean_p = " ".join(clean_p_tokens)
#                     updated = add_or_update_classification_rule(
#                         category=target_category,
#                         subcategory=target_subcategory,
#                         new_pattern=final_clean_p,
#                         entry_type=inferred_entry_type,
#                     )
#                     if updated:
#                         rules_updated = True
#                         learned_patterns.append(final_clean_p)

#         print("🔍" * 40 + "\n")

#     return {
#         "status": "success",
#         "reclassified_count": len(entries),
#         "entry_type_bound": inferred_entry_type,
#         "rules_updated": rules_updated,
#         "patterns_learned": learned_patterns,
#     }


# from datetime import datetime
# import hashlib
# import json
# import re
# from typing import Any, Dict, List, Optional
# from collections import Counter

# from django.db.models import Q
# from django.utils import timezone

# from tracker.classification.remarks_service import generate_cluster_pattern
# from tracker.classification.utils.upiparser import parse_upi_narration
# from tracker.models import (
#     AccountingRule,
#     ClassificationRule,
#     JournalEntry,
#     StatementStagingLine,
#     TaxonomyTree,
# )

# # 🛡️ Centralized Banking & System Noise Keyword Blacklist
# NOISE_KEYWORD_BLACKLIST = {
#     "UPI",
#     "NEFT",
#     "RTGS",
#     "IMPS",
#     "POS",
#     "ACH",
#     "NFT",
#     "TFR",
#     "TRANSFER",
#     "PAYMENT",
#     "DR",
#     "CR",
#     "BANK",
#     "INB",
#     "INF",
#     "BIL",
#     "CLG",
#     "CHQ",
#     "CHEQUE",
#     "CASH",
#     "ATM",
#     "DEBIT",
#     "CREDIT",
#     "NONE",
#     "UNDEFINED",
#     "GENERAL_OPERATING_EXPENSES",
#     "UNCLASSIFIED",
#     "SUSPENSE_ACCOUNT",
#     # Bank Identifier Tokens (Prevent Over-Matching)
#     "UTIB",
#     "YESB",
#     "FDRL",
#     "ICIC",
#     "HDFC",
#     "SBIN",
#     "BARB",
#     "SIBL",
#     "CNRB",
#     "IBKL",
#     "PUNB",
#     "MAHB",
#     "IDIB",
#     "IOBA",
#     "UBIN",
#     "KKBK",
#     "RATN",
#     "PYTM",
#     "PAYTM",
#     # UPI & Memo System Noise
#     "REMARKS",
#     "REMARK",
#     "NOREMARKS",
#     "NOREMARK",
#     "NO_REMARKS",
#     "NO_REMARK",
#     "PAYMENT_FOR",
#     "YOU_ARE_PAYING",
#     "INGESTED_VIA_STAGING",
#     "PAYTMQR",
#     "PI",
#     "CMN",
#     "PRCR",
#     "POSTRN",
#     # Location & Generic Noise
#     "TECHNOPARK",
#     "TRIVANDRUM",
#     "KERALA",
#     "INDIA",
#     "BRANCH",
#     "KALLAMBALAM",
#     "KALLAMBALA",
#     "VARKALA",
#     "ULLOOR",
# }

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

# BANK_TOKENS = {
#     "UPI",
#     "YESB",
#     "UTIB",
#     "SIBL",
#     "FDRL",
#     "ICIC",
#     "HDFC",
#     "SBIN",
#     "BARB",
#     "CNRB",
#     "IBKL",
#     "PUNB",
#     "MAHB",
#     "PAYTMQR",
# }

# GENERIC_NOISE_TOKENS = {
#     "MOB",
#     "UPI",
#     "PYTM",
#     "IMPS",
#     "NEFT",
#     "RTGS",
#     "TRANSFER",
#     "BY",
#     "TO",
#     "NO",
#     "REMARKS",
#     "REMARK",
# }

# GENERIC_IGNORE_PATTERNS = {
#     "MOB",
#     "UPI",
#     "PYTM",
#     "IMPS",
#     "NEFT",
#     "RTGS",
#     "TRANSFER",
#     "BY",
#     "TO",
#     "PAID",
#     "RECEIVED",
#     "INB",
#     "INB/IMPS",
#     "OTHERS",
# }


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


# def extract_meaningful_tokens(text: str) -> list[str]:
#     """
#     Cleans raw narration, respects slashes/delimiters, strips bank noise/UPI hashes,
#     and preserves payee initials without creating concatenated garbage (e.g. 'PNO REMARKS').
#     """
#     if not text:
#         return []

#     raw_str = str(text).upper().strip()

#     # 1. Clean out known UPI noise patterns explicitly before splitting
#     raw_str = re.sub(r"\bNO\s+REMARKS?\b", "", raw_str)
#     raw_str = re.sub(r"\bPAYTMQR[A-Z0-9]*\b", "", raw_str)
#     raw_str = re.sub(r"\bUPI[A-Z0-9]{10,}\b", "", raw_str)

#     # 2. Treat slashes, dashes, @, and non-alphanumerics as strict delimiters
#     delimiters_cleaned = re.sub(r"[^A-Z0-9]", " ", raw_str)
#     raw_tokens = delimiters_cleaned.split()

#     filtered_tokens = []
#     for token in raw_tokens:
#         # Filter out numbers, gateway handles, and noise keywords
#         if token.isdigit() or len(token) > 25:  # Skip raw numeric refs or long hashes
#             continue
#         if token in GENERIC_NOISE_TOKENS or token in NOISE_KEYWORD_BLACKLIST:
#             continue
#         filtered_tokens.append(token)

#     # 3. Smart Initial-Aware Token Preservation (No forced concatenation!)
#     final_tokens = []
#     for token in filtered_tokens:
#         if len(token) == 1:
#             # Preserve single initials (e.g., 'P' in 'MOHANAN P')
#             final_tokens.append(token)
#         elif len(token) > 1:
#             final_tokens.append(token)

#     return final_tokens


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

#     # POS bracket extraction e.g. POS TRN/ ID NO. (AZAD GROUP HOTELS TR)
#     pos_match = re.search(r"\(([^)]+)\)", text)
#     if pos_match:
#         candidate = pos_match.group(1).strip()
#         if len(candidate) >= 3 and not candidate.startswith("CIAL"):
#             return candidate

#     tokens = extract_meaningful_tokens(text)
#     if tokens:
#         return " ".join(tokens[:3])  # Top 3 meaningful tokens form clean payee name

#     return text[:30]


# def get_suspense_clusters(
#     target_subcategory="Suspense Account",
#     account_id=None,
#     search_query=None,
#     include_cleared=False,
# ):
#     print("\n" + "=" * 80)
#     print(
#         f"[engine] START get_suspense_clusters(sub='{target_subcategory}',"
#         f" account_id={account_id}, query='{search_query}', include_cleared={include_cleared})"
#     )
#     print("=" * 80)

#     if not include_cleared:
#         query = JournalEntry.objects.filter(account_id=99, is_reclassified=False)

#         if target_subcategory and target_subcategory.strip() not in [
#             "Suspense Account",
#             "All",
#         ]:
#             query = query.filter(
#                 evaluation_matrix_snapshot__resolved_subcategory=target_subcategory
#             )
#     else:
#         query = JournalEntry.objects.filter(account_id=99)

#         if target_subcategory and target_subcategory.strip() not in [
#             "Suspense Account",
#             "All",
#         ]:
#             query = query.filter(
#                 evaluation_matrix_snapshot__resolved_subcategory=target_subcategory
#             )

#     if account_id and str(account_id) != "99":
#         bank_row_ids = JournalEntry.objects.filter(account_id=account_id).values_list(
#             "row_identifier", flat=True
#         )
#         query = query.filter(row_identifier__in=bank_row_ids)

#     entries = list(query.order_by("-transaction_date"))
#     print(f"[engine] Total entries fetched: {len(entries)}")

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
#         dynamic_display_text = (
#             f"{direction_word} {target_subcategory} | {action_word}{ref_str} |"
#             " Ingested via Staging"
#         )

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
#                 "direction": "OUTFLOW" if is_outflow else "INFLOW",
#                 "transaction_date": str(entry.transaction_date),
#                 "remarks": item_remarks,
#             }
#         )

#     sorted_clusters = sorted(
#         clusters_map.values(), key=lambda c: c["count"], reverse=True
#     )

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

#             matches_pattern = norm_query in norm_pattern or norm_query in norm_samples
#             matches_item = any(
#                 norm_query in normalize_for_search(item.get("narration", ""))
#                 or norm_query
#                 in normalize_for_search(item.get("remarks", {}).get("payee", ""))
#                 for item in cluster.get("items", [])
#             )

#             if matches_pattern or matches_item:
#                 filtered_clusters.append(cluster)

#         return filtered_clusters

#     print(f"[engine] Total distinct clusters created: {len(sorted_clusters)}")
#     return sorted_clusters


# # def get_clean_patterns(rule) -> list[str]:
# #     """Parses and cleans rule patterns."""
# #     patterns = getattr(rule, "patterns", [])
# #     if isinstance(patterns, str):
# #         try:
# #             patterns = json.loads(patterns)
# #         except json.JSONDecodeError:
# #             patterns = [patterns]

# #     if not isinstance(patterns, list):
# #         patterns = [str(patterns)]

# #     return [p.strip() for p in patterns if p and str(p).strip()]


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


# # def classify_via_rules(
# #     raw_narration: str, is_debit: bool = True
# # ) -> Optional[Dict[str, str]]:
# #     """Evaluates raw narration text against active ClassificationRule patterns."""
# #     if not raw_narration or not str(raw_narration).strip():
# #         return None

# #     target_rule_type = "Debit" if is_debit else "Credit"

# #     active_rules = ClassificationRule.objects.filter(
# #         is_active=True, rule_type=target_rule_type
# #     ).order_by("-priority")

# #     for rule in active_rules:
# #         patterns_list = get_clean_patterns(rule)

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
#         # Use model method / fallback helper for clean pattern list
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


# def generate_strict_multitoken_pattern_older(narration_list: list[str]) -> list[str]:
#     """Extracts tokens present in the majority (>= 80%) of selected narrations."""
#     if not narration_list:
#         return []

#     token_sets = [set(extract_meaningful_tokens(n)) for n in narration_list if n]
#     if not token_sets:
#         return []

#     token_counts = Counter()
#     for t_set in token_sets:
#         for token in t_set:
#             token_counts[token] += 1

#     total_rows = len(token_sets)
#     threshold = max(1, int(total_rows * 0.8))

#     majority_tokens = [
#         token for token, count in token_counts.items() if count >= threshold
#     ]

#     return sorted(majority_tokens)


# def generate_strict_multitoken_pattern(narration_list: list[str]) -> list[str]:
#     """
#     Extracts tokens present in the majority (>= 80%) of selected narrations,
#     preserving natural word order instead of sorting alphabetically.
#     """
#     if not narration_list:
#         return []

#     # 1. Extract token lists preserving original sequence order
#     token_sequences = [extract_meaningful_tokens(n) for n in narration_list if n]
#     if not token_sequences:
#         return []

#     # 2. Count frequencies
#     token_counts = Counter()
#     for seq in token_sequences:
#         for token in set(seq):
#             token_counts[token] += 1

#     total_rows = len(token_sequences)
#     threshold = max(1, int(total_rows * 0.8))

#     majority_tokens_set = {
#         token for token, count in token_counts.items() if count >= threshold
#     }

#     # 3. Preserve natural order from the first sample narration!
#     ordered_tokens = []
#     first_sample_tokens = token_sequences[0]

#     for token in first_sample_tokens:
#         if token in majority_tokens_set and token not in ordered_tokens:
#             ordered_tokens.append(token)

#     # Append any remaining majority tokens not in the first sequence
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
#     """Appends pattern into an existing ClassificationRule or creates a new active rule."""
#     if not new_pattern or not str(new_pattern).strip():
#         return False

#     clean_pattern = str(new_pattern).strip().upper()

#     pattern_tokens = extract_meaningful_tokens(clean_pattern)
#     if not pattern_tokens or any(t in NOISE_KEYWORD_BLACKLIST for t in pattern_tokens):
#         print(f"⚠️ Rejected unsafe/noise keyword for auto-learning: '{clean_pattern}'")
#         return False

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
#         patterns = get_clean_patterns(existing_rule)
#         updated_fields = ["patterns", "match_count", "updated_at"]

#         if clean_pattern not in patterns:
#             patterns.append(clean_pattern)
#             existing_rule.patterns = patterns
#             existing_rule.match_count = (existing_rule.match_count or 0) + 1

#             if not existing_rule.taxonomy and resolved_taxonomy:
#                 existing_rule.taxonomy = resolved_taxonomy
#                 updated_fields.append("taxonomy")

#             existing_rule.save(update_fields=updated_fields)
#             print(
#                 f"✅ Appended pattern '{clean_pattern}' to existing rule {existing_rule.rule_code}"
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
#             f"✅ Created new distinct rule {rule_code} with pattern '{clean_pattern}'"
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
#     Executes bulk reclassification for Node 99 records and learns new distinct matching rules
#     by auto-grouping selected narrations into individual payee clusters.
#     Strips trailing single-letter initials from compound patterns (>= 3 words) to prevent over-filtering.
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

#         # Group narrations by clean extracted payee to prevent cross-tag token dilution
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
#         print("\n" + "🔍" * 40)
#         print(f"[ENGINE DEBUG] Learning Rules for Subcategory: '{target_subcategory}'")
#         print(
#             f"[ENGINE DEBUG] Grouped {len(entries)} items into {len(payee_groups)} distinct payee clusters:"
#         )

#         for payee_key, group_narrations in payee_groups.items():
#             common_tokens = generate_strict_multitoken_pattern(group_narrations)

#             common_tokens = [t for t in common_tokens if not re.search(r"\d", t)]

#             if len(common_tokens) >= 3:
#                 filtered_tokens = [t for t in common_tokens if len(t) > 1]
#                 if len(filtered_tokens) >= 2:
#                     common_tokens = filtered_tokens

#             print(f"  --> Cluster '{payee_key}': Extracted Tokens = {common_tokens}")

#             if len(common_tokens) >= 2:
#                 compound_pattern = " ".join(common_tokens)
#                 updated = add_or_update_classification_rule(
#                     category=target_category,
#                     subcategory=target_subcategory,
#                     new_pattern=compound_pattern,
#                     entry_type=inferred_entry_type,
#                 )
#                 if updated:
#                     rules_updated = True
#                     learned_patterns.append(compound_pattern)
#             else:
#                 clean_p = extract_clean_payee_pattern(payee_key)
#                 if clean_p and clean_p != "GENERIC":
#                     updated = add_or_update_classification_rule(
#                         category=target_category,
#                         subcategory=target_subcategory,
#                         new_pattern=clean_p,
#                         entry_type=inferred_entry_type,
#                     )
#                     if updated:
#                         rules_updated = True
#                         learned_patterns.append(clean_p)

#         print("🔍" * 40 + "\n")

#     return {
#         "status": "success",
#         "reclassified_count": len(entries),
#         "entry_type_bound": inferred_entry_type,
#         "rules_updated": rules_updated,
#         "patterns_learned": learned_patterns,
#     }


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

# # # 🛡️ Centralized Banking & System Noise Keyword Blacklist
# # NOISE_KEYWORD_BLACKLIST = {
# #     "UPI",
# #     "NEFT",
# #     "RTGS",
# #     "IMPS",
# #     "POS",
# #     "ACH",
# #     "NFT",
# #     "TFR",
# #     "TRANSFER",
# #     "PAYMENT",
# #     "DR",
# #     "CR",
# #     "BANK",
# #     "INB",
# #     "INF",
# #     "BIL",
# #     "CLG",
# #     "CHQ",
# #     "CHEQUE",
# #     "CASH",
# #     "ATM",
# #     "DEBIT",
# #     "CREDIT",
# #     "NONE",
# #     "UNDEFINED",
# #     "GENERAL_OPERATING_EXPENSES",
# #     "UNCLASSIFIED",
# #     "SUSPENSE_ACCOUNT",
# #     # Bank Identifier Tokens (Prevent Over-Matching)
# #     "UTIB",
# #     "YESB",
# #     "FDRL",
# #     "ICIC",
# #     "HDFC",
# #     "SBIN",
# #     "BARB",
# #     "SIBL",
# #     "CNRB",
# #     "IBKL",
# #     "PUNB",
# #     "MAHB",
# #     "IDIB",
# #     "IOBA",
# #     "UBIN",
# #     "KKBK",
# #     # Location & Generic Noise
# #     "TECHNOPARK",
# #     "TRIVANDRUM",
# #     "KERALA",
# #     "INDIA",
# #     "BRANCH",
# #     "KALLAMBALAM",
# #     "KALLAMBALA",
# #     "VARKALA",
# #     "ULLOOR",
# # }

# # GENERIC_PATTERNS = {
# #     "#GENERAL_OPERATING_EXPENSES",
# #     "#GENERAL_OPERATING_EXPENSE",
# #     "#SUSPENSE_ACCOUNT",
# #     "#UNCLASSIFIED_OTHER",
# #     "#SUSPENSE",
# #     "#TRANSFER_NACH",
# #     "GENERAL_OPERATING_EXPENSES",
# #     "UNCLASSIFIED",
# #     "TRANSFER_NACH",
# #     "UNCLASSIFIED_OTHER",
# #     "SUSPENSE_ACCOUNT",
# #     "NACH",
# #     "IMPS",
# #     "KALLAMBALAM",
# #     "POSTRN",
# # }

# # BANK_TOKENS = {
# #     "UPI",
# #     "YESB",
# #     "UTIB",
# #     "SIBL",
# #     "FDRL",
# #     "ICIC",
# #     "HDFC",
# #     "SBIN",
# #     "BARB",
# #     "CNRB",
# #     "IBKL",
# #     "PUNB",
# #     "MAHB",
# #     "PAYTMQR",
# # }

# # GENERIC_NOISE_TOKENS = {
# #     "MOB",
# #     "UPI",
# #     "PYTM",
# #     "IMPS",
# #     "NEFT",
# #     "RTGS",
# #     "TRANSFER",
# #     "BY",
# #     "TO",
# # }

# # GENERIC_IGNORE_PATTERNS = {
# #     "MOB",
# #     "UPI",
# #     "PYTM",
# #     "IMPS",
# #     "NEFT",
# #     "RTGS",
# #     "TRANSFER",
# #     "BY",
# #     "TO",
# #     "PAID",
# #     "RECEIVED",
# #     "INB",
# #     "INB/IMPS",
# #     "OTHERS",
# # }


# # def normalize_for_search(text: str) -> str:
# #     """Strips underscores, spaces, dashes, colons, and punctuation for fuzzy matching.

# #     e.g., 'B_AIJU' -> 'BAIJU', 'PRAVEE N P' -> 'PRAVEENP'
# #     """
# #     if not text:
# #         return ""
# #     return re.sub(r"[^A-Z0-9]+", "", str(text).upper())


# # def normalize_condensed(text: str) -> str:
# #     """
# #     Strips all non-alphanumeric characters AND spaces.
# #     Used ONLY for fuzzy boundary evaluation against learned rules.
# #     e.g., 'B AIJU' -> 'BAIJU', 'BA IJU' -> 'BAIJU'
# #     """
# #     if not text:
# #         return ""
# #     return re.sub(r"[^A-Z0-9]", "", str(text).upper())


# # def extract_meaningful_tokens(text: str) -> list[str]:
# #     """
# #     Cleans string, fuses fragmented bank spacing artifacts (e.g., 'B AIJU' -> 'BAIJU'),
# #     and extracts distinct, meaningful alphanumeric tokens excluding generic banking & location noise.
# #     """
# #     if not text:
# #         return []

# #     # 1. Replace non-alphanumeric characters with spaces and uppercase
# #     cleaned = re.sub(r"[^A-Za-z0-9]", " ", str(text)).upper()
# #     raw_tokens = [
# #         t
# #         for t in cleaned.split()
# #         if t not in GENERIC_NOISE_TOKENS and t not in NOISE_KEYWORD_BLACKLIST
# #     ]

# #     # 2. Dynamic Short-Token Fusion (handles fragmented bank spacing without hardcoding)
# #     fused_tokens = []
# #     i = 0
# #     while i < len(raw_tokens):
# #         token = raw_tokens[i]

# #         # If current token is 1-2 chars and followed by another token, fuse them
# #         if len(token) <= 2 and i + 1 < len(raw_tokens):
# #             next_token = raw_tokens[i + 1]
# #             fused = token + next_token
# #             if (
# #                 fused not in GENERIC_NOISE_TOKENS
# #                 and fused not in NOISE_KEYWORD_BLACKLIST
# #                 and len(fused) > 1
# #             ):
# #                 fused_tokens.append(fused)
# #             i += 2  # Skip next token since it was consumed in fusion
# #         else:
# #             if len(token) > 1:
# #                 fused_tokens.append(token)
# #             i += 1

# #     return fused_tokens


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

# #     # 🛡️ STRICT RULE 1: Minimum Token Threshold
# #     # Prevents single-token matching unless condensed string is significant (e.g. >= 6 chars)
# #     if len(pattern_tokens) < min_required_tokens:
# #         condensed_narration = normalize_condensed(narration)
# #         condensed_pattern = normalize_condensed(pattern)
# #         return len(condensed_pattern) >= 6 and condensed_pattern in condensed_narration

# #     # 🛡️ STRICT RULE 2: Require ALL pattern tokens to exist in narration
# #     if pattern_tokens.issubset(narration_tokens):
# #         return True

# #     # 🛡️ STRICT RULE 3: Condensed Fallback Check (Handles fragmented spacing like 'B AIJU' vs 'BAIJU')
# #     condensed_narration = normalize_condensed(narration)
# #     condensed_pattern = normalize_condensed(pattern)

# #     return len(condensed_pattern) >= 6 and condensed_pattern in condensed_narration


# # def extract_clean_payee_pattern(narration: str) -> str:
# #     """Extracts the true merchant/person payee name from raw bank narrations, bypassing bank handle prefixes, numeric reference codes, and location noise."""
# #     if not narration or not str(narration).strip():
# #         return ""

# #     text = str(narration).strip().upper()

# #     # 1. POS / ID NO bracket extraction e.g. POS TRN/ ID NO. (AZAD GROUP HOTELS TR)
# #     pos_match = re.search(r"\(([^)]+)\)", text)
# #     if pos_match:
# #         candidate = pos_match.group(1).strip()
# #         if len(candidate) >= 3 and not candidate.startswith("CIAL"):
# #             return candidate

# #     # 2. UPI slash-delimited token parsing
# #     if "UPI" in text or "/" in text:
# #         parts = [p.strip() for p in text.split("/") if p.strip()]

# #         candidates = []
# #         for part in parts:
# #             if part in BANK_TOKENS or part in NOISE_KEYWORD_BLACKLIST:
# #                 continue
# #             if re.match(r"^[\d\s]+$", part):
# #                 continue
# #             if len(part) < 3:
# #                 continue
# #             candidates.append(part)

# #         if candidates:
# #             return candidates[0]

# #     return text[:30]


# # # def get_suspense_clusters(
# # #     target_subcategory="Suspense Account",
# # #     account_id=None,
# # #     search_query=None,
# # #     include_cleared=False,
# # # ):
# # #     print("\n" + "=" * 80)
# # #     print(
# # #         f"[engine] START get_suspense_clusters(sub='{target_subcategory}',"
# # #         f" account_id={account_id}, query='{search_query}', include_cleared={include_cleared})"
# # #     )
# # #     print("=" * 80)

# # #     # 1. Base Query Construction
# # #     query = JournalEntry.objects.all()

# # #     if not include_cleared:
# # #         # Standard Processing Mode: Unclassified entries on Node 99
# # #         query = query.filter(account_id=99, is_reclassified=False)
# # #         if target_subcategory == "Suspense Account":
# # #             query = query.filter(is_reclassified=False)
# # #     else:
# # #         # Audit / Reclassified Mode for specific subcategory
# # #         if target_subcategory and target_subcategory != "All":
# # #             query = query.filter(
# # #                 evaluation_matrix_snapshot__resolved_subcategory=target_subcategory
# # #             )

# # #     # 2. Scope Node 99 entries via matching row_identifiers if a specific bank account is provided
# # #     if account_id and str(account_id) != "99":
# # #         bank_row_ids = JournalEntry.objects.filter(account_id=account_id).values_list(
# # #             "row_identifier", flat=True
# # #         )
# # #         query = query.filter(row_identifier__in=bank_row_ids)

# # #     entries = list(query.order_by("-transaction_date"))
# # #     print(f"[engine] Total entries fetched: {len(entries)}")

# # #     row_ids = [e.row_identifier for e in entries if e.row_identifier]
# # #     staging_map = {
# # #         s.row_identifier: s.narration
# # #         for s in StatementStagingLine.objects.filter(row_identifier__in=row_ids).only(
# # #             "row_identifier", "narration"
# # #         )
# # #     }

# # #     clusters_map = {}

# # #     for idx, entry in enumerate(entries, 1):
# # #         remarks = entry.remarks if isinstance(entry.remarks, dict) else {}
# # #         narration = staging_map.get(entry.row_identifier, "")
# # #         stored_pattern = remarks.get("pattern")

# # #         # Direction resolution based on credit vs debit values
# # #         debit_val = float(entry.debit or 0)
# # #         credit_val = float(entry.credit or 0)

# # #         if credit_val > 0 and debit_val == 0:
# # #             is_outflow = False
# # #             amount = credit_val
# # #         elif debit_val > 0 and credit_val == 0:
# # #             is_outflow = True
# # #             amount = debit_val
# # #         else:
# # #             amount = debit_val if debit_val > 0 else credit_val
# # #             is_outflow = debit_val > 0

# # #         parsed_meta = parse_upi_narration(narration) or {}
# # #         payee = parsed_meta.get("payee") or remarks.get("payee")
# # #         ref_no = parsed_meta.get("upi_ref") or remarks.get("upi_ref")

# # #         # Force live re-parsing if pattern is missing or generic
# # #         if not stored_pattern or stored_pattern in GENERIC_PATTERNS:
# # #             pattern = generate_cluster_pattern(
# # #                 narration=narration, remarks_data={"payee": payee}
# # #             )
# # #         else:
# # #             pattern = stored_pattern

# # #         if pattern not in clusters_map:
# # #             clusters_map[pattern] = {
# # #                 "pattern": pattern,
# # #                 "count": 0,
# # #                 "total_amount": 0.0,
# # #                 "total_inflow": 0.0,
# # #                 "total_outflow": 0.0,
# # #                 "sample_descriptions": [],
# # #                 "items": [],
# # #                 "transaction_ids": [],
# # #             }

# # #         direction_word = "By" if is_outflow else "To"

# # #         if is_outflow:
# # #             action_word = (
# # #                 f"Paid ₹{amount:,.2f} to {payee}"
# # #                 if payee
# # #                 else f"Outflow of ₹{amount:,.2f}"
# # #             )
# # #         else:
# # #             if pattern == "BANK_INTEREST" or (payee and "INTEREST" in payee.upper()):
# # #                 action_word = f"Received ₹{amount:,.2f} interest credit"
# # #             else:
# # #                 action_word = f"Received ₹{amount:,.2f} from {payee or 'Payee'}"

# # #         ref_str = f" [Ref: {ref_no}]" if ref_no else ""
# # #         dynamic_display_text = (
# # #             f"{direction_word} {target_subcategory} | {action_word}{ref_str} |"
# # #             " Ingested via Staging"
# # #         )

# # #         item_remarks = {
# # #             **remarks,
# # #             "payee": payee,
# # #             "upi_ref": ref_no,
# # #             "display_text": dynamic_display_text,
# # #             "target_account_name": target_subcategory,
# # #             "directional_prefix": direction_word,
# # #         }

# # #         cluster = clusters_map[pattern]
# # #         cluster["count"] += 1
# # #         cluster["total_amount"] += amount

# # #         if is_outflow:
# # #             cluster["total_outflow"] += amount
# # #         else:
# # #             cluster["total_inflow"] += amount

# # #         cluster["transaction_ids"].append(str(entry.id))

# # #         if (
# # #             len(cluster["sample_descriptions"]) < 3
# # #             and dynamic_display_text not in cluster["sample_descriptions"]
# # #         ):
# # #             cluster["sample_descriptions"].append(dynamic_display_text)

# # #         cluster["items"].append(
# # #             {
# # #                 "id": str(entry.id),
# # #                 "narration": narration,
# # #                 "debit": debit_val,
# # #                 "credit": credit_val,
# # #                 "amount": amount,
# # #                 "direction": "OUTFLOW" if is_outflow else "INFLOW",
# # #                 "transaction_date": str(entry.transaction_date),
# # #                 "remarks": item_remarks,
# # #             }
# # #         )

# # #     sorted_clusters = sorted(
# # #         clusters_map.values(), key=lambda c: c["count"], reverse=True
# # #     )

# # #     # Fuzzy normalized search filter
# # #     if search_query and str(search_query).strip():
# # #         norm_query = normalize_for_search(search_query)
# # #         filtered_clusters = []

# # #         for cluster in sorted_clusters:
# # #             norm_pattern = normalize_for_search(cluster["pattern"])
# # #             norm_samples = " ".join(
# # #                 [
# # #                     normalize_for_search(s)
# # #                     for s in cluster.get("sample_descriptions", [])
# # #                 ]
# # #             )

# # #             matches_pattern = norm_query in norm_pattern or norm_query in norm_samples
# # #             matches_item = any(
# # #                 norm_query in normalize_for_search(item.get("narration", ""))
# # #                 or norm_query
# # #                 in normalize_for_search(item.get("remarks", {}).get("payee", ""))
# # #                 for item in cluster.get("items", [])
# # #             )

# # #             if matches_pattern or matches_item:
# # #                 filtered_clusters.append(cluster)

# # #         print(
# # #             f"[engine] Search query '{search_query}' (normalized:"
# # #             f" '{norm_query}') filtered {len(sorted_clusters)} ->"
# # #             f" {len(filtered_clusters)} clusters"
# # #         )
# # #         return filtered_clusters

# # #     print(f"[engine] Total distinct clusters created: {len(sorted_clusters)}")
# # #     return sorted_clusters


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

# #     # 1. Base Query Construction
# #     # 1. Base Query Construction
# #     if not include_cleared:
# #         # Standard Processing Mode: Unclassified entries on Node 99 ONLY
# #         query = JournalEntry.objects.filter(account_id=99, is_reclassified=False)

# #         if target_subcategory and target_subcategory.strip() not in [
# #             "Suspense Account",
# #             "All",
# #         ]:
# #             query = query.filter(
# #                 evaluation_matrix_snapshot__resolved_subcategory=target_subcategory
# #             )
# #     else:
# #         # Audit / Reclassified Mode for Node 99 Workbench
# #         query = JournalEntry.objects.filter(account_id=99)

# #         if target_subcategory and target_subcategory.strip() not in [
# #             "Suspense Account",
# #             "All",
# #         ]:
# #             query = query.filter(
# #                 evaluation_matrix_snapshot__resolved_subcategory=target_subcategory
# #             )

# #     # 2. Scope Node 99 entries via matching row_identifiers if a specific bank account is provided
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

# #         # Direction resolution based on credit vs debit values
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

# #     # Fuzzy normalized search filter
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

# #         print(
# #             f"[engine] Search query '{search_query}' (normalized:"
# #             f" '{norm_query}') filtered {len(sorted_clusters)} ->"
# #             f" {len(filtered_clusters)} clusters"
# #         )
# #         return filtered_clusters

# #     print(f"[engine] Total distinct clusters created: {len(sorted_clusters)}")
# #     return sorted_clusters


# # def get_clean_patterns(rule) -> list[str]:
# #     """Parses and cleans rule patterns whether stored as a JSON string, list, or single string."""
# #     patterns = getattr(rule, "patterns", [])
# #     if isinstance(patterns, str):
# #         try:
# #             patterns = json.loads(patterns)
# #         except json.JSONDecodeError:
# #             patterns = [patterns]

# #     if not isinstance(patterns, list):
# #         patterns = [str(patterns)]

# #     return [p.strip() for p in patterns if p and str(p).strip()]


# # def classify_via_rules(
# #     raw_narration: str, is_debit: bool = True
# # ) -> Optional[Dict[str, str]]:
# #     """Evaluates raw narration text against active ClassificationRule patterns using strict multi-token matching."""
# #     if not raw_narration or not str(raw_narration).strip():
# #         return None

# #     target_rule_type = "Debit" if is_debit else "Credit"

# #     active_rules = ClassificationRule.objects.filter(
# #         is_active=True, rule_type=target_rule_type
# #     ).order_by("-priority")

# #     for rule in active_rules:
# #         patterns_list = get_clean_patterns(rule)

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
# #     Extracts tokens present in the majority (>= 80%) of selected narrations.
# #     Prevents single outlier rows from destroying common multi-token patterns.
# #     """
# #     if not narration_list:
# #         return []

# #     token_sets = [set(extract_meaningful_tokens(n)) for n in narration_list if n]
# #     if not token_sets:
# #         return []

# #     token_counts = Counter()
# #     for t_set in token_sets:
# #         for token in t_set:
# #             token_counts[token] += 1

# #     total_rows = len(token_sets)
# #     threshold = max(1, int(total_rows * 0.8))

# #     majority_tokens = [
# #         token for token, count in token_counts.items() if count >= threshold
# #     ]

# #     return sorted(majority_tokens)


# # def add_or_update_classification_rule(
# #     category: str,
# #     subcategory: str,
# #     new_pattern: str,
# #     entry_type: str = "Debit",
# # ) -> bool:
# #     """Appends a pattern into an existing ClassificationRule or creates a new active rule, enforcing noise blacklists and directional vectors."""
# #     if not new_pattern or not str(new_pattern).strip():
# #         return False

# #     clean_pattern = str(new_pattern).strip().upper()

# #     # 🛡️ GUARD 1: Noise Keyword & Short Pattern Blacklist Check
# #     pattern_tokens = extract_meaningful_tokens(clean_pattern)
# #     if not pattern_tokens or any(t in NOISE_KEYWORD_BLACKLIST for t in pattern_tokens):
# #         print(f"⚠️ Rejected unsafe/noise keyword for auto-learning: '{clean_pattern}'")
# #         return False

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
# #         patterns = get_clean_patterns(existing_rule)
# #         updated_fields = ["patterns", "match_count", "updated_at"]

# #         if clean_pattern not in patterns:
# #             patterns.append(clean_pattern)
# #             existing_rule.patterns = patterns
# #             existing_rule.match_count = (existing_rule.match_count or 0) + 1

# #             if not existing_rule.taxonomy and resolved_taxonomy:
# #                 existing_rule.taxonomy = resolved_taxonomy
# #                 updated_fields.append("taxonomy")

# #             existing_rule.save(update_fields=updated_fields)
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
# #         return True


# # def reclassify_and_learn(
# #     transaction_ids: List[str],
# #     target_category: str,
# #     target_subcategory: str,
# #     patterns: Optional[List[str]] = None,
# #     save_rule: bool = True,
# # ) -> Dict[str, Any]:
# #     """
# #     Executes bulk reclassification for Node 99 records and learns new matching rules
# #     in ClassificationRule using strict multi-token common intersections.
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

# #     raw_narrations = []

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
# #         if narration_text:
# #             raw_narrations.append(narration_text)

# #         direction_word = remarks_dict.get("directional_prefix", "By")
# #         payee = remarks_dict.get("payee") or ""
# #         upi_ref = remarks_dict.get("upi_ref") or ""
# #         user_note = remarks_dict.get("user_note") or ""

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
# #         common_tokens = generate_strict_multitoken_pattern(raw_narrations)

# #         if len(common_tokens) >= 2:
# #             compound_pattern = " ".join(common_tokens)
# #             updated = add_or_update_classification_rule(
# #                 category=target_category,
# #                 subcategory=target_subcategory,
# #                 new_pattern=compound_pattern,
# #                 entry_type=inferred_entry_type,
# #             )
# #             if updated:
# #                 rules_updated = True
# #                 learned_patterns.append(compound_pattern)
# #         else:
# #             candidates = list(patterns or [])
# #             for p in candidates:
# #                 clean_p = extract_clean_payee_pattern(p)
# #                 if clean_p:
# #                     updated = add_or_update_classification_rule(
# #                         category=target_category,
# #                         subcategory=target_subcategory,
# #                         new_pattern=clean_p,
# #                         entry_type=inferred_entry_type,
# #                     )
# #                     if updated:
# #                         rules_updated = True
# #                         learned_patterns.append(clean_p)

# #     return {
# #         "status": "success",
# #         "reclassified_count": len(entries),
# #         "entry_type_bound": inferred_entry_type,
# #         "rules_updated": rules_updated,
# #         "patterns_learned": learned_patterns,
# #     }


# # # from datetime import datetime
# # # import hashlib
# # # import json
# # # import re
# # # from typing import Any, Dict, List, Optional
# # # from django.db.models import Q
# # # from django.utils import timezone
# # # from collections import Counter

# # # from tracker.classification.remarks_service import generate_cluster_pattern
# # # from tracker.classification.utils.upiparser import parse_upi_narration
# # # from tracker.models import (
# # #     AccountingRule,
# # #     ClassificationRule,
# # #     JournalEntry,
# # #     StatementStagingLine,
# # #     TaxonomyTree,
# # # )

# # # # 🛡️ Centralized Banking & System Noise Keyword Blacklist
# # # NOISE_KEYWORD_BLACKLIST = {
# # #     "UPI",
# # #     "NEFT",
# # #     "RTGS",
# # #     "IMPS",
# # #     "POS",
# # #     "ACH",
# # #     "NFT",
# # #     "TFR",
# # #     "TRANSFER",
# # #     "PAYMENT",
# # #     "DR",
# # #     "CR",
# # #     "BANK",
# # #     "INB",
# # #     "INF",
# # #     "BIL",
# # #     "CLG",
# # #     "CHQ",
# # #     "CHEQUE",
# # #     "CASH",
# # #     "ATM",
# # #     "DEBIT",
# # #     "CREDIT",
# # #     "NONE",
# # #     "UNDEFINED",
# # #     "GENERAL_OPERATING_EXPENSES",
# # #     "UNCLASSIFIED",
# # #     "SUSPENSE_ACCOUNT",
# # #     # Bank Identifier Tokens (Prevent Over-Matching)
# # #     "UTIB",
# # #     "YESB",
# # #     "FDRL",
# # #     "ICIC",
# # #     "HDFC",
# # #     "SBIN",
# # #     "BARB",
# # #     "SIBL",
# # #     "CNRB",
# # #     "IBKL",
# # #     "PUNB",
# # #     "MAHB",
# # #     "IDIB",
# # #     "IOBA",
# # #     "UBIN",
# # #     "KKBK",
# # #     # Location & Generic Noise
# # #     "TECHNOPARK",
# # #     "TRIVANDRUM",
# # #     "KERALA",
# # #     "INDIA",
# # #     "BRANCH",
# # #     # Banking terms
# # #     "UPI",
# # #     "NEFT",
# # #     "RTGS",
# # #     "IMPS",
# # #     "POS",
# # #     "ACH",
# # #     "NFT",
# # #     "TFR",
# # #     "TRANSFER",
# # #     # Branch & Location Noise (Prevents locations from polluting learned rule keys)
# # #     "KALLAMBALAM",
# # #     "KALLAMBALA",
# # #     "VARKALA",
# # #     "ULLOOR",
# # #     "TRIVANDRUM",
# # #     "TECHNOPARK",
# # #     "KERALA",
# # # }

# # # GENERIC_PATTERNS = {
# # #     "#GENERAL_OPERATING_EXPENSES",
# # #     "#GENERAL_OPERATING_EXPENSE",
# # #     "#SUSPENSE_ACCOUNT",
# # #     "#UNCLASSIFIED_OTHER",
# # #     "#SUSPENSE",
# # #     "#TRANSFER_NACH",
# # #     "GENERAL_OPERATING_EXPENSES",
# # #     "UNCLASSIFIED",
# # #     "TRANSFER_NACH",
# # #     "UNCLASSIFIED_OTHER",
# # #     "SUSPENSE_ACCOUNT",
# # #     "NACH",
# # #     "IMPS",
# # #     "KALLAMBALAM",
# # #     "POSTRN",
# # # }

# # # BANK_TOKENS = {
# # #     "UPI",
# # #     "YESB",
# # #     "UTIB",
# # #     "SIBL",
# # #     "FDRL",
# # #     "ICIC",
# # #     "HDFC",
# # #     "SBIN",
# # #     "BARB",
# # #     "CNRB",
# # #     "IBKL",
# # #     "PUNB",
# # #     "MAHB",
# # #     "PAYTMQR",
# # # }

# # # GENERIC_NOISE_TOKENS = {
# # #     "MOB",
# # #     "UPI",
# # #     "PYTM",
# # #     "IMPS",
# # #     "NEFT",
# # #     "RTGS",
# # #     "TRANSFER",
# # #     "BY",
# # #     "TO",
# # # }
# # # GENERIC_IGNORE_PATTERNS = {
# # #     "MOB",
# # #     "UPI",
# # #     "PYTM",
# # #     "IMPS",
# # #     "NEFT",
# # #     "RTGS",
# # #     "TRANSFER",
# # #     "BY",
# # #     "TO",
# # #     "PAID",
# # #     "RECEIVED",
# # #     "INB",
# # #     "INB/IMPS",
# # #     "OTHERS",
# # # }


# # # def normalize_for_search(text: str) -> str:
# # #     """Strips underscores, spaces, dashes, colons, and punctuation for fuzzy matching.

# # #     e.g., 'B_AIJU' -> 'BAIJU', 'PRAVEE N P' -> 'PRAVEENP'
# # #     """
# # #     if not text:
# # #         return ""
# # #     return re.sub(r"[^A-Z0-9]+", "", str(text).upper())


# # # def extract_clean_payee_pattern(narration: str) -> str:
# # #     """Extracts the true merchant/person payee name from raw bank narrations, bypassing bank handle prefixes, numeric reference codes, and location noise.

# # #     Examples:
# # #       - "UPI/YESB/09 1313127631/BINI RAJ N/GROCERIES" -> "BINI RAJ N"
# # #       - "UPI/UTIB/50 3613972551/PADHAYAM FISH MART/UPI" -> "PADHAYAM FISH MART"
# # #       - "POS TRN/ ID NO. (AZAD GROUP HOTELS TR)/PRCR/..." -> "AZAD GROUP HOTELS TR"
# # #     """
# # #     if not narration or not str(narration).strip():
# # #         return ""

# # #     text = str(narration).strip().upper()

# # #     # 1. POS / ID NO bracket extraction e.g. POS TRN/ ID NO. (AZAD GROUP HOTELS TR)
# # #     pos_match = re.search(r"\(([^)]+)\)", text)
# # #     if pos_match:
# # #         candidate = pos_match.group(1).strip()
# # #         if len(candidate) >= 3 and not candidate.startswith("CIAL"):
# # #             return candidate

# # #     # 2. UPI slash-delimited token parsing
# # #     if "UPI" in text or "/" in text:
# # #         parts = [p.strip() for p in text.split("/") if p.strip()]

# # #         candidates = []
# # #         for part in parts:
# # #             # Skip known bank handles and location noise
# # #             if part in BANK_TOKENS or any(
# # #                 b in part
# # #                 for b in [
# # #                     "TECHNOPARK",
# # #                     "TRIVANDRUM",
# # #                     "KERALA",
# # #                     "INDIA",
# # #                     "BRANCH",
# # #                     "UPI",
# # #                 ]
# # #             ):
# # #                 continue
# # #             # Skip pure numeric strings or reference codes (e.g. "09 1313127631" or "50 3613972551")
# # #             if re.match(r"^[\d\s]+$", part):
# # #                 continue
# # #             # Skip short garbage tokens
# # #             if len(part) < 3:
# # #                 continue
# # #             candidates.append(part)

# # #         if candidates:
# # #             return candidates[0]

# # #     return text[:30]


# # # def get_suspense_clusters(
# # #     target_subcategory="Suspense Account",
# # #     account_id=None,
# # #     search_query=None,
# # #     include_cleared=False,  # <--- New Parameter
# # # ):
# # #     print("\n" + "=" * 80)
# # #     print(
# # #         f"[engine] START get_suspense_clusters(sub='{target_subcategory}',"
# # #         f" account_id={account_id}, query='{search_query}', include_cleared={include_cleared})"
# # #     )
# # #     print("=" * 80)

# # #     # 1. Base Query Construction
# # #     query = JournalEntry.objects.all()

# # #     if not include_cleared:
# # #         # Standard Processing Mode: Unclassified entries on Node 99
# # #         query = query.filter(account_id=99, is_reclassified=False)
# # #         if target_subcategory == "Suspense Account":
# # #             query = query.filter(is_reclassified=False)
# # #     else:
# # #         # Audit / Reclassified Mode: Query entries across all accounts
# # #         # Note: We omit account_id=99 and is_reclassified=False to allow cleared items to load
# # #         pass

# # #     # 2. Filter by target_subcategory (e.g., General Operating Expenses, MMC, Donations)
# # #     if (
# # #         target_subcategory
# # #         and target_subcategory.strip()
# # #         and target_subcategory != "All"
# # #     ):
# # #         query = query.filter(
# # #             evaluation_matrix_snapshot__resolved_subcategory=target_subcategory
# # #         )

# # #     # 3. Scope Node 99 entries via matching row_identifiers if a specific bank account is provided
# # #     if account_id and str(account_id) != "99":
# # #         bank_row_ids = JournalEntry.objects.filter(account_id=account_id).values_list(
# # #             "row_identifier", flat=True
# # #         )
# # #         query = query.filter(row_identifier__in=bank_row_ids)

# # #     entries = list(query.order_by("-transaction_date"))
# # #     print(f"[engine] Total entries fetched: {len(entries)}")

# # #     row_ids = [e.row_identifier for e in entries if e.row_identifier]
# # #     staging_map = {
# # #         s.row_identifier: s.narration
# # #         for s in StatementStagingLine.objects.filter(row_identifier__in=row_ids).only(
# # #             "row_identifier", "narration"
# # #         )
# # #     }

# # #     clusters_map = {}

# # #     for idx, entry in enumerate(entries, 1):
# # #         remarks = entry.remarks if isinstance(entry.remarks, dict) else {}
# # #         narration = staging_map.get(entry.row_identifier, "")
# # #         stored_pattern = remarks.get("pattern")

# # #         # Direction resolution based on credit vs debit values
# # #         debit_val = float(entry.debit or 0)
# # #         credit_val = float(entry.credit or 0)

# # #         if credit_val > 0 and debit_val == 0:
# # #             is_outflow = False
# # #             amount = credit_val
# # #         elif debit_val > 0 and credit_val == 0:
# # #             is_outflow = True
# # #             amount = debit_val
# # #         else:
# # #             amount = debit_val if debit_val > 0 else credit_val
# # #             is_outflow = debit_val > 0

# # #         parsed_meta = parse_upi_narration(narration) or {}
# # #         payee = parsed_meta.get("payee") or remarks.get("payee")
# # #         ref_no = parsed_meta.get("upi_ref") or remarks.get("upi_ref")

# # #         # Force live re-parsing if pattern is missing or generic
# # #         if not stored_pattern or stored_pattern in GENERIC_PATTERNS:
# # #             pattern = generate_cluster_pattern(
# # #                 narration=narration, remarks_data={"payee": payee}
# # #             )
# # #         else:
# # #             pattern = stored_pattern

# # #         if pattern not in clusters_map:
# # #             clusters_map[pattern] = {
# # #                 "pattern": pattern,
# # #                 "count": 0,
# # #                 "total_amount": 0.0,
# # #                 "total_inflow": 0.0,
# # #                 "total_outflow": 0.0,
# # #                 "sample_descriptions": [],
# # #                 "items": [],
# # #                 "transaction_ids": [],
# # #             }

# # #         direction_word = "By" if is_outflow else "To"

# # #         if is_outflow:
# # #             action_word = (
# # #                 f"Paid ₹{amount:,.2f} to {payee}"
# # #                 if payee
# # #                 else f"Outflow of ₹{amount:,.2f}"
# # #             )
# # #         else:
# # #             if pattern == "BANK_INTEREST" or (payee and "INTEREST" in payee.upper()):
# # #                 action_word = f"Received ₹{amount:,.2f} interest credit"
# # #             else:
# # #                 action_word = f"Received ₹{amount:,.2f} from {payee or 'Payee'}"

# # #         ref_str = f" [Ref: {ref_no}]" if ref_no else ""
# # #         dynamic_display_text = (
# # #             f"{direction_word} {target_subcategory} | {action_word}{ref_str} |"
# # #             " Ingested via Staging"
# # #         )

# # #         item_remarks = {
# # #             **remarks,
# # #             "payee": payee,
# # #             "upi_ref": ref_no,
# # #             "display_text": dynamic_display_text,
# # #             "target_account_name": target_subcategory,
# # #             "directional_prefix": direction_word,
# # #         }

# # #         cluster = clusters_map[pattern]
# # #         cluster["count"] += 1
# # #         cluster["total_amount"] += amount

# # #         if is_outflow:
# # #             cluster["total_outflow"] += amount
# # #         else:
# # #             cluster["total_inflow"] += amount

# # #         cluster["transaction_ids"].append(str(entry.id))

# # #         if (
# # #             len(cluster["sample_descriptions"]) < 3
# # #             and dynamic_display_text not in cluster["sample_descriptions"]
# # #         ):
# # #             cluster["sample_descriptions"].append(dynamic_display_text)

# # #         cluster["items"].append(
# # #             {
# # #                 "id": str(entry.id),
# # #                 "narration": narration,
# # #                 "debit": debit_val,
# # #                 "credit": credit_val,
# # #                 "amount": amount,
# # #                 "direction": "OUTFLOW" if is_outflow else "INFLOW",
# # #                 "transaction_date": str(entry.transaction_date),
# # #                 "remarks": item_remarks,
# # #             }
# # #         )

# # #     sorted_clusters = sorted(
# # #         clusters_map.values(), key=lambda c: c["count"], reverse=True
# # #     )

# # #     # Fuzzy normalized search filter
# # #     if search_query and str(search_query).strip():
# # #         norm_query = normalize_for_search(search_query)
# # #         filtered_clusters = []

# # #         for cluster in sorted_clusters:
# # #             norm_pattern = normalize_for_search(cluster["pattern"])
# # #             norm_samples = " ".join(
# # #                 [
# # #                     normalize_for_search(s)
# # #                     for s in cluster.get("sample_descriptions", [])
# # #                 ]
# # #             )

# # #             matches_pattern = norm_query in norm_pattern or norm_query in norm_samples
# # #             matches_item = any(
# # #                 norm_query in normalize_for_search(item.get("narration", ""))
# # #                 or norm_query
# # #                 in normalize_for_search(item.get("remarks", {}).get("payee", ""))
# # #                 for item in cluster.get("items", [])
# # #             )

# # #             if matches_pattern or matches_item:
# # #                 filtered_clusters.append(cluster)

# # #         print(
# # #             f"[engine] Search query '{search_query}' (normalized:"
# # #             f" '{norm_query}') filtered {len(sorted_clusters)} ->"
# # #             f" {len(filtered_clusters)} clusters"
# # #         )
# # #         return filtered_clusters

# # #     print(f"[engine] Total distinct clusters created: {len(sorted_clusters)}")
# # #     return sorted_clusters


# # # def classify_via_rules(
# # #     raw_narration: str, is_debit: bool = True
# # # ) -> Optional[Dict[str, str]]:
# # #     """Evaluates raw narration text against active ClassificationRule patterns, strictly matching the cash flow direction vector (Debit vs Credit)."""
# # #     if not raw_narration or not str(raw_narration).strip():
# # #         return None

# # #     narration_upper = str(raw_narration).strip().upper()
# # #     target_rule_type = "Debit" if is_debit else "Credit"

# # #     # Filter rules matching both active status AND the exact cash flow vector
# # #     active_rules = ClassificationRule.objects.filter(
# # #         is_active=True, rule_type=target_rule_type
# # #     ).order_by("-priority")

# # #     for rule in active_rules:
# # #         patterns_list = rule.patterns if isinstance(rule.patterns, list) else []
# # #         if isinstance(patterns_list, str):
# # #             try:
# # #                 patterns_list = json.loads(patterns_list)
# # #             except Exception:
# # #                 patterns_list = [patterns_list]

# # #         for pattern in patterns_list:
# # #             if pattern and str(pattern).strip().upper() in narration_upper:
# # #                 rule.match_count = (rule.match_count or 0) + 1
# # #                 rule.save(update_fields=["match_count", "updated_at"])

# # #                 return {
# # #                     "category": rule.target_category,
# # #                     "subcategory": rule.target_subcategory,
# # #                     "matched_pattern": pattern,
# # #                     "rule_code": rule.rule_code,
# # #                     "rule_type": rule.rule_type,
# # #                 }
# # #     return None


# # # def add_or_update_classification_rule(
# # #     category: str,
# # #     subcategory: str,
# # #     new_pattern: str,
# # #     entry_type: str = "Debit",
# # # ) -> bool:
# # #     """Appends a pattern into an existing ClassificationRule or creates a new active rule, enforcing noise blacklists, directional cash flow vector binding (DR/CR), and resolving the taxonomy foreign key."""
# # #     if not new_pattern or not str(new_pattern).strip():
# # #         return False

# # #     clean_pattern = str(new_pattern).strip().upper()

# # #     # 🛡️ GUARD 1: Noise Keyword & Short Pattern Blacklist Check
# # #     if clean_pattern in NOISE_KEYWORD_BLACKLIST or len(clean_pattern) < 3:
# # #         print(
# # #             "⚠️ Rejected unsafe/noise keyword for auto-learning:" f" '{clean_pattern}'"
# # #         )
# # #         return False

# # #     clean_entry_type = (
# # #         "Credit" if str(entry_type).strip().lower() == "credit" else "Debit"
# # #     )

# # #     # 🔍 TAXONOMY RESOLUTION: Look up matching TaxonomyTree record using category & subcategory
# # #     taxonomy_node = TaxonomyTree.objects.filter(
# # #         category__iexact=category, subcategory__iexact=subcategory
# # #     ).first()
# # #     resolved_taxonomy = taxonomy_node if taxonomy_node else None

# # #     # 🛡️ GUARD 2: Search existing active ClassificationRule matching target subcategory AND entry_type vector
# # #     existing_rule = ClassificationRule.objects.filter(
# # #         target_category=category,
# # #         target_subcategory=subcategory,
# # #         rule_type=clean_entry_type,
# # #         is_active=True,
# # #     ).first()

# # #     if existing_rule:
# # #         patterns = existing_rule.patterns or []
# # #         if isinstance(patterns, str):
# # #             try:
# # #                 patterns = json.loads(patterns)
# # #             except Exception:
# # #                 patterns = [patterns]

# # #         updated_fields = ["patterns", "match_count", "updated_at"]

# # #         if clean_pattern not in patterns:
# # #             patterns.append(clean_pattern)
# # #             existing_rule.patterns = patterns
# # #             existing_rule.match_count = (existing_rule.match_count or 0) + 1

# # #             # Backfill taxonomy if missing
# # #             if not existing_rule.taxonomy and resolved_taxonomy:
# # #                 existing_rule.taxonomy = resolved_taxonomy
# # #                 updated_fields.append("taxonomy")

# # #             existing_rule.save(update_fields=updated_fields)
# # #             return True
# # #         return False

# # #     else:
# # #         # 🛡️ GUARD 3: Create new active ClassificationRule entry with direction vector encoded in Rule Code
# # #         vector_prefix = "DE" if clean_entry_type == "Debit" else "CR"
# # #         hash_input = f"{subcategory}_{clean_pattern}_{clean_entry_type}".upper()
# # #         short_code = hashlib.md5(hash_input.encode()).hexdigest()[:6].upper()
# # #         rule_code = f"CR_{vector_prefix}_{short_code}"

# # #         ClassificationRule.objects.create(
# # #             name=f"Learned ({clean_entry_type}): {subcategory} ({clean_pattern})",
# # #             rule_code=rule_code,
# # #             rule_type=clean_entry_type,
# # #             target_category=category,
# # #             target_subcategory=subcategory,
# # #             patterns=[clean_pattern],
# # #             priority=1,
# # #             is_active=True,
# # #             created_from_manual_override=True,
# # #             match_count=1,
# # #             taxonomy=resolved_taxonomy,
# # #         )
# # #         return True


# # # # def reclassify_and_learn_older(
# # # #     transaction_ids: List[str],
# # # #     target_category: str,
# # # #     target_subcategory: str,
# # # #     patterns: Optional[List[str]] = None,
# # # #     save_rule: bool = True,
# # # # ) -> Dict[str, Any]:
# # # #     """Executes bulk reclassification for Node 99 records and learns new matching rules in ClassificationRule.

# # # #     Preserves payee metadata while updating target account names in remarks and
# # # #     enforcing directional cash flow vectors.
# # # #     """
# # # #     if not transaction_ids:
# # # #         return {"status": "success", "reclassified_count": 0, "rules_updated": False}

# # # #     # 1. Resolve row_identifiers from passed transaction_ids or row_identifiers
# # # #     target_row_ids = list(
# # # #         JournalEntry.objects.filter(
# # # #             Q(id__in=transaction_ids) | Q(row_identifier__in=transaction_ids)
# # # #         )
# # # #         .values_list("row_identifier", flat=True)
# # # #         .distinct()
# # # #     )

# # # #     if not target_row_ids:
# # # #         return {"status": "success", "reclassified_count": 0, "rules_updated": False}

# # # #     # 2. Fetch all target entries sitting in Node 99 matching those row_identifiers
# # # #     entries = list(
# # # #         JournalEntry.objects.filter(account_id=99, row_identifier__in=target_row_ids)
# # # #     )

# # # #     # 🛡️ VECTOR INFERENCE: Infer cash flow direction (Debit vs Credit)
# # # #     total_debit = sum(float(e.debit or 0) for e in entries)
# # # #     total_credit = sum(float(e.credit or 0) for e in entries)
# # # #     inferred_entry_type = "Credit" if total_credit > total_debit else "Debit"

# # # #     # Collect payee hints directly from entries in case raw patterns contain bank rail noise
# # # #     extracted_payees = []

# # # #     for entry in entries:
# # # #         snapshot = entry.evaluation_matrix_snapshot or {}
# # # #         snapshot["previous_category"] = snapshot.get("resolved_category")
# # # #         snapshot["previous_subcategory"] = snapshot.get("resolved_subcategory")
# # # #         snapshot["resolved_category"] = target_category
# # # #         snapshot["resolved_subcategory"] = target_subcategory
# # # #         snapshot["is_manual_override"] = True

# # # #         entry.evaluation_matrix_snapshot = snapshot
# # # #         entry.classification_status = "RECLASSIFIED"
# # # #         entry.is_reclassified = True

# # # #         # Update structured JSON remarks
# # # #         if isinstance(entry.remarks, dict):
# # # #             existing_remarks = entry.remarks
# # # #             direction_word = existing_remarks.get("directional_prefix", "By")
# # # #             payee = existing_remarks.get("payee") or ""
# # # #             upi_ref = existing_remarks.get("upi_ref") or ""
# # # #             user_note = existing_remarks.get("user_note") or ""

# # # #             if payee and payee.strip():
# # # #                 extracted_payees.append(payee.strip())

# # # #             amt = float(entry.debit or entry.credit or 0)
# # # #             ref_str = f" [Ref: {upi_ref}]" if upi_ref else ""
# # # #             action_word = (
# # # #                 f"Paid ₹{amt:,.2f} to {payee}" if payee else f"Amount ₹{amt:,.2f}"
# # # #             )
# # # #             note_str = f" | Note: {user_note.strip()}" if user_note else ""

# # # #             updated_display_text = (
# # # #                 f"{direction_word} {target_subcategory} |"
# # # #                 f" {action_word}{ref_str}{note_str} | Reclassified via Workbench"
# # # #             )

# # # #             entry.remarks = {
# # # #                 **existing_remarks,
# # # #                 "target_account_name": target_subcategory,
# # # #                 "display_text": updated_display_text,
# # # #                 "updated_at": timezone.now().isoformat(),
# # # #             }

# # # #     JournalEntry.objects.bulk_update(
# # # #         entries,
# # # #         [
# # # #             "evaluation_matrix_snapshot",
# # # #             "classification_status",
# # # #             "is_reclassified",
# # # #             "remarks",
# # # #         ],
# # # #     )

# # # #     # 3. Save learned patterns into ClassificationRule
# # # #     rules_updated = False
# # # #     learned_patterns = []

# # # #     if save_rule:
# # # #         # Combine passed patterns with extracted payee metadata from entries
# # # #         candidates_to_process = list(patterns or [])
# # # #         for p_hint in extracted_payees:
# # # #             if p_hint not in candidates_to_process:
# # # #                 candidates_to_process.append(p_hint)

# # # #         for p in candidates_to_process:
# # # #             if p and str(p).strip():
# # # #                 # Sanitize pattern string using extractor to bypass bank rail noise
# # # #                 clean_p = extract_clean_payee_pattern(p)

# # # #                 if clean_p and clean_p not in learned_patterns:
# # # #                     updated = add_or_update_classification_rule(
# # # #                         category=target_category,
# # # #                         subcategory=target_subcategory,
# # # #                         new_pattern=clean_p,
# # # #                         entry_type=inferred_entry_type,
# # # #                     )
# # # #                     if updated:
# # # #                         rules_updated = True
# # # #                         learned_patterns.append(clean_p)

# # # #     return {
# # # #         "status": "success",
# # # #         "reclassified_count": len(entries),
# # # #         "entry_type_bound": inferred_entry_type,
# # # #         "rules_updated": rules_updated,
# # # #         "patterns_learned": learned_patterns,
# # # #     }


# # # def reclassify_and_learn(
# # #     transaction_ids: List[str],
# # #     target_category: str,
# # #     target_subcategory: str,
# # #     patterns: Optional[List[str]] = None,
# # #     save_rule: bool = True,
# # # ) -> Dict[str, Any]:
# # #     """
# # #     Executes bulk reclassification for Node 99 records and learns new matching rules
# # #     in ClassificationRule using strict multi-token common intersections.
# # #     """
# # #     if not transaction_ids:
# # #         return {"status": "success", "reclassified_count": 0, "rules_updated": False}

# # #     # 1. Resolve target entries sitting in Node 99
# # #     entries = list(JournalEntry.objects.filter(account_id=99, id__in=transaction_ids))

# # #     if not entries:
# # #         # Fallback query if row_identifiers were passed instead of primary keys
# # #         entries = list(
# # #             JournalEntry.objects.filter(
# # #                 account_id=99, row_identifier__in=transaction_ids
# # #             )
# # #         )

# # #     if not entries:
# # #         return {"status": "success", "reclassified_count": 0, "rules_updated": False}

# # #     # 🛡️ VECTOR INFERENCE: Infer cash flow direction (Debit vs Credit)
# # #     total_debit = sum(float(e.debit or 0) for e in entries)
# # #     total_credit = sum(float(e.credit or 0) for e in entries)
# # #     inferred_entry_type = "Credit" if total_credit > total_debit else "Debit"

# # #     # Collect raw narrations for auto token intersection extraction
# # #     raw_narrations = []

# # #     for entry in entries:
# # #         snapshot = entry.evaluation_matrix_snapshot or {}
# # #         snapshot["previous_category"] = snapshot.get("resolved_category")
# # #         snapshot["previous_subcategory"] = snapshot.get("resolved_subcategory")
# # #         snapshot["resolved_category"] = target_category
# # #         snapshot["resolved_subcategory"] = target_subcategory
# # #         snapshot["is_manual_override"] = True

# # #         entry.evaluation_matrix_snapshot = snapshot
# # #         entry.classification_status = "RECLASSIFIED"
# # #         entry.is_reclassified = True

# # #         # Extract narration text from remarks dict or raw string
# # #         remarks_dict = entry.remarks if isinstance(entry.remarks, dict) else {}
# # #         narration_text = remarks_dict.get("narration") or str(entry.remarks or "")
# # #         if narration_text:
# # #             raw_narrations.append(narration_text)

# # #         # Update structured JSON remarks
# # #         direction_word = remarks_dict.get("directional_prefix", "By")
# # #         payee = remarks_dict.get("payee") or ""
# # #         upi_ref = remarks_dict.get("upi_ref") or ""
# # #         user_note = remarks_dict.get("user_note") or ""

# # #         amt = float(entry.debit or entry.credit or 0)
# # #         ref_str = f" [Ref: {upi_ref}]" if upi_ref else ""
# # #         action_word = f"Paid ₹{amt:,.2f} to {payee}" if payee else f"Amount ₹{amt:,.2f}"
# # #         note_str = f" | Note: {user_note.strip()}" if user_note else ""

# # #         updated_display_text = (
# # #             f"{direction_word} {target_subcategory} |"
# # #             f" {action_word}{ref_str}{note_str} | Reclassified via Workbench"
# # #         )

# # #         entry.remarks = {
# # #             **remarks_dict,
# # #             "target_account_name": target_subcategory,
# # #             "display_text": updated_display_text,
# # #             "updated_at": timezone.now().isoformat(),
# # #         }

# # #     JournalEntry.objects.bulk_update(
# # #         entries,
# # #         [
# # #             "evaluation_matrix_snapshot",
# # #             "classification_status",
# # #             "is_reclassified",
# # #             "remarks",
# # #         ],
# # #     )

# # #     # 3. Save auto-intersected compound pattern into ClassificationRule
# # #     rules_updated = False
# # #     learned_patterns = []

# # #     if save_rule:
# # #         # 🎯 AUTO MULTI-TOKEN GENERATION
# # #         # Extracts tokens common across ALL selected rows
# # #         common_tokens = generate_strict_multitoken_pattern(raw_narrations)

# # #         if len(common_tokens) >= 2:
# # #             # Join tokens into a strict space-delimited pattern
# # #             compound_pattern = " ".join(common_tokens)
# # #             updated = add_or_update_classification_rule(
# # #                 category=target_category,
# # #                 subcategory=target_subcategory,
# # #                 new_pattern=compound_pattern,
# # #                 entry_type=inferred_entry_type,
# # #             )
# # #             if updated:
# # #                 rules_updated = True
# # #                 learned_patterns.append(compound_pattern)
# # #         else:
# # #             # Fallback to single/passed pattern candidates if intersection yields < 2 tokens
# # #             candidates = list(patterns or [])
# # #             for p in candidates:
# # #                 clean_p = extract_clean_payee_pattern(p)
# # #                 if clean_p:
# # #                     updated = add_or_update_classification_rule(
# # #                         category=target_category,
# # #                         subcategory=target_subcategory,
# # #                         new_pattern=clean_p,
# # #                         entry_type=inferred_entry_type,
# # #                     )
# # #                     if updated:
# # #                         rules_updated = True
# # #                         learned_patterns.append(clean_p)

# # #     return {
# # #         "status": "success",
# # #         "reclassified_count": len(entries),
# # #         "entry_type_bound": inferred_entry_type,
# # #         "rules_updated": rules_updated,
# # #         "patterns_learned": learned_patterns,
# # #     }


# # # def normalize_condensed(text: str) -> str:
# # #     """
# # #     Strips all non-alphanumeric characters AND spaces.
# # #     Used ONLY for fuzzy boundary evaluation against learned rules.
# # #     e.g., 'B AIJU' -> 'BAIJU', 'BA IJU' -> 'BAIJU'
# # #     """
# # #     if not text:
# # #         return ""
# # #     return re.sub(r"[^A-Z0-9]", "", str(text).upper())


# # # def extract_meaningful_tokens(text: str) -> list[str]:
# # #     """
# # #     Cleans string, fuses fragmented bank spacing artifacts (e.g., 'B AIJU' -> 'BAIJU'),
# # #     and extracts distinct, meaningful alphanumeric tokens excluding generic banking noise.
# # #     """
# # #     if not text:
# # #         return []

# # #     # 1. Replace non-alphanumeric characters with spaces and uppercase
# # #     cleaned = re.sub(r"[^A-Za-z0-9]", " ", str(text)).upper()
# # #     raw_tokens = [t for t in cleaned.split() if t not in GENERIC_NOISE_TOKENS]

# # #     # 2. Dynamic Short-Token Fusion (handles fragmented bank spacing without hardcoding)
# # #     fused_tokens = []
# # #     i = 0
# # #     while i < len(raw_tokens):
# # #         token = raw_tokens[i]

# # #         # If current token is 1-2 chars and followed by another token, fuse them
# # #         if len(token) <= 2 and i + 1 < len(raw_tokens):
# # #             next_token = raw_tokens[i + 1]
# # #             fused = token + next_token
# # #             if fused not in GENERIC_NOISE_TOKENS and len(fused) > 1:
# # #                 fused_tokens.append(fused)
# # #             i += 2  # Skip next token since it was consumed in fusion
# # #         else:
# # #             if len(token) > 1:
# # #                 fused_tokens.append(token)
# # #             i += 1

# # #     return fused_tokens


# # # def match_multi_tokens(
# # #     narration: str, pattern: str, min_required_tokens: int = 2
# # # ) -> bool:
# # #     """
# # #     Validates if narration matches rule pattern tokens.
# # #     Handles space fragmentation by checking both standard token intersections
# # #     AND condensed normalized matching.
# # #     """
# # #     if not narration or not pattern:
# # #         return False

# # #     narration_tokens = set(extract_meaningful_tokens(narration))
# # #     pattern_tokens = set(extract_meaningful_tokens(pattern))

# # #     if not pattern_tokens:
# # #         return False

# # #     # 1. Direct Token Intersection Match
# # #     matched_tokens = pattern_tokens.intersection(narration_tokens)
# # #     required_count = min(len(pattern_tokens), min_required_tokens)

# # #     if len(matched_tokens) >= required_count:
# # #         return True

# # #     # 2. Condensed Fallback Check (Handles 'B AIJU' vs 'BAIJU' dynamically)
# # #     condensed_narration = normalize_condensed(narration)
# # #     condensed_pattern = normalize_condensed(pattern)

# # #     # If the condensed pattern exists as a substring in condensed narration
# # #     if len(condensed_pattern) >= 4 and condensed_pattern in condensed_narration:
# # #         return True

# # #     return False


# # # def get_clean_patterns(rule) -> list[str]:
# # #     """
# # #     Parses and cleans rule patterns whether stored as a JSON string,
# # #     list, or single string.
# # #     """
# # #     patterns = getattr(rule, "patterns", [])
# # #     if isinstance(patterns, str):
# # #         try:
# # #             patterns = json.loads(patterns)
# # #         except json.JSONDecodeError:
# # #             patterns = [patterns]

# # #     if not isinstance(patterns, list):
# # #         patterns = [str(patterns)]

# # #     return [p.strip() for p in patterns if p and str(p).strip()]


# # # def generate_strict_multitoken_pattern(narration_list: list[str]) -> list[str]:
# # #     """
# # #     Extracts tokens present in the majority (>= 80%) of selected narrations.
# # #     Prevents single outlier rows from destroying common multi-token patterns.
# # #     """
# # #     if not narration_list:
# # #         return []

# # #     token_sets = [set(extract_meaningful_tokens(n)) for n in narration_list if n]
# # #     if not token_sets:
# # #         return []

# # #     # Count token frequency across all selected row sets
# # #     token_counts = Counter()
# # #     for t_set in token_sets:
# # #         for token in t_set:
# # #             token_counts[token] += 1

# # #     total_rows = len(token_sets)
# # #     # Token must appear in at least 80% of selected rows
# # #     threshold = max(1, int(total_rows * 0.8))

# # #     majority_tokens = [
# # #         token for token, count in token_counts.items() if count >= threshold
# # #     ]

# # #     return sorted(majority_tokens)


# # # def generate_strict_multitoken_pattern_older(narration_list: list[str]) -> list[str]:
# # #     """
# # #     Extracts tokens present in the majority (>= 80%) of selected narrations.
# # #     Prevents single outlier rows from destroying common multi-token patterns.
# # #     """
# # #     if not narration_list:
# # #         return []

# # #     token_sets = [set(extract_meaningful_tokens(n)) for n in narration_list if n]
# # #     if not token_sets:
# # #         return []

# # #     # Count token frequency across all selected row sets
# # #     token_counts = Counter()
# # #     for t_set in token_sets:
# # #         for token in t_set:
# # #             token_counts[token] += 1

# # #     total_rows = len(token_sets)
# # #     # Threshold: token must appear in at least 80% of selected rows (or at least 1 row if total_rows == 1)
# # #     threshold = max(1, int(total_rows * 0.8))

# # #     majority_tokens = [
# # #         token for token, count in token_counts.items() if count >= threshold
# # #     ]

# # #     return sorted(majority_tokens)
