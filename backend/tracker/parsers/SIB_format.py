import io
import re
import csv
import decimal
import datetime
import traceback
from pypdf import PdfReader
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from tracker.models import Account, StatementStagingLine, BankCredential
from .utils import generate_row_fingerprint


class SIBEngineParser:
    """
    🔵 SOUTH INDIAN BANK (SIB) PARSER ENGINE:
    Robust single-line and multiline streaming state-machine.
    Handles variable narrative line-wrapping and embedded reference fusions
    with direct, deterministic token assignment. Supports 2-digit and 4-digit years.
    """

    def _is_metadata_noise(self, row_text):
        if not row_text or not row_text.strip():
            return True
        row_text_lower = row_text.lower().strip()
        noise_indicators = [
            "statement of account",
            "date particulars chq",
            "page total",
            "grand total",
            "system-generated statement",
            "page no",
            "visit us at",
            "customer id:",
            "ckyc id:",
            "a/c no:",
            "mode of opr:",
            "nominee:",
            "branch name",
            "ifsc :",
            "thiruvananthapuram",
            "kerala",
            "customercare toll-free",
            "brought forward",
            "b/f",
            "date particulars",
        ]
        return any(indicator in row_text_lower for indicator in noise_indicators)

    def _extract_raw_text(self, uploaded_file, filename, password_pool, account_name):
        was_encrypted = False
        raw_text_stream = ""

        if filename.endswith(".pdf"):
            uploaded_file.seek(0)
            pdf_bytes = io.BytesIO(uploaded_file.read())
            reader = PdfReader(pdf_bytes)

            if reader.is_encrypted:
                was_encrypted = True
                if not password_pool:
                    raise PermissionError(
                        f"PDF is encrypted, but no password vault configured for {account_name}."
                    )

                decryption_successful = False
                for current_passphrase in password_pool:
                    try:
                        if reader.decrypt(str(current_passphrase).strip()):
                            decryption_successful = True
                            print(
                                "🔓 [SIB VAULT] Successfully unlocked PDF document layer."
                            )
                            break
                    except Exception:
                        continue

                if not decryption_successful:
                    raise LookupError(
                        f"Tried {len(password_pool)} historical keys, but all variants were rejected."
                    )

            all_pages_text = [
                page.extract_text() for page in reader.pages if page.extract_text()
            ]
            raw_text_stream = "\n".join(all_pages_text)
        else:
            uploaded_file.seek(0)
            file_stream = io.StringIO(
                uploaded_file.read().decode("utf-8"), newline=None
            )
            csv_reader = csv.reader(file_stream)
            csv_lines = [" ".join(row) for row in csv_reader if row]
            raw_text_stream = "\n".join(csv_lines)

        return raw_text_stream, was_encrypted

    def _detect_and_parse_layout(self, normalized_text, account_profile):
        """
        Stream parses line entries dynamically. Captures financial numbers blocks
        at the trailing end of strings to handle text fusions. Supports 2-digit year lines.
        """
        parsed_transaction_items = []

        # Flex match regex handles both dd-mm-yyyy and dd-mm-yy date lines smoothly
        date_start_regex = re.compile(r"^(\d{2}[-/\.]\d{2}[-/\.]\d{2,4})")
        numbers_end_regex = re.compile(
            r"\b([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*(cr|dr)?\s*$", re.IGNORECASE
        )

        self.statement_opening_balance = None
        current_date = None
        narration_buffer = []

        for line in normalized_text.splitlines():
            line_str = line.strip()
            if self._is_metadata_noise(line_str):
                continue

            if "b/f" in line_str.lower() or "brought forward" in line_str.lower():
                bf_match = re.search(
                    r"([\d,]+\.\d{2})\s*(cr|dr)?$", line_str, flags=re.IGNORECASE
                )
                if bf_match:
                    self.statement_opening_balance = decimal.Decimal(
                        bf_match.group(1).replace(",", "")
                    )
                continue

            date_match = date_start_regex.match(line_str)
            if date_match:
                current_date = date_match.group(1)
                line_str = line_str[date_match.end() :].strip()

            num_match = numbers_end_regex.search(line_str)
            if num_match and current_date:
                raw_amount = num_match.group(1).replace(",", "")
                raw_balance = num_match.group(2).replace(",", "")
                raw_direction = (
                    num_match.group(3).lower() if num_match.group(3) else "cr"
                )

                leftover_narration = line_str[: num_match.start()].strip()
                if leftover_narration:
                    narration_buffer.append(leftover_narration)

                full_compiled_narration = " ".join(narration_buffer).strip()

                fused_credit_signature = bool(
                    re.search(
                        r"\bCR[A-Z0-9]{5,}\b", full_compiled_narration, re.IGNORECASE
                    )
                )

                parsed_transaction_items.append(
                    {
                        "date_str": current_date,
                        "raw_narration": full_compiled_narration
                        or "Bank Transaction Entry",
                        "amount_str": raw_amount,
                        "balance_str": raw_balance,
                        "direction": raw_direction,
                        "fused_credit": fused_credit_signature,
                    }
                )

                current_date = None
                narration_buffer = []
            else:
                if current_date and line_str:
                    narration_buffer.append(line_str)

        print(
            f"📋 [SIB ENGINE]: Stream-compiled {len(parsed_transaction_items)} transaction rows completely."
        )
        return parsed_transaction_items

    def _process_transaction_rows1(
        self, parsed_transaction_items, account, bank, existing_identifiers
    ):
        staged_records_preview = []
        total_debit_sum = total_credit_sum = decimal.Decimal("0.00")
        total_dr_count = total_cr_count = duplicate_count = 0
        closing_balance_final = None

        # 1. DETERMINISTIC BALANCE INITIALIZATION (B/F Check)
        if getattr(self, "statement_opening_balance", None) is not None:
            previous_balance = self.statement_opening_balance
            opening_bal = float(self.statement_opening_balance)
            print(
                f"🎯 [SIB ENGINE] Explicit B/F Opening Balance Captured: {opening_bal}"
            )
        elif parsed_transaction_items:
            first_bal = decimal.Decimal(parsed_transaction_items[0]["balance_str"])
            first_amt = decimal.Decimal(parsed_transaction_items[0]["amount_str"])

            # Reconstruct the exact opening balance based on statement metadata trends
            if len(parsed_transaction_items) > 1:
                second_bal = decimal.Decimal(parsed_transaction_items[1]["balance_str"])
                if first_bal >= second_bal:
                    previous_balance = first_bal + first_amt
                else:
                    previous_balance = first_bal - first_amt
            else:
                previous_balance = first_bal + first_amt

            opening_bal = float(previous_balance)
            print(
                f"⚖️ [SIB RECONSTRUCTION] Reconstructed base opening balance anchor: {opening_bal}"
            )
        else:
            previous_balance = None
            opening_bal = 0.00

        for index, item in enumerate(parsed_transaction_items):
            try:
                raw_date_str = item["date_str"]
                raw_narration = item["raw_narration"]
                raw_amount_str = item["amount_str"]
                raw_balance_str = item["balance_str"]

                tx_date = datetime.date.today()
                # Added %y and %y patterns to capture 2-digit year values cleanly
                for fmt in (
                    "%d-%m-%Y",
                    "%d/%m/%Y",
                    "%Y-%m-%d",
                    "%d %b %Y",
                    "%d-%m-%y",
                    "%d/%m/%y",
                ):
                    try:
                        tx_date = datetime.datetime.strptime(raw_date_str, fmt).date()
                        break
                    except ValueError:
                        continue

                current_running_balance = decimal.Decimal(raw_balance_str)
                current_txn_val = decimal.Decimal(raw_amount_str)

                if previous_balance is None:
                    previous_balance = current_running_balance

                # 2. CORE MATHEMATICAL CALCULATION RULES
                if current_running_balance < previous_balance:
                    is_debit_entry = True
                elif current_running_balance > previous_balance:
                    is_debit_entry = False
                else:
                    # Resolve flat balance shifts using transaction text context metrics
                    narr_upper = raw_narration.upper()
                    if (
                        "WITHDRAWAL" in narr_upper
                        or "CHARGES" in narr_upper
                        or "DEBIT" in narr_upper
                    ):
                        is_debit_entry = True
                    elif (
                        "INTEREST PAID" in narr_upper
                        or "INT.PD" in narr_upper
                        or "CREDIT" in narr_upper
                    ):
                        is_debit_entry = False
                    else:
                        is_debit_entry = "dr" in item["direction"].lower()

                if is_debit_entry:
                    amount = -current_txn_val
                    debit_val = float(current_txn_val)
                    credit_val = None
                    total_debit_sum += current_txn_val
                    total_dr_count += 1
                else:
                    amount = current_txn_val
                    debit_val = None
                    credit_val = float(current_txn_val)
                    total_credit_sum += current_txn_val
                    total_cr_count += 1

                previous_balance = current_running_balance
                closing_balance_final = float(current_running_balance)

                clean_narration = (
                    re.sub(r"\s+", " ", raw_narration).strip()
                    or "Bank Transaction Entry"
                )

                cheque_reference_id = None
                ref_match = re.search(
                    r"\b(CHQ|REF|INF|TRA|ID)[:/ ]*([a-zA-Z0-9]+)",
                    clean_narration,
                    re.IGNORECASE,
                )
                if ref_match:
                    cheque_reference_id = ref_match.group(2)

                tokens = clean_narration.split()
                discovered_tran_type = ""
                if tokens:
                    first_word = tokens[0].replace("/", "").strip().upper()
                    if len(first_word) <= 6 or first_word in [
                        "NFT",
                        "UPI",
                        "CHQ",
                        "TFR",
                        "RTGS",
                        "SBINT",
                        "POS",
                        "CHRG",
                        "UPIOUT",
                    ]:
                        discovered_tran_type = first_word

                row_hex = generate_row_fingerprint(
                    bank_id=bank.id,
                    account_id=account.id,
                    narration=clean_narration,
                    cheque_ref=cheque_reference_id,
                    amount=float(amount),
                    running_balance=float(current_running_balance),
                    debit=debit_val,
                    credit=credit_val,
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
                        "description": clean_narration,
                        "tran_type": discovered_tran_type,
                        "amount": float(amount),
                        "debit": debit_val,
                        "credit": credit_val,
                        "balance": float(current_running_balance),
                        "running_balance": float(current_running_balance),
                        "cheque_ref": cheque_reference_id or "",
                        "status": "DUPLICATE" if is_duplicate else "PENDING",
                    }
                )
            except Exception as e:
                print(f"❌ [SIB CALCULATOR ERR AT INDEX {index}] -> {str(e)}")
                continue

        return (
            staged_records_preview,
            opening_bal,
            closing_balance_final,
            float(total_debit_sum),
            float(total_credit_sum),
            total_dr_count,
            total_cr_count,
            duplicate_count,
        )

    def _process_transaction_rows(
        self, parsed_transaction_items, account, bank, existing_identifiers
    ):
        staged_records_preview = []
        total_debit_sum = total_credit_sum = decimal.Decimal("0.00")
        total_dr_count = total_cr_count = duplicate_count = 0
        closing_balance_final = None

        # 1. 🟢 ADVANCED MULTI-ROW LOOKAHEAD INITIALIZATION
        if getattr(self, "statement_opening_balance", None) is not None:
            previous_balance = self.statement_opening_balance
            opening_bal = float(self.statement_opening_balance)
            print(
                f"🎯 [SIB ENGINE] Explicit B/F Opening Balance Captured: {opening_bal}"
            )
        elif parsed_transaction_items:
            first_bal = decimal.Decimal(parsed_transaction_items[0]["balance_str"])
            first_amt = decimal.Decimal(parsed_transaction_items[0]["amount_str"])

            # Find the first row where the balance actually changes to determine layout trend
            trend_direction_debit = True
            for item in parsed_transaction_items:
                next_bal = decimal.Decimal(item["balance_str"])
                if next_bal != first_bal:
                    # If the balance eventually dropped below the first row, we are trending downwards
                    trend_direction_debit = next_bal < first_bal
                    break

            # Reconstruct starting point based on validated historical data trend
            if trend_direction_debit:
                previous_balance = first_bal + first_amt
            else:
                previous_balance = first_bal - first_amt

            opening_bal = float(previous_balance)
            print(
                f"⚖️ [SIB RECONSTRUCTION] Dynamic multi-row initialization set starting anchor to: {opening_bal}"
            )
        else:
            previous_balance = None
            opening_bal = 0.00

        for index, item in enumerate(parsed_transaction_items):
            try:
                raw_date_str = item["date_str"]
                raw_narration = item["raw_narration"]
                raw_amount_str = item["amount_str"]
                raw_balance_str = item["balance_str"]

                tx_date = datetime.date.today()
                for fmt in (
                    "%d-%m-%Y",
                    "%d/%m/%Y",
                    "%Y-%m-%d",
                    "%d %b %Y",
                    "%d-%m-%y",
                    "%d/%m/%y",
                ):
                    try:
                        tx_date = datetime.datetime.strptime(raw_date_str, fmt).date()
                        break
                    except ValueError:
                        continue

                current_running_balance = decimal.Decimal(raw_balance_str)
                current_txn_val = decimal.Decimal(raw_amount_str)

                if previous_balance is None:
                    previous_balance = current_running_balance

                # 2. 🟢 CONTEXT-AWARE DIRECTION MATRIX
                if current_running_balance < previous_balance:
                    is_debit_entry = True
                elif current_running_balance > previous_balance:
                    is_debit_entry = False
                else:
                    # Resolve flat balance shifts using textual transaction identifiers
                    narr_upper = raw_narration.upper()
                    if (
                        "WITHDRAWAL" in narr_upper
                        or "CHARGES" in narr_upper
                        or "DEBIT" in narr_upper
                        or "SHOPPING" in narr_upper
                    ):
                        is_debit_entry = True
                    elif (
                        "INTEREST PAID" in narr_upper
                        or "INT.PD" in narr_upper
                        or "CREDIT" in narr_upper
                        or "NACH_CR" in narr_upper
                    ):
                        is_debit_entry = False
                    else:
                        is_debit_entry = "dr" in item["direction"].lower()

                if is_debit_entry:
                    amount = -current_txn_val
                    debit_val = float(current_txn_val)
                    credit_val = None
                    total_debit_sum += current_txn_val
                    total_dr_count += 1
                else:
                    amount = current_txn_val
                    debit_val = None
                    credit_val = float(current_txn_val)
                    total_credit_sum += current_txn_val
                    total_cr_count += 1

                previous_balance = current_running_balance
                closing_balance_final = float(current_running_balance)

                clean_narration = (
                    re.sub(r"\s+", " ", raw_narration).strip()
                    or "Bank Transaction Entry"
                )

                cheque_reference_id = None
                ref_match = re.search(
                    r"\b(CHQ|REF|INF|TRA|ID)[:/ ]*([a-zA-Z0-9]+)",
                    clean_narration,
                    re.IGNORECASE,
                )
                if ref_match:
                    cheque_reference_id = ref_match.group(2)

                tokens = clean_narration.split()
                discovered_tran_type = ""
                if tokens:
                    first_word = tokens[0].replace("/", "").strip().upper()
                    if len(first_word) <= 6 or first_word in [
                        "NFT",
                        "UPI",
                        "CHQ",
                        "TFR",
                        "RTGS",
                        "SBINT",
                        "POS",
                        "CHRG",
                        "UPIOUT",
                    ]:
                        discovered_tran_type = first_word

                row_hex = generate_row_fingerprint(
                    bank_id=bank.id,
                    account_id=account.id,
                    narration=clean_narration,
                    cheque_ref=cheque_reference_id,
                    amount=float(amount),
                    running_balance=float(current_running_balance),
                    debit=debit_val,
                    credit=credit_val,
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
                        "description": clean_narration,
                        "tran_type": discovered_tran_type,
                        "amount": float(amount),
                        "debit": debit_val,
                        "credit": credit_val,
                        "balance": float(current_running_balance),
                        "running_balance": float(current_running_balance),
                        "cheque_ref": cheque_reference_id or "",
                        "status": "DUPLICATE" if is_duplicate else "PENDING",
                    }
                )
            except Exception as e:
                print(f"❌ [SIB CALCULATOR ERR AT INDEX {index}] -> {str(e)}")
                continue

        return (
            staged_records_preview,
            opening_bal,
            closing_balance_final,
            float(total_debit_sum),
            float(total_credit_sum),
            total_dr_count,
            total_cr_count,
            duplicate_count,
        )

    def execute_sib_parse_pipeline(self, request):
        uploaded_file = request.FILES.get("statement_file")
        account_id = request.data.get("account_id")

        if not uploaded_file or not account_id:
            return Response(
                {"message": "Required parameters missing."},
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

        try:
            self.statement_opening_balance = None
            raw_text_stream, was_encrypted = self._extract_raw_text(
                uploaded_file, filename, password_pool, account.name
            )
            report_from_date = report_to_date = None

            period_match = re.search(
                r"PERIOD\s+FROM\s+(\d{2}[-/\.]\d{2}[-/\.]\d{2,4})\s+to\s+(\d{2}[-/\.]\d{2}[-/\.]\d{2,4})",
                raw_text_stream,
                flags=re.IGNORECASE,
            )
            if period_match:
                for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y"):
                    try:
                        report_from_date = datetime.datetime.strptime(
                            period_match.group(1), fmt
                        ).date()
                        report_to_date = datetime.datetime.strptime(
                            period_match.group(2), fmt
                        ).date()
                        break
                    except ValueError:
                        continue

            parsed_transaction_items = self._detect_and_parse_layout(
                raw_text_stream, account
            )
            existing_identifiers = set(
                StatementStagingLine.objects.filter(account_id=account.id).values_list(
                    "row_identifier", flat=True
                )
            )

            (
                staged_records_preview,
                op_bal,
                cl_bal,
                deb_sum,
                cred_sum,
                dr_count,
                cr_count,
                duplicate_count,
            ) = self._process_transaction_rows(
                parsed_transaction_items, account, bank, existing_identifiers
            )

            if not report_from_date and staged_records_preview:
                try:
                    extracted_dates = sorted(
                        [
                            datetime.date.fromisoformat(item["date"])
                            for item in staged_records_preview
                        ]
                    )
                    report_from_date = extracted_dates[0]
                    report_to_date = extracted_dates[-1]
                except:
                    pass

            return Response(
                {
                    "status": "SUCCESS",
                    "file_type": "PDF" if filename.endswith(".pdf") else "CSV",
                    "decrypted": was_encrypted,
                    "report_from_date": (
                        report_from_date.isoformat() if report_from_date else None
                    ),
                    "report_to_date": (
                        report_to_date.isoformat() if report_to_date else None
                    ),
                    "opening_balance": round(op_bal or 0.00, 2),
                    "closing_balance": round(cl_bal or 0.00, 2),
                    "total_debit": round(deb_sum, 2),
                    "total_credit": round(cred_sum, 2),
                    "debit_line_count": dr_count,
                    "credit_line_count": cr_count,
                    "duplicate_count": duplicate_count,
                    "raw_match_count": len(staged_records_preview),
                    "count": len(staged_records_preview),
                    "preview_dataset": staged_records_preview,
                },
                status=status.HTTP_200_OK,
            )
        except (PermissionError, LookupError) as auth_err:
            return Response(
                {"status": "ERROR", "message": str(auth_err)},
                status=status.HTTP_403_FORBIDDEN,
            )
        except Exception as e:
            traceback.print_exc()
            return Response(
                {
                    "status": "ERROR",
                    "message": f"SIB Ingestion breakdown failure: {str(e)}",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


def process_SIB_pdf_statement(request):
    engine = SIBEngineParser()
    return engine.execute_sib_parse_pipeline(request)
