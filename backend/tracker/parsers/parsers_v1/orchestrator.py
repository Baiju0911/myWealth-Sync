import logging
import os
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from .engine import extract_raw_tokens
from .strategies import strict_matrix
from .strategies import (
    strict_matrix_v2,
    strict_matrix_v3,
)
from .strategies import relative_matrix
from tracker.models import (
    UserStatementTemplate,
)  # 🎯 Ensure absolute path match to your models folder

# ─── 🔌 NEW FALLBACK & CONFIDENCE IMPORTS ───────────────────────────────────
from .parser_orchestrator import FallbackOrchestratorService
from .confidence.evaluator import ConfidenceEvaluator
from .geometry.lane_detector import StructuredRow

logger = logging.getLogger(__name__)


def process_bank_statement(
    uploaded_file,
    template_obj,
    account_id,
    existing_database_hashes=None,
    password_vault=None,
):
    if existing_database_hashes is None:
        existing_database_hashes = set()

    # ─── 🛡️ STEP 1: EXTRACT DECRYPTED TEXT TOKENS FIRST ───
    try:
        pages_raw_data = extract_raw_tokens(
            uploaded_file, password_vault_raw=password_vault
        )
    except Exception as e:
        logger.error(f"❌ Geometric tokenization failed: {str(e)}")
        logger.warning(
            "🔀 Tokenization failed. Escalating to Intelligent Fallback Layer..."
        )
        return _run_paddle_fallback_bridge(uploaded_file, template_obj)

    # 👇 CRITICAL GATEWAY: If PyMuPDF extracts zero text, it is an image scan!
    if not pages_raw_data:
        logger.info(
            "📸 No native text streams detected. Redirecting to PaddleOCR Fallback..."
        )
        return _run_paddle_fallback_bridge(uploaded_file, template_obj)

    # ─── 🧬 STEP 2: HYBRID ACCOUNTS SIGNATURE ENGINE (INDENTATION FIXED) ───
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
            # 🎯 TWIN-TRACK FINGERPRINT MATCH
            if "SWIFT CODE" in page_sample_upper or "CKYC ID" in page_sample_upper:
                matched_template = candidate_templates.filter(
                    parser_strategy_code="GRID_COLUMN_FLOW_V2"
                ).first()
                if matched_template:
                    logger.info(
                        "🎯 Fingerprint Match: Modern SIB detected. Routing to Matrix Engine (V2)"
                    )
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
                    logger.info(
                        "🎯 Fingerprint Match: Legacy SIB detected. Routing to Sequence Engine (V3)"
                    )
                    template_obj = matched_template
            else:
                # Safe fallback default choice for SIB variants
                matched_template = candidate_templates.filter(
                    parser_strategy_code="GRID_COLUMN_FLOW_V2"
                ).first()
                if matched_template:
                    logger.info(
                        "🎯 Fingerprint Match: Routing SIB to Modern Matrix Engine (V2)"
                    )
                    template_obj = matched_template

        # 🎯 TRACK 2: Standard fallbacks for other banks (SBI, Federal, etc.)
        elif (
            "---" in page_sample_upper
            or "PARTICULARS" in page_sample_upper
            or "CHQ.NO" in page_sample_upper
            or "CHQ .NO" in page_sample_upper
        ):
            matched_template = candidate_templates.filter(
                parser_strategy_code="GRID_COLUMN_FLOW_V3"
            ).first()
            if matched_template:
                logger.info(
                    "🎯 Layout Signature Auto-Match: Routing to standard V3 Engine"
                )
                template_obj = matched_template
        else:
            matched_template = candidate_templates.filter(
                parser_strategy_code="GRID_COLUMN_FLOW_V2"
            ).first()
            if matched_template:
                logger.info(
                    "🎯 Layout Signature Auto-Match: Routing to standard V2 Engine"
                )
                template_obj = matched_template

    template_name = getattr(template_obj, "template_name", "UNKNOWN")
    strategy = getattr(template_obj, "parser_strategy_code", "GRID_COLUMN_FLOW").upper()

    logger.info(
        f"⚡ Ingestion Pipeline Active | Template: {template_name} | Strategy: {strategy}"
    )

    # ─── 🔀 STEP 3: ISOLATED ENGINE ROUTING TRACKS ───
    try:
        if strategy in ("GRID_COLUMN_FLOW_V2", "STRICT_MATRIX_V2"):
            logger.info(f"📐 Invoking Next-Gen Grid Flow Engine (V2)...")
            txns, bal, errs = strict_matrix_v2.execute(
                pages_raw_data, template_obj, account_id, existing_database_hashes
            )

        elif strategy in ("GRID_COLUMN_FLOW_V3", "STRICT_MATRIX_V3", "SIB_LEGACY_FLOW"):
            logger.info(f"📐 Invoking Legacy Wrapped Sequence Engine (V3)...")
            txns, bal, errs = strict_matrix_v3.execute(
                pages_raw_data, template_obj, account_id, existing_database_hashes
            )

        elif strategy in ("GRID_COLUMN_FLOW", "STRICT_MATRIX"):
            logger.info(f"📐 Invoking Legacy Federal Grid Lane Flow Engine...")
            txns, bal, errs = strict_matrix.execute(
                pages_raw_data, template_obj, account_id, existing_database_hashes
            )

        elif strategy in (
            "NARRATIVE_INLINE_FLOW",
            "RELATIVE_MATRIX",
            "RELATIVE_SEQUENCE",
        ):
            logger.info(f"🔄 Invoking SBI Narrative Inline Flow Engine...")
            txns, bal, errs = relative_matrix.execute(
                pages_raw_data, template_obj, account_id, existing_database_hashes
            )

        else:
            raise ValueError(f"❌ Unsupported strategy classification '{strategy}'.")

        # ─── ⚖️ NEW STEP 4: AUTOMATED QUALITY ASSURANCE CIRCUIT BREAKER ───────────
        eval_rows = []
        print(f"\n===== 🔍 DEBUGGING FAST LANE OUTPUT (Total: {len(txns)} items) =====")
        for idx, tx in enumerate(txns[:15]):
            print(f"Raw txn [{idx}]: {tx}")

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

            has_money_or_bal = dr_str != "" or cr_str != "" or bal_str != ""

            if not tx_date and not has_money_or_bal and tx_narration:
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

        print(
            f"🔄 Grouped Multi-Line Rows into {len(eval_rows)} Unified Transaction Envelopes."
        )
        print(f"Mapped eval_rows count: {len(eval_rows)}")

        confidence_score = ConfidenceEvaluator.evaluate_dataset(eval_rows)
        print(f"💥 RESULTING CONFIDENCE SCORE: {confidence_score}%")
        print("=====================================================\n")

        logger.info(
            f"📊 Fast Lane Execution Quality Confidence Score: {confidence_score}%"
        )

        if confidence_score >= 95:
            return txns, bal, errs

        logger.warning(
            f"⚠️ Low confidence calculation performance ({confidence_score}%). Tripping circuit breaker..."
        )

    except Exception as engine_error:
        logger.error(f"💥 Fast Lane Engine runtime crash: {str(engine_error)}")
        logger.warning(
            "Rerouting parsing payload execution to intelligent fallback runner..."
        )

    return _run_paddle_fallback_bridge(uploaded_file, template_obj)


def _run_paddle_fallback_bridge(uploaded_file, template_obj):
    logger.info(
        "🐼 Invoking Fallback System Core (PaddleOCR + Geometry Engine Matrix)..."
    )

    # 🎯 FIX: Ensure we always have a real, absolute disk path for OpenCV/Paddle
    if hasattr(uploaded_file, "temporary_file_path"):
        image_paths_list = [uploaded_file.temporary_file_path()]
    else:
        logger.info("💾 File is in memory. Writing temporary copy to disk path...")

        # 🎯 THE ESSENTIAL RESET: Move the stream pointer back to the beginning of the file
        uploaded_file.seek(0)

        # Now read the full binary content safely
        temp_filename = default_storage.save(
            f"temp_ocr_{uploaded_file.name}", ContentFile(uploaded_file.read())
        )

        # Get absolute system file track location path
        absolute_path = os.path.abspath(default_storage.path(temp_filename))
        image_paths_list = [absolute_path]

        # Reset memory pointer again for standard reuse safety downstream
        uploaded_file.seek(0)
    logger.info(f"📁 Processing absolute target path: {image_paths_list}")

    lane_override = getattr(template_obj, "coordinates_json", None)
    if not lane_override:
        lane_override = None

        fallback_result = FallbackOrchestratorService.process_failed_document(
            image_paths=image_paths_list, bank_template_override=lane_override
        )

        # 🧼 CLEANUP HOUSEKEEPING: Delete our temporary file copy after parsing wraps up
        if not hasattr(uploaded_file, "temporary_file_path") and os.path.exists(
            image_paths_list[0]
        ):
            try:
                os.remove(image_paths_list[0])
                logger.info("🧼 Temporary image file copy deleted successfully.")
            except Exception as e:
                logger.warning(f"⚠️ Could not delete temp copy: {str(e)}")

        # Unpack target transaction collections safely
        transactions = fallback_result.get("transactions", [])

        # 🎯 EXTRACT THE RAW CSV STREAM VALUE HERE
        # Store it directly inside the transaction list object attributes so it skips upstream filters!
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
                f"Low quality validation output warning. OCR Confidence Score: {fallback_result.get('confidence_score')}%"
            )

        # ─── 🎯 THE COUPLING UNIFICATION FIX ─────────────────────────────────────
        # Instead of breaking structural contracts by converting transactions to a string,
        # wrap the return list in a dictionary structure that includes the raw_csv_stream property.
        # Your upstream validation checker can inspect if it's a dictionary container wrapper.

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
