import logging
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
        if not pages_raw_data:
            return [], 0.0, []
    except Exception as e:
        logger.error(f"❌ Geometric tokenization failed: {str(e)}")
        raise e

    # ─── 🧬 STEP 2: RUN DECRYPTED STRING SIGNATURE INSPECTION ───
    candidate_templates = UserStatementTemplate.objects.filter(account_id=account_id)

    if candidate_templates.count() > 1:
        logger.info(
            f"🔍 Multi-Template Context Active for Account {account_id}. Analyzing text structures..."
        )

        # Consolidate the first 3 lines of plain text extracted from Page 1
        page_sample_text = ""
        if pages_raw_data and "words" in pages_raw_data[0]:
            # Pull text strings from the extracted spatial word blocks
            sample_words = [str(w[4]).strip() for w in pages_raw_data[0]["words"][:150]]
            page_sample_text = " ".join(sample_words).lower()

        # 🎯 LOOK FOR THE CHARACTERISTIC LEGACY DIVIDER SIGNATURE
        if (
            "---" in page_sample_text
            or "particulars" in page_sample_text
            or "chq.no" in page_sample_text
        ):
            matched_template = candidate_templates.filter(
                parser_strategy_code="GRID_COLUMN_FLOW_V3"
            ).first()
            if matched_template:
                logger.info(
                    "🎯 Layout Signature Auto-Match: Routing to Legacy Wrapped Sequence Engine (V3)"
                )
                template_obj = matched_template
        else:
            matched_template = candidate_templates.filter(
                parser_strategy_code="GRID_COLUMN_FLOW_V2"
            ).first()
            if matched_template:
                logger.info(
                    "🎯 Layout Signature Auto-Match: Routing to Modern Matrix Engine (V2)"
                )
                template_obj = matched_template

    # Unpack properties dynamically post-inspection
    template_name = getattr(template_obj, "template_name", "UNKNOWN")
    strategy = getattr(template_obj, "parser_strategy_code", "GRID_COLUMN_FLOW").upper()

    logger.info(
        f"⚡ Ingestion Pipeline Active | Template: {template_name} | Strategy: {strategy}"
    )

    # ─── 🔀 STEP 3: ISOLATED ENGINE ROUTING TRACKS ───
    if strategy in ("GRID_COLUMN_FLOW_V2", "STRICT_MATRIX_V2"):
        logger.info(f"📐 Invoking Next-Gen Grid Flow Engine (V2 - Sanitized Layout)...")
        return strict_matrix_v2.execute(
            pages_raw_data, template_obj, account_id, existing_database_hashes
        )

    elif strategy in ("GRID_COLUMN_FLOW_V3", "STRICT_MATRIX_V3", "SIB_LEGACY_FLOW"):
        logger.info(f"📐 Invoking Legacy Wrapped Sequence Engine (V3)...")
        return strict_matrix_v3.execute(
            pages_raw_data, template_obj, account_id, existing_database_hashes
        )

    elif strategy in ("GRID_COLUMN_FLOW", "STRICT_MATRIX"):
        logger.info(f"📐 Invoking Legacy Federal Grid Lane Flow Engine...")
        return strict_matrix.execute(
            pages_raw_data, template_obj, account_id, existing_database_hashes
        )

    elif strategy in ("NARRATIVE_INLINE_FLOW", "RELATIVE_MATRIX", "RELATIVE_SEQUENCE"):
        logger.info(f"🔄 Invoking SBI Narrative Inline Flow Engine...")
        return relative_matrix.execute(
            pages_raw_data, template_obj, account_id, existing_database_hashes
        )

    else:
        raise ValueError(
            f"❌ Pipeline Blocked: Unsupported strategy classification '{strategy}'."
        )
