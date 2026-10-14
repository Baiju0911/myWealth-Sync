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
} from '../components/subledger/helper/subledgerGrouping';

import { SubledgerHeaderNav } from '../components/subledger/modules/SubledgerHeaderNav';
import { AssetGroupContainer } from '../components/subledger/modules/AssetGroupContainer';
import { ComplianceFeed } from '../components/subledger/modules/ComplianceFeed';

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
  const [activeTab, setActiveTab] = useState<'ASSET' | 'INCOME' | 'EXPENSE'>('ASSET');
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});

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

  const toggleGroup = (key: string) => {
    setExpandedGroups((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const filteredAssetsByTab = useMemo(() => {
    return assets.filter((asset: any) => getSubledgerType(asset) === activeTab);
  }, [assets, activeTab]);

  const categoryGroups = useMemo(() => {
    return groupAssetsByHead(filteredAssetsByTab);
  }, [filteredAssetsByTab]);

  const getMetricLabel = () => {
    if (activeTab === 'INCOME') return 'TARGET YIELD / INCOME';
    if (activeTab === 'EXPENSE') return 'BUDGET / YTD SPEND';
    return 'CURRENT VALUATION';
  };

  return (
    <div className={isModal ? 'p-2 bg-transparent text-slate-100 space-y-4 font-sans' : 'min-h-screen bg-slate-950 p-6 text-slate-100 font-sans'}>
      <SubledgerHeaderNav
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        assetCount={assets.filter((a) => getSubledgerType(a) === 'ASSET').length}
        incomeCount={assets.filter((a) => getSubledgerType(a) === 'INCOME').length}
        expenseCount={assets.filter((a) => getSubledgerType(a) === 'EXPENSE').length}
        isModal={isModal}
        onCreateAsset={() => { setAssetToEdit(null); setIsAssetModalOpen(true); }}
        onRefresh={loadDashboardData}
      />

      {loading ? (
        <div className="py-16 text-center text-xs text-slate-400 font-mono flex flex-col items-center gap-2">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-emerald-500" />
          <span>Loading subledger entities...</span>
        </div>
      ) : (
        <div className={`grid grid-cols-12 gap-6 ${isModal ? 'mt-1' : 'mt-6'}`}>
          <div className="col-span-12 lg:col-span-8 space-y-4">
            <h2 className="text-xs font-bold tracking-wider text-slate-400 uppercase font-mono">
              {activeTab} DOMAINS ({categoryGroups.length} Heads / {filteredAssetsByTab.length} Folios)
            </h2>

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
              categoryGroups.map((group) => (
                <AssetGroupContainer
                  key={group.groupKey}
                  group={group}
                  isExpanded={expandedGroups[group.groupKey] !== false}
                  metricLabel={getMetricLabel()}
                  onToggleExpand={toggleGroup}
                  onOpenMatcher={(asset: any, sch: any, op: any) => {
                    setSelectedAsset(asset);
                    setSelectedSchedule(sch || null);
                    setSelectedUtility(op || null);
                    setIsMatcherOpen(true);
                  }}
                  onOpenHistory={(asset: any) => { setHistoryAsset(asset); setIsHistoryOpen(true); }}
                  onEditAsset={(asset: any) => { setAssetToEdit(asset); setIsAssetModalOpen(true); }}
                  onDeleteAsset={async (id: string, name: string) => {
                    if (window.confirm(`Delete entity "${name}"?`)) {
                      await subledgerApi.deleteAsset(id);
                      loadDashboardData();
                    }
                  }}
                  onCreateUtility={(asset: any) => { setSelectedAsset(asset); setUtilityToEdit(null); setIsOpModalOpen(true); }}
                  onEditUtility={(asset: any, op: any) => { setSelectedAsset(asset); setUtilityToEdit(op); setIsOpModalOpen(true); }}
                  onCreateSchedule={(asset: any) => { setSelectedAsset(asset); setScheduleToEdit(null); setIsScheduleModalOpen(true); }}
                  onEditSchedule={(asset: any, sch: any) => { setSelectedAsset(asset); setScheduleToEdit(sch); setIsScheduleModalOpen(true); }}
                />
              ))
            )}
          </div>

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

      {/* Candidate Matcher Modal */}
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

      {/* Asset Form Modal */}
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

      {/* Operational Account Modal */}
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

      {/* Schedule Modal */}
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

      {/* History Drawer Modal */}
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