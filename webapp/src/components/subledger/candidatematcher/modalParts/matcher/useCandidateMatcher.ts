import { useState, useCallback } from 'react';
import {
  subledgerApi,
  type CandidateMatchResult,
  type AssetComplianceSchedule,
  type AssetOperationalAccount,
  type AssetSubLedgerNode,
} from '../../../../../api/subledger';

// Helper to normalize dates cleanly to YYYY-MM-DD
const normalizeDateString = (dateVal?: string): string => {
  if (!dateVal) return new Date().toISOString().split('T')[0];
  const cleaned = dateVal.split('T')[0].trim();
  if (cleaned.includes('-')) {
    const parts = cleaned.split('-');
    if (parts[0].length === 2 && parts[2].length === 4) {
      return `${parts[2]}-${parts[1]}-${parts[0]}`;
    }
  }
  return cleaned;
};

export const useCandidateMatcher = (
  activeSubcategory: string | null,
  onSuccess: () => void,
  onClose: () => void
) => {
  const [loading, setLoading] = useState(false);
  const [binding, setBinding] = useState(false);
  const [candidates, setCandidates] = useState<CandidateMatchResult[]>([]);
  const [selectedRowIds, setSelectedRowIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  // 1. Direct Seed: Used when opening from the Classification Workbench
  const seedWorkbenchCandidates = useCallback(
    (rawItems: any[], preSelectedIds: string[] = []) => {
      const seenIds = new Set<string>();
      const formattedCandidates: CandidateMatchResult[] = [];

      for (const item of rawItems) {
        const rowId =
          item.row_identifier || String(item.id || item.journal_id || '');
        if (!rowId || seenIds.has(rowId)) continue;
        seenIds.add(rowId);

        const rawDebit = Number(
          item.debit ?? (item.amount && item.amount > 0 ? item.amount : 0) ?? 0
        );
        const rawCredit = Number(
          item.credit ??
            (item.amount && item.amount < 0 ? Math.abs(item.amount) : 0) ??
            0
        );

        formattedCandidates.push({
          journal_id: String(item.id || item.journal_id || ''),
          row_identifier: rowId,
          account_id: item.account_id || null,
          transaction_date: normalizeDateString(
            item.transaction_date || item.date
          ),
          date_offset_days: 0,
          debit: rawDebit,
          credit: rawCredit,
          remarks: item.remarks || item.narration || item.payee || '',
          //  matched_keywords: [],
          probability_score: 100,
          is_mapped: false,
          is_mapped_to_this_asset: false,
          mapping_info: null,
        });
      }

      setCandidates(formattedCandidates);
      if (preSelectedIds.length > 0) {
        setSelectedRowIds(Array.from(new Set(preSelectedIds)));
      } else {
        setSelectedRowIds(formattedCandidates.map((c) => c.row_identifier));
      }
    },
    []
  );

  // 2. Unmapped GL Ledger: Inspection of existing category variance
  const loadUnmappedGlRows = useCallback(
    async (subcategoryName: string, effectiveAssetId?: string) => {
      setLoading(true);
      setError(null);
      try {
        const cleanSub =
          subcategoryName.split('➔').pop()?.split('->').pop()?.trim() ||
          subcategoryName;

        const response = await subledgerApi.findCandidates({
          asset_id: effectiveAssetId,
          subcategory: cleanSub,
          document_date: new Date().toISOString().split('T')[0],
          day_window: 1825, // Till Today (~5 years)
          keywords: [],
          unmapped_only: true,
        } as any);

        const incoming = response.candidates || [];
        setCandidates(incoming);
      } catch (err: any) {
        console.error('Failed to load unmapped GL lines:', err);
        setError('Failed to fetch unmapped GL entries.');
        setCandidates([]);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  // 3. Staging Deep Scan: Exploratory search across staging
  const runScan = useCallback(
    async (
      docDate: string,
      amt: number | string,
      kwString: string,
      windowDays: number,
      effectiveAssetId?: string,
      targetRowId?: string
    ) => {
      setLoading(true);
      setError(null);

      const formattedDate = normalizeDateString(docDate);
      const kwArray = kwString
        ? kwString
            .split(',')
            .map((k) => k.trim())
            .filter(Boolean)
        : [];

      const parsedAmount = Number(amt);
      const cleanAmount =
        !isNaN(parsedAmount) && parsedAmount > 0 ? parsedAmount : null;

      if (!effectiveAssetId) {
        setError(`No subledger node available under '${activeSubcategory}'.`);
        setLoading(false);
        setCandidates([]);
        return;
      }

      try {
        const response = await subledgerApi.findCandidates({
          asset_id: effectiveAssetId,
          document_date: formattedDate,
          target_amount: cleanAmount,
          day_window: windowDays,
          keywords: kwArray,
        });

        const incoming = response.candidates || [];
        setCandidates(incoming);

        if (
          targetRowId &&
          incoming.some((c) => c.row_identifier === targetRowId)
        ) {
          setSelectedRowIds([targetRowId]);
        }
      } catch (err: any) {
        setError('Failed to fetch candidates from staging.');
        setCandidates([]);
      } finally {
        setLoading(false);
      }
    },
    [activeSubcategory]
  );

  // 4. Batch Bind Execution (Parallelized for high throughput)
  const executeBind = useCallback(
    async (
      targetRows: CandidateMatchResult[],
      targetAsset: AssetSubLedgerNode,
      options: {
        documentDate: string;
        targetAmount: number | string;
        schedule?: AssetComplianceSchedule | null;
        utility?: AssetOperationalAccount | null;
        userNote?: string;
        syncCost: boolean;
        isCash: boolean;
      }
    ) => {
      if (!targetRows.length) return;
      setBinding(true);
      setError(null);

      try {
        // Execute binds concurrently in parallel
        await Promise.all(
          targetRows.map((cand) => {
            const dateStr = normalizeDateString(
              cand?.transaction_date || options.documentDate
            );
            const amt = cand
              ? Number(cand.debit || cand.credit || 0)
              : Number(options.targetAmount) || 0;

            return subledgerApi.bindTransaction({
              asset_id: targetAsset.id,
              schedule_id: options.schedule?.id || null,
              operational_account_id:
                options.utility?.id ||
                targetAsset.operational_accounts?.[0]?.id ||
                null,
              row_identifier: options.isCash ? null : cand.row_identifier,
              is_cash_entry: options.isCash,
              transaction_date: dateStr,
              amount: amt,
              transaction_purpose:
                options.schedule?.schedule_type || 'SUB_LEDGER_PAYMENT',
              user_note: options.userNote || 'Reconciled via Matcher UI',
              sync_acquisition_cost: options.syncCost,
            });
          })
        );

        onSuccess();
        onClose();
      } catch (err: any) {
        console.error('Batch bind failed:', err);
        setError('Failed to bind selected transaction(s).');
      } finally {
        setBinding(false);
      }
    },
    [onSuccess, onClose]
  );

  return {
    loading,
    binding,
    candidates,
    setCandidates,
    selectedRowIds,
    setSelectedRowIds,
    error,
    setError,
    runScan,
    loadUnmappedGlRows,
    seedWorkbenchCandidates,
    executeBind,
  };
};
