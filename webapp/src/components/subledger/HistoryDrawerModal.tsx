import React, { useEffect, useState } from 'react';
import { Download, ExternalLink, AlertCircle, FileText, CheckCircle2, RefreshCw } from 'lucide-react';
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
  mapped_at: string | null;
}

interface HistoryDrawerModalProps {
  isOpen: boolean;
  onClose: () => void;
  asset: AssetSubLedgerNode;
}

export const HistoryDrawerModal: React.FC<HistoryDrawerModalProps> = ({
  isOpen,
  onClose,
  asset,
}) => {
  const [loading, setLoading] = useState<boolean>(true);
  const [syncingCost, setSyncingCost] = useState<boolean>(false);
  const [assetDetails, setAssetDetails] = useState<AssetSubLedgerNode | null>(null);
  const [transactions, setTransactions] = useState<MappedTransaction[]>([]);
  const [unmappingId, setUnmappingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedTxForDetail, setSelectedTxForDetail] = useState<MappedTransaction | null>(null);

  // Isolated ESC Key Listener
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

  const fetchData = async () => {
    if (!asset?.id) return;
    setLoading(true);
    setError(null);

    try {
      const [details, mappedRes] = await Promise.all([
        subledgerApi.getAssetById(asset.id),
        subledgerApi.getMappedTransactions(asset.id),
      ]);

      setAssetDetails(details);
      setTransactions(mappedRes.mapped_transactions || []);
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

  // 🎯 Safely resolve Node Category Type (ASSET, INCOME, EXPENSE)
  const nodeType = (
    (currentAsset as any).category_type ||
    (currentAsset as any).category_detail?.category_type ||
    (currentAsset.asset_code?.startsWith('INC') ? 'INCOME' : currentAsset.asset_code?.startsWith('EXP') ? 'EXPENSE' : 'ASSET')
  ).toUpperCase();

  const handleUnmap = async (mappingId: string) => {
    if (!mappingId) return;
    if (!window.confirm('Are you sure you want to unbind this transaction from the sub-ledger?')) return;

    setUnmappingId(mappingId);
    try {
      await subledgerApi.unmapTransaction({ mapping_id: mappingId });
      await fetchData();
    } catch (err) {
      console.error('Failed to unmap transaction:', err);
      setError('Failed to unmap transaction record.');
    } finally {
      setUnmappingId(null);
    }
  };

  // Sync Baseline Value
  const handleAutoSyncBaselineCost = async () => {
    if (!currentAsset?.id || totalBoundAmount <= 0) return;
    setSyncingCost(true);
    setError(null);

    try {
      await subledgerApi.updateAsset(currentAsset.id, {
        acquisition_cost: totalBoundAmount,
        current_valuation: totalBoundAmount,
      });
      await fetchData();
    } catch (err) {
      console.error('Failed to sync baseline cost:', err);
      setError('Failed to sync baseline figure.');
    } finally {
      setSyncingCost(false);
    }
  };

  // Calculations based on mode
  const baseTargetCost = Number(currentAsset.acquisition_cost || 0);

  // Sum Credits for INCOME, Sum Debits for ASSET and EXPENSE
  const totalBoundAmount = transactions.reduce((acc, curr) => {
    if (nodeType === 'INCOME') {
      return acc + (Number(curr.credit) > 0 ? Number(curr.credit) : Number(curr.debit));
    }
    return acc + Number(curr.debit || 0);
  }, 0);

  const currentValuation = Number(currentAsset.current_valuation || 0);

  // Mismatch & Variance Logic
  const hasValueDiscrepancy = transactions.length > 0 && baseTargetCost !== totalBoundAmount;
  const varianceAmount = Math.abs(totalBoundAmount - baseTargetCost);
  const variancePercentage = baseTargetCost > 0 ? (varianceAmount / baseTargetCost) * 100 : 0;

  // CSV Audit Exporter
  const handleExportCSV = () => {
    if (!transactions.length && !currentAsset) return;

    const masterNote =
      (currentAsset as any).user_note ||
      currentAsset.metadata_payload?.user_note ||
      'N/A';

    const masterMetaData = [
      [`${nodeType} SUB-LEDGER AUDIT STATEMENT & LEDGER RECONCILIATION`],
      [`Entity Code`, currentAsset.asset_code],
      [`Entity Name`, `"${currentAsset.name}"`],
      [`Mode`, nodeType],
      [`GL Account Lineage`, currentAsset.linked_gl_account || 'Unassigned'],
      [`Baseline Value (INR)`, baseTargetCost],
      [`Total Realized / Bound Amount (INR)`, totalBoundAmount],
      [`Master Audit Note`, `"${String(masterNote).replace(/"/g, '""')}"`],
      [`Statement Generated At`, new Date().toISOString()],
      [],
    ];

    const tableHeaders = [
      'Transaction Date',
      'Journal ID',
      'Row Identifier Hash',
      'Direction',
      'Debit (INR)',
      'Credit (INR)',
      'Narration / Audit Note',
      'Bound Timestamp',
    ];

    const tableRows = transactions.map((tx) => {
      const parsedNote =
        tx.user_note ||
        (typeof tx.remarks === 'object'
          ? JSON.stringify(tx.remarks)
          : tx.remarks) ||
        '';

      return [
        tx.transaction_date,
        tx.journal_id,
        tx.row_identifier,
        tx.credit > 0 ? 'CREDIT (INFLOW)' : 'DEBIT (OUTFLOW)',
        tx.debit || 0,
        tx.credit || 0,
        `"${String(parsedNote).replace(/"/g, '""')}"`,
        tx.mapped_at || 'N/A',
      ];
    });

    const csvLines = [
      ...masterMetaData.map((row) => row.join(',')),
      tableHeaders.join(','),
      ...tableRows.map((row) => row.join(',')),
    ];

    const csvContent = 'data:text/csv;charset=utf-8,' + csvLines.join('\n');
    const encodedUri = encodeURI(csvContent);

    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute(
      'download',
      `SubLedger_Statement_${nodeType}_${currentAsset.asset_code}_${new Date()
        .toISOString()
        .slice(0, 10)}.csv`
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (!isOpen) return null;

  const masterAssetNote =
    (currentAsset as any).user_note ||
    currentAsset.metadata_payload?.user_note ||
    '';

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-slate-950/70 backdrop-blur-sm transition-all font-sans"
      onClick={(e) => {
        e.stopPropagation();
        onClose();
      }}
    >
      <div
        className="relative z-10 w-full max-w-2xl bg-slate-900 border-l border-slate-800 p-6 h-full overflow-y-auto text-slate-100 shadow-2xl flex flex-col justify-between"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="space-y-5">
          {/* Header */}
          <div className="flex justify-between items-start border-b border-slate-800 pb-4">
            <div>
              <span className="text-xs text-amber-400 font-mono font-bold uppercase tracking-wider">
                🏛️ {nodeType} Sub-Ledger Statement & Audit Trail
              </span>
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
                onClick={(e) => {
                  e.stopPropagation();
                  onClose();
                }}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors cursor-pointer"
              >
                ✕
              </button>
            </div>
          </div>

          {/* User Audit Note Banner */}
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

          {/* Mode-Aware Discrepancy & Realization Banner */}
          {hasValueDiscrepancy && (
            <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 p-3 text-xs font-mono text-amber-300 flex items-start justify-between gap-3 shadow-md">
              <div className="flex items-start gap-2">
                <AlertCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                <div>
                  <span className="font-bold uppercase text-[10px] tracking-wider text-amber-400 block">
                    {nodeType === 'INCOME'
                      ? '📈 Income Realization Progress'
                      : nodeType === 'EXPENSE'
                      ? '📊 Expense Budget Variance'
                      : '⚠️ Asset Cost Basis Discrepancy'}
                  </span>
                  <p className="mt-0.5 text-slate-200 leading-normal">
                    {nodeType === 'INCOME' ? (
                      <>
                        Cleared income received (<span className="text-emerald-400 font-bold">₹{totalBoundAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>) vs target yield (<span className="text-amber-300 font-bold">₹{baseTargetCost.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>). Variance: <span className="text-cyan-400 font-bold">₹{varianceAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })} ({variancePercentage.toFixed(1)}%)</span>.
                      </>
                    ) : nodeType === 'EXPENSE' ? (
                      <>
                        Total spent (<span className="text-rose-400 font-bold">₹{totalBoundAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>) vs budget cap (<span className="text-amber-300 font-bold">₹{baseTargetCost.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>). Variance: <span className="text-cyan-400 font-bold">₹{varianceAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })} ({variancePercentage.toFixed(1)}%)</span>.
                      </>
                    ) : (
                      <>
                        Cleared outflows (<span className="text-emerald-400 font-bold">₹{totalBoundAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>) vs baseline (<span className="text-amber-300 font-bold">₹{baseTargetCost.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>). Discrepancy: <span className="text-cyan-400 font-bold">₹{varianceAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })} ({variancePercentage.toFixed(1)}%)</span>.
                      </>
                    )}
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={handleAutoSyncBaselineCost}
                disabled={syncingCost}
                className="shrink-0 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 px-2.5 py-1 text-[10px] font-bold hover:bg-amber-500 hover:text-slate-950 transition-colors cursor-pointer font-mono flex items-center gap-1 disabled:opacity-50"
                title="Update baseline to match cleared transactions"
              >
                <RefreshCw className={`w-3 h-3 ${syncingCost ? 'animate-spin' : ''}`} />
                <span>{syncingCost ? 'Syncing...' : '⚡ Sync Baseline'}</span>
              </button>
            </div>
          )}

          {/* Mode-Aware Metric Summary Cards */}
          <div className="grid grid-cols-4 gap-2 font-mono">
            {/* Card 1 */}
            <div className={`rounded-lg p-2.5 border transition-colors ${hasValueDiscrepancy ? 'bg-amber-500/10 border-amber-500/40 text-amber-300' : 'bg-slate-950 border-slate-800 text-slate-200'}`}>
              <span className="text-[9px] text-slate-500 block uppercase">
                {nodeType === 'INCOME' ? 'Base Target Yield' : nodeType === 'EXPENSE' ? 'Budget Cap' : 'Acquisition Cost'}
              </span>
              <span className="text-xs font-bold block mt-0.5">
                ₹{baseTargetCost.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>

            {/* Card 2 */}
            <div className="rounded-lg bg-slate-950 p-2.5 border border-slate-800">
              <span className="text-[9px] text-slate-500 block uppercase">
                {nodeType === 'INCOME' ? 'Realized Inflows' : nodeType === 'EXPENSE' ? 'YTD Outflows' : 'Bound Outflows'}
              </span>
              <span className="text-xs font-bold text-emerald-400 block mt-0.5">
                ₹{totalBoundAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>

            {/* Card 3 */}
            <div className="rounded-lg bg-slate-950 p-2.5 border border-slate-800">
              <span className="text-[9px] text-slate-500 block uppercase">
                {nodeType === 'INCOME' ? 'Realized YTD' : nodeType === 'EXPENSE' ? 'Total Spend' : 'Total Investment'}
              </span>
              <span className="text-xs font-bold text-cyan-400 block mt-0.5">
                ₹{(totalBoundAmount > 0 ? totalBoundAmount : baseTargetCost).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>

            {/* Card 4 */}
            <div className="rounded-lg bg-slate-950 p-2.5 border border-slate-800">
              <span className="text-[9px] text-slate-500 block uppercase">
                {nodeType === 'INCOME' ? 'Annual Target' : nodeType === 'EXPENSE' ? 'Annual Cap' : 'Market Valuation'}
              </span>
              <span className="text-xs font-bold text-emerald-300 block mt-0.5">
                ₹{currentValuation.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>
          </div>

          {/* Lineage Info */}
          <div className="rounded-lg bg-slate-950/60 p-3 border border-slate-800/80 space-y-2 text-xs font-mono">
            <div className="flex justify-between items-center border-b border-slate-800/60 pb-2">
              <span className="text-slate-400 font-semibold uppercase text-[10px] tracking-wider">
                Chart of Accounts Lineage
              </span>
              <span className="text-[11px] text-amber-400 font-bold">
                {currentAsset.linked_gl_account ? `GL: ${currentAsset.linked_gl_account}` : 'Unassigned GL'}
              </span>
            </div>

            {/* Linked Parent Asset Indicator */}
            {(currentAsset as any).parent_asset_detail && (
              <div className="pt-1 flex items-center justify-between text-[11px]">
                <span className="text-slate-500">Underlying Master Asset:</span>
                <span className="text-emerald-400 font-bold">
                  [{(currentAsset as any).parent_asset_detail.asset_code}] {(currentAsset as any).parent_asset_detail.name}
                </span>
              </div>
            )}
          </div>

          {/* Bound Staging Ledger Entries Table */}
          <div>
            <div className="flex justify-between items-center mb-2">
              <h3 className="text-xs font-bold uppercase text-slate-400 tracking-wider font-mono">
                Bound {nodeType === 'INCOME' ? 'Income Credits' : 'Expense / Outflow Lines'} ({transactions.length})
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
                  No {nodeType.toLowerCase()} transactions bound to this sub-ledger yet.
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

                  return (
                    <div
                      key={tx.journal_id}
                      className="flex items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-950 p-3 hover:border-slate-700 transition-colors"
                    >
                      <div className="min-w-0 flex-1 space-y-1 font-mono">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-slate-200">
                            {tx.transaction_date}
                          </span>
                          <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-bold text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
                            <CheckCircle2 className="w-2.5 h-2.5" />
                            {tx.credit > 0 ? 'INFLOW (CREDIT)' : 'OUTFLOW (DEBIT)'}
                          </span>
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

                          {tx.mapping_id && (
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

        {/* Raw Staging Inspector Sub-Modal */}
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
                  Raw Bank Staging Metadata
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
                <div>
                  <span className="text-slate-500">Row Identifier:</span>{' '}
                  <span className="break-all">{selectedTxForDetail.row_identifier}</span>
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
            onClick={(e) => {
              e.stopPropagation();
              onClose();
            }}
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




// import React, { useEffect, useState } from 'react';
// import { Download, ExternalLink, AlertCircle, ArrowUpRight, ArrowDownRight, FileText, CheckCircle2, RefreshCw, TrendingUp } from 'lucide-react';
// import { subledgerApi } from '../../api/subledger';
// import type { AssetSubLedgerNode } from '../../api/subledger';

// interface MappedTransaction {
//   mapping_id: string;
//   journal_id: string;
//   row_identifier: string;
//   transaction_date: string;
//   debit: number;
//   credit: number;
//   remarks: string | Record<string, any>;
//   user_note?: string; // Optional mapping-level user note
//   mapped_at: string | null;
// }

// interface HistoryDrawerModalProps {
//   isOpen: boolean;
//   onClose: () => void;
//   asset: AssetSubLedgerNode;
// }

// export const HistoryDrawerModal: React.FC<HistoryDrawerModalProps> = ({
//   isOpen,
//   onClose,
//   asset,
// }) => {
//   const [loading, setLoading] = useState<boolean>(true);
//   const [syncingCost, setSyncingCost] = useState<boolean>(false);
//   const [assetDetails, setAssetDetails] = useState<AssetSubLedgerNode | null>(null);
//   const [transactions, setTransactions] = useState<MappedTransaction[]>([]);
//   const [unmappingId, setUnmappingId] = useState<string | null>(null);
//   const [error, setError] = useState<string | null>(null);
//   const [selectedTxForDetail, setSelectedTxForDetail] = useState<MappedTransaction | null>(null);

//   // Isolated ESC Key Listener
//   useEffect(() => {
//     const handleKeyDown = (e: KeyboardEvent) => {
//       if (e.key === 'Escape') {
//         e.stopPropagation();
//         onClose();
//       }
//     };
//     if (isOpen) window.addEventListener('keydown', handleKeyDown);
//     return () => window.removeEventListener('keydown', handleKeyDown);
//   }, [isOpen, onClose]);

//   const fetchData = async () => {
//     if (!asset?.id) return;
//     setLoading(true);
//     setError(null);

//     try {
//       const [details, mappedRes] = await Promise.all([
//         subledgerApi.getAssetById(asset.id),
//         subledgerApi.getMappedTransactions(asset.id),
//       ]);

//       setAssetDetails(details);
//       setTransactions(mappedRes.mapped_transactions || []);
//     } catch (err: any) {
//       console.error('Failed to load asset history:', err);
//       setError('Failed to fetch asset sub-ledger statement.');
//     } finally {
//       setLoading(false);
//     }
//   };

//   useEffect(() => {
//     if (isOpen && asset) {
//       fetchData();
//     }
//   }, [isOpen, asset?.id]);

//   const handleUnmap = async (mappingId: string) => {
//     if (!mappingId) return;
//     if (!window.confirm('Are you sure you want to unbind this bank transaction from the asset?')) return;

//     setUnmappingId(mappingId);
//     try {
//       await subledgerApi.unmapTransaction({ mapping_id: mappingId });
//       await fetchData();
//     } catch (err) {
//       console.error('Failed to unmap transaction:', err);
//       setError('Failed to unmap transaction record.');
//     } finally {
//       setUnmappingId(null);
//     }
//   };

//   // One-Click Auto-Sync Baseline Cost Handler
//   const handleAutoSyncBaselineCost = async () => {
//     if (!currentAsset?.id || totalMappedOutflows <= 0) return;
//     setSyncingCost(true);
//     setError(null);

//     try {
//       await subledgerApi.updateAsset(currentAsset.id, {
//         acquisition_cost: totalMappedOutflows,
//         current_valuation: totalMappedOutflows,
//       });
//       await fetchData();
//     } catch (err) {
//       console.error('Failed to sync baseline cost:', err);
//       setError('Failed to sync master asset baseline cost.');
//     } finally {
//       setSyncingCost(false);
//     }
//   };

//   // Comprehensive CSV Sub-Ledger Audit Exporter
//   const handleExportCSV = () => {
//     if (!transactions.length && !currentAsset) return;

//     const currentAssetObj = assetDetails || asset;
//     const masterNote =
//       (currentAssetObj as any).user_note ||
//       currentAssetObj.metadata_payload?.user_note ||
//       'N/A';

//     // Master Header Section
//     const masterMetaData = [
//       ['SUB-LEDGER AUDIT STATEMENT & LEDGER RECONCILIATION'],
//       [`Asset Code`, currentAssetObj.asset_code],
//       [`Asset Name`, `"${currentAssetObj.name}"`],
//       [`GL Account Lineage`, currentAssetObj.linked_gl_account || 'Unassigned'],
//       [`Category`, currentAssetObj.category_display || currentAssetObj.category || 'N/A'],
//       [`Baseline Acquisition Cost (INR)`, acquisitionCost],
//       [`Total Bound Cleared Outflows (INR)`, totalMappedOutflows],
//       [`Total Deployed Capital (INR)`, totalCostBasis],
//       [`Excess Paid Over Baseline (INR)`, excessPaidAmount],
//       [`Current Market Valuation (INR)`, currentValuation],
//       [`Master Audit Note`, `"${masterNote.replace(/"/g, '""')}"`],
//       [`Statement Generated At`, new Date().toISOString()],
//       [], // Blank separator row
//     ];

//     // Transaction Data Rows
//     const tableHeaders = [
//       'Transaction Date',
//       'Journal ID',
//       'Row Identifier Hash',
//       'Direction',
//       'Debit (INR)',
//       'Credit (INR)',
//       'Narration / Audit Note',
//       'Bound Timestamp',
//     ];

//     const tableRows = transactions.map((tx) => {
//       const parsedNote =
//         tx.user_note ||
//         (typeof tx.remarks === 'object'
//           ? JSON.stringify(tx.remarks)
//           : tx.remarks) ||
//         '';

//       return [
//         tx.transaction_date,
//         tx.journal_id,
//         tx.row_identifier,
//         tx.debit > 0 ? 'DEBIT (OUTFLOW)' : 'CREDIT (INFLOW)',
//         tx.debit || 0,
//         tx.credit || 0,
//         `"${String(parsedNote).replace(/"/g, '""')}"`,
//         tx.mapped_at || 'N/A',
//       ];
//     });

//     const csvLines = [
//       ...masterMetaData.map((row) => row.join(',')),
//       tableHeaders.join(','),
//       ...tableRows.map((row) => row.join(',')),
//     ];

//     const csvContent = 'data:text/csv;charset=utf-8,' + csvLines.join('\n');
//     const encodedUri = encodeURI(csvContent);

//     const link = document.createElement('a');
//     link.setAttribute('href', encodedUri);
//     link.setAttribute(
//       'download',
//       `SubLedger_Statement_${currentAssetObj.asset_code}_${new Date()
//         .toISOString()
//         .slice(0, 10)}.csv`
//     );
//     document.body.appendChild(link);
//     link.click();
//     document.body.removeChild(link);
//   };

//   if (!isOpen) return null;

//   const currentAsset = assetDetails || asset;

//   // Master asset user note extraction with structural fallbacks
//   const masterAssetNote =
//     (currentAsset as any).user_note ||
//     currentAsset.metadata_payload?.user_note ||
//     '';

//   const acquisitionCost = Number(currentAsset.acquisition_cost || 0);
//   const totalMappedOutflows = transactions.reduce(
//     (acc, curr) => acc + Number(curr.debit || 0),
//     0
//   );

//   // Progressive Investment / Cost Basis Calculation
//   const totalCostBasis =
//     totalMappedOutflows > 0 ? totalMappedOutflows : acquisitionCost;

//   const currentValuation = Number(currentAsset.current_valuation || 0);

//   // ⚠️ Baseline Discrepancy & Excess Investment Calculations
//   const hasCostDiscrepancy =
//     transactions.length > 0 && acquisitionCost !== totalMappedOutflows;
//   const discrepancyAmount = Math.abs(acquisitionCost - totalMappedOutflows);

//   // Calculate excess capital paid beyond initial baseline
//   const isPaidOverBaseline =
//     transactions.length > 0 && totalMappedOutflows > acquisitionCost;
//   const excessPaidAmount = totalMappedOutflows - acquisitionCost;
//   const overBaselinePercentage =
//     acquisitionCost > 0 ? (excessPaidAmount / acquisitionCost) * 100 : 0;

//   // Variance & Funding Calculation
//   const isPartiallyOutflowed =
//     totalMappedOutflows > 0 && totalMappedOutflows < acquisitionCost;

//   const fundingVariancePercentage =
//     acquisitionCost > 0
//       ? ((totalMappedOutflows - acquisitionCost) / acquisitionCost) * 100
//       : 0;

//   const unrealizedGain = currentValuation - totalCostBasis;
//   const roiPercentage =
//     totalCostBasis > 0 ? (unrealizedGain / totalCostBasis) * 100 : 0;

//   return (
//     <div
//       className="fixed inset-0 z-50 flex justify-end bg-slate-950/70 backdrop-blur-sm transition-all font-sans"
//       onClick={(e) => {
//         e.stopPropagation();
//         onClose();
//       }}
//     >
//       {/* Slide-over Panel Content */}
//       <div
//         className="relative z-10 w-full max-w-2xl bg-slate-900 border-l border-slate-800 p-6 h-full overflow-y-auto text-slate-100 shadow-2xl flex flex-col justify-between"
//         onClick={(e) => e.stopPropagation()}
//       >
//         <div className="space-y-5">
//           {/* Header */}
//           <div className="flex justify-between items-start border-b border-slate-800 pb-4">
//             <div>
//               <span className="text-xs text-amber-400 font-mono font-bold uppercase tracking-wider">
//                 🏛️ Sub-Ledger Statement & Audit Trail
//               </span>
//               <h2 className="text-xl font-bold text-white mt-1 flex items-center gap-2">
//                 <span>{currentAsset.name}</span>
//                 <span className="font-mono text-xs text-emerald-400 font-normal">
//                   ({currentAsset.asset_code})
//                 </span>
//               </h2>
//             </div>
//             <div className="flex items-center gap-2">
//               <button
//                 type="button"
//                 onClick={handleExportCSV}
//                 disabled={transactions.length === 0 && !currentAsset}
//                 className="flex items-center gap-1 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 px-2.5 py-1 rounded text-xs font-mono font-bold transition-all disabled:opacity-40 cursor-pointer"
//                 title="Export Sub-Ledger Audit Trail to CSV"
//               >
//                 <Download className="w-3.5 h-3.5 text-cyan-400" />
//                 <span>Export Statement</span>
//               </button>
//               <button
//                 type="button"
//                 onClick={(e) => {
//                   e.stopPropagation();
//                   onClose();
//                 }}
//                 className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors cursor-pointer"
//               >
//                 ✕
//               </button>
//             </div>
//           </div>

//           {/* Master Asset Audit Note Banner */}
//           {masterAssetNote && (
//             <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3 text-xs font-mono flex items-start gap-2 text-emerald-300">
//               <FileText className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
//               <div>
//                 <span className="font-bold uppercase text-[10px] tracking-wider text-emerald-400 block">
//                   Master Asset Audit Note
//                 </span>
//                 <p className="mt-0.5 text-slate-200">{masterAssetNote}</p>
//               </div>
//             </div>
//           )}

//           {/* ⚠️ Audit Baseline Discrepancy & Over-Baseline Payment Banner */}
//           {hasCostDiscrepancy && (
//             <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 p-3 text-xs font-mono text-amber-300 flex items-start justify-between gap-3 shadow-md">
//               <div className="flex items-start gap-2">
//                 <AlertCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
//                 <div>
//                   <span className="font-bold uppercase text-[10px] tracking-wider text-amber-400 block">
//                     ⚠️ Asset Cost Basis Discrepancy Detected
//                   </span>
//                   <p className="mt-0.5 text-slate-200 leading-normal">
//                     Cleared outflows (<span className="text-emerald-400 font-bold">₹{totalMappedOutflows.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>) 
//                     exceed baseline cost (<span className="text-amber-300 font-bold">₹{acquisitionCost.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>) 
//                     by <span className="text-cyan-400 font-bold">+₹{excessPaidAmount.toLocaleString('en-IN', { minimumFractionDigits: 2 })} (+{overBaselinePercentage.toFixed(1)}%)</span>.
//                   </p>
//                 </div>
//               </div>

//               <button
//                 type="button"
//                 onClick={handleAutoSyncBaselineCost}
//                 disabled={syncingCost}
//                 className="shrink-0 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 px-2.5 py-1 text-[10px] font-bold hover:bg-amber-500 hover:text-slate-950 transition-colors cursor-pointer font-mono flex items-center gap-1 disabled:opacity-50"
//                 title="Update master asset baseline acquisition cost to match cleared outflows"
//               >
//                 <RefreshCw className={`w-3 h-3 ${syncingCost ? 'animate-spin' : ''}`} />
//                 <span>{syncingCost ? 'Syncing...' : '⚡ Sync Baseline Cost'}</span>
//               </button>
//             </div>
//           )}

//           {/* Capital & Outflow Summary Cards */}
//           <div className="grid grid-cols-4 gap-2 font-mono">
//             {/* Acquisition Cost Card */}
//             <div
//               className={`rounded-lg p-2.5 border transition-colors ${
//                 hasCostDiscrepancy
//                   ? 'bg-amber-500/10 border-amber-500/40 text-amber-300'
//                   : 'bg-slate-950 border-slate-800 text-slate-200'
//               }`}
//             >
//               <div className="flex justify-between items-center">
//                 <span className="text-[9px] text-slate-500 block uppercase">
//                   Acquisition Cost
//                 </span>
//                 {hasCostDiscrepancy && (
//                   <span className="text-[8px] font-bold text-amber-400 bg-amber-500/20 px-1 rounded border border-amber-500/30">
//                     MISMATCH
//                   </span>
//                 )}
//               </div>
//               <span className="text-xs font-bold block mt-0.5">
//                 ₹{acquisitionCost.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
//               </span>
//             </div>

//             {/* Bound Outflows Card */}
//             <div className="rounded-lg bg-slate-950 p-2.5 border border-slate-800">
//               <span className="text-[9px] text-slate-500 block uppercase">
//                 Bound Outflows
//               </span>
//               <span className="text-xs font-bold text-emerald-400 block mt-0.5">
//                 ₹{totalMappedOutflows.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
//               </span>
//             </div>

//             {/* Total Investment Card (with Over-Baseline Badge) */}
//             <div className="rounded-lg bg-slate-950 p-2.5 border border-slate-800">
//               <div className="flex justify-between items-center">
//                 <span className="text-[9px] text-slate-500 block uppercase">
//                   Total Investment
//                 </span>
//                 {isPaidOverBaseline && (
//                   <span
//                     className="text-[8px] font-bold text-cyan-400 bg-cyan-500/20 px-1 rounded border border-cyan-500/30 flex items-center gap-0.5"
//                     title={`Paid ₹${excessPaidAmount.toLocaleString('en-IN')} over baseline`}
//                   >
//                     <TrendingUp className="w-2.5 h-2.5" />
//                     +{overBaselinePercentage.toFixed(1)}%
//                   </span>
//                 )}
//               </div>
//               <span className="text-xs font-bold text-cyan-400 block mt-0.5">
//                 ₹{totalCostBasis.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
//               </span>
//             </div>

//             {/* Market Valuation Card */}
//             <div className="rounded-lg bg-slate-950 p-2.5 border border-slate-800">
//               <span className="text-[9px] text-slate-500 block uppercase">
//                 Market Valuation
//               </span>
//               <div className="flex items-center justify-between mt-0.5">
//                 <span className="text-xs font-bold text-emerald-300">
//                   ₹{currentValuation.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
//                 </span>
//                 {isPartiallyOutflowed ? (
//                   <span
//                     className="inline-flex items-center text-[9px] font-bold px-1 rounded bg-amber-500/20 text-amber-400"
//                     title="Installment / Partial Outflow Execution Progress"
//                   >
//                     {fundingVariancePercentage.toFixed(1)}%
//                   </span>
//                 ) : (
//                   roiPercentage !== 0 && (
//                     <span
//                       className={`inline-flex items-center text-[9px] font-bold px-1 rounded ${
//                         unrealizedGain >= 0
//                           ? 'bg-emerald-500/20 text-emerald-400'
//                           : 'bg-rose-500/20 text-rose-400'
//                       }`}
//                     >
//                       {unrealizedGain >= 0 ? (
//                         <ArrowUpRight className="w-2.5 h-2.5" />
//                       ) : (
//                         <ArrowDownRight className="w-2.5 h-2.5" />
//                       )}
//                       {Math.abs(roiPercentage).toFixed(1)}%
//                     </span>
//                   )
//                 )}
//               </div>
//             </div>
//           </div>

//           {/* Lineage & Operational Meta */}
//           <div className="rounded-lg bg-slate-950/60 p-3 border border-slate-800/80 space-y-2 text-xs">
//             <div className="flex justify-between items-center border-b border-slate-800/60 pb-2">
//               <span className="text-slate-400 font-semibold uppercase text-[10px] tracking-wider font-mono">
//                 Chart of Accounts Lineage
//               </span>
//               <span className="font-mono text-[11px] text-amber-400 font-bold">
//                 {currentAsset.linked_gl_account
//                   ? `GL: ${currentAsset.linked_gl_account}`
//                   : 'Unassigned GL'}
//               </span>
//             </div>

//             {currentAsset.operational_accounts &&
//               currentAsset.operational_accounts.length > 0 && (
//                 <div className="pt-1 space-y-1">
//                   <span className="text-[10px] text-slate-500 block uppercase font-mono">
//                     Mapped Operational Accounts
//                   </span>
//                   <div className="flex flex-wrap gap-1.5">
//                     {currentAsset.operational_accounts.map((op) => (
//                       <span
//                         key={op.id}
//                         className="inline-flex items-center gap-1.5 rounded bg-slate-800/80 px-2 py-0.5 text-[11px] font-mono text-slate-300 border border-slate-700/50"
//                       >
//                         <span>{op.provider_name}</span>
//                         <span className="text-emerald-400 font-bold">
//                           [{op.matching_keyword}]
//                         </span>
//                       </span>
//                     ))}
//                   </div>
//                 </div>
//               )}
//           </div>

//           {/* Bound Staging Ledger Statement Table */}
//           <div>
//             <div className="flex justify-between items-center mb-2">
//               <h3 className="text-xs font-bold uppercase text-slate-400 tracking-wider font-mono">
//                 Bound Bank Staging Entries ({transactions.length})
//               </h3>
//               <span className="text-[11px] font-mono text-slate-500">
//                 Node 99 Cleared Entries
//               </span>
//             </div>

//             {error && (
//               <div className="rounded-lg bg-rose-500/10 p-2.5 text-xs text-rose-400 border border-rose-500/20 font-mono mb-3 flex items-center gap-2">
//                 <AlertCircle className="w-4 h-4 shrink-0" />
//                 <span>{error}</span>
//               </div>
//             )}

//             {loading ? (
//               <div className="p-8 text-center text-xs text-slate-500 font-mono">
//                 ⚡ Fetching sub-ledger transaction statement...
//               </div>
//             ) : transactions.length === 0 ? (
//               <div className="p-8 text-center rounded-xl border border-dashed border-slate-800 bg-slate-950/40 text-xs text-slate-500 space-y-1 font-mono">
//                 <p className="font-semibold text-slate-400">
//                   No transactions bound to this sub-ledger yet.
//                 </p>
//                 <p className="text-[11px]">
//                   Use the Candidate Matcher to search bank staging lines and bind payments.
//                 </p>
//               </div>
//             ) : (
//               <div className="space-y-2 max-h-95 overflow-y-auto pr-1">
//                 {transactions.map((tx) => {
//                   const parseNarration = () => {
//                     if (tx.user_note && tx.user_note.trim().length > 0) {
//                       return tx.user_note;
//                     }
//                     if (!tx.remarks)
//                       return masterAssetNote || 'No narration available';
//                     if (typeof tx.remarks === 'string') {
//                       try {
//                         const parsed = JSON.parse(tx.remarks);
//                         return (
//                           parsed.display_text ||
//                           parsed.narration ||
//                           parsed.payee ||
//                           tx.remarks
//                         );
//                       } catch {
//                         return tx.remarks;
//                       }
//                     }
//                     return (
//                       tx.remarks.display_text ||
//                       tx.remarks.narration ||
//                       JSON.stringify(tx.remarks)
//                     );
//                   };

//                   const narration = parseNarration();
//                   const isDisconnecting = unmappingId === tx.mapping_id;

//                   return (
//                     <div
//                       key={tx.journal_id}
//                       className="flex items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-950 p-3 hover:border-slate-700 transition-colors"
//                     >
//                       <div className="min-w-0 flex-1 space-y-1">
//                         <div className="flex items-center gap-2">
//                           <span className="font-mono text-xs font-bold text-slate-200">
//                             {tx.transaction_date}
//                           </span>
//                           <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 font-mono text-[10px] font-bold text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
//                             <CheckCircle2 className="w-2.5 h-2.5" />
//                             CLEARED
//                           </span>
//                         </div>
//                         <p
//                           className="font-mono text-[11px] text-slate-300 line-clamp-2 break-all leading-tight cursor-pointer hover:text-cyan-300 transition-colors"
//                           title={narration}
//                           onClick={() => setSelectedTxForDetail(tx)}
//                         >
//                           {narration}
//                         </p>
//                       </div>

//                       <div className="flex shrink-0 flex-col items-end justify-between pl-3 border-l border-slate-800 gap-1">
//                         <span className="font-mono text-xs font-bold text-emerald-400">
//                           ₹
//                           {Number(tx.debit || tx.credit || 0).toLocaleString(
//                             'en-IN',
//                             { minimumFractionDigits: 2 }
//                           )}
//                         </span>

//                         <div className="flex items-center gap-1">
//                           <button
//                             type="button"
//                             onClick={() => setSelectedTxForDetail(tx)}
//                             className="text-slate-400 hover:text-cyan-300 text-[10px] font-mono p-0.5 transition-colors"
//                             title="Inspect raw staging line details"
//                           >
//                             <ExternalLink className="w-3 h-3" />
//                           </button>

//                           {tx.mapping_id && (
//                             <button
//                               type="button"
//                               onClick={() => handleUnmap(tx.mapping_id)}
//                               disabled={isDisconnecting}
//                               className="rounded bg-rose-600/20 text-rose-400 border border-rose-500/30 px-2 py-0.5 text-[10px] font-bold hover:bg-rose-600 hover:text-white transition-colors disabled:opacity-50 cursor-pointer font-mono"
//                             >
//                               {isDisconnecting ? 'Removing...' : 'Unmap'}
//                             </button>
//                           )}
//                         </div>
//                       </div>
//                     </div>
//                   );
//                 })}
//               </div>
//             )}
//           </div>
//         </div>

//         {/* Raw Staging Line Inspector Sub-Modal */}
//         {selectedTxForDetail && (
//           <div
//             className="fixed inset-0 z-60 bg-black/80 flex items-center justify-center p-4 font-sans"
//             onClick={() => setSelectedTxForDetail(null)}
//           >
//             <div
//               className="bg-slate-900 border border-slate-700 p-5 rounded-xl max-w-lg w-full font-mono text-xs space-y-3 shadow-2xl"
//               onClick={(e) => e.stopPropagation()}
//             >
//               <div className="flex justify-between items-center border-b border-slate-800 pb-2">
//                 <span className="font-bold text-cyan-400">
//                   Raw Bank Staging Metadata
//                 </span>
//                 <button
//                   type="button"
//                   onClick={() => setSelectedTxForDetail(null)}
//                   className="text-slate-400 hover:text-white"
//                 >
//                   ✕
//                 </button>
//               </div>
//               <div className="space-y-1.5 text-slate-300">
//                 <div>
//                   <span className="text-slate-500">Row Identifier:</span>{' '}
//                   <span className="break-all">{selectedTxForDetail.row_identifier}</span>
//                 </div>
//                 <div>
//                   <span className="text-slate-500">Journal ID:</span>{' '}
//                   {selectedTxForDetail.journal_id}
//                 </div>
//                 <div>
//                   <span className="text-slate-500">Transaction Date:</span>{' '}
//                   {selectedTxForDetail.transaction_date}
//                 </div>
//                 <div>
//                   <span className="text-slate-500">Debit Amount:</span> ₹
//                   {Number(selectedTxForDetail.debit).toLocaleString('en-IN')}
//                 </div>
//                 {selectedTxForDetail.user_note && (
//                   <div>
//                     <span className="text-slate-500">User Audit Note:</span>{' '}
//                     <span className="text-emerald-400">
//                       {selectedTxForDetail.user_note}
//                     </span>
//                   </div>
//                 )}
//                 <div className="p-2 bg-slate-950 rounded border border-slate-800 text-[11px] break-all">
//                   <span className="text-slate-500 block mb-1">
//                     Narration Payload:
//                   </span>
//                   {typeof selectedTxForDetail.remarks === 'object'
//                     ? JSON.stringify(selectedTxForDetail.remarks, null, 2)
//                     : selectedTxForDetail.remarks}
//                 </div>
//               </div>
//             </div>
//           </div>
//         )}

//         {/* Footer */}
//         <div className="border-t border-slate-800 pt-4 mt-6 flex justify-between items-center">
//           <span className="text-[11px] text-slate-500 font-mono">
//             Audited Ledger Sheet • Node 99
//           </span>
//           <button
//             type="button"
//             onClick={(e) => {
//               e.stopPropagation();
//               onClose();
//             }}
//             className="rounded-lg bg-slate-800 px-4 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 transition-colors cursor-pointer font-mono"
//           >
//             Close Statement
//           </button>
//         </div>
//       </div>
//     </div>
//   );
// };

// export default HistoryDrawerModal;