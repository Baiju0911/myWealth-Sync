// webapp/src/components/subledger/candidatematcher/candidateMatchingUtils.ts
import type {
  CandidateMatchResult,
  AssetSubLedgerNode,
} from '../../../api/subledger';
import {
  toIsoDateString,
  resolveCandidateNarration,
} from '../../../utils/classificationHelpers';

export const parseNumericAmount = (val: any): number => {
  if (typeof val === 'number') return isNaN(val) ? 0 : Math.abs(val);
  if (!val) return 0;
  const cleanStr = String(val).replace(/[^0-9.-]+/g, '');
  const num = parseFloat(cleanStr);
  return isNaN(num) ? 0 : Math.abs(num);
};

export function transformWorkbenchRowsToCandidates(
  rows: any[],
  targetNode?: AssetSubLedgerNode | null,
  fallbackAccountId?: number | string | null
): CandidateMatchResult[] {
  const activeNodeId = targetNode?.id ? String(targetNode.id) : null;

  return rows.map((r) => {
    const rawDebit = parseNumericAmount(
      r.debit || r.outflow || r.total_outflow || r.withdrawal
    );
    const rawCredit = parseNumericAmount(
      r.credit || r.inflow || r.total_inflow || r.deposit
    );
    const rawGeneralAmount = parseNumericAmount(
      r.amount || r.txn_amount || r.total_amount || r.value
    );

    const remarksAmount =
      typeof r.remarks === 'object' && r.remarks !== null
        ? parseNumericAmount(
            r.remarks.amount || r.remarks.debit || r.remarks.credit
          )
        : 0;

    let narrationAmount = 0;
    if (
      rawDebit === 0 &&
      rawCredit === 0 &&
      rawGeneralAmount === 0 &&
      remarksAmount === 0
    ) {
      const narrationText = String(
        r.narration || r.universal_narration || r.remarks || ''
      );
      const match = narrationText.match(/[₹Rs.]*\s*([0-9,]+(?:\.[0-9]{2})?)/);
      if (match && match[1]) {
        narrationAmount = parseNumericAmount(match[1]);
      }
    }

    const resolvedAmount =
      rawDebit > 0
        ? rawDebit
        : rawCredit > 0
          ? rawCredit
          : rawGeneralAmount > 0
            ? rawGeneralAmount
            : remarksAmount > 0
              ? remarksAmount
              : narrationAmount;

    const resolvedNarration = resolveCandidateNarration(
      r.remarks,
      r.narration ||
        r.universal_narration ||
        r.description ||
        (Array.isArray(r.sample_descriptions) ? r.sample_descriptions[0] : '')
    );

    const isMappedToActive = Boolean(
      r.is_mapped_to_this_asset ||
      (activeNodeId &&
        (String(r.asset_id || '') === activeNodeId ||
          String(r.mapping_info?.asset_id || '') === activeNodeId))
    );

    return {
      account_id: Number(r.account_id ?? fallbackAccountId ?? 0),
      row_identifier: String(
        r.row_identifier || r.transaction_id || r.id || ''
      ),
      journal_id: String(r.journal_id || r.id || ''),
      transaction_date: toIsoDateString(
        r.date || r.transaction_date || r.timestamp
      ),
      debit: resolvedAmount,
      credit: rawCredit,
      remarks: resolvedNarration,
      probability_score: r.probability_score ?? 100,
      date_offset_days: r.date_offset_days ?? 0,
      amount_difference: 0,
      is_mapped: Boolean(r.is_mapped || isMappedToActive),
      is_mapped_to_this_asset: isMappedToActive,
      mapping_info:
        r.mapping_info ||
        (isMappedToActive
          ? {
              mapping_id: String(r.mapping_id || r.id),
              asset_id: activeNodeId || '',
            }
          : null),
    } as CandidateMatchResult;
  });
}

export function deduplicateAndAnnotateCandidates(
  workbenchList: CandidateMatchResult[],
  scannedList: CandidateMatchResult[],
  activeNode: AssetSubLedgerNode | null | undefined,
  locallyBoundMap: Map<string, string>,
  globalBoundMap: Map<string, any>
): CandidateMatchResult[] {
  // Pinned workbench rows always appear first, followed by Re-Scan query rows
  const combinedRaw = [...workbenchList, ...scannedList];

  const seenRowKeys = new Set<string>();
  const seenJournalKeys = new Set<string>();
  const seenSignatures = new Set<string>();
  const deduplicated: CandidateMatchResult[] = [];

  const sorted = [...combinedRaw].sort((a, b) => {
    const aMapped = a.is_mapped || a.is_mapped_to_this_asset ? 1 : 0;
    const bMapped = b.is_mapped || b.is_mapped_to_this_asset ? 1 : 0;
    return bMapped - aMapped;
  });

  for (const cand of sorted) {
    const rKey = cand.row_identifier ? String(cand.row_identifier).trim() : '';
    const jKey = cand.journal_id ? String(cand.journal_id).trim() : '';

    const amt = Number(cand.debit || cand.credit || 0).toFixed(2);
    const dt = cand.transaction_date
      ? String(cand.transaction_date).slice(0, 10)
      : '';
    const contentSig = dt && Number(amt) > 0 ? `${dt}_${amt}` : '';

    const isDuplicateKey =
      (rKey && seenRowKeys.has(rKey)) || (jKey && seenJournalKeys.has(jKey));
    const isDuplicateSig =
      contentSig && seenSignatures.has(contentSig) && !rKey && !jKey;

    if (isDuplicateKey || isDuplicateSig) {
      continue;
    }

    if (rKey) seenRowKeys.add(rKey);
    if (jKey) seenJournalKeys.add(jKey);
    if (contentSig) seenSignatures.add(contentSig);

    deduplicated.push(cand);
  }

  const activeNodeId = activeNode ? String(activeNode.id) : '';

  return deduplicated.map((cand) => {
    const rowKey = cand.row_identifier ? String(cand.row_identifier) : '';
    const journalKey = cand.journal_id ? String(cand.journal_id) : '';

    const localMappingId =
      locallyBoundMap.get(rowKey) || locallyBoundMap.get(journalKey);
    const globalInfo =
      globalBoundMap.get(rowKey) || globalBoundMap.get(journalKey);

    // Case 1: Bound to active selected folio
    if (
      localMappingId ||
      (globalInfo && String(globalInfo.asset_id) === activeNodeId)
    ) {
      return {
        ...cand,
        is_mapped: true,
        is_mapped_to_this_asset: true,
        mapping_info: {
          mapping_id: localMappingId || globalInfo!.mapping_id,
          asset_id: activeNodeId,
          asset_code: activeNode?.asset_code,
          asset_name: activeNode?.name,
          vendor_name: globalInfo?.vendor_name,
        },
      };
    }

    // Case 2: Bound to another folio in the system (Lock State)
    if (globalInfo && String(globalInfo.asset_id) !== activeNodeId) {
      return {
        ...cand,
        is_mapped: true,
        is_mapped_to_this_asset: false,
        mapping_info: globalInfo,
      };
    }

    return cand;
  });
}
