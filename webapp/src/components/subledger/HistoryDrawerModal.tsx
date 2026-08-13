import React, { useEffect, useState } from 'react';
import { subledgerApi } from '../../api/subledger';
import type { AssetSubLedgerNode } from '../../api/subledger';

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

  useEffect(() => {
    if (isOpen && asset) {
      setLoading(true);
      subledgerApi
        .getAssetById(asset.id)
        .then((data) => setAssetDetails(data))
        .catch((err) => console.error('Failed to load asset history:', err))
        .finally(() => setLoading(false));
    }
  }, [isOpen, asset]);

  if (!isOpen) return null;

  const currentAsset = assetDetails || asset;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/40 backdrop-blur-[2px] transition-all">
      {/* Clickable Backdrop Overlay to close */}
      <div className="absolute inset-0" onClick={onClose} />

      {/* Slide-over Panel Content */}
      <div className="relative z-10 w-full max-w-xl bg-slate-900 border-l border-slate-800/80 p-6 h-full overflow-y-auto text-slate-100 shadow-2xl flex flex-col justify-between">
        <div>
          {/* Header */}
          <div className="flex justify-between items-start border-b border-slate-800 pb-4">
            <div>
              <span className="text-xs text-amber-400 font-mono font-bold uppercase tracking-wider">
                🏛️ General Ledger & Sub-Ledger Traceability
              </span>
              <h2 className="text-xl font-bold text-white mt-1">
                {currentAsset.name}{' '}
                <span className="font-mono text-xs text-emerald-400">
                  ({currentAsset.asset_code})
                </span>
              </h2>
            </div>
            <button
              onClick={onClose}
              className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
            >
              ✕
            </button>
          </div>

          {/* Taxonomy & Sub-Ledger Mapping Card */}
          <div className="mt-4 rounded-lg bg-slate-950 p-4 border border-slate-800/80 space-y-2 text-xs">
            <h3 className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">
              Chart of Accounts Lineage
            </h3>

            <div className="grid grid-cols-2 gap-2 pt-1 font-mono text-[11px]">
              <div>
                <span className="text-slate-500 block text-[10px]">
                  PRIMARY GL ACCOUNT
                </span>
                <span className="text-amber-400 font-bold">
                  {currentAsset.linked_gl_account
                    ? `GL: ${currentAsset.linked_gl_account}`
                    : 'Unassigned GL'}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px]">CATEGORY</span>
                <span className="text-slate-200">
                  {currentAsset.category_display || currentAsset.category}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px]">
                  CURRENT VALUATION
                </span>
                <span className="text-emerald-400 font-bold">
                  ₹{Number(currentAsset.current_valuation).toLocaleString('en-IN')}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px]">
                  OWNERSHIP SHARE
                </span>
                <span className="text-slate-200">
                  {currentAsset.ownership_share_pct || 100}% ({currentAsset.ownership_type})
                </span>
              </div>
            </div>
          </div>

          {/* Bound Sub-Ledger Transaction History */}
          <div className="mt-6">
            <h3 className="text-xs font-bold uppercase text-slate-400 tracking-wider">
              Bound Bank Staging Transactions
            </h3>

            {loading ? (
              <div className="p-8 text-center text-xs text-slate-500">
                ⚡ Loading sub-ledger journal history...
              </div>
            ) : (
              <div className="mt-3 space-y-2">
                {/* Registered Operational Accounts Status */}
                <div className="rounded-lg bg-slate-950/60 p-3 border border-slate-800/60 space-y-2">
                  <span className="text-[11px] font-bold text-slate-400 uppercase">
                    Mapped Sub-Ledger Accounts ({currentAsset.operational_accounts.length})
                  </span>
                  {currentAsset.operational_accounts.length === 0 ? (
                    <p className="text-xs text-slate-600">
                      No active utility mappings found.
                    </p>
                  ) : (
                    <ul className="space-y-1">
                      {currentAsset.operational_accounts.map((op) => (
                        <li
                          key={op.id}
                          className="text-xs text-slate-300 flex justify-between font-mono"
                        >
                          <span>
                            • {op.provider_name} ({op.consumer_identifier})
                          </span>
                          <span className="text-emerald-400">
                            [{op.matching_keyword}]
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {/* Audit Trail Note */}
                <div className="rounded-lg bg-slate-800/30 p-3 border border-slate-700/30 text-xs text-slate-400 space-y-1">
                  <p className="font-semibold text-slate-300">
                    💡 Audit Verification
                  </p>
                  <p className="text-[11px]">
                    All bank staging candidate bindings automatically reflect debits under this asset's General Ledger Taxonomy line item.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-slate-800 pt-4 mt-6 flex justify-end">
          <button
            onClick={onClose}
            className="rounded-lg bg-slate-800 px-4 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 transition-colors"
          >
            Close History
          </button>
        </div>
      </div>
    </div>
  );
};