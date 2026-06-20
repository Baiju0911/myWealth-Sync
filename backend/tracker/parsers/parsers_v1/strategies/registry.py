from . import strict_matrix
from . import relative_matrix

# ─── 🔄 THE MASTER STRATEGY ROUTING TABLE ───
# Maps both clean domain terminology and legacy structural names to the code engines
STRATEGY_ROUTING_TABLE = {
    # New domain-driven nomenclature
    "GRID_COLUMN_FLOW": strict_matrix,
    "NARRATIVE_INLINE_FLOW": relative_matrix,
    # Legacy compatibility fallback keys
    "STRICT_MATRIX": strict_matrix,
    "RELATIVE_MATRIX": relative_matrix,
    "RELATIVE_SEQUENCE": relative_matrix,
}


def get_strategy_by_identifier(strategy_identifier):
    """
    Looks up the explicit strategy code from your template DB model.
    Defaults to strict_matrix (GRID_COLUMN_FLOW) if no match is found.
    """
    if not strategy_identifier:
        return strict_matrix

    # Clean string input to protect against casing mismatches
    lookup_key = str(strategy_identifier).strip().upper()

    return STRATEGY_ROUTING_TABLE.get(lookup_key, strict_matrix)
