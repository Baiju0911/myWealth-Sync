# backend/tracker/parsers/parsers_v1/strategies/registry.py
from . import strict_matrix
from . import relative_matrix

# Add your future strategies here as your platform grows
STRATEGY_ROUTING_TABLE = {
    "STRICT_MATRIX": strict_matrix,
    "RELATIVE_MATRIX": relative_matrix,
}


def get_strategy_by_identifier(strategy_identifier):
    """
    Looks up the explicit strategy code from your template DB model.
    Defaults to strict_matrix if no match is found.
    """
    return STRATEGY_ROUTING_TABLE.get(strategy_identifier, strict_matrix)
