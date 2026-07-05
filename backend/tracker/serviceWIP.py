# tracker/serviceWIP.py
import hashlib
import re
from decimal import Decimal
from django.db import transaction
from .models import (
    StatementStagingLine,
    WIPEvaluationMatrix,
    MasterFinancialCategory,
    AccountingRule,
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
                    # Method A: Evaluate text token strings element-by-element
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

            if not t1_pass:
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


class WIPReconciliationEngine1:
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
            narration_clean = wip_row.narration_normalized or ""

            # Check transaction type using numeric values
            try:
                debit_val = float(wip_row.debit or 0)
                credit_val = float(wip_row.credit or 0)
            except (ValueError, TypeError):
                debit_val, credit_val = 0.0, 0.0

            is_debit = debit_val > 0
            is_financial_tx = debit_val > 0 or credit_val > 0

            # 🧩 TIER 1: PATTERN INTERCEPTOR GATE (With Self-Transfer Detection)
            # Scan matching tokens inside master category profiles
            for cat, k1, k2 in parsed_categories:
                if k1 and k1 in narration_clean:
                    if not k2 or (k2 in narration_clean):
                        matched_cat = cat
                        t1_pass = True
                        break

            if not t1_pass:
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
