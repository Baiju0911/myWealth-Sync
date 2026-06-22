# trackers/parsers/parsers_v1/canonical/standardizer.py

from .token_schema import CanonicalToken


def standardize_pymupdf_word(
    word_tuple, page_width: float, page_height: float, page_num: int
) -> CanonicalToken:
    """
    Maps PyMuPDF word box tuple to CanonicalToken.
    PyMuPDF native format: (x0, y0, x1, y1, "text", block_no, line_no, word_no)
    """
    x0, y0, x1, y1, text = (
        word_tuple[0],
        word_tuple[1],
        word_tuple[2],
        word_tuple[3],
        word_tuple[4],
    )

    width = x1 - x0
    height = y1 - y0

    return CanonicalToken(
        text=str(text).strip(),
        x_pct=round((x0 / page_width) * 100, 2),
        y_pct=round((y0 / page_height) * 100, 2),
        w_pct=round((width / page_width) * 100, 2),
        h_pct=round((height / page_height) * 100, 2),
        page_num=page_num,
    )


def standardize_paddleocr_box(
    ocr_result_item, img_width: float, img_height: float, page_num: int
) -> CanonicalToken:
    """
    Maps PaddleOCR box item output to CanonicalToken.
    PaddleOCR format: [ [[x0,y0], [x1,y0], [x1,y1], [x0,y1]], ("text_string", confidence_score) ]
    """
    box_matrix, (text, confidence) = ocr_result_item

    x_coords = [point[0] for point in box_matrix]
    y_coords = [point[1] for point in box_matrix]

    xmin, xmax = min(x_coords), max(x_coords)
    ymin, ymax = min(y_coords), max(y_coords)

    width = xmax - xmin
    height = ymax - ymin

    return CanonicalToken(
        text=str(text).strip(),
        x_pct=round((xmin / img_width) * 100, 2),
        y_pct=round((ymin / img_height) * 100, 2),
        w_pct=round((width / img_width) * 100, 2),
        h_pct=round((height / img_height) * 100, 2),
        page_num=page_num,
    )


def _sanitize_merged_ocr_tokens(text_str: str, box_coords: list) -> list:
    """
    Detects if an OCR engine grouped a reference token and an amount into one string.
    Splits them visually into two distinct virtual boxes side-by-side so the geometry
    lane detector doesn't mistake the whole string for a single multi-billion amount.
    Example: "15468 800000.00" -> Two individual token tracking elements.
    """
    cleaned_str = text_str.strip()
    parts = cleaned_str.split()

    # If there's an embedded space and the last segment looks like a numeric amount
    if len(parts) > 1:
        last_part = parts[-1].replace(",", "")
        # Remove trailing flags like CR/DR if present
        if last_part.upper().endswith(("CR", "DR")):
            last_part = last_part[:-2].strip()

        if last_part.replace(".", "", 1).isdigit():
            remaining_prefix = " ".join(parts[:-1])
            actual_amount = parts[-1]

            # Subdivide the bounding box horizontally based on string lengths roughly
            # box_coords looks like: [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]]
            xmin = box_coords[0][0]
            xmax = box_coords[1][0]
            ymin = box_coords[0][1]
            ymax = box_coords[2][1]

            total_width = xmax - xmin
            total_chars = len(cleaned_str)
            prefix_width = (len(remaining_prefix) / total_chars) * total_width

            # Create two fresh separate polygon coordinate matrix frames
            box1 = [
                [xmin, ymin],
                [xmin + prefix_width, ymin],
                [xmin + prefix_width, ymax],
                [xmin, ymax],
            ]
            box2 = [
                [xmin + prefix_width, ymin],
                [xmax, ymin],
                [xmax, ymax],
                [xmin + prefix_width, ymax],
            ]

            return [[box1, (remaining_prefix, 0.99)], [box2, (actual_amount, 0.99)]]

    # Default: return original format unmodified inside an array bundle
    return [[box_coords, (text_str, 0.99)]]
