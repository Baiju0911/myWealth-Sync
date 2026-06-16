import fitz  # PyMuPDF
import re
from datetime import datetime

# NATIVE TABLE CONFIGURATION AND UTILITY IMPORTS
from .raw_extractor import match_statement_template
from .utils import generate_row_fingerprint


class UniversalStatementParser:
    DATE_MATCH_REGEX = re.compile(
        r"\b\d{2}-\d{2}-\d{4}\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{2}/\d{2}/\d{4}\b"
    )
    CLEAN_NUM_REGEX = re.compile(r"[^\d.]")
    NUMERIC_FINDER_REGEX = re.compile(
        r"\b\d{1,3}(?:,\d{2,3})*(?:\.\d{2})(?:CR|DR)?\b", re.I
    )
    BALANCE_SIGN_REGEX = re.compile(r"(CR|DR)$", re.I)
    ACCOUNT_REF_REGEX = re.compile(r"\b\d{9,18}\b")

    INLINE_CREDIT_REGEX = re.compile(r"\b([\d,]+\.\d{2})CR\b", re.I)
    RAW_DECIMAL_REGEX = re.compile(r"\b\d{1,3}(?:,\d{2,3})*(?:\.\d{2})\b")

    OPENING_BALANCE_MARKERS = [
        r"\bBROUGHT\s+FORWARD\b",
        r"\bOPENING\s+BALANCE\b",
        r"\bB/F\b",
        r"\bO/B\b",
        r"\bBAL\s+BF\b",
    ]
    OPENING_BALANCE_REGEX = [re.compile(p, re.I) for p in OPENING_BALANCE_MARKERS]

    SYSTEM_NOISE_PATTERNS = [
        r"\bPAGE\s+NO\b",
        r"\bVALUE\s+DATE\b",
        r"\bCHEQUE\b",
        r"\bPOST\s+DATE\b",
        r"\bDESCRIPTION\b",
        r"\bDEBIT\b",
        r"\bCREDIT\b",
        r"\bBALANCE\b",
        r"\bNO/REFERENCE\b",
    ]
    SYSTEM_NOISE_REGEX = [re.compile(p, re.I) for p in SYSTEM_NOISE_PATTERNS]

    def __init__(self, uploaded_file, account_id):
        self.uploaded_file = uploaded_file
        self.account_id = account_id
        self.bounds = {}
        self.password = None
        self.template_obj = None
        self.calculated_opening_balance = 0.0
        self.calculated_closing_balance = 0.0
        self.running_tally_debits = 0.0
        self.running_tally_credits = 0.0
        self.count_debits = 0
        self.count_credits = 0
        self.count_empty_memo_lines = 0
        self.reconciliation_status = "PENDING"
        self.audit_warning_message = None

    def _parse_float(self, value):
        if not value:
            return 0.0
        clean = self.CLEAN_NUM_REGEX.sub("", str(value))
        try:
            if clean and clean != ".":
                return float(clean)
        except (TypeError, ValueError):
            pass
        return 0.0

    def _normalize_date(self, date_str):
        target_fmt = self.bounds.get("date_format", "%d-%m-%Y")
        for fmt in (target_fmt, "%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
        return date_str

    def execute_full_parse(self):
        payload = match_statement_template(self.uploaded_file, self.account_id)
        if not payload or payload.get("template") is None:
            return {
                "success": False,
                "error_message": "Document template mapping parameters could not be resolved.",
            }

        self.template_obj = payload["template"]
        self.password = payload["unlocked_password"]
        self.bounds = payload["bounds"]

        raw_rows = self._extract_pdf_rows()
        final_clean_dataset = self._process_stream_buffer(raw_rows)

        return {
            "success": True,
            "data": {
                "count": len(final_clean_dataset),
                "preview_dataset": final_clean_dataset,
                "opening_balance": self.calculated_opening_balance,
                "closing_balance": self.calculated_closing_balance,
                "total_debit": round(self.running_tally_debits, 2),
                "total_credit": round(self.running_tally_credits, 2),
                "debit_line_count": self.count_debits,
                "credit_line_count": self.count_credits,
                "empty_memo_line_count": self.count_empty_memo_lines,
                "reconciliation_status": self.reconciliation_status,
                "audit_warning": self.audit_warning_message,
            },
        }

    def _extract_pdf_rows(self):
        self.uploaded_file.seek(0)
        pdf_bytes = self.uploaded_file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        output = []
        y_tolerance = float(self.bounds.get("y_tolerance", 3.0))

        for page_idx, page in enumerate(doc, start=1):
            page_width = float(page.rect.width or 1)
            words = page.get_text("words")
            if not words:
                continue

            lines_pool = []
            for w in words:
                x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4].strip()
                if not text:
                    continue
                x_pct = round((x0 / page_width) * 100, 2)

                matched = False
                for line in lines_pool:
                    if not (
                        y1 < (line["y0"] - y_tolerance)
                        or y0 > (line["y1"] + y_tolerance)
                    ):
                        line["tokens"].append({"text": text, "x": x_pct, "y": y0})
                        line["y0"], line["y1"] = min(line["y0"], y0), max(
                            line["y1"], y1
                        )
                        matched = True
                        break
                if not matched:
                    lines_pool.append(
                        {
                            "y0": y0,
                            "y1": y1,
                            "tokens": [{"text": text, "x": x_pct, "y": y0}],
                        }
                    )

            for line in sorted(lines_pool, key=lambda l: l["y0"]):
                sorted_tokens = sorted(line["tokens"], key=lambda t: (t["y"], t["x"]))
                output.append(
                    {
                        "tokens": sorted_tokens,
                        "full_line_text": " ".join(t["text"] for t in sorted_tokens),
                        "page_source": page_idx,
                    }
                )
        return output

    def _process_stream_buffer(self, raw_rows):
        explicit_opening_balance = None
        for row in raw_rows:
            text_upper = row["full_line_text"].upper()
            if any(regex.search(text_upper) for regex in self.OPENING_BALANCE_REGEX):
                decimal_candidates = self.NUMERIC_FINDER_REGEX.findall(
                    row["full_line_text"]
                )
                if decimal_candidates:
                    explicit_opening_balance = self._parse_float(decimal_candidates[-1])
                    break

        intermediate_txns = []
        debit_target_x = float(self.bounds.get("debit_x", 66.0))
        credit_target_x = float(self.bounds.get("credit_x", 78.5))

        i = 0
        while i < len(raw_rows):
            row = raw_rows[i]
            text = row["full_line_text"].strip()
            text_upper = text.upper()
            page_idx = row.get("page_source", 1)

            if any(
                m in text_upper
                for m in (
                    "STATEMENT SUMMARY",
                    "TOTAL DEBITS",
                    "TOTAL CREDITS",
                    "CLOSING BALANCE",
                )
            ):
                i += 1
                continue

            line_dates = []
            for token in row["tokens"]:
                t_text = token["text"].strip()
                if self.DATE_MATCH_REGEX.match(t_text):
                    line_dates.append({"text": t_text, "x": token["x"]})

            primary_anchor_found = any(dt["x"] <= 12.0 for dt in line_dates)
            if not primary_anchor_found:
                i += 1
                continue

            active_post_date = None
            active_value_date = None
            found_dts = [dt["text"] for dt in line_dates if dt["x"] <= 24.0]
            if len(found_dts) >= 2:
                active_post_date, active_value_date = found_dts[0], found_dts[1]
            elif len(found_dts) == 1:
                active_post_date = active_value_date = found_dts[0]

            row_tokens_pool = list(row["tokens"])

            k = i + 1
            while k < len(raw_rows):
                next_row = raw_rows[k]
                has_true_date_anchor = any(
                    self.DATE_MATCH_REGEX.match(t["text"].strip())
                    and float(t["x"]) <= 24.0
                    for t in next_row["tokens"]
                )
                if has_true_date_anchor or any(
                    m in next_row["full_line_text"].upper()
                    for m in ("STATEMENT SUMMARY", "CLOSING BALANCE")
                ):
                    break
                row_tokens_pool.extend(next_row["tokens"])
                k += 1

            i = k

            row_numbers = []
            active_refs = []
            for token in row_tokens_pool:
                t_text = token["text"].strip()
                if self.ACCOUNT_REF_REGEX.match(t_text):
                    if t_text not in active_refs:
                        active_refs.append(t_text)
                    continue
                if self.NUMERIC_FINDER_REGEX.match(
                    t_text
                ) and not self.DATE_MATCH_REGEX.match(t_text):
                    row_numbers.append(
                        {"val": t_text, "x": float(token["x"]), "y": float(token["y"])}
                    )

            row_numbers = sorted(row_numbers, key=lambda n: n["x"])

            balances = [
                n
                for n in row_numbers
                if n["x"] >= 80.0 or self.BALANCE_SIGN_REGEX.search(n["val"])
            ]
            tx_amounts = [n for n in row_numbers if n not in balances]

            # Clean text arrays for normal description tokens
            sub_words = []
            for t in row_tokens_pool:
                t_text = t["text"].strip()
                if (
                    not self.DATE_MATCH_REGEX.match(t_text)
                    and not self.NUMERIC_FINDER_REGEX.match(t_text)
                    and not self.ACCOUNT_REF_REGEX.match(t_text)
                ):
                    if not any(
                        noise in t_text.upper()
                        for noise in ("CR", "DR", "₹", "NEW", "INR")
                    ):
                        sub_words.append(t_text)

            # ─── 📐 UNIVERSAL ROW A & B GEOMETRIC MULTI-ROW SPLITTER ───
            if len(tx_amounts) >= 2 and len(balances) >= 2:
                for idx_amt, amt in enumerate(tx_amounts):
                    if idx_amt < len(balances):
                        target_y = amt["y"]
                        line_specific_words = []
                        for t in row_tokens_pool:
                            t_text = t["text"].strip()
                            if abs(float(t["y"]) - target_y) <= 4.0:
                                if (
                                    not self.DATE_MATCH_REGEX.match(t_text)
                                    and not self.NUMERIC_FINDER_REGEX.match(t_text)
                                    and not self.ACCOUNT_REF_REGEX.match(t_text)
                                ):
                                    if not any(
                                        noise in t_text.upper()
                                        for noise in ("CR", "DR", "₹", "NEW", "INR")
                                    ):
                                        line_specific_words.append(t_text)

                        if not line_specific_words:
                            # Fallback to general segment if vertical filter is too tight
                            line_specific_words = (
                                sub_words[:4] if idx_amt == 0 else sub_words[4:]
                            )

                        self._commit_record(
                            intermediate_txns,
                            active_post_date,
                            active_value_date,
                            line_specific_words,
                            (
                                amt["val"]
                                if amt["x"] <= ((debit_target_x + credit_target_x) / 2)
                                else None
                            ),
                            (
                                amt["val"]
                                if amt["x"] > ((debit_target_x + credit_target_x) / 2)
                                else None
                            ),
                            balances[idx_amt]["val"],
                            active_refs,
                            page_idx,
                        )
                continue

            active_debit = None
            active_credit = None
            active_balance = None

            if (
                len(row_numbers) >= 2
                and row_numbers[-1]["x"] >= 80.0
                and row_numbers[-2]["x"] >= 65.0
            ):
                active_balance = row_numbers[-1]["val"]
                amt_token = row_numbers[-2]
                if amt_token["x"] <= ((debit_target_x + credit_target_x) / 2):
                    active_debit = amt_token["val"]
                else:
                    active_credit = amt_token["val"]
            else:
                if balances:
                    active_balance = balances[0]["val"]
                if tx_amounts:
                    target_amt = tx_amounts[0]
                    if target_amt["x"] <= ((debit_target_x + credit_target_x) / 2):
                        active_debit = target_amt["val"]
                    else:
                        active_credit = target_amt["val"]

            inline_cr_match = self.INLINE_CREDIT_REGEX.search(" ".join(sub_words))
            if not active_credit and not active_debit and inline_cr_match:
                active_credit = inline_cr_match.group(1)

            if active_credit and active_balance:
                if self.BALANCE_SIGN_REGEX.search(
                    str(active_credit)
                ) or self._parse_float(active_credit) > self._parse_float(
                    active_balance
                ):
                    active_credit, active_balance = active_balance, active_credit

            self._commit_record(
                intermediate_txns,
                active_post_date,
                active_value_date,
                sub_words,
                active_debit,
                active_credit,
                active_balance,
                active_refs,
                page_idx,
            )

        # ====================== PURE GEOMETRIC CHRONOLOGICAL RECONCILIATION ======================
        if intermediate_txns:
            if explicit_opening_balance is not None:
                resolved_opening_anchor = explicit_opening_balance
            else:
                if self.bounds.get("opening_balance"):
                    resolved_opening_anchor = self._parse_float(
                        self.bounds.get("opening_balance")
                    )
                else:
                    first_tx = intermediate_txns[0]
                    resolved_opening_anchor = (
                        self._parse_float(first_tx["balance"])
                        + self._parse_float(first_tx["debit"])
                        - self._parse_float(first_tx["credit"])
                    )

            self.calculated_opening_balance = round(resolved_opening_anchor, 2)
            running_calculation_tally = resolved_opening_anchor

            variance_rows_pool = []
            admin_memo_rows_pool = []

            for idx, tx in enumerate(intermediate_txns, start=1):
                # ─── 🛡️ THE PARENT NARRATIVE INHERITANCE PASS ───
                # If a row's description compiled completely empty, pull down the narrative string from the record above it
                if tx["narration_description"] == "ONLINE TRANSACTION" and idx > 1:
                    tx["narration_description"] = intermediate_txns[idx - 2][
                        "narration_description"
                    ]

                dr_val = self._parse_float(tx["debit"])
                cr_val = self._parse_float(tx["credit"])
                parsed_row_bal = self._parse_float(tx["balance"])

                if dr_val > 0.0:
                    self.running_tally_debits += dr_val
                    self.count_debits += 1
                if cr_val > 0.0:
                    self.running_tally_credits += cr_val
                    self.count_credits += 1
                if dr_val == 0.0 and cr_val == 0.0:
                    self.count_empty_memo_lines += 1
                    admin_memo_rows_pool.append((idx, tx))

                running_calculation_tally = round(
                    running_calculation_tally - dr_val + cr_val, 2
                )
                tx["calculated_running_total"] = running_calculation_tally

                if (
                    parsed_row_bal > 0.0
                    and abs(running_calculation_tally - parsed_row_bal) > 0.01
                ):
                    variance_rows_pool.append(
                        (
                            idx,
                            tx,
                            parsed_row_bal,
                            round(parsed_row_bal - running_calculation_tally, 2),
                        )
                    )

            self.calculated_closing_balance = round(running_calculation_tally, 2)

            if variance_rows_pool:
                self.reconciliation_status = (
                    f"🔴 VARIANCE BREAK ({len(variance_rows_pool)} Lines)"
                )
                print("\n🚨 === PIPELINE DRIFT ANOMALY ISOLATION REPORT ===")
                for v_idx, v_tx, bank_bal, drift in variance_rows_pool[:30]:
                    print(
                        f"  Line {v_idx}. [{v_tx['date']}] {v_tx['narration_description'][:40]}... | Dr: {v_tx['debit'] or '0.00'} | Cr: {v_tx['credit'] or '0.00'} | PDF Bal: {v_tx['balance']} | Calc: ₹{v_tx['calculated_running_total']} | Drift: ₹{drift}"
                    )
                print(
                    f" ...Total rows exhibiting active math deviations: {len(variance_rows_pool)}"
                )
                print("===================================================\n")
            else:
                self.reconciliation_status = "🟢 VERIFIED MATCHED"
                print("\n📋 === CHRONOLOGICAL TRANSACTION JOURNAL SUMMARY ===")
                for idx, tx in enumerate(intermediate_txns, start=1):
                    print(
                        f" {idx}. [{tx['date']}] {tx['narration_description'][:45]}... | Dr: {tx['debit'] or '0.00'} | Cr: {tx['credit'] or '0.00'} | PDF Bal: {tx['balance']} | Calc Bal: ₹{tx['calculated_running_total']}"
                    )
                print("====================================================\n")

            if admin_memo_rows_pool:
                print("👻 === ADMINISTRATIVE NOTES COMPILATION PROFILE ===")
                for m_idx, m_tx in admin_memo_rows_pool:
                    print(
                        f"  [Row {m_idx} on Page {m_tx['id'].split('_')[2][1:]}] Date: {m_tx['date']} | Narration: {m_tx['narration_description']} | Bal: {m_tx['balance']}"
                    )
                print("==================================================\n")

            print("⚖️ === AUTOMATED ENGINE VERIFICATION SUMMARY DECK ===")
            print(f" 📂 TOTAL LEDGER LINES EVALUATED   : {len(intermediate_txns)}")
            print(
                f" 📦 NET ACCOUNT DEBITS SUMMED      : ₹{round(self.running_tally_debits, 2):,.2f} ({self.count_debits} Rows)"
            )
            print(
                f" 📦 NET ACCOUNT CREDITS SUMMED     : ₹{round(self.running_tally_credits, 2):,.2f} ({self.count_credits} Rows)"
            )
            print(
                f" 📋 ZERO-VALUE ADMINISTRATIVE NOTES: {self.count_empty_memo_lines} Rows"
            )
            print(
                f" 🏁 DERIVED ACCOUNT OPENING BASE   : ₹{self.calculated_opening_balance:,.2f}"
            )
            print(
                f" 🏁 COMPILED STATEMENT CLOSING     : ₹{self.calculated_closing_balance:,.2f}"
            )
            print(
                f" ⚖️ PIPELINE RECONCILIATION STATUS   : {self.reconciliation_status}"
            )
            print("=====================================================\n")

        return intermediate_txns

    def _commit_record(
        self,
        target_list,
        post_dt,
        val_dt,
        tokens_list,
        debit_val,
        credit_val,
        balance_val,
        refs_list,
        page_idx,
    ):
        full_desc = " ".join(tokens_list).strip()
        full_desc = re.sub(r"\s+-\s+", " ", full_desc)
        full_desc = re.sub(r"-$", "", full_desc)
        full_desc = re.sub(r"^-", "", full_desc)

        words = full_desc.split()
        seen = []
        for w in words:
            if not seen or w.upper() != seen[-1].upper():
                seen.append(w)
        final_narration = " ".join(seen).strip()

        if refs_list:
            final_narration = f"{final_narration} Ref: {' / '.join(refs_list)}"

        normalized_post_date = self._normalize_date(post_dt)
        normalized_val_date = (
            self._normalize_date(val_dt) if val_dt else normalized_post_date
        )

        target_list.append(
            {
                "id": f"row_hex_p{page_idx}_{normalized_post_date.replace('-', '')}_{len(target_list)}",
                "date": normalized_post_date,
                "value_date": normalized_val_date,
                "narration_description": (
                    final_narration if final_narration else "ONLINE TRANSACTION"
                ),
                "chq_ref": "",
                "tran_type": "",
                "debit": debit_val,
                "credit": credit_val,
                "balance": balance_val,
                "calculated_running_total": 0.0,
                "status": "NEW",
                "Hex": "PRODUCTION_VERIFIED",
            }
        )
