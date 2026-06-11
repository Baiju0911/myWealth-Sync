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
            "statement summary",
            # "brought forward",
            # "dr count",
            # "cr count",
            "total debits",
            "total credits",
            # "letter of authority",
            # "power of attorney",
        ]
        return any(indicator in row_text_lower for indicator in noise_indicators)

    @staticmethod
    def _safe_float(value):
        try:
            if not value:
                return None
            # Strip anything that isn't a number or decimal point
            clean_str = re.sub(r"[^\d.-]", "", value.replace(",", ""))
            return float(clean_str) if clean_str else None
        except:
            return None

    def _finalize_txn(self, txn, bank_id, existing_hashes):
        """
        Calculates the unique cryptographic row fingerprint, running dupe-checking
        subroutines, and flags the transaction status before committing to the dataset.
        """
        amount_val = float(
            (txn["credit"] or 0.0) if txn["credit"] else (txn["debit"] or 0.0)
        )

        txn["Hex"] = generate_row_fingerprint(
            bank_id=bank_id,
            account_id=self.account_id,
            narration=txn["description"],
            cheque_ref="",
            amount=amount_val,
            running_balance=float(txn["amount"]),
            debit=txn.get("debit"),
            credit=txn.get("credit"),
            date_str=str(txn["date"]),
        )

        txn["status"] = "DUPLICATE" if txn["Hex"] in existing_hashes else "NEW"
        return txn

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
        }

        preview_dataset = []
        total_debit = 0.0
        total_credit = 0.0
        debit_line_count = 0
        credit_line_count = 0
        duplicate_count = 0
        pdf_opening_balance = 0.0
        pdf_opening_captured = False
        target_bank_id = self.account.bank_id if hasattr(self.account, "bank_id") else 1

        existing_hashes = set(
            StatementStagingLine.objects.filter(account_id=self.account_id).values_list(
                "row_identifier", flat=True
            )
        )

        active_txn = None
        self.uploaded_file.seek(0)

        try:
            with pdfplumber.open(
                self.uploaded_file, password=verified_password or None
            ) as pdf:
                for page in pdf.pages:
                    lines_dict = {}
                    tolerance = 5

                    # ─── VERTICAL SNAPPING ALGORITHM REGION ───
                    for w in page.extract_words():
                        w_top = float(w["top"])
                        w_text = w["text"]
                        w_x_pct = (float(w["x0"]) / float(page.width)) * 100

                        # Find an existing horizontal lane group within the pixel tolerance
                        matched_lane = None
                        for assigned_top in lines_dict.keys():
                            if abs(w_top - assigned_top) <= tolerance:
                                matched_lane = assigned_top
                                break

                        if matched_lane is not None:
                            lines_dict[matched_lane].append(
                                {"text": w_text, "x_pct": w_x_pct}
                            )
                        else:
                            # Create a brand new horizontal lane anchor key entry point
                            lines_dict[round(w_top, 1)] = [
                                {"text": w_text, "x_pct": w_x_pct}
                            ]

                    # ─── ROW PROCESSING STREAM REGION ───
                    for v_pos in sorted(lines_dict.keys()):
                        row_tokens = sorted(lines_dict[v_pos], key=lambda t: t["x_pct"])
                        raw_line_text = " ".join(
                            [t["text"] for t in row_tokens]
                        ).strip()

                        # --- DEBUG GATEWAY DISPLAY ---
                        print(
                            f"DEBUG: Processing row: '{raw_line_text}' | Tokens found: {len(row_tokens)}"
                        )

                        if self._is_header_row(
                            raw_line_text
                        ) or self._is_metadata_noise(raw_line_text):
                            continue

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
                            ]
                        }

                        for token in row_tokens:
                            x, txt = token["x_pct"], token["text"].strip()
                            if not txt:
                                continue
                            if len(txt) > 25 and ("," in txt or " " in txt):
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

                        # 🟢 CRITICAL ARCHITECTURAL REFIX: Isolate strictly the first date token item
                        f_date = cols["date"][0].strip() if cols["date"] else ""
                        f_part = " ".join(cols["part"]).strip()

                        raw_debit = "".join(cols["wth"])
                        raw_credit = "".join(cols["dep"])
                        raw_bal = "".join(cols["bal"])

                        val_debit = self._safe_float(raw_debit)
                        val_credit = self._safe_float(raw_credit)
                        val_bal = self._safe_float(raw_bal) or 0.0

                        # Handle Opening Balance Sequences
                        if any(k in f_part.upper() for k in ["B/F", "OPENING BALANCE"]):
                            if not pdf_opening_captured:
                                pdf_opening_balance, pdf_opening_captured = (
                                    val_bal,
                                    True,
                                )
                            continue

                        # Case 1: Start of a New Transaction Record Row
                        # ─── CASE 1: START OF A NEW TRANSACTION RECORD ROW ───
                        if re.match(r"^\d{2}-\d{2}-\d{4}$", f_date):
                            if val_debit or val_credit:
                                if active_txn and (
                                    active_txn.get("debit") or active_txn.get("credit")
                                ):
                                    # Finalize and capture the state output directly
                                    finalized = self._finalize_txn(
                                        active_txn, target_bank_id, existing_hashes
                                    )
                                    preview_dataset.append(finalized)
                                    if finalized.get("status") == "DUPLICATE":
                                        duplicate_count += 1

                                active_txn = {
                                    "date": f"{f_date[6:]}-{f_date[3:5]}-{f_date[:2]}",
                                    "description": f_part,
                                    "debit": val_debit,
                                    "credit": val_credit,
                                    "amount": val_bal,
                                }
                                if val_debit:
                                    total_debit += val_debit
                                    debit_line_count += 1
                                if val_credit:
                                    total_credit += val_credit
                                    credit_line_count += 1
                            else:
                                # Date matched but no transaction values found: skip tracking noise row
                                active_txn = None

                        # ─── CASE 2: MULTI-LINE NARRATIVE DESCRIPTION CONTINUATION ───
                        elif active_txn and f_part:
                            # 🛡️ THE UNIVERSAL FINANCIAL ISOLATION SHIELD:
                            # If a line has no date, but has numeric transactional values, it's
                            # a footer summary summary deck block—NOT a narrative continuation.
                            if val_debit or val_credit:
                                if active_txn.get("debit") or active_txn.get("credit"):
                                    finalized = self._finalize_txn(
                                        active_txn, target_bank_id, existing_hashes
                                    )
                                    preview_dataset.append(finalized)
                                    if finalized.get("status") == "DUPLICATE":
                                        duplicate_count += 1
                                active_txn = None  # Instantly break memory buffer tracking connection
                                continue

                            # Safe narration text string line. Stitch it!
                            active_txn["description"] += f" {f_part}"

                            if val_bal:
                                active_txn["amount"] = val_bal

                            if val_debit and not active_txn.get("debit"):
                                active_txn["debit"] = val_debit
                                total_debit += val_debit
                                debit_line_count += 1

                            if val_credit and not active_txn.get("credit"):
                                active_txn["credit"] = val_credit
                                total_credit += val_credit
                                credit_line_count += 1

                # ─── LOOP EXIT: APPEND FINAL DANGLING BUFFERED TRANSACTION SAFELY ───
                if active_txn and (active_txn.get("debit") or active_txn.get("credit")):
                    finalized = self._finalize_txn(
                        active_txn, target_bank_id, existing_hashes
                    )
                    preview_dataset.append(finalized)
                    if finalized.get("status") == "DUPLICATE":
                        duplicate_count += 1

        except Exception as e:
            return {"success": False, "error_message": str(e)}

        return {
            "success": True,
            "data": {
                "preview_dataset": preview_dataset,
                "total_debit": round(total_debit, 2),
                "total_credit": round(total_credit, 2),
                "opening_balance": round(pdf_opening_balance, 2),
                "closing_balance": round(
                    pdf_opening_balance + total_credit - total_debit, 2
                ),
                "count": len(preview_dataset),
            },
        }
