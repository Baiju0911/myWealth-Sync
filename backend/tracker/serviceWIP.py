# tracker/serviceWIP.py
import hashlib
import json
import re
import copy
from decimal import Decimal
from django.db import transaction
from .models import (
    StatementStagingLine,
    WIPEvaluationMatrix,
    MasterFinancialCategory,
    AccountingRule,
    DirectionalVectorOverride,
)


class WIPIngestionSweeper:
    """
    🎛️ AIR-GAPPED TRANSACTION INITIALIZATION ENGINE
    Sweeps unallocated StatementStagingLines into the WIP Evaluation Sandbox
    using strict deterministic SHA-256 state tracking keys.
    """

    @staticmethod
    def generate_row_hash(date_obj, debit_val, credit_val, balance_val) -> str:
        def clean_num(val) -> str:
            if val is None:
                return "0.00"
            return f"{Decimal(str(val)):.2f}"

        date_str = (
            date_obj.strftime("%Y-%m-%d")
            if hasattr(date_obj, "strftime")
            else str(date_obj)
        )
        data_payload = f"{date_str}|{clean_num(debit_val)}|{clean_num(credit_val)}|{clean_num(balance_val)}"
        return hashlib.sha256(data_payload.encode("utf-8")).hexdigest()

    @classmethod
    def execute_sweep(cls, account_context_id) -> dict:
        metrics = {"scanned": 0, "initialized": 0, "skipped": 0}
        with transaction.atomic():
            staging_queue = StatementStagingLine.objects.filter(
                account_id=account_context_id, routing_status="PENDING"
            ).select_for_update()

            metrics["scanned"] = staging_queue.count()

            existing_wip_hashes = set(
                WIPEvaluationMatrix.objects.filter(
                    account_id=account_context_id
                ).values_list("row_footprint_hash", flat=True)
            )

            wip_insertions = []

            for row in staging_queue:
                dr_clean = row.debit if row.debit is not None else Decimal("0.00")
                cr_clean = row.credit if row.credit is not None else Decimal("0.00")
                bal_clean = (
                    row.running_balance
                    if row.running_balance is not None
                    else Decimal("0.00")
                )

                row_hash = cls.generate_row_hash(
                    row.raw_statement_date, dr_clean, cr_clean, bal_clean
                )

                if row_hash in existing_wip_hashes:
                    metrics["skipped"] += 1
                    continue

                wip_row = WIPEvaluationMatrix(
                    staging_line=row,
                    row_footprint_hash=row_hash,
                    account=row.account,
                    bank=row.bank,
                    raw_statement_date=row.raw_statement_date,
                    narration_normalized=" ".join(
                        row.narration.strip().lower().split()
                    ),
                    debit=dr_clean,
                    credit=cr_clean,
                    confidence_level="ZERO",
                    tier_1_passed=False,
                    tier_2_passed=False,
                    tier_3_passed=False,
                    evaluation_errors=["UNPROCESSED_RUN"],
                )
                wip_insertions.append(wip_row)
                existing_wip_hashes.add(row_hash)

            if wip_insertions:
                WIPEvaluationMatrix.objects.bulk_create(wip_insertions)
                metrics["initialized"] = len(wip_insertions)

        return metrics


class WIPReconciliationEngine:
    """
    🤖 DECISION-TREE AUTOMATED AUTO-CATEGORIZATION ENGINE
    Version 3.0: Ensemble Architecture with Weighted Confidence Logic
    """

    @classmethod
    def evaluate_account_queue(cls, account_id: int) -> dict:
        # 1. Load data tables into local cache memory blocks
        master_categories = list(MasterFinancialCategory.objects.all())
        accounting_rules = list(
            AccountingRule.objects.filter(is_active=True).order_by("-rule_priority")
        )

        # Pre-Compile Categories Map
        parsed_categories = []
        for cat in master_categories:
            if isinstance(cat.keys, dict):
                k1 = (cat.keys.get("key1") or "").strip().lower()
                k2 = (cat.keys.get("key2") or "").strip().lower()
            else:
                k1, k2 = "", ""
            parsed_categories.append((cat, k1, k2))

        # Pre-Compile Accounting Rules Map
        parsed_rules = []
        for rule in accounting_rules:
            tags = (
                rule.description_tags if isinstance(rule.description_tags, list) else []
            )
            clean_tags = [tag.strip().lower() for tag in tags if tag]

            # Parse rule metadata context safely
            meta = {}
            if rule.rule_metadata:
                if isinstance(rule.rule_metadata, dict):
                    meta = rule.rule_metadata
                elif isinstance(rule.rule_metadata, str):
                    try:
                        meta = json.loads(rule.rule_metadata)
                    except json.JSONDecodeError:
                        meta = {}
            parsed_rules.append((rule, clean_tags, meta))

        # Fetch active WIP records via optimal relational JOIN commands
        active_wip_rows = WIPEvaluationMatrix.objects.filter(
            account_id=account_id,
            is_split_component=False,
        ).select_related("staging_line", "matched_category", "applied_rule")

        total_promoted_to_high = 0
        total_promoted_to_medium = 0
        total_failed_to_zero = 0
        modified_wip_rows = []

        # 2. Processing Loop Matrix
        for wip_row in active_wip_rows:
            errors_list = []
            matched_cat = None
            matched_rule = None

            # Variables to store separate Tier outputs
            t1_cat, t1_sub = None, None
            t2_cat, t2_sub = None, None
            t3_cat, t3_sub = None, None

            # Points Accumulator
            score = 0

            narration_clean = (wip_row.narration_normalized or "").strip().lower()

            try:
                debit_val = float(wip_row.debit or 0)
                credit_val = float(wip_row.credit or 0)
            except (ValueError, TypeError):
                debit_val, credit_val = 0.0, 0.0

            is_financial_tx = debit_val > 0 or credit_val > 0

            # 🧩 TIER 1 EVALUATION: DIRECTION-AWARE KEYWORD CHECK (Weight: 35)
            for cat, k1, k2 in parsed_categories:
                if not k1:
                    continue

                # Ignore rule if money vector direction contradicts category type
                if credit_val > 0 and cat.act_category.strip().lower() in [
                    "expense",
                    "expenses",
                    "charity",
                ]:
                    continue
                if debit_val > 0 and cat.act_category.strip().lower() in [
                    "income",
                    "revenue",
                ]:
                    continue

                # Token matching execution strings
                is_match = False
                if len(k1) == 64:  # SHA-256 Check
                    normalized_delimiters = re.sub(r"[/:\-_,]", " ", narration_clean)
                    words = normalized_delimiters.split()
                    is_match = any(
                        hashlib.sha256(w.encode("utf-8")).hexdigest() == k1
                        for w in words
                    )
                    if not is_match:
                        is_match = (
                            hashlib.sha256(narration_clean.encode("utf-8")).hexdigest()
                            == k1
                        )
                elif k1 in narration_clean:
                    k2_clean = k2.replace(" ", "") if k2 else None
                    narration_nospace = narration_clean.replace(" ", "")
                    if not k2_clean or (k2_clean in narration_nospace):
                        is_match = True

                if is_match:
                    matched_cat = cat
                    t1_cat = cat.act_category
                    t1_sub = cat.act_subcategory
                    score += 35
                    break

            if not t1_cat:
                errors_list.append("T1_KEYWORD_UNMAPPED")

            # 📊 TIER 2 EVALUATION: REPORTING CONTEXT VERIFICATION (Weight: 15)
            if (
                matched_cat
                and matched_cat.dashboard_cat
                and matched_cat.dashboard_cat.strip()
            ):
                t2_cat = matched_cat.act_category
                t2_sub = matched_cat.act_subcategory
                score += 15
            else:
                errors_list.append("T2_DASHBOARD_CONTEXT_MISSING")

            # 📜 TIER 3 EVALUATION: GOLDEN ACCOUNTING RULES ALIGNMENT (Weight: 50)
            for rule, clean_tags, meta in parsed_rules:
                if any(tag in narration_clean for tag in clean_tags):
                    # Direct text hit inside the accounting rules table tags
                    matched_rule = rule
                    t3_cat = meta.get("category")
                    t3_sub = meta.get("subcategory")
                    score += 50
                    break

            # Smart Fallback Pass: Apply global nominal rule defaults if no tag matches
            if not t3_cat and is_financial_tx:
                t3_cat = "Income" if credit_val > 0 else "Expenses"
                t3_sub = "Revenue" if credit_val > 0 else "Operational Expenses"
                score += 30  # Partial points for general directional compliance

            if not matched_rule:
                errors_list.append("T3_COMPLIANCE_FALLBACK_APPLIED")

            # 🏆 ENSEMBLE RESOLUTION LOGIC (Weighing the Outputs)
            votes = {}
            for c, s in [(t3_cat, t3_sub), (t1_cat, t1_sub), (t2_cat, t2_sub)]:
                if c:
                    votes[(c, s)] = votes.get((c, s), 0) + 1

            if votes:
                # Select the category combination with the maximum tier agreement
                winner_cat, winner_sub = max(votes, key=votes.get)
            else:
                winner_cat, winner_sub = "Unassigned", "Unmapped Pattern"

            # Determine Confidence Classification Levels
            if score >= 85:
                confidence_level = "HIGH"
                total_promoted_to_high += 1
            elif score >= 50:
                confidence_level = "MEDIUM"
                total_promoted_to_medium += 1
            else:
                confidence_level = "ZERO"
                total_failed_to_zero += 1

            # 💾 Bind properties back onto DB matrix row footprints
            wip_row.t1_category = t1_cat
            wip_row.t1_subcategory = t1_sub
            wip_row.t2_category = t2_cat
            wip_row.t2_subcategory = t2_sub
            wip_row.t3_category = t3_cat
            wip_row.t3_subcategory = t3_sub

            wip_row.resolved_category = winner_cat
            wip_row.resolved_subcategory = winner_sub

            wip_row.confidence_score = score
            wip_row.confidence_level = confidence_level
            wip_row.evaluation_errors = errors_list

            wip_row.matched_category = matched_cat
            wip_row.applied_rule = matched_rule
            wip_row.tier_1_passed = t1_cat is not None
            wip_row.tier_2_passed = t2_cat is not None
            wip_row.tier_3_passed = matched_rule is not None

            modified_wip_rows.append(wip_row)

        # ⚡ Bulk Commit Performance Block
        if modified_wip_rows:
            with transaction.atomic():
                WIPEvaluationMatrix.objects.bulk_update(
                    modified_wip_rows,
                    fields=[
                        "t1_category",
                        "t1_subcategory",
                        "t2_category",
                        "t2_subcategory",
                        "t3_category",
                        "t3_subcategory",
                        "resolved_category",
                        "resolved_subcategory",
                        "confidence_score",
                        "confidence_level",
                        "evaluation_errors",
                        "matched_category",
                        "applied_rule",
                        "tier_1_passed",
                        "tier_2_passed",
                        "tier_3_passed",
                    ],
                    batch_size=500,
                )

        return {
            "processed_rows": modified_wip_rows,
            "staged_for_bulk_high": total_promoted_to_high,
            "staged_for_bulk_medium": total_promoted_to_medium,  # Added for completeness
            "uncategorized_vault_zero": total_failed_to_zero,
        }


class WIPReconciliationEngine1:
    """
    🤖 DECISION-TREE AUTOMATED AUTO-CATEGORIZATION ENGINE
    Implements a direction-aware keyword scanner with an active database safety net.
    """

    @classmethod
    def evaluate_account_queue(cls, account_id: int) -> dict:
        master_categories = list(MasterFinancialCategory.objects.all())
        accounting_rules = list(
            AccountingRule.objects.filter(is_active=True).order_by("-rule_priority")
        )

        # 🔄 Load our dynamic safety net fallback maps from the DB
        vector_overrides = {
            ov.source_category.strip().lower(): {
                "target_cat": ov.target_category,
                "target_sub": ov.target_subcategory,
            }
            for ov in DirectionalVectorOverride.objects.filter(
                is_active=True, expected_vector="DEBIT"
            )
        }

        parsed_categories = []
        for cat in master_categories:
            if isinstance(cat.keys, dict):
                k1 = (cat.keys.get("key1") or "").strip().lower()
                k2 = (cat.keys.get("key2") or "").strip().lower()
            else:
                k1, k2 = "", ""
            parsed_categories.append((cat, k1, k2))

        parsed_rules = []
        for rule in accounting_rules:
            tags = (
                rule.description_tags if isinstance(rule.description_tags, list) else []
            )
            clean_tags = [tag.strip().lower() for tag in tags if tag]
            parsed_rules.append((rule, clean_tags))

        active_wip_rows = WIPEvaluationMatrix.objects.filter(
            account_id=account_id,
            is_split_component=False,
        ).select_related("staging_line", "matched_category", "applied_rule")

        total_promoted_to_high = 0
        total_failed_to_zero = 0
        modified_wip_rows = []

        for wip_row in active_wip_rows:
            t1_pass, t2_pass, t3_pass = False, False, False
            errors_list = []
            matched_cat = None
            matched_rule = None

            narration_clean = (wip_row.narration_normalized or "").strip().lower()

            try:
                debit_val = float(wip_row.debit or 0)
                credit_val = float(wip_row.credit or 0)
            except (ValueError, TypeError):
                debit_val, credit_val = 0.0, 0.0

            is_financial_tx = debit_val > 0 or credit_val > 0

            # 🧩 STAGE 1: DIRECTION-AWARE PATTERN INTERCEPTOR GATE
            for cat, k1, k2 in parsed_categories:
                if not k1:
                    continue

                # 🎯 STRATEGY 1: Skip wrong directional matches immediately to avoid line 2184 traps!
                if credit_val > 0 and cat.act_category.strip().lower() in [
                    "expense",
                    "expenses",
                    "charity",
                ]:
                    continue  # Keep cruising down the loop to look for an explicit Income counterpart
                if debit_val > 0 and cat.act_category.strip().lower() in [
                    "income",
                    "revenue",
                ]:
                    continue

                # SHA-256 Mask evaluation block
                if len(k1) == 64:
                    normalized_delimiters = re.sub(r"[/:\-_,]", " ", narration_clean)
                    words = normalized_delimiters.split()
                    matched_hash = any(
                        hashlib.sha256(w.encode("utf-8")).hexdigest() == k1
                        for w in words
                    )
                    if not matched_hash:
                        matched_hash = (
                            hashlib.sha256(narration_clean.encode("utf-8")).hexdigest()
                            == k1
                        )
                    if matched_hash:
                        matched_cat = cat
                        t1_pass = True
                        break

                # Standard String lookup matching execution blocks
                elif k1 in narration_clean:
                    k2_clean = k2.replace(" ", "") if k2 else None
                    narration_nospace = narration_clean.replace(" ", "")
                    if not k2_clean or (k2_clean in narration_nospace):
                        matched_cat = cat
                        t1_pass = True
                        break

            # 🧠 STAGE 2: THE AUTO-CORRECTION INTELLIGENT SAFETY NET
            # This only runs if Stage 1 matched a strict rule that lacks a dual-direction setup
            if not t1_pass:
                # Run an emergency back-check sweep over all rules without the direction filters
                for cat, k1, k2 in parsed_categories:
                    if not k1:
                        continue
                    if k1 in narration_clean:
                        k2_clean = k2.replace(" ", "") if k2 else None
                        narration_nospace = narration_clean.replace(" ", "")
                        if not k2_clean or (k2_clean in narration_nospace):
                            matched_cat = cat
                            t1_pass = True
                            break

                # If an Emergency back-match occurred but it's an Expense on a Credit flow:
                if t1_pass and matched_cat and credit_val > 0:
                    act_cat_clean = (matched_cat.act_category or "").strip().lower()

                    if act_cat_clean in vector_overrides:
                        # 🧬 Hit our Intelligent category matrix fallback config!
                        override_rule = vector_overrides[act_cat_clean]
                        intelligent_cat = copy.copy(matched_cat)
                        intelligent_cat.act_category = override_rule["target_cat"]
                        intelligent_cat.act_subcategory = override_rule["target_sub"]
                        intelligent_cat.categories_items = (
                            f"Corrected {matched_cat.categories_items}"
                        )

                        matched_cat = intelligent_cat
                        errors_list.append(
                            f"SAFETY_NET_CORRECTED_{act_cat_clean.upper()}"
                        )
                    else:
                        # 🚫 No category rule defined -> Drop it directly to UNMAPPED for manual review
                        t1_pass = False
                        matched_cat = None

            if not t1_pass:
                errors_list.append("UNMAPPED_PATTERN")

            # 📊 TIER 2: BALANCE SHEET DASHBOARD ROUTING GATE
            if t1_pass and matched_cat:
                if matched_cat.dashboard_cat and matched_cat.dashboard_cat.strip():
                    t2_pass = True
                else:
                    errors_list.append("MISSING_BALANCE_SHEET_CONTEXT")

            # 📜 TIER 3: DOUBLE-ENTRY COMPLIANCE CHECK
            if t1_pass and t2_pass and matched_cat:
                for rule, clean_tags in parsed_rules:
                    if any(tag in narration_clean for tag in clean_tags):
                        matched_rule = rule
                        t3_pass = True
                        break

                if not t3_pass:
                    if is_financial_tx:
                        t3_pass = (
                            True  # Accounting Golden Rule validation fallback pass
                        )
                    else:
                        t3_pass = False

                if not t3_pass:
                    errors_list.append("RULE_COMPLIANCE_FAILED")

            # 🏁 VERDICT ENGINE
            if t1_pass and t2_pass and t3_pass:
                wip_row.confidence_level = "HIGH"
                wip_row.evaluation_errors = errors_list
                total_promoted_to_high += 1
            else:
                wip_row.confidence_level = "ZERO"
                wip_row.evaluation_errors = errors_list
                total_failed_to_zero += 1

            wip_row.matched_category = matched_cat
            wip_row.applied_rule = matched_rule
            wip_row.tier_1_passed = t1_pass
            wip_row.tier_2_passed = t2_pass
            wip_row.tier_3_passed = t3_pass

            modified_wip_rows.append(wip_row)

        if modified_wip_rows:
            with transaction.atomic():
                WIPEvaluationMatrix.objects.bulk_update(
                    modified_wip_rows,
                    fields=[
                        "confidence_level",
                        "evaluation_errors",
                        "matched_category",
                        "applied_rule",
                        "tier_1_passed",
                        "tier_2_passed",
                        "tier_3_passed",
                    ],
                    batch_size=500,
                )

        return {
            "processed_rows": modified_wip_rows,
            "staged_for_bulk_high": total_promoted_to_high,
            "uncategorized_vault_zero": total_failed_to_zero,
        }


class WIPReconciliationEngine_olderCode_before_VecoreOverride:
    """
    🤖 DECISION-TREE AUTOMATED AUTO-CATEGORIZATION ENGINE
    Implements a strict, high-speed matching sequence across:
    Self Transfers ──> Known Defaults ──> Regular Ledger Mapping Targets.
    """

    @classmethod
    def evaluate_account_queue(cls, account_id: int) -> dict:
        # Load tables dynamically into local cache memory blocks
        master_categories = list(MasterFinancialCategory.objects.all())
        accounting_rules = list(
            AccountingRule.objects.filter(is_active=True).order_by("-rule_priority")
        )

        # 1. Pre-Compile Multi-Key Categories Map
        parsed_categories = []
        for cat in master_categories:
            if isinstance(cat.keys, dict):
                k1 = (cat.keys.get("key1") or "").strip().lower()
                k2 = (cat.keys.get("key2") or "").strip().lower()
            else:
                k1, k2 = "", ""
            parsed_categories.append((cat, k1, k2))

        # 2. Pre-Compile Explicit Accounting Verification Rules Map
        parsed_rules = []
        for rule in accounting_rules:
            tags = (
                rule.description_tags if isinstance(rule.description_tags, list) else []
            )
            clean_tags = [tag.strip().lower() for tag in tags if tag]
            parsed_rules.append((rule, clean_tags))

        # Fetch active roots via optimal relational JOIN commands

        active_wip_rows = WIPEvaluationMatrix.objects.filter(
            account_id=account_id,
            is_split_component=False,
        ).select_related("staging_line", "matched_category", "applied_rule")

        total_promoted_to_high = 0
        total_failed_to_zero = 0
        modified_wip_rows = []

        # 3. High-Speed Processing Pipeline
        for wip_row in active_wip_rows:
            t1_pass, t2_pass, t3_pass = False, False, False
            errors_list = []
            matched_cat = None
            matched_rule = None

            # Ensure the incoming narration text is normalized to prevent matching misses
            narration_clean = (wip_row.narration_normalized or "").strip().lower()

            # Check transaction type using numeric values
            try:
                debit_val = float(wip_row.debit or 0)
                credit_val = float(wip_row.credit or 0)
            except (ValueError, TypeError):
                debit_val, credit_val = 0.0, 0.0

            is_debit = debit_val > 0
            is_financial_tx = debit_val > 0 or credit_val > 0

            # 🧩 TIER 1: PATTERN INTERCEPTOR GATE (With Private Hash Interceptor Support)
            for cat, k1, k2 in parsed_categories:
                if not k1:
                    continue

                # 🔐 INTERCEPT BLOCK: Check if key1 is a 64-character SHA-256 target mask
                if len(k1) == 64:
                    normalized_delimiters = re.sub(r"[/:\-_,]", " ", narration_clean)
                    words = normalized_delimiters.split()

                    # Method A: Evaluate text token strings element-by-element
                    matched_hash = any(
                        hashlib.sha256(w.encode("utf-8")).hexdigest() == k1
                        for w in words
                    )

                    # Method B Fallback: Evaluate string phrase arrays holistically
                    if not matched_hash:
                        matched_hash = (
                            hashlib.sha256(narration_clean.encode("utf-8")).hexdigest()
                            == k1
                        )

                    if matched_hash:
                        matched_cat = cat
                        t1_pass = True
                        break

                # 📝 STANDARD KEYWORD BLOCK: Default operational routing checks (Amazon, SBI, etc.)
                elif k1 in narration_clean:
                    # Defensive spacing lookup checks to eliminate trailing index formatting traps
                    k2_clean = k2.replace(" ", "") if k2 else None
                    narration_nospace = narration_clean.replace(" ", "")

                    if not k2_clean or (k2_clean in narration_nospace):
                        matched_cat = cat
                        t1_pass = True
                        break

            # 🚨 ROBUST DIRECTIONAL FIRST-AID INTERCEPTOR
            # Validates that cash inflows (Credits) do not get mismapped into Expense metrics groups
            if t1_pass and matched_cat and credit_val > 0:
                act_cat_clean = (matched_cat.act_category or "").strip().lower()
                if act_cat_clean in ["charity", "expense", "expenses"]:
                    errors_list.append("CREDIT_MATCHED_TO_EXPENSE_RULE")
                    t1_pass = False
                    matched_cat = None

            if not t1_pass:
                if "CREDIT_MATCHED_TO_EXPENSE_RULE" not in errors_list:
                    errors_list.append("UNMAPPED_PATTERN")

            # 📊 TIER 2: BALANCE SHEET DASHBOARD ROUTING GATE
            if t1_pass and matched_cat:
                if matched_cat.dashboard_cat and matched_cat.dashboard_cat.strip():
                    t2_pass = True
                else:
                    errors_list.append("MISSING_BALANCE_SHEET_CONTEXT")

            # 📜 TIER 3: DOUBLE-ENTRY COMPLIANCE CHECK (Universal Validation Framework)
            if t1_pass and t2_pass and matched_cat:
                # Phase A: Check explicit business rules override blocks
                for rule, clean_tags in parsed_rules:
                    if any(tag in narration_clean for tag in clean_tags):
                        matched_rule = rule
                        t3_pass = True
                        break

                # Phase B: Universal Fallback Check
                if not t3_pass:
                    if is_financial_tx:
                        t3_pass = True  # Verified by cashflow vector parameters
                    else:
                        t3_pass = False  # Blocks non-financial admin notes

                if not t3_pass:
                    errors_list.append("RULE_COMPLIANCE_FAILED")

            # 🏁 VERDICT ENGINE
            if t1_pass and t2_pass and t3_pass:
                wip_row.confidence_level = "HIGH"
                wip_row.evaluation_errors = []
                total_promoted_to_high += 1
            else:
                wip_row.confidence_level = "ZERO"
                wip_row.evaluation_errors = errors_list
                total_failed_to_zero += 1

            wip_row.matched_category = matched_cat
            wip_row.applied_rule = matched_rule
            wip_row.tier_1_passed = t1_pass
            wip_row.tier_2_passed = t2_pass
            wip_row.tier_3_passed = t3_pass

            modified_wip_rows.append(wip_row)

        # ⚡ Execute Bulk Commit Action Leg
        if modified_wip_rows:
            with transaction.atomic():
                WIPEvaluationMatrix.objects.bulk_update(
                    modified_wip_rows,
                    fields=[
                        "confidence_level",
                        "evaluation_errors",
                        "matched_category",
                        "applied_rule",
                        "tier_1_passed",
                        "tier_2_passed",
                        "tier_3_passed",
                    ],
                    batch_size=500,
                )

        return {
            "processed_rows": modified_wip_rows,
            "staged_for_bulk_high": total_promoted_to_high,
            "uncategorized_vault_zero": total_failed_to_zero,
        }
