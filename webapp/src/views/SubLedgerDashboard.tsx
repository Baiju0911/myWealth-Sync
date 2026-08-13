import React, { useEffect, useState } from 'react';
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

export const SubLedgerDashboard: React.FC = () => {
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

  const loadDashboardData = async () => {
    setLoading(true);
    try {
      const [assetsData, duesData] = await Promise.all([
        subledgerApi.getAssets(),
        subledgerApi.getPendingDues(),
      ]);
      setAssets(assetsData);
      setPendingDues(duesData);
    } catch (err) {
      console.error('Failed to load sub-ledger data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardData();
  }, []);

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
    <div className="min-h-screen bg-slate-950 p-6 text-slate-100">
      {/* Top Navigation Banner */}
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
            className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 transition-colors"
          >
            + New Asset
          </button>
          <button
            onClick={loadDashboardData}
            className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 transition-colors"
          >
            🔄 Refresh Feed
          </button>
        </div>
      </div>

      {loading ? (
        <div className="mt-12 text-center text-sm text-slate-400">
          Loading sub-ledger assets and compliance queues...
        </div>
      ) : (
        <div className="mt-6 grid grid-cols-12 gap-6">
          {/* Left Side: Asset Registry Cards (8 Columns) */}
          <div className="col-span-12 lg:col-span-8 space-y-4">
            <h2 className="text-sm font-bold tracking-wider text-slate-400 uppercase">
              Registered Master Assets ({assets.length})
            </h2>

            {assets.map((asset) => (
              <div
                key={asset.id}
                className="rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-lg"
              >
                {/* Card Header with Interactive Taxonomy GL Badge */}
                <div className="flex items-start justify-between">
                  <div>
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
                        className="rounded bg-amber-500/10 px-2.5 py-0.5 font-mono text-[11px] font-bold text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-colors flex items-center gap-1"
                        title="Click to remap General Ledger Taxonomy"
                      >
                        🏛️ GL: {asset.linked_gl_account ? `${asset.linked_gl_account}` : 'Real Estate'}
                        <span className="text-[9px] text-amber-500">✏️</span>
                      </button>
                    </div>
                    <h3 className="mt-1 text-lg font-bold text-white">{asset.name}</h3>
                  </div>

                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <span className="text-xs text-slate-400">Current Valuation</span>
                      <p className="font-mono text-lg font-bold text-emerald-400">
                        ₹{Number(asset.current_valuation).toLocaleString('en-IN')}
                      </p>
                    </div>
                    
                    <div className="flex items-center gap-1.5">
                      {/* 🎯 NEW: Primary Asset Purchase Outflow Scanner */}
                      <button
                        onClick={() => openMatcher(asset, null, null)}
                        className="rounded bg-emerald-950/60 border border-emerald-500/30 px-2.5 py-1 text-xs font-semibold text-emerald-400 hover:bg-emerald-900/50 transition-colors flex items-center gap-1"
                        title="Scan bank/journal entries to map asset purchase payments"
                      >
                        🔍 Scan Outflows
                      </button>

                      {/* 📜 History Drawer Trigger */}
                      <button
                        onClick={() => openHistoryDrawer(asset)}
                        className="rounded bg-slate-800 px-2 py-1 text-xs font-semibold text-slate-300 hover:text-emerald-400 hover:bg-slate-700 transition-colors flex items-center gap-1"
                        title="View Asset History & Mapped Transactions"
                      >
                        📜 History
                      </button>
                      
                      <button
                        onClick={() => handleEditAsset(asset)}
                        className="rounded bg-slate-800 p-1 text-slate-400 hover:text-white text-xs transition-colors"
                        title="Edit Asset Details"
                      >
                        ✏️
                      </button>
                      <button
                        onClick={() => handleDeleteAsset(asset.id, asset.name)}
                        className="rounded bg-slate-800 p-1 text-slate-400 hover:text-rose-400 text-xs transition-colors"
                        title="Delete Asset"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                </div>

                {/* Metadata Badges */}
                {asset.metadata_payload && (
                  <div className="mt-3 flex flex-wrap gap-2 border-t border-slate-800/80 pt-3">
                    {Object.entries(asset.metadata_payload).map(([k, v]) => (
                      <span
                        key={k}
                        className="rounded bg-slate-800 px-2 py-1 font-mono text-[11px] text-slate-300"
                      >
                        <span className="text-slate-500">{k}:</span> {String(v)}
                      </span>
                    ))}
                  </div>
                )}

                {/* Operational Accounts & Compliance Schedules Grid */}
                <div className="mt-4 grid grid-cols-2 gap-4 rounded-lg bg-slate-950 p-3 border border-slate-800/50">
                  
                  {/* Operational Sub-Ledgers Section */}
                  <div>
                    <div className="flex items-center justify-between">
                      <h4 className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                        Operational Sub-Ledgers
                      </h4>
                      <button
                        onClick={() => handleCreateUtility(asset)}
                        className="text-[10px] text-emerald-400 hover:underline font-semibold"
                      >
                        + Add Utility
                      </button>
                    </div>

                    {asset.operational_accounts.length === 0 ? (
                      <p className="text-xs text-slate-600 mt-2">None registered</p>
                    ) : (
                      <ul className="mt-2 space-y-1.5">
                        {asset.operational_accounts.map((op) => (
                          <li
                            key={op.id}
                            className="flex items-center justify-between text-xs text-slate-300 rounded bg-slate-900/60 p-1.5 border border-slate-800/80"
                          >
                            <div className="flex items-center gap-1.5 min-w-0">
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

                            <div className="flex items-center gap-1 shrink-0 pl-1">
                              <button
                                onClick={() => openMatcher(asset, null, op)}
                                className="rounded bg-emerald-600/20 px-2 py-0.5 text-[10px] font-bold text-emerald-400 border border-emerald-500/30 hover:bg-emerald-600 hover:text-white transition-colors"
                                title="Scan staging lines & map to sub-ledger"
                              >
                                🔍 Scan & Map
                              </button>
                              <button
                                onClick={() => handleEditUtility(asset, op)}
                                className="text-slate-400 hover:text-white text-[10px] px-1 transition-colors"
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
                                className="text-slate-500 hover:text-rose-400 text-[10px] px-1 transition-colors"
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
                  <div>
                    <div className="flex items-center justify-between">
                      <h4 className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                        Compliance Reminders
                      </h4>
                      <button
                        onClick={() => handleCreateSchedule(asset)}
                        className="text-[10px] text-emerald-400 hover:underline font-semibold"
                      >
                        + Add Reminder
                      </button>
                    </div>

                    {asset.compliance_schedules.length === 0 ? (
                      <p className="text-xs text-slate-600 mt-2">No pending schedules</p>
                    ) : (
                      <ul className="mt-2 space-y-1.5">
                        {asset.compliance_schedules.map((sch) => {
                          const linkedUtility = asset.operational_accounts.find(
                            (op) => op.id === sch.operational_account
                          );

                          return (
                            <li
                              key={sch.id}
                              className="flex items-center justify-between text-xs rounded bg-slate-900/60 p-1.5 border border-slate-800/80"
                            >
                              <div className="min-w-0 pr-1">
                                <span
                                  className={
                                    sch.is_paid
                                      ? 'line-through text-slate-500 font-medium'
                                      : 'text-slate-200 font-medium'
                                  }
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
                                  <span className="rounded bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] font-bold text-emerald-400 border border-emerald-500/20">
                                    🟢 PAID
                                  </span>
                                ) : (
                                  <span className="rounded bg-amber-500/10 px-2 py-0.5 font-mono text-[10px] font-bold text-amber-400 border border-amber-500/20">
                                    🟡 DUE {sch.due_date} (₹
                                    {Number(sch.expected_amount).toLocaleString('en-IN')})
                                  </span>
                                )}

                                <button
                                  onClick={() => handleEditSchedule(asset, sch)}
                                  className="text-slate-400 hover:text-white text-[10px] px-1 transition-colors"
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
                                  className="text-slate-500 hover:text-rose-400 text-[10px] px-1 transition-colors"
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
            ))}
          </div>

          {/* Right Side: Pending Dues Feed (4 Columns) */}
          <div className="col-span-12 lg:col-span-4 space-y-4">
            <h2 className="text-sm font-bold tracking-wider text-slate-400 uppercase">
              Upcoming Compliance Dues ({pendingDues.length})
            </h2>

            <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 space-y-3">
              {pendingDues.length === 0 ? (
                <p className="text-xs text-slate-500 text-center py-4">
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
                      <div className="flex justify-between items-start">
                        <div>
                          <p className="text-xs font-bold text-white">{due.title}</p>
                          <p className="text-[10px] text-slate-400 mt-0.5">
                            Due Date:{' '}
                            <span className="font-mono text-amber-400">{due.due_date}</span>
                          </p>
                        </div>
                        <span className="font-mono text-sm font-bold text-emerald-400">
                          ₹{Number(due.expected_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      </div>

                      {targetAsset && (
                        <button
                          onClick={() => openMatcher(targetAsset, due, linkedUtility)}
                          className="w-full rounded bg-emerald-600 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 transition-colors"
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