# tracker/parsers/parsers_v1/confidence/evaluator.py

import re
import logging
from typing import List
from ..geometry.lane_detector import StructuredRow

logger = logging.getLogger(__name__)


class ConfidenceEvaluator:
    # Pre-compile patterns to avoid overhead inside high-frequency execution loops
    DATE_PATTERN = re.compile(r"\d{2,4}[-/\.]\d{2}[-/\.]\d{2,4}")

    # 🎯 HARDENED BOUNDARY WORDS: Only skip formal page structures, never conversational narratives
    SUMMARY_FILTER_WORDS = {
        "page total:",
        "grand total:",
        "brought forward",
        "carried forward",
        "eff avl amt",
        "statement of account",
    }

    @staticmethod
    def clean_numeric(val_str: str) -> float:
        """
        🔒 SIGN-AWARE MONETARY SANITIZER:
        Converts financial text blocks into valid floats. Realizes trailing
        DR / CR indicators to handle overdraft accounting math flawlessly.
        """
        if not val_str:
            return 0.0
        if isinstance(val_str, (int, float)):
            return float(val_str)

        val_upper = str(val_str).upper().strip()

        # Isolate clean numeric digits and decimal anchors
        sanitized = re.sub(r"[^\d\.]", "", val_upper.replace(",", ""))
        if not sanitized:
            return 0.0

        try:
            magnitude = float(sanitized)
            # 🎯 THE SIGN OVERRIDE SHIELD: Flip sign to negative if the transaction reflects a debt position
            if "DR" in val_upper:
                return -magnitude
            return magnitude
        except ValueError:
            return 0.0

    @classmethod
    def evaluate_dataset(cls, rows: List[StructuredRow]) -> int:
        if not rows:
            return 0

        # ─── STEP 1: PRE-FILTERING & CONTEXT CLEANUP ───
        valid_tx_rows = []
        for r in rows:
            narration_lower = str(r.narration).lower()

            # Skip page headers/footers noise signatures cleanly
            if any(term in narration_lower for term in cls.SUMMARY_FILTER_WORDS):
                continue
            if "------" in str(r.date) or "------" in str(r.narration):
                continue

            dr_cleaned = cls.clean_numeric(r.debit)
            cr_cleaned = cls.clean_numeric(r.credit)
            bal_str_clean = str(r.balance).strip()

            # A valid transactional row anchor needs a date and at least one operational metric value
            if bool(str(r.date).strip()) and (
                dr_cleaned != 0.0 or cr_cleaned != 0.0 or bal_str_clean != ""
            ):
                # Enforce that table header text layers don't slip into our evaluation sets
                if (
                    "PARTICULARS" in str(r.narration).upper()
                    or "WITHDRAWALS" in str(r.narration).upper()
                ):
                    continue
                valid_tx_rows.append((r, dr_cleaned, cr_cleaned))

        total_tx_count = len(valid_tx_rows)
        if total_tx_count == 0:
            return 0

        confidence = 20  # Structural baseline anchor base
        date_matches = 0
        amount_matches = 0
        narration_matches = 0
        balance_math_passes = 0

        # ─── STEP 2: MULTI-STRATEGY LEDGER CALCULATOR ───
        for i, (row, debit_val, credit_val) in enumerate(valid_tx_rows):
            # 1. Date Validation Pass
            if cls.DATE_PATTERN.search(str(row.date)):
                date_matches += 1

            # 2. Narration Validation Pass
            if len(str(row.narration).strip()) >= 3:
                narration_matches += 1

            # 3. Target Operational Amount Check
            if debit_val != 0.0 or credit_val != 0.0:
                amount_matches += 1

            # 4. Running Balance Vector Calculations
            curr_balance = cls.clean_numeric(row.balance)

            if i > 0:
                prev_row_balance = cls.clean_numeric(valid_tx_rows[i - 1][0].balance)

                actual_balance = round(curr_balance, 2)

                # Standard double-entry balance computation map tracking values
                standard_computed = round(prev_row_balance - debit_val + credit_val, 2)

                active_amount = credit_val if credit_val != 0.0 else debit_val
                single_col_addition = round(prev_row_balance + active_amount, 2)
                single_col_subtraction = round(prev_row_balance - active_amount, 2)

                # Vector margin match verification check (Allows for small rounding variances)
                if (
                    abs(standard_computed - actual_balance) <= 0.05
                    or abs(single_col_addition - actual_balance) <= 0.05
                    or abs(single_col_subtraction - actual_balance) <= 0.05
                ):
                    balance_math_passes += 1
                else:
                    # Clear trace output diagnostic logs track visibility parameters inline
                    pass
            else:
                # The first row baseline is evaluated against the seed anchor directly
                if curr_balance != 0.0:
                    balance_math_passes += 1

        # ─── STEP 3: SCORE RATIO COMPILATION ───
        pillars = {
            "Date": date_matches / total_tx_count,
            "Narr": narration_matches / total_tx_count,
            "Amt": amount_matches / total_tx_count,
            "Math": balance_math_passes / total_tx_count,
        }

        print(
            f"📊 Pillar Scores -> Date: {pillars['Date']:.2f} | Narr: {pillars['Narr']:.2f} | "
            f"Amt: {pillars['Amt']:.2f} | Math: {pillars['Math']:.2f}"
        )

        for score_pct in pillars.values():
            if score_pct >= 0.95:
                confidence += 20

        return confidence


# # tracker/parsers/parsers_v1/confidence/evaluator.py

# import re
# from typing import List
# from ..geometry.lane_detector import StructuredRow


# class ConfidenceEvaluator:
#     # Pre-compile patterns to avoid overhead inside high-frequency execution loops
#     DATE_PATTERN = re.compile(r"\d{2,4}[-/\.]\d{2}[-/\.]\d{2,4}")
#     SUMMARY_FILTER_WORDS = {
#         "total",
#         "page",
#         "grand",
#         "opening balance",
#         "closing balance",
#         "brought forward",
#         "carried forward",
#         "b/f",
#         "c/f",
#         "opnbal",
#         "statement of account",
#         "particulars",
#         "withdrawals",
#         "deposits",
#     }

#     @staticmethod
#     def clean_numeric(val_str: str) -> float:
#         """Sanitizes text strings or numbers into valid float objects."""
#         if not val_str:
#             return 0.0
#         if isinstance(val_str, (int, float)):
#             return float(val_str)

#         sanitized = re.sub(r"[^\d\.\-]", "", str(val_str).replace(",", ""))
#         try:
#             return float(sanitized) if sanitized else 0.0
#         except ValueError:
#             return 0.0

#     @classmethod
#     def evaluate_dataset(cls, rows: List[StructuredRow]) -> int:
#         if not rows:
#             return 0

#         # ─── STEP 1: PRE-FILTERING & SUMMARY CLEANUP ──────────────────────────
#         valid_tx_rows = []
#         for r in rows:
#             narration_lower = str(r.narration).lower()
#             if any(term in narration_lower for term in cls.SUMMARY_FILTER_WORDS):
#                 continue

#             # Cache values to prevent repetitive execution inside conditions
#             dr_cleaned = cls.clean_numeric(r.debit)
#             cr_cleaned = cls.clean_numeric(r.credit)

#             if bool(str(r.date).strip()) and (
#                 dr_cleaned != 0.0 or cr_cleaned != 0.0 or str(r.balance).strip() != ""
#             ):
#                 valid_tx_rows.append((r, dr_cleaned, cr_cleaned))

#         total_tx_count = len(valid_tx_rows)
#         if total_tx_count == 0:
#             return 0

#         confidence = 20  # Structural base baseline anchor score
#         date_matches = 0
#         amount_matches = 0
#         narration_matches = 0
#         balance_math_passes = 0

#         # ─── STEP 2: MULTI-STRATEGY LEDGER CALCULATOR ────────────────────────
#         for i, (row, debit_val, credit_val) in enumerate(valid_tx_rows):
#             # 1. Date Validation Pass
#             if cls.DATE_PATTERN.search(str(row.date)):
#                 date_matches += 1

#             # 2. Narration Validation Pass
#             if len(str(row.narration).strip()) >= 3:
#                 narration_matches += 1

#             # 3. Target Operational Amount Validation Check
#             if debit_val != 0.0 or credit_val != 0.0:
#                 amount_matches += 1

#             # 4. Running Balance Vector Calculations
#             curr_balance = cls.clean_numeric(row.balance)
#             if i > 0:
#                 prev_balance = valid_tx_rows[i - 1][
#                     1
#                 ]  # Safely extract stored cached values
#                 prev_row_balance = cls.clean_numeric(valid_tx_rows[i - 1][0].balance)

#                 actual_balance = round(curr_balance, 2)
#                 standard_computed = round(prev_row_balance - debit_val + credit_val, 2)

#                 active_amount = credit_val if credit_val != 0.0 else debit_val
#                 single_col_addition = round(prev_row_balance + active_amount, 2)
#                 single_col_subtraction = round(prev_row_balance - active_amount, 2)

#                 # Vector margin match verification check
#                 if (
#                     abs(standard_computed - actual_balance) <= 0.10
#                     or abs(single_col_addition - actual_balance) <= 0.10
#                     or abs(single_col_subtraction - actual_balance) <= 0.10
#                 ):
#                     balance_math_passes += 1
#                 else:
#                     print(
#                         f"⚠️ Math Fail at Row [{i}]: Prev={prev_row_balance}, Amt={active_amount}, Curr={curr_balance}"
#                     )
#             else:
#                 if curr_balance != 0.0:
#                     balance_math_passes += 1

#         # ─── STEP 3: SCORE RATIO COMPILATION & DIAGNOSTICS ───────────────────
#         pillars = {
#             "Date": date_matches / total_tx_count,
#             "Narr": narration_matches / total_tx_count,
#             "Amt": amount_matches / total_tx_count,
#             "Math": balance_math_passes / total_tx_count,
#         }

#         print(
#             f"📊 Pillar Scores -> Date: {pillars['Date']:.2f} | Narr: {pillars['Narr']:.2f} | "
#             f"Amt: {pillars['Amt']:.2f} | Math: {pillars['Math']:.2f}"
#         )

#         # Award points iteration
#         for score_pct in pillars.values():
#             if score_pct >= 0.95:
#                 confidence += 20

#         return confidence
