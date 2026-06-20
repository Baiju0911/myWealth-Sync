import sys
import time
import pandas as pd
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
)  # 🟢 FIX: Import the PDF-specific options class
from docling.datamodel.base_models import InputFormat


def run_docling_safe_test():
    sample_pdf_path = "statement-67093359418.pdf"

    print("⏳ Configuring native PDF layout options...")

    # ─── 🟢 FIXED: INJECTING PROPER PDF PROPERTIES ───
    pipeline_options = PdfPipelineOptions()

    # Instruct the engine to process using native vector text extraction directly
    pipeline_options.force_backend_text = True

    # Disable the image-rendering OCR tracking engine completely to save memory
    pipeline_options.do_ocr = False
    pipeline_options.generate_page_images = False

    # Pack the options cleanly into the Converter using the explicit PDF format option wrapper
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

    print(f"🚀 Parsing file with text-stream extraction: '{sample_pdf_path}'...")
    start_time = time.time()

    try:
        conv_res = converter.convert(sample_pdf_path)
        discovered_tables = conv_res.document.tables
        print(
            f"\n🎯 Complete! Processed everything smoothly in {time.time() - start_time:.2f} seconds."
        )
        print(f"📌 Total isolated data tables discovered: {len(discovered_tables)}\n")

        if not discovered_tables:
            print("❌ No structured ledger tables detected on the document layer.")
            return

        # Let's inspect the very first table block discovered
        first_table = discovered_tables[0]
        df = first_table.export_to_dataframe()
        print("📊 --- SAMPLE LEDGER OUTPUT ---")
        print(df.head(15).to_string())
        print("-" * 50)

    except Exception as e:
        print(f"⚠️ Runtime Test Error: {str(e)}")


if __name__ == "__main__":
    run_docling_safe_test()
