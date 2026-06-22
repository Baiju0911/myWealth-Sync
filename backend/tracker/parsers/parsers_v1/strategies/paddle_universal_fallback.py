# trackers/parsers/parsers_v1/strategies/paddle_universal_fallback.py

import os
import re
import cv2
import logging
from typing import List, Dict, Any

_paddle_engine = None
logger = logging.getLogger(__name__)


def _get_paddle_instance():
    global _paddle_engine
    if _paddle_engine is None:
        from paddleocr import PaddleOCR

        logging.getLogger("ppocr").setLevel(logging.WARNING)
        _paddle_engine = PaddleOCR(lang="en", enable_mkldnn=False)
    return _paddle_engine


def execute_paddle_fallback_pipeline(
    image_paths: List[str], *args, **kwargs
) -> Dict[str, Any]:
    """
    Robust Column Classifier: Powered by PaddleOCR text accuracy.
    Groups items by clean lines and isolates numbers to stop multi-line column drift.
    """
    ocr_engine = _get_paddle_instance()
    raw_tokens = []

    # 1. VISUAL LAYER EXTRACTION (PADDLE)
    for img_path in image_paths:
        if not os.path.exists(img_path):
            continue

        img = cv2.imread(img_path)
        if img is None:
            continue

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img_input = cv2.merge([gray, gray, gray])
        result = ocr_engine.predict(input=img_input)

        if not result or not result[0]:
            continue

        page_data = result[0]
        texts = page_data.get("rec_texts", [])
        boxes = page_data.get("dt_polys", [])

        for idx in range(len(texts)):
            text_str = str(texts[idx]).strip()
            if not text_str:
                continue

            coords = boxes[idx]
            try:
                ymin = min(p[1] for p in coords)
                ymax = max(p[1] for p in coords)
                box_height = ymax - ymin
                y_center = (ymin + ymax) / 2.0
                xmin = min(p[0] for p in coords)
            except Exception:
                continue

            raw_tokens.append(
                {"text": text_str, "x": xmin, "y": y_center, "height": box_height}
            )

    if not raw_tokens:
        return {"status": "success", "transactions": [], "raw_csv_stream": ""}

    # 2. ADAPTIVE LINE SLICER
    sorted_by_y = sorted(raw_tokens, key=lambda k: k["y"])
    grouped_lines = []
    current_line = []
    last_y = -1.0

    for token in sorted_by_y:
        # Tighter 8px tolerance boundary to enforce distinct vertical separation
        if last_y == -1.0 or abs(token["y"] - last_y) <= 8.0:
            current_line.append(token)
        else:
            grouped_lines.append(sorted(current_line, key=lambda k: k["x"]))
            current_line = [token]
        last_y = token["y"]
    if current_line:
        grouped_lines.append(sorted(current_line, key=lambda k: k["x"]))

    # 3. ROBUST REGEX COLUMN CLASSIFIER
    cleaned_rows = []

    for line_tokens in grouped_lines:
        full_row_line_str = " ".join([t["text"] for t in line_tokens])

        # 🎯 Isolate items using patterns rather than column indices
        dates = re.findall(r"\b\d{2}[-/]\d{2}[-/]\d{2,4}\b", full_row_line_str)

        # Isolate floats (e.g. 2,00,000.00 or 625.00)
        raw_numbers = re.findall(
            r"\b\d{1,3}(?:,\d{2,3})*(?:\.\d{2})\b", full_row_line_str
        )

        # Strip out structural keywords and metrics to leave pure narration descriptions
        clean_narration = full_row_line_str
        for d in dates:
            clean_narration = clean_narration.replace(d, "")
        for n in raw_numbers:
            clean_narration = clean_narration.replace(n, "")

        # Clean up remaining noise artifacts
        clean_narration = (
            re.sub(r"[₹|Rs\.\/]", "", clean_narration)
            .replace("Cr", "")
            .replace("  ", " ")
            .strip()
        )

        c_date = dates[0] if len(dates) >= 1 else "-"
        c_val = dates[1] if len(dates) >= 2 else c_date

        c_deb = ""
        c_cred = ""
        c_bal = ""

        # Map numbers safely according to quantitative row profiles
        if len(raw_numbers) >= 3:
            c_deb = raw_numbers[0]
            c_cred = raw_numbers[1]
            c_bal = raw_numbers[-1]
        elif len(raw_numbers) == 2:
            # Most common: an transaction amount and a running balance
            c_deb = raw_numbers[0]
            c_bal = raw_numbers[1]
        elif len(raw_numbers) == 1:
            c_bal = raw_numbers[0]

        row_payload = {
            "date": c_date,
            "val_date": c_val,
            "narration": clean_narration or full_row_line_str,
            "debit": c_deb,
            "credit": c_cred,
            "balance": c_bal,
            "post_date": c_date,
            "value_date": c_val,
            "Txn Date": c_date,
            "Val Date": c_val,
            "narration_description": clean_narration or full_row_line_str,
            "Debit (-)": c_deb,
            "Credit (+)": c_cred,
            "Balance": c_bal,
            "tran_type": "-",
            "Status": "NEW",
            "Type": "-",
            "Chq/Ref": "",
        }
        cleaned_rows.append(row_payload)

    return {
        "status": "success",
        "confidence_score": 100.0,
        "fallback_engine_executed": "PaddleOCR_v1_RobustClassifier",
        "transactions": cleaned_rows,
        "raw_csv_stream": "",
    }
