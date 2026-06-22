# trackers/parsers/parsers_v1/geometry/lane_detector.py

from typing import List, Dict, Optional
from .clusterer import GeometricRow
import re


class StructuredRow:
    """A row where spatial tokens have been mapped into explicit bank column buckets."""

    def __init__(self):
        self.date: str = ""
        self.narration: str = ""
        self.debit: str = ""
        self.credit: str = ""
        self.balance: str = ""
        self.raw_baseline_y: float = 0.0

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "narration": self.narration,
            "debit": self.debit,
            "credit": self.credit,
            "balance": self.balance,
        }


def map_row_to_lanes(
    row: GeometricRow, lane_config: Dict[str, Dict[str, float]]
) -> StructuredRow:
    """
    Maps tokens inside a GeometricRow into explicit column keys based on X-axis percentage boundaries.

    lane_config format example:
    {
        "date": {"x_start": 0.0, "x_end": 20.0},
        "narration": {"x_start": 20.0, "x_end": 50.0},
        "debit": {"x_start": 50.0, "x_end": 65.0},
        "credit": {"x_start": 65.0, "x_end": 80.0},
        "balance": {"x_start": 80.0, "x_end": 100.0}
    }
    """
    structured = StructuredRow()
    structured.raw_baseline_y = row.baseline_y

    # Buffers to collect strings landing in the same vertical slot
    lane_buffers: Dict[str, List[str]] = {key: [] for key in lane_config.keys()}

    for token in row.tokens:
        assigned = False
        # Match token center or start point to predefined lanes
        token_x = token.x_pct

        for lane_name, bounds in lane_config.items():
            if bounds["x_start"] <= token_x <= bounds["x_end"]:
                lane_buffers[lane_name].append(token.text)
                assigned = True
                break

        # Fallback to absolute closest lane if a token slips through boundary cracks
        if not assigned:
            closest_lane = min(
                lane_config.keys(),
                key=lambda k: min(
                    abs(token_x - lane_config[k]["x_start"]),
                    abs(token_x - lane_config[k]["x_end"]),
                ),
            )
            lane_buffers[closest_lane].append(token.text)

    # Flatten collected lists into final sanitized text values
    structured.date = " ".join(lane_buffers.get("date", [])).strip()
    structured.narration = " ".join(lane_buffers.get("narration", [])).strip()
    structured.debit = " ".join(lane_buffers.get("debit", [])).strip()
    structured.credit = " ".join(lane_buffers.get("credit", [])).strip()
    structured.balance = " ".join(lane_buffers.get("balance", [])).strip()

    return structured


def extract_structured_dataset(
    rows: List[GeometricRow], lane_config: Dict[str, Dict[str, float]]
) -> List[StructuredRow]:
    """Processes a comprehensive page array of GeometricRows against our structural lane mappings."""
    return [map_row_to_lanes(row, lane_config) for row in rows]


def clean_transaction_row_noise(raw_row_data: list) -> dict:
    """
    Cleans structural noise artifacts (stray currency symbols, layout flags)
    and formats transaction rows cleanly.
    """
    # 1. Skip non-transactional global metadata blocks entirely
    row_string = " ".join([str(item) for item in raw_row_data])
    if any(
        keyword in row_string
        for keyword in ["CUSTOMER ID", "ACCOUNT STATUS", "BANKING PARTNER", "Page"]
    ):
        return None

    cleaned_tokens = []
    for token in raw_row_data:
        text = str(token).strip()

        # Strip structural characters and isolated currency markers
        text = re.sub(r"(^₹+$|^NEW$|^-+$)", "", text)
        if not text:
            continue

        cleaned_tokens.append(text)

    return cleaned_tokens
