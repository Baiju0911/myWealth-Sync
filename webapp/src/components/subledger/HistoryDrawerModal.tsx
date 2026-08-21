import React, { useEffect, useState } from 'react';
import { Download, ExternalLink, AlertCircle, FileText, CheckCircle2, Trash2, RefreshCw } from 'lucide-react';
import { subledgerApi } from '../../api/subledger';
import type { AssetSubLedgerNode } from '../../api/subledger';

interface MappedTransaction {
  mapping_id: string;
  journal_id: string;
  row_identifier: string;
  transaction_date: string;
  debit: number;
  credit: number;
  remarks: string | Record<string, any>;
  user_note?: string;
  is_cash_entry?: boolean;
  mapped_at: string | null;
  source_asset_code?: string;
  source_asset_name?: string;
  is_child_tx?: boolean;
}

interface HistoryDrawerModalProps {
  isOpen: boolean;
  onClose: () => void;
  asset: AssetSubLedgerNode;
  onSuccess?: () => void;
}

export const HistoryDrawerModal: React.FC<HistoryDrawerModalProps> = ({
  isOpen,
  onClose,
  asset,
  onSuccess,
}) => {
  const [loading, setLoading] = useState<boolean>(true);
  const [syncingValuation, setSyncingValuation] = useState<boolean>(false);
  const [assetDetails, setAssetDetails] = useState<AssetSubLedgerNode | null>(null);
  const [childAssets, setChildAssets] = useState<AssetSubLedgerNode[]>([]);
  const [transactions, setTransactions] = useState<MappedTransaction[]>([]);
  const [unmappingId, setUnmappingId] = useState<string | null>(null);
  const [resettingCost, setResettingCost] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedTxForDetail, setSelectedTxForDetail] = useState<MappedTransaction | null>(null);

  const fetchData = async () => {
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
        const parentId = a.parent_asset_id || a.parent_asset?.id || a.parent_asset;
        return parentId === asset.id;
      });
      setChildAssets(children);

      const parentTxs: MappedTransaction[] = (mappedRes.mapped_transactions || []).map((tx: any) => ({
        ...tx,
        source_asset_code: details.asset_code,
        source_asset_name: details.name,
        is_child_tx: false,
      }));

      const childTxPromises = children.map(async (child) => {
        try {
          const childMapped = await subledgerApi.getMappedTransactions(child.id);
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
      const combinedChildTxs = childTxsArrays.flat();

      const allCombinedTxs = [...parentTxs, ...combinedChildTxs].sort((a, b) => {
        if (a.is_child_tx !== b.is_child_tx) {
          return a.is_child_tx ? 1 : -1;
        }
        return new Date(b.transaction_date).getTime() - new Date(a.transaction_date).getTime();
      });

      setTransactions(allCombinedTxs);
    } catch (err: any) {
      console.error('Failed to load sub-ledger statement:', err);
      setError('Failed to fetch sub-ledger statement.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen && asset) {
      fetchData();
    }
  }, [isOpen, asset?.id]);

  const currentAsset = assetDetails || asset;

  const nodeType = (
    (currentAsset as any).category_type ||
    (currentAsset as any).category_detail?.category_type ||
    (currentAsset.asset_code?.startsWith('INC') ? 'INCOME' : currentAsset.asset_code?.startsWith('EXP') ? 'EXPENSE' : 'ASSET')
  ).toUpperCase();

  const statusStr = String(currentAsset.status || '').toUpperCase();

  const isMaturedOrClosed =
    statusStr === 'MATURED' ||
    statusStr === 'CLOSED' ||
    statusStr === 'LIQUIDATED' ||
    statusStr === 'SOLD' ||
    statusStr === 'WRITTEN_OFF';

  // 🟢 1. STRICT NODE TYPE CHECK (Income/Expense Stream vs Physical Asset)
  const isIncomeOrExpense =
    nodeType === 'INCOME' ||
    nodeType === 'EXPENSE' ||
    currentAsset.asset_code?.startsWith('INC') ||
    currentAsset.asset_code?.startsWith('EXP');

  // Income/Expense nodes ALWAYS have ₹0.00 Acquisition Baseline Cost
  const baseAcquisitionCost = isIncomeOrExpense
    ? 0
    : Number(currentAsset.acquisition_cost || 0) +
      childAssets
        .filter((child: any) => {
          const childType = String(
            child.category_type || child.category_detail?.category_type || ''
          ).toUpperCase();
          return childType === 'ASSET' || child.asset_code?.startsWith('AST');
        })
        .reduce((sum, child) => sum + Number(child.acquisition_cost || 0), 0);

  // 🟢 2. PURE OPERATING CASH FLOWS
  const totalInflows = transactions
    .filter((tx) => Number(tx.credit) > 0)
    .reduce((acc, curr) => acc + Number(curr.credit || 0), 0);

  const totalOutflows = transactions
    .filter((tx) => Number(tx.debit) > 0)
    .reduce((acc, curr) => acc + Number(curr.debit || 0), 0);

  const netRealizedYield = totalInflows - totalOutflows;

  // 🟢 3. VALUATION DISTINCTION
  // Income nodes display their Net Yield as current operating stream balance.
  // Physical Asset nodes calculate Total Carrying Valuation = Acquisition Cost + Net Yield.
  const calculatedValuation = isIncomeOrExpense
    ? netRealizedYield
    : baseAcquisitionCost + netRealizedYield;

  const savedDbValuation = Number(currentAsset.current_valuation || 0);

  // 🟢 4. SYNC BANNER DISPLAY CONDITION
  // Sync banner ONLY applies to Physical Master Assets (NEVER to Income/Expense Streams)
  const needsValuationSync =
    !isIncomeOrExpense &&
    Math.abs(calculatedValuation - savedDbValuation) > 0.01;

  // 🟢 5. MANUAL USER-INITIATED SYNC HANDLER (MASTER ASSET ONLY)
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
    } catch (err) {
      console.error('Failed to sync valuation:', err);
      setError('Failed to sync valuation figure to database.');
    } finally {
      setSyncingValuation(false);
    }
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    if (isOpen) window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const handleUnmap = async (mappingId: string) => {
    if (!mappingId) return;
    if (isMaturedOrClosed) {
      alert('Unmapping is locked on matured or closed sub-ledger nodes.');
      return;
    }
    if (!window.confirm('Are you sure you want to unbind this transaction from the sub-ledger?')) return;

    setUnmappingId(mappingId);
    try {
      await subledgerApi.unmapTransaction({ mapping_id: mappingId });
      await fetchData();
      if (onSuccess) onSuccess();
    } catch (err) {
      console.error('Failed to unmap transaction:', err);
      setError('Failed to unmap transaction record.');
    } finally {
      setUnmappingId(null);
    }
  };

  const handleRemoveCapitalCost = async () => {
    if (!currentAsset?.id) return;
    if (!window.confirm('Are you sure you want to reset the baseline Acquisition Cost to ₹0.00?')) return;

    setResettingCost(true);
    try {
      await subledgerApi.updateAsset(currentAsset.id, {
        acquisition_cost: 0,
      });
      await fetchData();
      if (onSuccess) onSuccess();
    } catch (err) {
      console.error('Failed to reset acquisition cost:', err);
      setError('Failed to reset acquisition cost.');
    } finally {
      setResettingCost(false);
    }
  };

  const handleExportCSV = () => {
    if (!transactions.length && !currentAsset) return;

    const escapeCSV = (value: any) => {
      const str = String(value ?? '');
      return `"${str.replace(/"/g, '""')}"`;
    };

    const metadataRows = [
      ['SUB-LEDGER AUDIT STATEMENT & LEDGER RECONCILIATION'],
      ['Master Asset Code', currentAsset.asset_code],
      ['Master Asset Name', currentAsset.name],
      ['Sub-Components Count', childAssets.length],
      ['Sub-Ledger Category', nodeType],
      ['Lifecycle Status', currentAsset.status || 'ACTIVE'],
      ['GL Account Lineage', currentAsset.linked_gl_account || 'Unassigned'],
      ['Acquisition Cost Baseline (INR)', baseAcquisitionCost.toFixed(2)],
      ['Total Cumulative Inflows (INR)', totalInflows.toFixed(2)],
      ['Total Operating Outflows (INR)', totalOutflows.toFixed(2)],
      ['Net Yield Recognized (INR)', netRealizedYield.toFixed(2)],
      ['Current Valuation (INR)', calculatedValuation.toFixed(2)],
      ['Statement Export Date', new Date().toISOString()],
      [],
    ];

    const headers = [
      'Transaction Date',
      'Entry Source',
      'Source Tier',
      'Source Entity Code',
      'Source Entity Name',
      'Journal ID',
      'Row Identifier Hash',
      'Direction',
      'Debit Amount (INR)',
      'Credit Amount (INR)',
      'Narration / Audit Remarks',
    ];

    const dataRows = transactions.map((tx) => {
      const isCash = tx.is_cash_entry || !tx.row_identifier;
      const parsedNote =
        tx.user_note ||
        (typeof tx.remarks === 'object'
          ? JSON.stringify(tx.remarks)
          : tx.remarks) ||
        '';

      return [
        tx.transaction_date,
        isCash ? 'DIRECT CASH' : 'BANK STAGING',
        tx.is_child_tx ? 'SUB-ASSET' : 'MASTER ASSET',
        tx.source_asset_code || currentAsset.asset_code,
        tx.source_asset_name || currentAsset.name,
        tx.journal_id,
        tx.row_identifier || 'N/A (CASH)',
        tx.credit > 0 ? 'INFLOW (CREDIT)' : 'OUTFLOW (DEBIT)',
        Number(tx.debit || 0).toFixed(2),
        Number(tx.credit || 0).toFixed(2),
        parsedNote,
      ];
    });

    const csvContent = [
      ...metadataRows.map((r) => r.map(escapeCSV).join(',')),
      headers.map(escapeCSV).join(','),
      ...dataRows.map((r) => r.map(escapeCSV).join(',')),
    ].join('\r\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute(
      'download',
      `SubLedger_Statement_${currentAsset.asset_code}_${new Date().toISOString().slice(0, 10)}.csv`
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  if (!isOpen) return null;

  const masterAssetNote =
    (currentAsset as any).user_note ||
    currentAsset.metadata_payload?.user_note ||
    '';

  const isBankRowMissing = (currentAsset as any).is_bank_row_missing;
  const fundingSourceDisplay =
    (currentAsset as any).acquisition_funding_source_display ||
    (currentAsset as any).acquisition_funding_source ||
    'DIRECT_CASH';

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-slate-950/70 backdrop-blur-sm transition-all font-sans"
      onClick={(e) => {
        e.stopPropagation();
        onClose();
      }}
    >
      <div
        className="relative z-10 w-full max-w-2xl bg-slate-900 border-l border-slate-800 p-6 h-full overflow-y-auto text-slate-100 shadow-2xl flex flex-col justify-between font-mono"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="space-y-5">
          {/* Header */}
          <div className="flex justify-between items-start border-b border-slate-800 pb-4">
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs text-amber-400 font-mono font-bold uppercase tracking-wider">
                  🏛️ {nodeType} Sub-Ledger Statement
                </span>

                {childAssets.length > 0 && (
                  <span className="rounded bg-cyan-500/20 px-2 py-0.5 font-mono text-[10px] font-bold text-cyan-300 border border-cyan-500/40">
                    📦 {childAssets.length} SUB-COMPONENTS ROLLUP
                  </span>
                )}

                {isMaturedOrClosed ? (
                  <span className="rounded bg-amber-500/20 px-2 py-0.5 font-mono text-[10px] font-bold text-amber-300 border border-amber-500/40 flex items-center gap-1">
                    🏁 MATURED / CLOSED
                  </span>
                ) : (
                  <span className="rounded bg-emerald-500/20 px-2 py-0.5 font-mono text-[10px] font-bold text-emerald-300 border border-emerald-500/40">
                    ⚡ ACTIVE
                  </span>
                )}
              </div>

              <h2 className="text-xl font-bold text-white mt-1 flex items-center gap-2">
                <span>{currentAsset.name}</span>
                <span className="font-mono text-xs text-emerald-400 font-normal">
                  ({currentAsset.asset_code})
                </span>
              </h2>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleExportCSV}
                disabled={transactions.length === 0 && !currentAsset}
                className="flex items-center gap-1 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 px-2.5 py-1 rounded text-xs font-mono font-bold transition-all disabled:opacity-40 cursor-pointer"
                title="Export Sub-Ledger Statement to CSV"
              >
                <Download className="w-3.5 h-3.5 text-cyan-400" />
                <span>Export Statement</span>
              </button>
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors cursor-pointer"
              >
                ✕
              </button>
            </div>
          </div>

          {/* Banners */}
          {isMaturedOrClosed && (
            <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 p-3 text-xs font-mono text-amber-300 flex items-start gap-2 shadow-md">
              <AlertCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-bold uppercase text-[10px] tracking-wider text-amber-400 block">
                  🏁 Node Lifecycle Status: {currentAsset.status}
                </span>
                <p className="mt-0.5 text-slate-300 leading-normal">
                  This sub-ledger entity is closed or matured. Historical audit statements remain accessible, but binding new entries is locked.
                </p>
              </div>
            </div>
          )}

          {masterAssetNote && (
            <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3 text-xs font-mono flex items-start gap-2 text-emerald-300">
              <FileText className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-bold uppercase text-[10px] tracking-wider text-emerald-400 block">
                  {nodeType} Audit Note
                </span>
                <p className="mt-0.5 text-slate-200">{masterAssetNote}</p>
              </div>
            </div>
          )}

          {/* 🟢 VALUATION OUT-OF-SYNC WARNING BANNER (MASTER PHYSICAL ASSETS ONLY) */}
          {needsValuationSync && !isMaturedOrClosed && (
            <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 p-3 text-xs font-mono text-amber-300 flex items-start justify-between gap-3 shadow-md">
              <div className="flex items-start gap-2">
                <AlertCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                <div>
                  <span className="font-bold uppercase text-[10px] tracking-wider text-amber-400 block">
                    ⚠️ Master Asset Valuation Out of Sync
                  </span>
                  <p className="mt-0.5 text-slate-200 leading-normal">
                    Database Valuation is <span className="text-amber-300 font-bold">₹{savedDbValuation.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>. Live carrying valuation (Acquisition + Yield) is <span className="text-emerald-400 font-bold">₹{calculatedValuation.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>.
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={handleManualSyncValuation}
                disabled={syncingValuation}
                className="shrink-0 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 px-2.5 py-1 text-[10px] font-bold hover:bg-amber-500 hover:text-slate-950 transition-colors cursor-pointer font-mono flex items-center gap-1 disabled:opacity-50"
                title="Update master asset database valuation to match calculated live ledger"
              >
                <RefreshCw className={`w-3 h-3 ${syncingValuation ? 'animate-spin' : ''}`} />
                <span>{syncingValuation ? 'Syncing...' : '⚡ Sync Valuation'}</span>
              </button>
            </div>
          )}

          {/* 🟢 5-COLUMN FINANCIAL METRICS SUMMARY BAR */}
          <div className="grid grid-cols-5 gap-2 font-mono">
            <div className="rounded-lg bg-slate-950 p-2.5 border border-slate-800">
              <span className="text-[9px] text-slate-500 block uppercase tracking-wider">
                Acquisition Cost
              </span>
              <span className="text-xs font-bold text-amber-400 block mt-0.5">
                ₹{baseAcquisitionCost.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>

            <div className="rounded-lg bg-slate-950 p-2.5 border border-slate-800">
              <span className="text-[9px] text-slate-500 block uppercase tracking-wider">
                Cumulative Inflows
              </span>
              <span className="text-xs font-bold text-cyan-400 block mt-0.5">
                ₹{totalInflows.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>

            <div className="rounded-lg bg-slate-950 p-2.5 border border-slate-800">
              <span className="text-[9px] text-slate-500 block uppercase tracking-wider">
                Operating Outflows
              </span>
              <span className="text-xs font-bold text-rose-400 block mt-0.5">
                ₹{totalOutflows.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>

            <div className="rounded-lg bg-slate-950 p-2.5 border border-slate-800">
              <span className="text-[9px] text-slate-500 block uppercase tracking-wider">
                Net Yield
              </span>
              <span className={`text-xs font-bold block mt-0.5 ${netRealizedYield >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                ₹{netRealizedYield.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>

            <div className="rounded-lg bg-slate-950 p-2.5 border border-emerald-500/30">
              <span className="text-[9px] text-emerald-400/80 block uppercase tracking-wider font-bold">
                Current Valuation
              </span>
              <span className="text-xs font-bold text-emerald-300 block mt-0.5">
                ₹{calculatedValuation.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>
          </div>

          {/* Lineage */}
          <div className="rounded-lg bg-slate-950/60 p-3 border border-slate-800/80 space-y-2 text-xs font-mono">
            <div className="flex justify-between items-center border-b border-slate-800/60 pb-2">
              <span className="text-slate-400 font-semibold uppercase text-[10px] tracking-wider">
                Chart of Accounts Lineage
              </span>
              <span className="text-[11px] text-amber-400 font-bold">
                {currentAsset.linked_gl_account ? `GL: ${currentAsset.linked_gl_account}` : 'Unassigned GL'}
              </span>
            </div>

            {(currentAsset as any).parent_asset_detail && (
              <div className="pt-1 flex items-center justify-between text-[11px]">
                <span className="text-slate-500">Underlying Master Asset:</span>
                <span className="text-emerald-400 font-bold">
                  [{(currentAsset as any).parent_asset_detail.asset_code}] {(currentAsset as any).parent_asset_detail.name}
                </span>
              </div>
            )}
          </div>

          {/* 🟢 DIRECT CAPITAL BASELINE CARD (MASTER PHYSICAL ASSETS ONLY) */}
          {!isIncomeOrExpense && Number(currentAsset.acquisition_cost) > 0 && isBankRowMissing && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-950/20 p-3 font-mono flex items-center justify-between">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 px-1.5 py-0.5 text-[10px] font-bold">
                    💵 DIRECT CASH / CAPITAL BASELINE
                  </span>
                  <span className="text-xs font-bold text-slate-200">
                    {currentAsset.acquisition_date || 'N/A'}
                  </span>
                </div>
                <p className="text-[11px] text-slate-400">
                  Origin: {fundingSourceDisplay} (Non-Bank Staging Purchase Baseline)
                </p>
              </div>

              <div className="flex items-center gap-3">
                <span className="text-xs font-bold text-amber-400">
                  ₹{Number(currentAsset.acquisition_cost).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>

                {!isMaturedOrClosed && (
                  <button
                    type="button"
                    onClick={handleRemoveCapitalCost}
                    disabled={resettingCost}
                    className="rounded bg-rose-600/20 text-rose-300 border border-rose-500/30 px-2 py-1 text-[10px] font-bold hover:bg-rose-600 hover:text-white transition-colors cursor-pointer flex items-center gap-1 disabled:opacity-50"
                    title="Reset capital baseline cost to ₹0.00"
                  >
                    <Trash2 className="w-3 h-3" />
                    <span>{resettingCost ? 'Removing...' : 'Remove Cost'}</span>
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Bound Transactions List */}
          <div>
            <div className="flex justify-between items-center mb-2">
              <h3 className="text-xs font-bold uppercase text-slate-400 tracking-wider font-mono flex items-center gap-2">
                <span>Bound Transactions ({transactions.length})</span>
              </h3>
              <span className="text-[11px] font-mono text-slate-500">
                Cleared Ledger Entries
              </span>
            </div>

            {error && (
              <div className="rounded-lg bg-rose-500/10 p-2.5 text-xs text-rose-400 border border-rose-500/20 font-mono mb-3 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {loading ? (
              <div className="p-8 text-center text-xs text-slate-500 font-mono">
                ⚡ Fetching sub-ledger transaction statement...
              </div>
            ) : transactions.length === 0 ? (
              <div className="p-8 text-center rounded-xl border border-dashed border-slate-800 bg-slate-950/40 text-xs text-slate-500 space-y-1 font-mono">
                <p className="font-semibold text-slate-400">
                  No transactions bound to this sub-ledger yet.
                </p>
                <p className="text-[11px]">
                  Use Candidate Matcher to search bank staging lines and bind entries.
                </p>
              </div>
            ) : (
              <div className="space-y-2 max-h-95 overflow-y-auto pr-1">
                {transactions.map((tx) => {
                  const parseNarration = () => {
                    if (tx.user_note && tx.user_note.trim().length > 0) return tx.user_note;
                    if (!tx.remarks) return masterAssetNote || 'No narration available';
                    if (typeof tx.remarks === 'string') {
                      try {
                        const parsed = JSON.parse(tx.remarks);
                        return parsed.display_text || parsed.narration || parsed.payee || tx.remarks;
                      } catch {
                        return tx.remarks;
                      }
                    }
                    return tx.remarks.display_text || tx.remarks.narration || JSON.stringify(tx.remarks);
                  };

                  const narration = parseNarration();
                  const isDisconnecting = unmappingId === tx.mapping_id;
                  const txAmount = Number(tx.credit || tx.debit || 0);

                  const isCash = tx.is_cash_entry || !tx.row_identifier;

                  return (
                    <div
                      key={tx.journal_id}
                      className={`flex items-center justify-between gap-3 rounded-lg border p-3 transition-colors ${
                        tx.is_child_tx
                          ? 'bg-slate-950/90 border-emerald-500/30 hover:border-emerald-500/60'
                          : 'bg-slate-950 border-slate-800 hover:border-slate-700'
                      }`}
                    >
                      <div className="min-w-0 flex-1 space-y-1 font-mono">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs font-bold text-slate-200">
                            {tx.transaction_date}
                          </span>

                          <span
                            className={`rounded px-1.5 py-0.5 text-[10px] font-bold border ${
                              isCash
                                ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                                : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                            }`}
                          >
                            {isCash ? '💵 DIRECT CASH' : '🏦 BANK STAGING'}
                          </span>

                          <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-bold text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
                            <CheckCircle2 className="w-2.5 h-2.5" />
                            {tx.credit > 0 ? 'INFLOW (CREDIT)' : 'OUTFLOW (DEBIT)'}
                          </span>

                          {tx.is_child_tx ? (
                            <span className="rounded bg-cyan-950/90 border border-cyan-500/40 px-2 py-0.5 text-[9px] font-bold text-cyan-300">
                              ↳ SUB-ASSET: [{tx.source_asset_code}] {tx.source_asset_name}
                            </span>
                          ) : (
                            <span className="rounded bg-slate-800 border border-slate-700 px-2 py-0.5 text-[9px] font-bold text-slate-300">
                              🏛️ MASTER ASSET DIRECT
                            </span>
                          )}
                        </div>

                        <p
                          className="text-[11px] text-slate-300 line-clamp-2 break-all leading-tight cursor-pointer hover:text-cyan-300 transition-colors"
                          title={narration}
                          onClick={() => setSelectedTxForDetail(tx)}
                        >
                          {narration}
                        </p>
                      </div>

                      <div className="flex shrink-0 flex-col items-end justify-between pl-3 border-l border-slate-800 gap-1 font-mono">
                        <span className={`text-xs font-bold ${tx.credit > 0 ? 'text-emerald-400' : 'text-slate-200'}`}>
                          ₹{txAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>

                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => setSelectedTxForDetail(tx)}
                            className="text-slate-400 hover:text-cyan-300 text-[10px] p-0.5 transition-colors"
                            title="Inspect raw staging details"
                          >
                            <ExternalLink className="w-3 h-3" />
                          </button>

                          {tx.mapping_id && !isMaturedOrClosed && (
                            <button
                              type="button"
                              onClick={() => handleUnmap(tx.mapping_id)}
                              disabled={isDisconnecting}
                              className="rounded bg-rose-600/20 text-rose-400 border border-rose-500/30 px-2 py-0.5 text-[10px] font-bold hover:bg-rose-600 hover:text-white transition-colors disabled:opacity-50 cursor-pointer font-mono"
                            >
                              {isDisconnecting ? 'Removing...' : 'Unmap'}
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Detail Modal */}
        {selectedTxForDetail && (
          <div
            className="fixed inset-0 z-60 bg-black/80 flex items-center justify-center p-4 font-sans"
            onClick={() => setSelectedTxForDetail(null)}
          >
            <div
              className="bg-slate-900 border border-slate-700 p-5 rounded-xl max-w-lg w-full font-mono text-xs space-y-3 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex justify-between items-center border-b border-slate-800 pb-2">
                <span className="font-bold text-cyan-400">
                  Raw Staging Metadata
                </span>
                <button
                  type="button"
                  onClick={() => setSelectedTxForDetail(null)}
                  className="text-slate-400 hover:text-white"
                >
                  ✕
                </button>
              </div>
              <div className="space-y-1.5 text-slate-300">
                {selectedTxForDetail.source_asset_code && (
                  <div>
                    <span className="text-slate-500">Source Entity:</span>{' '}
                    <span className="text-cyan-400">
                      [{selectedTxForDetail.source_asset_code}] {selectedTxForDetail.source_asset_name}
                    </span>
                  </div>
                )}
                <div>
                  <span className="text-slate-500">Entry Source:</span>{' '}
                  <span className={selectedTxForDetail.is_cash_entry || !selectedTxForDetail.row_identifier ? 'text-amber-400 font-bold' : 'text-emerald-400 font-bold'}>
                    {selectedTxForDetail.is_cash_entry || !selectedTxForDetail.row_identifier ? '💵 DIRECT CASH ENTRY' : '🏦 BANK STAGING ROW'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Row Identifier:</span>{' '}
                  <span className="break-all">{selectedTxForDetail.row_identifier || 'N/A (Cash Entry)'}</span>
                </div>
                <div>
                  <span className="text-slate-500">Journal ID:</span>{' '}
                  {selectedTxForDetail.journal_id}
                </div>
                <div>
                  <span className="text-slate-500">Transaction Date:</span>{' '}
                  {selectedTxForDetail.transaction_date}
                </div>
                <div>
                  <span className="text-slate-500">Amount:</span> ₹
                  {Number(selectedTxForDetail.credit || selectedTxForDetail.debit || 0).toLocaleString('en-IN')}
                </div>
                {selectedTxForDetail.user_note && (
                  <div>
                    <span className="text-slate-500">User Audit Note:</span>{' '}
                    <span className="text-emerald-400">
                      {selectedTxForDetail.user_note}
                    </span>
                  </div>
                )}
                <div className="p-2 bg-slate-950 rounded border border-slate-800 text-[11px] break-all">
                  <span className="text-slate-500 block mb-1">
                    Narration Payload:
                  </span>
                  {typeof selectedTxForDetail.remarks === 'object'
                    ? JSON.stringify(selectedTxForDetail.remarks, null, 2)
                    : selectedTxForDetail.remarks}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="border-t border-slate-800 pt-4 mt-6 flex justify-between items-center font-mono">
          <span className="text-[11px] text-slate-500">
            Audited {nodeType} Sub-Ledger Statement
          </span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-slate-800 px-4 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 transition-colors cursor-pointer"
          >
            Close Statement
          </button>
        </div>
      </div>
    </div>
  );
};

export default HistoryDrawerModal;