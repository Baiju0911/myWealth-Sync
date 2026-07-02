import logging
import os
import io
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from .engine import extract_raw_tokens
from .strategies import strict_matrix
from .strategies import (
    strict_matrix_v2,
    strict_matrix_v3,
)
from .strategies import relative_matrix, relative_matrix_v2
from tracker.models import UserStatementTemplate
from .utils.csv_engine import (
    parse_universal_csv_stream,
)  # 🟢 Import our new CSV tokenizer

# Fallback & Quality Assurance metrics
from .parser_orchestrator import FallbackOrchestratorService
from .confidence.evaluator import ConfidenceEvaluator
from .geometry.lane_detector import StructuredRow

logger = logging.getLogger(__name__)


def process_bank_statement_older(
    uploaded_file,
    template_obj,
    account_id,
    existing_database_hashes=None,
    password_vault=None,
):
    if existing_database_hashes is None:
        existing_database_hashes = set()

    # ─── 🚀 STEP 0: EXTENSION INTEGRITY INTERCEPTION (ACCOUNT-AGNOSTIC) ───
    original_filename = getattr(uploaded_file, "name", "statement.pdf").lower()

    if original_filename.endswith((".csv", ".txt", ".xlsx", ".xls")):
        logger.info(
            "📊 Tabular document format detected by file extension. Forcing Universal CSV Engine Track."
        )
        try:
            uploaded_file.seek(0)
            raw_bytes = uploaded_file.read()
            uploaded_file.seek(0)  # Reset pointer back to beginning

            if (
                not template_obj
                or getattr(template_obj, "parser_strategy_code", "")
                != "UNIVERSAL_CSV_FLOW"
            ):
                logger.info(
                    "🔀 Overriding specialized PDF template configuration rules with Universal CSV Landmark schema matrix."
                )
                template_obj = UserStatementTemplate.objects.filter(
                    template_name="UNIVERSAL"
                ).first()

            # Execute the single-pass CSV tokenizer using our safe matrix rules
            csv_txns = parse_universal_csv_stream(raw_bytes, template_obj)

            calculated_op_bal = 0.00
            if csv_txns:
                try:
                    # ─── 🎯 MATHEMATICAL REVERSE-ENGINEERING ANCHOR SEED ───
                    first_row = csv_txns[0]
                    first_row_bal = float(
                        str(first_row.get("balance", "0.00")).replace(",", "")
                    )

                    raw_deb = str(first_row.get("debit", "-")).replace(",", "").strip()
                    raw_crd = str(first_row.get("credit", "-")).replace(",", "").strip()

                    first_row_deb = (
                        float(raw_deb) if raw_deb and raw_deb != "-" else 0.0
                    )
                    first_row_crd = (
                        float(raw_crd) if raw_crd and raw_crd != "-" else 0.0
                    )

                    if first_row_deb > 0:
                        calculated_op_bal = first_row_bal + first_row_deb
                        logger.info(
                            f"🔄 Reverse-engineered opening anchor baseline: {first_row_bal} + {first_row_deb} = {calculated_op_bal}"
                        )
                    elif first_row_crd > 0:
                        calculated_op_bal = first_row_bal - first_row_crd
                        logger.info(
                            f"🔄 Reverse-engineered opening anchor baseline: {first_row_bal} - {first_row_crd} = {calculated_op_bal}"
                        )
                    else:
                        calculated_op_bal = first_row_bal
                except (ValueError, IndexError):
                    pass

            return csv_txns, calculated_op_bal, []

        except Exception as csv_crash:
            logger.error(f"❌ Account-Agnostic CSV Tokenizer failed: {str(csv_crash)}")
            raise csv_crash

    # ─── 🛡️ STEP 1: NATIVE PDF LAYOUT PATTERNS (UNTOUCHED & STABLE) ───
    try:
        pages_raw_data = extract_raw_tokens(
            uploaded_file, password_vault_raw=password_vault
        )
    except Exception as e:
        print(f"🚨 DEBUG LOG: extract_raw_tokens CRASHED with error: {str(e)}")
        logger.error(f"❌ Geometric tokenization failed: {str(e)}")
        return _run_paddle_fallback_bridge(uploaded_file, template_obj)

    if not pages_raw_data:
        print(
            "🚨 DEBUG LOG: pages_raw_data is EMPTY. PDF has no native text layer (Scanned Image)."
        )
        logger.info(
            "📸 No native text streams detected. Redirecting to PaddleOCR Fallback..."
        )
        return _run_paddle_fallback_bridge(uploaded_file, template_obj)

    # ─── 🧬 STEP 2: HYBRID ACCOUNTS SIGNATURE ENGINE ───
    candidate_templates = UserStatementTemplate.objects.filter(account_id=account_id)

    if candidate_templates.count() > 1:
        logger.info(
            f"🔍 Hybrid Account Context Active for Account {account_id}. Running footprint routing..."
        )
        page_sample_text = ""
        if pages_raw_data and "words" in pages_raw_data[0]:
            sample_words = [str(w[4]).strip() for w in pages_raw_data[0]["words"][:250]]
            page_sample_text = " ".join(sample_words)

        page_sample_upper = page_sample_text.upper()

        if "SOUTH INDIAN" in page_sample_upper or "SIBL0000624" in page_sample_upper:
            if "SWIFT CODE" in page_sample_upper or "CKYC ID" in page_sample_upper:
                matched_template = candidate_templates.filter(
                    parser_strategy_code="GRID_COLUMN_FLOW_V2"
                ).first()
                if matched_template:
                    template_obj = matched_template
            elif (
                "CURRENCY CODE" in page_sample_upper
                or "---" in page_sample_upper
                or "SIB EXPRESS" in page_sample_upper
            ):
                matched_template = candidate_templates.filter(
                    parser_strategy_code="GRID_COLUMN_FLOW_V3"
                ).first()
                if matched_template:
                    template_obj = matched_template
            else:
                matched_template = candidate_templates.filter(
                    parser_strategy_code="GRID_COLUMN_FLOW_V2"
                ).first()
                if matched_template:
                    template_obj = matched_template
        elif (
            "---" in page_sample_upper
            or "PARTICULARS" in page_sample_upper
            or "CHQ.NO" in page_sample_upper
        ):
            # 🎯 HYBRID CHECK: If it contains legacy indicators like "Brought Forward" or compact structures, auto-route to V2
            if "BROUGHT FORWARD" in page_sample_upper or "OPNBAL" in page_sample_upper:
                matched_template = candidate_templates.filter(
                    parser_strategy_code="RELATIVE_MATRIX_V2"
                ).first()
                if matched_template:
                    template_obj = matched_template
            else:
                matched_template = candidate_templates.filter(
                    parser_strategy_code="GRID_COLUMN_FLOW_V3"
                ).first()
                if matched_template:
                    template_obj = matched_template
        else:
            matched_template = candidate_templates.filter(
                parser_strategy_code="GRID_COLUMN_FLOW_V2"
            ).first()
            if matched_template:
                template_obj = matched_template

    strategy = getattr(template_obj, "parser_strategy_code", "GRID_COLUMN_FLOW").upper()
    logger.info(f"⚡ Ingestion Pipeline Active | Strategy: {strategy}")

    # ─── 🔀 STEP 3: ISOLATED ENGINE ROUTING TRACKS ───
    try:
        if strategy in ("GRID_COLUMN_FLOW_V2", "STRICT_MATRIX_V2"):
            txns, bal, errs = strict_matrix_v2.execute(
                pages_raw_data, template_obj, account_id, existing_database_hashes
            )
        elif strategy in ("GRID_COLUMN_FLOW_V3", "STRICT_MATRIX_V3", "SIB_LEGACY_FLOW"):
            txns, bal, errs = strict_matrix_v3.execute(
                pages_raw_data, template_obj, account_id, existing_database_hashes
            )
        elif strategy in ("GRID_COLUMN_FLOW", "STRICT_MATRIX"):
            txns, bal, errs = strict_matrix.execute(
                pages_raw_data, template_obj, account_id, existing_database_hashes
            )
        # ─── 🎯 THE FIX: INTERCEPT RECTIFICATION ROUTE FOR V2 ENGINE ───
        elif strategy in ("RELATIVE_MATRIX_V2", "TOKEN_SPLITTER_FLOW"):
            txns, bal, errs = relative_matrix_v2.execute_v2(
                pages_raw_data, template_obj, account_id, existing_database_hashes
            )
        elif strategy in (
            "NARRATIVE_INLINE_FLOW",
            "RELATIVE_MATRIX",
            "RELATIVE_SEQUENCE",
        ):
            txns, bal, errs = relative_matrix.execute(
                pages_raw_data, template_obj, account_id, existing_database_hashes
            )
        else:
            raise ValueError(f"❌ Unsupported strategy classification '{strategy}'.")

        # ─── ⚖️ STEP 4: AUTOMATED QUALITY ASSURANCE CIRCUIT BREAKER ───────────
        eval_rows = []
        for tx in txns:
            tx_date = (
                tx.get("date") or tx.get("post_date") or tx.get("value_date") or ""
            )
            tx_narration = str(
                tx.get("narration") or tx.get("description") or ""
            ).strip()
            dr_str = (
                "" if tx.get("debit") == "-" else str(tx.get("debit") or "").strip()
            )
            cr_str = (
                "" if tx.get("credit") == "-" else str(tx.get("credit") or "").strip()
            )
            bal_str = (
                "" if tx.get("balance") == "-" else str(tx.get("balance") or "").strip()
            )

            if not tx_date and not (dr_str or cr_str or bal_str) and tx_narration:
                if eval_rows:
                    eval_rows[-1].narration += " " + tx_narration
                continue

            row = StructuredRow()
            row.date = tx_date
            row.narration = tx_narration
            row.debit = dr_str
            row.credit = cr_str
            row.balance = bal_str
            eval_rows.append(row)

        confidence_score = ConfidenceEvaluator.evaluate_dataset(eval_rows)
        if confidence_score >= 95:
            return txns, bal, errs

        print(
            f"🚨 DEBUG LOG: Circuit breaker tripped! Confidence score was only {confidence_score}%."
        )
    except Exception as engine_error:
        print(
            f"🚨 DEBUG LOG: Active strategy {strategy} crashed during execution: {str(engine_error)}"
        )

    return _run_paddle_fallback_bridge(uploaded_file, template_obj)


def process_bank_statement(
    uploaded_file,
    template_obj,
    account_id,
    existing_database_hashes=None,
    password_vault=None,
):
    if existing_database_hashes is None:
        existing_database_hashes = set()

    # ─── 🚀 STEP 0: EXTENSION INTEGRITY INTERCEPTION (ACCOUNT-AGNOSTIC) ───
    original_filename = getattr(uploaded_file, "name", "statement.pdf").lower()

    if original_filename.endswith((".csv", ".txt", ".xlsx", ".xls")):
        logger.info(
            "📊 Tabular document format detected by file extension. Forcing Universal CSV Engine Track."
        )
        try:
            uploaded_file.seek(0)
            raw_bytes = uploaded_file.read()
            uploaded_file.seek(0)  # Reset pointer back to beginning

            if (
                not template_obj
                or getattr(template_obj, "parser_strategy_code", "")
                != "UNIVERSAL_CSV_FLOW"
            ):
                logger.info(
                    "🔀 Overriding specialized PDF template configuration rules with Universal CSV Landmark schema matrix."
                )
                template_obj = UserStatementTemplate.objects.filter(
                    template_name="UNIVERSAL"
                ).first()

            # Execute the single-pass CSV tokenizer using our safe matrix rules
            csv_txns = parse_universal_csv_stream(raw_bytes, template_obj)

            calculated_op_bal = 0.00
            if csv_txns:
                try:
                    # ─── 🎯 MATHEMATICAL REVERSE-ENGINEERING ANCHOR SEED ───
                    first_row = csv_txns[0]
                    first_row_bal = float(
                        str(first_row.get("balance", "0.00")).replace(",", "")
                    )

                    raw_deb = str(first_row.get("debit", "-")).replace(",", "").strip()
                    raw_crd = str(first_row.get("credit", "-")).replace(",", "").strip()

                    first_row_deb = (
                        float(raw_deb) if raw_deb and raw_deb != "-" else 0.0
                    )
                    first_row_crd = (
                        float(raw_crd) if raw_crd and raw_crd != "-" else 0.0
                    )

                    if first_row_deb > 0:
                        calculated_op_bal = first_row_bal + first_row_deb
                        logger.info(
                            f"🔄 Reverse-engineered opening anchor baseline: {first_row_bal} + {first_row_deb} = {calculated_op_bal}"
                        )
                    elif first_row_crd > 0:
                        calculated_op_bal = first_row_bal - first_row_crd
                        logger.info(
                            f"🔄 Reverse-engineered opening anchor baseline: {first_row_bal} - {first_row_crd} = {calculated_op_bal}"
                        )
                    else:
                        calculated_op_bal = first_row_bal
                except (ValueError, IndexError):
                    pass

                # 🎯 STRATEGY FLAG INJECTION FOR CSV TRACK
                for tx in csv_txns:
                    tx["strategy_used"] = "UNIVERSAL_CSV_FLOW"

            return csv_txns, calculated_op_bal, []

        except Exception as csv_crash:
            logger.error(f"❌ Account-Agnostic CSV Tokenizer failed: {str(csv_crash)}")
            raise csv_crash

    # ─── 🛡️ STEP 1: NATIVE PDF LAYOUT PATTERNS (UNTOUCHED & STABLE) ───
    try:
        pages_raw_data = extract_raw_tokens(
            uploaded_file, password_vault_raw=password_vault
        )
    except Exception as e:
        print(f"🚨 DEBUG LOG: extract_raw_tokens CRASHED with error: {str(e)}")
        logger.error(f"❌ Geometric tokenization failed: {str(e)}")
        return _run_paddle_fallback_bridge(uploaded_file, template_obj)

    if not pages_raw_data:
        print(
            "🚨 DEBUG LOG: pages_raw_data is EMPTY. PDF has no native text layer (Scanned Image)."
        )
        logger.info(
            "📸 No native text streams detected. Redirecting to PaddleOCR Fallback..."
        )
        return _run_paddle_fallback_bridge(uploaded_file, template_obj)

    # ─── 🧬 STEP 2: HYBRID ACCOUNTS SIGNATURE ENGINE ───
    candidate_templates = UserStatementTemplate.objects.filter(account_id=account_id)

    if candidate_templates.count() > 1:
        logger.info(
            f"🔍 Hybrid Account Context Active for Account {account_id}. Running footprint routing..."
        )
        page_sample_text = ""
        if pages_raw_data and "words" in pages_raw_data[0]:
            sample_words = [str(w[4]).strip() for w in pages_raw_data[0]["words"][:250]]
            page_sample_text = " ".join(sample_words)

        page_sample_upper = page_sample_text.upper()

        if "SOUTH INDIAN" in page_sample_upper or "SIBL0000624" in page_sample_upper:
            if "SWIFT CODE" in page_sample_upper or "CKYC ID" in page_sample_upper:
                matched_template = candidate_templates.filter(
                    parser_strategy_code="GRID_COLUMN_FLOW_V2"
                ).first()
                if matched_template:
                    template_obj = matched_template
            elif (
                "CURRENCY CODE" in page_sample_upper
                or "---" in page_sample_upper
                or "SIB EXPRESS" in page_sample_upper
            ):
                matched_template = candidate_templates.filter(
                    parser_strategy_code="GRID_COLUMN_FLOW_V3"
                ).first()
                if matched_template:
                    template_obj = matched_template
            else:
                matched_template = candidate_templates.filter(
                    parser_strategy_code="GRID_COLUMN_FLOW_V2"
                ).first()
                if matched_template:
                    template_obj = matched_template
        elif (
            "---" in page_sample_upper
            or "PARTICULARS" in page_sample_upper
            or "CHQ.NO" in page_sample_upper
        ):
            if "BROUGHT FORWARD" in page_sample_upper or "OPNBAL" in page_sample_upper:
                matched_template = candidate_templates.filter(
                    parser_strategy_code="RELATIVE_MATRIX_V2"
                ).first()
                if matched_template:
                    template_obj = matched_template
            else:
                matched_template = candidate_templates.filter(
                    parser_strategy_code="GRID_COLUMN_FLOW_V3"
                ).first()
                if matched_template:
                    template_obj = matched_template
        else:
            matched_template = candidate_templates.filter(
                parser_strategy_code="GRID_COLUMN_FLOW_V2"
            ).first()
            if matched_template:
                template_obj = matched_template

    strategy = getattr(template_obj, "parser_strategy_code", "GRID_COLUMN_FLOW").upper()
    logger.info(f"⚡ Ingestion Pipeline Active | Strategy: {strategy}")

    # ─── 🔀 STEP 3: ISOLATED ENGINE ROUTING TRACKS ───
    try:
        if strategy in ("GRID_COLUMN_FLOW_V2", "STRICT_MATRIX_V2"):
            txns, bal, errs = strict_matrix_v2.execute(
                pages_raw_data, template_obj, account_id, existing_database_hashes
            )
        elif strategy in ("GRID_COLUMN_FLOW_V3", "STRICT_MATRIX_V3", "SIB_LEGACY_FLOW"):
            txns, bal, errs = strict_matrix_v3.execute(
                pages_raw_data, template_obj, account_id, existing_database_hashes
            )
        elif strategy in ("GRID_COLUMN_FLOW", "STRICT_MATRIX"):
            txns, bal, errs = strict_matrix.execute(
                pages_raw_data, template_obj, account_id, existing_database_hashes
            )
        elif strategy in ("RELATIVE_MATRIX_V2", "TOKEN_SPLITTER_FLOW"):
            txns, bal, errs = relative_matrix_v2.execute_v2(
                pages_raw_data, template_obj, account_id, existing_database_hashes
            )
        elif strategy in (
            "NARRATIVE_INLINE_FLOW",
            "RELATIVE_MATRIX",
            "RELATIVE_SEQUENCE",
        ):
            txns, bal, errs = relative_matrix.execute(
                pages_raw_data, template_obj, account_id, existing_database_hashes
            )
        else:
            raise ValueError(f"❌ Unsupported strategy classification '{strategy}'.")

        # 🎯 THE INJECTION POINT: Safely map the strategy used into each record dictionary
        if txns:
            for tx in txns:
                tx["strategy_used"] = strategy

        # ─── ⚖️ STEP 4: AUTOMATED QUALITY ASSURANCE CIRCUIT BREAKER ───────────
        eval_rows = []
        for tx in txns:
            tx_date = (
                tx.get("date") or tx.get("post_date") or tx.get("value_date") or ""
            )
            tx_narration = str(
                tx.get("narration") or tx.get("description") or ""
            ).strip()
            dr_str = (
                "" if tx.get("debit") == "-" else str(tx.get("debit") or "").strip()
            )
            cr_str = (
                "" if tx.get("credit") == "-" else str(tx.get("credit") or "").strip()
            )
            val_str = (
                "" if tx.get("balance") == "-" else str(tx.get("balance") or "").strip()
            )

            if not tx_date and not (dr_str or cr_str or val_str) and tx_narration:
                if eval_rows:
                    eval_rows[-1].narration += " " + tx_narration
                continue

            row = StructuredRow()
            row.date = tx_date
            row.narration = tx_narration
            row.debit = dr_str
            row.credit = cr_str
            row.balance = val_str
            eval_rows.append(row)

        confidence_score = ConfidenceEvaluator.evaluate_dataset(eval_rows)
        if confidence_score >= 95:
            return txns, bal, errs

        print(
            f"🚨 DEBUG LOG: Circuit breaker tripped! Confidence score was only {confidence_score}%."
        )
    except Exception as engine_error:
        print(
            f"🚨 DEBUG LOG: Active strategy {strategy} crashed during execution: {str(engine_error)}"
        )

    # 🎯 FALLBACK INJECTION PASS: If native fails and redirects to OCR, mark it clearly
    fallback_txns, fallback_bal, fallback_errs = _run_paddle_fallback_bridge(
        uploaded_file, template_obj
    )
    if fallback_txns:
        for tx in fallback_txns:
            tx["strategy_used"] = f"PADDLE_OCR_FALLBACK_{strategy}"

    return fallback_txns, fallback_bal, fallback_errs


def _run_paddle_fallback_bridge(uploaded_file, template_obj):
    logger.info(
        "🐼 Invoking Fallback System Core (PaddleOCR + Geometry Engine Matrix)..."
    )

    if hasattr(uploaded_file, "temporary_file_path"):
        image_paths_list = [uploaded_file.temporary_file_path()]
    else:
        logger.info("💾 File is in memory. Writing temporary copy to disk path...")
        uploaded_file.seek(0)
        temp_filename = default_storage.save(
            f"temp_ocr_{uploaded_file.name}", ContentFile(uploaded_file.read())
        )
        absolute_path = os.path.abspath(default_storage.path(temp_filename))
        image_paths_list = [absolute_path]
        uploaded_file.seek(0)

    logger.info(f"📁 Processing absolute target path: {image_paths_list}")

    lane_override = getattr(template_obj, "coordinates_json", None)
    if not lane_override:
        lane_override = None

    fallback_result = FallbackOrchestratorService.process_failed_document(
        image_paths=image_paths_list, bank_template_override=lane_override
    )

    if not hasattr(uploaded_file, "temporary_file_path") and os.path.exists(
        image_paths_list[0]
    ):
        try:
            os.remove(image_paths_list[0])
            logger.info("🧼 Temporary image file copy deleted successfully.")
        except Exception as e:
            logger.warning(f"⚠️ Could not delete temp copy: {str(e)}")

    transactions = fallback_result.get("transactions", [])
    raw_csv_payload = fallback_result.get("raw_csv_stream", "")

    final_balance = 0.0
    if transactions:
        final_balance = ConfidenceEvaluator.clean_numeric(
            transactions[-1].get("balance", "0")
        )

    errors = []
    confidence_score = fallback_result.get("confidence_score", 0.0)
    if fallback_result.get("status") == "manual_review_recommended":
        errors.append(
            f"Low quality validation output warning. OCR Confidence Score: {confidence_score}%"
        )

    return (
        {
            "transactions_list": transactions,
            "raw_csv_stream": raw_csv_payload,
            "confidence_score": confidence_score,
        },
        final_balance,
        errors,
    )


# older working code before fallback
# import logging
# from .engine import extract_raw_tokens
# from .strategies import strict_matrix
# from .strategies import (
#     strict_matrix_v2,
#     strict_matrix_v3,
# )
# from .strategies import relative_matrix
# from tracker.models import (
#     UserStatementTemplate,
# )  # 🎯 Ensure absolute path match to your models folder

# logger = logging.getLogger(__name__)


# def process_bank_statement(
#     uploaded_file,
#     template_obj,
#     account_id,
#     existing_database_hashes=None,
#     password_vault=None,
# ):
#     if existing_database_hashes is None:
#         existing_database_hashes = set()

#     # ─── 🛡️ STEP 1: EXTRACT DECRYPTED TEXT TOKENS FIRST ───
#     try:
#         pages_raw_data = extract_raw_tokens(
#             uploaded_file, password_vault_raw=password_vault
#         )
#         if not pages_raw_data:
#             return [], 0.0, []
#     except Exception as e:
#         logger.error(f"❌ Geometric tokenization failed: {str(e)}")
#         raise e

#     # ─── 🧬 STEP 2: RUN DECRYPTED STRING SIGNATURE INSPECTION ───
#     candidate_templates = UserStatementTemplate.objects.filter(account_id=account_id)

#     if candidate_templates.count() > 1:
#         logger.info(
#             f"🔍 Multi-Template Context Active for Account {account_id}. Analyzing text structures..."
#         )

#         # Consolidate the first 3 lines of plain text extracted from Page 1
#         page_sample_text = ""
#         if pages_raw_data and "words" in pages_raw_data[0]:
#             # Pull text strings from the extracted spatial word blocks
#             sample_words = [str(w[4]).strip() for w in pages_raw_data[0]["words"][:150]]
#             page_sample_text = " ".join(sample_words).lower()

#         # 🎯 LOOK FOR THE CHARACTERISTIC LEGACY DIVIDER SIGNATURE
#         if (
#             "---" in page_sample_text
#             or "particulars" in page_sample_text
#             or "chq.no" in page_sample_text
#         ):
#             matched_template = candidate_templates.filter(
#                 parser_strategy_code="GRID_COLUMN_FLOW_V3"
#             ).first()
#             if matched_template:
#                 logger.info(
#                     "🎯 Layout Signature Auto-Match: Routing to Legacy Wrapped Sequence Engine (V3)"
#                 )
#                 template_obj = matched_template
#         else:
#             matched_template = candidate_templates.filter(
#                 parser_strategy_code="GRID_COLUMN_FLOW_V2"
#             ).first()
#             if matched_template:
#                 logger.info(
#                     "🎯 Layout Signature Auto-Match: Routing to Modern Matrix Engine (V2)"
#                 )
#                 template_obj = matched_template

#     # Unpack properties dynamically post-inspection
#     template_name = getattr(template_obj, "template_name", "UNKNOWN")
#     strategy = getattr(template_obj, "parser_strategy_code", "GRID_COLUMN_FLOW").upper()

#     logger.info(
#         f"⚡ Ingestion Pipeline Active | Template: {template_name} | Strategy: {strategy}"
#     )

#     # ─── 🔀 STEP 3: ISOLATED ENGINE ROUTING TRACKS ───
#     if strategy in ("GRID_COLUMN_FLOW_V2", "STRICT_MATRIX_V2"):
#         logger.info(f"📐 Invoking Next-Gen Grid Flow Engine (V2 - Sanitized Layout)...")
#         return strict_matrix_v2.execute(
#             pages_raw_data, template_obj, account_id, existing_database_hashes
#         )

#     elif strategy in ("GRID_COLUMN_FLOW_V3", "STRICT_MATRIX_V3", "SIB_LEGACY_FLOW"):
#         logger.info(f"📐 Invoking Legacy Wrapped Sequence Engine (V3)...")
#         return strict_matrix_v3.execute(
#             pages_raw_data, template_obj, account_id, existing_database_hashes
#         )

#     elif strategy in ("GRID_COLUMN_FLOW", "STRICT_MATRIX"):
#         logger.info(f"📐 Invoking Legacy Federal Grid Lane Flow Engine...")
#         return strict_matrix.execute(
#             pages_raw_data, template_obj, account_id, existing_database_hashes
#         )

#     elif strategy in ("NARRATIVE_INLINE_FLOW", "RELATIVE_MATRIX", "RELATIVE_SEQUENCE"):
#         logger.info(f"🔄 Invoking SBI Narrative Inline Flow Engine...")
#         return relative_matrix.execute(
#             pages_raw_data, template_obj, account_id, existing_database_hashes
#         )

#     else:
#         raise ValueError(
#             f"❌ Pipeline Blocked: Unsupported strategy classification '{strategy}'."
#         )
