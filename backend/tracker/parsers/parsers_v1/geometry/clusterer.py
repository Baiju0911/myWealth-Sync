# trackers/parsers/parsers_v1/geometry/clusterer.py

from typing import List, Dict
from ..canonical.token_schema import CanonicalToken


class GeometricRow:
    """Represents a collection of spatial tokens aligned along a single horizontal path."""

    def __init__(self, baseline_y: float):
        self.baseline_y = baseline_y
        self.tokens: List[CanonicalToken] = []

    def add_token(self, token: CanonicalToken):
        self.tokens.append(token)
        # Dynamic baseline adjustment using running average
        self.baseline_y = sum(t.y_pct for t in self.tokens) / len(self.tokens)

    def sort_horizontally(self):
        """Sorts tokens inside this row from left to right."""
        self.tokens.sort(key=lambda token: token.x_pct)

    @property
    def text_content(self) -> str:
        """Helper to print or scan the entire line quickly."""
        return " ".join(t.text for t in self.tokens)


def cluster_tokens_into_rows(
    tokens: List[CanonicalToken], delta_y: float = 0.5
) -> List[GeometricRow]:
    if not tokens:
        return []

    # FIX: Ensure variable name matches throughout the loop block
    sorted_tokens = sorted(tokens, key=lambda t: t.y_pct)

    rows: List[GeometricRow] = []

    for token in sorted_tokens:  # <-- Fixed from sorted_by_y to sorted_tokens
        assigned = False
        for row in rows:
            if abs(token.y_pct - row.baseline_y) <= delta_y:
                row.add_token(token)
                assigned = True
                break
        if not assigned:
            new_row = GeometricRow(baseline_y=token.y_pct)
            new_row.add_token(token)
            rows.append(new_row)

    rows.sort(key=lambda r: r.baseline_y)
    for row in rows:
        row.sort_horizontally()

    return rows
