from __future__ import annotations
import re
from typing import Any, Dict, Optional


class UniversalNarrationExtractor:
    """
    Dual-mode narration engine:
    - Mode A (Slash-Delimited): SIB MOB/IMPS, NEFT wires, ICICI CMS.
    - Mode B (Space-Delimited / Free-Form): POS swipes, ATMs, CBS internal transfers.
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

    SIB_CHANNEL_TAGS = {
        "FRIENDS",
        "TRADING",
        "EXPENSES",
        "FAMILY",
        "SELF",
        "BILL PAYMENT",
        "TRANSFER",
        "INVESTMENT",
        "PERSONAL",
    }

    PROTECTED_TOKENS = {
        "IN",
        "AT",
        "TO",
        "OF",
        "BY",
        "FOR",
        "ON",
        "OR",
        "NO",
        "A",
        "AN",
        "THE",
        "NRI",
        "NRE",
        "NRO",
        "MOB",
        "ATM",
        "POS",
        "TRN",
        "WDL",
        "DEP",
        "TFR",
        "MBS",
    }

    @classmethod
    def clean_boilerplate_header(cls, text: str) -> str:
        if not text:
            return ""
        cleaned = text.strip()
        if cls.INFO_PREFIX_PATTERN.search(cleaned):
            cleaned = cls.INFO_PREFIX_PATTERN.sub("", cleaned).strip()
        elif cls.BOILERPLATE_PATTERN.match(cleaned):
            cleaned = cls.BOILERPLATE_PATTERN.sub("", cleaned).strip()
        return cls.repair_segment_kerning(cleaned)

    @classmethod
    def is_statement_or_notice(cls, text: str) -> bool:
        if not text:
            return False
        return bool(cls.STATEMENT_NOTICE_PATTERN.search(text))

    @classmethod
    def repair_kerning_and_splits(cls, text: str) -> str:
        """Compatibility alias for existing engine callers."""
        return cls.repair_segment_kerning(text)

    @classmethod
    def repair_segment_kerning(cls, segment: str) -> str:
        if not segment:
            return ""

        s = re.sub(r"\s+", " ", str(segment)).strip().upper()

        s = re.sub(r"\bN\s+RI\b", "NRI", s)
        s = re.sub(r"\bOW\s+N\s*ACCOUNT\b", "OWN ACCOUNT", s)

        prev = None
        while prev != s:
            prev = s
            s = re.sub(r"\b([A-Z0-9])\s+([A-Z0-9])\s+([A-Z0-9])\b", r"\1\2\3", s)

        words = s.split()
        if not words:
            return ""

        merged = []
        i = 0
        n = len(words)

        while i < n:
            curr = words[i]

            if i + 1 < n:
                nxt = words[i + 1]

                if nxt in cls.PROTECTED_TOKENS:
                    merged.append(curr)
                    i += 1
                    continue

                if i + 1 == n - 1 and len(nxt) == 1 and nxt.isalpha():
                    merged.append(curr)
                    i += 1
                    continue

                if curr.isalpha() and nxt.isdigit():
                    merged.append(curr)
                    i += 1
                    continue

                if (
                    len(curr) <= 2
                    and curr.isalpha()
                    and len(nxt) >= 3
                    and nxt.isalpha()
                ):
                    merged.append(curr + nxt)
                    i += 2
                    continue

                if (
                    len(curr) >= 3
                    and curr.isalpha()
                    and len(nxt) <= 2
                    and nxt.isalpha()
                ):
                    if len(nxt) == 1 and i + 1 < n - 1:
                        merged.append(curr + nxt)
                        i += 2
                        continue
                    elif len(nxt) == 2 and nxt not in cls.PROTECTED_TOKENS:
                        merged.append(curr + nxt)
                        i += 2
                        continue

            merged.append(curr)
            i += 1

        return " ".join(merged).strip()

    @classmethod
    def repair_kerning_and_splits(cls, text: str) -> str:
        """Compatibility alias for existing engine callers."""
        return cls.repair_segment_kerning(text)

    @classmethod
    def decompose_raw_narration(cls, text: str) -> Dict[str, Any]:
        if not text:
            return {
                "rail": "UNKNOWN",
                "channel": None,
                "bank_code": None,
                "reference": None,
                "raw_payee": None,
                "raw_remark": None,
                "bank_purpose": None,
                "branch_location": None,
                "raw_segments": [],
            }

        raw_str = text.strip()
        has_slashes = (
            "/" in raw_str and len([p for p in raw_str.split("/") if p.strip()]) >= 2
        )

        if has_slashes:
            return cls._decompose_slash_delimited(raw_str)
        else:
            return cls._decompose_free_form_spaces(raw_str)

    @classmethod
    def _decompose_slash_delimited(cls, clean_text: str) -> Dict[str, Any]:
        clean_text = re.sub(r"/+$", "", clean_text.strip())
        raw_parts = [p.strip() for p in clean_text.split("/") if p.strip()]
        parts = [cls.repair_segment_kerning(p) for p in raw_parts]

        if "/NEFT:" in clean_text.upper() or "/RTGS:" in clean_text.upper():
            ref_no = parts[0] if len(parts) > 0 else None
            ifsc_code = parts[1] if len(parts) > 1 else None

            remitter = None
            rail_type = "NEFT"
            for p in raw_parts:
                m = re.match(r"^(?:NEFT|RTGS):\s*(.+)$", p, flags=re.IGNORECASE)
                if m:
                    remitter = cls.repair_segment_kerning(m.group(1)).upper()
                    rail_type = "RTGS" if "RTGS" in p.upper() else "NEFT"
                    break

            desk = parts[3] if len(parts) > 3 else "CENTRAL CLEARING"
            bank_label = (
                "ICICI BANK"
                if ifsc_code and ifsc_code.startswith("ICIC")
                else (ifsc_code or "CLEARING")
            )

            return {
                "rail": rail_type,
                "channel": "CLEARING_WIRE",
                "bank_code": bank_label,
                "reference": ref_no,
                "raw_payee": remitter or bank_label,
                "raw_remark": f"{bank_label} • {desk}",
                "bank_purpose": "INWARD_REMITTANCE",
                "branch_location": desk,
                "raw_segments": raw_parts,
            }

        upper_text = clean_text.upper()
        if re.search(r"(?:^|/)\s*MOB(?:\s*[/]|$)", upper_text):
            ref_no = None
            if parts and (
                re.match(r"^\d{6,22}$", parts[0]) or parts[0].startswith("100000")
            ):
                ref_no = parts.pop(0)

            tokens = [p for p in parts if p.upper() not in ["MOB", "IMPS"]]

            purpose_tag = None
            counterparty = None
            branch_location = None

            if len(tokens) >= 3:
                purpose_tag = tokens[0]
                counterparty = tokens[1]
                branch_location = tokens[2]
            elif len(tokens) == 2:
                if tokens[0].upper() in cls.SIB_CHANNEL_TAGS:
                    purpose_tag = tokens[0]
                    counterparty = tokens[1]
                else:
                    counterparty = tokens[0]
                    branch_location = tokens[1]
            elif len(tokens) == 1:
                counterparty = tokens[0]
            else:
                counterparty = "UNKNOWN"

            remark_elements = ["MOB_PAYMENT"]
            if purpose_tag:
                remark_elements.append(f"Purpose: {purpose_tag}")
            if branch_location:
                remark_elements.append(branch_location)

            return {
                "rail": "IMPS/MOB",
                "channel": "MOB_PAYMENT",
                "bank_code": "SIB",
                "reference": ref_no,
                "raw_payee": re.sub(r"\s+", " ", str(counterparty or "UNKNOWN"))
                .strip()
                .upper(),
                "raw_remark": " • ".join(remark_elements),
                "bank_purpose": purpose_tag,
                "branch_location": branch_location,
                "raw_segments": raw_parts,
            }

        return {
            "rail": cls._detect_rail(clean_text),
            "channel": "CBS_DELIMITED",
            "bank_code": None,
            "reference": None,
            "raw_payee": parts[0].upper() if parts else clean_text,
            "raw_remark": " / ".join(parts[1:]) if len(parts) > 1 else None,
            "bank_purpose": None,
            "branch_location": None,
            "raw_segments": raw_parts,
        }

    @classmethod
    def _decompose_free_form_spaces(cls, text: str) -> Dict[str, Any]:
        cleaned = cls.repair_segment_kerning(text)
        rail = cls._detect_rail(cleaned)

        m_rrn = cls.RRN_PATTERN.search(cleaned) or re.search(r"\b(\d{12})\b", cleaned)
        reference = (
            m_rrn.group(1)
            if (m_rrn and m_rrn.lastindex)
            else (m_rrn.group(0) if m_rrn else None)
        )

        upper_text = cleaned.upper()
        if any(
            marker in upper_text
            for marker in ["INB", "MBS", "WDL TFR", "DEP TFR", "SELF"]
        ):
            return {
                "rail": "CBS_TRANSFER",
                "channel": "BRANCH_CBS",
                "bank_code": "INTERNAL",
                "reference": reference,
                "raw_payee": cleaned,
                "raw_remark": "Internal Book Transfer",
                "bank_purpose": "SELF_TRANSFER",
                "branch_location": "BRANCH",
                "raw_segments": cleaned.split(),
            }

        raw_tokens = cleaned.split()
        meaningful_tokens = [
            t
            for t in raw_tokens
            if t
            not in ["ATM", "POS", "TRN", "WDL", "DEP", "TFR", "IN", "OUT", "DR", "CR"]
            and not t.isdigit()
        ]

        payee = " ".join(meaningful_tokens[:3]) if meaningful_tokens else cleaned

        return {
            "rail": rail,
            "channel": "FREE_FORM",
            "bank_code": None,
            "reference": reference,
            "raw_payee": payee.upper(),
            "raw_remark": cleaned,
            "bank_purpose": None,
            "branch_location": None,
            "raw_segments": raw_tokens,
        }

    @classmethod
    def resolve_from_staging_line(cls, line: Any) -> Dict[str, Any]:
        """
        Integrates dynamic staging line fields, live telemetry alerts,
        and dual-mode parsed narration for ledger models.
        """
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
        if cheque_ref and not parsed_tokens.get("reference"):
            parsed_tokens["reference"] = str(cheque_ref).strip()

        raw_payee = parsed_tokens.get("raw_payee")
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
        elif parsed_tokens.get("raw_remark"):
            context_parts.append(parsed_tokens["raw_remark"])

        final_remark = " • ".join(context_parts) if context_parts else None

        return {
            "raw_statement_narration": raw_statement_narration,
            "statement_amount": (
                float(line.amount) if getattr(line, "amount", None) is not None else 0.0
            ),
            "raw_segments": parsed_tokens.get("raw_segments", []),
            "detected_rail": parsed_tokens.get("rail", "BANK_TRANSFER"),
            "detected_bank_code": parsed_tokens.get("bank_code"),
            "detected_reference": parsed_tokens.get("reference") or live_rrn,
            "statement_payee_raw": parsed_tokens.get("raw_payee"),
            "statement_remark_raw": parsed_tokens.get("raw_remark"),
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
