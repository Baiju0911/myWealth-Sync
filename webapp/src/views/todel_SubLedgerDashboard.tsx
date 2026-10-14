import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { subledgerApi } from '../api/subledger';
import type {
  AssetSubLedgerNode,
  AssetComplianceSchedule,
  AssetOperationalAccount,
} from '../api/subledger';

import { CandidateMatcherModal } from '../components/subledger/toDel_CandidateMatcherModal';
import { AssetFormModal } from '../components/subledger/todel_AssetFormModal';
import { OperationalAccountModal } from '../components/subledger/OperationalAccountModal';
import { ScheduleModal } from '../components/subledger/ScheduleModal';
import { HistoryDrawerModal } from '../components/subledger/HistoryDrawerModal';

interface SubLedgerDashboardProps {
  filterSubcategory?: string | null;
  isModal?: boolean;
}

export interface HierarchyAssetNode extends AssetSubLedgerNode {
  children?: AssetSubLedgerNode[];
}

export const SubLedgerDashboard: React.FC<SubLedgerDashboardProps> = ({
  filterSubcategory,
  isModal = false,
}) => {
  const [assets, setAssets] = useState<AssetSubLedgerNode[]>([]);
  const [pendingDues, setPendingDues] = useState<AssetComplianceSchedule[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Active Subledger Tab Filter (ASSET, INCOME, EXPENSE)
  const [activeTab, setActiveTab] = useState<'ASSET' | 'INCOME' | 'EXPENSE'>('ASSET');

  // Accordion Collapsed State by Vendor
  const [expandedVendors, setExpandedVendors] = useState<Record<string, boolean>>({});

  // Matcher Modal Control State
  const [selectedAsset, setSelectedAsset] = useState<AssetSubLedgerNode | null>(null);
  const [selectedSchedule, setSelectedSchedule] = useState<AssetComplianceSchedule | null>(null);
  const [selectedUtility, setSelectedUtility] = useState<AssetOperationalAccount | null>(null);
  const [isMatcherOpen, setIsMatcherOpen] = useState<boolean>(false);

  // Form Modal State
  const [isAssetModalOpen, setIsAssetModalOpen] = useState<boolean>(false);
  const [assetToEdit, setAssetToEdit] = useState<AssetSubLedgerNode | null>(null);

  // Operational Account (Utility) Modal State
  const [isOpModalOpen, setIsOpModalOpen] = useState<boolean>(false);
  const [utilityToEdit, setUtilityToEdit] = useState<AssetOperationalAccount | null>(null);

  // Schedule Reminder Modal State
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
    if (window.confirm(`Are you sure you want to delete entity "${name}"?`)) {
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

  const loadDashboardData = useCallback(async () => {
    setLoading(true);
    try {
      const targetCategory = filterSubcategory ? filterSubcategory.trim() : undefined;

      const [assetsData, duesData] = await Promise.all([
        subledgerApi.getAssets(targetCategory),
        subledgerApi.getPendingDues().catch(() => []),
      ]);

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
    } 
    finally {
      setLoading(false);
    }
  }, [filterSubcategory]);

  useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  const toggleVendor = (vendorKey: string) => {
    setExpandedVendors((prev) => ({
      ...prev,
      [vendorKey]: !prev[vendorKey],
    }));
  };

  // Helper to resolve string category_type
  const getSubledgerType = (asset: any): string => {
    if (asset.category_type) return String(asset.category_type).toUpperCase();
    if (asset.category_detail?.category_type) return String(asset.category_detail.category_type).toUpperCase();
    if (asset.asset_code?.startsWith('INC')) return 'INCOME';
    if (asset.asset_code?.startsWith('EXP')) return 'EXPENSE';
    return 'ASSET';
  };

  // Filter Assets strictly by active tab
  const filteredAssetsByTab = useMemo(() => {
    return assets.filter((asset: any) => getSubledgerType(asset) === activeTab);
  }, [assets, activeTab]);

  // 🎯 Structure Vendor Groups with Master Node Top Sorting & Sub-Asset Nesting
  const structuredVendorEntries = useMemo(() => {
    const groups: Record<
      string,
      {
        vendorKey: string;
        vendorName: string;
        rootAssets: HierarchyAssetNode[];
        totalValuation: number;
        totalNodeCount: number;
      }
    > = {};

    filteredAssetsByTab.forEach((asset: any) => {
      const vendorName =
        asset.vendor_name ||
        asset.vendor_detail?.name ||
        (typeof asset.vendor === 'string' && asset.vendor.length > 0 ? asset.vendor : null) ||
        'Independent / Uncategorized';

      const vendorKey =
        asset.vendor_id ||
        asset.vendor_detail?.id ||
        asset.vendor ||
        'uncategorized';

      if (!groups[vendorKey]) {
        groups[vendorKey] = {
          vendorKey,
          vendorName,
          rootAssets: [],
          totalValuation: 0,
          totalNodeCount: 0,
        };
      }

      groups[vendorKey].totalValuation += Number(asset.current_valuation || 0);
      groups[vendorKey].totalNodeCount += 1;
    });

    // Build Parent -> Child relations per vendor group
    Object.keys(groups).forEach((vKey) => {
      const vendorAssets = filteredAssetsByTab.filter((a: any) => {
        const key = a.vendor_id || a.vendor_detail?.id || a.vendor || 'uncategorized';
        return key === vKey;
      });

      const nodeMap = new Map<string, HierarchyAssetNode>();
      vendorAssets.forEach((a) => {
        nodeMap.set(a.id, { ...a, children: [] });
      });

      const rootNodes: HierarchyAssetNode[] = [];

      nodeMap.forEach((node) => {
        const parentId = (node as any).parent_asset_id || (node as any).parent_asset?.id || (node as any).parent_asset;

        if (parentId && nodeMap.has(parentId)) {
          // Attach as child component
          nodeMap.get(parentId)!.children!.push(node);
        } else {
          // Master top-level node
          rootNodes.push(node);
        }
      });

      // 🟢 Sort Root Master Nodes and ensure child sub-assets follow deterministically
      rootNodes.sort((a, b) => a.asset_code.localeCompare(b.asset_code));
      rootNodes.forEach((parent) => {
        if (parent.children) {
          parent.children.sort((a, b) => a.asset_code.localeCompare(b.asset_code));
        }
      });

      groups[vKey].rootAssets = rootNodes;
    });

    return Object.values(groups).sort((a, b) => {
      if (a.vendorKey === 'uncategorized') return 1;
      if (b.vendorKey === 'uncategorized') return -1;
      return b.totalValuation - a.totalValuation;
    });
  }, [filteredAssetsByTab]);

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

  const getMetricLabel = () => {
    if (activeTab === 'INCOME') return 'TARGET YIELD / INCOME';
    if (activeTab === 'EXPENSE') return 'BUDGET / YTD SPEND';
    return 'CURRENT VALUATION';
  };

  // Reusable Single Node Card Renderer (Differentiates Master vs Sub-Assets)
  const renderAssetNodeCard = (asset: HierarchyAssetNode, isChild: boolean = false) => {
    // 🟢 Distinct Compact Teal Row for Sub-Assets
    if (isChild) {
      return (
        <div
          key={asset.id}
          className="flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-lg bg-slate-950/90 border border-teal-500/30 border-l-4 border-l-teal-400 hover:border-teal-400/60 transition-all font-mono shadow-sm"
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="text-teal-400 font-bold text-xs shrink-0">↳</span>
            <span className="rounded bg-teal-500/10 px-2 py-0.5 text-[10px] font-bold text-teal-300 border border-teal-500/30 shrink-0">
              SUB-ASSET [{asset.asset_code}]
            </span>
            <span className="text-xs font-bold text-slate-100 truncate">
              {asset.name}
            </span>
            {asset.metadata_payload && Object.keys(asset.metadata_payload).length > 0 && (
              <span className="text-[10px] text-slate-400 truncate hidden md:inline font-sans">
                ({Object.entries(asset.metadata_payload).map(([k, v]) => `${k}: ${v}`).join(', ')})
              </span>
            )}
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <span className="text-xs font-bold text-teal-300">
              ₹{Number(asset.current_valuation || 0).toLocaleString('en-IN')}
            </span>

            <div className="flex items-center gap-1">
              <button
                onClick={() => openMatcher(asset, null, null)}
                className="rounded bg-teal-950/90 border border-teal-500/40 px-2.5 py-1 text-[10px] font-bold text-teal-300 hover:bg-teal-900/80 transition-colors cursor-pointer"
                title="Scan & Map"
              >
                🔍 Map
              </button>
              <button
                onClick={() => handleEditAsset(asset)}
                className="rounded bg-slate-800 p-1 text-slate-400 hover:text-white text-xs cursor-pointer border border-slate-700/60"
                title="Edit Details"
              >
                ✏️
              </button>
              <button
                onClick={() => handleDeleteAsset(asset.id, asset.name)}
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

    // 🟢 Master Parent Container Card
    return (
      <div
        key={asset.id}
        className="p-4 sm:p-5 rounded-xl bg-slate-900/90 border border-slate-800/90 shadow-xl space-y-3 hover:border-slate-700/80 transition-all"
      >
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
                onClick={() => handleEditAsset(asset)}
                className="rounded bg-amber-500/10 px-2.5 py-0.5 font-mono text-[10px] font-bold text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-colors flex items-center gap-1 cursor-pointer"
              >
                🏛️ GL: {asset.linked_gl_account ? `${asset.linked_gl_account}` : 'Mapped GL'}
                <span className="text-[9px] text-amber-500">✏️</span>
              </button>
            </div>

            <h3 className="font-bold font-mono text-white text-sm sm:text-base truncate">
              {asset.name}
            </h3>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <div className="text-right hidden sm:block">
              <span className="text-[9px] text-slate-400 uppercase tracking-wider block font-mono">
                {getMetricLabel()}
              </span>
              <p className="font-mono text-sm font-bold text-emerald-400">
                ₹{Number(asset.current_valuation || 0).toLocaleString('en-IN')}
              </p>
            </div>

            <div className="flex items-center gap-1 font-mono">
              <button
                onClick={() => openMatcher(asset, null, null)}
                className="rounded bg-emerald-950/80 border border-emerald-500/40 px-2 py-1 text-[10px] font-bold text-emerald-400 hover:bg-emerald-900/80 transition-colors cursor-pointer"
              >
                🔍 Scan & Map
              </button>
              <button
                onClick={() => openHistoryDrawer(asset)}
                className="rounded bg-slate-800/90 px-2 py-1 text-[10px] font-bold text-slate-300 hover:text-emerald-400 hover:bg-slate-700 transition-colors cursor-pointer border border-slate-700/80"
              >
                📜 History
              </button>
              <button
                onClick={() => handleEditAsset(asset)}
                className="rounded bg-slate-800/80 p-1 text-slate-400 hover:text-white text-xs cursor-pointer border border-slate-700/60"
              >
                ✏️
              </button>
              <button
                onClick={() => handleDeleteAsset(asset.id, asset.name)}
                className="rounded bg-slate-800/80 p-1 text-slate-400 hover:text-rose-400 text-xs cursor-pointer border border-slate-700/60"
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

        {/* Operational Identifiers & Schedules */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 rounded-lg bg-slate-950/90 p-2.5 border border-slate-800/60">
          <div className="space-y-1.5 min-w-0">
            <div className="flex items-center justify-between">
              <h4 className="text-[9px] font-bold text-slate-400 uppercase font-mono">Operational Identifiers</h4>
              <button onClick={() => handleCreateUtility(asset)} className="text-[9px] text-emerald-400 font-mono">+ Add Utility</button>
            </div>
            {asset.operational_accounts.length === 0 ? (
              <p className="text-[10px] text-slate-600 italic font-mono">None registered</p>
            ) : (
              <ul className="space-y-1 font-mono">
                {asset.operational_accounts.map((op) => (
                  <li key={op.id} className="flex items-center justify-between text-[10px] text-slate-300 bg-slate-900/90 p-1.5 rounded border border-slate-800">
                    <span>{op.provider_name} ({op.consumer_identifier})</span>
                    <div className="flex items-center gap-1">
                      <button onClick={() => openMatcher(asset, null, op)} className="text-[9px] text-emerald-400 font-bold">Map</button>
                      <button onClick={() => handleEditUtility(asset, op)} className="text-slate-400 hover:text-white text-[10px] p-0.5 transition-colors cursor-pointer" title="Edit Utility">✏️</button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="space-y-1.5 min-w-0">
            <div className="flex items-center justify-between">
              <h4 className="text-[9px] font-bold text-slate-400 uppercase font-mono">Schedules & Due Dates</h4>
              <button onClick={() => handleCreateSchedule(asset)} className="text-[9px] text-emerald-400 font-mono">+ Add Reminder</button>
            </div>
            {asset.compliance_schedules.length === 0 ? (
              <p className="text-[10px] text-slate-600 italic font-mono">No pending schedules</p>
            ) : (
              <ul className="space-y-1 font-mono">
                {asset.compliance_schedules.map((sch) => (
                  <li key={sch.id} className="flex items-center justify-between text-[10px] bg-slate-900/90 p-1.5 rounded border border-slate-800">
                    <span className="text-slate-200">{sch.title}</span>
                    <div className="flex items-center gap-1">
                      <span className="text-[9px] text-amber-400 font-bold">DUE {sch.due_date}</span>
                      <button onClick={() => handleEditSchedule(asset, sch)} className="text-slate-400 hover:text-white text-[10px] p-0.5 transition-colors cursor-pointer" title="Edit Schedule">✏️</button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* 🟢 Distinct Sub-Components Container */}
        {asset.children && asset.children.length > 0 && (
          <div className="pt-2 space-y-2 border-t border-slate-800/80">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono font-bold text-teal-300 bg-teal-950 px-2 py-0.5 rounded border border-teal-500/40 uppercase tracking-wider">
                📦 LINKED SUB-ASSETS ({asset.children.length})
              </span>
            </div>
            <div className="space-y-2 pl-3 border-l-2 border-teal-500/40">
              {asset.children.map((childNode) => renderAssetNodeCard(childNode, true))}
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div
      className={
        isModal
          ? 'p-2 bg-transparent text-slate-100 space-y-4 font-sans'
          : 'min-h-screen bg-slate-950 p-6 text-slate-100 font-sans'
      }
    >
      {/* Top Banner & Switcher Tabs */}
      <div className="flex flex-wrap items-center justify-between border-b border-slate-800 pb-4 gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            Sub-Ledger & Compliance Engine
          </h1>
          <p className="text-xs text-slate-400 font-mono mt-0.5">
            Manage balance sheet assets, income yield streams, vendor cost centers, and transaction bindings.
          </p>
        </div>

        {/* Subledger Category Type Tabs */}
        <div className="flex items-center gap-1 bg-slate-900 p-1 rounded-xl border border-slate-800">
          <button
            onClick={() => setActiveTab('ASSET')}
            className={`px-3 py-1.5 text-xs font-mono font-bold rounded-lg transition-all cursor-pointer ${
              activeTab === 'ASSET'
                ? 'bg-emerald-600 text-white shadow-md'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            📦 Assets ({assets.filter((a) => getSubledgerType(a) === 'ASSET').length})
          </button>
          <button
            onClick={() => setActiveTab('INCOME')}
            className={`px-3 py-1.5 text-xs font-mono font-bold rounded-lg transition-all cursor-pointer ${
              activeTab === 'INCOME'
                ? 'bg-cyan-600 text-white shadow-md'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            💰 Income ({assets.filter((a) => getSubledgerType(a) === 'INCOME').length})
          </button>
          <button
            onClick={() => setActiveTab('EXPENSE')}
            className={`px-3 py-1.5 text-xs font-mono font-bold rounded-lg transition-all cursor-pointer ${
              activeTab === 'EXPENSE'
                ? 'bg-rose-600 text-white shadow-md'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            📊 Expenses ({assets.filter((a) => getSubledgerType(a) === 'EXPENSE').length})
          </button>
        </div>

        {!isModal && (
          <div className="flex items-center gap-2">
            <button
              onClick={handleCreateAsset}
              className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-bold font-mono text-white hover:bg-emerald-500 transition-colors cursor-pointer shadow-md"
            >
              + New Sub-Ledger
            </button>
            <button
              onClick={loadDashboardData}
              className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-bold font-mono text-slate-300 hover:bg-slate-700 transition-colors cursor-pointer"
            >
              🔄 Refresh
            </button>
          </div>
        )}
      </div>

      {loading ? (
        <div className="py-16 text-center text-xs text-slate-400 font-mono flex flex-col items-center gap-2">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-emerald-500"></div>
          <span>Loading sub-ledger entities and compliance queues...</span>
        </div>
      ) : (
        <div className={`grid grid-cols-12 gap-6 ${isModal ? 'mt-1' : 'mt-6'}`}>
          {/* Left Side: Subledger Cards */}
          <div className="col-span-12 lg:col-span-8 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-bold tracking-wider text-slate-400 uppercase font-mono">
                {activeTab} SUB-LEDGER NODES ({filteredAssetsByTab.length})
              </h2>
              {isModal && (
                <button
                  onClick={handleCreateAsset}
                  className="rounded bg-emerald-600 px-2.5 py-1 text-[11px] font-bold font-mono text-white hover:bg-emerald-500 transition-colors cursor-pointer"
                >
                  + New Sub-Ledger
                </button>
              )}
            </div>

            {filteredAssetsByTab.length === 0 ? (
              <div className="p-8 border border-dashed border-slate-800/80 rounded-xl text-center text-slate-500 text-xs font-mono space-y-3 bg-slate-900/30">
                <p>No subledger entities registered under {activeTab} mode yet.</p>
                <button
                  onClick={handleCreateAsset}
                  className="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-emerald-400 rounded text-xs font-bold font-mono transition-colors cursor-pointer border border-slate-700"
                >
                  Register First {activeTab} Node
                </button>
              </div>
            ) : (
              structuredVendorEntries.map((group) => {
                const isExpanded = expandedVendors[group.vendorKey] !== false;

                return (
                  <div
                    key={group.vendorKey}
                    className="rounded-xl border border-slate-800/90 bg-slate-900/60 overflow-hidden shadow-xl"
                  >
                    {/* Collapsible Group Header */}
                    <div
                      onClick={() => toggleVendor(group.vendorKey)}
                      className="flex items-center justify-between bg-slate-800/80 px-4 py-3 cursor-pointer hover:bg-slate-800 transition-colors select-none border-b border-slate-800/60"
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-[10px] text-emerald-400 font-mono">
                          {isExpanded ? '▼' : '▶'}
                        </span>
                        <h3 className="text-xs font-bold text-white font-mono flex items-center gap-2">
                          🏬 {group.vendorName}
                          <span className="text-[10px] font-mono text-slate-400 bg-slate-950 px-2 py-0.5 rounded-full border border-slate-700/80">
                            {group.totalNodeCount} {group.totalNodeCount === 1 ? 'Node' : 'Nodes'}
                          </span>
                        </h3>
                      </div>

                      <div className="flex items-center gap-6 text-xs font-mono">
                        <div className="text-right">
                          <span className="text-slate-500 block text-[9px] uppercase tracking-wider">
                            TOTAL {getMetricLabel()}
                          </span>
                          <span className="text-emerald-400 font-bold text-xs">
                            ₹{group.totalValuation.toLocaleString('en-IN')}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Hierarchy Node Cards */}
                    {isExpanded && (
                      <div className="p-4 space-y-4 bg-slate-950/40">
                        {group.rootAssets.map((rootAsset) => renderAssetNodeCard(rootAsset))}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>

          {/* Right Side: Compliance Feed */}
          <div className="col-span-12 lg:col-span-4 space-y-4">
            <h2 className="text-xs font-bold tracking-wider text-slate-400 uppercase font-mono">
              Upcoming Dues & Reminders ({pendingDues.length})
            </h2>

            <div className="rounded-xl border border-slate-800/80 bg-slate-900/90 p-4 space-y-3 shadow-xl">
              {pendingDues.length === 0 ? (
                <p className="text-xs text-slate-500 text-center py-6 font-mono">
                  🎉 No pending dues in queue!
                </p>
              ) : (
                pendingDues.map((due) => {
                  const targetAsset = assets.find((a) => a.id === due.asset);
                  return (
                    <div
                      key={due.id}
                      className="rounded-lg border border-slate-800 bg-slate-950 p-3 space-y-2.5 shadow-inner"
                    >
                      <div className="flex justify-between items-start gap-2">
                        <div className="min-w-0">
                          <p className="text-xs font-bold text-white truncate font-mono">{due.title}</p>
                          <p className="text-[10px] text-slate-400 mt-0.5 font-mono">
                            Due Date: <span className="text-amber-400 font-bold">{due.due_date}</span>
                          </p>
                        </div>
                        <span className="font-mono text-xs font-bold text-emerald-400 whitespace-nowrap">
                          ₹{Number(due.expected_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      </div>

                      {targetAsset && (
                        <button
                          onClick={() => openMatcher(targetAsset, due, null)}
                          className="w-full rounded bg-emerald-600 py-1 text-xs font-bold font-mono text-white hover:bg-emerald-500 transition-colors cursor-pointer shadow-md"
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

      {/* Modals */}
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

      <AssetFormModal
        isOpen={isAssetModalOpen}
        onClose={() => setIsAssetModalOpen(false)}
        assetToEdit={assetToEdit}
        defaultSubcategory={filterSubcategory}
        activeTab={
          assetToEdit
            ? (getSubledgerType(assetToEdit) as 'ASSET' | 'INCOME' | 'EXPENSE')
            : activeTab
        }
        onSuccess={loadDashboardData}
      />

      {selectedAsset && (
        <OperationalAccountModal
          isOpen={isOpModalOpen}
          onClose={() => setIsOpModalOpen(false)}
          asset={selectedAsset}
          utilityToEdit={utilityToEdit}
          onSuccess={loadDashboardData}
        />
      )}

      {selectedAsset && (
        <ScheduleModal
          isOpen={isScheduleModalOpen}
          onClose={() => setIsScheduleModalOpen(false)}
          asset={selectedAsset}
          scheduleToEdit={scheduleToEdit}
          onSuccess={loadDashboardData}
        />
      )}

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

export default SubLedgerDashboard;


