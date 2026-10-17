// webapp/src/components/subledger/history/useHistoryDrawerData.ts
import { useState, useEffect, useCallback, useMemo } from 'react';
import { subledgerApi } from '../../../api/subledger';
import type { AssetSubLedgerNode } from '../../../api/subledger';

export interface MappedTransaction {
  mapping_id: string;
  journal_id: string;
  row_identifier: string;
  transaction_date: string;
  debit: number;
  credit: number;
  amount?: number;
  direction?: 'INFLOW' | 'OUTFLOW';
  transaction_purpose?: string;
  remarks: string | Record<string, any>;
  narration?: string;
  bank_name?: string;
  bank_last4?: string;
  bank_account_id?: number | string;
  user_note?: string;
  is_cash_entry?: boolean;
  mapped_at: string | null;
  source_asset_code?: string;
  source_asset_name?: string;
  is_child_tx?: boolean;
}

export function useHistoryDrawerData(
  asset: AssetSubLedgerNode,
  isOpen: boolean,
  onSuccess?: () => void
) {
  const [loading, setLoading] = useState(true);
  const [syncingValuation, setSyncingValuation] = useState(false);
  const [assetDetails, setAssetDetails] = useState<AssetSubLedgerNode | null>(
    null
  );
  const [childAssets, setChildAssets] = useState<AssetSubLedgerNode[]>([]);
  const [transactions, setTransactions] = useState<MappedTransaction[]>([]);
  const [unmappingId, setUnmappingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!asset?.id) return;
    setLoading(true);
    setError(null);

    try {
      const [details, mappedRes, allAssets] = await Promise.all([
        subledgerApi.getAssetById(asset.id),
        subledgerApi.getMappedTransactions(asset.id),
        subledgerApi.getAssets().catch(() => []),
      ]);

      setAssetDetails(details);

      const children = allAssets.filter((a: any) => {
        const parentId =
          a.parent_asset_id || a.parent_asset?.id || a.parent_asset;
        return parentId === asset.id;
      });
      setChildAssets(children);

      const parentTxs: MappedTransaction[] = (
        mappedRes.mapped_transactions || []
      ).map((tx: any) => ({
        ...tx,
        source_asset_code: details.asset_code,
        source_asset_name: details.name,
        is_child_tx: false,
      }));

      const childTxPromises = children.map(async (child) => {
        try {
          const childMapped = await subledgerApi.getMappedTransactions(
            child.id
          );
          return (childMapped.mapped_transactions || []).map((tx: any) => ({
            ...tx,
            source_asset_code: child.asset_code,
            source_asset_name: child.name,
            is_child_tx: true,
          }));
        } catch {
          return [];
        }
      });

      const childTxsArrays = await Promise.all(childTxPromises);
      const combined = [...parentTxs, ...childTxsArrays.flat()].sort((a, b) => {
        if (a.is_child_tx !== b.is_child_tx) return a.is_child_tx ? 1 : -1;
        return (
          new Date(b.transaction_date).getTime() -
          new Date(a.transaction_date).getTime()
        );
      });

      setTransactions(combined);
    } catch (err) {
      console.error('Failed to load sub-ledger statement:', err);
      setError('Failed to fetch sub-ledger statement.');
    } finally {
      setLoading(false);
    }
  }, [asset?.id]);

  useEffect(() => {
    if (isOpen && asset?.id) {
      fetchData();
    }
  }, [isOpen, asset?.id, fetchData]);

  const currentAsset = assetDetails || asset;

  // Domain & Type Detection
  const catCode = String((currentAsset as any).category || '').toUpperCase();
  const glHead = String(
    (currentAsset as any).linked_gl_account || ''
  ).toLowerCase();
  const isCashFloat =
    catCode.includes('CASH') ||
    catCode.includes('FLOAT') ||
    glHead.includes('cash') ||
    glHead.includes('float');

  const nodeType = (
    (currentAsset as any).category_type ||
    (currentAsset as any).category_detail?.category_type ||
    (currentAsset.asset_code?.startsWith('INC')
      ? 'INCOME'
      : currentAsset.asset_code?.startsWith('EXP')
        ? 'EXPENSE'
        : 'ASSET')
  ).toUpperCase();

  const isIncomeOrExpense = nodeType === 'INCOME' || nodeType === 'EXPENSE';

  // Financial Metrics
  const baseAcquisitionCost = isIncomeOrExpense
    ? 0
    : Number(currentAsset.acquisition_cost || 0) +
      childAssets
        .filter((child: any) => {
          const type = String(
            child.category_type || child.category_detail?.category_type || ''
          ).toUpperCase();
          return type === 'ASSET' || child.asset_code?.startsWith('AST');
        })
        .reduce((sum, c) => sum + Number(c.acquisition_cost || 0), 0);

  const checkIsInflow = useCallback((tx: MappedTransaction) => {
    // 🔍 Console log each transaction's evaluated direction
    console.log('🔍 [DEBUG TRANSACTION]:', {
      date: tx.transaction_date,
      amount: tx.amount || tx.credit || tx.debit,
      credit: tx.credit,
      debit: tx.debit,
      direction: tx.direction,
      purpose: tx.transaction_purpose,
    });

    if (tx.direction === 'INFLOW') return true;
    if (tx.direction === 'OUTFLOW') return false;

    // 2. Fallback to purpose if direction is missing
    const purpose = String(tx.transaction_purpose || '').toUpperCase();
    if (
      purpose.includes('CAPITAL') ||
      purpose.includes('INFLOW') ||
      purpose.includes('TOPUP')
    )
      return true;
    if (
      purpose.includes('EXPENSE') ||
      purpose.includes('SPEND') ||
      purpose.includes('OUTFLOW') ||
      purpose.includes('OPERATING')
    )
      return false;

    // 3. Fallback to numeric legs only if direction and purpose are completely absent
    const creditVal = Number(tx.credit || 0);
    const debitVal = Number(tx.debit || 0);
    if (creditVal > 0 && debitVal === 0) return true;
    if (debitVal > 0 && creditVal === 0) return false;

    return false;
  }, []);

  const totalInflows = useMemo(() => {
    return transactions
      .filter((tx) => checkIsInflow(tx))
      .reduce(
        (acc, curr) =>
          acc + Math.abs(Number(curr.credit || curr.amount || curr.debit || 0)),
        0
      );
  }, [transactions, checkIsInflow]);

  const totalOutflows = useMemo(() => {
    return transactions
      .filter((tx) => !checkIsInflow(tx))
      .reduce(
        (acc, curr) => acc + Math.abs(Number(curr.debit || curr.amount || 0)),
        0
      );
  }, [transactions, checkIsInflow]);

  const netRealizedYield = totalInflows - totalOutflows;

  const calculatedValuation = isCashFloat
    ? totalInflows - totalOutflows
    : isIncomeOrExpense
      ? netRealizedYield
      : baseAcquisitionCost + netRealizedYield;

  const savedDbValuation = Number(currentAsset.current_valuation || 0);
  const needsValuationSync =
    !isCashFloat &&
    !isIncomeOrExpense &&
    Math.abs(calculatedValuation - savedDbValuation) > 0.01;

  const handleManualSyncValuation = async () => {
    if (!currentAsset?.id || isIncomeOrExpense) return;
    setSyncingValuation(true);
    setError(null);

    try {
      await subledgerApi.updateAsset(currentAsset.id, {
        current_valuation: calculatedValuation,
      });
      await fetchData();
      if (onSuccess) onSuccess();
    } catch {
      setError('Failed to sync valuation figure to database.');
    } finally {
      setSyncingValuation(false);
    }
  };

  const handleUnmap = async (mappingId: string) => {
    if (
      !mappingId ||
      !window.confirm('Unbind this transaction from the sub-ledger?')
    )
      return;
    setUnmappingId(mappingId);
    try {
      await subledgerApi.unmapTransaction({ mapping_id: mappingId });
      await fetchData();
      if (onSuccess) onSuccess();
    } catch {
      setError('Failed to unmap transaction record.');
    } finally {
      setUnmappingId(null);
    }
  };

  const handleExportCSV = () => {
    if (!transactions.length && !currentAsset) return;

    const escapeCSV = (val: any) =>
      `"${String(val ?? '').replace(/"/g, '""')}"`;
    const headers = [
      'Date',
      'Entry Source',
      'Source Entity',
      'Direction',
      'Debit (INR)',
      'Credit (INR)',
      'Narration',
    ];

    const rows = transactions.map((tx) => {
      const isInflow = checkIsInflow(tx);
      const rowAmt = Math.abs(Number(tx.credit || tx.debit || tx.amount || 0));
      return [
        tx.transaction_date,
        tx.is_cash_entry ? 'DIRECT CASH' : 'BANK STAGING',
        tx.source_asset_code || currentAsset.asset_code,
        tx.source_asset_name || currentAsset.name,
        isInflow ? 'INFLOW (CREDIT)' : 'OUTFLOW (DEBIT)',
        isInflow ? '0.00' : rowAmt.toFixed(2),
        isInflow ? rowAmt.toFixed(2) : '0.00',
        tx.narration ||
          (typeof tx.remarks === 'string'
            ? tx.remarks
            : JSON.stringify(tx.remarks)),
      ];
    });

    const csvContent = [
      headers.map(escapeCSV).join(','),
      ...rows.map((r) => r.map(escapeCSV).join(',')),
    ].join('\r\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute(
      'download',
      `Statement_${currentAsset.asset_code}_${new Date().toISOString().slice(0, 10)}.csv`
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return {
    state: {
      loading,
      syncingValuation,
      currentAsset,
      childAssets,
      transactions,
      unmappingId,
      error,
      isCashFloat,
      nodeType,
      baseAcquisitionCost,
      totalInflows,
      totalOutflows,
      netRealizedYield,
      calculatedValuation,
      savedDbValuation,
      needsValuationSync,
    },
    actions: {
      handleManualSyncValuation,
      handleUnmap,
      handleExportCSV,
    },
  };
}
