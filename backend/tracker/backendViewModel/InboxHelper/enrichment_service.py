import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db.models import Q
from django.utils import timezone

from tracker.constants import (
    ACTIVE_STAGED_PAYLOAD_STATUSES,
    EnrichmentMetadata,
    MatchingRules,
    PayloadStatus,
    StagingMatchStatus,
)
from tracker.models import Bank, RawEmailPayload, StatementStagingLine
from tracker.parsers.utils import (
    extract_rail_reference,
    generate_live_collision_hash,
    resolve_statement_collision,
)
from .smart_enricher import SmartPayloadEnricher

logger = logging.getLogger(__name__)

GENERIC_PAYEE_BLACKLIST = {
    "DIRECT PAYMENT",
    "DIRECT_PAYMENT",
    "UNKNOWN",
    "PAYMENT",
    "UPI",
    "TRANSFER",
    "INFO",
    "UNCLASSIFIED",
    "NO REMARK",
    "NO REMAR",
}


class LiveStreamEnrichmentService:
    """
    Core execution engine for candidate loading, matching, and dual-table synchronization.
    """

    @classmethod
    def execute_pipeline(cls) -> Dict[str, Any]:
        staged_payloads = list(
            RawEmailPayload.objects.filter(
                status__in=ACTIVE_STAGED_PAYLOAD_STATUSES,
                is_completed=0,
            )
        )

        if not staged_payloads:
            return {
                "enriched_count": 0,
                "waiting_count": 0,
                "companion_retired_count": 0,
            }

        # 1. Pre-cache dynamic bank lookup map
        bank_name_to_id = cls._build_bank_cache()

        # 2. Extract bounds using SmartPayloadEnricher
        alert_amounts = set()
        alert_rrns = set()
        enriched_runtime_data = {}

        for p in staged_payloads:
            body_text = (
                getattr(p, "decrypted_body", None)
                or getattr(p, "body_text", None)
                or getattr(p, "body", None)
                or getattr(p, "snippet", None)
                or ""
            )
            harvested = SmartPayloadEnricher.harvest_all(
                subject=p.subject,
                body_text=body_text,
                headers_json=p.headers_json,
                existing_amount=p.amount,
                existing_account_last4=p.account_last4,
                existing_upi_ref=p.upi_ref,
            )
            enriched_runtime_data[p.id] = harvested

            amt = harvested.get("amount")
            if amt is not None:
                try:
                    amt_dec = Decimal(str(amt))
                    alert_amounts.add(amt_dec)
                    alert_amounts.add(amt_dec.quantize(Decimal("1")))
                except Exception:
                    pass

            ref = harvested.get("upi_ref")
            if ref and len(str(ref).strip()) >= MatchingRules.MIN_RRN_ANCHOR_LENGTH:
                alert_rrns.add(str(ref).strip())

        # 3. Idempotent candidate statement line query
        candidate_conditions = Q()
        if alert_rrns:
            candidate_conditions |= Q(live_upi_rrn__in=alert_rrns)
            candidate_conditions |= Q(cheque_ref_number__in=alert_rrns)
            for rrn in alert_rrns:
                candidate_conditions |= Q(raw_narration__icontains=rrn)

        if alert_amounts:
            candidate_conditions |= Q(is_enriched_from_live=0) & Q(
                amount__in=alert_amounts
            )

        staging_query = StatementStagingLine.objects.filter(
            candidate_conditions
        ).select_related("account", "bank", "account__bank")

        # 4. Build lookup maps
        staging_rrn_map, staging_hash_map = cls._build_staging_maps(staging_query)

        # 5. Execute Multi-Tier Resolution
        lines_to_update = []
        payloads_to_retire = []
        enriched_count = 0
        waiting_count = 0
        now_ts = timezone.now()

        for payload in staged_payloads:
            harvested = enriched_runtime_data.get(payload.id, {})
            amt_val = harvested.get("amount")
            extracted_ref = harvested.get("upi_ref")
            acc_last4 = harvested.get("account_last4") or ""

            payload_bank_key = cls._resolve_bank_key(payload, bank_name_to_id)

            # Prioritize extracted execution date over delivery date
            date_val = None
            raw_txn_date = harvested.get("txn_date")
            if raw_txn_date:
                try:
                    date_val = datetime.strptime(raw_txn_date, "%d-%m-%Y").date()
                except Exception:
                    pass

            if not date_val:
                date_val = (
                    payload.email_date.date()
                    if payload.email_date
                    else (payload.created_at.date() if payload.created_at else None)
                )

            target_line = None
            matched_hash = None
            has_amount_discrepancy = False
            amount_variance = Decimal("0.00")

            # Tier 1: RRN Anchor Matching
            if extracted_ref and str(extracted_ref).strip() in staging_rrn_map:
                clean_ref = str(extracted_ref).strip()
                candidates = staging_rrn_map.get(clean_ref, [])

                exact_matches = [
                    c
                    for c in candidates
                    if amt_val is not None
                    and Decimal(str(c.amount)) == Decimal(str(amt_val))
                ]
                if exact_matches:
                    target_line = exact_matches[0]
                else:
                    near_matches = [
                        c
                        for c in candidates
                        if amt_val is not None
                        and abs(Decimal(str(c.amount)) - Decimal(str(amt_val)))
                        <= MatchingRules.PAISE_TOLERANCE_THRESHOLD
                    ]
                    if near_matches:
                        target_line = near_matches[0]
                        has_amount_discrepancy = True
                        amount_variance = abs(
                            Decimal(str(target_line.amount)) - Decimal(str(amt_val))
                        )

                if target_line:
                    candidates.remove(target_line)
                    for h_list in staging_hash_map.values():
                        if target_line in h_list:
                            h_list.remove(target_line)
                            break

            # Tier 2: Heuristic Hash Matching
            if not target_line and date_val and amt_val is not None:
                for offset in MatchingRules.HOLIDAY_DAY_OFFSETS:
                    check_date = date_val + timedelta(days=offset)
                    h = generate_live_collision_hash(
                        date_val=check_date,
                        bank_val=payload_bank_key,
                        account_last4=acc_last4[-4:] if acc_last4 else "",
                        amount_val=amt_val,
                    )
                    candidates = staging_hash_map.get(h, [])
                    if candidates:
                        target_line = resolve_statement_collision(candidates, payload)
                        if target_line:
                            candidates.remove(target_line)
                            matched_hash = h
                            break

            # Populate Statement line and Payload
            if target_line:
                cls._populate_enrichment(
                    target_line=target_line,
                    payload=payload,
                    harvested=harvested,
                    extracted_ref=extracted_ref,
                    matched_hash=matched_hash,
                    has_amount_discrepancy=has_amount_discrepancy,
                    amount_variance=amount_variance,
                    now_ts=now_ts,
                )
                lines_to_update.append(target_line)
                payloads_to_retire.append(payload)
                enriched_count += 1
            else:
                waiting_count += 1

        # 6. Bulk update matches
        if lines_to_update:
            StatementStagingLine.objects.bulk_update(
                lines_to_update,
                [
                    "is_enriched_from_live",
                    "live_upi_rrn",
                    "live_metadata",
                    "raw_narration",
                ],
                batch_size=MatchingRules.BULK_UPDATE_BATCH_SIZE,
            )

        if payloads_to_retire:
            RawEmailPayload.objects.bulk_update(
                payloads_to_retire,
                [
                    "status",
                    "amount",
                    "account_last4",
                    "upi_ref",
                    "is_completed",
                    "is_staged_for_matching",
                    "completed_at",
                    "processed_at",
                    "staging_payload",
                ],
                batch_size=MatchingRules.BULK_UPDATE_BATCH_SIZE,
            )

        # 7. Retire Companion Duplicates
        companion_retired_count = cls._retire_companion_duplicates(
            now_ts, bank_name_to_id
        )

        return {
            "enriched_count": enriched_count,
            "waiting_count": max(0, waiting_count - companion_retired_count),
            "companion_retired_count": companion_retired_count,
        }

    @classmethod
    def _build_bank_cache(cls) -> Dict[str, int]:
        bank_map = {}
        for b in Bank.objects.all():
            for attr in EnrichmentMetadata.BANK_LOOKUP_ATTRIBUTES:
                val = getattr(b, attr, None)
                if val and isinstance(val, str):
                    bank_map[val.strip().upper()] = b.id
        return bank_map

    @classmethod
    def _build_staging_maps(cls, staging_query):
        staging_rrn_map = {}
        staging_hash_map = {}

        for line in staging_query:
            acc_num = line.account.account_number if line.account else ""
            line_bank_id = line.bank_id or (
                line.account.bank_id if line.account else None
            )
            bank_key = str(line_bank_id) if line_bank_id is not None else ""

            ref_anchor = line.live_upi_rrn or line.cheque_ref_number
            if not ref_anchor:
                rail_info = extract_rail_reference(line.raw_narration or "")
                ref_anchor = rail_info.get("anchor")

            if ref_anchor:
                clean_anchor = str(ref_anchor).strip()
                staging_rrn_map.setdefault(clean_anchor, []).append(line)

            if not line.is_enriched_from_live:
                line_hash = generate_live_collision_hash(
                    date_val=line.raw_statement_date,
                    bank_val=bank_key,
                    account_last4=acc_num[-4:] if acc_num else "",
                    amount_val=line.amount,
                )
                staging_hash_map.setdefault(line_hash, []).append(line)

        return staging_rrn_map, staging_hash_map

    @classmethod
    def _resolve_bank_key(
        cls, payload: RawEmailPayload, bank_name_to_id: Dict[str, int]
    ) -> str:
        headers = payload.headers_json if isinstance(payload.headers_json, dict) else {}
        parsed = headers.get("parsed_summary", {}) if isinstance(headers, dict) else {}
        payload_bank_name = (
            (payload.bank_name or parsed.get("bank") or "").strip().upper()
        )

        bank_id = (
            getattr(payload, "bank_id", None)
            or (payload.account.bank_id if getattr(payload, "account", None) else None)
            or bank_name_to_id.get(payload_bank_name)
        )
        return str(bank_id) if bank_id is not None else ""

    @staticmethod
    def _extract_payee_from_narration(narration: str) -> Optional[str]:
        """
        Dynamically extracts legitimate entity names from variable-length
        bank narration strings regardless of bank routing tokens or RRN prefix styles.
        Examples:
          UPI/YESB/RRN 112817426804/MOHANAN P/NO REMARK  -> MOHANAN P
          UPI/CNRB/RRN 124152697363/SUDHEER SASIDHARAN/NO REMAR -> SUDHEER SASIDHARAN
          UPI/170054413824/SHESHADRI AYYAR/NO REMARK     -> SHESHADRI AYYAR
          IMPS/REF/VAZHIVARAM HARDWARES                 -> VAZHIVARAM HARDWARES
        """
        if not narration:
            return None

        text = narration.strip()
        parts = [p.strip() for p in text.split("/") if p.strip()]
        if not parts:
            return None

        # Filter out protocol headers, bank routing codes, RRN tokens, and remark footers
        valid_candidates = []
        for segment in parts:
            seg_upper = segment.upper()
            # Skip rail protocols
            if seg_upper in {"UPI", "IMPS", "NEFT", "RTGS"}:
                continue
            # Skip RRN or numeric reference tokens
            if re.match(r"^(?:RRN\s*)?\d{8,16}$", seg_upper):
                continue
            # Skip standard short bank route handles (e.g. YESB, CNRB, SIBL, SBIN)
            if re.match(r"^[A-Z]{3,5}$", seg_upper) and seg_upper not in {
                "CAFE",
                "SHOP",
                "STORE",
                "MART",
            }:
                continue
            # Skip generic remark footers
            if re.match(r"^NO\s*REMAR.*$", seg_upper):
                continue
            if seg_upper in GENERIC_PAYEE_BLACKLIST:
                continue

            valid_candidates.append(segment)

        if valid_candidates:
            # The longest or primary named candidate is the entity name
            chosen = valid_candidates[0]
            cleaned = re.sub(r"\s*NO\s*REMAR.*$", "", chosen, flags=re.I).strip()
            if cleaned.upper() not in GENERIC_PAYEE_BLACKLIST and len(cleaned) > 1:
                return cleaned

        return None

    @classmethod
    def _resolve_clean_merchant_hierarchy(
        cls, statement_narration: str, candidate_donor_merchant: str
    ) -> str:
        """
        Preserves specific physical statement entity names (e.g., MOHANAN P, VAZHIVARAM HARDWARES)
        if the donor alert provides only a generic fallback like 'Direct Payment'.
        """
        statement_candidate = cls._extract_payee_from_narration(statement_narration)

        donor_clean = (candidate_donor_merchant or "").strip()
        is_donor_generic = (
            not donor_clean or donor_clean.upper() in GENERIC_PAYEE_BLACKLIST
        )

        if not is_donor_generic:
            return donor_clean
        if statement_candidate:
            return statement_candidate
        return donor_clean or EnrichmentMetadata.DEFAULT_MERCHANT

    @classmethod
    def _populate_enrichment(
        cls,
        target_line: StatementStagingLine,
        payload: RawEmailPayload,
        harvested: Dict[str, Any],
        extracted_ref: Optional[str],
        matched_hash: Optional[str],
        has_amount_discrepancy: bool,
        amount_variance: Decimal,
        now_ts,
    ):
        target_line.is_enriched_from_live = 1
        if extracted_ref:
            target_line.live_upi_rrn = str(extracted_ref).strip()

        headers = payload.headers_json if isinstance(payload.headers_json, dict) else {}
        parsed = headers.get("parsed_summary", {}) if isinstance(headers, dict) else {}
        current_meta = target_line.live_metadata or {}

        donor_merchant = (
            harvested.get("payee_hint")
            or getattr(payload, "merchant", None)
            or parsed.get("merchant")
            or headers.get("merge_details", {}).get("resolved_narration")
            or current_meta.get("merchant")
            or ""
        )

        # 🛡️ Enforce Authoritative Merchant Hierarchy
        final_merchant = cls._resolve_clean_merchant_hierarchy(
            statement_narration=target_line.raw_narration or "",
            candidate_donor_merchant=donor_merchant,
        )

        tier_label = (
            "TIER 1 (RRN Exact Match)" if extracted_ref else "TIER 2 (Hex Fingerprint)"
        )

        donor_snippet = (
            getattr(payload, "snippet", None) or getattr(payload, "subject", None) or ""
        )

        # 🔍 Prioritize harvested remark hint ("Bill Payment", "Fuel", etc.), fallback to statement narration
        remark = harvested.get("remark_hint")
        if not remark:
            narration_str = target_line.raw_narration or ""
            if narration_str.count("/") >= 4:
                candidate_remark = narration_str.split("/")[-1].strip()
                if candidate_remark.upper() not in {"NO REMARK", "NO REMAR", ""}:
                    remark = candidate_remark

        # Clean generic remark leftovers
        if remark and remark.upper() in {
            "NO REMARK",
            "NO REMAR",
            "UPI",
            "IMPS",
            "NEFT",
        }:
            remark = None

        # Build synthesized resolved narration
        synthesized_narration = (
            f"{final_merchant} ({remark})" if remark else final_merchant
        )

        # 🎯 FIX: Replace boilerplate greeting in statement line narration with clean entity
        current_narr = target_line.raw_narration or ""
        if (
            "Dear Customer" in current_narr
            or current_narr.strip().lower().startswith("alert:")
            or not current_narr.strip()
        ):
            if synthesized_narration:
                target_line.raw_narration = synthesized_narration

        current_meta.update(
            {
                "hash_val": matched_hash or current_meta.get("hash_val"),
                "raw_payload_id": str(payload.id),
                "source": payload.source or EnrichmentMetadata.DEFAULT_SOURCE,
                "merchant": final_merchant,
                "remark": remark,
                "matched_tier": tier_label,
                "donor_raw_snippet": donor_snippet[:200],
                "enriched_at": now_ts.isoformat(),
                "original_narration": target_line.raw_narration,
                "resolved_narration": synthesized_narration,
                "has_amount_discrepancy": has_amount_discrepancy,
                "smart_extra_meta": harvested.get("extra_meta"),
                "discrepancy_details": (
                    {
                        "alert_amount": (
                            float(harvested["amount"])
                            if harvested.get("amount") is not None
                            else (
                                float(payload.amount)
                                if payload.amount is not None
                                else None
                            )
                        ),
                        "statement_amount": float(target_line.amount),
                        "variance": float(amount_variance),
                        "warning_type": EnrichmentMetadata.WARNING_TYPE_PAISE_DELTA,
                        "raw_snippet": donor_snippet[:120],
                    }
                    if has_amount_discrepancy
                    else None
                ),
            }
        )

        target_line.live_metadata = current_meta

        # Synchronize raw email payload
        payload.amount = harvested.get("amount") or payload.amount
        payload.account_last4 = harvested.get("account_last4") or payload.account_last4
        payload.upi_ref = extracted_ref or payload.upi_ref
        payload.status = (
            PayloadStatus.ENRICHED_WITH_WARNING.value
            if has_amount_discrepancy
            else PayloadStatus.ENRICHED.value
        )
        payload.is_completed = 1
        payload.is_staged_for_matching = 0
        payload.completed_at = now_ts
        payload.processed_at = now_ts

        stg_dict = (
            payload.staging_payload if isinstance(payload.staging_payload, dict) else {}
        )
        stg_dict.update(
            {
                "match_status": (
                    StagingMatchStatus.COMPLETED_WITH_WARNING.value
                    if has_amount_discrepancy
                    else StagingMatchStatus.COMPLETED.value
                ),
                "enriched": "YES",
                "is_enriched": True,
                "enriched_at": now_ts.isoformat(),
                "matched_staging_line_id": str(target_line.id),
                "resolved_payee": final_merchant,
                "remark": remark,
                "has_amount_discrepancy": has_amount_discrepancy,
                "discrepancy_details": (
                    {
                        "alert_amount": (
                            float(payload.amount) if payload.amount else None
                        ),
                        "statement_amount": float(target_line.amount),
                        "variance": float(amount_variance),
                    }
                    if has_amount_discrepancy
                    else None
                ),
                "smart_extra_meta": harvested.get("extra_meta"),
            }
        )
        payload.staging_payload = stg_dict

    @classmethod
    def _retire_companion_duplicates(
        cls, now_ts, bank_name_to_id: Dict[str, int]
    ) -> int:
        """
        Retires twin alerts (e.g., IOS_SMS matching GMAIL_API) across both RRN anchors
        and deterministic collision hashes (Date + Bank + Account Last4 + Amount).
        Synchronizes matched statement line context and marks both rows enriched.
        """
        # 1. Fetch all actively enriched statement lines
        enriched_statement_lines = (
            StatementStagingLine.objects.filter(is_enriched_from_live=1)
            .select_related("account", "bank", "account__bank")
            .only(
                "id",
                "live_upi_rrn",
                "cheque_ref_number",
                "raw_narration",
                "raw_statement_date",
                "amount",
                "live_metadata",
                "bank_id",
                "account__bank_id",
                "account__account_number",
            )
        )

        if not enriched_statement_lines:
            return 0

        # Build dual lookup tables: RRN map and Hexa Collision Hash map
        rrn_to_line = {}
        hash_to_line = {}

        for line in enriched_statement_lines:
            # Anchor 1: UPI RRN / Cheque ref
            clean_rrn = str(line.live_upi_rrn or line.cheque_ref_number or "").strip()
            if clean_rrn:
                rrn_to_line[clean_rrn] = line

            # Anchor 2: Hexa Hash from statement line
            acc_num = line.account.account_number if line.account else ""
            line_bank_id = line.bank_id or (
                line.account.bank_id if line.account else None
            )
            bank_key = str(line_bank_id) if line_bank_id is not None else ""

            line_hash = generate_live_collision_hash(
                date_val=line.raw_statement_date,
                bank_val=bank_key,
                account_last4=acc_num[-4:] if acc_num else "",
                amount_val=line.amount,
            )
            if line_hash:
                hash_to_line[line_hash] = line

        # 2. Query remaining STAGED candidate payloads
        staged_candidates = list(
            RawEmailPayload.objects.filter(
                status=PayloadStatus.STAGED.value,
                is_completed=0,
            )
        )

        companion_updates = []
        for comp in staged_candidates:
            matched_line = None

            # Check 1: RRN match
            clean_comp_ref = str(comp.upi_ref or "").strip()
            if clean_comp_ref and clean_comp_ref in rrn_to_line:
                matched_line = rrn_to_line[clean_comp_ref]

            # Check 2: Hexa Hash match (handles non-RRN transactions: POS, NEFT, ATM, etc.)
            if not matched_line and comp.amount is not None:
                comp_bank_key = cls._resolve_bank_key(comp, bank_name_to_id)
                comp_acc_last4 = str(comp.account_last4 or "")[-4:]

                # Resolve execution date or delivery date
                comp_date = None
                if comp.staging_payload and isinstance(comp.staging_payload, dict):
                    raw_txn_date = comp.staging_payload.get("txn_date")
                    if raw_txn_date:
                        try:
                            comp_date = datetime.strptime(
                                raw_txn_date, "%d-%m-%Y"
                            ).date()
                        except Exception:
                            pass
                if not comp_date:
                    comp_date = (
                        comp.email_date.date()
                        if comp.email_date
                        else (comp.created_at.date() if comp.created_at else None)
                    )

                if comp_date:
                    for offset in MatchingRules.HOLIDAY_DAY_OFFSETS:
                        h = generate_live_collision_hash(
                            date_val=comp_date + timedelta(days=offset),
                            bank_val=comp_bank_key,
                            account_last4=comp_acc_last4,
                            amount_val=comp.amount,
                        )
                        if h in hash_to_line:
                            matched_line = hash_to_line[h]
                            break

            # If matched via RRN or Hexa Hash, synchronize and retire
            if matched_line:
                parent_meta = (
                    matched_line.live_metadata
                    if isinstance(matched_line.live_metadata, dict)
                    else {}
                )
                resolved_merchant = (
                    parent_meta.get("merchant")
                    or parent_meta.get("resolved_narration")
                    or EnrichmentMetadata.DEFAULT_MERCHANT
                )

                comp.status = PayloadStatus.DUPLICATE_RETIRED.value
                comp.is_completed = 1
                comp.is_staged_for_matching = 0
                comp.completed_at = now_ts
                comp.processed_at = now_ts

                stg_dict = (
                    comp.staging_payload
                    if isinstance(comp.staging_payload, dict)
                    else {}
                )
                stg_dict.update(
                    {
                        "match_status": StagingMatchStatus.DUPLICATE_COMPANION_RETIRED.value,
                        "retirement_reason": EnrichmentMetadata.COMPANION_RETIREMENT_REASON,
                        "retired_at": now_ts.isoformat(),
                        "is_enriched": True,
                        "enriched": "YES",
                        "enriched_at": now_ts.isoformat(),
                        "matched_staging_line_id": str(matched_line.id),
                        "resolved_payee": resolved_merchant,
                        "twin_source": parent_meta.get("source"),
                        "matched_via": (
                            "HEXA_HASH"
                            if not (clean_comp_ref and clean_comp_ref in rrn_to_line)
                            else "RRN"
                        ),
                    }
                )
                comp.staging_payload = stg_dict
                companion_updates.append(comp)

        if companion_updates:
            RawEmailPayload.objects.bulk_update(
                companion_updates,
                [
                    "status",
                    "is_completed",
                    "is_staged_for_matching",
                    "completed_at",
                    "processed_at",
                    "staging_payload",
                ],
                batch_size=MatchingRules.BULK_UPDATE_BATCH_SIZE,
            )

        return len(companion_updates)
