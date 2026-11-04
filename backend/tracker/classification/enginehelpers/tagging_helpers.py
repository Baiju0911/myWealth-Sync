from __future__ import annotations
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from django.apps import apps
from tracker.constants import (
    ACTION_AND_RAIL_NOISE,
    CORPORATE_NOISE_SUFFIXES,
    KNOWN_MERCHANTS,
    NOISE_KEYWORD_BLACKLIST,
    OK_WORD_LIST,
    RULE_SAFETY_BLACKLIST,
    TRANSFER_BANK_NOISE,
    UPI_RAIL_TOKENS,
    TokenCatalog,
)
from .confidence_helpers import ConfidenceScorer

_CBS_SESSION_REGEX = re.compile(r"\b[A-Z]\d{6,10}\b", re.IGNORECASE)
_NUMERIC_ID_REGEX = re.compile(r"\b\d{4,}\b")
_VPA_REGEX = re.compile(r"([A-Z0-9.\-_]+)@([A-Z]+)", re.IGNORECASE)
_RRN_12_REGEX = re.compile(r"\b(\d{12})\b")
_UTR_REGEX = re.compile(r"\b([A-Z]{4}[A-Z0-9]{12,18})\b")
_HONORIFICS_REGEX = re.compile(
    r"\b(?:OF\s+)?(?:MR|MRS|MS|DR|SHRI|SMT)\.?\s+", re.IGNORECASE
)
_P2A_RAIL_REGEX = re.compile(r"\b(?:P2A|P2P|IMPS/P2A|UPI/P2A)\b", re.IGNORECASE)
_DIRECTION_SUFFIX_REGEX = re.compile(r"\s*\((?:IN|OUT|DR|CR)\)$", re.IGNORECASE)


class TaggingEngine:
    """Dynamic tagging, pairing, and scoring engine without hardcoded account identifiers."""

    @classmethod
    def get_dynamic_accounts_registry(cls) -> List[Dict[str, Any]]:
        Account = apps.get_model("ledger", "Account")
        registry = []
        for acc in Account.objects.exclude(id=99):
            acc_num = str(getattr(acc, "account_number", "") or "").strip()
            acc_name = getattr(acc, "name", None) or getattr(acc, "bank_name", "Bank")
            last4 = acc_num[-4:] if len(acc_num) >= 4 else str(acc.id)

            registry.append(
                {
                    "id": acc.id,
                    "name": acc_name,
                    "full_number": acc_num,
                    "last4": last4,
                    "patterns": [
                        acc_num if len(acc_num) >= 6 else None,
                        f"XX{last4}",
                        f"X{last4}",
                        f"..{last4}",
                        last4 if len(last4) == 4 else None,
                    ],
                }
            )
        return registry

    @classmethod
    def detect_internal_counterpart(
        cls,
        narration: str,
        host_account_id: Optional[int],
        registry: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not narration:
            return None
        upper_narr = narration.upper()
        for acc in registry:
            if host_account_id and acc["id"] == host_account_id:
                continue
            for pat in acc["patterns"]:
                if pat and pat.upper() in upper_narr:
                    return acc
        return None

    @classmethod
    def repair_narration_kerning(cls, raw_text: str) -> str:
        if not raw_text:
            return ""
        text = re.sub(r"\s+", " ", str(raw_text)).strip()
        text = re.sub(r"\bOW\s+NACCOUNT\b", "OWN ACCOUNT", text, flags=re.IGNORECASE)
        text = re.sub(r"\bNR\s+I\s+BRANCH\b", "NRI BRANCH", text, flags=re.IGNORECASE)
        text = _HONORIFICS_REGEX.sub(" ", text)
        text = _P2A_RAIL_REGEX.sub(" ", text)
        text = _DIRECTION_SUFFIX_REGEX.sub("", text)
        return re.sub(r"\s+", " ", text).strip().upper()

    @classmethod
    def extract_rail_reference(cls, narration: str) -> Optional[str]:
        if not narration:
            return None
        m_rrn = _RRN_12_REGEX.search(narration)
        if m_rrn:
            return m_rrn.group(1)
        m_utr = _UTR_REGEX.search(narration)
        if m_utr:
            return m_utr.group(1)
        return None

    @classmethod
    def extract_meaningful_tokens(cls, text: str) -> List[str]:
        if not text:
            return []
        cleaned = cls.repair_narration_kerning(text)
        filtered_tokens = []
        for token in cleaned.split():
            if token in NOISE_KEYWORD_BLACKLIST or token in RULE_SAFETY_BLACKLIST:
                continue
            if token.isdigit() or len(token) > 20:
                continue
            if re.search(r"[A-Z]", token) and re.search(r"[0-9]", token):
                continue
            if token in ACTION_AND_RAIL_NOISE:
                continue
            filtered_tokens.append(token)
        return filtered_tokens

    @classmethod
    def extract_clean_payee_pattern(cls, narration: str) -> str:
        if not narration:
            return ""
        tokens = cls.extract_meaningful_tokens(narration)
        if not tokens:
            return ""
        for t in tokens:
            if t in KNOWN_MERCHANTS:
                return t
        clean_tokens = tokens[:2] if len(tokens) >= 2 else tokens
        return " ".join(clean_tokens).upper()

    @classmethod
    def generate_canonical_cluster_tag(
        cls,
        raw_narration: str,
        payee: Optional[str] = None,
        host_account_id: Optional[int] = None,
        registry: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, str, float, str, bool]:
        """
        Returns:
            (pattern_tag, canonical_title, confidence_score, confidence_label, ok_to_classify)
        """
        cleaned_narr = cls.repair_narration_kerning(raw_narration or "")
        acc_registry = (
            registry if registry is not None else cls.get_dynamic_accounts_registry()
        )
        ref_id = cls.extract_rail_reference(cleaned_narr)
        has_ref = bool(ref_id)

        # 1. Unilateral Internal Account Match
        internal_match = cls.detect_internal_counterpart(
            cleaned_narr, host_account_id, acc_registry
        )
        if internal_match:
            dest_name = internal_match["name"].upper()
            score, label, ok = ConfidenceScorer.evaluate(
                is_unilateral_internal=True,
                has_ref_proof=has_ref,
                has_clean_tokens=True,
            )
            return "#SELF_TRANSFER", f"TRANSFER TO {dest_name}", score, label, ok

        if "OWN ACCOUNT" in cleaned_narr or "SELF TRANSFER" in cleaned_narr:
            score, label, ok = ConfidenceScorer.evaluate(
                is_unilateral_internal=True,
                has_ref_proof=has_ref,
                has_clean_tokens=True,
            )
            return "#SELF_TRANSFER", "OWN ACCOUNT TRANSFER", score, label, ok

        # 2. Clean Payee / Merchant Extract
        source_name = payee or cleaned_narr
        clean_merchant = cls.extract_clean_payee_pattern(source_name)
        if clean_merchant:
            is_known = clean_merchant in KNOWN_MERCHANTS
            tokens = clean_merchant.split()
            tag_slug = "_".join(tokens[:2])
            score, label, ok = ConfidenceScorer.evaluate(
                has_known_merchant=is_known,
                has_ref_proof=has_ref,
                has_clean_tokens=True,
            )
            return f"#{tag_slug}", clean_merchant, score, label, ok

        # 3. Reference Fallback
        if ref_id:
            score, label, ok = ConfidenceScorer.evaluate(
                has_ref_proof=True,
                has_clean_tokens=False,
            )
            return f"#REF_{ref_id}", f"REF: {ref_id}", score, label, ok

        # 4. Absolute Fallback
        return "#UNRESOLVED_LINE", "UNRESOLVED SUSPENSE ITEM", 0.10, "LOW", False
