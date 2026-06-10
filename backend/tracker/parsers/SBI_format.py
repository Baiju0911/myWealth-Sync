# tracker/parsers/sbi_format.py
import io
import re
import csv
import decimal
import datetime
from pypdf import PdfReader
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .utils import MatchWrapper, generate_row_fingerprint

from tracker.models import (
    Account,
    StatementStagingLine,
    BankCredential,
    BankLayoutSchema,
)


class SBIEngineParser:
    """
    🚀 COUPLING CAPSULE CLASS:
    Binds all your multi-page string regex logic steps together safely
    without leaking structural view routes into memory profiles.
    """

    def _is_header_row(self, row_text):
        if not row_text:
            return True
        metadata_garbage = [
            "drawing power",
            "account open date",
            "interest rate",
            "branch code",
            "branch email",
            "statement from",
            "cleared balance",
            "uncleared amount",
            "operated by a letter",
            "extra care",
            "last transaction date",
        ]
        if any(garbage in row_text for garbage in metadata_garbage):
            return True

        row_text_lower = row_text.lower()
        if "summary" in row_text_lower and (
            "page" in row_text_lower or "statement" in row_text_lower
        ):
            return True
        if "total debit" in row_text_lower and (
            "closing" in row_text_lower or "balance" in row_text_lower
        ):
            return True
        if "total credit" in row_text_lower and (
            "closing" in row_text_lower or "balance" in row_text_lower
        ):
            return True
        return False

    def _extract_raw_text(self, uploaded_file, filename, password_pool, account_name):
        was_encrypted = False
        raw_text_stream = ""

        if filename.endswith(".pdf"):
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
                                "🔓 [VAULT UNLOCKED] Clean match found using password variant indicator."
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
            file_stream = io.StringIO(
                uploaded_file.read().decode("utf-8"), newline=None
            )
            csv_reader = csv.reader(file_stream)
            csv_lines = [" ".join(row) for row in csv_reader if row]
            raw_text_stream = "\n".join(csv_lines)

        return raw_text_stream, was_encrypted

    def _detect_and_parse_layout(self, normalized_text):
        transaction_matches = []
        is_compressed_layout = bool(
            re.search(
                r"\.\d{2}\d{2}\s+[A-Z]{3}\s+\d{4}", normalized_text, re.IGNORECASE
            )
            or "@" in normalized_text
        )

        if not is_compressed_layout:
            print("📋 [LAYOUT ROUTER] -> Standard Spaced Variant (Pass A Engine)")
            master_tx_pattern = re.compile(
                r"(\d{2}[-/\.]\d{2}[-/\.]\d{2,4})\s+(\d{2}[-/\.]\d{2}[-/\.]\d{2,4})\s+(.*?)([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*(cr|dr)?",
                re.IGNORECASE,
            )
            transaction_matches = list(master_tx_pattern.finditer(normalized_text))
            return transaction_matches, is_compressed_layout

        print(
            "📋 [LAYOUT ROUTER] -> Tokenized Number-Stream Array Lock (Pass B Engine)"
        )
        raw_chunks = re.split(
            r"(?=\d{2}\s+[A-Z]{3}\s+\d{4})|(?=\d{2}-\d{2}-\d{4})",
            normalized_text,
            flags=re.IGNORECASE,
        )

        for chunk in raw_chunks:
            if not chunk.strip():
                continue
            chunk_slice = re.search(
                r"([\d,]+\.\d{2}\s*(?:CR|DR))\s+(?:Page\s+no|Brought\s+Forward|Statement\s+Summary|CLOSING\s+BALANCE|Dr\s+Count|Total\s+Debits)",
                chunk,
                re.IGNORECASE,
            )
            if chunk_slice:
                chunk = chunk[: chunk_slice.end(1)].strip()

            all_decimals = re.findall(r"[\d,]+\.\d{2}", chunk)
            if len(all_decimals) < 2:
                continue

            raw_bal = all_decimals[-1].replace(",", "").strip()
            clean_amt_str = all_decimals[-2].replace(",", "").strip()

            check_amt = re.sub(r"[^\d\.]", "", clean_amt_str)
            check_bal = re.sub(r"[^\d\.]", "", raw_bal)
            if not check_amt or not check_bal:
                continue

            raw_narr = chunk.split(all_decimals[-2])[0].strip()
            raw_narr = re.sub(
                r"^\d{2}\s+[A-Z]{3}\s+\d{4}\s+", "", raw_narr, flags=re.IGNORECASE
            )
            raw_narr = re.sub(
                r"^\d{2}-\d{2}-\d{4}\s+", "", raw_narr, flags=re.IGNORECASE
            )
            raw_narr = raw_narr.replace("|", "").strip()

            if clean_amt_str == raw_bal and any(
                term in raw_narr.lower()
                for term in ["closing", "summary", "total balance"]
            ):
                continue

            narr_lower = raw_narr.lower()
            is_reversal = any(
                term in narr_lower for term in ["reverse", "refund", "rev tfr"]
            )
            is_debit = bool(
                re.search(
                    r"\b(transfer to|debit|withdrawal|fee|chrg|pos|wdl|tax|dr|purchase)\b",
                    narr_lower,
                )
            )
            is_credit = bool(
                re.search(
                    r"\b(credit|interest|transfer from|rtgs|neft|unf|imps|prov|cr)\b",
                    narr_lower,
                )
            )

            if is_reversal:
                direction_flag = "cr"
            elif is_debit:
                direction_flag = "dr"
            elif is_credit:
                direction_flag = "cr"
            else:
                direction_flag = (
                    "dr"
                    if (narr_lower.startswith("wdl") or narr_lower.startswith("dr"))
                    else "cr"
                )

            dummy_date_str = "01 JAN 2026"
            date_match = re.search(
                r"(\d{2}\s+[A-Z]{3}\s+\d{4})|(\d{2}-\d{2}-\d{4})", chunk
            )
            if date_match:
                dummy_date_str = date_match.group(0)

            transaction_matches.append(
                MatchWrapper(
                    dummy_date_str, raw_narr, clean_amt_str, raw_bal, direction_flag
                )
            )

        return transaction_matches, is_compressed_layout

    def _process_transaction_rows(
        self,
        transaction_matches,
        is_compressed_layout,
        account,
        bank,
        debit_aliases,
        opening_bal,
        existing_identifiers,
    ):
        staged_records_preview = []
        total_debit_sum = total_credit_sum = 0.00
        total_dr_count = total_cr_count = duplicate_count = 0
        previous_balance = closing_balance_final = None

        print("\n" + "=" * 80)
        print("📊 STARTING DETAILED LINE-BY-LINE RUNNING TOTAL SIDE-BY-SIDE AUDIT")
        print("=" * 80)

        for index, match in enumerate(transaction_matches):
            raw_date_str = match.group(1).strip()
            raw_narration = match.group(3).strip()
            raw_amount_str = match.group(4).replace(",", "").strip()
            raw_balance_str = match.group(5).replace(",", "").strip()
            raw_direction = match.group(6).lower().strip() if match.group(6) else ""

            if self._is_header_row(raw_narration.lower()):
                continue

            raw_narration = re.sub(
                r"page\s+no\.\s*\d+", "", raw_narration, flags=re.IGNORECASE
            )
            raw_narration = re.sub(
                r"post\s+date\s+value\s+date\s+description.* balance",
                "",
                raw_narration,
                flags=re.IGNORECASE,
            )
            raw_narration = re.sub(
                r"brought\s+forward", "", raw_narration, flags=re.IGNORECASE
            ).strip()

            tx_date = datetime.date.today()
            for fmt in (
                " %d %b %Y",
                "%d %b %Y",
                "%d-%m-%Y",
                "%d/%m/%Y",
                "%Y-%m-%d",
                "%d-%b-%Y",
                "%d-%b-%y",
            ):
                try:
                    tx_date = datetime.datetime.strptime(
                        raw_date_str.strip(), fmt
                    ).date()
                    break
                except ValueError:
                    continue

            try:
                clean_amt_digits = re.sub(r"[^\d\.]", "", raw_amount_str)
                clean_bal_digits = re.sub(r"[^\d\.]", "", raw_balance_str)
                if not clean_amt_digits or not clean_bal_digits:
                    continue

                current_txn_val = decimal.Decimal(clean_amt_digits)
                current_running_balance = decimal.Decimal(clean_bal_digits)

                if current_txn_val <= decimal.Decimal("0.01"):
                    continue

                if previous_balance is None:
                    if index <= 2 and opening_bal is not None:
                        previous_balance = decimal.Decimal(str(opening_bal))
                    else:
                        temp_is_debit = raw_direction == "dr" or any(
                            m in raw_narration.lower()
                            for m in debit_aliases + ["wdl", "withdrawal", "debit"]
                        )
                        previous_balance = (
                            (current_running_balance + current_txn_val)
                            if temp_is_debit
                            else (current_running_balance - current_txn_val)
                        )

                if current_running_balance < previous_balance:
                    is_debit_entry = True
                elif current_running_balance > previous_balance:
                    is_debit_entry = False
                else:
                    is_debit_entry = raw_direction == "dr" or any(
                        m in raw_narration.lower()
                        for m in debit_aliases + ["wdl", "withdrawal", "debit"]
                    )

                if opening_bal is None:
                    opening_bal = float(previous_balance)

                expected_balance = (
                    (previous_balance - current_txn_val)
                    if is_debit_entry
                    else (previous_balance + current_txn_val)
                )

                if expected_balance != current_running_balance:
                    expected_str, printed_str = (
                        f"{expected_balance:.2f}",
                        f"{current_running_balance:.2f}",
                    )
                    if (
                        current_running_balance == decimal.Decimal("0.00")
                        or current_running_balance is None
                    ):
                        current_running_balance = expected_balance
                    elif printed_str.endswith(expected_str) or printed_str.replace(
                        ".", ""
                    ).endswith(expected_str.replace(".", "")):
                        current_running_balance = expected_balance

                previous_balance = current_running_balance
                closing_balance_final = float(current_running_balance)

                if is_debit_entry:
                    amount, debit_val, credit_val = (
                        -current_txn_val,
                        float(current_txn_val),
                        None,
                    )
                    total_debit_sum += float(current_txn_val)
                    total_dr_count += 1
                else:
                    amount, debit_val, credit_val = (
                        current_txn_val,
                        None,
                        float(current_txn_val),
                    )
                    total_credit_sum += float(current_txn_val)
                    total_cr_count += 1

                clean_narration = (
                    re.sub(r"\s+", " ", raw_narration).strip()
                    or "Online Bank Transfer Entry"
                )

                cheque_reference_id = None
                ref_match = re.search(
                    r"\b(?:CHQ|REF|INF|TRA|ID)[:/ ]*([a-zA-Z0-9]+)",
                    clean_narration,
                    re.IGNORECASE,
                )
                if ref_match:
                    cheque_reference_id = ref_match.group(1)

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

                # 🚀 PASS EXPLICIT UNMUTATED DATA FIELDS TO REMOVE COUPLING DRIFT
                row_hex = generate_row_fingerprint(
                    bank_id=bank.id,
                    account_id=account.id,
                    narration=clean_narration,
                    cheque_ref=cheque_reference_id,
                    amount=amount,
                    running_balance=current_running_balance,
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
                        "balance": float(current_running_balance),  # 🟢 Fixed
                        "running_balance": float(current_running_balance),  # 🟢 Fixed
                        "cheque_ref": (
                            cheque_reference_id if cheque_reference_id else ""
                        ),
                        "status": "DUPLICATE" if is_duplicate else "PENDING",
                    }
                )
            except Exception as num_err:
                print(f"❌ [CALCULATOR BREAKDOWN] -> {str(num_err)}")
                continue

        return (
            staged_records_preview,
            opening_bal,
            closing_balance_final,
            total_debit_sum,
            total_credit_sum,
            total_dr_count,
            total_cr_count,
            duplicate_count,
        )

    def execute_sbi_parse_pipeline(self, request):
        uploaded_file = request.FILES.get("statement_file")
        account_id = request.data.get("account_id")

        if not uploaded_file or not account_id:
            return Response(
                {"message": "Required parameters missing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        account = get_object_or_404(Account, id=account_id)
        bank = account.bank

        credential = BankCredential.objects.filter(account=account).first()
        password_pool = (
            credential.password_vault
            if credential and isinstance(credential.password_vault, list)
            else []
        )

        debit_aliases = ["debit", "withdrawal", "dr"]
        schema = BankLayoutSchema.objects.filter(name="SBI_GENERIC").first()
        if schema and hasattr(schema, "debit_aliases") and schema.debit_aliases:
            debit_aliases = [t.strip().lower() for t in schema.debit_aliases.split(",")]

        filename = uploaded_file.name.lower()

        try:
            raw_text_stream, was_encrypted = self._extract_raw_text(
                uploaded_file, filename, password_pool, account.name
            )
            report_from_date = report_to_date = None

            sbi_period_match = re.search(
                r"FROM\s+(\d{2}[-/\.]\d{2}[-/\.]\d{2,4})\s+TO\s+(\d{2}[-/\.]\d{2}[-/\.]\d{2,4})",
                raw_text_stream,
                flags=re.IGNORECASE,
            )
            if sbi_period_match:
                for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
                    try:
                        report_from_date = datetime.datetime.strptime(
                            sbi_period_match.group(1), fmt
                        ).date()
                        report_to_date = datetime.datetime.strptime(
                            sbi_period_match.group(2), fmt
                        ).date()
                        break
                    except ValueError:
                        continue

            repaired_text = re.sub(
                r"(@)\s*\n\s*([\d,]+\.\d{2})",
                r"\1 \2",
                raw_text_stream,
                flags=re.IGNORECASE,
            )
            repaired_text = re.sub(
                r"(\bUSD\s+\d+)\s*\n\s*(@)",
                r"\1 \2",
                repaired_text,
                flags=re.IGNORECASE,
            )
            repaired_text = re.sub(
                r"(\bWDL\s+TFR|\bDEP\s+TFR|\bDEBIT|\bCREDIT)\s*\n\s*",
                r"\1 ",
                repaired_text,
                flags=re.IGNORECASE,
            )
            repaired_text = re.sub(
                r"(\bSBILT\d+-?)\s*\n\s*([\d,]+\.\d{2})",
                r"\1 \2",
                repaired_text,
                flags=re.IGNORECASE,
            )

            right_margin_regex = re.compile(
                r"^(.*?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2}(?:\s*CR|\s*DR)?)\s*$",
                re.IGNORECASE,
            )

            delimited_lines = []
            for line in repaired_text.splitlines():
                if not line.strip():
                    continue
                slice_match = re.search(
                    r"([\d,]+\.\d{2}\s*(?:CR|DR))\s+(?:Statement\s+Summary|Page\s+no|Brought\s+Forward|CLOSING\s+BALANCE|In\s+Case|Dr\s+Count|Total\s+Debits|Total\s+Credits|\*---)",
                    line,
                    re.IGNORECASE,
                )
                if slice_match:
                    line = line[: slice_match.end(1)].strip()

                match = right_margin_regex.match(line)
                if match:
                    line = f"{match.group(1).strip()} | {match.group(2).strip()} | {match.group(3).strip()}"
                delimited_lines.append(line)

            repaired_text = "\n".join(delimited_lines)
            normalized_document_text = re.sub(r"\s+", " ", repaired_text)
            normalized_document_text = re.sub(
                r"(@\s*[\d,]+\.\d{2})\s+(?=[\d,]+\.\d{2}\s+[\d,]+\.\d{2})",
                r"\1 ",
                normalized_document_text,
            )

            opening_balance_final = None
            bf_match = re.search(
                r"(?:brought\s+forward|opening\s+balance|b/f|bal\s+bf)\s*[:\-]?\s*([\d,]+\.\d{2})",
                normalized_document_text,
                re.IGNORECASE,
            )
            if bf_match:
                opening_balance_final = float(bf_match.group(1).replace(",", ""))

            transaction_matches, is_compressed_layout = self._detect_and_parse_layout(
                normalized_document_text
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
                transaction_matches,
                is_compressed_layout,
                account,
                bank,
                debit_aliases,
                opening_balance_final,
                existing_identifiers,
            )

            if not report_from_date and staged_records_preview:
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
            return Response(
                {
                    "status": "ERROR",
                    "message": f"Ingestion breakdown failure: {str(e)}",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


def process_SBI_pdf_statement(request):
    engine = SBIEngineParser()
    return engine.execute_sbi_parse_pipeline(request)
