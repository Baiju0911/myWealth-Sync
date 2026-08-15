import React, { useEffect, useState } from 'react';
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
  const [assetDetails, setAssetDetails] = useState<AssetSubLedgerNode | null>(null);
  const [transactions, setTransactions] = useState<MappedTransaction[]>([]);
  const [unmappingId, setUnmappingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
      console.error('Failed to load asset history:', err);
      setError('Failed to fetch asset sub-ledger statement.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen && asset) {
      fetchData();
    }
  }, [isOpen, asset?.id]);

  const handleUnmap = async (mappingId: string) => {
    if (!mappingId) return;
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

  if (!isOpen) return null;

  const currentAsset = assetDetails || asset;

  const acquisitionCost = Number(currentAsset.acquisition_cost || 0);
  const totalMappedOutflows = transactions.reduce((acc, curr) => acc + (curr.debit || 0), 0);
  const totalCostBasis = acquisitionCost + totalMappedOutflows;

  return (
    <div 
      className="fixed inset-0 z-50 flex justify-end bg-slate-950/50 backdrop-blur-sm transition-all"
      onClick={(e) => {
        e.stopPropagation();
        onClose();
      }}
    >
      {/* Slide-over Panel Content */}
      <div 
        className="relative z-10 w-full max-w-2xl bg-slate-900 border-l border-slate-800 p-6 h-full overflow-y-auto text-slate-100 shadow-2xl flex flex-col justify-between font-sans"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="space-y-5">
          {/* Header */}
          <div className="flex justify-between items-start border-b border-slate-800 pb-4">
            <div>
              <span className="text-xs text-amber-400 font-mono font-bold uppercase tracking-wider">
                🏛️ Sub-Ledger Statement & Audit Trail
              </span>
              <h2 className="text-xl font-bold text-white mt-1">
                {currentAsset.name}{' '}
                <span className="font-mono text-xs text-emerald-400">
                  ({currentAsset.asset_code})
                </span>
              </h2>
            </div>
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

          {/* Asset Capital & Outflow Summary Cards */}
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-lg bg-slate-950 p-3 border border-slate-800">
              <span className="text-[10px] text-slate-500 font-mono block">ACQUISITION COST</span>
              <span className="text-sm font-bold text-slate-200 font-mono">
                ₹{acquisitionCost.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>
            <div className="rounded-lg bg-slate-950 p-3 border border-slate-800">
              <span className="text-[10px] text-slate-500 font-mono block">BOUND OUTFLOWS</span>
              <span className="text-sm font-bold text-emerald-400 font-mono">
                ₹{totalMappedOutflows.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>
            <div className="rounded-lg bg-slate-950 p-3 border border-slate-800">
              <span className="text-[10px] text-slate-500 font-mono block">TOTAL INVESTMENT</span>
              <span className="text-sm font-bold text-cyan-400 font-mono">
                ₹{totalCostBasis.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>
          </div>

          {/* Lineage & Operational Meta */}
          <div className="rounded-lg bg-slate-950/60 p-3.5 border border-slate-800/80 space-y-2 text-xs">
            <div className="flex justify-between items-center border-b border-slate-800/60 pb-2">
              <span className="text-slate-400 font-semibold uppercase text-[10px] tracking-wider font-mono">
                Chart of Accounts Lineage
              </span>
              <span className="font-mono text-[11px] text-amber-400 font-bold">
                {currentAsset.linked_gl_account ? `GL: ${currentAsset.linked_gl_account}` : 'Unassigned GL'}
              </span>
            </div>

            {currentAsset.operational_accounts && currentAsset.operational_accounts.length > 0 && (
              <div className="pt-1 space-y-1">
                <span className="text-[10px] text-slate-500 block uppercase font-mono">Mapped Operational Accounts</span>
                <div className="flex flex-wrap gap-1.5">
                  {currentAsset.operational_accounts.map((op) => (
                    <span
                      key={op.id}
                      className="inline-flex items-center gap-1.5 rounded bg-slate-800/80 px-2 py-0.5 text-[11px] font-mono text-slate-300 border border-slate-700/50"
                    >
                      <span>{op.provider_name}</span>
                      <span className="text-emerald-400 font-bold">[{op.matching_keyword}]</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Bound Staging Ledger Statement Table */}
          <div>
            <div className="flex justify-between items-center mb-2">
              <h3 className="text-xs font-bold uppercase text-slate-400 tracking-wider font-mono">
                Bound Bank Staging Entries ({transactions.length})
              </h3>
              <span className="text-[11px] font-mono text-slate-500">Node 99 Cleared Entries</span>
            </div>

            {error && (
              <div className="rounded-lg bg-rose-500/10 p-2.5 text-xs text-rose-400 border border-rose-500/20 font-mono mb-3">
                {error}
              </div>
            )}

            {loading ? (
              <div className="p-8 text-center text-xs text-slate-500 font-mono">
                ⚡ Fetching sub-ledger transaction statement...
              </div>
            ) : transactions.length === 0 ? (
              <div className="p-8 text-center rounded-xl border border-dashed border-slate-800 bg-slate-950/40 text-xs text-slate-500 space-y-1 font-mono">
                <p className="font-semibold text-slate-400">No transactions bound to this sub-ledger yet.</p>
                <p className="text-[11px]">Use the Candidate Matcher to search bank staging lines and bind payments.</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-[380px] overflow-y-auto pr-1">
                {transactions.map((tx) => {
                  const parseNarration = () => {
                    if (!tx.remarks) return 'No narration available';
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

                  return (
                    <div
                      key={tx.journal_id}
                      className="flex items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-950 p-3 hover:border-slate-700 transition-colors"
                    >
                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-bold text-slate-200">
                            {tx.transaction_date}
                          </span>
                          <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 font-mono text-[10px] font-bold text-emerald-400 border border-emerald-500/20">
                            CLEARED
                          </span>
                        </div>
                        <p
                          className="font-mono text-[11px] text-slate-300 line-clamp-2 break-all leading-tight"
                          title={narration}
                        >
                          {narration}
                        </p>
                      </div>

                      <div className="flex shrink-0 flex-col items-end justify-between pl-3 border-l border-slate-800">
                        <span className="font-mono text-xs font-bold text-emerald-400">
                          ₹{Number(tx.debit || tx.credit || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>

                        {tx.mapping_id && (
                          <button
                            type="button"
                            onClick={() => handleUnmap(tx.mapping_id)}
                            disabled={isDisconnecting}
                            className="mt-1.5 rounded bg-rose-600/20 text-rose-400 border border-rose-500/30 px-2 py-0.5 text-[10px] font-bold hover:bg-rose-600 hover:text-white transition-colors disabled:opacity-50 cursor-pointer font-mono"
                          >
                            {isDisconnecting ? 'Removing...' : 'Unmap'}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-slate-800 pt-4 mt-6 flex justify-between items-center">
          <span className="text-[11px] text-slate-500 font-mono">
            Audited Ledger Sheet • Node 99
          </span>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onClose();
            }}
            className="rounded-lg bg-slate-800 px-4 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 transition-colors cursor-pointer font-mono"
          >
            Close Statement
          </button>
        </div>
      </div>
    </div>
  );
};