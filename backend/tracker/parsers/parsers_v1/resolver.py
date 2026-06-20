# backend/tracker/parsersv1.0/resolver.py


def resolve_strategy(profile_vector):
    """
    Traffic Controller:
    Decides the strategy based on the vector, not the bank name.
    """

    # Logic: If it has columns, use the Matrix Strategy
    if profile_vector["is_fixed_layout"]:
        return "STRICT_MATRIX"

    # Logic: If it has explicit DR/CR markers on rows
    elif profile_vector["has_dr_cr_indicator"]:
        return "DR_CR_LAYOUT"

    # Logic: If neither, default to the most flexible strategy
    else:
        return "RELATIVE_SEQUENCE"
