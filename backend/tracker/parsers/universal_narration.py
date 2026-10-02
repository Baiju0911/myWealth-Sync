import re
from typing import Any, Dict, Optional


class UniversalNarrationExtractor:
    """
    100% additive narration engine.
    Retains the exact bank statement narration untouched while layering
    full protocol decomposition and live alert stream telemetry.
    """

    RRN_PATTERN = re.compile(r"^(?:RRN|REF|UTR)?\s*[:.-]?\s*(\d{8,18})$", re.IGNORECASE)
    BANK_CODE_PATTERN = re.compile(r"^[A-Z]{3,5}$")

    @classmethod
    def resolve_from_staging_line(cls, line: Any) -> Dict[str, Any]:
        """
        Takes a StatementStagingLine and returns the authentic bank statement
        narration verbatim, enriched with decomposed segments and live stream data.
        """
        # 1. Authentic Statement String (Zero Modification)
        raw_statement_narration = getattr(line, "narration", "") or ""

        # 2. Decompose Raw Statement Segments (Additive Only)
        parsed_tokens = cls.decompose_raw_narration(raw_statement_narration)

        # 3. Pull Live Alert Enrichment Telemetry from live_metadata
        meta = getattr(line, "live_metadata", None)
        if not isinstance(meta, dict):
            meta = {}

        live_merchant = meta.get("merchant") or meta.get("clean_merchant")
        live_remark = meta.get("remark") or meta.get("clean_remark")
        live_rrn = getattr(line, "live_upi_rrn", None) or meta.get("live_upi_rrn")
        live_source = meta.get("source")
        matched_tier = meta.get("matched_tier")
        has_amount_discrepancy = meta.get("has_amount_discrepancy", False)
        discrepancy_details = meta.get("discrepancy_details")

        # 4. Check Cheque Reference Fallback
        cheque_ref = getattr(line, "cheque_ref_number", None)
        if cheque_ref and not parsed_tokens["reference"]:
            parsed_tokens["reference"] = str(cheque_ref).strip()

        return {
            # === AUTHENTIC BANK DATA (UNTOUCHED) ===
            "raw_statement_narration": raw_statement_narration,
            "statement_amount": (
                float(line.amount) if getattr(line, "amount", None) is not None else 0.0
            ),
            "raw_segments": parsed_tokens["raw_segments"],
            "detected_rail": parsed_tokens["rail"],
            "detected_bank_code": parsed_tokens["bank_code"],
            "detected_reference": parsed_tokens["reference"],
            "statement_payee_raw": parsed_tokens["raw_payee"],
            "statement_remark_raw": parsed_tokens["raw_remark"],
            # === LIVE STREAM ENRICHMENT TELEMETRY ===
            "is_enriched_from_live": bool(getattr(line, "is_enriched_from_live", 0)),
            "live_source": live_source,
            "live_rrn": live_rrn,
            "live_payee": live_merchant,
            "live_remark": live_remark,
            "matched_tier": matched_tier,
            "has_amount_discrepancy": has_amount_discrepancy,
            "discrepancy_details": discrepancy_details,
            # === UNIFIED SUGGESTIONS (FOR DESK & RULES) ===
            "suggested_payee": live_merchant
            or parsed_tokens["raw_payee"]
            or raw_statement_narration,
            "suggested_remark": live_remark or parsed_tokens["raw_remark"],
        }

    @classmethod
    def decompose_raw_narration(cls, text: str) -> Dict[str, Any]:
        """
        Splits slash or MOB protocols without dropping or modifying tokens.
        """
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

        # Handle MOB / Bill Payment pattern: MOB/<REF>/Bill Payment/<PAYEE>
        mob_match = re.search(
            r"MOB/(?:(\d{6,18})/)?(?:Bill\s*Payment/)?([^/]+)(?:/(.*))?$",
            text,
            re.IGNORECASE,
        )
        if mob_match:
            ref = mob_match.group(1)
            p1 = mob_match.group(2)
            p2 = mob_match.group(3)
            return {
                "rail": "MOB/IMPS",
                "bank_code": None,
                "reference": ref,
                "raw_payee": p1,
                "raw_remark": p2 or "Bill Payment",
                "raw_segments": [s for s in [ref, p1, p2] if s],
            }

        # Slash-delimited protocols (UPI, IMPS, NEFT)
        segments = [s.strip() for s in text.split("/") if s.strip()]
        bank_code = None
        reference = None
        raw_payee = None
        raw_remark = None

        if len(segments) >= 2:
            remaining = []
            for seg in segments[1:]:
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
                raw_payee = remaining[0]
            if len(remaining) >= 2:
                raw_remark = " / ".join(remaining[1:])
        else:
            raw_payee = text

        return {
            "rail": rail,
            "bank_code": bank_code,
            "reference": reference,
            "raw_payee": raw_payee,
            "raw_remark": raw_remark,
            "raw_segments": segments,
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
