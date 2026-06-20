# backend/tracker/parsers/parsersv1.0/resolver.py


# backend/tracker/parsers_v1/resolver.py


def resolve_strategy(profile_vector):
    """
    TRAFFIC CONTROLLER / PREDICTOR:
    Analyzes physical structural layout vector traits of an UNKNOWN PDF
    and predicts which domain strategy name it should use.
    """
    # Trait A: Fixed bounding lanes, strict vertical grid columns (FED, SIB, etc.)
    if profile_vector.get("is_fixed_layout") or profile_vector.get("is_matrix_grid"):
        return "GRID_COLUMN_FLOW"

    # Trait B: Dynamic line elements, transaction values fused inline (SBI, etc.)
    elif profile_vector.get("has_dr_cr_indicator") or profile_vector.get(
        "is_relative_narrative"
    ):
        return "NARRATIVE_INLINE_FLOW"

    # Fallback Option
    else:
        return "GRID_COLUMN_FLOW"


# # backend/tracker/parsers/parsersv1.0/resolver.py


# def resolve_strategy(profile_vector):
#     """
#     Traffic Controller:
#     Decides the strategy based on the vector, not the bank name.
#     """

#     # Logic: If it has columns, use the Matrix Strategy
#     if profile_vector["is_fixed_layout"]:
#         return "STRICT_MATRIX"

#     # Logic: If it has explicit DR/CR markers on rows
#     elif profile_vector["has_dr_cr_indicator"]:
#         return "DR_CR_LAYOUT"

#     # Logic: If neither, default to the most flexible strategy
#     else:
#         return "RELATIVE_SEQUENCE"
