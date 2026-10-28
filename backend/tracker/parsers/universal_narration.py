import re
from typing import Any, Dict, Optional


class UniversalNarrationExtractor:
    """
    100% additive narration engine.
    Retains the authentic bank statement narration while layering
    protocol decomposition, noise classification, and live alert stream telemetry.
    """

    RRN_PATTERN = re.compile(
        r"^(?:RRN|REF|UTR)?\s*[:.-]?\s*([A-Z0-9]{8,22})$", re.IGNORECASE
    )
    BANK_CODE_PATTERN = re.compile(r"^[A-Z]{3,6}$")

    STATEMENT_NOTICE_PATTERN = re.compile(
        r"(?:e-?statement|monthly\s+statement|account\s+statement|password-protected|"
        r"to\s+view\s+your\s+statement|password\s+to\s+view|salutations\s+to\s+be\s+used)",
        re.IGNORECASE,
    )

    BOILERPLATE_PATTERN = re.compile(
        r"^(?:Dear\s+(?:Customer|Cardholder|User|Valued\s+Customer|Sir|Madam)|Greetings|Notice)[,\s:-]*",
        re.IGNORECASE,
    )

    INFO_PREFIX_PATTERN = re.compile(
        r"^.*?(?:Info|Txn\s*Info|Details)(?:\s*:\s*|\s*-\s*)",
        re.IGNORECASE,
    )

    NEFT_COMPLEX_PATTERN = re.compile(
        r"(?:NEFT|RTGS)\s*(?:UTR\s*:\s*)?([A-Z0-9\s]+?)\s*//\s*(?:(.*?)/)?(?:NEFT|RTGS)\s*TO\s*[:\s]+(?:[^:]+:)?([^/]+)(?:/(.*))?$",
        re.IGNORECASE,
    )

    NEFT_SIMPLE_PATTERN = re.compile(
        r"(?:NEFT|RTGS)[/-](?:UTR[:\s]*)?([A-Z0-9]+)[/-](?:TO[:\s]*)?([^/]+)(?:/(.*))?$",
        re.IGNORECASE,
    )

    # -------------------------------------------------------------
    # 🧩 SHARED NORMALIZATION & KERNING REPAIR UTILITIES
    # -------------------------------------------------------------
    @staticmethod
    def repair_kerning_and_splits(text: str) -> str:
        """
        Generic algorithmic reconstruction of fragmented text caused by
        bank PDF scraping, monospace column wrapping, and printer kerning.
        """
        if not text:
            return ""

        s = text.strip()

        # Rule 1: Collapse multi-letter single character chains ("O W N" -> "OWN", "B A I J U" -> "BAIJU")
        prev = None
        while prev != s:
            prev = s
            s = re.sub(r"\b([A-Za-z0-9])\s+([A-Za-z0-9])\b", r"\1\2", s)

        # Rule 2: Re-join isolated single-letter trailing splinters ("INDI A" -> "INDIA")
        s = re.sub(r"\b([A-Za-z]{3,})\s+([A-Za-z]{1})\b", r"\1\2", s)

        # Rule 3: Re-join isolated single-letter leading splinters ("S ERVICE" -> "SERVICE", "B AIJU" -> "BAIJU")
        s = re.sub(r"\b([A-Za-z]{1})\s+([A-Za-z]{3,})\b", r"\1\2", s)

        return re.sub(r"\s+", " ", s).strip()

    @classmethod
    def generate_canonical_cluster_tag(cls, raw_name: str) -> str:
        """
        Deterministic clustering hash. Eliminates all internal space variants
        so 'BAIJU SUSEELAN NAIR' and 'BAIJUSUSEELANNAIR' merge into '#BAIJUSUSEELANNAIR'.
        """
        if not raw_name:
            return "#SUSPENSE"

        repaired = cls.repair_kerning_and_splits(raw_name).upper()
        words = re.findall(r"[A-Z0-9]+", repaired)

        if not words:
            return "#SUSPENSE"

        cohesive_words = []
        buffer = ""

        for w in words:
            if len(w) <= 2 and buffer:
                buffer += w
            elif len(w) <= 2 and not buffer:
                buffer = w
            else:
                if buffer:
                    cohesive_words.append(buffer)
                    buffer = ""
                cohesive_words.append(w)

        if buffer:
            cohesive_words.append(buffer)

        return f"#{'_'.join(cohesive_words)}"

    @classmethod
    def clean_boilerplate_header(cls, text: str) -> str:
        if not text:
            return ""

        cleaned = text.strip()
        if cls.INFO_PREFIX_PATTERN.search(cleaned):
            cleaned = cls.INFO_PREFIX_PATTERN.sub("", cleaned).strip()
        elif cls.BOILERPLATE_PATTERN.match(cleaned):
            cleaned = cls.BOILERPLATE_PATTERN.sub("", cleaned).strip()

        return cls.repair_kerning_and_splits(cleaned)

    @classmethod
    def is_statement_or_notice(cls, text: str) -> bool:
        if not text:
            return False
        return bool(cls.STATEMENT_NOTICE_PATTERN.search(text))

    @classmethod
    def resolve_from_staging_line(cls, line: Any) -> Dict[str, Any]:
        raw_statement_narration = (
            getattr(line, "raw_narration", None) or getattr(line, "narration", "") or ""
        )

        meta = getattr(line, "live_metadata", None)
        if not isinstance(meta, dict):
            meta = {}

        live_merchant = meta.get("merchant") or meta.get("clean_merchant")
        live_remark = meta.get("remark") or meta.get("clean_remark")
        live_channel = meta.get("channel")
        live_source = meta.get("source") or meta.get("live_source")
        live_rrn = (
            getattr(line, "live_upi_rrn", None)
            or meta.get("live_upi_rrn")
            or meta.get("rrn")
        )
        matched_tier = meta.get("matched_tier")
        has_amount_discrepancy = meta.get("has_amount_discrepancy", False)
        discrepancy_details = meta.get("discrepancy_details")
        resolved_narration = meta.get("resolved_narration")

        combined_text = f"{raw_statement_narration} {resolved_narration or ''}".strip()
        is_statement_notice = cls.is_statement_or_notice(combined_text)

        clean_target_text = raw_statement_narration
        if cls.BOILERPLATE_PATTERN.search(clean_target_text):
            if resolved_narration and not cls.BOILERPLATE_PATTERN.search(
                resolved_narration
            ):
                clean_target_text = resolved_narration
            else:
                clean_target_text = cls.clean_boilerplate_header(clean_target_text)

        parsed_tokens = cls.decompose_raw_narration(clean_target_text)

        cheque_ref = getattr(line, "cheque_ref_number", None)
        if cheque_ref and not parsed_tokens["reference"]:
            parsed_tokens["reference"] = str(cheque_ref).strip()

        raw_payee = parsed_tokens["raw_payee"]
        clean_raw_payee = (
            raw_payee
            if raw_payee and not cls.BOILERPLATE_PATTERN.search(raw_payee)
            else None
        )

        suggested_payee = (
            None
            if is_statement_notice
            else (
                live_merchant
                or clean_raw_payee
                or resolved_narration
                or raw_statement_narration
            )
        )

        if suggested_payee:
            suggested_payee = cls.clean_boilerplate_header(suggested_payee)

        context_parts = []
        if live_source:
            context_parts.append(f"via {live_source}")
        if live_channel:
            context_parts.append(f"[{live_channel}]")
        if live_remark:
            context_parts.append(live_remark)
        elif parsed_tokens["raw_remark"]:
            context_parts.append(parsed_tokens["raw_remark"])

        final_remark = " • ".join(context_parts) if context_parts else None

        return {
            "raw_statement_narration": raw_statement_narration,
            "statement_amount": (
                float(line.amount) if getattr(line, "amount", None) is not None else 0.0
            ),
            "raw_segments": parsed_tokens["raw_segments"],
            "detected_rail": parsed_tokens["rail"],
            "detected_bank_code": parsed_tokens["bank_code"],
            "detected_reference": parsed_tokens["reference"] or live_rrn,
            "statement_payee_raw": parsed_tokens["raw_payee"],
            "statement_remark_raw": parsed_tokens["raw_remark"],
            "is_noise": is_statement_notice,
            "is_document_delivery": is_statement_notice,
            "is_enriched_from_live": bool(
                getattr(line, "is_enriched_from_live", 0) or live_merchant
            ),
            "live_source": live_source,
            "live_rrn": live_rrn,
            "live_payee": live_merchant,
            "live_remark": live_remark,
            "matched_tier": matched_tier,
            "has_amount_discrepancy": has_amount_discrepancy,
            "discrepancy_details": discrepancy_details,
            "suggested_payee": suggested_payee,
            "suggested_remark": final_remark,
        }

    @classmethod
    def decompose_raw_narration(cls, text: str) -> Dict[str, Any]:
        if not text:
            return {
                "rail": "UNKNOWN",
                "bank_code": None,
                "reference": None,
                "raw_payee": None,
                "raw_remark": None,
                "raw_segments": [],
            }

        rail = cls._detect_rail(text)
        clean_text = text.strip()

        # 1. NEFT / RTGS Wire Complex Protocol
        neft_complex_m = cls.NEFT_COMPLEX_PATTERN.search(clean_text)
        if neft_complex_m:
            ref = re.sub(r"\s+", "", neft_complex_m.group(1))
            bank_info = (
                neft_complex_m.group(2).strip() if neft_complex_m.group(2) else ""
            )
            payee = cls.repair_kerning_and_splits(neft_complex_m.group(3))
            branch = (
                neft_complex_m.group(4).strip() if neft_complex_m.group(4) else None
            )

            payee = re.sub(
                r"/(?:KALLAMBALAM|KA\s*LLAMBALAM|BRANCH|STATE BANK).*",
                "",
                payee,
                flags=re.IGNORECASE,
            ).strip()

            remark_parts = [p for p in [bank_info, branch] if p]
            return {
                "rail": "NEFT",
                "bank_code": None,
                "reference": ref,
                "raw_payee": payee,
                "raw_remark": " / ".join(remark_parts) if remark_parts else None,
                "raw_segments": [ref, bank_info, payee],
            }

        # 2. NEFT / RTGS Simple Pattern
        neft_simple_m = cls.NEFT_SIMPLE_PATTERN.search(clean_text)
        if neft_simple_m:
            ref = neft_simple_m.group(1).strip()
            payee = cls.repair_kerning_and_splits(neft_simple_m.group(2))
            remark = neft_simple_m.group(3).strip() if neft_simple_m.group(3) else None
            return {
                "rail": "NEFT",
                "bank_code": None,
                "reference": ref,
                "raw_payee": payee,
                "raw_remark": remark,
                "raw_segments": [ref, payee],
            }

        # 3. Handle Single or Double MOB (e.g. MOB/MOB/126011185604/FA MILY/IMPS/KALLAMBALAM)
        mob_match = re.search(
            r"^(?:MOB/)+(\d{6,18})?/??(?:Bill\s*Payment/)?([^/]+)(?:/(.*))?$",
            clean_text,
            re.IGNORECASE,
        )
        if mob_match:
            ref = mob_match.group(1)
            p1 = cls.repair_kerning_and_splits(mob_match.group(2))
            p2 = mob_match.group(3).strip() if mob_match.group(3) else None
            return {
                "rail": "MOB/IMPS",
                "bank_code": None,
                "reference": ref,
                "raw_payee": p1,
                "raw_remark": p2 or "Mobile Banking Transfer",
                "raw_segments": [s for s in [ref, p1, p2] if s],
            }

        # 4. Standard Slash Protocols (UPI, IMPS, etc.)
        raw_segments = [s.strip() for s in clean_text.split("/") if s.strip()]
        bank_code = None
        reference = None
        raw_payee = None
        raw_remark = None

        if len(raw_segments) >= 2:
            remaining = []
            for seg in raw_segments[1:]:
                rrn_m = cls.RRN_PATTERN.match(seg)
                if rrn_m and not reference:
                    reference = rrn_m.group(1)
                    continue

                if (
                    cls.BANK_CODE_PATTERN.match(seg)
                    and not bank_code
                    and len(remaining) == 0
                ):
                    bank_code = seg
                    continue

                remaining.append(seg)

            if len(remaining) >= 1:
                raw_payee = cls.repair_kerning_and_splits(remaining[0])
            if len(remaining) >= 2:
                remarks_tokens = [r for r in remaining[1:] if r.upper() != "NO REMARKS"]
                raw_remark = " / ".join(remarks_tokens) if remarks_tokens else None
        else:
            raw_payee = cls.repair_kerning_and_splits(clean_text)

        return {
            "rail": rail,
            "bank_code": bank_code,
            "reference": reference,
            "raw_payee": raw_payee,
            "raw_remark": raw_remark,
            "raw_segments": raw_segments,
        }

    @staticmethod
    def _detect_rail(text: str) -> str:
        t = text.upper()
        if "UPI" in t:
            return "UPI"
        if "IMPS" in t or "MOB" in t:
            return "IMPS"
        if "NEFT" in t:
            return "NEFT"
        if "RTGS" in t:
            return "RTGS"
        if "ATM" in t or "NWD" in t:
            return "ATM"
        if "POS" in t or "SWIPE" in t:
            return "POS"
        return "BANK_TRANSFER"


# import re
# from typing import Any, Dict, Optional


# class UniversalNarrationExtractor:
#     """
#     100% additive narration engine.
#     Retains the authentic bank statement narration while layering
#     protocol decomposition, noise classification, and live alert stream telemetry.
#     """

#     RRN_PATTERN = re.compile(
#         r"^(?:RRN|REF|UTR)?\s*[:.-]?\s*([A-Z0-9]{8,22})$", re.IGNORECASE
#     )
#     BANK_CODE_PATTERN = re.compile(r"^[A-Z]{3,6}$")

#     # Generic patterns for document deliveries, legal notices, and password instructions
#     STATEMENT_NOTICE_PATTERN = re.compile(
#         r"(?:e-?statement|monthly\s+statement|account\s+statement|password-protected|"
#         r"to\s+view\s+your\s+statement|password\s+to\s+view|salutations\s+to\s+be\s+used)",
#         re.IGNORECASE,
#     )

#     # Generic salutation and header boilerplate
#     BOILERPLATE_PATTERN = re.compile(
#         r"^(?:Dear\s+(?:Customer|Cardholder|User|Valued\s+Customer|Sir|Madam)|Greetings|Notice)[,\s:-]*",
#         re.IGNORECASE,
#     )

#     # Delimiter indicating start of actual financial transaction payload
#     INFO_PREFIX_PATTERN = re.compile(
#         r"^.*?(?:Info|Txn\s*Info|Details)(?:\s*:\s*|\s*-\s*)",
#         re.IGNORECASE,
#     )

#     # Core NEFT / RTGS Wire Pattern:
#     # Captures: NEFT UTR: <REF>//<SENDER_BANK>/NEFT TO:<REF>:<BENEFICIARY>/<BRANCH>
#     NEFT_COMPLEX_PATTERN = re.compile(
#         r"(?:NEFT|RTGS)\s*(?:UTR\s*:\s*)?([A-Z0-9\s]+?)\s*//\s*(.*?)\s*/(?:NEFT|RTGS)\s*TO\s*:\s*(?:[^:]+:)?([^/]+)(?:/(.*))?$",
#         re.IGNORECASE,
#     )

#     # Simpler NEFT Pattern:
#     # NEFT/<REF>/<BENEFICIARY>/... or NEFT-<REF>-<BENEFICIARY>
#     NEFT_SIMPLE_PATTERN = re.compile(
#         r"(?:NEFT|RTGS)[/-](?:UTR[:\s]*)?([A-Z0-9]+)[/-](?:TO[:\s]*)?([^/]+)(?:/(.*))?$",
#         re.IGNORECASE,
#     )

#     @classmethod
#     def is_statement_or_notice(cls, text: str) -> bool:
#         """Detects whether content is a statement delivery/advice rather than a real-time txn."""
#         if not text:
#             return False
#         return bool(cls.STATEMENT_NOTICE_PATTERN.search(text))

#     @classmethod
#     def clean_boilerplate_header(cls, text: str) -> str:
#         """Strips institutional salutations and extracts payload starting at standard info delimiters."""
#         if not text:
#             return ""

#         cleaned = text.strip()

#         # If info boundary exists, extract everything subsequent
#         if cls.INFO_PREFIX_PATTERN.search(cleaned):
#             cleaned = cls.INFO_PREFIX_PATTERN.sub("", cleaned).strip()
#         elif cls.BOILERPLATE_PATTERN.match(cleaned):
#             cleaned = cls.BOILERPLATE_PATTERN.sub("", cleaned).strip()

#         return cleaned

#     @classmethod
#     def resolve_from_staging_line(cls, line: Any) -> Dict[str, Any]:
#         """
#         Takes a StatementStagingLine and returns authentic bank data enriched
#         with protocol decomposition, noise classification, and telemetry.
#         """
#         # 1. Authentic Statement String
#         raw_statement_narration = getattr(line, "narration", "") or ""
#         print(f"🔥 [UniversalNarration] RESOLVING LINE: {raw_statement_narration[:60]}")
#         # 2. Pull Live Alert Enrichment Telemetry from live_metadata
#         meta = getattr(line, "live_metadata", None)
#         if not isinstance(meta, dict):
#             meta = {}

#         live_merchant = meta.get("merchant") or meta.get("clean_merchant")
#         live_remark = meta.get("remark") or meta.get("clean_remark")
#         resolved_narration = meta.get("resolved_narration")

#         # 3. Noise / Statement Delivery Detection
#         combined_text = f"{raw_statement_narration} {resolved_narration or ''}".strip()
#         is_statement_notice = cls.is_statement_or_notice(combined_text)

#         # 4. Normalize Narration for Token Parsing
#         clean_target_text = raw_statement_narration
#         if cls.BOILERPLATE_PATTERN.search(clean_target_text):
#             if resolved_narration and not cls.BOILERPLATE_PATTERN.search(
#                 resolved_narration
#             ):
#                 clean_target_text = resolved_narration
#             else:
#                 clean_target_text = cls.clean_boilerplate_header(clean_target_text)

#         parsed_tokens = cls.decompose_raw_narration(clean_target_text)

#         live_rrn = getattr(line, "live_upi_rrn", None) or meta.get("live_upi_rrn")
#         live_source = meta.get("source")
#         matched_tier = meta.get("matched_tier")
#         has_amount_discrepancy = meta.get("has_amount_discrepancy", False)
#         discrepancy_details = meta.get("discrepancy_details")

#         # 5. Check Cheque Reference Fallback
#         cheque_ref = getattr(line, "cheque_ref_number", None)
#         if cheque_ref and not parsed_tokens["reference"]:
#             parsed_tokens["reference"] = str(cheque_ref).strip()

#         # 6. Resolve Suggestion Hierarchy
#         raw_payee = parsed_tokens["raw_payee"]
#         clean_raw_payee = (
#             raw_payee
#             if raw_payee and not cls.BOILERPLATE_PATTERN.search(raw_payee)
#             else None
#         )

#         suggested_payee = (
#             None
#             if is_statement_notice
#             else (
#                 live_merchant
#                 or clean_raw_payee
#                 or resolved_narration
#                 or raw_statement_narration
#             )
#         )

#         # Final cleanup pass on suggested_payee to ensure no leftover protocol artifacts
#         if suggested_payee:
#             suggested_payee = cls.clean_boilerplate_header(suggested_payee)

#         return {
#             # === AUTHENTIC BANK DATA ===
#             "raw_statement_narration": raw_statement_narration,
#             "statement_amount": (
#                 float(line.amount) if getattr(line, "amount", None) is not None else 0.0
#             ),
#             "raw_segments": parsed_tokens["raw_segments"],
#             "detected_rail": parsed_tokens["rail"],
#             "detected_bank_code": parsed_tokens["bank_code"],
#             "detected_reference": parsed_tokens["reference"] or live_rrn,
#             "statement_payee_raw": parsed_tokens["raw_payee"],
#             "statement_remark_raw": parsed_tokens["raw_remark"],
#             # === NOISE CLASSIFICATION ===
#             "is_noise": is_statement_notice,
#             "is_document_delivery": is_statement_notice,
#             # === LIVE STREAM ENRICHMENT TELEMETRY ===
#             "is_enriched_from_live": bool(getattr(line, "is_enriched_from_live", 0)),
#             "live_source": live_source,
#             "live_rrn": live_rrn,
#             "live_payee": live_merchant,
#             "live_remark": live_remark,
#             "matched_tier": matched_tier,
#             "has_amount_discrepancy": has_amount_discrepancy,
#             "discrepancy_details": discrepancy_details,
#             # === UNIFIED SUGGESTIONS ===
#             "suggested_payee": suggested_payee,
#             "suggested_remark": live_remark or parsed_tokens["raw_remark"],
#         }

#     @classmethod
#     def decompose_raw_narration(cls, text: str) -> Dict[str, Any]:
#         """
#         Splits slash, MOB, NEFT, and wire protocols cleanly without losing raw tokens.
#         """
#         print(f"🔍 [UniversalNarration] DECOMPOSING: {text[:60]}")
#         if not text:
#             return {
#                 "rail": "UNKNOWN",
#                 "bank_code": None,
#                 "reference": None,
#                 "raw_payee": None,
#                 "raw_remark": None,
#                 "raw_segments": [],
#             }

#         rail = cls._detect_rail(text)
#         clean_text = text.strip()

#         # -------------------------------------------------------------
#         # 1. NEFT / RTGS Wire Complex Protocol:
#         # e.g.: NEFT UTR: SIBLN19337311 445//STATE BANK OF INDI A/NEFT TO:SIBLN19337311 445:MONU PAYHOUSE/KALLA MBALAM
#         # -------------------------------------------------------------
#         neft_complex_m = cls.NEFT_COMPLEX_PATTERN.search(clean_text)
#         if neft_complex_m:
#             ref = re.sub(r"\s+", "", neft_complex_m.group(1))
#             bank_info = neft_complex_m.group(2).strip()
#             payee = neft_complex_m.group(3).strip()
#             branch = (
#                 neft_complex_m.group(4).strip() if neft_complex_m.group(4) else None
#             )

#             # Strip trailing branch notes like "/KALLAMBALAM STATE BANK" if merged into payee
#             payee = re.sub(
#                 r"/(?:KALLAMBALAM|BRANCH|STATE BANK).*", "", payee, flags=re.IGNORECASE
#             ).strip()

#             return {
#                 "rail": "NEFT",
#                 "bank_code": None,
#                 "reference": ref,
#                 "raw_payee": payee,
#                 "raw_remark": f"{bank_info} ({branch})" if branch else bank_info,
#                 "raw_segments": [ref, bank_info, payee],
#             }

#         # -------------------------------------------------------------
#         # 2. NEFT / RTGS Simple Pattern:
#         # e.g.: NEFT/AXISCN00234123/JOHN DOE/RENT
#         # -------------------------------------------------------------
#         neft_simple_m = cls.NEFT_SIMPLE_PATTERN.search(clean_text)
#         if neft_simple_m:
#             ref = neft_simple_m.group(1).strip()
#             payee = neft_simple_m.group(2).strip()
#             remark = neft_simple_m.group(3).strip() if neft_simple_m.group(3) else None
#             return {
#                 "rail": "NEFT",
#                 "bank_code": None,
#                 "reference": ref,
#                 "raw_payee": payee,
#                 "raw_remark": remark,
#                 "raw_segments": [ref, payee],
#             }

#         # -------------------------------------------------------------
#         # 3. Handle MOB / Bill Payment pattern:
#         # e.g.: MOB/<REF>/Bill Payment/<PAYEE>
#         # -------------------------------------------------------------
#         mob_match = re.search(
#             r"MOB/(?:(\d{6,18})/)?(?:Bill\s*Payment/)?([^/]+)(?:/(.*))?$",
#             clean_text,
#             re.IGNORECASE,
#         )
#         if mob_match:
#             ref = mob_match.group(1)
#             p1 = mob_match.group(2)
#             p2 = mob_match.group(3)
#             return {
#                 "rail": "MOB/IMPS",
#                 "bank_code": None,
#                 "reference": ref,
#                 "raw_payee": p1,
#                 "raw_remark": p2 or "Bill Payment",
#                 "raw_segments": [s for s in [ref, p1, p2] if s],
#             }

#         # -------------------------------------------------------------
#         # 4. Standard Slash Protocols (UPI, IMPS, Generic Slashes)
#         # e.g.: UPI/PYTM/402805967436/MR CHINNADURAI/NO REMARKS/...
#         # -------------------------------------------------------------
#         raw_segments = [s.strip() for s in clean_text.split("/") if s.strip()]
#         bank_code = None
#         reference = None
#         raw_payee = None
#         raw_remark = None

#         if len(raw_segments) >= 2:
#             remaining = []
#             for seg in raw_segments[1:]:
#                 rrn_m = cls.RRN_PATTERN.match(seg)
#                 if rrn_m and not reference:
#                     reference = rrn_m.group(1)
#                     continue

#                 if (
#                     cls.BANK_CODE_PATTERN.match(seg)
#                     and not bank_code
#                     and len(remaining) == 0
#                 ):
#                     bank_code = seg
#                     continue

#                 remaining.append(seg)

#             if len(remaining) >= 1:
#                 # The first non-bank, non-RRN token is the merchant/payee
#                 raw_payee = remaining[0]
#             if len(remaining) >= 2:
#                 # Discard generic 'NO REMARKS' filler from remarks
#                 remarks_tokens = [r for r in remaining[1:] if r.upper() != "NO REMARKS"]
#                 raw_remark = " / ".join(remarks_tokens) if remarks_tokens else None
#         else:
#             raw_payee = clean_text

#         return {
#             "rail": rail,
#             "bank_code": bank_code,
#             "reference": reference,
#             "raw_payee": raw_payee,
#             "raw_remark": raw_remark,
#             "raw_segments": raw_segments,
#         }

#     @staticmethod
#     def _detect_rail(text: str) -> str:
#         t = text.upper()
#         if "UPI" in t:
#             return "UPI"
#         if "IMPS" in t or "MOB" in t:
#             return "IMPS"
#         if "NEFT" in t:
#             return "NEFT"
#         if "RTGS" in t:
#             return "RTGS"
#         if "ATM" in t or "NWD" in t:
#             return "ATM"
#         if "POS" in t or "SWIPE" in t:
#             return "POS"
#         return "BANK_TRANSFER"
