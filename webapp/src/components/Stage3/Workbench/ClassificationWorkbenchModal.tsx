import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { 
  getSuspenseClusters, 
  applyReclassification, 
  getTaxonomyTree, 
  addTaxonomyNode, 
  getSuggestedRule, 
  getClusterLineItems,
  type SuggestedRule, 
  type TaxonomyOption, 
  type ExtendedCluster, 
  type Cluster,
} from '../../../api/api';
import { subledgerApi } from '../../../api/subledger';

import { calculateSelectedMetrics } from '../../../utils/classificationHelpers';
import { ClusterListPanel } from './ClusterListPanel';
import { TaxonomyMapperPanel, clearSubledgerBreakdownCache } from './TaxonomyMapperPanel';
import { PatternSelectionModal } from './PatternSelectionModal';
import { AssetFormModal } from '../../subledger/AssetFormModal';
import type { TaxonomyMatchContext } from '../../subledger/CandidateMatcherModal';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  targetSubcategory?: string;
  accountId?: number;
  subledgerCapableSet?: Set<string>;
  onOpenSubledgerDrawer?: (subcategory: string, matchContext?: TaxonomyMatchContext) => void;
  onOpenOperationsHub?: (subcategory: string) => void;
}

const DEFAULT_SUBLEDGER_CAPABLE_HEADS = new Set<string>([
  'Suspense Account',
  'Gold & Precious Metals',
  'ShareMarket & Mutual Funds',
  'Real Estate',
  'Insurance Assets',
  'Fixed Deposits',
  'Loans & Advances',
  'Sundry Debtors',
  'Sundry Creditors',
]);

export const ClassificationWorkbenchModal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  targetSubcategory = 'Suspense Account',
  accountId,
  subledgerCapableSet = DEFAULT_SUBLEDGER_CAPABLE_HEADS,
  onOpenSubledgerDrawer,
}) => {
  const [clusters, setClusters] = useState<ExtendedCluster[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');

  const [selectedTxnIds, setSelectedTxnIds] = useState<string[]>([]);
  const [activePreviewCluster, setActivePreviewCluster] = useState<ExtendedCluster | Cluster | null>(null);

  const [vectorType, setVectorType] = useState<'Debit' | 'Credit'>('Debit');
  const [isPatternModalOpen, setIsPatternModalOpen] = useState<boolean>(false);
  const [suggestedRule, setSuggestedRule] = useState<SuggestedRule | null>(null);

  const [selectedCategory, setSelectedCategory] = useState<string>('Expense');
  const [selectedSubcategory, setSelectedSubcategory] = useState<string>('Housing & Rent');
  const [saveRule, setSaveRule] = useState<boolean>(true);
  const [upiStrategy, setUpiStrategy] = useState<'vendor' | 'auto_consolidate'>('auto_consolidate');

  const [taxonomyTree, setTaxonomyTree] = useState<TaxonomyOption[]>([]);

  const [isCreatingNew, setIsCreatingNew] = useState<boolean>(false);
  const [newCatInput, setNewCatInput] = useState<string>('');
  const [newSubInput, setNewSubInput] = useState<string>('');
  const [savingNewTaxonomy, setSavingNewTaxonomy] = useState<boolean>(false);

  // Folio Direct Creation Bridge Modal
  const [isFolioModalOpen, setIsFolioModalOpen] = useState<boolean>(false);
  const [pendingTargetSubcategory, setPendingTargetSubcategory] = useState<string>('');
  const [pendingFolioBindId, setPendingFolioBindId] = useState<string | null>(null);

  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastExecutedSearchRef = useRef<string>('');
  const isFirstMountRef = useRef<boolean>(true);

  // Central cluster fetcher
  const loadClusters = useCallback(async (
    subcategoryName: string,
    currentAccountId?: number,
    query?: string
  ) => {
    setLoading(true);

    try {
      const data = await getSuspenseClusters(subcategoryName, currentAccountId, query);
      if (data?.status === 'success') {
        const list = (data.clusters || []) as ExtendedCluster[];
        setClusters(list);

        if (list.length > 0) {
          setActivePreviewCluster((prev) => {
            if (!prev) {
              const first = list[0];
              const outflow = (first.total_outflow ?? first.total_amount ?? 0) > 0;
              setVectorType(outflow ? 'Debit' : 'Credit');
              return first;
            }
            return prev;
          });
        }
      }
    } catch (err) {
      console.error('Failed to load clusters:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadTaxonomy = useCallback(async () => {
    try {
      const data = await getTaxonomyTree();
      if (data && data.length > 0) {
        setTaxonomyTree(data);

        const getSubName = (sub: any): string => 
          typeof sub === 'object' && sub !== null 
            ? String(sub.subcategory || sub.name || sub.title || '') 
            : String(sub || '');

        const targetName = String(targetSubcategory || 'Suspense Account');

        let matchedCatNode = data.find((t: TaxonomyOption) => 
          (t.subcategories || []).some((s: any) => getSubName(s).toLowerCase() === targetName.toLowerCase())
        );

        if (!matchedCatNode) {
          if (
            targetName.toLowerCase().includes('gold') || 
            targetName.toLowerCase().includes('asset') || 
            targetName.toLowerCase().includes('share') ||
            targetName.toLowerCase().includes('deposit') ||
            targetName.toLowerCase().includes('real estate')
          ) {
            matchedCatNode = data.find((t: TaxonomyOption) => t.category === 'Asset');
          }
        }

        if (!matchedCatNode) {
          matchedCatNode = data.find((t: TaxonomyOption) => t.category === 'Expense') || data[0];
        }

        setSelectedCategory(matchedCatNode.category);

        const currentSubs = (matchedCatNode.subcategories || []).map(getSubName).filter(Boolean);
        if (currentSubs.length > 0) {
          setSelectedSubcategory(
            currentSubs.includes(targetName) ? targetName : currentSubs[0]
          );
        }
      }
    } catch (err) {
      console.error('Failed to load dynamic taxonomy:', err);
    }
  }, [targetSubcategory]);

  useEffect(() => {
    if (isOpen) {
      isFirstMountRef.current = true;
      lastExecutedSearchRef.current = '';
      setSearchQuery('');
      setSelectedTxnIds([]);
      setActivePreviewCluster(null);

      loadClusters(targetSubcategory, accountId, '');
      loadTaxonomy();
    }
  }, [isOpen, targetSubcategory, accountId, loadClusters, loadTaxonomy]);

  useEffect(() => {
    if (!isOpen) return;

    if (isFirstMountRef.current) {
      isFirstMountRef.current = false;
      return;
    }

    const trimmed = searchQuery.trim();
    if (trimmed === lastExecutedSearchRef.current) return;

    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);

    searchDebounceRef.current = setTimeout(() => {
      lastExecutedSearchRef.current = trimmed;
      loadClusters(targetSubcategory, accountId, trimmed);
    }, 350);

    return () => {
      if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    };
  }, [searchQuery, isOpen, targetSubcategory, accountId, loadClusters]);

  useEffect(() => {
    let isMounted = true;
    const fetchSuggestion = async () => {
      if (!activePreviewCluster?.pattern) {
        if (isMounted) setSuggestedRule(null);
        return;
      }
      console.log('ACTIVE CLUSTER COMPLETE DUMP:', JSON.stringify(activePreviewCluster, null, 2));
      const cleanPattern = activePreviewCluster.pattern.replace(/^#+/, '');
      const suggestion = await getSuggestedRule(cleanPattern, vectorType);

      if (isMounted && suggestion) {
        setSuggestedRule(suggestion);
        const targetCat = (suggestion as any).target_category || suggestion.suggested_category;
        const targetSub = (suggestion as any).target_subcategory || suggestion.suggested_subcategory;

        if (targetCat) setSelectedCategory(targetCat);
        if (targetSub) setSelectedSubcategory(targetSub);
      }
    };

    fetchSuggestion();
    return () => { isMounted = false; };
  }, [activePreviewCluster?.pattern, vectorType]);

  const availableSubcategories = useMemo(() => {
    if (!taxonomyTree || taxonomyTree.length === 0) return [];
    const found = taxonomyTree.find((item: TaxonomyOption) => item.category === selectedCategory) || taxonomyTree[0];
    const rawList = found ? found.subcategories || [] : [];

    return rawList
      .map((sub: any) => {
        if (typeof sub === 'object' && sub !== null) {
          return String(sub.subcategory || sub.name || sub.title || '');
        }
        return String(sub || '');
      })
      .filter(Boolean);
  }, [taxonomyTree, selectedCategory]);

  const visibleTxnIds = useMemo(() => clusters.flatMap((c) => c.transaction_ids || []), [clusters]);
  const selectedSummary = useMemo(() => calculateSelectedMetrics(clusters, selectedTxnIds), [clusters, selectedTxnIds]);

  const activeVendorName = useMemo(() => {
    if (!activePreviewCluster) return '';
    return (activePreviewCluster.pattern || '').replace(/^#+/, '').trim();
  }, [activePreviewCluster]);

  const handleSelectCluster = useCallback((cluster: ExtendedCluster | Cluster) => {
    setActivePreviewCluster(cluster);
    const ext = cluster as ExtendedCluster;
    const isOutflow = (ext.total_outflow ?? ext.total_amount ?? 0) > 0;
    setVectorType(isOutflow ? 'Debit' : 'Credit');
  }, []);

  const toggleIndividualTxn = useCallback((txnId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedTxnIds((prev) => 
      prev.includes(txnId) ? prev.filter((id) => id !== txnId) : [...prev, txnId]
    );
  }, []);

  const toggleClusterTxns = useCallback((clusterTxnIds: string[], e: React.MouseEvent) => {
    e.stopPropagation();
    const allInClusterSelected = clusterTxnIds.length > 0 && clusterTxnIds.every((id) => selectedTxnIds.includes(id));
    
    if (allInClusterSelected) {
      setSelectedTxnIds((prev) => prev.filter((id) => !clusterTxnIds.includes(id)));
    } else {
      setSelectedTxnIds((prev) => Array.from(new Set([...prev, ...clusterTxnIds])));
    }
  }, [selectedTxnIds]);

  const toggleSelectAllVisible = useCallback(() => {
    const allVisibleSelected = visibleTxnIds.length > 0 && visibleTxnIds.every((id) => selectedTxnIds.includes(id));
    if (allVisibleSelected) {
      setSelectedTxnIds((prev) => prev.filter((id) => !visibleTxnIds.includes(id)));
    } else {
      setSelectedTxnIds((prev) => Array.from(new Set([...prev, ...visibleTxnIds])));
    }
  }, [visibleTxnIds, selectedTxnIds]);

  const clearAllSelections = useCallback(() => setSelectedTxnIds([]), []);

  const handleCreateTaxonomy = async () => {
    if (!newCatInput.trim() || !newSubInput.trim()) return;
    setSavingNewTaxonomy(true);
    try {
      const success = await addTaxonomyNode({
        category: newCatInput.trim(),
        subcategory: newSubInput.trim(),
      });
      if (success) {
        await loadTaxonomy();
        setSelectedCategory(newCatInput.trim());
        setSelectedSubcategory(newSubInput.trim());
        setNewCatInput('');
        setNewSubInput('');
        setIsCreatingNew(false);
      }
    } catch (err) {
      console.error('Error creating new taxonomy node:', err);
    } finally {
      setSavingNewTaxonomy(false);
    }
  };

  const handleOpenPatternSelectionFlow = (targetFolioId?: string) => {
    if (selectedSummary.allTxnIds.length === 0) return;
    setPendingFolioBindId(targetFolioId || null);
    setIsPatternModalOpen(true);
  };

  const handleFinalReclassificationSubmit = async (chosenPatterns: string[]) => {
    if (selectedSummary.allTxnIds.length === 0) return;
    setSubmitting(true);

    try {
      const data = await applyReclassification({
        transaction_ids: selectedSummary.allTxnIds,
        target_category: selectedCategory,
        target_subcategory: selectedSubcategory,
        patterns: chosenPatterns,
        save_rule: saveRule && chosenPatterns.length > 0,
        entry_type: vectorType,
        upi_strategy: vectorType === 'Debit' ? upiStrategy : 'vendor',
      } as any);

      // Bind directly to folio if user selected one
      if (data?.status === 'success' && pendingFolioBindId) {
        try {
          const selectedItems = clusters
            .flatMap((c) => (c as any).items || [])
            .filter((item) => selectedSummary.allTxnIds.includes(String(item.id || item.row_identifier)));

          for (const item of selectedItems) {
            await subledgerApi.bindTransaction({
              asset_id: pendingFolioBindId,
              row_identifier: item.row_identifier || item.id,
              transaction_date: item.transaction_date || item.date || new Date().toISOString().split('T')[0],
              amount: Number(item.debit || item.credit || item.amount || 0),
              transaction_purpose: 'ACQUISITION_PAYMENT',
              user_note: `Classified & Bound via Workbench (${selectedSubcategory})`,
            });
          }
          clearSubledgerBreakdownCache(selectedSubcategory);
        } catch (bindErr) {
          console.error('Folio direct auto-binding failed:', bindErr);
        }
      }

      if (data?.status === 'success') {
        setIsPatternModalOpen(false);
        setSelectedTxnIds([]);
        setPendingFolioBindId(null);
        await loadClusters(targetSubcategory, accountId, searchQuery);
        onSuccess();
      }
    } catch (err) {
      console.error('Failed to apply reclassification:', err);
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-9999 flex items-center justify-center p-2 sm:p-4 bg-black/90 backdrop-blur-md font-mono">
      <div className="bg-zinc-950 border border-zinc-800 rounded-2xl w-[96vw] max-w-[1720px] h-[93vh] flex flex-col shadow-2xl overflow-hidden text-zinc-100">
        
        {/* Header Bar */}
        <div className="flex justify-between items-center px-6 py-3.5 border-b border-zinc-800 bg-zinc-900/90 shrink-0">
          <div>
            <h2 className="text-xs sm:text-sm font-bold uppercase tracking-wider text-zinc-100 flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${vectorType === 'Debit' ? 'bg-rose-500' : 'bg-emerald-500'}`} />
              <span>Classification Workbench — {targetSubcategory || 'Suspense Account'}</span>
              <span className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase ${
                vectorType === 'Debit' ? 'bg-rose-950/80 text-rose-300 border border-rose-800/60' : 'bg-emerald-950/80 text-emerald-300 border border-emerald-800/60'
              }`}>
                {vectorType === 'Debit' ? 'Outflow (DR)' : 'Inflow (CR)'}
              </span>
            </h2>
            <p className="text-[11px] text-zinc-500 font-sans mt-0.5">
              Reviewing merchant clusters under <span className="text-zinc-200 font-semibold">{targetSubcategory || 'Suspense Account'}</span>
            </p>
          </div>

          <button 
            onClick={onClose} 
            className="text-zinc-400 hover:text-zinc-100 p-1.5 rounded-lg hover:bg-zinc-800 transition-colors cursor-pointer"
            title="Close Workbench (Esc)"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Workspace Split Body */}
        <div className="flex-1 flex overflow-hidden">
          <ClusterListPanel
            loading={loading}
            filteredClusters={clusters}
            selectedTxnIds={selectedTxnIds}
            visibleTxnIds={visibleTxnIds}
            activePreviewCluster={activePreviewCluster}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            setActivePreviewCluster={handleSelectCluster}
            toggleIndividualTxn={toggleIndividualTxn}
            toggleClusterTxns={toggleClusterTxns}
            toggleSelectAllVisible={toggleSelectAllVisible}
            clearAllSelections={clearAllSelections}
          />

          {/* <TaxonomyMapperPanel
            targetSubcategoryContext={targetSubcategory}
            selectedSummary={selectedSummary}
            activePreviewCluster={activePreviewCluster}
            taxonomyTree={taxonomyTree}
            availableSubcategories={availableSubcategories}
            selectedCategory={selectedCategory}
            setSelectedCategory={setSelectedCategory}
            selectedSubcategory={selectedSubcategory}
            setSelectedSubcategory={setSelectedSubcategory}
            isCreatingNew={isCreatingNew}
            setIsCreatingNew={setIsCreatingNew}
            newCatInput={newCatInput}
            setNewCatInput={setNewCatInput}
            newSubInput={newSubInput}
            setNewSubInput={setNewSubInput}
            savingNewTaxonomy={savingNewTaxonomy}
            handleCreateTaxonomy={handleCreateTaxonomy}
            saveRule={saveRule}
            setSaveRule={setSaveRule}
            upiStrategy={upiStrategy}
            setUpiStrategy={setUpiStrategy}
            vectorType={vectorType}
            submitting={submitting}
            handleApplyClassification={handleOpenPatternSelectionFlow}
            onClose={onClose}
            suggestedRule={suggestedRule}
            subledgerCapableSet={subledgerCapableSet}
            onOpenSubledgerDrawer={onOpenSubledgerDrawer}
            onOpenNewFolioModal={(sub) => {
              setPendingTargetSubcategory(sub);
              setIsFolioModalOpen(true);
            }}
          /> */}
          {/* Memoized Interceptor to inject In-Memory Staged Cluster Rows */}
          <TaxonomyMapperPanel
            targetSubcategoryContext={targetSubcategory}
            selectedSummary={selectedSummary}
            activePreviewCluster={activePreviewCluster}
            taxonomyTree={taxonomyTree}
            availableSubcategories={availableSubcategories}
            selectedCategory={selectedCategory}
            setSelectedCategory={setSelectedCategory}
            selectedSubcategory={selectedSubcategory}
            setSelectedSubcategory={setSelectedSubcategory}
            isCreatingNew={isCreatingNew}
            setIsCreatingNew={setIsCreatingNew}
            newCatInput={newCatInput}
            setNewCatInput={setNewCatInput}
            newSubInput={newSubInput}
            setNewSubInput={setNewSubInput}
            savingNewTaxonomy={savingNewTaxonomy}
            handleCreateTaxonomy={handleCreateTaxonomy}
            saveRule={saveRule}
            setSaveRule={setSaveRule}
            upiStrategy={upiStrategy}
            setUpiStrategy={setUpiStrategy}
            vectorType={vectorType}
            submitting={submitting}
            handleApplyClassification={handleOpenPatternSelectionFlow}
            onClose={onClose}
            suggestedRule={suggestedRule}
            subledgerCapableSet={subledgerCapableSet}
            // onOpenSubledgerDrawer={async (sub, incomingContext) => {
            //   if (!onOpenSubledgerDrawer) return;

            //   let clusterRows =
            //     (activePreviewCluster as any)?.items ||
            //     (activePreviewCluster as any)?.transactions ||
            //     [];

            //   // 🎯 THE BRIDGE: Await granular line items if not loaded in memory
            //   if (
            //     clusterRows.length === 0 &&
            //     Array.isArray(activePreviewCluster?.transaction_ids) &&
            //     activePreviewCluster.transaction_ids.length > 0
            //   ) {
            //     try {
            //       console.log('⚡ [WORKBENCH] Fetching granular line items for cluster before drawer open...');
            //       const fetchedRows = await getClusterLineItems(activePreviewCluster.transaction_ids);
            //       if (Array.isArray(fetchedRows) && fetchedRows.length > 0) {
            //         clusterRows = fetchedRows;
            //       }
            //     } catch (err) {
            //       console.error('Failed to fetch cluster line items for subledger:', err);
            //     }
            //   }

            //   const inspectingPattern = (activePreviewCluster?.pattern || '').replace(/^#+/, '').trim();

            //   console.log('🔍 [WORKBENCH -> DRAWER DISPATCH - RESOLVED]', {
            //     sub,
            //     clusterRowsCount: clusterRows.length,
            //     inspectingPattern,
            //     sampleFirstRow: clusterRows[0],
            //   });

            //   const enrichedContext: TaxonomyMatchContext = {
            //     category: selectedCategory,
            //     subcategory: sub || selectedSubcategory,
            //     defaultKeyword: inspectingPattern || incomingContext?.defaultKeyword || '',
            //     stagedItems: clusterRows,
            //     selectedRowIds: selectedTxnIds.length > 0
            //       ? selectedTxnIds
            //       : clusterRows.map((r: any) => r.row_identifier || String(r.id)),
            //     ...incomingContext,
            //   };

            //   onOpenSubledgerDrawer(sub, enrichedContext);
            // }}
            onOpenSubledgerDrawer={async (sub, incomingContext) => {
              if (!onOpenSubledgerDrawer) return;

              // 🎯 1. Collect ALL transaction IDs across ALL visible clusters in workbench
              const allClusterTxnIds = clusters.flatMap((c) => c.transaction_ids || []);
              
              // Also check if any clusters already have in-memory items
              let combinedItems = clusters.flatMap(
                (c) => (c as any).items || (c as any).transactions || []
              );

              // 🎯 2. If granular items aren't loaded, fetch ALL cluster line items
              if (combinedItems.length < allClusterTxnIds.length && allClusterTxnIds.length > 0) {
                try {
                  console.log('⚡ [WORKBENCH] Fetching complete line items across all clusters for subledger:', allClusterTxnIds.length);
                  const fetchedRows = await getClusterLineItems(allClusterTxnIds);
                  if (Array.isArray(fetchedRows) && fetchedRows.length > 0) {
                    combinedItems = fetchedRows;
                  }
                } catch (err) {
                  console.error('Failed to fetch full cluster line items for subledger:', err);
                }
              }

              console.log('🔍 [WORKBENCH -> DRAWER DISPATCH - COMPLETE SUBLEDGER DATA]', {
                sub,
                totalClusters: clusters.length,
                totalTransactionsCount: combinedItems.length,
                sampleFirstRow: combinedItems[0],
              });

              const enrichedContext: TaxonomyMatchContext = {
                category: selectedCategory,
                subcategory: sub || selectedSubcategory,
                // Don't pin defaultKeyword to a single cluster when opening hub for all
                defaultKeyword: incomingContext?.defaultKeyword || '',
                stagedItems: combinedItems,
                selectedRowIds: selectedTxnIds.length > 0 
                  ? selectedTxnIds 
                  : combinedItems.map((r: any) => r.row_identifier || String(r.id)),
                ...incomingContext,
              };

              onOpenSubledgerDrawer(sub, enrichedContext);
            }}
            onOpenNewFolioModal={(sub) => {
              setPendingTargetSubcategory(sub);
              setIsFolioModalOpen(true);
            }}
          />
        </div>                                     
      </div>

      {/* Pattern Modal */}
      <PatternSelectionModal
        isOpen={isPatternModalOpen}
        selectedTxnIds={selectedSummary.allTxnIds}
        targetCategory={selectedCategory}
        targetSubcategory={selectedSubcategory}
        activeVendorName={activeVendorName}
        upiStrategy={upiStrategy}
        onClose={() => {
          setIsPatternModalOpen(false);
          setPendingFolioBindId(null);
        }}
        onConfirm={handleFinalReclassificationSubmit}
        isSubmitting={submitting}
      />

      {/* Direct Folio Creation Modal */}
      <AssetFormModal
        isOpen={isFolioModalOpen}
        onClose={() => setIsFolioModalOpen(false)}
        defaultSubcategory={pendingTargetSubcategory || selectedSubcategory}
        activeTab="ASSET"
        onSuccess={() => {
          clearSubledgerBreakdownCache(pendingTargetSubcategory || selectedSubcategory);
          loadClusters(targetSubcategory, accountId, searchQuery);
        }}
      />
    </div>,
    document.body
  );
};

export default ClassificationWorkbenchModal;