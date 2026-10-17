// webapp/src/components/subledger/HistoryDrawerModal.tsx
import React, { useEffect, useState } from 'react';
import { Download, AlertCircle, RefreshCw } from 'lucide-react';
import type { AssetSubLedgerNode } from '../../api/subledger';
import { useHistoryDrawerData, type MappedTransaction } from './history/useHistoryDrawerData';
import { HistoryMetricsHeader } from './history/HistoryMetricsHeader';
import { StagingDetailModal } from './history/StagingDetailModal';
import { SubledgerTransactionCard } from './modules/SubledgerTransactionCard';

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
  const { state, actions } = useHistoryDrawerData(asset, isOpen, onSuccess);
  const [selectedTxForDetail, setSelectedTxForDetail] = useState<MappedTransaction | null>(null);

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

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-slate-950/70 backdrop-blur-sm transition-all font-sans"
      onClick={onClose}
    >
      <div
        className="relative z-10 w-full max-w-2xl bg-slate-900 border-l border-slate-800 p-6 h-full overflow-y-auto text-slate-100 shadow-2xl flex flex-col justify-between font-mono"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="space-y-4">
          {/* Header */}
          <div className="flex justify-between items-start border-b border-slate-800 pb-3">
            <div>
              <span className="text-xs text-amber-400 font-bold uppercase tracking-wider block">
                {state.isCashFloat ? '💵 Cash Float Statement' : `🏛️ ${state.nodeType} Sub-Ledger Statement`}
              </span>
              <h2 className="text-lg font-bold text-white mt-1 flex items-center gap-2">
                <span>{state.currentAsset.name}</span>
                <span className="text-xs text-emerald-400 font-normal">({state.currentAsset.asset_code})</span>
              </h2>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={actions.handleExportCSV}
                disabled={state.transactions.length === 0}
                className="flex items-center gap-1 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 px-2.5 py-1 rounded text-xs font-bold transition-all disabled:opacity-40 cursor-pointer"
              >
                <Download className="w-3.5 h-3.5 text-cyan-400" />
                <span>Export</span>
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

          {/* Out of sync warning for physical capital assets */}
          {state.needsValuationSync && (
            <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 p-2.5 text-xs text-amber-300 flex items-center justify-between gap-3 shadow-md">
              <div className="flex items-center gap-2 min-w-0">
                <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
                <span className="truncate">
                  Valuation out of sync: DB is ₹{state.savedDbValuation.toLocaleString('en-IN')}, Live is ₹
                  {state.calculatedValuation.toLocaleString('en-IN')}
                </span>
              </div>
              <button
                type="button"
                onClick={actions.handleManualSyncValuation}
                disabled={state.syncingValuation}
                className="shrink-0 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 px-2 py-0.5 text-[10px] font-bold hover:bg-amber-500 hover:text-slate-950 transition-colors cursor-pointer flex items-center gap-1"
              >
                <RefreshCw className={`w-3 h-3 ${state.syncingValuation ? 'animate-spin' : ''}`} />
                <span>Sync</span>
              </button>
            </div>
          )}

          {/* 4-Card Clean Metrics Header */}
          <HistoryMetricsHeader
            isCashFloat={state.isCashFloat}
            baseAcquisitionCost={state.baseAcquisitionCost}
            totalInflows={state.totalInflows}
            totalOutflows={state.totalOutflows}
            calculatedValuation={state.calculatedValuation}
          />

          {/* GL Lineage Tag */}
          <div className="flex justify-between items-center text-[11px] bg-slate-950/60 px-3 py-1.5 rounded border border-slate-800/80">
            <span className="text-slate-500 uppercase">GL Lineage:</span>
            <span className="text-amber-400 font-bold">
              {state.currentAsset.linked_gl_account ? `GL: ${state.currentAsset.linked_gl_account}` : 'Unassigned'}
            </span>
          </div>

          {/* Bound Transactions Stream */}
          <div className="space-y-2">
            <div className="flex justify-between items-center pt-1">
              <h3 className="text-xs font-bold uppercase text-slate-400 tracking-wider">
                Bound Transactions ({state.transactions.length})
              </h3>
              <span className="text-[10px] text-slate-500">Cleared Entries</span>
            </div>

            {state.loading ? (
              <div className="py-12 text-center text-xs text-slate-500">⚡ Loading ledger statement...</div>
            ) : state.transactions.length === 0 ? (
              <div className="py-12 text-center rounded-xl border border-dashed border-slate-800 bg-slate-950/40 text-xs text-slate-500">
                No transactions bound to this sub-ledger yet.
              </div>
            ) : (
              <div className="space-y-2 max-h-[48vh] overflow-y-auto pr-1">
                {state.transactions.map((tx) => (
                  <SubledgerTransactionCard
                    key={tx.mapping_id || tx.journal_id}
                    tx={tx}
                    isMaturedOrClosed={false}
                    unmappingId={state.unmappingId}
                    onUnmap={actions.handleUnmap}
                    onInspect={setSelectedTxForDetail}
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-slate-800 pt-3 mt-4 flex justify-between items-center">
          <span className="text-[10px] text-slate-500">
            Audited {state.isCashFloat ? 'Cash Float' : state.nodeType} Statement
          </span>
          <button
            type="button"
            onClick={onClose}
            className="rounded bg-slate-800 px-3 py-1 text-xs font-semibold text-slate-300 hover:bg-slate-700 cursor-pointer transition-colors"
          >
            Close Statement
          </button>
        </div>

        <StagingDetailModal tx={selectedTxForDetail} onClose={() => setSelectedTxForDetail(null)} />
      </div>
    </div>
  );
};

export default HistoryDrawerModal;