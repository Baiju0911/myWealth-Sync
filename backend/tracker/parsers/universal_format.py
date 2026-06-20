import fitz  # PyMuPDF
import re
from datetime import datetime
import json

# NATIVE TABLE CONFIGURATION AND UTILITY IMPORTS
from .raw_extractor import match_statement_template
from .utils import generate_row_fingerprint
from tracker.models import Account, StatementStagingLine, BankCredential


class UniversalStatementParser:

    def __init__(self, uploaded_file, account_id, template_obj=None):
        self.uploaded_file = uploaded_file
        self.account_id = account_id
        self.template_obj = template_obj
        self.bounds = {}
        self.password = None

        # Operational dynamic tallies
        self.calculated_opening_balance = 0.0
        self.calculated_closing_balance = 0.0
        self.running_tally_debits = 0.0
        self.running_tally_credits = 0.0
        self.count_debits = 0
        self.count_credits = 0
        self.count_empty_memo_lines = 0
        self.reconciliation_status = "PENDING"
        self.audit_warning_message = None
        self.detected_header_indices = {}

        # ─── 🧠 CENTRAL SSOT HASH GUARDIAN & DYNAMIC CONFIG ROUTER ───
        try:
            # Unpack escaping string schemas directly out of DB columns
            config_payload = json.loads(
                getattr(self.template_obj, "signature_json", "{}")
            )
        except Exception:
            config_payload = {}

        db_regex = config_payload.get("regex_patterns", {})
        db_opening = config_payload.get("opening_balance_markers") or [
            r"\bBROUGHT\s+FORWARD\b",
            r"\bOPENING\s+BALANCE\b",
            r"\bB/F\b",
            r"\bO/B\b",
            r"\bBAL\s+BF\b",
        ]
        db_noise = config_payload.get("system_noise_patterns") or [
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

        # Pull raw pattern target strings out of database configurations cleanly
        date_match_pat = db_regex.get(
            "DATE_MATCH",
            r"\b\d{2}-\d{2}-\d{4}\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{2}/\d{2}/\d{4}\b",
        )
        numeric_finder_pat = db_regex.get(
            "NUMERIC_FINDER", r"\b\d{1,3}(?:,\d{2,3})*(?:\.\d{2})(?:CR|DR)?\b"
        )
        raw_decimal_pat = db_regex.get(
            "RAW_DECIMAL", r"\b\d{1,3}(?:,\d{2,3})*(?:\.\d{2})\b"
        )

        # ─── 🛡️ THE UNIFIED BOUNDARY CLEANER INTERCEPT ───
        # 🟢 FIXED: Use regex sub to strip out word boundaries regardless of backslash scaling traps!
        if getattr(self.template_obj, "template_name", "SBI") == "FED":
            numeric_finder_pat = re.sub(r"\\+b", "", numeric_finder_pat)
            raw_decimal_pat = re.sub(r"\\+b", "", raw_decimal_pat)

        # Compile matching engine regular expressions on-the-fly dynamically
        self.DATE_MATCH_REGEX = re.compile(date_match_pat)
        self.CLEAN_NUM_REGEX = re.compile(db_regex.get("CLEAN_NUM", r"[^\d.]"))

        self.NUMERIC_FINDER_REGEX = re.compile(numeric_finder_pat, re.I)
        self.RAW_DECIMAL_REGEX = re.compile(raw_decimal_pat)

        self.BALANCE_SIGN_REGEX = re.compile(
            db_regex.get("BALANCE_SIGN", r"(CR|DR)$"), re.I
        )
        # self.ACCOUNT_REF_REGEX = re.compile(
        #     db_regex.get("ACCOUNT_REF", r"\b\d{9,18}\b")
        # )
        self.ACCOUNT_REF_REGEX = re.compile(
            r"\b(?:[Ss]\d+|IFN\d+|ifn\d+|[Ff][Bb]\d+|[A-Za-z0-9]{8,25}|\d{6})\b"
        )
        self.INLINE_CREDIT_REGEX = re.compile(
            db_regex.get("INLINE_CREDIT", r"\b([\d,]+\.\d{2})CR\b"), re.I
        )

        # Build clean mapping sets from model-driven pattern iterations
        self.OPENING_BALANCE_REGEX = [re.compile(p, re.I) for p in db_opening]
        self.SYSTEM_NOISE_REGEX = [re.compile(p, re.I) for p in db_noise]

    def _map_header_indices(self, raw_rows):
        """Scans the header lines to find where columns actually are."""
        try:
            mapping = json.loads(
                getattr(self.template_obj, "header_mapping_json", "{}")
            )
        except Exception:
            mapping = {}

        header_limit = int(getattr(self.template_obj, "header_lines_to_skip", 5))

        # Scan only the rows designated as headers
        for i in range(min(header_limit, len(raw_rows))):
            row = raw_rows[i]
            for token in row["tokens"]:
                t_text = token["text"].strip().lower()
                for key, aliases in mapping.items():
                    if any(alias.lower() in t_text for alias in aliases):
                        self.detected_header_indices[key] = int(token["x"])

        # Fallback to DB indices if no headers are found
        if not self.detected_header_indices:
            self.detected_header_indices = {
                "date": getattr(self.template_obj, "date_x", 4.5),
                "type": getattr(self.template_obj, "type_x", 19.5),
                "debit": getattr(self.template_obj, "debit_x", 66.0),
                "credit": getattr(self.template_obj, "credit_x", 78.5),
                "balance": getattr(self.template_obj, "balance_x", 98.0),
            }

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
        target_fmt = getattr(self.template_obj, "date_format", "%d-%m-%Y")
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
        self._map_header_indices(raw_rows)
        final_clean_dataset, system_noise_dataset = self._process_stream_buffer(
            raw_rows
        )

        return {
            "success": True,
            "data": {
                "count": len(final_clean_dataset),
                "preview_dataset": final_clean_dataset,
                "system_noise_dataset": system_noise_dataset,
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

        base_y_tolerance = float(getattr(self.template_obj, "y_tolerance", 2.5))
        is_fed = getattr(self.template_obj, "template_name", "SBI") == "FED"
        active_delta = 4.2 if is_fed else base_y_tolerance

        for page_idx, page in enumerate(doc, start=1):
            page_width = float(page.rect.width or 1)
            words = page.get_text("words")
            if not words:
                continue

            # ─── 🔍 STEP 1: LOOKAHEAD SCAN FOR LINE DATE ANCHORS ───
            date_baselines = []
            for w in words:
                x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4].strip()
                x_pct = (x0 / page_width) * 100
                if self.DATE_MATCH_REGEX.match(text) and x_pct <= 10.0:
                    date_baselines.append(y0)

            lines_pool = []
            for w in words:
                x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4].strip()
                if not text:
                    continue
                x_pct = round((x0 / page_width) * 100, 2)

                belongs_to_date_row = any(
                    abs(y0 - d_y) <= active_delta for d_y in date_baselines
                )

                matched = False
                for line in lines_pool:
                    if belongs_to_date_row != line["belongs_to_date_row"]:
                        continue

                    if abs(y0 - line["base_y"]) <= active_delta:
                        line["tokens"].append({"text": text, "x": x_pct, "y": y0})
                        matched = True
                        break

                if not matched:
                    lines_pool.append(
                        {
                            "base_y": y0,
                            "belongs_to_date_row": belongs_to_date_row,
                            "tokens": [{"text": text, "x": x_pct, "y": y0}],
                        }
                    )

            # ─── 📊 TWO-DIMENSIONAL SPATIAL AGGREGATION ENGINE ───
            for line in sorted(lines_pool, key=lambda l: l["base_y"]):
                # 🟢 FIXED: Sort tokens by vertical tier line level (Y) first, then horizontal column layout (X)
                # This guarantees multi-line statements read natively from top-to-bottom, left-to-right!
                sorted_tokens = sorted(
                    line["tokens"], key=lambda t: (t.get("y", 0), t.get("x", 0))
                )

                output.append(
                    {
                        "tokens": sorted_tokens,
                        "full_line_text": " ".join(t["text"] for t in sorted_tokens),
                        "page_source": page_idx,
                    }
                )
        return output

    def _process_stream_buffer2(self, raw_rows):
        final_clean_dataset = []
        system_noise_records = []

        date_x = self.detected_header_indices.get(
            "date", float(getattr(self.template_obj, "date_x", 4.5))
        )
        debit_x = self.detected_header_indices.get(
            "debit", float(getattr(self.template_obj, "debit_x", 66.0))
        )
        credit_x = self.detected_header_indices.get(
            "credit", float(getattr(self.template_obj, "credit_x", 78.5))
        )
        balance_x = self.detected_header_indices.get(
            "balance", float(getattr(self.template_obj, "balance_x", 86.0))
        )

        try:
            config_payload = json.loads(
                getattr(self.template_obj, "signature_json", "{}")
            )
        except Exception:
            config_payload = {}

        db_summary_markers = config_payload.get("summary_markers") or [
            "STATEMENT SUMMARY",
            "TOTAL DEBITS",
            "TOTAL CREDITS",
            "CLOSING BALANCE",
            "GRAND TOTAL",
        ]

        opening_markers = config_payload.get("opening_balance_markers") or [
            "BROUGHT FORWARD",
            "OPENING BALANCE",
            "B/F",
            "O/B",
            "BAL BF",
        ]

        header_noise_words = [
            "VALUE DATE",
            "CHEQUE",
            "POST DESCRIPTION",
            "DEBIT",
            "CREDIT",
            "BALANCE",
            "NO/REFERENCE",
            "TRAN",
            "ABBREVIATIONS USED",
            "DISCLAIMER",
            "COMPUTER GENERATED",
            "END OF STATEMENT",
            "WEBSITE:",
        ]

        # ─── 🟢 STEP 0: INITIAL BASELINE ANCHOR SCANNER ───
        extracted_opening_balance = 0.0
        for row in raw_rows[:15]:
            text_upper = row["full_line_text"].upper()
            if any(m in text_upper for m in opening_markers):
                for t in row["tokens"]:
                    t_clean = t["text"].strip()
                    if "." in t_clean and any(c.isdigit() for c in t_clean):
                        try:
                            num_only = "".join(
                                c for c in t_clean if c.isdigit() or c == "."
                            )
                            val = float(num_only)
                            if "DR" in t_clean.upper() or "DR" in text_upper:
                                extracted_opening_balance = -val
                            else:
                                extracted_opening_balance = val
                            break
                        except ValueError:
                            pass
                if extracted_opening_balance != 0.0:
                    break

        if extracted_opening_balance != 0.0:
            setattr(self.template_obj, "opening_balance", extracted_opening_balance)

        active_txn = None
        last_known_balance = extracted_opening_balance

        for idx, row in enumerate(raw_rows):
            text_upper = row["full_line_text"].upper()
            page_idx = row.get("page_source", 1)

            # 🟢 DROP SYSTEMIC FOOTER LAYOUT ROWS IMMEDIATELY
            if (
                any(m in text_upper for m in db_summary_markers)
                or "PAGE " in text_upper
                or "THE FEDERAL BANK" in text_upper
                or "ABBREVIATIONS USED:" in text_upper
                or "DISCLAIMER:" in text_upper
                or "END OF STATEMENT" in text_upper
                or "IN CASE YOUR ACCOUNT IS OPERATED" in text_upper
                or "LAST DATE AND TIME APPEARING" in text_upper
                or "LAST TRANSACTION DATE" in text_upper
                or "DR COUNT" in text_upper
                or "CR COUNT" in text_upper
                or "STATEMENT SUMMARY" in text_upper
                or "VALUE DATE" in text_upper
            ):
                continue

            if sum(1 for hw in header_noise_words if hw in text_upper) >= 3:
                continue

            row_dates = [
                t["text"]
                for t in row["tokens"]
                if self.DATE_MATCH_REGEX.match(t["text"].strip())
                and t["x"] <= (date_x + 6.0)
            ]

            if row_dates:
                if active_txn:
                    if active_txn["balance"]:
                        try:
                            last_known_balance = float(
                                self.CLEAN_NUM_REGEX.sub("", active_txn["balance"])
                            )
                        except ValueError:
                            pass

                    # ─── 📊 CHRONOLOGICAL NARRATION FLATTENER ───
                    final_ordered_narration = []
                    for raw_t in active_txn["_raw_line_text_tokens"]:
                        clean_raw_t = raw_t.strip()

                        if (
                            not clean_raw_t
                            or clean_raw_t.upper() in ("CR", "DR")
                            or self.DATE_MATCH_REGEX.match(clean_raw_t)
                        ):
                            continue

                        for d in active_txn["_discovered_decimals"]:
                            clean_raw_t = clean_raw_t.replace(d, "")

                        clean_raw_t = clean_raw_t.strip()
                        if clean_raw_t and not any(
                            hw in clean_raw_t.upper() for hw in header_noise_words
                        ):
                            if clean_raw_t not in final_ordered_narration:
                                final_ordered_narration.append(clean_raw_t)

                    # Join tokens into a single clean line string pass
                    joined_narration = " ".join(final_ordered_narration).strip()
                    joined_upper = joined_narration.upper()

                    # ─── 🛡️ HARDENED STATEMENT SUMMARY TERMINATOR INTERCEPT ───
                    # Cut off text collection immediately if statement metadata appends to the line
                    cutoff_markers = [
                        "STATEMENT SUMMARY",
                        "BROUGHT FORWARD",
                        "DR COUNT",
                        "CR COUNT",
                        "CLOSING BALANCE",
                        "TOTAL DEBITS",
                        "TOTAL CREDITS" "IN CASE YOUR ACCOUNT IS OPERATED",
                        "LAST TRANSACTION DATE",
                        "PAGE NO.",
                    ]

                    for marker in cutoff_markers:
                        if marker in joined_upper:
                            # Isolate the exact point where the summary layout block starts
                            marker_idx = joined_upper.find(marker)
                            # Slice the narration string clean right before that index marker
                            joined_narration = joined_narration[:marker_idx].strip()
                            break

                    # Update transaction container token array with the cleaned text pass
                    active_txn["narration_tokens"] = (
                        [joined_narration] if joined_narration else []
                    )

                    self._commit_record(
                        final_clean_dataset,
                        active_txn["post_date"],
                        active_txn["value_date"] or active_txn["post_date"],
                        active_txn["narration_tokens"],
                        active_txn["debit"],
                        active_txn["credit"],
                        active_txn["balance"],
                        active_txn["page_idx"],
                    )

                active_txn = {
                    "page_idx": page_idx,
                    "post_date": row_dates[0],
                    "value_date": None,
                    "narration_tokens": [],
                    "debit": None,
                    "credit": None,
                    "balance": None,
                    "_raw_line_text_tokens": [],
                    "_discovered_decimals": [],
                }

            if not active_txn:
                continue

            # GLOBAL LINE BOUNDARY-FREE DECIMALS INTERCEPT
            line_decimals = []
            for t in row["tokens"]:
                clean_t = t["text"].strip()
                if (
                    "." in clean_t
                    and any(c.isdigit() for c in clean_t)
                    and not any(hw in clean_t.upper() for hw in header_noise_words)
                ):
                    num_only = "".join(c for c in clean_t if c.isdigit() or c == ".")
                    if num_only and num_only != "." and num_only.count(".") == 1:
                        line_decimals.append({"val": num_only, "x": t["x"]})
                        if num_only not in active_txn["_discovered_decimals"]:
                            active_txn["_discovered_decimals"].append(num_only)
                        if clean_t not in active_txn["_discovered_decimals"]:
                            active_txn["_discovered_decimals"].append(clean_t)

            sorted_tokens = sorted(
                row["tokens"], key=lambda k: (k.get("y", 0), k.get("x", 0))
            )

            for token in sorted_tokens:
                t_text = token["text"].strip()
                x = token["x"]
                if not t_text or any(hw in t_text.upper() for hw in header_noise_words):
                    continue

                active_txn["_raw_line_text_tokens"].append(token["text"])

                if (date_x + 5.0) < x < 18.5 and self.DATE_MATCH_REGEX.match(t_text):
                    if t_text != active_txn["post_date"]:
                        active_txn["value_date"] = t_text

                # ─── 📊 SLOT C: BALANCE-BASED MONETARY ROUTER ───
                elif "." in t_text and any(c.isdigit() for c in t_text):
                    clean_num = "".join(c for c in t_text if c.isdigit() or c == ".")
                    if clean_num and clean_num != "." and clean_num.count(".") == 1:
                        # If we have multiple numbers on the line, the last one is ALWAYS the balance column
                        if x < 62.0 and len(line_decimals) >= 2:
                            current_row_balance = float(line_decimals[-1]["val"])
                            txn_amt_str = line_decimals[-2]["val"]
                            txn_amt_flo = float(txn_amt_str)

                            active_txn["balance"] = line_decimals[-1]["val"]

                            # 🟢 RULE: Let the running balance dictate the column type completely
                            if last_known_balance is not None:
                                # Balance increased -> Must be a Deposit (Credit)
                                if current_row_balance > last_known_balance:
                                    active_txn["credit"] = txn_amt_str
                                    active_txn["debit"] = "-"
                                # Balance decreased -> Must be a Withdrawal (Debit)
                                else:
                                    active_txn["debit"] = txn_amt_str
                                    active_txn["credit"] = "-"
                            else:
                                # Initial fallback check if baseline is missing
                                if (
                                    "CREDIT" in text_upper
                                    or "SBINT" in text_upper
                                    or "INT ON" in text_upper
                                ):
                                    active_txn["credit"] = txn_amt_str
                                else:
                                    active_txn["debit"] = txn_amt_str
                        else:
                            # Single number fallback fallback coordinate bounding box lane checking
                            dist_to_debit = abs(x - debit_x)
                            dist_to_credit = abs(x - credit_x)
                            dist_to_balance = abs(x - balance_x)
                            min_dist = min(
                                dist_to_debit, dist_to_credit, dist_to_balance
                            )

                            if min_dist == dist_to_balance:
                                active_txn["balance"] = clean_num
                            elif min_dist == dist_to_credit:
                                active_txn["credit"] = clean_num
                                active_txn["debit"] = "-"
                            elif min_dist == dist_to_debit:
                                active_txn["debit"] = clean_num
                                active_txn["credit"] = "-"

        if active_txn:
            final_ordered_narration = []
            for raw_t in active_txn["_raw_line_text_tokens"]:
                clean_raw_t = raw_t.strip()
                if (
                    not clean_raw_t
                    or clean_raw_t.upper() in ("CR", "DR")
                    or self.DATE_MATCH_REGEX.match(clean_raw_t)
                ):
                    continue
                for d in active_txn["_discovered_decimals"]:
                    clean_raw_t = clean_raw_t.replace(d, "")
                clean_raw_t = clean_raw_t.strip()
                if clean_raw_t and not any(
                    hw in clean_raw_t.upper() for hw in header_noise_words
                ):
                    if clean_raw_t not in final_ordered_narration:
                        final_ordered_narration.append(clean_raw_t)
            active_txn["narration_tokens"] = final_ordered_narration

            self._commit_record(
                final_clean_dataset,
                active_txn["post_date"],
                active_txn["value_date"] or active_txn["post_date"],
                active_txn["narration_tokens"],
                active_txn["debit"],
                active_txn["credit"],
                active_txn["balance"],
                active_txn["page_idx"],
            )
        return final_clean_dataset, system_noise_records

    def _process_stream_buffer(self, raw_rows):
        import re  # 🟢 Ensure regex engine is ready for structural pattern tracking

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
        system_noise_records = []

        debit_target_x = self.detected_header_indices.get(
            "debit", float(getattr(self.template_obj, "debit_x", 66.0))
        )
        credit_target_x = self.detected_header_indices.get(
            "credit", float(getattr(self.template_obj, "credit_x", 78.5))
        )
        y_tolerance = float(getattr(self.template_obj, "y_tolerance", 2.5))
        date_bound_x = self.detected_header_indices.get(
            "date", float(getattr(self.template_obj, "date_x", 4.5))
        )
        mid_point = (debit_target_x + credit_target_x) / 2

        try:
            config_payload = json.loads(
                getattr(self.template_obj, "signature_json", "{}")
            )
        except Exception:
            config_payload = {}
        db_summary_markers = config_payload.get("summary_markers") or [
            "STATEMENT SUMMARY",
            "TOTAL DEBITS",
            "TOTAL CREDITS",
            "CLOSING BALANCE",
        ]

        i = 0
        while i < len(raw_rows):
            row = raw_rows[i]
            text = row["full_line_text"].strip()
            text_upper = text.upper()
            page_idx = row.get("page_source", 1)

            # ─── 🛡️ DYNAMIC GENERIC INTERCEPTOR (NO HARDCODING) ───
            # Slices off dynamic summary blocks and dynamic row counts before token extraction loops run
            generic_cutoff_patterns = [
                "DR COUNT",
                "CR COUNT",
                "STATEMENT SUMMARY",
                "BROUGHT FORWARD",
                "CLOSING BALANCE",
            ]

            cutoff_pt = -1
            for marker in generic_cutoff_patterns:
                if marker in text_upper:
                    cutoff_pt = text_upper.find(marker)
                    break

            if cutoff_pt == -1:
                # Matches generic structural layout pattern: Standalone integers tracking into dynamic currency tags
                stat_match = re.search(r"\s+(\d+)\s+(\d+)\s*--?\s*₹", text)
                if stat_match:
                    cutoff_pt = stat_match.start()

            if cutoff_pt != -1:
                # Dynamically truncate text line variables
                text = text[:cutoff_pt].strip()
                text_upper = text.upper()
                row["full_line_text"] = text

                # Filter token coordinate lists to drop everything past the cutoff threshold geometry
                row["tokens"] = [t for t in row["tokens"] if t["text"].strip() in text]

            # Run summary validation logic on cleaned text bounds safely
            if any(m in text_upper for m in db_summary_markers):
                system_noise_records.append(
                    {
                        "id": f"noise_sum_{page_idx}_{i}",
                        "date": "-",
                        "value_date": "-",
                        "narration_description": text,
                        "tran_type": "SUMMARY",
                        "debit": None,
                        "credit": None,
                        "balance": None,
                        "status": "SYSTEM_NOISE",
                    }
                )
                i += 1
                continue

            line_dates = []
            for token in row["tokens"]:
                t_text = token["text"].strip()
                if self.DATE_MATCH_REGEX.match(t_text):
                    line_dates.append({"text": t_text, "x": token["x"]})

            primary_anchor_found = any(
                dt["x"] <= (date_bound_x + 8.0) for dt in line_dates
            )
            if not primary_anchor_found:
                if text and not any(
                    regex.search(text_upper) for regex in self.SYSTEM_NOISE_REGEX
                ):
                    system_noise_records.append(
                        {
                            "id": f"noise_frag_{page_idx}_{i}",
                            "date": "-",
                            "value_date": "-",
                            "narration_description": text,
                            "tran_type": "FRAGMENT",
                            "debit": None,
                            "credit": None,
                            "balance": None,
                            "status": "FRAGMENT_NOISE",
                        }
                    )
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
                    m in next_row["full_line_text"].upper() for m in db_summary_markers
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

            if not tx_amounts:
                trapped_numbers = self.NUMERIC_FINDER_REGEX.findall(
                    row["full_line_text"]
                )

                if trapped_numbers:
                    sub_words = [
                        w
                        for w in sub_words
                        if not any(num in w for num in trapped_numbers)
                        and w.upper() not in ("CR", "DR")
                    ]

                    if len(trapped_numbers) >= 2:
                        tx_amounts = [
                            {
                                "val": trapped_numbers[-2],
                                "x": (debit_target_x + credit_target_x) / 2,
                                "y": (
                                    row_tokens_pool[0]["y"] if row_tokens_pool else 0.0
                                ),
                            }
                        ]
                        balances = [
                            {
                                "val": trapped_numbers[-1],
                                "x": 90.0,
                                "y": (
                                    row_tokens_pool[0]["y"] if row_tokens_pool else 0.0
                                ),
                            }
                        ]
                    else:
                        tx_amounts = [
                            {
                                "val": trapped_numbers[0],
                                "x": (debit_target_x + credit_target_x) / 2,
                                "y": (
                                    row_tokens_pool[0]["y"] if row_tokens_pool else 0.0
                                ),
                            }
                        ]

            if len(tx_amounts) >= 2 and len(balances) >= 2:
                for idx_amt, amt in enumerate(tx_amounts):
                    if idx_amt < len(balances):
                        target_y = amt["y"]
                        line_specific_words = []
                        for t in row_tokens_pool:
                            t_text = t["text"].strip()
                            if abs(float(t["y"]) - target_y) <= (y_tolerance + 1.5):
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
                            line_specific_words = (
                                sub_words[:4] if idx_amt == 0 else sub_words[4:]
                            )
                        active_debit = amt["val"] if amt["x"] <= mid_point else None
                        active_credit = amt["val"] if amt["x"] > mid_point else None

                        self._commit_record(
                            intermediate_txns,
                            active_post_date,
                            active_value_date,
                            line_specific_words,
                            active_debit,
                            active_credit,
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

            if (
                not active_debit
                and not active_credit
                and not active_balance
                and not sub_words
            ):
                continue

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

        # ====================== GEOMETRIC RECONCILIATION CHANNELS ======================
        if intermediate_txns:
            if explicit_opening_balance is not None:
                resolved_opening_anchor = explicit_opening_balance
            else:
                resolved_opening_anchor = self._parse_float(
                    getattr(self.template_obj, "opening_balance", 0.0)
                )
                if resolved_opening_anchor == 0.0:
                    first_tx = intermediate_txns[0]
                    resolved_opening_anchor = (
                        self._parse_float(first_tx["balance"])
                        + self._parse_float(first_tx["debit"])
                        + -self._parse_float(first_tx["credit"])
                    )

            self.calculated_opening_balance = round(resolved_opening_anchor, 2)
            running_calculation_tally = resolved_opening_anchor
            variance_rows_pool = []
            admin_memo_rows_pool = []

            existing_database_hashes = set(
                StatementStagingLine.objects.filter(
                    account_id=str(self.account_id)
                ).values_list("row_identifier", flat=True)
            )

            for idx, tx in enumerate(intermediate_txns, start=1):
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
                    tx["status"] = "MEMO"
                    system_noise_records.append(
                        {
                            "id": tx["id"].replace("row_hex", "noise_hex"),
                            "date": tx["date"],
                            "value_date": tx["value_date"],
                            "narration_description": tx["narration_description"],
                            "tran_type": "MEMO",
                            "debit": "-",
                            "credit": "-",
                            "balance": tx["balance"],
                            "status": "ADMIN_NOTE",
                        }
                    )
                elif tx.get("Hex") in existing_database_hashes:
                    tx["status"] = "DUPLICATE"
                else:
                    tx["status"] = "NEW"

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
            self.reconciliation_status = (
                f"🔴 VARIANCE BREAK ({len(variance_rows_pool)} Lines)"
                if variance_rows_pool
                else "🟢 VERIFIED MATCHED"
            )

            if variance_rows_pool:
                print("\n🚨 === PIPELINE DRIFT ANOMALY ISOLATION REPORT ===")
                for v_idx, v_tx, bank_bal, drift in variance_rows_pool[:30]:
                    print(
                        f" Line {v_idx}. [{v_tx['date']}] {v_tx['narration_description'][:40]}... | PDF Bal: {v_tx['balance']} | Calc: ₹{v_tx['calculated_running_total']} | Drift: ₹{drift}"
                    )
            else:
                print("\n📋 === CHRONOLOGICAL TRANSACTION JOURNAL SUMMARY ===")
                for idx, tx in enumerate(intermediate_txns, start=1):
                    print(
                        f" {idx}. [{tx['date']}] {tx['narration_description'][:45]}... | PDF Bal: {tx['balance']} | Calc Bal: ₹{tx['calculated_running_total']}"
                    )

            if admin_memo_rows_pool:
                print("\n👻 === ADMINISTRATIVE NOTES COMPILATION PROFILE ===")
                for m_idx, m_tx in admin_memo_rows_pool:
                    print(
                        f" [Row {m_idx}] Date: {m_tx['date']} | Narration: {m_tx['narration_description']} | Bal: {m_tx['balance']}"
                    )

            print("\n⚖️ === AUTOMATED ENGINE VERIFICATION SUMMARY DECK ===")
            print(f" 📂 TOTAL LEDGER LINES EVALUATED : {len(intermediate_txns)}")
            print(
                f" 📦 NET ACCOUNT DEBITS SUMMED : ₹{round(self.running_tally_debits, 2):,.2f} ({self.count_debits} Rows)"
            )
            print(
                f" 📦 NET ACCOUNT CREDITS SUMMED : ₹{round(self.running_tally_credits, 2):,.2f} ({self.count_credits} Rows)"
            )
            print(
                f" 📋 ZERO-VALUE ADMINISTRATIVE NOTES: {self.count_empty_memo_lines} Rows"
            )
            print(
                f" ⚖️ PIPELINE RECONCILIATION STATUS : {self.reconciliation_status}\n"
            )

        return intermediate_txns, system_noise_records

    def _commit_record1(
        self,
        dataset,
        post_date,
        value_date,
        narration_tokens,
        debit,
        credit,
        balance,
        page_idx,
    ):
        # 1. Join incoming text tokens natively
        final_narration = " ".join(narration_tokens).strip()
        final_narration_upper = final_narration.upper()

        # ─── 🟢 STATIC FOOTER CLEANUP INTERCEPT ───
        # Identify exact structural start words of the glued footer blocks
        cleanup_markers = [
            "CASH : CASH",
            "ABBREVIATIONS USED",
            "DISCLAIMER:",
            "THIS IS A COMPUTER GENERATED",
            "CIN:",
            "WEBSITE:",
        ]

        for marker in cleanup_markers:
            if marker in final_narration_upper:
                # Find the exact index where the bank footer begins
                cutoff_index = final_narration_upper.find(marker)
                # Slice the string right before that marker index and strip trailing whitespace
                final_narration = final_narration[:cutoff_index].strip()
                # Re-sync uppercase reference map just in case multiple markers hit
                final_narration_upper = final_narration.upper()

        # 🟢 Clean out trailing punctuation artifacts left over from the slice pass
        if final_narration.endswith("/") or final_narration.endswith(":"):
            final_narration = final_narration[:-1].strip()

        # 2. Commit the clean structured dictionary object safely to memory arrays
        dataset.append(
            {
                "post_date": post_date,
                "value_date": value_date or post_date,
                "narration": final_narration,
                "type": "-",
                "cheque_ref": "-",
                "debit": debit if debit else "-",
                "credit": credit if credit else "-",
                "balance": balance if balance else "-",
                "page_idx": page_idx,
            }
        )

    def _commit_record(
        self,
        dataset,
        post_date,
        value_date,
        narration_tokens,
        debit,
        credit,
        balance,
        page_idx,
        *args,
        **kwargs,
    ):
        # 1. Safely handle if active_refs array is passed as an extra positional argument
        final_page_idx = page_idx
        if args:
            final_page_idx = args[0] if len(args) == 1 else args[1]

        # 2. Join incoming text tokens natively
        if isinstance(narration_tokens, list):
            final_narration = " ".join(narration_tokens).strip()
        else:
            final_narration = str(narration_tokens).strip()

        final_narration_upper = final_narration.upper()

        # ─── 🛡️ STATIC FOOTER CLEANUP INTERCEPT ───
        cleanup_markers = [
            "CASH : CASH",
            "ABBREVIATIONS USED",
            "DISCLAIMER:",
            "THIS IS A COMPUTER GENERATED",
            "CIN:",
            "WEBSITE:",
        ]

        for marker in cleanup_markers:
            if marker in final_narration_upper:
                cutoff_index = final_narration_upper.find(marker)
                final_narration = final_narration[:cutoff_index].strip()
                final_narration_upper = final_narration.upper()

        if final_narration.endswith("/") or final_narration.endswith(":"):
            final_narration = final_narration[:-1].strip()

        # 3. Commit the clean dictionary object with dual-key aliases
        dataset.append(
            {
                "id": f"row_hex_{final_page_idx}_{len(dataset)}",  # Unique tracking ID string fallback
                "date": post_date,  # Backwards compatible alias keys
                "post_date": post_date,
                "value_date": value_date or post_date,
                "narration": final_narration,  # 🟢 Used by new model configurations
                "narration_description": final_narration,  # 🟢 Used by your old reconciliation logs
                "type": "-",
                "tran_type": "-",  # Alias fallback
                "cheque_ref": "-",
                "debit": debit if debit else "-",
                "credit": credit if credit else "-",
                "balance": balance if balance else "-",
                "page_idx": final_page_idx,
            }
        )
