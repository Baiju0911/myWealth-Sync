import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { 
  getSuspenseClusters, 
  applyReclassification, 
  getTaxonomyTree, 
  addTaxonomyNode,
  getSuggestedRule,
  type SuggestedRule, 
  type TaxonomyOption, 
  type ExtendedCluster,
  type Cluster,
} from '../api/api';

import { calculateSelectedMetrics, filterClustersByQuery } from '../utils/classificationHelpers';
import { ClusterListPanel } from '../components/classification/ClusterListPanel';
import { TaxonomyMapperPanel } from '../components/classification/TaxonomyMapperPanel';
import { PatternSelectionModal } from '../components/classification/PatternSelectionModal';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  targetSubcategory?: string;
  accountId?: number;
}

export const ClassificationWorkbenchModal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  targetSubcategory = 'Suspense Account',
  accountId,
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

  useEffect(() => {
    if (isOpen) {
      fetchClusters(targetSubcategory, accountId);
      loadTaxonomy();
    }
  }, [isOpen, targetSubcategory, accountId]);

  useEffect(() => {
    if (selectedTxnIds.length === 0) {
      setActivePreviewCluster(null);
      setSuggestedRule(null);
    }
  }, [selectedTxnIds]);

  // Auto-Fetch Rule Suggestion on Cluster Select
  useEffect(() => {
    let isMounted = true;
    const fetchSuggestion = async () => {
      if (!activePreviewCluster?.pattern) {
        if (isMounted) setSuggestedRule(null);
        return;
      }

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
  }, [activePreviewCluster, vectorType]);

  const fetchClusters = async (subcategoryName: string = targetSubcategory || 'Suspense Account', currentAccountId?: number) => {
    setLoading(true);
    setSelectedTxnIds([]);
    setActivePreviewCluster(null);
    setSuggestedRule(null);

    try {
      const data = await getSuspenseClusters(subcategoryName, currentAccountId);
      if (data?.status === 'success') {
        const list = data.clusters || [];
        setClusters(list);
        
        if (list.length > 0) {
          const firstItem = list[0]?.items?.[0];
          setVectorType(firstItem?.direction === 'INFLOW' || (firstItem?.credit || 0) > 0 ? 'Credit' : 'Debit');
        }
      }
    } catch (err) {
      console.error('Failed to load clusters:', err);
    } finally {
      setLoading(false);
    }
  };

  // const loadTaxonomy = async () => {
  //   try {
  //     const data = await getTaxonomyTree();
  //     if (data && data.length > 0) {
  //       setTaxonomyTree(data);
        
  //       let matchedCatNode = data.find((t: TaxonomyOption) => 
  //         (t.subcategories || []).includes(targetSubcategory)
  //       );

  //       if (!matchedCatNode) {
  //         matchedCatNode = data.find((t: TaxonomyOption) => t.category === 'Expense') || data[0];
  //       }

  //       setSelectedCategory(matchedCatNode.category);
  //       if (matchedCatNode.subcategories && matchedCatNode.subcategories.length > 0) {
  //         setSelectedSubcategory(
  //           matchedCatNode.subcategories.includes(targetSubcategory) 
  //             ? targetSubcategory 
  //             : matchedCatNode.subcategories[0]
  //         );
  //       }
  //     }
  //   } catch (err) {
  //     console.error('Failed to load dynamic taxonomy:', err);
  //   }
  // };

  const loadTaxonomy = async () => {
    try {
      const data = await getTaxonomyTree();
      if (data && data.length > 0) {
        setTaxonomyTree(data);

        // Helper to extract string name from string OR object
        const getSubName = (sub: any): string => 
          typeof sub === 'object' && sub !== null 
            ? String(sub.subcategory || sub.name || sub.title || '') 
            : String(sub || '');

        const targetName = String(targetSubcategory || 'Suspense Account');

        // Find matching node comparing extracted strings
        let matchedCatNode = data.find((t: TaxonomyOption) => 
          (t.subcategories || []).some((s: any) => getSubName(s) === targetName)
        );

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
  };


  // const availableSubcategories = useMemo(() => {
  //   if (!taxonomyTree || taxonomyTree.length === 0) return [];
  //   const found = taxonomyTree.find((item: TaxonomyOption) => item.category === selectedCategory) || taxonomyTree[0];
  //   return found ? found.subcategories || [] : [];
  // }, [taxonomyTree, selectedCategory]);

  const availableSubcategories = useMemo(() => {
    if (!taxonomyTree || taxonomyTree.length === 0) return [];
    
    const found = taxonomyTree.find((item: TaxonomyOption) => item.category === selectedCategory) || taxonomyTree[0];
    const rawList = found ? found.subcategories || [] : [];

    // Ensure array contains ONLY plain primitive strings for <option> components
    return rawList
      .map((sub: any) => {
        if (typeof sub === 'object' && sub !== null) {
          return String(sub.subcategory || sub.name || sub.title || '');
        }
        return String(sub || '');
      })
      .filter(Boolean);
  }, [taxonomyTree, selectedCategory]);
  
  const filteredClusters = useMemo(() => filterClustersByQuery(clusters, searchQuery), [clusters, searchQuery]);
  const visibleTxnIds = useMemo(() => filteredClusters.flatMap((c) => c.transaction_ids || []), [filteredClusters]);
  const selectedSummary = useMemo(() => calculateSelectedMetrics(clusters, selectedTxnIds), [clusters, selectedTxnIds]);

  const activeVendorName = useMemo(() => {
    if (!activePreviewCluster) return '';
    return (activePreviewCluster.pattern || '').replace(/^#+/, '').trim();
  }, [activePreviewCluster]);

  const handleSelectCluster = useCallback((cluster: ExtendedCluster | Cluster) => {
    setActivePreviewCluster(cluster);
    const sampleItem = cluster.items?.[0];
    if (sampleItem) {
      setVectorType(sampleItem.direction === 'INFLOW' || (sampleItem.credit || 0) > 0 ? 'Credit' : 'Debit');
    }
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

  const handleOpenPatternSelectionFlow = () => {
    if (selectedSummary.allTxnIds.length === 0) return;
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

      if (data?.status === 'success') {
        setIsPatternModalOpen(false);
        await fetchClusters(targetSubcategory);
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
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        width: '100vw',
        height: '100vh',
        backgroundColor: 'rgba(0, 0, 0, 0.85)',
        backdropFilter: 'blur(8px)',
        zIndex: 999999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
        boxSizing: 'border-box',
        fontFamily: 'monospace',
      }}
    >
      <div
        style={{
          backgroundColor: '#09090b',
          border: '1px solid #27272a',
          borderRadius: '16px',
          width: '100%',
          maxWidth: '1100px',
          height: '80vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.75)',
          overflow: 'hidden',
          color: '#f4f4f5',
        }}
      >
        {/* Header Bar */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 24px', borderBottom: '1px solid #27272a', backgroundColor: '#18181b' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '14px', fontWeight: 'bold', textTransform: 'uppercase', color: '#f4f4f5', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: vectorType === 'Debit' ? '#ef4444' : '#10b981' }} />
              Classification Workbench — {targetSubcategory || 'Suspense Account'}
              <span style={{ fontSize: '10px', padding: '2px 6px', borderRadius: '4px', backgroundColor: '#27272a', color: vectorType === 'Debit' ? '#fca5a5' : '#6ee7b7' }}>
                {vectorType === 'Debit' ? 'OUTFLOW (DR)' : 'INFLOW (CR)'}
              </span>
            </h2>
            <p style={{ margin: '4px 0 0 0', fontSize: '11px', color: '#71717a' }}>
              Reviewing merchant clusters under <strong style={{ color: '#e4e4e7' }}>{targetSubcategory || 'Suspense Account'}</strong>.
            </p>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#71717a', fontSize: '18px', cursor: 'pointer', padding: '4px 8px', borderRadius: '6px' }}>
            ✕
          </button>
        </div>

        {/* Workspace Body */}
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          <ClusterListPanel
            loading={loading}
            filteredClusters={filteredClusters}
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
          />
        </div>
      </div>

      {/* STEP-2 PATTERN ANCHOR SELECTION SUB-MODAL */}
      <PatternSelectionModal
        isOpen={isPatternModalOpen}
        selectedTxnIds={selectedSummary.allTxnIds}
        targetCategory={selectedCategory}
        targetSubcategory={selectedSubcategory}
        activeVendorName={activeVendorName}
        upiStrategy={upiStrategy}
        onClose={() => setIsPatternModalOpen(false)}
        onConfirm={handleFinalReclassificationSubmit}
        isSubmitting={submitting}
      />
    </div>,
    document.body
  );
};

