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
        # Users = apps.get_model("ledger", "User")
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
        """
        Reconstructs fragmented text, eliminates isolated printer splinters,
        and purges trailing direction flags.
        """
        if not raw_text:
            return ""

        s = re.sub(r"\s+", " ", str(raw_text)).strip()

        # 1. Multi-letter single character chains ("O W N" -> "OWN")
        prev = None
        while prev != s:
            prev = s
            s = re.sub(r"\b([A-Za-z0-9])\s+([A-Za-z0-9])\b", r"\1\2", s)

        # 2. Leading splinter repair first ("S USEELAN" -> "SUSEELAN")
        s = re.sub(r"\b([A-Za-z]{1})\s+([A-Za-z]{3,})\b", r"\1\2", s)

        # 3. Trailing splinter repair ("INDI A" -> "INDIA")
        s = re.sub(r"\b([A-Za-z]{3,})\s+([A-Za-z]{1})\b", r"\1\2", s)

        # 4. Standard business phrase canonicals & noise
        s = re.sub(r"\bOW\s+NACCOUNT\b", "OWN ACCOUNT", s, flags=re.IGNORECASE)
        s = re.sub(r"\bNR\s+I\s+BRANCH\b", "NRI BRANCH", s, flags=re.IGNORECASE)
        s = _HONORIFICS_REGEX.sub(" ", s)
        s = _P2A_RAIL_REGEX.sub(" ", s)
        s = _DIRECTION_SUFFIX_REGEX.sub("", s)

        return re.sub(r"\s+", " ", s).strip().upper()

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
        clean_payee = cls.repair_narration_kerning(payee or "")
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
            slug = re.sub(r"[^A-Z0-9]+", "_", dest_name).strip("_")
            return f"#TRANSFER_TO_{slug}", f"TRANSFER TO {dest_name}", score, label, ok

        if "OWN ACCOUNT" in cleaned_narr or "SELF TRANSFER" in cleaned_narr:
            score, label, ok = ConfidenceScorer.evaluate(
                is_unilateral_internal=True,
                has_ref_proof=has_ref,
                has_clean_tokens=True,
            )
            return "#SELF_TRANSFER", "OWN ACCOUNT TRANSFER", score, label, ok

        # 2. Clean Payee / Merchant Extract
        source_name = clean_payee or cleaned_narr
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

    @classmethod
    def resolve_cluster_envelope(
        cls,
        is_contra: bool,
        contra_info: Dict[str, Any],
        raw_narration: str,
        payee: str,
        amount: float,
        ref_no: Optional[str],
        host_account_id: Optional[int],
        acc_registry: List[Dict[str, Any]],
    ) -> Tuple[str, str, str, Optional[str], float, str, bool]:
        """
        Unified router that produces:
            (pattern, canonical_title, display_subgroup, pair_id, score, label, ok_to_classify)
        Keeps engine.py free of presentation and string manipulation logic.
        """

        clean_payee = cls.repair_narration_kerning(payee)

        if is_contra:
            src_name = contra_info.get("from_account_name", "Bank").upper()
            dst_name = contra_info.get("to_account_name", "Bank").upper()
            canonical_title = f"{src_name} ➔ {dst_name}"

            slug_src = re.sub(r"[^A-Z0-9]+", "_", src_name).strip("_")
            slug_dst = re.sub(r"[^A-Z0-9]+", "_", dst_name).strip("_")
            pattern = f"#{slug_src}_TO_{slug_dst}"

            score, label, ok_to_classify = ConfidenceScorer.evaluate(
                is_paired_contra=True,
                has_ref_proof=bool(ref_no),
                has_rule_precedent=True,
            )
            pair_amt = f"{amount:.2f}"
            pair_id = (
                f"PAIR_{min(src_name, dst_name)}_{max(src_name, dst_name)}_{pair_amt}"
            )
            display_subgroup = canonical_title
        else:
            (
                pattern,
                canonical_title,
                score,
                label,
                ok_to_classify,
            ) = cls.generate_canonical_cluster_tag(
                raw_narration=raw_narration,
                payee=clean_payee,
                host_account_id=host_account_id,
                registry=acc_registry,
            )
            pair_id = None
            display_subgroup = clean_payee or canonical_title

        return (
            pattern.upper().strip(),
            canonical_title,
            display_subgroup,
            pair_id,
            score,
            label,
            ok_to_classify,
        )

    @classmethod
    def create_empty_cluster(
        cls,
        pattern: str,
        display_name: str,
        score: float,
        label: str,
        is_contra: bool,
    ) -> Dict[str, Any]:
        """Returns standard structure for cluster dictionary."""
        return {
            "pattern": pattern,
            "display_name": display_name,
            "count": 0,
            "total_amount": 0.0,
            "total_inflow": 0.0,
            "total_outflow": 0.0,
            "confidence_score": score,
            "confidence_label": label,
            "sample_descriptions": [],
            "items": [],
            "transaction_ids": [],
            "is_contra_group": is_contra,
        }


# from __future__ import annotations
# import re
# from typing import Any, Dict, List, Optional, Set, Tuple
# from django.apps import apps
# from tracker.constants import (
#     ACTION_AND_RAIL_NOISE,
#     CORPORATE_NOISE_SUFFIXES,
#     KNOWN_MERCHANTS,
#     NOISE_KEYWORD_BLACKLIST,
#     OK_WORD_LIST,
#     RULE_SAFETY_BLACKLIST,
#     TRANSFER_BANK_NOISE,
#     UPI_RAIL_TOKENS,
#     TokenCatalog,
# )
# from .confidence_helpers import ConfidenceScorer
# from django.contrib.auth import get_user_model

# _CBS_SESSION_REGEX = re.compile(r"\b[A-Z]\d{6,10}\b", re.IGNORECASE)
# _NUMERIC_ID_REGEX = re.compile(r"\b\d{4,}\b")
# _VPA_REGEX = re.compile(r"([A-Z0-9.\-_]+)@([A-Z]+)", re.IGNORECASE)
# _RRN_12_REGEX = re.compile(r"\b(\d{12})\b")
# _UTR_REGEX = re.compile(r"\b([A-Z]{4}[A-Z0-9]{12,18})\b")
# _HONORIFICS_REGEX = re.compile(
#     r"\b(?:OF\s+)?(?:MR|MRS|MS|DR|SHRI|SMT)\.?\s+", re.IGNORECASE
# )
# _P2A_RAIL_REGEX = re.compile(r"\b(?:P2A|P2P|IMPS/P2A|UPI/P2A)\b", re.IGNORECASE)
# _DIRECTION_SUFFIX_REGEX = re.compile(r"\s*\((?:IN|OUT|DR|CR)\)$", re.IGNORECASE)


# class TaggingEngine:
#     """Dynamic tagging, pairing, and scoring engine without hardcoded account identifiers or names."""

#     # @classmethod
#     # def get_dynamic_accounts_registry(cls) -> List[Dict[str, Any]]:
#     #     """
#     #     Dynamically extracts registered accounts, branch numbers, and account-holder
#     #     identities/aliases directly from the database ledger models.
#     #     """
#     #     Account = apps.get_model("ledger", "Account")
#     #     registry = []
#     #     for acc in Account.objects.exclude(id=99):
#     #         acc_num = str(getattr(acc, "account_number", "") or "").strip()
#     #         acc_name = getattr(acc, "name", None) or getattr(acc, "bank_name", "Bank")
#     #         holder_name = str(
#     #             getattr(acc, "holder_name", "")
#     #             or getattr(acc, "account_holder", "")
#     #             or ""
#     #         ).strip()
#     #         last4 = acc_num[-4:] if len(acc_num) >= 4 else str(acc.id)

#     #         registry.append(
#     #             {
#     #                 "id": acc.id,
#     #                 "name": acc_name,
#     #                 "holder_name": holder_name,
#     #                 "full_number": acc_num,
#     #                 "last4": last4,
#     #                 "patterns": [
#     #                     acc_num if len(acc_num) >= 6 else None,
#     #                     f"XX{last4}",
#     #                     f"X{last4}",
#     #                     f"..{last4}",
#     #                     last4 if len(last4) == 4 else None,
#     #                 ],
#     #             }
#     #         )
#     #     return registry

#     @classmethod
#     def get_dynamic_accounts_registry(cls) -> List[Dict[str, Any]]:
#         Account = apps.get_model("ledger", "Account")
#         UserModel = get_user_model()

#         # Discover primary user/owner name dynamically from active admin/users
#         primary_user = (
#             UserModel.objects.filter(is_superuser=True).first()
#             or UserModel.objects.first()
#         )
#         fallback_holder = ""
#         if primary_user:
#             first = getattr(primary_user, "first_name", "") or ""
#             last = getattr(primary_user, "last_name", "") or ""
#             full = f"{first} {last}".strip()
#             fallback_holder = full or getattr(primary_user, "username", "")

#         registry = []
#         for acc in Account.objects.exclude(id=99):
#             acc_num = str(getattr(acc, "account_number", "") or "").strip()
#             acc_name = getattr(acc, "name", None) or getattr(acc, "bank_name", "Bank")

#             raw_holder = str(
#                 getattr(acc, "holder_name", "")
#                 or getattr(acc, "account_holder", "")
#                 or ""
#             ).strip()
#             holder_name = raw_holder or fallback_holder
#             last4 = acc_num[-4:] if len(acc_num) >= 4 else str(acc.id)

#             registry.append(
#                 {
#                     "id": acc.id,
#                     "name": acc_name,
#                     "holder_name": holder_name,
#                     "full_number": acc_num,
#                     "last4": last4,
#                     "patterns": [
#                         acc_num if len(acc_num) >= 6 else None,
#                         f"XX{last4}",
#                         f"X{last4}",
#                         f"..{last4}",
#                         last4 if len(last4) == 4 else None,
#                     ],
#                 }
#             )
#         return registry

#     @classmethod
#     def get_known_identity_tokens(cls, registry: List[Dict[str, Any]]) -> Set[str]:
#         """
#         Extracts distinctive identity tokens from registered account holder names.
#         """
#         tokens = set()
#         for acc in registry:
#             holder = acc.get("holder_name") or ""
#             cleaned = cls.repair_narration_kerning(holder)
#             for part in cleaned.split():
#                 if len(part) >= 4 and part not in NOISE_KEYWORD_BLACKLIST:
#                     tokens.add(part)
#         return tokens

#     @classmethod
#     def detect_internal_counterpart(
#         cls,
#         narration: str,
#         host_account_id: Optional[int],
#         registry: List[Dict[str, Any]],
#     ) -> Optional[Dict[str, Any]]:
#         """Matches transaction strings against account numbers and patterns."""
#         if not narration:
#             return None
#         upper_narr = narration.upper()
#         for acc in registry:
#             if host_account_id and acc["id"] == host_account_id:
#                 continue
#             for pat in acc["patterns"]:
#                 if pat and pat.upper() in upper_narr:
#                     return acc
#         return None

#     @classmethod
#     def repair_narration_kerning(cls, raw_text: str) -> str:
#         """
#         Generic algorithmic reconstruction of fragmented monospace text
#         and stripping of directional annotations.
#         """
#         if not raw_text:
#             return ""

#         s = re.sub(r"\s+", " ", str(raw_text)).strip()

#         # Rule 1: Collapse single-character chains ("O W N" -> "OWN")
#         prev = None
#         while prev != s:
#             prev = s
#             s = re.sub(r"\b([A-Za-z0-9])\s+([A-Za-z0-9])\b", r"\1\2", s)

#         # Rule 2: Re-join isolated leading splinters first ("S USEELAN" -> "SUSEELAN")
#         s = re.sub(r"\b([A-Za-z]{1})\s+([A-Za-z]{3,})\b", r"\1\2", s)

#         # Rule 3: Re-join isolated trailing splinters ("INDI A" -> "INDIA")
#         s = re.sub(r"\b([A-Za-z]{3,})\s+([A-Za-z]{1})\b", r"\1\2", s)

#         # Rule 4: Structural banking cleanups
#         s = re.sub(r"\bOW\s+NACCOUNT\b", "OWN ACCOUNT", s, flags=re.IGNORECASE)
#         s = re.sub(r"\bNR\s+I\s+BRANCH\b", "NRI BRANCH", s, flags=re.IGNORECASE)
#         s = _HONORIFICS_REGEX.sub(" ", s)
#         s = _P2A_RAIL_REGEX.sub(" ", s)
#         s = _DIRECTION_SUFFIX_REGEX.sub("", s)

#         return re.sub(r"\s+", " ", s).strip().upper()

#     @classmethod
#     def canonicalize_dynamic_identity(
#         cls, name: str, registry: List[Dict[str, Any]]
#     ) -> str:
#         """
#         Matches a raw extracted name against dynamic registered account holders.
#         If words match a known profile holder, returns their canonical registered name.
#         """
#         if not name:
#             return ""
#         norm_name = cls.repair_narration_kerning(name).upper()
#         name_words = set(re.findall(r"[A-Z]{3,}", norm_name))

#         # Check against database account holders
#         for acc in registry:
#             holder = acc.get("holder_name") or ""
#             if not holder:
#                 continue
#             canonical_holder = cls.repair_narration_kerning(holder).upper()
#             holder_words = set(re.findall(r"[A-Z]{3,}", canonical_holder))

#             # Match on 2 or more shared key words, or substring equivalence
#             if (
#                 len(name_words.intersection(holder_words)) >= 2
#                 or norm_name in canonical_holder
#             ):
#                 return canonical_holder

#         return norm_name

#     @classmethod
#     def extract_rail_reference(cls, narration: str) -> Optional[str]:
#         if not narration:
#             return None
#         m_rrn = _RRN_12_REGEX.search(narration)
#         if m_rrn:
#             return m_rrn.group(1)
#         m_utr = _UTR_REGEX.search(narration)
#         if m_utr:
#             return m_utr.group(1)
#         return None

#     @classmethod
#     def extract_meaningful_tokens(cls, text: str) -> List[str]:
#         if not text:
#             return []
#         cleaned = cls.repair_narration_kerning(text)
#         filtered_tokens = []
#         for token in cleaned.split():
#             if token in NOISE_KEYWORD_BLACKLIST or token in RULE_SAFETY_BLACKLIST:
#                 continue
#             if token.isdigit() or len(token) > 20:
#                 continue
#             if re.search(r"[A-Z]", token) and re.search(r"[0-9]", token):
#                 continue
#             if token in ACTION_AND_RAIL_NOISE:
#                 continue
#             filtered_tokens.append(token)
#         return filtered_tokens

#     @classmethod
#     def extract_clean_payee_pattern(cls, narration: str) -> str:
#         if not narration:
#             return ""
#         tokens = cls.extract_meaningful_tokens(narration)
#         if not tokens:
#             return ""
#         for t in tokens:
#             if t in KNOWN_MERCHANTS:
#                 return t
#         clean_tokens = tokens[:2] if len(tokens) >= 2 else tokens
#         return " ".join(clean_tokens).upper()

#     @classmethod
#     def generate_canonical_cluster_tag(
#         cls,
#         raw_narration: str,
#         payee: Optional[str] = None,
#         host_account_id: Optional[int] = None,
#         registry: Optional[List[Dict[str, Any]]] = None,
#     ) -> Tuple[str, str, float, str, bool]:
#         cleaned_narr = cls.repair_narration_kerning(raw_narration or "")
#         acc_registry = (
#             registry if registry is not None else cls.get_dynamic_accounts_registry()
#         )
#         clean_payee = cls.canonicalize_dynamic_identity(payee or "", acc_registry)

#         ref_id = cls.extract_rail_reference(cleaned_narr)
#         has_ref = bool(ref_id)

#         # 1. Unilateral Internal Account Match via Registry
#         internal_match = cls.detect_internal_counterpart(
#             cleaned_narr, host_account_id, acc_registry
#         )
#         if internal_match:
#             dest_name = internal_match["name"].upper()
#             score, label, ok = ConfidenceScorer.evaluate(
#                 is_unilateral_internal=True,
#                 has_ref_proof=has_ref,
#                 has_clean_tokens=True,
#             )
#             slug = re.sub(r"[^A-Z0-9]+", "_", dest_name).strip("_")
#             return f"#TRANSFER_TO_{slug}", f"TRANSFER TO {dest_name}", score, label, ok

#         if "OWN ACCOUNT" in cleaned_narr or "SELF TRANSFER" in cleaned_narr:
#             score, label, ok = ConfidenceScorer.evaluate(
#                 is_unilateral_internal=True,
#                 has_ref_proof=has_ref,
#                 has_clean_tokens=True,
#             )
#             return "#SELF_TRANSFER", "OWN ACCOUNT TRANSFER", score, label, ok

#         # 2. Clean Payee / Merchant Extract
#         source_name = clean_payee or cleaned_narr
#         clean_merchant = cls.extract_clean_payee_pattern(source_name)
#         if clean_merchant:
#             is_known = clean_merchant in KNOWN_MERCHANTS
#             tokens = clean_merchant.split()
#             tag_slug = "_".join(tokens[:2])
#             score, label, ok = ConfidenceScorer.evaluate(
#                 has_known_merchant=is_known,
#                 has_ref_proof=has_ref,
#                 has_clean_tokens=True,
#             )
#             return f"#{tag_slug}", clean_merchant, score, label, ok

#         # 3. Reference Fallback
#         if ref_id:
#             score, label, ok = ConfidenceScorer.evaluate(
#                 has_ref_proof=True,
#                 has_clean_tokens=False,
#             )
#             return f"#REF_{ref_id}", f"REF: {ref_id}", score, label, ok

#         # 4. Absolute Fallback
#         return "#UNRESOLVED_LINE", "UNRESOLVED SUSPENSE ITEM", 0.10, "LOW", False

#     @classmethod
#     def resolve_cluster_envelope(
#         cls,
#         is_contra: bool,
#         contra_info: Dict[str, Any],
#         raw_narration: str,
#         payee: str,
#         amount: float,
#         ref_no: Optional[str],
#         host_account_id: Optional[int],
#         acc_registry: List[Dict[str, Any]],
#     ) -> Tuple[str, str, str, Optional[str], float, str, bool]:
#         """
#         Unified router that produces standard cluster coordinates dynamically.
#         """
#         clean_payee = cls.canonicalize_dynamic_identity(payee, acc_registry)

#         if is_contra:
#             src_name = contra_info.get("from_account_name", "Bank").upper()
#             dst_name = contra_info.get("to_account_name", "Bank").upper()
#             canonical_title = f"{src_name} ➔ {dst_name}"

#             slug_src = re.sub(r"[^A-Z0-9]+", "_", src_name).strip("_")
#             slug_dst = re.sub(r"[^A-Z0-9]+", "_", dst_name).strip("_")
#             pattern = f"#{slug_src}_TO_{slug_dst}"

#             score, label, ok_to_classify = ConfidenceScorer.evaluate(
#                 is_paired_contra=True,
#                 has_ref_proof=bool(ref_no),
#                 has_rule_precedent=True,
#             )
#             pair_amt = f"{amount:.2f}"
#             pair_id = (
#                 f"PAIR_{min(src_name, dst_name)}_{max(src_name, dst_name)}_{pair_amt}"
#             )
#             display_subgroup = canonical_title
#         else:
#             (
#                 pattern,
#                 canonical_title,
#                 score,
#                 label,
#                 ok_to_classify,
#             ) = cls.generate_canonical_cluster_tag(
#                 raw_narration=raw_narration,
#                 payee=clean_payee,
#                 host_account_id=host_account_id,
#                 registry=acc_registry,
#             )
#             pair_id = None
#             display_subgroup = clean_payee or canonical_title

#         return (
#             pattern.upper().strip(),
#             canonical_title,
#             display_subgroup,
#             pair_id,
#             score,
#             label,
#             ok_to_classify,
#         )

#     @classmethod
#     def create_empty_cluster(
#         cls,
#         pattern: str,
#         display_name: str,
#         score: float,
#         label: str,
#         is_contra: bool,
#     ) -> Dict[str, Any]:
#         return {
#             "pattern": pattern,
#             "display_name": display_name,
#             "count": 0,
#             "total_amount": 0.0,
#             "total_inflow": 0.0,
#             "total_outflow": 0.0,
#             "confidence_score": score,
#             "confidence_label": label,
#             "sample_descriptions": [],
#             "items": [],
#             "transaction_ids": [],
#             "is_contra_group": is_contra,
#         }


# from __future__ import annotations
# import re
# from typing import Any, Dict, List, Optional, Set, Tuple
# from django.apps import apps
# from tracker.constants import (
#     ACTION_AND_RAIL_NOISE,
#     CORPORATE_NOISE_SUFFIXES,
#     KNOWN_MERCHANTS,
#     NOISE_KEYWORD_BLACKLIST,
#     OK_WORD_LIST,
#     RULE_SAFETY_BLACKLIST,
#     TRANSFER_BANK_NOISE,
#     UPI_RAIL_TOKENS,
#     TokenCatalog,
# )
# from .confidence_helpers import ConfidenceScorer

# _CBS_SESSION_REGEX = re.compile(r"\b[A-Z]\d{6,10}\b", re.IGNORECASE)
# _NUMERIC_ID_REGEX = re.compile(r"\b\d{4,}\b")
# _VPA_REGEX = re.compile(r"([A-Z0-9.\-_]+)@([A-Z]+)", re.IGNORECASE)
# _RRN_12_REGEX = re.compile(r"\b(\d{12})\b")
# _UTR_REGEX = re.compile(r"\b([A-Z]{4}[A-Z0-9]{12,18})\b")
# _HONORIFICS_REGEX = re.compile(
#     r"\b(?:OF\s+)?(?:MR|MRS|MS|DR|SHRI|SMT)\.?\s+", re.IGNORECASE
# )
# _P2A_RAIL_REGEX = re.compile(r"\b(?:P2A|P2P|IMPS/P2A|UPI/P2A)\b", re.IGNORECASE)
# _DIRECTION_SUFFIX_REGEX = re.compile(r"\s*\((?:IN|OUT|DR|CR)\)$", re.IGNORECASE)


# class TaggingEngine:
#     """Dynamic tagging, pairing, and scoring engine without hardcoded account identifiers."""

#     @classmethod
#     def get_dynamic_accounts_registry(cls) -> List[Dict[str, Any]]:
#         Account = apps.get_model("ledger", "Account")
#         registry = []
#         for acc in Account.objects.exclude(id=99):
#             acc_num = str(getattr(acc, "account_number", "") or "").strip()
#             acc_name = getattr(acc, "name", None) or getattr(acc, "bank_name", "Bank")
#             last4 = acc_num[-4:] if len(acc_num) >= 4 else str(acc.id)

#             registry.append(
#                 {
#                     "id": acc.id,
#                     "name": acc_name,
#                     "full_number": acc_num,
#                     "last4": last4,
#                     "patterns": [
#                         acc_num if len(acc_num) >= 6 else None,
#                         f"XX{last4}",
#                         f"X{last4}",
#                         f"..{last4}",
#                         last4 if len(last4) == 4 else None,
#                     ],
#                 }
#             )
#         return registry

#     @classmethod
#     def detect_internal_counterpart(
#         cls,
#         narration: str,
#         host_account_id: Optional[int],
#         registry: List[Dict[str, Any]],
#     ) -> Optional[Dict[str, Any]]:
#         if not narration:
#             return None
#         upper_narr = narration.upper()
#         for acc in registry:
#             if host_account_id and acc["id"] == host_account_id:
#                 continue
#             for pat in acc["patterns"]:
#                 if pat and pat.upper() in upper_narr:
#                     return acc
#         return None

#     @classmethod
#     def repair_narration_kerning(cls, raw_text: str) -> str:
#         if not raw_text:
#             return ""
#         text = re.sub(r"\s+", " ", str(raw_text)).strip()
#         text = re.sub(r"\bOW\s+NACCOUNT\b", "OWN ACCOUNT", text, flags=re.IGNORECASE)
#         text = re.sub(r"\bNR\s+I\s+BRANCH\b", "NRI BRANCH", text, flags=re.IGNORECASE)
#         text = _HONORIFICS_REGEX.sub(" ", text)
#         text = _P2A_RAIL_REGEX.sub(" ", text)
#         text = _DIRECTION_SUFFIX_REGEX.sub("", text)
#         return re.sub(r"\s+", " ", text).strip().upper()

#     @classmethod
#     def canonicalize_user_identity(cls, name: str) -> str:
#         """
#         Normalizes core banking variations of the primary account holder.
#         Prevents splitting between NEFT wires, SIB MOB transfers, and branch printouts.
#         """
#         if not name:
#             return ""
#         norm = cls.repair_narration_kerning(name).upper()

#         # Matches BAIJU NAIR, BAIJU S NAIR, BAIJU SUSEELAN, BAIJU SUSEELANN, etc.
#         if re.search(r"\bBAIJU\b.*\bNAIR\b", norm) or re.search(
#             r"\bBAIJU\s+SUSEELAN\b", norm
#         ):
#             return "BAIJU SUSEELAN NAIR"
#         return norm

#     @classmethod
#     def extract_rail_reference(cls, narration: str) -> Optional[str]:
#         if not narration:
#             return None
#         m_rrn = _RRN_12_REGEX.search(narration)
#         if m_rrn:
#             return m_rrn.group(1)
#         m_utr = _UTR_REGEX.search(narration)
#         if m_utr:
#             return m_utr.group(1)
#         return None

#     @classmethod
#     def extract_meaningful_tokens(cls, text: str) -> List[str]:
#         if not text:
#             return []
#         cleaned = cls.repair_narration_kerning(text)
#         filtered_tokens = []
#         for token in cleaned.split():
#             if token in NOISE_KEYWORD_BLACKLIST or token in RULE_SAFETY_BLACKLIST:
#                 continue
#             if token.isdigit() or len(token) > 20:
#                 continue
#             if re.search(r"[A-Z]", token) and re.search(r"[0-9]", token):
#                 continue
#             if token in ACTION_AND_RAIL_NOISE:
#                 continue
#             filtered_tokens.append(token)
#         return filtered_tokens

#     @classmethod
#     def extract_clean_payee_pattern(cls, narration: str) -> str:
#         if not narration:
#             return ""
#         tokens = cls.extract_meaningful_tokens(narration)
#         if not tokens:
#             return ""
#         for t in tokens:
#             if t in KNOWN_MERCHANTS:
#                 return t
#         clean_tokens = tokens[:2] if len(tokens) >= 2 else tokens
#         return " ".join(clean_tokens).upper()

#     @classmethod
#     def generate_canonical_cluster_tag(
#         cls,
#         raw_narration: str,
#         payee: Optional[str] = None,
#         host_account_id: Optional[int] = None,
#         registry: Optional[List[Dict[str, Any]]] = None,
#     ) -> Tuple[str, str, float, str, bool]:
#         """
#         Returns:
#             (pattern_tag, canonical_title, confidence_score, confidence_label, ok_to_classify)
#         """
#         cleaned_narr = cls.repair_narration_kerning(raw_narration or "")
#         acc_registry = (
#             registry if registry is not None else cls.get_dynamic_accounts_registry()
#         )
#         ref_id = cls.extract_rail_reference(cleaned_narr)
#         has_ref = bool(ref_id)

#         # 1. Unilateral Internal Account Match
#         internal_match = cls.detect_internal_counterpart(
#             cleaned_narr, host_account_id, acc_registry
#         )
#         if internal_match:
#             dest_name = internal_match["name"].upper()
#             score, label, ok = ConfidenceScorer.evaluate(
#                 is_unilateral_internal=True,
#                 has_ref_proof=has_ref,
#                 has_clean_tokens=True,
#             )
#             return "#SELF_TRANSFER", f"TRANSFER TO {dest_name}", score, label, ok

#         if "OWN ACCOUNT" in cleaned_narr or "SELF TRANSFER" in cleaned_narr:
#             score, label, ok = ConfidenceScorer.evaluate(
#                 is_unilateral_internal=True,
#                 has_ref_proof=has_ref,
#                 has_clean_tokens=True,
#             )
#             return "#SELF_TRANSFER", "OWN ACCOUNT TRANSFER", score, label, ok

#         # 2. Clean Payee / Merchant Extract
#         source_name = payee or cleaned_narr
#         clean_merchant = cls.extract_clean_payee_pattern(source_name)
#         if clean_merchant:
#             is_known = clean_merchant in KNOWN_MERCHANTS
#             tokens = clean_merchant.split()
#             tag_slug = "_".join(tokens[:2])
#             score, label, ok = ConfidenceScorer.evaluate(
#                 has_known_merchant=is_known,
#                 has_ref_proof=has_ref,
#                 has_clean_tokens=True,
#             )
#             return f"#{tag_slug}", clean_merchant, score, label, ok

#         # 3. Reference Fallback
#         if ref_id:
#             score, label, ok = ConfidenceScorer.evaluate(
#                 has_ref_proof=True,
#                 has_clean_tokens=False,
#             )
#             return f"#REF_{ref_id}", f"REF: {ref_id}", score, label, ok

#         # 4. Absolute Fallback
#         return "#UNRESOLVED_LINE", "UNRESOLVED SUSPENSE ITEM", 0.10, "LOW", False
