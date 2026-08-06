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
    ABSOLUTE_GREEDY_BLACKLIST,
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


def is_ref_hash_or_noise(token: str) -> bool:
    """
    Detects UPI transaction hashes, reference numbers, and mixed alphanumeric strings.
    E.g., 'Q672606239', 'PYTM40905', 'YBL123', '9876543210'
    """
    if not token or not str(token).strip():
        return True

    clean_t = str(token).strip().upper()

    # Pure numbers (account/ref numbers)
    if clean_t.isdigit():
        return True

    # Alphanumeric reference strings containing BOTH letters and numbers
    if re.search(r"[A-Z]", clean_t) and re.search(r"[0-9]", clean_t):
        return True

    # Ultra long tokens (>20 chars) are usually bank hashes
    if len(clean_t) > 20:
        return True

    return False


def sanitize_user_pattern(pattern: str) -> str:
    """
    Cleans explicit user-selected patterns (e.g. 'APAN DAS', 'MARGIN FREE HYPERMAR')
    as ATOMIC phrases without splitting multi-word strings into individual tokens,
    while stripping out UPI reference hashes and numbers.
    """
    if not pattern or not str(pattern).strip():
        return ""

    # 1. Strip special characters (keep alphanumerics and spaces)
    clean_str = re.sub(r"[^A-Z0-9\.\s]", " ", str(pattern).upper())

    # 2. Collapse internal whitespace (e.g. "APAN    DAS" -> "APAN DAS")
    clean_str = re.sub(r"\s+", " ", clean_str).strip()

    if not clean_str:
        return ""

    # 3. Verify component words against blacklists AND ref hash filters
    words = clean_str.split()
    valid_words = [
        w
        for w in words
        if w not in NOISE_KEYWORD_BLACKLIST
        and w not in RULE_SAFETY_BLACKLIST
        and not is_ref_hash_or_noise(w)  # 💡 Strips out 'Q672606239', 'PYTM123', etc.
    ]

    # If every word in the pattern was noise or ref hash, reject
    if not valid_words:
        return ""

    # Reconstruct intact multi-word phrase
    return " ".join(valid_words)


def sanitize_explicit_user_pattern(pattern: str) -> str:
    """
    Bypasses standard noise blacklists (allows 'SUMEE', 'INT.PD', etc.),
    while ensuring string safety and preventing dangerous greedy catch-alls.
    """
    if not pattern or not str(pattern).strip():
        return ""

    raw = str(pattern).upper().strip()

    # 1. Reject universal system catch-alls
    if raw in ABSOLUTE_GREEDY_BLACKLIST or len(raw) < 2:
        return ""

    # 2. Convert non-alphanumerics to spaces (or preserve dots depending on matcher strategy)
    clean = re.sub(r"[^A-Z0-9\s]", " ", raw)
    clean = re.sub(r"\s+", " ", clean).strip()

    return clean


def extract_meaningful_tokens(text: str) -> list[str]:
    """
    Cleans raw statement narrations and extracts candidate words
    for auto-rule generation, filtering out blacklisted noise and ref hashes.
    """
    if not text:
        return []

    clean_str = re.sub(r"[^A-Z0-9\s]", " ", str(text).upper())
    clean_str = re.sub(r"\s+", " ", clean_str).strip()

    raw_tokens = clean_str.split()

    filtered_tokens = []
    for token in raw_tokens:
        if token in NOISE_KEYWORD_BLACKLIST or token in RULE_SAFETY_BLACKLIST:
            continue

        if is_ref_hash_or_noise(token):
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


def extract_clean_payee_pattern(narration: str) -> str:
    """Extracts true merchant/person payee name, stripping reference noise and slashes."""
    if not narration or not str(narration).strip():
        return ""

    text = str(narration).strip().upper()

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
            return token

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


def add_or_update_classification_rule(
    category: str,
    subcategory: str,
    new_pattern: str,
    entry_type: str = "Debit",
) -> bool:
    """
    Appends an explicit pattern into an existing ClassificationRule or creates a new active rule.
    Protects multi-word phrases from token-splitting, prunes loose single sub-tokens when
    compounds are learned, and keeps patterns sorted compound-first.
    """
    if not new_pattern or not str(new_pattern).strip():
        return False

    # 1. Clean explicit user selection as an ATOMIC unit (NO word splitting)
    clean_pattern = sanitize_user_pattern(new_pattern)
    if not clean_pattern:
        return False

    # 2. Single token safety validation (only applies if pattern is a single word)
    if " " not in clean_pattern:
        if (
            clean_pattern in NOISE_KEYWORD_BLACKLIST
            or clean_pattern in RULE_SAFETY_BLACKLIST
            or is_ref_hash_or_noise(clean_pattern)
        ):
            print(
                f"⚠️ Rejected unsafe single-token pattern from blacklist: '{clean_pattern}'"
            )
            return False

        if len(clean_pattern) < 4:
            print(
                f"⚠️ Rejected short single-token pattern (<4 chars): '{clean_pattern}'"
            )
            return False

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
        patterns = set(get_clean_patterns(existing_rule))
        updated_fields = ["patterns", "match_count", "updated_at"]

        if clean_pattern not in patterns:
            # 💡 FULL REVERSE PRUNING:
            # Gather all component words from all multi-word compounds (including clean_pattern)
            all_compound_words = set()
            for p in patterns:
                if " " in p:
                    all_compound_words.update(p.split())
            if " " in clean_pattern:
                all_compound_words.update(clean_pattern.split())

            # Automatically prune any single-word token that belongs to a multi-word compound
            pruned_tokens = {
                p for p in patterns if " " not in p and p in all_compound_words
            }
            if pruned_tokens:
                patterns = patterns - pruned_tokens
                print(
                    f"🧹 Pruned loose sub-tokens {pruned_tokens} from rule {existing_rule.rule_code} in favor of compound phrases"
                )

            patterns.add(clean_pattern)

            # Sort array so multi-word compound phrases ALWAYS appear first
            sorted_patterns = sorted(
                list(patterns), key=lambda x: (-len(x.split()), -len(x))
            )

            existing_rule.patterns = sorted_patterns
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

        if patterns and isinstance(patterns, list) and len(patterns) > 0:
            print(f"[ENGINE DEBUG] Using Explicit User Patterns ONLY: {patterns}")
            for user_p in patterns:
                clean_user_p = sanitize_user_pattern(user_p)
                if not clean_user_p:
                    continue

                is_compound = " " in clean_user_p
                if len(clean_user_p) >= 3 and (
                    is_compound or clean_user_p not in RULE_SAFETY_BLACKLIST
                ):
                    updated = add_or_update_classification_rule(
                        category=target_category,
                        subcategory=target_subcategory,
                        new_pattern=clean_user_p,
                        entry_type=inferred_entry_type,
                    )
                    if updated:
                        rules_updated = True
                        learned_patterns.append(clean_user_p)

        else:
            print(
                f"[ENGINE DEBUG] No explicit patterns passed. Grouped {len(entries)} items into {len(payee_groups)} distinct payee clusters:"
            )

            for payee_key, group_narrations in payee_groups.items():
                common_tokens = generate_strict_multitoken_pattern(group_narrations)

                safe_tokens = [
                    t
                    for t in common_tokens
                    if not is_ref_hash_or_noise(t)
                    and t.upper() not in NOISE_KEYWORD_BLACKLIST
                    and t.upper() not in RULE_SAFETY_BLACKLIST
                    and len(t) > 2
                ]

                print(
                    f"    --> Cluster '{payee_key}': Extracted Safe Tokens = {safe_tokens}"
                )

                if safe_tokens:
                    capped_tokens = safe_tokens[:2]
                    compound_pattern = " ".join(capped_tokens)

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


# region older

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
# from tracker.constants import (
#     NOISE_KEYWORD_BLACKLIST,
#     GENERIC_IGNORE_PATTERNS,
#     GENERIC_PATTERNS,
#     KNOWN_MERCHANTS,
#     RULE_SAFETY_BLACKLIST,
# )

# GENERIC_NOISE_TOKENS = NOISE_KEYWORD_BLACKLIST


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


# def sanitize_user_pattern(pattern: str) -> str:
#     """
#     Cleans explicit user-selected patterns (e.g. 'APAN DAS', 'MARGIN FREE HYPERMAR')
#     as ATOMIC phrases without splitting multi-word strings into individual tokens.
#     """
#     if not pattern or not str(pattern).strip():
#         return ""

#     # 1. Strip special characters (keep alphanumerics and spaces)
#     clean_str = re.sub(r"[^A-Z0-9\s]", " ", str(pattern).upper())

#     # 2. Collapse internal whitespace (e.g. "APAN    DAS" -> "APAN DAS")
#     clean_str = re.sub(r"\s+", " ", clean_str).strip()

#     if not clean_str:
#         return ""

#     # 3. Verify component words against blacklists
#     words = clean_str.split()
#     valid_words = [
#         w
#         for w in words
#         if w not in NOISE_KEYWORD_BLACKLIST and w not in RULE_SAFETY_BLACKLIST
#     ]

#     # If every word in the pattern was blacklisted noise, reject
#     if not valid_words:
#         return ""

#     # Reconstruct intact multi-word phrase
#     return " ".join(valid_words)


# def extract_meaningful_tokens(text: str) -> list[str]:
#     """
#     Cleans raw statement narrations and extracts candidate words
#     for auto-rule generation, filtering out blacklisted noise.
#     """
#     if not text:
#         return []

#     # 1. Clean special characters and normalize whitespace
#     clean_str = re.sub(r"[^A-Z0-9\s]", " ", str(text).upper())
#     clean_str = re.sub(r"\s+", " ", clean_str).strip()

#     # 2. Split into individual words
#     raw_tokens = clean_str.split()

#     filtered_tokens = []
#     for token in raw_tokens:
#         # Check against centralized constants
#         if token in NOISE_KEYWORD_BLACKLIST or token in RULE_SAFETY_BLACKLIST:
#             continue

#         # Filter out pure numbers and ultra-long ref hashes
#         if token.isdigit() or len(token) > 25:
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

#     # 1. POS bracket extraction e.g. POS TRN/ ID NO. (AZAD GROUP HOTELS TR)
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
#             return token  # 🎯 Returns clean "ZOMATO" or "BLINKIT" immediately!

#     # 3. Fallback: Take top tokens but ignore trailing person names/noise if merchant/action word present
#     clean_tokens = tokens[:2] if len(tokens) >= 2 else tokens
#     return " ".join(clean_tokens)


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
#     """
#     Appends an explicit pattern into an existing ClassificationRule or creates a new active rule.
#     Protects multi-word phrases from token-splitting, prunes loose single sub-tokens when
#     compounds are learned, and keeps patterns sorted compound-first.
#     """
#     if not new_pattern or not str(new_pattern).strip():
#         return False

#     # 1. Clean explicit user selection as an ATOMIC unit (NO word splitting)
#     clean_pattern = sanitize_user_pattern(new_pattern)
#     if not clean_pattern:
#         return False

#     # 2. Single token safety validation (only applies if pattern is a single word)
#     if " " not in clean_pattern:
#         if (
#             clean_pattern in NOISE_KEYWORD_BLACKLIST
#             or clean_pattern in RULE_SAFETY_BLACKLIST
#         ):
#             print(
#                 f"⚠️ Rejected unsafe single-token pattern from blacklist: '{clean_pattern}'"
#             )
#             return False

#         if len(clean_pattern) < 4:
#             print(
#                 f"⚠️ Rejected short single-token pattern (<4 chars): '{clean_pattern}'"
#             )
#             return False

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
#         patterns = set(get_clean_patterns(existing_rule))
#         updated_fields = ["patterns", "match_count", "updated_at"]

#         if clean_pattern not in patterns:
#             # 💡 REVERSE PRUNING: When adding a multi-word compound (e.g. "APAN DAS" or "MARGIN FREE"),
#             # automatically prune loose single sub-tokens ("APAN", "DAS", "MARGIN", "FREE") from the rule.
#             if " " in clean_pattern:
#                 sub_words = set(clean_pattern.split())
#                 pruned_tokens = {p for p in patterns if p in sub_words}
#                 if pruned_tokens:
#                     patterns = patterns - pruned_tokens
#                     print(
#                         f"🧹 Pruned loose sub-tokens {pruned_tokens} from rule {existing_rule.rule_code} in favor of compound '{clean_pattern}'"
#                     )

#             patterns.add(clean_pattern)

#             # Sort array so multi-word compound phrases ALWAYS appear first
#             sorted_patterns = sorted(
#                 list(patterns), key=lambda x: (-len(x.split()), -len(x))
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
#         print("\n" + "🔍" * 40)
#         print(f"[ENGINE DEBUG] Learning Rules for Subcategory: '{target_subcategory}'")

#         # -------------------------------------------------------------------------
#         # PATH A: Explicit User Patterns Passed from Frontend UI (Highest Priority)
#         # ONLY runs when user manually selects tokens in the modal.
#         # -------------------------------------------------------------------------
#         if patterns and isinstance(patterns, list) and len(patterns) > 0:
#             print(f"[ENGINE DEBUG] Using Explicit User Patterns ONLY: {patterns}")
#             for user_p in patterns:
#                 clean_user_p = str(user_p).strip().upper()

#                 # Check for length and skip direct single-token blacklist hits
#                 # (Allows compound phrases like 'AMAZON INDIA' or 'MARGIN FREE')
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

#         # -------------------------------------------------------------------------
#         # PATH B: Controlled Auto-Extraction with Strict Safety Guardrails
#         # Fallback path ONLY when frontend provides ZERO explicit user choices.
#         # -------------------------------------------------------------------------
#         else:
#             print(
#                 f"[ENGINE DEBUG] No explicit patterns passed. Grouped {len(entries)} items into {len(payee_groups)} distinct payee clusters:"
#             )

#             for payee_key, group_narrations in payee_groups.items():
#                 common_tokens = generate_strict_multitoken_pattern(group_narrations)

#                 # Filter out numbers, blacklist words, and generic city/store names
#                 safe_tokens = [
#                     t
#                     for t in common_tokens
#                     if not re.search(r"\d", t)
#                     and t.upper() not in NOISE_KEYWORD_BLACKLIST
#                     and t.upper() not in RULE_SAFETY_BLACKLIST
#                     and len(t) > 2
#                 ]

#                 print(
#                     f"    --> Cluster '{payee_key}': Extracted Safe Tokens = {safe_tokens}"
#                 )

#                 if safe_tokens:
#                     # Cap at max 2 anchor tokens (e.g. "SKECHERS", "LULU PARKING")
#                     capped_tokens = safe_tokens[:2]
#                     compound_pattern = " ".join(capped_tokens)

#                     # Only proceed if pattern meets minimum length requirement
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

#         print("🔍" * 40 + "\n")

#     return {
#         "status": "success",
#         "reclassified_count": len(entries),
#         "entry_type_bound": inferred_entry_type,
#         "rules_updated": rules_updated,
#         "patterns_learned": learned_patterns,
#     }

# end region
