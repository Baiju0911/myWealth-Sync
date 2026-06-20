import logging
from .engine import extract_raw_tokens
from .strategies import strict_matrix
from .strategies import strict_matrix_v2  # 🎯 Import your fresh V2 layout file!
from .strategies import relative_matrix

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

    template_name = getattr(template_obj, "template_name", "UNKNOWN")
    strategy = getattr(template_obj, "parser_strategy_code", "GRID_COLUMN_FLOW").upper()

    logger.info(
        f"⚡ Ingestion Pipeline Active | Template: {template_name} | Strategy: {strategy}"
    )

    try:
        pages_raw_data = extract_raw_tokens(
            uploaded_file, password_vault_raw=password_vault
        )
        if not pages_raw_data:
            return [], 0.0, []
    except Exception as e:
        logger.error(f"❌ Geometric tokenization failed: {str(e)}")
        raise e

    # ─── 🔀 ISOLATED ENGINE ROUTING TRACKS ───
    if strategy in ("GRID_COLUMN_FLOW_V2", "STRICT_MATRIX_V2"):
        logger.info(f"📐 Invoking Next-Gen Grid Flow Engine (V2 - Sanitized Layout)...")
        return strict_matrix_v2.execute(
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
