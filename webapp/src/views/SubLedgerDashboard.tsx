import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { subledgerApi } from '../api/subledger';
import type {
  AssetSubLedgerNode,
  AssetComplianceSchedule,
  AssetOperationalAccount,
} from '../api/subledger';

import {
  getSubledgerType,
  groupAssetsByHead,
 // type HierarchyAssetNode,
} from '../components/subledger/helper/subledgerGrouping';

import { SubledgerHeaderNav } from '../components/subledger/modules/SubledgerHeaderNav';
import { ComplianceFeed } from '../components/subledger/modules/ComplianceFeed';
import { DomainSummaryCard } from '../components/subledger/modules/DomainSummaryCard';
import { VendorSummaryCard, type VendorSubCluster } from '../components/subledger/modules/VendorSummaryCard';
import { AssetNodeCard } from '../components/subledger/modules/AssetNodeCard';

import { CandidateMatcherModal } from '../components/subledger/CandidateMatcherModal';
import { AssetFormModal } from '../components/subledger/AssetFormModal';
import { OperationalAccountModal } from '../components/subledger/OperationalAccountModal';
import { ScheduleModal } from '../components/subledger/ScheduleModal';
import { HistoryDrawerModal } from '../components/subledger/HistoryDrawerModal';

import { inrFormatter } from '../utils/classificationHelpers';
import { ArrowLeft, Wallet } from 'lucide-react';

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
  const [activeTab, setActiveTab] = useState<'ASSET' | 'INCOME' | 'EXPENSE'>('ASSET');

  // Navigation Drill-Down State
  // Level 1 = (null, null), Level 2 = (domainKey, null), Level 3 = (domainKey, vendorKey)
  const [activeDomainKey, setActiveDomainKey] = useState<string | null>(null);
  const [activeVendorKey, setActiveVendorKey] = useState<string | null>(null);

  // Modal States
  const [selectedAsset, setSelectedAsset] = useState<AssetSubLedgerNode | null>(null);
  const [selectedSchedule, setSelectedSchedule] = useState<AssetComplianceSchedule | null>(null);
  const [selectedUtility, setSelectedUtility] = useState<AssetOperationalAccount | null>(null);
  const [isMatcherOpen, setIsMatcherOpen] = useState<boolean>(false);

  const [isAssetModalOpen, setIsAssetModalOpen] = useState<boolean>(false);
  const [assetToEdit, setAssetToEdit] = useState<AssetSubLedgerNode | null>(null);

  const [isOpModalOpen, setIsOpModalOpen] = useState<boolean>(false);
  const [utilityToEdit, setUtilityToEdit] = useState<AssetOperationalAccount | null>(null);

  const [isScheduleModalOpen, setIsScheduleModalOpen] = useState<boolean>(false);
  const [scheduleToEdit, setScheduleToEdit] = useState<AssetComplianceSchedule | null>(null);

  const [isHistoryOpen, setIsHistoryOpen] = useState<boolean>(false);
  const [historyAsset, setHistoryAsset] = useState<AssetSubLedgerNode | null>(null);

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
            const term = targetCategory.toLowerCase();
            return (
              String(a.category || '').toLowerCase().includes(term) ||
              String(a.category_display || '').toLowerCase().includes(term) ||
              String(a.linked_gl_account || '').toLowerCase().includes(term) ||
              String(a.name || '').toLowerCase().includes(term)
            );
          })
        : assetsData;

      setAssets(filteredAssets);
      setPendingDues(duesData);
    } catch (err) {
      console.error('Failed to load subledger data:', err);
    } finally {
      setLoading(false);
    }
  }, [filterSubcategory]);

  useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  const filteredAssetsByTab = useMemo(() => {
    return assets.filter((asset: any) => getSubledgerType(asset) === activeTab);
  }, [assets, activeTab]);

  const categoryGroups = useMemo(() => {
    return groupAssetsByHead(filteredAssetsByTab);
  }, [filteredAssetsByTab]);

  const selectedDomainGroup = useMemo(() => {
    if (!activeDomainKey) return null;
    return categoryGroups.find((g) => g.groupKey === activeDomainKey) || null;
  }, [categoryGroups, activeDomainKey]);

  // Compute vendor subclusters for the active domain
  const vendorClusters = useMemo<VendorSubCluster[]>(() => {
    if (!selectedDomainGroup) return [];
    const map: Record<string, VendorSubCluster> = {};

    selectedDomainGroup.rootAssets.forEach((asset) => {
      const vName =
        asset.vendor_name ||
        (asset as any).vendor_detail?.name ||
        (typeof (asset as any).vendor === 'string' && (asset as any).vendor.trim().length > 0
          ? (asset as any).vendor
          : null) ||
        (selectedDomainGroup.isCashDomain ? 'Float Account' : 'Direct / Independent');

      const vKey = vName.toLowerCase().replace(/[^a-z0-9]/g, '_');

      if (!map[vKey]) {
        map[vKey] = {
          vendorKey: vKey,
          vendorName: vName,
          assets: [],
          totalValuation: 0,
        };
      }

      map[vKey].assets.push(asset);
      map[vKey].totalValuation += Number(asset.current_valuation || 0);
    });

    return Object.values(map).sort((a, b) => {
      if (a.vendorName.includes('Independent') || a.vendorName.includes('Direct')) return 1;
      if (b.vendorName.includes('Independent') || b.vendorName.includes('Direct')) return -1;
      return b.totalValuation - a.totalValuation;
    });
  }, [selectedDomainGroup]);

  const selectedVendorCluster = useMemo(() => {
    if (!activeVendorKey) return null;
    return vendorClusters.find((v) => v.vendorKey === activeVendorKey) || null;
  }, [vendorClusters, activeVendorKey]);

  const getMetricLabel = () => {
    if (activeTab === 'INCOME') return 'TARGET YIELD / INCOME';
    if (activeTab === 'EXPENSE') return 'BUDGET / YTD SPEND';
    return 'CURRENT VALUATION';
  };

  return (
    <div className={isModal ? 'p-2 bg-transparent text-slate-100 space-y-4 font-sans' : 'min-h-screen bg-slate-950 p-6 text-slate-100 font-sans'}>
      <SubledgerHeaderNav
        activeTab={activeTab}
        onSelectTab={(tab) => {
          setActiveTab(tab);
          setActiveDomainKey(null);
          setActiveVendorKey(null);
        }}
        assetCount={assets.filter((a) => getSubledgerType(a) === 'ASSET').length}
        incomeCount={assets.filter((a) => getSubledgerType(a) === 'INCOME').length}
        expenseCount={assets.filter((a) => getSubledgerType(a) === 'EXPENSE').length}
        isModal={isModal}
        onCreateAsset={() => { setAssetToEdit(null); setIsAssetModalOpen(true); }}
        onRefresh={loadDashboardData}
      />

      {loading ? (
        <div className="py-20 text-center text-xs text-slate-400 font-mono flex flex-col items-center gap-2">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-emerald-500" />
          <span>Loading subledger entities...</span>
        </div>
      ) : (
        <div className={`grid grid-cols-12 gap-6 ${isModal ? 'mt-1' : 'mt-6'}`}>
          <div className="col-span-12 lg:col-span-8 space-y-4">

            {/* LEVEL 3: Dedicated Folio Item List (Inside a specific Vendor/Account) */}
            {selectedDomainGroup && selectedVendorCluster ? (
              <div className="space-y-4 font-mono">
                {/* 3-Level Breadcrumb Bar */}
                <div className="flex items-center justify-between bg-slate-900/80 border border-slate-800 p-3 rounded-xl">
                  <div className="flex items-center gap-2 text-xs">
                    <button
                      type="button"
                      onClick={() => { setActiveDomainKey(null); setActiveVendorKey(null); }}
                      className="text-slate-400 hover:text-emerald-400 transition-colors font-bold cursor-pointer"
                    >
                      All Domains
                    </button>
                    <span className="text-slate-600">/</span>
                    <button
                      type="button"
                      onClick={() => setActiveVendorKey(null)}
                      className="text-slate-400 hover:text-emerald-400 transition-colors font-bold cursor-pointer"
                    >
                      {selectedDomainGroup.groupTitle}
                    </button>
                    <span className="text-slate-600">/</span>
                    <span className="text-white font-bold truncate">
                      {selectedVendorCluster.vendorName}
                    </span>
                  </div>

                  <div className="text-right">
                    <span className="text-[9px] text-slate-500 uppercase block font-semibold">
                      {selectedDomainGroup.isCashDomain ? 'FLOAT BALANCE' : 'VALUATION'}
                    </span>
                    <span className="text-sm font-bold text-emerald-400 tabular-nums">
                      {inrFormatter.format(selectedVendorCluster.totalValuation)}
                    </span>
                  </div>
                </div>

                {/* Back to Vendors trigger */}
                <button
                  type="button"
                  onClick={() => setActiveVendorKey(null)}
                  className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors font-mono cursor-pointer"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  <span>Back to {selectedDomainGroup.groupTitle} Groups</span>
                </button>

                {/* Items List */}
                <div className="space-y-3">
                  {selectedVendorCluster.assets.map((asset) => (
                    <AssetNodeCard
                      key={asset.id}
                      asset={asset}
                      metricLabel={selectedDomainGroup.isCashDomain ? 'CURRENT FLOAT BALANCE' : getMetricLabel()}
                      onOpenMatcher={(a: any, sch: any, op: any) => {
                        setSelectedAsset(a);
                        setSelectedSchedule(sch || null);
                        setSelectedUtility(op || null);
                        setIsMatcherOpen(true);
                      }}
                      onOpenHistory={(a: any) => { setHistoryAsset(a); setIsHistoryOpen(true); }}
                      onEditAsset={(a: any) => { setAssetToEdit(a); setIsAssetModalOpen(true); }}
                      onDeleteAsset={async (id: string, name: string) => {
                        if (window.confirm(`Delete entity "${name}"?`)) {
                          await subledgerApi.deleteAsset(id);
                          loadDashboardData();
                        }
                      }}
                      onCreateUtility={(a: any) => { setSelectedAsset(a); setUtilityToEdit(null); setIsOpModalOpen(true); }}
                      onEditUtility={(a: any, op: any) => { setSelectedAsset(a); setUtilityToEdit(op); setIsOpModalOpen(true); }}
                      onCreateSchedule={(a: any) => { setSelectedAsset(a); setScheduleToEdit(null); setIsScheduleModalOpen(true); }}
                      onEditSchedule={(a: any, sch: any) => { setSelectedAsset(a); setScheduleToEdit(sch); setIsScheduleModalOpen(true); }}
                    />
                  ))}
                </div>
              </div>

            /* LEVEL 2: Vendor / Institution Card Grid (Inside Domain) */
            ) : selectedDomainGroup ? (
              <div className="space-y-4 font-mono">
                {/* 2-Level Breadcrumb Bar */}
                <div className="flex items-center justify-between bg-slate-900/80 border border-slate-800 p-3 rounded-xl">
                  <div className="flex items-center gap-2.5">
                    <button
                      type="button"
                      onClick={() => setActiveDomainKey(null)}
                      className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-emerald-400 transition-colors font-bold cursor-pointer"
                    >
                      <ArrowLeft className="w-4 h-4" />
                      <span>All Domains</span>
                    </button>
                    <span className="text-slate-600">/</span>
                    <span className="text-xs font-bold text-white flex items-center gap-2">
                      {selectedDomainGroup.isCashDomain && <Wallet className="w-4 h-4 text-emerald-400" />}
                      {selectedDomainGroup.groupTitle}
                    </span>
                  </div>

                  <div className="text-right">
                    <span className="text-[10px] text-slate-500 uppercase block font-semibold">
                      {selectedDomainGroup.isCashDomain ? 'CURRENT FLOAT BALANCE' : getMetricLabel()}
                    </span>
                    <span className="text-sm font-bold text-emerald-400 tabular-nums">
                      {inrFormatter.format(selectedDomainGroup.totalValuation)}
                    </span>
                  </div>
                </div>

                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold tracking-wider text-slate-400 uppercase">
                    Select Account / Counterparty ({vendorClusters.length} Groups)
                  </h3>
                </div>

                {/* Vendor / Counterparty Grid */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {vendorClusters.map((cluster) => (
                    <VendorSummaryCard
                      key={cluster.vendorKey}
                      cluster={cluster}
                      isCashDomain={selectedDomainGroup.isCashDomain}
                      metricLabel={selectedDomainGroup.isCashDomain ? 'FLOAT' : 'VALUATION'}
                      onClick={() => setActiveVendorKey(cluster.vendorKey)}
                    />
                  ))}
                </div>
              </div>

            /* LEVEL 1: High-Level Asset Head Grid (Home) */
            ) : (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-xs font-bold tracking-wider text-slate-400 uppercase font-mono">
                    {activeTab} DOMAINS ({categoryGroups.length} Heads / {filteredAssetsByTab.length} Folios)
                  </h2>
                </div>

                {categoryGroups.length === 0 ? (
                  <div className="p-8 border border-dashed border-slate-800/80 rounded-xl text-center text-slate-500 text-xs font-mono space-y-3 bg-slate-900/30">
                    <p>No subledger entities registered under {activeTab} mode yet.</p>
                    <button
                      type="button"
                      onClick={() => { setAssetToEdit(null); setIsAssetModalOpen(true); }}
                      className="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-emerald-400 rounded text-xs font-bold font-mono transition-colors cursor-pointer border border-slate-700"
                    >
                      Register First {activeTab} Node
                    </button>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {categoryGroups.map((group) => (
                      <DomainSummaryCard
                        key={group.groupKey}
                        group={group}
                        metricLabel={getMetricLabel()}
                        onClick={() => {
                          setActiveDomainKey(group.groupKey);
                          setActiveVendorKey(null);
                        }}
                      />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Right Area: Compliance Feed (4 Columns) */}
          <div className="col-span-12 lg:col-span-4 space-y-4">
            <ComplianceFeed
              pendingDues={pendingDues}
              assets={assets}
              onOpenMatcher={(asset, sch) => {
                setSelectedAsset(asset);
                setSelectedSchedule(sch);
                setSelectedUtility(null);
                setIsMatcherOpen(true);
              }}
            />
          </div>
        </div>
      )}

      {/* Modals */}
      {selectedAsset && (
        <CandidateMatcherModal
          isOpen={isMatcherOpen}
          onClose={() => {
            setIsMatcherOpen(false);
            setSelectedAsset(null);
            setSelectedSchedule(null);
            setSelectedUtility(null);
          }}
          asset={selectedAsset}
          schedule={selectedSchedule}
          utility={selectedUtility}
          onSuccess={loadDashboardData}
        />
      )}

      <AssetFormModal
        isOpen={isAssetModalOpen}
        onClose={() => {
          setIsAssetModalOpen(false);
          setAssetToEdit(null);
        }}
        assetToEdit={assetToEdit}
        defaultSubcategory={filterSubcategory}
        activeTab={assetToEdit ? (getSubledgerType(assetToEdit) as any) : activeTab}
        onSuccess={loadDashboardData}
      />

      {selectedAsset && (
        <OperationalAccountModal
          isOpen={isOpModalOpen}
          onClose={() => {
            setIsOpModalOpen(false);
            setUtilityToEdit(null);
          }}
          asset={selectedAsset}
          utilityToEdit={utilityToEdit}
          onSuccess={loadDashboardData}
        />
      )}

      {selectedAsset && (
        <ScheduleModal
          isOpen={isScheduleModalOpen}
          onClose={() => {
            setIsScheduleModalOpen(false);
            setScheduleToEdit(null);
          }}
          asset={selectedAsset}
          scheduleToEdit={scheduleToEdit}
          onSuccess={loadDashboardData}
        />
      )}

      {historyAsset && (
        <HistoryDrawerModal
          isOpen={isHistoryOpen}
          onClose={() => {
            setIsHistoryOpen(false);
            setHistoryAsset(null);
          }}
          asset={historyAsset}
        />
      )}
    </div>
  );
};

export default SubLedgerDashboard;