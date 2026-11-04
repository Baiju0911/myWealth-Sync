# tracker/classification/engine/rule_learning_helpers.py
from __future__ import annotations
import hashlib
import json
import re
from collections import Counter
from typing import List, Optional, Set

from tracker.models.models import ClassificationRule, TaxonomyTree
from tracker.constants import (
    ABSOLUTE_GREEDY_BLACKLIST,
    KNOWN_MERCHANTS,
    NOISE_KEYWORD_BLACKLIST,
    OK_WORD_LIST,
    RULE_SAFETY_BLACKLIST,
)
from .tagging_helpers import TaggingEngine


class RuleLearningEngine:
    """Manages pattern sanitization, anti-corruption pruning, and rule learning."""

    @staticmethod
    def sanitize_user_pattern(pattern: str) -> str:
        """Sanitizes user patterns as an atomic phrase, rejecting reference noise."""
        if not pattern or not str(pattern).strip():
            return ""

        clean_str = re.sub(r"[^A-Z0-9\.\s]", " ", str(pattern).upper())
        clean_str = re.sub(r"\s+", " ", clean_str).strip()
        if not clean_str:
            return ""

        words = clean_str.split()
        valid_words = [
            w
            for w in words
            if w not in NOISE_KEYWORD_BLACKLIST
            and w not in RULE_SAFETY_BLACKLIST
            and not TaggingEngine.is_ref_hash_or_noise(w)
        ]

        if not valid_words:
            return ""

        return " ".join(valid_words)

    @staticmethod
    def get_clean_patterns(rule) -> List[str]:
        """Extracts clean patterns list from model or dict."""
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

    @staticmethod
    def match_multi_tokens(
        narration: str, pattern: str, min_required_tokens: int = 2
    ) -> bool:
        """Validates if narration contains pattern tokens."""
        if not narration or not pattern:
            return False

        narration_tokens = set(TaggingEngine.extract_meaningful_tokens(narration))
        pattern_tokens = set(TaggingEngine.extract_meaningful_tokens(pattern))

        if not pattern_tokens:
            return False

        if len(pattern_tokens) < min_required_tokens:
            condensed_narration = TaggingEngine.normalize_condensed(narration)
            condensed_pattern = TaggingEngine.normalize_condensed(pattern)
            return (
                len(condensed_pattern) >= 6 and condensed_pattern in condensed_narration
            )

        if pattern_tokens.issubset(narration_tokens):
            return True

        condensed_narration = TaggingEngine.normalize_condensed(narration)
        condensed_pattern = TaggingEngine.normalize_condensed(pattern)
        return len(condensed_pattern) >= 6 and condensed_pattern in condensed_narration

    @classmethod
    def generate_strict_multitoken_pattern(cls, narration_list: List[str]) -> List[str]:
        """Finds tokens present in >=80% of narrations."""
        if not narration_list:
            return []

        token_sequences = [
            TaggingEngine.extract_meaningful_tokens(n) for n in narration_list if n
        ]
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
            t for t, count in token_counts.items() if count >= threshold
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

    @classmethod
    def add_or_update_classification_rule(
        cls,
        category: str,
        subcategory: str,
        new_pattern: str,
        entry_type: str = "Debit",
    ) -> bool:
        """Appends pattern to ClassificationRule safely without token pollution."""
        if not new_pattern or not str(new_pattern).strip():
            return False

        clean_pattern = cls.sanitize_user_pattern(new_pattern)
        if not clean_pattern:
            return False

        clean_pattern = clean_pattern.upper().strip()

        # Single-token safety checks
        if " " not in clean_pattern:
            if (
                clean_pattern in NOISE_KEYWORD_BLACKLIST
                or clean_pattern in RULE_SAFETY_BLACKLIST
                or TaggingEngine.is_ref_hash_or_noise(clean_pattern)
            ):
                return False

            if len(clean_pattern) < 4 and clean_pattern not in OK_WORD_LIST:
                return False

        clean_entry_type = (
            "Credit" if str(entry_type).strip().lower() == "credit" else "Debit"
        )
        resolved_taxonomy = TaxonomyTree.objects.filter(
            category__iexact=category, subcategory__iexact=subcategory
        ).first()

        existing_rule = ClassificationRule.objects.filter(
            target_category=category,
            target_subcategory=subcategory,
            rule_type=clean_entry_type,
            is_active=True,
        ).first()

        if existing_rule:
            patterns = {
                p.upper().strip() for p in cls.get_clean_patterns(existing_rule) if p
            }
            updated_fields = ["patterns", "match_count", "updated_at"]

            if clean_pattern not in patterns:
                # 1. Prune loose tokens if covered by compound phrases
                all_compound_words: Set[str] = set()
                for p in patterns:
                    if " " in p:
                        all_compound_words.update(p.split())
                if " " in clean_pattern:
                    all_compound_words.update(clean_pattern.split())

                pruned_tokens = {
                    p
                    for p in patterns
                    if " " not in p
                    and p in all_compound_words
                    and p not in KNOWN_MERCHANTS
                    and p not in OK_WORD_LIST
                }
                if pruned_tokens:
                    patterns = patterns - pruned_tokens

                # 2. Reverse Prune compounds covered by single-word brand anchors
                active_brand_anchors = {
                    p
                    for p in (patterns | {clean_pattern})
                    if " " not in p and p in KNOWN_MERCHANTS
                }
                redundant_compounds = {
                    p
                    for p in patterns
                    if " " in p
                    and any(brand in p.split() for brand in active_brand_anchors)
                }
                if redundant_compounds:
                    patterns = patterns - redundant_compounds

                patterns.add(clean_pattern)
                sorted_patterns = sorted(
                    list(patterns), key=lambda x: (-len(x.split()), -len(x), x)
                )

                existing_rule.patterns = sorted_patterns
                existing_rule.match_count = (existing_rule.match_count or 0) + 1

                if not existing_rule.taxonomy and resolved_taxonomy:
                    existing_rule.taxonomy = resolved_taxonomy
                    updated_fields.append("taxonomy")

                existing_rule.save(update_fields=updated_fields)
                return True
            return False

        # Create new rule
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
        return True
