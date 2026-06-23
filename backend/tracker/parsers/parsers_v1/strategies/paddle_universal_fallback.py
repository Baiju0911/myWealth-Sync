# trackers/parsers/parsers_v1/strategies/paddle_universal_fallback.py

import os
import re
import cv2
import logging
import pprint
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
    Strict Geometric Intersection Parser:
    Dynamically maps columns based on horizontal bounding box overlap with page headers.
    Keeps debug logging and structural array object printers fully functional.
    """
    ocr_engine = _get_paddle_instance()
    final_processed_rows = []

    for page_idx, img_path in enumerate(image_paths):
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

        # ─── 📊 LIVE DIAGNOSTIC MONITOR PRINTS ────────────────────────────
        page_tokens = []
        print(f"\n🔍 ====== PADDLEOCR RAW CONTENT LOG (PAGE INDEX: {page_idx}) ======")

        for idx in range(len(texts)):
            text_str = str(texts[idx]).strip()
            if not text_str:
                continue
            coords = boxes[idx]
            try:
                ymin = min(p[1] for p in coords)
                ymax = max(p[1] for p in coords)
                xmin = min(p[0] for p in coords)
                xmax = max(p[0] for p in coords)
                y_center = (ymin + ymax) / 2.0
            except Exception:
                continue

            print(
                f"📍 Text: '{text_str:<45}' | X: [{int(xmin):>4} -> {int(xmax):<4}] | Y-Center: {int(y_center)}"
            )

            page_tokens.append(
                {
                    "text": text_str,
                    "xmin": xmin,
                    "xmax": xmax,
                    "y": y_center,
                    "height": ymax - ymin,
                }
            )

        print("==================================================================\n")

        print(f"📋 === FULL PAGE_TOKENS STRUCT OBJECTS (PAGE INDEX: {page_idx}) ===")
        pprint.pprint(page_tokens)
        print("==================================================================\n")

        if not page_tokens:
            continue

        # ─── 1. UNIVERSAL HEADER ANCHOR SCANNER ────────────────────────────
        header_y = None

        # Adaptive tracking boxes
        bounds = {
            "date": {"min": 0, "max": 80},
            "debit": {"min": None, "max": None},
            "credit": {"min": None, "max": None},
            "balance": {"min": None, "max": None},
        }

        for token in page_tokens:
            txt = token["text"].upper()

            # Universal match matrix covering typical bank naming variants
            if any(k in txt for k in ["TXN DATE", "VALUE DATE", "VAL DATE"]) or (
                txt == "DATE" and bounds["debit"]["min"] is None
            ):
                bounds["date"]["min"] = token["xmin"]
                bounds["date"]["max"] = token["xmax"]
                header_y = token["y"]
            elif any(
                k in txt for k in ["WITHDRAWAL", "DEBIT", "WITHDRAMALS", "DEBIT(-)"]
            ):
                bounds["debit"]["min"] = token["xmin"]
                bounds["debit"]["max"] = token["xmax"]
                header_y = token["y"]
            elif any(k in txt for k in ["DEPOSIT", "CREDIT", "DEPOSITS", "CREDIT(+)"]):
                bounds["credit"]["min"] = token["xmin"]
                bounds["credit"]["max"] = token["xmax"]
                header_y = token["y"]
            elif "BALANCE" in txt:
                bounds["balance"]["min"] = token["xmin"]
                bounds["balance"]["max"] = token["xmax"]
                header_y = token["y"]

        # Dynamic fallback offsets if specialized headers can't be matched
        img_width = img.shape[1]
        if bounds["debit"]["min"] is None:
            bounds["debit"] = {"min": img_width * 0.52, "max": img_width * 0.68}
        if bounds["credit"]["min"] is None:
            bounds["credit"] = {"min": img_width * 0.68, "max": img_width * 0.83}
        if bounds["balance"]["min"] is None:
            bounds["balance"] = {"min": img_width * 0.83, "max": img_width * 0.98}
        if header_y is None:
            header_y = 175.0

        # ─── 2. ADAPTIVE ROW SLICER (8px line grouping tolerance) ──────────
        data_tokens = [t for t in page_tokens if t["y"] > header_y]
        sorted_by_y = sorted(data_tokens, key=lambda k: k["y"])

        grouped_lines = []
        current_line = []
        last_y = -1.0

        for token in sorted_by_y:
            if last_y == -1.0 or abs(token["y"] - last_y) <= 8.0:
                current_line.append(token)
            else:
                grouped_lines.append(sorted(current_line, key=lambda k: k["xmin"]))
                current_line = [token]
            last_y = token["y"]
        if current_line:
            grouped_lines.append(sorted(current_line, key=lambda k: k["xmin"]))

        # ─── 3. INTERSECTION-BASED DATA ASSIGNMENT ─────────────────────────
        for line in grouped_lines:
            line_str = " ".join([t["text"] for t in line])
            if "PAGE TOTAL" in line_str.upper():
                continue

            c_date = None
            c_deb = ""
            c_cred = ""
            c_bal = ""
            narration_tokens = []

            for item in line:
                val = item["text"]

                # Dynamic intersection helper
                def get_overlap_percentage(b_key: str) -> float:
                    b = bounds[b_key]
                    if b["min"] is None or b["max"] is None:
                        return 0.0
                    overlap_min = max(item["xmin"], b["min"])
                    overlap_max = min(item["xmax"], b["max"])
                    if overlap_min < overlap_max:
                        return (overlap_max - overlap_min) / float(
                            item["xmax"] - item["xmin"]
                        )
                    return 0.0

                # A. Date validation matrix
                date_match = re.search(r"\b\d{2}[-/]\d{2}[-/]\d{2,4}\b", val)
                if date_match and item["xmin"] < (
                    bounds["debit"]["min"] or img_width * 0.5
                ):
                    c_date = date_match.group(0)
                    continue

                # B. Number extraction check
                clean_num = (
                    val.replace(",", "")
                    .replace("Cr", "")
                    .replace("Cz", "")
                    .replace("Dr", "")
                    .strip()
                )
                is_numeric = False
                if any(c.isdigit() for c in clean_num) and not re.search(
                    r"[a-zA-Z]{3,}", val
                ):
                    if len(clean_num.split(".")[0]) <= 9:
                        is_numeric = True

                if is_numeric:
                    overlap_deb = get_overlap_percentage("debit")
                    overlap_cred = get_overlap_percentage("credit")
                    overlap_bal = get_overlap_percentage("balance")

                    # Route to column with highest horizontal intersection percentage
                    max_overlap = max(overlap_deb, overlap_cred, overlap_bal)

                    if max_overlap > 0.15:
                        if max_overlap == overlap_deb:
                            c_deb = val
                        elif max_overlap == overlap_cred:
                            c_cred = val
                        else:
                            c_bal = val
                    else:
                        # Fallback step based on positioning if intersection fails
                        mid_x = (item["xmin"] + item["xmax"]) / 2.0
                        if mid_x >= bounds["balance"]["min"] - 15 or any(
                            k in val for k in ["Cz", "Cr", "Dr"]
                        ):
                            c_bal = val
                        elif mid_x >= bounds["credit"]["min"] - 10:
                            c_cred = val
                        elif mid_x >= bounds["debit"]["min"] - 10:
                            c_deb = val
                        else:
                            narration_tokens.append(val)
                else:
                    if val not in ["₹", "Rs.", "|", ""]:
                        narration_tokens.append(val)

            c_narr = " ".join(narration_tokens).strip()

            # C. Sub-line Continuation Aggregator
            if c_date is None:
                if final_processed_rows and (c_narr or c_deb or c_cred or c_bal):
                    target_row = final_processed_rows[-1]
                    if c_narr:
                        target_row["narration"] += f" {c_narr}"
                        target_row["narration_description"] = target_row["narration"]
                    if c_deb:
                        target_row["debit"] = c_deb
                        target_row["Debit (-)"] = c_deb
                    if c_cred:
                        target_row["credit"] = c_cred
                        target_row["Credit (+)"] = c_cred
                    if c_bal:
                        target_row["balance"] = c_bal
                        target_row["Balance"] = c_bal
                continue

            row_payload = {
                "date": c_date,
                "val_date": c_date,
                "narration": c_narr,
                "debit": c_deb,
                "credit": c_cred,
                "balance": c_bal,
                "post_date": c_date,
                "value_date": c_date,
                "Txn Date": c_date,
                "Val Date": c_date,
                "narration_description": c_narr,
                "Debit (-)": c_deb,
                "Credit (+)": c_cred,
                "Balance": c_bal,
                "tran_type": "-",
                "Status": "NEW",
                "Type": "-",
                "Chq/Ref": "",
            }
            final_processed_rows.append(row_payload)

    return {
        "status": "success",
        "confidence_score": 100.0,
        "fallback_engine_executed": "PaddleOCR_v1_StrictOverlap",
        "transactions": final_processed_rows,
        "raw_csv_stream": "",
    }
