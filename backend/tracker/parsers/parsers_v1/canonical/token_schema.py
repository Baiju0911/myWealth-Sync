# trackers/parsers/parsers_v1/canonical/token_schema.py

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class CanonicalToken:
    """
    Unified Data Contract for Document Layout Elements.
    Translates arbitrary engine points/pixels into standardized page percentages.
    """

    text: str  # The raw alphanumeric string captured
    x_pct: float  # Horizontal anchor point (0.00 to 100.00)
    y_pct: float  # Vertical anchor point (0.00 to 100.00)
    w_pct: float  # Width of token relative to page width (0.00 to 100.00)
    h_pct: float  # Height of token relative to page height (0.00 to 100.00)
    page_num: int  # 1-indexed page track identifier

    def to_dict(self) -> dict:
        """Utility serialization method for frontend JSON canvas communication."""
        return asdict(self)
