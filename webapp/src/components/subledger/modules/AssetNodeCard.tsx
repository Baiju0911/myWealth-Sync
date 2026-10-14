import React, { useState } from 'react';
import type { HierarchyAssetNode } from '../helper/subledgerGrouping';
import type { AssetComplianceSchedule, AssetOperationalAccount } from '../../../api/subledger';
import { inrFormatter } from '../../../utils/classificationHelpers';

interface AssetNodeCardProps {
  asset: HierarchyAssetNode;
  isChild?: boolean;
  metricLabel: string;
  onOpenMatcher: (asset: HierarchyAssetNode, sch?: AssetComplianceSchedule | null, op?: AssetOperationalAccount | null) => void;
  onOpenHistory: (asset: HierarchyAssetNode) => void;
  onEditAsset: (asset: HierarchyAssetNode) => void;
  onDeleteAsset: (id: string, name: string) => void;
  onCreateUtility: (asset: HierarchyAssetNode) => void;
  onEditUtility: (asset: HierarchyAssetNode, op: AssetOperationalAccount) => void;
  onCreateSchedule: (asset: HierarchyAssetNode) => void;
  onEditSchedule: (asset: HierarchyAssetNode, sch: AssetComplianceSchedule) => void;
}

export const AssetNodeCard: React.FC<AssetNodeCardProps> = ({
  asset,
  isChild = false,
  metricLabel,
  onOpenMatcher,
  onOpenHistory,
  onEditAsset,
  onDeleteAsset,
  onCreateUtility,
  onEditUtility,
  onCreateSchedule,
  onEditSchedule,
}) => {
  const isMatured =
    asset.status === 'MATURED' || asset.status === 'CLOSED' || asset.status === 'LIQUIDATED';

  const opCount = asset.operational_accounts?.length || 0;
  const schCount = asset.compliance_schedules?.length || 0;
  const hasOpsOrSchedules = opCount > 0 || schCount > 0;

  // Toggle for operational & schedule details if initially empty
  const [showOpsDrawer, setShowOpsDrawer] = useState<boolean>(hasOpsOrSchedules);

  // Vendor resolution fallback
  const displayVendorName =
    asset.vendor_name ||
    asset.vendor_detail?.name ||
    (typeof asset.vendor === 'string' && asset.vendor.trim().length > 0 ? asset.vendor : null);

  // Mapped transaction reconciliation tracking
  const mappedTotal = Number((asset as any).mapped_transaction_total || (asset as any).mapped_total || 0);
  const currentValuation = Number(asset.current_valuation || 0);

  // Sub-Asset Node Display (Compact Teal Row)
  if (isChild) {
    return (
      <div className="flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-lg bg-slate-950/90 border border-teal-500/30 border-l-4 border-l-teal-400 hover:border-teal-400/60 transition-all font-mono shadow-sm">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="text-teal-400 font-bold text-xs shrink-0">↳</span>
          <span className="rounded bg-teal-500/10 px-2 py-0.5 text-[10px] font-bold text-teal-300 border border-teal-500/30 shrink-0">
            {asset.asset_code}
          </span>
          <span className="text-xs font-bold text-slate-100 truncate">{asset.name}</span>
          {displayVendorName && (
            <span className="text-[10px] text-slate-400 font-mono hidden sm:inline">
              [{displayVendorName}]
            </span>
          )}
          {asset.metadata_payload && Object.keys(asset.metadata_payload).length > 0 && (
            <span className="text-[10px] text-slate-400 truncate hidden md:inline font-sans">
              ({Object.entries(asset.metadata_payload).map(([k, v]) => `${k}: ${v}`).join(', ')})
            </span>
          )}
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <span className="text-xs font-bold text-teal-300">
            {inrFormatter.format(currentValuation)}
          </span>

          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => onOpenMatcher(asset)}
              className="rounded bg-teal-950/90 border border-teal-500/40 px-2.5 py-1 text-[10px] font-bold text-teal-300 hover:bg-teal-900/80 transition-colors cursor-pointer"
            >
              🔍 Map
            </button>
            <button
              type="button"
              onClick={() => onEditAsset(asset)}
              className="rounded bg-slate-800 p-1 text-slate-400 hover:text-white text-xs cursor-pointer border border-slate-700/60"
              title="Edit Details"
            >
              ✏️
            </button>
            <button
              type="button"
              onClick={() => onDeleteAsset(asset.id, asset.name)}
              className="rounded bg-slate-800 p-1 text-slate-400 hover:text-rose-400 text-xs cursor-pointer border border-slate-700/60"
              title="Delete Sub-Node"
            >
              🗑️
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Master Folio Card
  return (
    <div className="p-4 sm:p-5 rounded-xl bg-slate-900/90 border border-slate-800/90 shadow-xl space-y-3 hover:border-slate-700/80 transition-all">
      {/* Top Identity Row */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="rounded bg-emerald-500/10 px-2 py-0.5 font-mono text-[11px] font-bold text-emerald-400 border border-emerald-500/20">
              {asset.asset_code}
            </span>

            <span className="text-[11px] font-mono text-slate-400">
              {asset.category_display || asset.category}
            </span>

            <button
              type="button"
              onClick={() => onEditAsset(asset)}
              className="rounded bg-amber-500/10 px-2.5 py-0.5 font-mono text-[10px] font-bold text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-colors flex items-center gap-1 cursor-pointer"
            >
              🏛️ GL: {asset.linked_gl_account || 'Mapped GL'}
              <span className="text-[9px] text-amber-500">✏️</span>
            </button>

            {displayVendorName && (
              <span className="rounded bg-slate-950 px-2 py-0.5 font-mono text-[10px] text-slate-300 border border-slate-800/90">
                🏬 {displayVendorName}
              </span>
            )}

            {isMatured && (
              <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[9px] font-bold text-amber-300 border border-amber-500/40">
                🏁 MATURED
              </span>
            )}
          </div>

          <h3 className="font-bold font-mono text-white text-sm sm:text-base truncate">
            {asset.name}
          </h3>
        </div>

        {/* Valuation & Action Shelves */}
        <div className="flex items-center gap-3.5 shrink-0">
          <div className="text-right hidden sm:block font-mono">
            <span className="text-[9px] text-slate-400 uppercase tracking-wider block">
              {metricLabel}
            </span>
            <p className="text-sm font-bold text-emerald-400">
              {inrFormatter.format(currentValuation)}
            </p>
            {mappedTotal > 0 && (
              <span className="text-[9px] text-teal-400 block font-mono">
                Matched: {inrFormatter.format(mappedTotal)}
              </span>
            )}
          </div>

          <div className="flex items-center gap-1 font-mono">
            <button
              type="button"
              onClick={() => onOpenMatcher(asset)}
              disabled={isMatured}
              className={`rounded px-2.5 py-1 text-[10px] font-bold transition-colors ${
                isMatured
                  ? 'bg-slate-900 border border-slate-800 text-slate-600 cursor-not-allowed'
                  : 'bg-emerald-950/80 border border-emerald-500/40 text-emerald-400 hover:bg-emerald-900/80 cursor-pointer'
              }`}
            >
              🔍 Scan & Map
            </button>
            <button
              type="button"
              onClick={() => onOpenHistory(asset)}
              className="rounded bg-slate-800/90 px-2 py-1 text-[10px] font-bold text-slate-300 hover:text-emerald-400 hover:bg-slate-700 transition-colors cursor-pointer border border-slate-700/80"
            >
              📜 History
            </button>
            <button
              type="button"
              onClick={() => onEditAsset(asset)}
              className="rounded bg-slate-800/80 p-1 text-slate-400 hover:text-white text-xs cursor-pointer border border-slate-700/60"
              title="Edit Folio"
            >
              ✏️
            </button>
            <button
              type="button"
              onClick={() => onDeleteAsset(asset.id, asset.name)}
              className="rounded bg-slate-800/80 p-1 text-slate-400 hover:text-rose-400 text-xs cursor-pointer border border-slate-700/60"
              title="Delete Folio"
            >
              🗑️
            </button>
          </div>
        </div>
      </div>

      {/* Dynamic Metadata Attributes */}
      {asset.metadata_payload && Object.keys(asset.metadata_payload).length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-t border-slate-800/60 pt-2">
          {Object.entries(asset.metadata_payload).map(([k, v]) => (
            <span
              key={k}
              className="rounded bg-slate-950 px-2 py-0.5 font-mono text-[10px] text-slate-300 border border-slate-800/80"
            >
              <span className="text-slate-500">{k}:</span> {String(v)}
            </span>
          ))}
        </div>
      )}

      {/* Operational Identifiers & Schedules Section */}
      {hasOpsOrSchedules || showOpsDrawer ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 rounded-lg bg-slate-950/90 p-2.5 border border-slate-800/60 font-mono">
          {/* Identifiers Column */}
          <div className="space-y-1.5 min-w-0">
            <div className="flex items-center justify-between">
              <h4 className="text-[9px] font-bold text-slate-400 uppercase">
                Operational Identifiers ({opCount})
              </h4>
              <button
                type="button"
                onClick={() => onCreateUtility(asset)}
                className="text-[9px] text-emerald-400 cursor-pointer hover:underline"
              >
                + Add Utility
              </button>
            </div>
            {opCount === 0 ? (
              <p className="text-[10px] text-slate-600 italic">None registered</p>
            ) : (
              <ul className="space-y-1">
                {asset.operational_accounts.map((op) => (
                  <li
                    key={op.id}
                    className="flex items-center justify-between text-[10px] text-slate-300 bg-slate-900/90 p-1.5 rounded border border-slate-800"
                  >
                    <span className="truncate mr-2">
                      {op.provider_name} ({op.consumer_identifier})
                    </span>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        type="button"
                        onClick={() => onOpenMatcher(asset, null, op)}
                        className="text-[9px] text-emerald-400 font-bold cursor-pointer"
                      >
                        Map
                      </button>
                      <button
                        type="button"
                        onClick={() => onEditUtility(asset, op)}
                        className="text-slate-400 hover:text-white text-[10px] p-0.5 cursor-pointer"
                      >
                        ✏️
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Schedules Column */}
          <div className="space-y-1.5 min-w-0">
            <div className="flex items-center justify-between">
              <h4 className="text-[9px] font-bold text-slate-400 uppercase">
                Schedules & Due Dates ({schCount})
              </h4>
              <button
                type="button"
                onClick={() => onCreateSchedule(asset)}
                className="text-[9px] text-emerald-400 cursor-pointer hover:underline"
              >
                + Add Reminder
              </button>
            </div>
            {schCount === 0 ? (
              <p className="text-[10px] text-slate-600 italic">No pending schedules</p>
            ) : (
              <ul className="space-y-1">
                {asset.compliance_schedules.map((sch) => (
                  <li
                    key={sch.id}
                    className="flex items-center justify-between text-[10px] bg-slate-900/90 p-1.5 rounded border border-slate-800"
                  >
                    <span className="text-slate-200 truncate mr-2">{sch.title}</span>
                    <div className="flex items-center gap-1 shrink-0">
                      <span className="text-[9px] text-amber-400 font-bold">DUE {sch.due_date}</span>
                      <button
                        type="button"
                        onClick={() => onEditSchedule(asset, sch)}
                        className="text-slate-400 hover:text-white text-[10px] p-0.5 cursor-pointer"
                      >
                        ✏️
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : (
        /* Compact Footprint when neither utility nor schedule exists */
        <div className="flex items-center justify-between pt-1 border-t border-slate-800/40 font-mono text-[10px] text-slate-500">
          <span>No operational meters or tax reminders attached</span>
          <button
            type="button"
            onClick={() => setShowOpsDrawer(true)}
            className="text-emerald-400 hover:text-emerald-300 font-bold transition-colors cursor-pointer"
          >
            + Attach Utility / Reminder
          </button>
        </div>
      )}

      {/* Linked Sub-Assets */}
      {asset.children && asset.children.length > 0 && (
        <div className="pt-2 space-y-2 border-t border-slate-800/80">
          <span className="text-[10px] font-mono font-bold text-teal-300 bg-teal-950 px-2 py-0.5 rounded border border-teal-500/40 uppercase tracking-wider inline-block">
            📦 LINKED SUB-ASSETS ({asset.children.length})
          </span>
          <div className="space-y-2 pl-3 border-l-2 border-teal-500/40">
            {asset.children.map((childNode) => (
              <AssetNodeCard
                key={childNode.id}
                asset={childNode}
                isChild={true}
                metricLabel={metricLabel}
                onOpenMatcher={onOpenMatcher}
                onOpenHistory={onOpenHistory}
                onEditAsset={onEditAsset}
                onDeleteAsset={onDeleteAsset}
                onCreateUtility={onCreateUtility}
                onEditUtility={onEditUtility}
                onCreateSchedule={onCreateSchedule}
                onEditSchedule={onEditSchedule}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};