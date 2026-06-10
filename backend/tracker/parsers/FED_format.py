import io
import re
import decimal
import datetime
import traceback
from pypdf import PdfReader
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from tracker.models import Account, StatementStagingLine, BankCredential
from .utils import generate_row_fingerprint


class FEDEngineParser:
    """
    🔵 FEDERAL BANK (FED) PRODUCTION ENGINE:
    Completely decoupled dual-pipeline parsing architecture.
    The Legacy Flat layout and New Multiline layout execute in isolated data paths
    to ensure 0% cross-contamination and 100% mathematical precision.
    """

    def _is_metadata_noise(self, row_text):
        if not row_text or not row_text.strip():
            return True
        row_text_lower = row_text.lower().strip()
        noise_indicators = [
            "statement of account",
            "date value date particulars chq",
            "date particulars tran",
            "cheque details withdrawals",
            "deposits cr/dr",
            "withdrawals deposits",
            "balancetran id",
            "page total",
            "grand total",
            "system-generated statement",
            "page no",
            "visit us at",
            "customer id:",
            "ckyc no:",
            "a/c no:",
            "mode of opr:",
            "communication address",
            "regd. mobile number",
            "type of account",
            "scheme :",
            "swift code",
            "ifsc",
            "date of issue",
            "customer id",
            "branch name",
            "currency inr",
            "nomination",
            "effective available",
            "address last updated",
            "micr code",
            "account open date",
            "email id",
            "branch sol id",
            "account status",
            "page 1 of",
            "page 2 of",
            "page 3 of",
            "abbreviations used:",
            "cash    : cash",
            "ft      : fund transfer",
            "sbint   :",
            "tdint   :",
            "disclaimer:",
            "this is a computer generated",
            "statement date.",
            "**** end of statement ****",
            "grand total",
            "page 10 of",
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
                    raise PermissionError(f"PDF encrypted for {account_name}.")
                decryption_successful = False
                for pwd in password_pool:
                    try:
                        if reader.decrypt(str(pwd).strip()):
                            decryption_successful = True
                            break
                    except:
                        continue
                if not decryption_successful:
                    raise LookupError("Vault passwords rejected.")
            raw_text_stream = "\n".join(
                [p.extract_text() for p in reader.pages if p.extract_text()]
            )
        return raw_text_stream, was_encrypted

    def _detect_and_parse_layout(self, raw_text, account_profile):
        """
        🔀 LAYOUT ROUTER DISPATCHER
        Uses the strict layout header maps provided to route statements perfectly.
        Old format uses 'Cr/Dr' in header columns; New layout maps 'Deposits Balance'.
        """
        # Clean whitespaces slightly to capture variant multiline wrapping safely
        normalized_text = " ".join(raw_text.split())

        if re.search(r"Deposits\s+Cr/Dr", normalized_text, re.IGNORECASE) or re.search(
            r"Particulars\s+Tran\s+Type.*Cr/Dr", normalized_text, re.IGNORECASE
        ):
            print("📋 [ROUTER] -> Detected: LEGACY Flat FED Format Layout")
            return "LEGACY_FLAT"

        if (
            re.search(r"Deposits\s+Balance", normalized_text, re.IGNORECASE)
            or re.search(
                r"Particulars\s+Tran\s+Type.*Balance", normalized_text, re.IGNORECASE
            )
            or re.search(r"\b[CD]\s+\d+\s+[\d.]+$", raw_text, re.MULTILINE)
        ):
            print("📋 [ROUTER] -> Detected: NEW Multiline FED Format Layout")
            return "NEW_MULTILINE"

        # Safe structural fallback to legacy engine path
        print("📋 [ROUTER] -> Fallback Default: LEGACY Flat FED Format Layout")
        return "LEGACY_FLAT"

    # =========================================================================
    # 🔥 PIPELINE PATH A: NEW MULTILINE ENGINE (Isolated Logic & Processing)
    # =========================================================================

    def _process_new_multiline_pipeline(
        self, raw_text, account, bank, existing_identifiers
    ):
        """
        Stream parses the new layout page-by-page and executes its dedicated math.
        """
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

        def format_fed_date(date_str):
            for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y"):
                try:
                    return datetime.datetime.strptime(date_str, fmt).strftime(
                        "%d/%m/%Y"
                    )
                except ValueError:
                    continue
            return datetime.date.today().strftime("%d/%m/%Y")

        parsed_items = []
        current_date = None
        narration_buffer = []

        # Step 1: Stream and extract narrative tokens and data pivots
        for line in lines:
            if self._is_metadata_noise(line):
                continue

            date_match = re.match(r"^(\d{2}-[A-Z]{3}-\d{4})", line, re.IGNORECASE)
            if date_match:
                current_date = format_fed_date(date_match.group(1))
                narration_buffer = []
                continue

            pivot_match = re.search(
                r"\b([CD])\s+([0-9,.]+)\s+([0-9,.]+)$", line, re.IGNORECASE
            )
            if pivot_match and current_date:
                direction_flag = "cr" if pivot_match.group(1).upper() == "C" else "dr"
                fused_narration_part = line[: pivot_match.start()].strip()
                if fused_narration_part:
                    narration_buffer.append(fused_narration_part)

                parsed_items.append(
                    {
                        "date_str": current_date,
                        "raw_narration": " ".join(narration_buffer).strip()
                        or "Bank Transaction Entry",
                        "amount_str": pivot_match.group(2).replace(",", ""),
                        "balance_str": pivot_match.group(3).replace(",", ""),
                        "direction": direction_flag,
                    }
                )
                narration_buffer = []
                continue

            if not re.match(r"^\d{2}:\d{2}:\d{2}", line):
                narration_buffer.append(line)

        print(
            f"📋 [NEW ENGINE]: Isolated and stream-parsed {len(parsed_items)} multiline records."
        )

        # Step 2: Run dedicated calculation loop using New Format boundary math
        staged_records_preview = []
        total_debit_sum = total_credit_sum = decimal.Decimal("0.00")
        total_dr_count = total_cr_count = duplicate_count = 0
        closing_balance_final = None

        if parsed_items:
            first_row_bal = decimal.Decimal(parsed_items[0]["balance_str"])
            first_row_amt = decimal.Decimal(parsed_items[0]["amount_str"])
            first_row_dir = parsed_items[0]["direction"].lower()

            if "dr" in first_row_dir:
                previous_balance = first_row_bal + first_row_amt
            else:
                previous_balance = first_row_bal - first_row_amt
            opening_bal = float(previous_balance)
        else:
            previous_balance = decimal.Decimal("0.00")
            opening_bal = 0.00

        for index, item in enumerate(parsed_items):
            try:
                tx_date = datetime.date.today()
                for fmt in ("%d-%m-%Y", "%d/%m/%Y"):
                    try:
                        tx_date = datetime.datetime.strptime(
                            item["date_str"], fmt
                        ).date()
                        break
                    except ValueError:
                        continue

                current_balance = decimal.Decimal(item["balance_str"])
                raw_txn_amount = decimal.Decimal(item["amount_str"])

                is_debit = "dr" in item["direction"]
                derived_txn_val = raw_txn_amount

                if is_debit:
                    amount = -derived_txn_val
                    debit_val = float(derived_txn_val)
                    credit_val = None
                    total_debit_sum += derived_txn_val
                    total_dr_count += 1
                else:
                    amount = derived_txn_val
                    debit_val = None
                    credit_val = float(derived_txn_val)
                    total_credit_sum += derived_txn_val
                    total_cr_count += 1

                previous_balance = current_balance
                closing_balance_final = float(current_balance)

                clean_narration = item["raw_narration"]
                clean_narration = re.sub(
                    r"TRF\s*\d{2}[-/\.]\d{2}[-/\.]\d{2,4}\s*$",
                    "",
                    clean_narration,
                    flags=re.IGNORECASE,
                ).strip()
                clean_narration = re.sub(
                    r"^\d{2}[-/\.]\d{2}[-/\.]\d{2,4}\s*", "", clean_narration
                ).strip()

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
                        tokens = tokens[1:]
                clean_narration = " ".join(tokens).strip() or "Bank Transaction Entry"

                cheque_reference_id = None
                ref_match = re.search(
                    r"\b(?:CHQ|REF|ID|FT|TXN)[:/ ]*([a-zA-Z0-9]+)",
                    clean_narration,
                    re.IGNORECASE,
                )
                if ref_match:
                    cheque_reference_id = ref_match.group(1)

                row_hex = generate_row_fingerprint(
                    bank_id=bank.id,
                    account_id=account.id,
                    narration=clean_narration,
                    cheque_ref=cheque_reference_id,
                    amount=float(amount),
                    running_balance=float(current_balance),
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
                        "balance": float(current_balance),
                        "running_balance": float(current_balance),
                        "bank_transaction_id": cheque_reference_id or "",
                        "cheque_ref": cheque_reference_id or "",
                        "status": "DUPLICATE" if is_duplicate else "PENDING",
                        "Hex": row_hex,
                    }
                )
            except:
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

    # =========================================================================
    # 🗜️ PIPELINE PATH B: LEGACY FLAT ENGINE (Isolated Logic & Processing)
    # =========================================================================

    def _process_legacy_pipeline(self, raw_text, account, bank, existing_identifiers):
        """
        Your original legacy parsing logic complete with direct text normalization
        and explicit opening balance string extraction tracking profiles.
        """
        cleaned_text = re.sub(
            r"\b(CR|DR)([A-Z0-9]+)\b", r"\1 \2", raw_text, flags=re.IGNORECASE
        )

        parsed_transaction_items = []
        date_finder_regex = re.compile(r"(\d{2}[-/\.]\d{2}[-/\.]\d{2,4})")
        numbers_end_regex = re.compile(
            r"(\d+\.\d{2})\s+(\d+\.\d{2})\s*(cr|dr)\b", flags=re.IGNORECASE
        )

        statement_opening_balance = None
        running_timeline_date = "01-01-2022"

        for line in cleaned_text.splitlines():
            line_str = line.strip()
            if self._is_metadata_noise(line_str):
                continue

            if "opening balance" in line_str.lower():
                op_match = re.search(r"(\d+\.\d{2})", line_str)
                if op_match:
                    statement_opening_balance = decimal.Decimal(op_match.group(1))
                continue

            num_match = numbers_end_regex.search(line_str)
            if num_match:
                raw_amount = num_match.group(1).strip()
                raw_balance = num_match.group(2).strip()
                raw_direction = num_match.group(3).lower().strip()

                text_left = line_str[: num_match.start()].strip()
                date_matches = date_finder_regex.findall(text_left)
                if date_matches:
                    running_timeline_date = date_matches[0]
                    clean_narration = date_finder_regex.sub("", text_left).strip()
                else:
                    clean_narration = text_left

                parsed_transaction_items.append(
                    {
                        "date_str": running_timeline_date,
                        "raw_narration": (
                            clean_narration
                            if clean_narration
                            else "Bank Transaction Entry"
                        ),
                        "amount_str": raw_amount,
                        "balance_str": raw_balance,
                        "direction": raw_direction,
                    }
                )

        print(
            f"📋 [LEGACY ENGINE]: Isolated and flat-parsed {len(parsed_transaction_items)} historical rows."
        )

        staged_records_preview = []
        total_debit_sum = total_credit_sum = decimal.Decimal("0.00")
        total_dr_count = total_cr_count = duplicate_count = 0

        if statement_opening_balance is not None:
            previous_balance = statement_opening_balance
            opening_bal = float(statement_opening_balance)
        else:
            previous_balance = None
            opening_bal = 0.00

        closing_balance_final = None

        for index, item in enumerate(parsed_transaction_items):
            try:
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
                        tx_date = datetime.datetime.strptime(
                            item["date_str"], fmt
                        ).date()
                        break
                    except ValueError:
                        continue

                current_balance = decimal.Decimal(item["balance_str"])
                raw_txn_amount = decimal.Decimal(item["amount_str"])
                raw_direction = item["direction"]

                if previous_balance is None:
                    if "dr" in raw_direction:
                        previous_balance = current_balance + raw_txn_amount
                    else:
                        previous_balance = current_balance - raw_txn_amount
                    opening_bal = float(previous_balance)

                if current_balance < previous_balance:
                    is_debit = True
                    derived_txn_val = previous_balance - current_balance
                elif current_balance > previous_balance:
                    is_debit = False
                    derived_txn_val = current_balance - previous_balance
                else:
                    is_debit = "dr" in raw_direction
                    derived_txn_val = raw_txn_amount

                if is_debit:
                    amount = -derived_txn_val
                    debit_val = float(derived_txn_val)
                    credit_val = None
                    total_debit_sum += derived_txn_val
                    total_dr_count += 1
                else:
                    amount = derived_txn_val
                    debit_val = None
                    credit_val = float(derived_txn_val)
                    total_credit_sum += derived_txn_val
                    total_cr_count += 1

                previous_balance = current_balance
                closing_balance_final = float(current_balance)

                raw_narration = item["raw_narration"]
                raw_narration = re.sub(
                    r"TRF\s*\d{2}[-/\.]\d{2}[-/\.]\d{2,4}\s*$",
                    "",
                    raw_narration,
                    flags=re.IGNORECASE,
                ).strip()
                raw_narration = re.sub(
                    r"^\d{2}[-/\.]\d{2}[-/\.]\d{2,4}\s*", "", raw_narration
                ).strip()

                tokens = raw_narration.split()
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
                        tokens = tokens[1:]

                clean_narration = " ".join(tokens).strip() or "Bank Transaction Entry"
                cheque_reference_id = None
                ref_match = re.search(
                    r"\b(?:CHQ|REF|ID|FT|TXN)[:/ ]*([a-zA-Z0-9]+)",
                    clean_narration,
                    re.IGNORECASE,
                )
                if ref_match:
                    cheque_reference_id = ref_match.group(1)

                row_hex = generate_row_fingerprint(
                    bank_id=bank.id,
                    account_id=account.id,
                    narration=clean_narration,
                    cheque_ref=cheque_reference_id,
                    amount=float(amount),
                    running_balance=float(current_balance),
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
                        "balance": float(current_balance),
                        "running_balance": float(current_balance),
                        "bank_transaction_id": cheque_reference_id or "",
                        "cheque_ref": cheque_reference_id or "",
                        "status": "DUPLICATE" if is_duplicate else "PENDING",
                        "Hex": row_hex,
                    }
                )
            except:
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

    # =========================================================================
    # 🎛️ CORE EXECUTIVE PIPELINE ENTRANCE LINK
    # =========================================================================

    def execute_FED_parse_pipeline(self, request):
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

        try:
            # Clear internal layout parameter state hooks
            self.statement_opening_balance = None

            raw_text_stream, was_encrypted = self._extract_raw_text(
                uploaded_file, filename, password_pool, account.name
            )
            report_from_date = report_to_date = None

            period_match = re.search(
                r"period\s+(\d{2}[-/\.]\d{2}[-/\.]\d{2,4})\s+to\s+(\d{2}[-/\.]\d{2}[-/\.]\d{2,4})",
                raw_text_stream,
                flags=re.IGNORECASE,
            )
            if period_match:
                for fmt in ("%d-%m-%Y", "%d/%m/%Y"):
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

            existing_identifiers = set(
                StatementStagingLine.objects.filter(
                    account_id=str(account_id).strip()
                ).values_list("row_identifier", flat=True)
            )

            # Execute strict layout variant separation mapping
            layout_variant = self._detect_and_parse_layout(raw_text_stream, account)

            if layout_variant == "NEW_MULTILINE":
                print("🔀 [SWITCHBOARD] -> Executing: NEW MULTILINE ENGINE")
                (
                    staged_records_preview,
                    op_bal,
                    cl_bal,
                    deb_sum,
                    cred_sum,
                    dr_count,
                    cr_count,
                    duplicate_count,
                ) = self._process_new_multiline_pipeline(
                    raw_text_stream, account, bank, existing_identifiers
                )
            else:
                print("🔀 [SWITCHBOARD] -> Executing: LEGACY FLAT ENGINE")
                (
                    staged_records_preview,
                    op_bal,
                    cl_bal,
                    deb_sum,
                    cred_sum,
                    dr_count,
                    cr_count,
                    duplicate_count,
                ) = self._process_legacy_pipeline(
                    raw_text_stream, account, bank, existing_identifiers
                )

            if not report_from_date and staged_records_preview:
                try:
                    extracted_dates = sorted(
                        [
                            datetime.date.fromisoformat(item["date"])
                            for item in staged_records_preview
                        ]
                    )
                    report_from_date, report_to_date = (
                        extracted_dates[0],
                        extracted_dates[-1],
                    )
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

        except Exception as e:
            traceback.print_exc()
            return Response(
                {"status": "ERROR", "message": f"FED Pipeline break: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


def process_FED_pdf_statement(request):
    engine = FEDEngineParser()
    return engine.execute_FED_parse_pipeline(request)
