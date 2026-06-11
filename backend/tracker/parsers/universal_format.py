import json
import os
import re
import datetime
import pdfplumber
from django.shortcuts import get_object_or_404
from django.utils.crypto import get_random_string
from ..models import Account, BankCredential, StatementStagingLine
from .raw_extractor import match_statement_template

# ─── 🟢 INJECTED CRYPTOGRAPHIC UTILITY ROOT HOOK ───
from .utils import generate_row_fingerprint


class UniversalStatementIngestionProcessor:
    """
    Production-grade processing engine parsing 100% of data tokens
    across all pages without row limitations, compiling double-trust ledger summaries.
    """

    def __init__(self, uploaded_file, account_id):
        self.uploaded_file = uploaded_file
        self.account_id = account_id
        self.account = get_object_or_404(Account, id=account_id)

    @staticmethod
    def _is_header_row(row_text: str) -> bool:
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

    @staticmethod
    def _is_metadata_noise(row_text: str) -> bool:
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
            "cash     : cash",
            "ft       : fund transfer",
            "sbint    :",
            "tdint    :",
            "disclaimer:",
            "this is a computer generated",
            "statement date.",
            "**** end of statement ****",
            "page 10 of",
            ".bank.in",
            "br. mail id:",
            # fed below
            "(cid:",
            "trf : transfer transaction",
            "clg : clearing transaction",
            "mb : mobile banking",
            "tds : tax deducted",
            "statement which need not normally be signed",
            "bank ltd. branch:",
            "sasthamanga",
            "federalbank.co.in",
            "cin:l65191kl1931plc000368",
            # SBI addtiona
            "closing balance",
            "dr count",
            "cr count",
            "letter of authority",
            "power of attorney",
            "last transaction date and time appearing",
            "*---end",
        ]
        return any(indicator in row_text_lower for indicator in noise_indicators)

    def execute_full_parse(self):
        routing_match = match_statement_template(self.uploaded_file, self.account_id)

        if routing_match["type"] == "UNKNOWN":
            return {
                "success": False,
                "error_message": "Document layout profile signature missing.",
            }

        raw_bounds = routing_match["bounds"]
        template_model = routing_match["template"]
        verified_password = routing_match.get("unlocked_password", "")

        bounds = {
            "date_max": int(raw_bounds.get("date_max") or 0),
            "value_date_max": int(raw_bounds.get("value_date_max") or 0),
            "particulars_max": int(raw_bounds.get("particulars_max") or 0),
            "trantype_max": int(raw_bounds.get("trantype_max") or 0),
            "cheque_max": int(raw_bounds.get("cheque_max") or 0),
            "withdrawals_max": int(raw_bounds.get("withdrawals_max") or 0),
            "deposits_max": int(raw_bounds.get("deposits_max") or 0),
            "balance_max": int(raw_bounds.get("balance_max") or 0),
            "indicator_max": int(raw_bounds.get("indicator_max") or 100),
        }

        preview_dataset = []
        total_debit = 0.0
        total_credit = 0.0
        debit_line_count = 0
        credit_line_count = 0
        duplicate_count = 0

        pdf_opening_balance = 0.0
        pdf_opening_captured = False

        # Extract parent relation model properties safely to pass down to SSOT hasher
        target_bank_id = self.account.bank_id if hasattr(self.account, "bank_id") else 1

        # ─── 🟢 DYNAMIC LIVE PREVIEW DUPLICATE DETECTOR INDICES ───
        existing_hashes = set(
            StatementStagingLine.objects.filter(account_id=self.account_id).values_list(
                "row_identifier", flat=True
            )
        )

        active_txn = None

        print(
            f"⚙️ [ENGINE TRACKING RUN] Running multi-line memory buffer parse compilation with Hexa Hero..."
        )
        self.uploaded_file.seek(0)

        try:
            with pdfplumber.open(
                self.uploaded_file,
                password=verified_password if verified_password else None,
            ) as pdf:
                for page_idx, page in enumerate(pdf.pages):
                    words = page.extract_words()
                    if not words:
                        continue

                    lines_dict = {}
                    for w in words:
                        top_rounded = round(float(w["top"]), 1)
                        if top_rounded not in lines_dict:
                            lines_dict[top_rounded] = []
                        lines_dict[top_rounded].append(
                            {
                                "text": w["text"],
                                "x_pct": (float(w["x0"]) / float(page.width)) * 100,
                            }
                        )

                    sorted_vertical_keys = sorted(lines_dict.keys())

                    for v_pos in sorted_vertical_keys:
                        row_tokens = sorted(lines_dict[v_pos], key=lambda t: t["x_pct"])

                        # ─── 🟢 STEP 1: INTERCEPT RAW STRING NOISE BEFORE FILLING COLUMNS ───
                        raw_line_text = " ".join(
                            [t["text"] for t in row_tokens]
                        ).strip()

                        if self._is_header_row(
                            raw_line_text
                        ) or self._is_metadata_noise(raw_line_text):
                            continue  # 🛡️ Hard-drop footer strings instantly! Bypasses Case 1 & Case 2 completely.

                        cols = {
                            k: []
                            for k in [
                                "date",
                                "v_date",
                                "part",
                                "type",
                                "chq",
                                "wth",
                                "dep",
                                "bal",
                                "ind",
                            ]
                        }

                        for token in row_tokens:
                            x = token["x_pct"]
                            txt = token["text"].strip()
                            if not txt:
                                continue

                            if bounds["date_max"] > 0 and x <= bounds["date_max"]:
                                cols["date"].append(txt)
                            elif (
                                bounds["value_date_max"] > 0
                                and x <= bounds["value_date_max"]
                            ):
                                cols["v_date"].append(txt)
                            elif (
                                bounds["particulars_max"] > 0
                                and x <= bounds["particulars_max"]
                            ):
                                cols["part"].append(txt)
                            elif (
                                bounds["trantype_max"] > 0
                                and x <= bounds["trantype_max"]
                            ):
                                cols["type"].append(txt)
                            elif bounds["cheque_max"] > 0 and x <= bounds["cheque_max"]:
                                cols["chq"].append(txt)
                            elif (
                                bounds["withdrawals_max"] > 0
                                and x <= bounds["withdrawals_max"]
                            ):
                                cols["wth"].append(txt)
                            elif (
                                bounds["deposits_max"] > 0
                                and x <= bounds["deposits_max"]
                            ):
                                cols["dep"].append(txt)
                            elif (
                                bounds["balance_max"] > 0 and x <= bounds["balance_max"]
                            ):
                                cols["bal"].append(txt)
                            else:
                                cols["ind"].append(txt)

                        f_date = " ".join(cols["date"]).strip()
                        f_part = " ".join(cols["part"]).strip()
                        f_vdate = " ".join(cols["v_date"]).strip() or None
                        f_type = " ".join(cols["type"]).strip() or None
                        f_chq = " ".join(cols["chq"]).strip() or None

                        raw_debit = (
                            " ".join(cols["wth"])
                            .replace(",", "")
                            .replace(" ", "")
                            .strip()
                        )
                        raw_credit = (
                            " ".join(cols["dep"])
                            .replace(",", "")
                            .replace(" ", "")
                            .strip()
                        )
                        raw_balance = (
                            " ".join(cols["bal"])
                            .replace(",", "")
                            .replace(" ", "")
                            .strip()
                        )

                        val_debit, val_credit, val_balance = None, None, 0.0
                        try:
                            val_debit = float(raw_debit) if raw_debit else None
                        except ValueError:
                            pass
                        try:
                            val_credit = float(raw_credit) if raw_credit else None
                        except ValueError:
                            pass
                        try:
                            val_balance = float(raw_balance) if raw_balance else 0.0
                        except ValueError:
                            pass

                        combined_context = f"{f_date} {f_part}".strip()
                        if self._is_header_row(
                            combined_context
                        ) or self._is_metadata_noise(combined_context):
                            continue

                        f_part_upper = f_part.upper()
                        if (
                            "B/F" in f_part_upper
                            or "BROUGHT FORWARD" in f_part_upper
                            or "OPENING BALANCE" in f_part_upper
                        ):
                            if not pdf_opening_captured:
                                pdf_opening_balance = val_balance
                                pdf_opening_captured = True
                            continue

                        # ─── CASE 1: START OF A NEW ROW (Valid Date Found) ───
                        if re.match(r"^\d{2}-\d{2}-\d{4}$", f_date):
                            if (
                                active_txn
                                and isinstance(active_txn, dict)
                                and active_txn.get("date")
                            ):
                                # 🟢 FIX: Use the standardized YYYY-MM-DD 'date' field for hashing alignment
                                row_hex = generate_row_fingerprint(
                                    bank_id=target_bank_id,
                                    account_id=self.account_id,
                                    narration=active_txn["description"],
                                    cheque_ref=active_txn["cheque_ref"],
                                    amount=float(
                                        (active_txn["credit"] or 0.0)
                                        if active_txn["credit"]
                                        else (active_txn["debit"] or 0.0)
                                    ),
                                    running_balance=float(active_txn["amount"]),
                                    debit=active_txn["debit"],
                                    credit=active_txn["credit"],
                                    date_str=str(
                                        active_txn["date"]
                                    ),  # 🚀 Changed from display_date to date
                                )
                                active_txn["Hex"] = row_hex

                                if row_hex in existing_hashes:
                                    active_txn["status"] = "DUPLICATE"
                                    duplicate_count += 1

                                preview_dataset.append(active_txn)

                            # ISO transformation for standard DB DateField validation
                            d_parts = f_date.split("-")
                            db_date_format = f"{d_parts[2]}-{d_parts[1]}-{d_parts[0]}"

                            db_vdate_format = None
                            if f_vdate and re.match(r"^\d{2}-\d{2}-\d{4}$", f_vdate):
                                vd_parts = f_vdate.split("-")
                                db_vdate_format = (
                                    f"{vd_parts[2]}-{vd_parts[1]}-{vd_parts[0]}"
                                )

                            active_txn = {
                                "id": get_random_string(8),
                                "date": db_date_format,  # 🚀 Standard YYYY-MM-DD
                                "display_date": f_date,
                                "value_date": db_vdate_format or f_vdate,
                                "description": f_part,
                                "tran_type": f_type,
                                "cheque_ref": f_chq,
                                "debit": val_debit,
                                "credit": val_credit,
                                "amount": val_balance,
                                "status": "NEW",
                                "Hex": "",
                            }

                            if val_debit:
                                total_debit += val_debit
                                debit_line_count += 1
                            if val_credit:
                                total_credit += val_credit
                                credit_line_count += 1
                            continue

                        # ─── CASE 2: MULTI-LINE DESCRIPTION WRAPPER TEXT (No Date) ───
                        if active_txn and isinstance(active_txn, dict) and f_part:
                            active_txn["description"] = (
                                f"{active_txn['description']} {f_part}".strip()
                            )

                            if val_debit and not active_txn.get("debit"):
                                active_txn["debit"] = val_debit
                                total_debit += val_debit
                                debit_line_count += 1
                            if val_credit and not active_txn.get("credit"):
                                active_txn["credit"] = val_credit
                                total_credit += val_credit
                                credit_line_count += 1

                            if val_balance:
                                active_txn["amount"] = val_balance

                # ─── SAFE LOOP EXIT AGGREGATION: Final Row Signature Assignment ───
                if (
                    active_txn
                    and isinstance(active_txn, dict)
                    and active_txn.get("date")
                ):
                    row_hex = generate_row_fingerprint(
                        bank_id=target_bank_id,
                        account_id=self.account_id,
                        narration=active_txn["description"],
                        cheque_ref=active_txn["cheque_ref"],
                        amount=float(
                            (active_txn["credit"] or 0.0)
                            if active_txn["credit"]
                            else (active_txn["debit"] or 0.0)
                        ),
                        running_balance=float(active_txn["amount"]),
                        debit=active_txn["debit"],
                        credit=active_txn["credit"],
                        date_str=str(
                            active_txn["date"]
                        ),  # 🚀 Changed from display_date to date
                    )
                    active_txn["Hex"] = row_hex

                    if row_hex in existing_hashes:
                        active_txn["status"] = "DUPLICATE"
                        duplicate_count += 1

                    preview_dataset.append(active_txn)

        except Exception as e:
            print(f"❌ CRITICAL PARSING LOOP FAILURE TRACE: {str(e)}")
            return {
                "success": False,
                "error_message": f"Core stream processing crash: {str(e)}",
            }

        self.uploaded_file.seek(0)
        print(
            f"🏁 [PIPELINE OUTPUT SUMMARY] Packed {len(preview_dataset)} immaculate transaction records with deterministic hex fingerprinting."
        )

        pdf_closing_balance = pdf_opening_balance + total_credit - total_debit

        return {
            "success": True,
            "data": {
                "status": "SUCCESS",
                "file_type": template_model.template_name,
                "decrypted": bool(verified_password),
                "count": len(preview_dataset),
                "opening_balance": pdf_opening_balance,
                "closing_balance": pdf_closing_balance,
                "total_debit": total_debit,
                "total_credit": total_credit,
                "raw_match_count": len(preview_dataset),
                "debit_line_count": debit_line_count,
                "credit_line_count": credit_line_count,
                "duplicate_count": duplicate_count,
                "preview_dataset": preview_dataset,
            },
        }
