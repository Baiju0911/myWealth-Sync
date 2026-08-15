import React, { useEffect, useState, useCallback } from 'react';
import { subledgerApi } from '../api/subledger';
import type {
  AssetSubLedgerNode,
  AssetComplianceSchedule,
  AssetOperationalAccount,
} from '../api/subledger';

import { CandidateMatcherModal } from '../components/subledger/CandidateMatcherModal';
import { AssetFormModal } from '../components/subledger/AssetFormModal';
import { OperationalAccountModal } from '../components/subledger/OperationalAccountModal';
import { ScheduleModal } from '../components/subledger/ScheduleModal';
import { HistoryDrawerModal } from '../components/subledger/HistoryDrawerModal';

interface SubLedgerDashboardProps {
  filterSubcategory?: string | null;
  isModal?: boolean;
}

export const SubLedgerDashboard: React.FC<SubLedgerDashboardProps> = ({
  filterSubcategory,
  isModal = false,
}) => {
  const [assets, setAssets] = useState<AssetSubLedgerNode[]>([]);
  const [pendingDues, setPendingDues] = useState<AssetComplianceSchedule[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Matcher Modal Control State
  const [selectedAsset, setSelectedAsset] = useState<AssetSubLedgerNode | null>(null);
  const [selectedSchedule, setSelectedSchedule] = useState<AssetComplianceSchedule | null>(null);
  const [selectedUtility, setSelectedUtility] = useState<AssetOperationalAccount | null>(null);
  const [isMatcherOpen, setIsMatcherOpen] = useState<boolean>(false);

  // Master Asset Form Modal State
  const [isAssetModalOpen, setIsAssetModalOpen] = useState<boolean>(false);
  const [assetToEdit, setAssetToEdit] = useState<AssetSubLedgerNode | null>(null);

  // Operational Account (Utility) Modal State (Create & Edit)
  const [isOpModalOpen, setIsOpModalOpen] = useState<boolean>(false);
  const [utilityToEdit, setUtilityToEdit] = useState<AssetOperationalAccount | null>(null);

  // Schedule Reminder Modal State (Create & Edit)
  const [isScheduleModalOpen, setIsScheduleModalOpen] = useState<boolean>(false);
  const [scheduleToEdit, setScheduleToEdit] = useState<AssetComplianceSchedule | null>(null);

  // History Drawer State
  const [isHistoryOpen, setIsHistoryOpen] = useState<boolean>(false);
  const [historyAsset, setHistoryAsset] = useState<AssetSubLedgerNode | null>(null);

  const handleCreateAsset = () => {
    setAssetToEdit(null);
    setIsAssetModalOpen(true);
  };

  const handleEditAsset = (asset: AssetSubLedgerNode) => {
    setAssetToEdit(asset);
    setIsAssetModalOpen(true);
  };

  const handleDeleteAsset = async (id: string, name: string) => {
    if (window.confirm(`Are you sure you want to delete asset "${name}"?`)) {
      await subledgerApi.deleteAsset(id);
      loadDashboardData();
    }
  };

  const openHistoryDrawer = (asset: AssetSubLedgerNode) => {
    setHistoryAsset(asset);
    setIsHistoryOpen(true);
  };

  const handleCreateUtility = (asset: AssetSubLedgerNode) => {
    setSelectedAsset(asset);
    setUtilityToEdit(null);
    setIsOpModalOpen(true);
  };

  const handleEditUtility = (asset: AssetSubLedgerNode, op: AssetOperationalAccount) => {
    setSelectedAsset(asset);
    setUtilityToEdit(op);
    setIsOpModalOpen(true);
  };

  const handleCreateSchedule = (asset: AssetSubLedgerNode) => {
    setSelectedAsset(asset);
    setScheduleToEdit(null);
    setIsScheduleModalOpen(true);
  };

  const handleEditSchedule = (asset: AssetSubLedgerNode, sch: AssetComplianceSchedule) => {
    setSelectedAsset(asset);
    setScheduleToEdit(sch);
    setIsScheduleModalOpen(true);
  };

  // const loadDashboardData = useCallback(async () => {
  //   setLoading(true);
  //   try {
  //     const targetCategory = filterSubcategory ? filterSubcategory.trim() : undefined;
      
  //     const [assetsData, duesData] = await Promise.all([
  //       subledgerApi.getAssets(targetCategory),
  //       subledgerApi.getPendingDues(),
  //     ]);

  //     setAssets(assetsData);
  //     setPendingDues(duesData);
  //   } catch (err) {
  //     console.error('Failed to load sub-ledger data:', err);
  //   } finally {
  //     setLoading(false);
  //   }
  // }, [filterSubcategory]);

  const loadDashboardData = useCallback(async () => {
  setLoading(true);
  try {
    const targetCategory = filterSubcategory ? filterSubcategory.trim() : undefined;

    const [assetsData, duesData] = await Promise.all([
      subledgerApi.getAssets(targetCategory),
      subledgerApi.getPendingDues().catch(() => []),
    ]);

    // 🎯 Client-side fallback filter with explicit string conversion
    const filteredAssets = targetCategory
      ? assetsData.filter((a) => {
          const categoryMatch = String(a.category || '').toLowerCase().includes(targetCategory.toLowerCase());
          const displayMatch = String(a.category_display || '').toLowerCase().includes(targetCategory.toLowerCase());
          const glMatch = String(a.linked_gl_account || '').toLowerCase().includes(targetCategory.toLowerCase());
          const nameMatch = String(a.name || '').toLowerCase().includes(targetCategory.toLowerCase());
          
          return categoryMatch || displayMatch || glMatch || nameMatch;
        })
      : assetsData;

    setAssets(filteredAssets);
    setPendingDues(duesData);
  } catch (err) {
    console.error('Failed to load sub-ledger data:', err);
  } finally {
    setLoading(false);
  }
}, [filterSubcategory]);


  useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  const openMatcher = (
    asset: AssetSubLedgerNode,
    schedule?: AssetComplianceSchedule | null,
    utility?: AssetOperationalAccount | null
  ) => {
    setSelectedAsset(asset);
    setSelectedSchedule(schedule || null);
    setSelectedUtility(utility || null);
    setIsMatcherOpen(true);
  };

  return (
    <div className={isModal ? 'p-2 bg-transparent text-slate-100 space-y-4' : 'min-h-screen bg-slate-950 p-6 text-slate-100'}>
      {/* Top Navigation Banner (Hidden in Modal Mode) */}
      {!isModal && (
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">
              Asset Sub-Ledgers & Compliance
            </h1>
            <p className="text-sm text-slate-400">
              Manage real estate, fixed deposits, utility IDs, and post-facto transaction bindings.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCreateAsset}
              className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 transition-colors cursor-pointer"
            >
              + New Asset
            </button>
            <button
              onClick={loadDashboardData}
              className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 transition-colors cursor-pointer"
            >
              🔄 Refresh Feed
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="py-12 text-center text-sm text-slate-400 font-mono">
          Loading sub-ledger assets and compliance queues...
        </div>
      ) : (
        <div className={`grid grid-cols-12 gap-6 ${isModal ? 'mt-1' : 'mt-6'}`}>
          {/* Left Side: Asset Registry Cards (8 Columns) */}
          <div className="col-span-12 lg:col-span-8 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-bold tracking-wider text-slate-400 uppercase font-mono">
                {filterSubcategory ? `${filterSubcategory} Assets` : 'Registered Master Assets'} ({assets.length})
              </h2>
              {isModal && (
                <button
                  onClick={handleCreateAsset}
                  className="rounded bg-emerald-600 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-emerald-500 transition-colors cursor-pointer"
                >
                  + New Asset
                </button>
              )}
            </div>

            {assets.length === 0 ? (
              <div className="p-8 border border-dashed border-slate-800 rounded-xl text-center text-slate-500 text-xs font-mono space-y-2">
                <p>No asset instances registered under {filterSubcategory || 'this category'} yet.</p>
                <button
                  onClick={handleCreateAsset}
                  className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-emerald-400 rounded text-xs font-bold transition-colors cursor-pointer"
                >
                  Register First Asset
                </button>
              </div>
            ) : (
              assets.map((asset) => (
                <div
                  key={asset.id}
                  className="rounded-xl border border-slate-800/80 bg-slate-900/90 p-4 sm:p-5 shadow-lg space-y-3"
                >
                  {/* Card Header with Interactive Taxonomy GL Badge */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="rounded bg-emerald-500/10 px-2 py-0.5 font-mono text-xs font-bold text-emerald-400 border border-emerald-500/20">
                          {asset.asset_code}
                        </span>
                        <span className="text-xs text-slate-400">
                          {asset.category_display || asset.category}
                        </span>

                        {/* 🏛️ Clickable GL Taxonomy Badge */}
                        <button
                          onClick={() => handleEditAsset(asset)}
                          className="rounded bg-amber-500/10 px-2.5 py-0.5 font-mono text-[11px] font-bold text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-colors flex items-center gap-1 cursor-pointer"
                          title="Click to remap General Ledger Taxonomy"
                        >
                          🏛️ GL: {asset.linked_gl_account ? `${asset.linked_gl_account}` : 'Real Estate'}
                          <span className="text-[9px] text-amber-500">✏️</span>
                        </button>
                      </div>
                      <h3 className="mt-1 text-base sm:text-lg font-bold text-white truncate">{asset.name}</h3>
                    </div>

                    <div className="flex items-center gap-3 shrink-0">
                      <div className="text-right hidden sm:block">
                        <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Valuation</span>
                        <p className="font-mono text-sm sm:text-base font-bold text-emerald-400">
                          ₹{Number(asset.current_valuation).toLocaleString('en-IN')}
                        </p>
                      </div>

                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => openMatcher(asset, null, null)}
                          className="rounded bg-emerald-950/60 border border-emerald-500/30 px-2 py-1 text-[11px] font-semibold text-emerald-400 hover:bg-emerald-900/50 transition-colors flex items-center gap-1 whitespace-nowrap cursor-pointer"
                          title="Scan bank/journal entries to map asset purchase payments"
                        >
                          🔍 Scan Outflows
                        </button>

                        <button
                          onClick={() => openHistoryDrawer(asset)}
                          className="rounded bg-slate-800 px-2 py-1 text-[11px] font-semibold text-slate-300 hover:text-emerald-400 hover:bg-slate-700 transition-colors flex items-center gap-1 whitespace-nowrap cursor-pointer"
                          title="View Asset History & Mapped Transactions"
                        >
                          📜 History
                        </button>

                        <button
                          onClick={() => handleEditAsset(asset)}
                          className="rounded bg-slate-800 p-1 text-slate-400 hover:text-white text-xs transition-colors cursor-pointer"
                          title="Edit Asset Details"
                        >
                          ✏️
                        </button>
                        <button
                          onClick={() => handleDeleteAsset(asset.id, asset.name)}
                          className="rounded bg-slate-800 p-1 text-slate-400 hover:text-rose-400 text-xs transition-colors cursor-pointer"
                          title="Delete Asset"
                        >
                          🗑️
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Metadata Badges */}
                  {asset.metadata_payload && Object.keys(asset.metadata_payload).length > 0 && (
                    <div className="flex flex-wrap gap-2 border-t border-slate-800/80 pt-2">
                      {Object.entries(asset.metadata_payload).map(([k, v]) => (
                        <span
                          key={k}
                          className="rounded bg-slate-950 px-2 py-0.5 font-mono text-[10px] text-slate-300 border border-slate-800"
                        >
                          <span className="text-slate-500">{k}:</span> {String(v)}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Operational Accounts & Compliance Schedules Grid */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 rounded-lg bg-slate-950 p-3 border border-slate-800/50">
                    {/* Operational Sub-Ledgers Section */}
                    <div className="space-y-2 min-w-0">
                      <div className="flex items-center justify-between">
                        <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider font-mono">
                          Operational Sub-Ledgers
                        </h4>
                        <button
                          onClick={() => handleCreateUtility(asset)}
                          className="text-[10px] text-emerald-400 hover:underline font-semibold cursor-pointer"
                        >
                          + Add Utility
                        </button>
                      </div>

                      {asset.operational_accounts.length === 0 ? (
                        <p className="text-[11px] text-slate-600 italic">None registered</p>
                      ) : (
                        <ul className="space-y-1.5">
                          {asset.operational_accounts.map((op) => (
                            <li
                              key={op.id}
                              className="flex items-center justify-between gap-2 text-xs text-slate-300 rounded bg-slate-900/80 p-1.5 border border-slate-800/80 min-w-0"
                            >
                              <div className="flex items-center gap-1.5 min-w-0 truncate">
                                <span className="font-semibold text-slate-200 truncate">
                                  {op.provider_name}
                                </span>
                                <span className="text-[10px] text-slate-500 font-mono shrink-0">
                                  ({op.consumer_identifier})
                                </span>
                                <span className="text-[10px] text-emerald-400/80 font-mono shrink-0">
                                  [{op.matching_keyword}]
                                </span>
                              </div>

                              <div className="flex items-center gap-1 shrink-0">
                                <button
                                  onClick={() => openMatcher(asset, null, op)}
                                  className="rounded bg-emerald-600/20 px-1.5 py-0.5 text-[9px] font-bold text-emerald-400 border border-emerald-500/30 hover:bg-emerald-600 hover:text-white transition-colors whitespace-nowrap cursor-pointer"
                                  title="Scan staging lines & map to sub-ledger"
                                >
                                  Scan & Map
                                </button>
                                <button
                                  onClick={() => handleEditUtility(asset, op)}
                                  className="text-slate-400 hover:text-white text-[10px] p-0.5 transition-colors cursor-pointer"
                                  title="Edit Utility Keywords & Details"
                                >
                                  ✏️
                                </button>
                                <button
                                  onClick={async () => {
                                    if (
                                      window.confirm(
                                        `Delete sub-ledger utility ${op.provider_name}?`
                                      )
                                    ) {
                                      await subledgerApi.deleteOperationalAccount(op.id);
                                      loadDashboardData();
                                    }
                                  }}
                                  className="text-slate-500 hover:text-rose-400 text-[10px] p-0.5 transition-colors cursor-pointer"
                                  title="Delete Utility"
                                >
                                  🗑️
                                </button>
                              </div>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>

                    {/* Compliance Reminders Section */}
                    <div className="space-y-2 min-w-0">
                      <div className="flex items-center justify-between">
                        <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider font-mono">
                          Compliance Reminders
                        </h4>
                        <button
                          onClick={() => handleCreateSchedule(asset)}
                          className="text-[10px] text-emerald-400 hover:underline font-semibold cursor-pointer"
                        >
                          + Add Reminder
                        </button>
                      </div>

                      {asset.compliance_schedules.length === 0 ? (
                        <p className="text-[11px] text-slate-600 italic">No pending schedules</p>
                      ) : (
                        <ul className="space-y-1.5">
                          {asset.compliance_schedules.map((sch) => {
                            const linkedUtility = asset.operational_accounts.find(
                              (op) => op.id === sch.operational_account
                            );

                            return (
                              <li
                                key={sch.id}
                                className="flex items-center justify-between gap-2 text-xs rounded bg-slate-900/80 p-1.5 border border-slate-800/80 min-w-0"
                              >
                                <div className="min-w-0 truncate pr-1">
                                  <span
                                    className={`truncate ${
                                      sch.is_paid
                                        ? 'line-through text-slate-500 font-medium'
                                        : 'text-slate-200 font-medium'
                                    }`}
                                  >
                                    • {sch.title}
                                  </span>
                                  {linkedUtility && (
                                    <span className="ml-1 text-[10px] text-slate-500 font-mono">
                                      [{linkedUtility.provider_name}]
                                    </span>
                                  )}
                                </div>

                                <div className="flex items-center gap-1 shrink-0">
                                  {sch.is_paid ? (
                                    <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 font-mono text-[9px] font-bold text-emerald-400 border border-emerald-500/20">
                                      PAID
                                    </span>
                                  ) : (
                                    <span className="rounded bg-amber-500/10 px-1.5 py-0.5 font-mono text-[9px] font-bold text-amber-400 border border-amber-500/20 whitespace-nowrap">
                                      DUE {sch.due_date} (₹
                                      {Number(sch.expected_amount).toLocaleString('en-IN')})
                                    </span>
                                  )}

                                  <button
                                    onClick={() => handleEditSchedule(asset, sch)}
                                    className="text-slate-400 hover:text-white text-[10px] p-0.5 transition-colors cursor-pointer"
                                    title="Edit Reminder Details"
                                  >
                                    ✏️
                                  </button>
                                  <button
                                    onClick={async () => {
                                      if (window.confirm(`Delete reminder ${sch.title}?`)) {
                                        await subledgerApi.deleteSchedule(sch.id);
                                        loadDashboardData();
                                      }
                                    }}
                                    className="text-slate-500 hover:text-rose-400 text-[10px] p-0.5 transition-colors cursor-pointer"
                                    title="Delete Reminder"
                                  >
                                    🗑️
                                  </button>
                                </div>
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Right Side: Pending Dues Feed (4 Columns) */}
          <div className="col-span-12 lg:col-span-4 space-y-4">
            <h2 className="text-xs font-bold tracking-wider text-slate-400 uppercase font-mono">
              Upcoming Compliance Dues ({pendingDues.length})
            </h2>

            <div className="rounded-xl border border-slate-800/80 bg-slate-900/90 p-4 space-y-3">
              {pendingDues.length === 0 ? (
                <p className="text-xs text-slate-500 text-center py-4 font-mono">
                  🎉 No pending dues in queue!
                </p>
              ) : (
                pendingDues.map((due) => {
                  const targetAsset = assets.find((a) => a.id === due.asset);
                  const linkedUtility = targetAsset?.operational_accounts.find(
                    (op) => op.id === due.operational_account
                  );

                  return (
                    <div
                      key={due.id}
                      className="rounded-lg border border-slate-800 bg-slate-950 p-3 space-y-2 shadow-inner"
                    >
                      <div className="flex justify-between items-start gap-2">
                        <div className="min-w-0">
                          <p className="text-xs font-bold text-white truncate">{due.title}</p>
                          <p className="text-[10px] text-slate-400 mt-0.5">
                            Due Date:{' '}
                            <span className="font-mono text-amber-400">{due.due_date}</span>
                          </p>
                        </div>
                        <span className="font-mono text-xs font-bold text-emerald-400 whitespace-nowrap">
                          ₹{Number(due.expected_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      </div>

                      {targetAsset && (
                        <button
                          onClick={() => openMatcher(targetAsset, due, linkedUtility)}
                          className="w-full rounded bg-emerald-600 py-1 text-xs font-semibold text-white hover:bg-emerald-500 transition-colors cursor-pointer"
                        >
                          ⚡ Scan Staging & Resolve
                        </button>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}

      {/* Candidate Matcher Modal Component */}
      {selectedAsset && (
        <CandidateMatcherModal
          isOpen={isMatcherOpen}
          onClose={() => setIsMatcherOpen(false)}
          asset={selectedAsset}
          schedule={selectedSchedule}
          utility={selectedUtility}
          onSuccess={loadDashboardData}
        />
      )}

      {/* Asset Form Modal (Create / Edit Master Asset) */}
      <AssetFormModal
        isOpen={isAssetModalOpen}
        onClose={() => setIsAssetModalOpen(false)}
        assetToEdit={assetToEdit}
        onSuccess={loadDashboardData}
      />

      {/* Utility / Operational Account Modal (Create / Edit Utility) */}
      {selectedAsset && (
        <OperationalAccountModal
          isOpen={isOpModalOpen}
          onClose={() => setIsOpModalOpen(false)}
          asset={selectedAsset}
          utilityToEdit={utilityToEdit}
          onSuccess={loadDashboardData}
        />
      )}

      {/* Compliance Schedule Modal (Create / Edit Reminder) */}
      {selectedAsset && (
        <ScheduleModal
          isOpen={isScheduleModalOpen}
          onClose={() => setIsScheduleModalOpen(false)}
          asset={selectedAsset}
          scheduleToEdit={scheduleToEdit}
          onSuccess={loadDashboardData}
        />
      )}

      {/* History Slide-over Drawer Modal */}
      {historyAsset && (
        <HistoryDrawerModal
          isOpen={isHistoryOpen}
          onClose={() => setIsHistoryOpen(false)}
          asset={historyAsset}
        />
      )}
    </div>
  );
};