# tracker/parsers/unified_csv_format.py
import io
import csv
import zipfile
import decimal
import datetime
import traceback
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from tracker.models import Account, StatementStagingLine, BankCredential
from .utils import generate_row_fingerprint


def _safe_float(val_str):
    if not val_str:
        return 0.0
    try:
        clean_str = str(val_str).replace(",", "").strip()
        return float(clean_str) if clean_str else 0.0
    except (ValueError, TypeError):
        return 0.0


def process_unified_csv_statement(request):
    """
    🚀 UNIFIED TRI-BANK CSV ENGINE (PASSWORD VAPORIZER EDITION):
    Dynamically attempts vault decryption if a zipped spreadsheet lands,
    then processes structural bank matrices smoothly.
    """
    try:
        uploaded_file = request.FILES.get("statement_file")
        account_id = request.data.get("account_id")

        if not uploaded_file or not account_id:
            return Response(
                {"message": "Required fields missing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        account = get_object_or_404(Account, id=account_id)
        bank = account.bank
        filename = uploaded_file.name.lower()

        credential = BankCredential.objects.filter(account=account).first()
        password_pool = (
            credential.password_vault
            if credential and isinstance(credential.password_vault, list)
            else []
        )

        file_data = ""
        was_encrypted = False

        if filename.endswith(".zip"):
            was_encrypted = True
            zip_bytes = io.BytesIO(uploaded_file.read())

            with zipfile.ZipFile(zip_bytes) as zf:
                csv_targets = [
                    name for name in zf.namelist() if name.lower().endswith(".csv")
                ]
                if not csv_targets:
                    return Response(
                        {
                            "message": "No valid CSV file found inside uploaded ZIP archive."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                target_csv_name = csv_targets[0]
                decryption_successful = False

                if not password_pool:
                    return Response(
                        {
                            "status": "ERROR",
                            "message": f"ZIP archive is locked, but no password vault is configured for {account.name}.",
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

                for current_passphrase in password_pool:
                    try:
                        pwd_bytes = str(current_passphrase).strip().encode("utf-8")
                        with zf.open(target_csv_name, pwd=pwd_bytes) as extracted_file:
                            file_data = extracted_file.read().decode("utf-8-sig")
                            decryption_successful = True
                            print(
                                "🔓 [CSV ZIP UNLOCKED] Match verified using vault pool variant index."
                            )
                            break
                    except (RuntimeError, zipfile.BadZipFile, UnicodeDecodeError):
                        continue

                if not decryption_successful:
                    return Response(
                        {
                            "status": "ERROR",
                            "message": f"Tried {len(password_pool)} vault keys, but all variants were rejected by the ZIP wrapper.",
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
        else:
            file_data = uploaded_file.read().decode("utf-8-sig")

        csv_reader = csv.reader(io.StringIO(file_data))

        raw_rows = []
        for row in csv_reader:
            if not row:
                continue
            clean_row = []
            for cell in row:
                c = (
                    cell.replace('"', "")
                    .replace("'", "")
                    .replace("\n", " ")
                    .replace("\r", " ")
                    .strip()
                )
                c = " ".join(c.split())
                clean_row.append(c)
            if any(clean_row):
                raw_rows.append(clean_row)

        bank_flavor = None
        header_index = -1
        column_mapping = {}

        for idx, row in enumerate(raw_rows[:20]):
            row_normalized = [cell.lower() for cell in row]

            def find_col_idx(keywords):
                for cell_idx, cell_text in enumerate(row_normalized):
                    if any(kw in cell_text for kw in keywords):
                        return cell_idx
                return None

            has_debit = any("debit" in c or "withdrawal" in c for c in row_normalized)
            has_credit = any("credit" in c or "deposit" in c for c in row_normalized)
            has_balance = any("balance" in c for c in row_normalized)

            if has_debit and has_credit and has_balance:
                row_combined_str = " ".join(row_normalized)

                if (
                    "tran id" in row_combined_str
                    or "tran type" in row_combined_str
                    or "cheque details" in row_combined_str
                ):
                    bank_flavor = "FED"
                    header_index = idx
                    column_mapping = {
                        "date": find_col_idx(["date"]),
                        "value_date": find_col_idx(["value date"]),
                        "narration": find_col_idx(
                            ["particulars", "description", "narration"]
                        ),
                        "tran_type": find_col_idx(["tran type", "type"]),
                        "cheque_ref": find_col_idx(
                            ["cheque details", "chq details", "cheque"]
                        ),
                        "debit": find_col_idx(["withdrawals", "debit"]),
                        "credit": find_col_idx(["deposits", "credit"]),
                        "balance": find_col_idx(["balance"]),
                    }
                    break
                elif "particulars" in row_combined_str and "chq" in row_combined_str:
                    bank_flavor = "SIB"
                    header_index = idx
                    column_mapping = {
                        "date": find_col_idx(["date"]),
                        "narration": find_col_idx(["particulars"]),
                        "cheque_ref": find_col_idx(["chq .no.", "chq no", "chq"]),
                        "debit": find_col_idx(["withdrawals"]),
                        "credit": find_col_idx(["deposits"]),
                        "balance": find_col_idx(["balance"]),
                    }
                    break
                else:
                    bank_flavor = "SBI"
                    header_index = idx
                    column_mapping = {
                        "date": find_col_idx(["post date", "date"]),
                        "value_date": find_col_idx(["value date"]),
                        "narration": find_col_idx(["description", "narration"]),
                        "cheque_ref": find_col_idx(["cheque no/reference", "cheque"]),
                        "debit": find_col_idx(["debit"]),
                        "credit": find_col_idx(["credit"]),
                        "balance": find_col_idx(["balance"]),
                    }
                    break

        if not bank_flavor or header_index == -1:
            return Response(
                {
                    "error": "CSV Parser could not safely align header columns. Verify file schema format."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        staged_records_preview = []
        existing_identifiers = set(
            StatementStagingLine.objects.filter(account_id=account.id).values_list(
                "row_identifier", flat=True
            )
        )

        total_debit_sum = total_credit_sum = decimal.Decimal("0.00")
        debit_count = credit_count = duplicate_count = 0
        opening_balance_final = None
        closing_balance_final = None

        print("\n🔎 " + "═" * 35 + " [FINGERPRINT ENGINE RADAR LOOP] " + "═" * 35)

        for idx, row in enumerate(raw_rows[header_index + 1 :]):
            if not row or len(row) < 3:
                continue
            if any(
                marker in str(row[0]).lower()
                for marker in ["total", "disclaimer", "page", "***"]
            ):
                continue

            try:

                def get_cell(key):
                    cell_idx = column_mapping.get(key)
                    return (
                        row[cell_idx].strip()
                        if cell_idx is not None and cell_idx < len(row)
                        else ""
                    )

                raw_date_str = get_cell("date")
                raw_balance_str = get_cell("balance").replace(",", "")
                raw_narration = get_cell("narration")

                if (
                    any("opening balance" in str(cell).lower() for cell in row)
                    and raw_balance_str
                ):
                    try:
                        opening_balance_final = decimal.Decimal(str(raw_balance_str))
                    except (decimal.InvalidOperation, ValueError):
                        pass
                    continue

                if not raw_date_str or not raw_balance_str:
                    continue

                current_balance = decimal.Decimal(str(raw_balance_str))

                if opening_balance_final is None:
                    p_deb = _safe_float(get_cell("debit"))
                    p_cred = _safe_float(get_cell("credit"))
                    try:
                        if p_deb > 0:
                            opening_balance_final = current_balance + decimal.Decimal(
                                f"{p_deb:.2f}"
                            )
                        elif p_cred > 0:
                            opening_balance_final = current_balance - decimal.Decimal(
                                f"{p_cred:.2f}"
                            )
                        else:
                            opening_balance_final = current_balance
                    except (decimal.InvalidOperation, ValueError):
                        opening_balance_final = current_balance

                closing_balance_final = current_balance

                parsed_debit = _safe_float(get_cell("debit"))
                parsed_credit = _safe_float(get_cell("credit"))

                txn_amount = decimal.Decimal("0.00")
                is_debit = True

                if parsed_debit > 0.0:
                    txn_amount = decimal.Decimal(f"{parsed_debit:.2f}")
                    is_debit = True
                    total_debit_sum += txn_amount
                    debit_count += 1
                elif parsed_credit > 0.0:
                    txn_amount = decimal.Decimal(f"{parsed_credit:.2f}")
                    is_debit = False
                    total_credit_sum += txn_amount
                    credit_count += 1
                else:
                    continue

                final_signed_amount = -txn_amount if is_debit else txn_amount
                debit_numeric_val = float(txn_amount) if is_debit else None
                credit_numeric_val = None if is_debit else float(txn_amount)

                tx_date = None
                for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y", "%d-%b-%y"):
                    try:
                        tx_date = datetime.datetime.strptime(raw_date_str, fmt).date()
                        break
                    except ValueError:
                        continue

                if not tx_date:
                    continue

                cheque_reference_id = get_cell("cheque_ref")
                tran_type_val = get_cell("tran_type")

                # 🚀 PASS EXPLICIT UNMUTATED DATA FIELDS TO REMOVE COUPLING DRIFT
                row_hex = generate_row_fingerprint(
                    bank_id=bank.id,
                    account_id=account.id,
                    narration=raw_narration,
                    cheque_ref=cheque_reference_id if cheque_reference_id else None,
                    amount=final_signed_amount,
                    running_balance=current_balance,
                    debit=debit_numeric_val,
                    credit=credit_numeric_val,
                    date_str=str(tx_date),
                )

                is_duplicate = row_hex in existing_identifiers
                if is_duplicate:
                    duplicate_count += 1
                else:
                    existing_identifiers.add(row_hex)

                staged_records_preview.append(
                    {
                        "id": row_hex,
                        "date": tx_date.isoformat(),
                        "description": raw_narration,
                        "tran_type": tran_type_val if tran_type_val else "",
                        "amount": float(final_signed_amount),
                        "debit": debit_numeric_val,
                        "credit": credit_numeric_val,
                        "balance": float(current_balance),  # 🟢 Fixed
                        "running_balance": float(current_balance),  # 🟢 Fixed
                        "cheque_ref": (
                            cheque_reference_id if cheque_reference_id else ""
                        ),
                        "status": "DUPLICATE" if is_duplicate else "PENDING",
                    }
                )

            except Exception as row_error:
                print(
                    f"❌ [CSV ENGINE] Row line exception drop at index {idx}: {str(row_error)}"
                )
                continue

        print("\n" + "═" * 100 + "\n")

        report_from_date = None
        report_to_date = None
        if staged_records_preview:
            try:
                extracted_dates = sorted(
                    [
                        datetime.date.fromisoformat(item["date"])
                        for item in staged_records_preview
                        if item.get("date")
                    ]
                )
                if extracted_dates:
                    report_from_date = extracted_dates[0]
                    report_to_date = extracted_dates[-1]
            except Exception:
                pass

        if (
            opening_balance_final is not None
            and closing_balance_final is not None
            and len(staged_records_preview) > 1
        ):
            if staged_records_preview[0]["date"] > staged_records_preview[-1]["date"]:
                opening_balance_final, closing_balance_final = (
                    closing_balance_final,
                    opening_balance_final,
                )

        return Response(
            {
                "status": "SUCCESS",
                "file_type": "ZIP_CSV" if filename.endswith(".zip") else "CSV",
                "detected_bank": bank_flavor,
                "decrypted": was_encrypted,
                "report_from_date": (
                    report_from_date.isoformat() if report_from_date else None
                ),
                "report_to_date": (
                    report_to_date.isoformat() if report_to_date else None
                ),
                "opening_balance": float(opening_balance_final or 0.00),
                "closing_balance": float(closing_balance_final or 0.00),
                "total_debit": float(total_debit_sum),
                "total_credit": float(total_credit_sum),
                "debit_line_count": debit_count,
                "credit_line_count": credit_count,
                "duplicate_count": duplicate_count,
                "raw_match_count": len(staged_records_preview),
                "count": len(staged_records_preview),
                "preview_dataset": staged_records_preview,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as global_err:
        print("🚨 [CSV GLOBAL CRITICAL BREAKDOWNAGE]")
        traceback.print_exc()
        return Response(
            {"message": f"Staging engine processing failure: {str(global_err)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
