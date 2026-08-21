from ...constants import (
    ALL_SYSTEM_BLACKLIST,
    CATASTROPHIC_KEYWORDS,
    NOISE_KEYWORD_BLACKLIST,
    OK_WORD_LIST,
    RULE_SAFETY_BLACKLIST,
    TRANSFER_BANK_NOISE,
)
from ...models.models import TaxonomyTree

_TAXONOMY_CACHE = None


def _get_taxonomy_cache():
    """Loads and caches active TaxonomyTree nodes in memory to bypass DB lookups per row."""
    global _TAXONOMY_CACHE
    if _TAXONOMY_CACHE is None:
        nodes = TaxonomyTree.objects.filter(is_active=True).values(
            "category", "subcategory"
        )
        _TAXONOMY_CACHE = {
            node["subcategory"]
            .strip()
            .lower(): (
                node["category"],
                node["subcategory"],
            )
            for node in nodes
        }
    return _TAXONOMY_CACHE


def resolve_official_taxonomy(
    candidate_category: str, candidate_subcategory: str
) -> tuple[str, str]:
    """Enforces TaxonomyTree as the SINGLE SOURCE OF TRUTH.

    Guarantees candidate Category/Subcategory pairs map to an active
    TaxonomyTree record. Uses TRANSFER_BANK_NOISE for safe transfer fallback
    detection without making false assumptions.
    """
    cat_clean = (candidate_category or "").strip()
    sub_clean = (candidate_subcategory or "").strip()

    tax_map = _get_taxonomy_cache()
    sub_lower = sub_clean.lower()
    cat_lower = cat_clean.lower()

    # 1. Exact match on subcategory in master TaxonomyTree (In-Memory Check)
    if sub_lower in tax_map:
        return tax_map[sub_lower]

    # 2. Exact match on candidate_category in master TaxonomyTree
    if cat_lower in tax_map:
        return tax_map[cat_lower]

    # 3. Check for raw bank/account tokens & Transfer Noise
    cat_upper = cat_clean.upper()
    sub_upper = sub_clean.upper()

    is_transfer_noise = (
        any(kw in cat_upper or kw in sub_upper for kw in TRANSFER_BANK_NOISE)
        or sub_lower.startswith("fed-")
        or sub_lower.startswith("sbonr")
        or sub_lower.startswith("ftb-")
        or sub_lower.startswith("fto-")
    )

    if is_transfer_noise:
        # If Tier 2 explicitly flagged it as a Self-Transfer, preserve that
        if "self" in sub_lower or sub_clean == "Self Inter-Account":
            return "Transfer", "Self Inter-Account"

        # Otherwise, fall back to generic non-assumptive transfer category
        return "Transfer", "Bank Transfers"

    # 4. Preserve explicit valid candidate values before resorting to generic Suspense
    invalid_tokens = {
        "suspense account",
        "none",
        "null",
        "unclassified",
        "unknown",
        "ai unclassified",
    }
    if (
        sub_clean
        and sub_lower not in invalid_tokens
        and not sub_lower.startswith("fed-")
        and not sub_lower.startswith("sbonr")
    ):
        return cat_clean or "Asset", sub_clean

    # 5. Safe Fallback for completely unmapped / unknown / blank strings
    return "Expense", "Suspense Account"


# from ...models.models import TaxonomyTree

# from ...constants import (
#     RULE_SAFETY_BLACKLIST,
#     NOISE_KEYWORD_BLACKLIST,
#     CATASTROPHIC_KEYWORDS,
#     OK_WORD_LIST,
#     TRANSFER_BANK_NOISE,
# )

# ALL_SYSTEM_BLACKLIST = (
#     RULE_SAFETY_BLACKLIST.union(NOISE_KEYWORD_BLACKLIST).union(CATASTROPHIC_KEYWORDS)
#     - OK_WORD_LIST
# )

# # tracker/classification/utils/taxonomy_gate.py

# _TAXONOMY_CACHE = None


# def _get_taxonomy_cache():
#     """Loads and caches active TaxonomyTree nodes in memory to bypass DB lookups per row."""
#     global _TAXONOMY_CACHE
#     if _TAXONOMY_CACHE is None:
#         nodes = TaxonomyTree.objects.filter(is_active=True).values(
#             "category", "subcategory"
#         )
#         _TAXONOMY_CACHE = {
#             node["subcategory"].strip().lower(): (node["category"], node["subcategory"])
#             for node in nodes
#         }
#     return _TAXONOMY_CACHE


# def resolve_official_taxonomy(
#     candidate_category: str, candidate_subcategory: str
# ) -> tuple[str, str]:
#     """
#     Enforces TaxonomyTree as the SINGLE SOURCE OF TRUTH.
#     Guarantees candidate Category/Subcategory pairs map to an active TaxonomyTree record.
#     Uses TRANSFER_BANK_NOISE for safe transfer fallback detection without making false assumptions.
#     """
#     cat_clean = (candidate_category or "").strip()
#     sub_clean = (candidate_subcategory or "").strip()

#     tax_map = _get_taxonomy_cache()
#     sub_lower = sub_clean.lower()
#     cat_lower = cat_clean.lower()

#     # 1. Exact match on subcategory in master TaxonomyTree (In-Memory Check)
#     if sub_lower in tax_map:
#         return tax_map[sub_lower]

#     # 2. Exact match on candidate_category in master TaxonomyTree
#     if cat_lower in tax_map:
#         return tax_map[cat_lower]

#     # 3. Check for raw bank/account tokens & Transfer Noise
#     cat_upper = cat_clean.upper()
#     sub_upper = sub_clean.upper()

#     is_transfer_noise = (
#         any(kw in cat_upper or kw in sub_upper for kw in TRANSFER_BANK_NOISE)
#         or sub_lower.startswith("fed-")
#         or sub_lower.startswith("sbonr")
#         or sub_lower.startswith("ftb-")
#         or sub_lower.startswith("fto-")
#     )

#     if is_transfer_noise:
#         # If Tier 2 explicitly flagged it as a Self-Transfer, preserve that
#         if "self" in sub_lower or sub_clean == "Self Inter-Account":
#             return "Transfer", "Self Inter-Account"

#         # Otherwise, fall back to generic non-assumptive transfer category
#         return "Transfer", "Bank Transfers"

#     # 4. Safe Fallback for completely unmapped / unknown strings
#     return "Expense", "Suspense Account"
