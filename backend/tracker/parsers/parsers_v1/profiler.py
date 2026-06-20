# backend/tracker/parsersv1.0/profiler.py
import re


def create_profile(raw_structure):
    """
    Analyzes the structure to build a Profile Vector.
    This vector dictates the Strategy without needing bank-specific logic.
    """
    all_tokens = [t for page in raw_structure for t in page["tokens"]]

    # Analyze column alignment (Profiler logic)
    # Check if numbers are clustered into specific 'lanes' (Fixed Columns)
    x_coords = [t["x"] for t in all_tokens if re.match(r"^\d+\.?\d*$", t["text"])]

    # Logic to detect 'Fixed' vs 'Relative'
    # If numbers have high variance in X-position, it's RELATIVE_SEQUENCE.
    # If they cluster in 2-3 distinct X-bands, it's STRICT_MATRIX.

    profile_vector = {
        "has_dr_cr_indicator": any(
            "DR" in t["text"].upper() or "CR" in t["text"].upper() for t in all_tokens
        ),
        "amount_column_count": 0,  # Logic to count clusters
        "is_fixed_layout": False,  # Logic based on x_coords variance
        "confidence": 0.95,
    }

    return profile_vector
