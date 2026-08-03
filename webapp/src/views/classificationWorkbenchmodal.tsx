import React, { useState, useEffect, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { 
  getSuspenseClusters, 
  applyReclassification, 
  getTaxonomyTree, 
  addTaxonomyNode,
  getSuggestedRule, // 👈 Import API function
  type SuggestedRule, // 👈 Import interface
  type TaxonomyOption, 
  type ExtendedCluster,
  type Cluster,
} from '../api';

import { calculateSelectedMetrics, filterClustersByQuery } from '../utils/classificationHelpers';
import { ClusterListPanel } from '../components/classification/ClusterlistPanel.tsx';
import { TaxonomyMapperPanel } from '../components/classification/TaxonomyMapperPanel.tsx';

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

  // 🟢 Direction Vector & Batch Sweep State
  const [vectorType, setVectorType] = useState<'Debit' | 'Credit'>('Debit');
  
  // 🟢 Smart Suggestion State
  const [suggestedRule, setSuggestedRule] = useState<SuggestedRule | null>(null);

  const [selectedCategory, setSelectedCategory] = useState<string>('Expense');
  const [selectedSubcategory, setSelectedSubcategory] = useState<string>('Housing & Rent');
  const [saveRule, setSaveRule] = useState<boolean>(true);

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

  // 🟢 AUTO-FETCH SUGGESTION WHEN ACTIVE CLUSTER / VECTOR CHANGES
  useEffect(() => {
    let isMounted = true;
    const fetchSuggestion = async () => {
      if (!activePreviewCluster?.pattern) {
        if (isMounted) setSuggestedRule(null);
        return;
      }

      const suggestion = await getSuggestedRule(activePreviewCluster.pattern, vectorType);
      if (isMounted) {
        setSuggestedRule(suggestion);
      }
    };

    fetchSuggestion();
    return () => {
      isMounted = false;
    };
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
          setActivePreviewCluster(list[0]);
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

  const loadTaxonomy = async () => {
    try {
      const data = await getTaxonomyTree();
      if (data && data.length > 0) {
        setTaxonomyTree(data);
        
        let matchedCatNode = data.find((t: TaxonomyOption) => 
          (t.subcategories || []).includes(targetSubcategory)
        );

        if (!matchedCatNode) {
          matchedCatNode = data.find((t: TaxonomyOption) => t.category === 'Expense') || data[0];
        }

        setSelectedCategory(matchedCatNode.category);
        if (matchedCatNode.subcategories && matchedCatNode.subcategories.length > 0) {
          setSelectedSubcategory(
            matchedCatNode.subcategories.includes(targetSubcategory) 
              ? targetSubcategory 
              : matchedCatNode.subcategories[0]
          );
        }
      }
    } catch (err) {
      console.error('Failed to load dynamic taxonomy:', err);
    }
  };

  const availableSubcategories = useMemo(() => {
    if (!taxonomyTree || taxonomyTree.length === 0) return [];
    const found = taxonomyTree.find((item: TaxonomyOption) => item.category === selectedCategory) || taxonomyTree[0];
    return found ? found.subcategories || [] : [];
  }, [taxonomyTree, selectedCategory]);

  const filteredClusters = useMemo(() => filterClustersByQuery(clusters, searchQuery), [clusters, searchQuery]);
  const visibleTxnIds = useMemo(() => filteredClusters.flatMap((c) => c.transaction_ids || []), [filteredClusters]);
  const selectedSummary = useMemo(() => calculateSelectedMetrics(clusters, selectedTxnIds), [clusters, selectedTxnIds]);

  // 🟢 Vector Auto-Detection on Active Preview Selection
  const handleSelectCluster = (cluster: ExtendedCluster | Cluster) => {
    setActivePreviewCluster(cluster);
    const sampleItem = cluster.items?.[0];
    if (sampleItem) {
      setVectorType(sampleItem.direction === 'INFLOW' || (sampleItem.credit || 0) > 0 ? 'Credit' : 'Debit');
    }
  };

  const toggleIndividualTxn = (txnId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedTxnIds((prev) => 
      prev.includes(txnId) ? prev.filter((id) => id !== txnId) : [...prev, txnId]
    );
  };

  const toggleClusterTxns = (clusterTxnIds: string[], e: React.MouseEvent) => {
    e.stopPropagation();
    const allInClusterSelected = clusterTxnIds.length > 0 && clusterTxnIds.every((id) => selectedTxnIds.includes(id));
    
    if (allInClusterSelected) {
      setSelectedTxnIds((prev) => prev.filter((id) => !clusterTxnIds.includes(id)));
    } else {
      setSelectedTxnIds((prev) => Array.from(new Set([...prev, ...clusterTxnIds])));
    }
  };

  const toggleSelectAllVisible = () => {
    const allVisibleSelected = visibleTxnIds.length > 0 && visibleTxnIds.every((id) => selectedTxnIds.includes(id));
    if (allVisibleSelected) {
      setSelectedTxnIds((prev) => prev.filter((id) => !visibleTxnIds.includes(id)));
    } else {
      setSelectedTxnIds((prev) => Array.from(new Set([...prev, ...visibleTxnIds])));
    }
  };

  const clearAllSelections = () => setSelectedTxnIds([]);

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

  const handleApplyClassification = async () => {
    if (selectedSummary.allTxnIds.length === 0) return;
    setSubmitting(true);
    try {
      const selectedPatternsSet = new Set<string>();
      clusters.forEach((cluster) => {
        const clusterTxns = cluster.transaction_ids || [];
        const hasSelectedTxn = clusterTxns.some((id) => selectedTxnIds.includes(id));
        if (hasSelectedTxn && cluster.pattern && cluster.pattern !== 'UNCLASSIFIED_OTHER') {
          selectedPatternsSet.add(cluster.pattern);
        }
      });

      const patternsToSave = Array.from(selectedPatternsSet);
      const data = await applyReclassification({
        transaction_ids: selectedSummary.allTxnIds,
        target_category: selectedCategory,
        target_subcategory: selectedSubcategory,
        patterns: patternsToSave,
        save_rule: saveRule,
        entry_type: vectorType,
      });

      if (data?.status === 'success') {
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
            submitting={submitting}
            handleApplyClassification={handleApplyClassification}
            onClose={onClose}
            selectedTxnIds={selectedTxnIds}
            toggleClusterTxns={toggleClusterTxns}
            suggestedRule={suggestedRule}
          />
        </div>
      </div>
    </div>,
    document.body
  );
};



// import React, { useState, useEffect, useMemo } from 'react';
// import { createPortal } from 'react-dom';
// import { 
//   getSuspenseClusters, 
//   applyReclassification, 
//   getTaxonomyTree, 
//   addTaxonomyNode,
//   type TaxonomyOption, 
//   type ExtendedCluster,
//   type Cluster,
// } from '../api';

// import { calculateSelectedMetrics, filterClustersByQuery } from '../utils/classificationHelpers';
// import { ClusterListPanel } from '../components/classification/ClusterlistPanel.tsx';
// import { TaxonomyMapperPanel } from '../components/classification/TaxonomyMapperPanel.tsx';

// interface ModalProps {
//   isOpen: boolean;
//   onClose: () => void;
//   onSuccess: () => void;
//   targetSubcategory?: string;
//   accountId?: number;
// }

// export const ClassificationWorkbenchModal: React.FC<ModalProps> = ({
//   isOpen,
//   onClose,
//   onSuccess,
//   targetSubcategory = 'Suspense Account',
//   accountId,
// }) => {
//   const [clusters, setClusters] = useState<ExtendedCluster[]>([]);
//   const [loading, setLoading] = useState<boolean>(false);
//   const [submitting, setSubmitting] = useState<boolean>(false);
//   const [searchQuery, setSearchQuery] = useState<string>('');

//   const [selectedTxnIds, setSelectedTxnIds] = useState<string[]>([]);
//   const [activePreviewCluster, setActivePreviewCluster] = useState<ExtendedCluster | Cluster | null>(null);

//   // 🟢 Direction Vector & Batch Sweep State
//   const [vectorType, setVectorType] = useState<'Debit' | 'Credit'>('Debit');
  
//   const [selectedCategory, setSelectedCategory] = useState<string>('Expense');
//   const [selectedSubcategory, setSelectedSubcategory] = useState<string>('Housing & Rent');
//   const [saveRule, setSaveRule] = useState<boolean>(true);

//   const [taxonomyTree, setTaxonomyTree] = useState<TaxonomyOption[]>([]);

//   const [isCreatingNew, setIsCreatingNew] = useState<boolean>(false);
//   const [newCatInput, setNewCatInput] = useState<string>('');
//   const [newSubInput, setNewSubInput] = useState<string>('');
//   const [savingNewTaxonomy, setSavingNewTaxonomy] = useState<boolean>(false);

//   useEffect(() => {
//     if (isOpen) {
//       fetchClusters(targetSubcategory, accountId);
//       loadTaxonomy();
//     }
//   }, [isOpen, targetSubcategory, accountId]);

//   const fetchClusters = async (subcategoryName: string = targetSubcategory || 'Suspense Account', currentAccountId?: number) => {
//     setLoading(true);
//     setSelectedTxnIds([]);
//     setActivePreviewCluster(null);

//     try {
//       const data = await getSuspenseClusters(subcategoryName, currentAccountId);
//       if (data?.status === 'success') {
//         const list = data.clusters || [];
//         setClusters(list);
//         if (list.length > 0) {
//           setActivePreviewCluster(list[0]);
//           // Detect initial direction vector (Debit vs Credit)
//           const firstItem = list[0]?.items?.[0];
//           setVectorType(firstItem?.direction === 'INFLOW' || (firstItem?.credit || 0) > 0 ? 'Credit' : 'Debit');
//         }
//       }
//     } catch (err) {
//       console.error('Failed to load clusters:', err);
//     } finally {
//       setLoading(false);
//     }
//   };

//   const loadTaxonomy = async () => {
//     try {
//       const data = await getTaxonomyTree();
//       if (data && data.length > 0) {
//         setTaxonomyTree(data);
        
//         let matchedCatNode = data.find((t: TaxonomyOption) => 
//           (t.subcategories || []).includes(targetSubcategory)
//         );

//         if (!matchedCatNode) {
//           matchedCatNode = data.find((t: TaxonomyOption) => t.category === 'Expense') || data[0];
//         }

//         setSelectedCategory(matchedCatNode.category);
//         if (matchedCatNode.subcategories && matchedCatNode.subcategories.length > 0) {
//           setSelectedSubcategory(
//             matchedCatNode.subcategories.includes(targetSubcategory) 
//               ? targetSubcategory 
//               : matchedCatNode.subcategories[0]
//           );
//         }
//       }
//     } catch (err) {
//       console.error('Failed to load dynamic taxonomy:', err);
//     }
//   };

//   const availableSubcategories = useMemo(() => {
//     if (!taxonomyTree || taxonomyTree.length === 0) return [];
//     const found = taxonomyTree.find((item: TaxonomyOption) => item.category === selectedCategory) || taxonomyTree[0];
//     return found ? found.subcategories || [] : [];
//   }, [taxonomyTree, selectedCategory]);

//   const filteredClusters = useMemo(() => filterClustersByQuery(clusters, searchQuery), [clusters, searchQuery]);
//   const visibleTxnIds = useMemo(() => filteredClusters.flatMap((c) => c.transaction_ids || []), [filteredClusters]);
//   const selectedSummary = useMemo(() => calculateSelectedMetrics(clusters, selectedTxnIds), [clusters, selectedTxnIds]);

//   // 🟢 Vector Auto-Detection on Active Preview Selection
//   const handleSelectCluster = (cluster: ExtendedCluster | Cluster) => {
//     setActivePreviewCluster(cluster);
//     const sampleItem = cluster.items?.[0];
//     if (sampleItem) {
//       setVectorType(sampleItem.direction === 'INFLOW' || (sampleItem.credit || 0) > 0 ? 'Credit' : 'Debit');
//     }
//   };

//   const toggleIndividualTxn = (txnId: string, e: React.MouseEvent) => {
//     e.stopPropagation();
//     setSelectedTxnIds((prev) => (prev.includes(txnId) ? prev.filter((id) => id !== txnId) : [...prev, txnId]));
//   };

//   const toggleClusterTxns = (clusterTxnIds: string[], e: React.MouseEvent) => {
//     e.stopPropagation();
//     const allInClusterSelected = clusterTxnIds.every((id) => selectedTxnIds.includes(id));
//     if (allInClusterSelected) {
//       setSelectedTxnIds((prev) => prev.filter((id) => !clusterTxnIds.includes(id)));
//     } else {
//       setSelectedTxnIds((prev) => Array.from(new Set([...prev, ...clusterTxnIds])));
//     }
//   };

//   const toggleSelectAllVisible = () => {
//     const allVisibleSelected = visibleTxnIds.length > 0 && visibleTxnIds.every((id) => selectedTxnIds.includes(id));
//     if (allVisibleSelected) {
//       setSelectedTxnIds((prev) => prev.filter((id) => !visibleTxnIds.includes(id)));
//     } else {
//       setSelectedTxnIds((prev) => Array.from(new Set([...prev, ...visibleTxnIds])));
//     }
//   };

//   const clearAllSelections = () => setSelectedTxnIds([]);

//   const handleCreateTaxonomy = async () => {
//     if (!newCatInput.trim() || !newSubInput.trim()) return;
//     setSavingNewTaxonomy(true);
//     try {
//       const success = await addTaxonomyNode({
//         category: newCatInput.trim(),
//         subcategory: newSubInput.trim(),
//       });
//       if (success) {
//         await loadTaxonomy();
//         setSelectedCategory(newCatInput.trim());
//         setSelectedSubcategory(newSubInput.trim());
//         setNewCatInput('');
//         setNewSubInput('');
//         setIsCreatingNew(false);
//       }
//     } catch (err) {
//       console.error('Error creating new taxonomy node:', err);
//     } finally {
//       setSavingNewTaxonomy(false);
//     }
//   };

//   const handleApplyClassification = async () => {
//     if (selectedSummary.allTxnIds.length === 0) return;
//     setSubmitting(true);
//     try {
//       const selectedPatternsSet = new Set<string>();
//       clusters.forEach((cluster) => {
//         const clusterTxns = cluster.transaction_ids || [];
//         const hasSelectedTxn = clusterTxns.some((id) => selectedTxnIds.includes(id));
//         if (hasSelectedTxn && cluster.pattern && cluster.pattern !== 'UNCLASSIFIED_OTHER') {
//           selectedPatternsSet.add(cluster.pattern);
//         }
//       });

//       const patternsToSave = Array.from(selectedPatternsSet);
//       const data = await applyReclassification({
//         transaction_ids: selectedSummary.allTxnIds,
//         target_category: selectedCategory,
//         target_subcategory: selectedSubcategory,
//         patterns: patternsToSave,
//         save_rule: saveRule,
//         entry_type: vectorType, // 👈 PASS DR/CR DIRECTION VECTOR!
//       });

//       if (data?.status === 'success') {
//         await fetchClusters(targetSubcategory);
//         onSuccess();
//       }
//     } catch (err) {
//       console.error('Failed to apply reclassification:', err);
//     } finally {
//       setSubmitting(false);
//     }
//   };

//   if (!isOpen) return null;

//   return createPortal(
//     <div
//       style={{
//         position: 'fixed',
//         top: 0,
//         left: 0,
//         right: 0,
//         bottom: 0,
//         width: '100vw',
//         height: '100vh',
//         backgroundColor: 'rgba(0, 0, 0, 0.85)',
//         backdropFilter: 'blur(8px)',
//         zIndex: 999999,
//         display: 'flex',
//         alignItems: 'center',
//         justifyContent: 'center',
//         padding: '20px',
//         boxSizing: 'border-box',
//         fontFamily: 'monospace',
//       }}
//     >
//       <div
//         style={{
//           backgroundColor: '#09090b',
//           border: '1px solid #27272a',
//           borderRadius: '16px',
//           width: '100%',
//           maxWidth: '1100px',
//           height: '80vh',
//           display: 'flex',
//           flexDirection: 'column',
//           boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.75)',
//           overflow: 'hidden',
//           color: '#f4f4f5',
//         }}
//       >
//         {/* Header Bar with Vector Indicator */}
//         <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 24px', borderBottom: '1px solid #27272a', backgroundColor: '#18181b' }}>
//           <div>
//             <h2 style={{ margin: 0, fontSize: '14px', fontWeight: 'bold', textTransform: 'uppercase', color: '#f4f4f5', display: 'flex', alignItems: 'center', gap: '8px' }}>
//               <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: vectorType === 'Debit' ? '#ef4444' : '#10b981' }} />
//               Classification Workbench — {targetSubcategory || 'Suspense Account'}
//               <span style={{ fontSize: '10px', padding: '2px 6px', borderRadius: '4px', backgroundColor: '#27272a', color: vectorType === 'Debit' ? '#fca5a5' : '#6ee7b7' }}>
//                 {vectorType === 'Debit' ? 'OUTFLOW (DR)' : 'INFLOW (CR)'}
//               </span>
//             </h2>
//             <p style={{ margin: '4px 0 0 0', fontSize: '11px', color: '#71717a' }}>
//               Reviewing merchant clusters under <strong style={{ color: '#e4e4e7' }}>{targetSubcategory || 'Suspense Account'}</strong>.
//             </p>
//           </div>
//           <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#71717a', fontSize: '18px', cursor: 'pointer', padding: '4px 8px', borderRadius: '6px' }}>
//             ✕
//           </button>
//         </div>

//         {/* Workspace Body */}
//         <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
//           <ClusterListPanel
//             loading={loading}
//             filteredClusters={filteredClusters}
//             selectedTxnIds={selectedTxnIds}
//             visibleTxnIds={visibleTxnIds}
//             activePreviewCluster={activePreviewCluster}
//             searchQuery={searchQuery}
//             setSearchQuery={setSearchQuery}
//             setActivePreviewCluster={handleSelectCluster}
//             toggleIndividualTxn={toggleIndividualTxn}
//             toggleClusterTxns={toggleClusterTxns}
//             toggleSelectAllVisible={toggleSelectAllVisible}
//             clearAllSelections={clearAllSelections}
//           />

//           <TaxonomyMapperPanel
//             targetSubcategoryContext={targetSubcategory}
//             selectedSummary={selectedSummary}
//             activePreviewCluster={activePreviewCluster}
//             taxonomyTree={taxonomyTree}
//             availableSubcategories={availableSubcategories}
//             selectedCategory={selectedCategory}
//             setSelectedCategory={setSelectedCategory}
//             selectedSubcategory={selectedSubcategory}
//             setSelectedSubcategory={setSelectedSubcategory}
//             isCreatingNew={isCreatingNew}
//             setIsCreatingNew={setIsCreatingNew}
//             newCatInput={newCatInput}
//             setNewCatInput={setNewCatInput}
//             newSubInput={newSubInput}
//             setNewSubInput={setNewSubInput}
//             savingNewTaxonomy={savingNewTaxonomy}
//             handleCreateTaxonomy={handleCreateTaxonomy}
//             saveRule={saveRule}
//             setSaveRule={setSaveRule}
//             submitting={submitting}
//             handleApplyClassification={handleApplyClassification}
//             onClose={onClose}
//             selectedTxnIds={selectedTxnIds}
//             toggleClusterTxns={toggleClusterTxns}
//             suggestedRule={suggestedRule}
//           />
//         </div>
//       </div>
//     </div>,
//     document.body
//   );
// };





// // import React, { useState, useEffect, useMemo } from 'react';
// // import { createPortal } from 'react-dom';
// // import { 
// //   getSuspenseClusters, 
// //   applyReclassification, 
// //   getTaxonomyTree, 
// //   addTaxonomyNode,
// //   type TaxonomyOption, 
// //   type ExtendedCluster,
// //   type Cluster,
// // } from '../api';

// // import { calculateSelectedMetrics, filterClustersByQuery } from '../utils/classificationHelpers';
// // import { ClusterListPanel } from '../components/classification/ClusterlistPanel.tsx';
// // import { TaxonomyMapperPanel } from '../components/classification/TaxonomyMapperPanel.tsx';

// // interface ModalProps {
// //   isOpen: boolean;
// //   onClose: () => void;
// //   onSuccess: () => void;
// //   targetSubcategory?: string;
// //   accountId?: number;
// // }

// // export const ClassificationWorkbenchModal: React.FC<ModalProps> = ({
// //   isOpen,
// //   onClose,
// //   onSuccess,
// //   targetSubcategory = 'Suspense Account',
// //   accountId,
// // }) => {
// //   const [clusters, setClusters] = useState<ExtendedCluster[]>([]);
// //   const [loading, setLoading] = useState<boolean>(false);
// //   const [submitting, setSubmitting] = useState<boolean>(false);
// //   const [searchQuery, setSearchQuery] = useState<string>('');

// //   const [selectedTxnIds, setSelectedTxnIds] = useState<string[]>([]);
// //   const [activePreviewCluster, setActivePreviewCluster] = useState<ExtendedCluster | Cluster | null>(null);
  
// //   const [selectedCategory, setSelectedCategory] = useState<string>('Expense');
// //   const [selectedSubcategory, setSelectedSubcategory] = useState<string>('Housing & Rent');
// //   const [saveRule, setSaveRule] = useState<boolean>(true);

// //   const [taxonomyTree, setTaxonomyTree] = useState<TaxonomyOption[]>([]);

// //   const [isCreatingNew, setIsCreatingNew] = useState<boolean>(false);
// //   const [newCatInput, setNewCatInput] = useState<string>('');
// //   const [newSubInput, setNewSubInput] = useState<string>('');
// //   const [savingNewTaxonomy, setSavingNewTaxonomy] = useState<boolean>(false);

// //   useEffect(() => {
// //     if (isOpen) {
// //       fetchClusters(targetSubcategory, accountId);
// //       loadTaxonomy();
// //     }
// //   }, [isOpen, targetSubcategory, accountId]);

// //   const fetchClusters = async (subcategoryName: string = targetSubcategory || 'Suspense Account', currentAccountId?: number) => {
// //     setLoading(true);
// //     setSelectedTxnIds([]);
// //     setActivePreviewCluster(null);

// //     try {
// //       const data = await getSuspenseClusters(subcategoryName, currentAccountId);
// //       if (data?.status === 'success') {
// //         const list = data.clusters || [];
// //         setClusters(list);
// //         if (list.length > 0) setActivePreviewCluster(list[0]);
// //       }
// //     } catch (err) {
// //       console.error('Failed to load clusters:', err);
// //     } finally {
// //       setLoading(false);
// //     }
// //   };

// //   const loadTaxonomy = async () => {
// //     try {
// //       const data = await getTaxonomyTree();
// //       if (data && data.length > 0) {
// //         setTaxonomyTree(data);
        
// //         // 🟢 AUTO-DETECT: Find which primary category targetSubcategory belongs to!
// //         let matchedCatNode = data.find((t: TaxonomyOption) => 
// //           (t.subcategories || []).includes(targetSubcategory)
// //         );

// //         // Fallback to default if inspecting unclassified suspense
// //         if (!matchedCatNode) {
// //           matchedCatNode = data.find((t: TaxonomyOption) => t.category === 'Expense') || data[0];
// //         }

// //         setSelectedCategory(matchedCatNode.category);
// //         if (matchedCatNode.subcategories && matchedCatNode.subcategories.length > 0) {
// //           setSelectedSubcategory(
// //             matchedCatNode.subcategories.includes(targetSubcategory) 
// //               ? targetSubcategory 
// //               : matchedCatNode.subcategories[0]
// //           );
// //         }
// //       }
// //     } catch (err) {
// //       console.error('Failed to load dynamic taxonomy:', err);
// //     }
// //   };

// //   const availableSubcategories = useMemo(() => {
// //     if (!taxonomyTree || taxonomyTree.length === 0) return [];
// //     const found = taxonomyTree.find((item: TaxonomyOption) => item.category === selectedCategory) || taxonomyTree[0];
// //     return found ? found.subcategories || [] : [];
// //   }, [taxonomyTree, selectedCategory]);

// //   const filteredClusters = useMemo(() => filterClustersByQuery(clusters, searchQuery), [clusters, searchQuery]);
// //   const visibleTxnIds = useMemo(() => filteredClusters.flatMap((c) => c.transaction_ids || []), [filteredClusters]);
// //   const selectedSummary = useMemo(() => calculateSelectedMetrics(clusters, selectedTxnIds), [clusters, selectedTxnIds]);

// //   const toggleIndividualTxn = (txnId: string, e: React.MouseEvent) => {
// //     e.stopPropagation();
// //     setSelectedTxnIds((prev) => (prev.includes(txnId) ? prev.filter((id) => id !== txnId) : [...prev, txnId]));
// //   };

// //   const toggleClusterTxns = (clusterTxnIds: string[], e: React.MouseEvent) => {
// //     e.stopPropagation();
// //     const allInClusterSelected = clusterTxnIds.every((id) => selectedTxnIds.includes(id));
// //     if (allInClusterSelected) {
// //       setSelectedTxnIds((prev) => prev.filter((id) => !clusterTxnIds.includes(id)));
// //     } else {
// //       setSelectedTxnIds((prev) => Array.from(new Set([...prev, ...clusterTxnIds])));
// //     }
// //   };

// //   const toggleSelectAllVisible = () => {
// //     const allVisibleSelected = visibleTxnIds.length > 0 && visibleTxnIds.every((id) => selectedTxnIds.includes(id));
// //     if (allVisibleSelected) {
// //       setSelectedTxnIds((prev) => prev.filter((id) => !visibleTxnIds.includes(id)));
// //     } else {
// //       setSelectedTxnIds((prev) => Array.from(new Set([...prev, ...visibleTxnIds])));
// //     }
// //   };

// //   const clearAllSelections = () => setSelectedTxnIds([]);

// //   const handleCreateTaxonomy = async () => {
// //     if (!newCatInput.trim() || !newSubInput.trim()) return;
// //     setSavingNewTaxonomy(true);
// //     try {
// //       const success = await addTaxonomyNode({
// //         category: newCatInput.trim(),
// //         subcategory: newSubInput.trim(),
// //       });
// //       if (success) {
// //         await loadTaxonomy();
// //         setSelectedCategory(newCatInput.trim());
// //         setSelectedSubcategory(newSubInput.trim());
// //         setNewCatInput('');
// //         setNewSubInput('');
// //         setIsCreatingNew(false);
// //       }
// //     } catch (err) {
// //       console.error('Error creating new taxonomy node:', err);
// //     } finally {
// //       setSavingNewTaxonomy(false);
// //     }
// //   };

// //   const handleApplyClassification = async () => {
// //     if (selectedSummary.allTxnIds.length === 0) return;
// //     setSubmitting(true);
// //     try {
// //       const selectedPatternsSet = new Set<string>();
// //       clusters.forEach((cluster) => {
// //         const clusterTxns = cluster.transaction_ids || [];
// //         const hasSelectedTxn = clusterTxns.some((id) => selectedTxnIds.includes(id));
// //         if (hasSelectedTxn && cluster.pattern && cluster.pattern !== 'UNCLASSIFIED_OTHER') {
// //           selectedPatternsSet.add(cluster.pattern);
// //         }
// //       });

// //       const patternsToSave = Array.from(selectedPatternsSet);
// //       const data = await applyReclassification({
// //         transaction_ids: selectedSummary.allTxnIds,
// //         target_category: selectedCategory,
// //         target_subcategory: selectedSubcategory,
// //         patterns: patternsToSave,
// //         save_rule: saveRule,
// //       });

// //       if (data?.status === 'success') {
// //         await fetchClusters(targetSubcategory);
// //         onSuccess();
// //       }
// //     } catch (err) {
// //       console.error('Failed to apply reclassification:', err);
// //     } finally {
// //       setSubmitting(false);
// //     }
// //   };

// //   if (!isOpen) return null;

// //   return createPortal(
// //     <div
// //       style={{
// //         position: 'fixed',
// //         top: 0,
// //         left: 0,
// //         right: 0,
// //         bottom: 0,
// //         width: '100vw',
// //         height: '100vh',
// //         backgroundColor: 'rgba(0, 0, 0, 0.85)',
// //         backdropFilter: 'blur(8px)',
// //         zIndex: 999999,
// //         display: 'flex',
// //         alignItems: 'center',
// //         justifyContent: 'center',
// //         padding: '20px',
// //         boxSizing: 'border-box',
// //         fontFamily: 'monospace',
// //       }}
// //     >
// //       <div
// //         style={{
// //           backgroundColor: '#09090b',
// //           border: '1px solid #27272a',
// //           borderRadius: '16px',
// //           width: '100%',
// //           maxWidth: '1100px',
// //           height: '80vh',
// //           display: 'flex',
// //           flexDirection: 'column',
// //           boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.75)',
// //           overflow: 'hidden',
// //           color: '#f4f4f5',
// //         }}
// //       >
// //         {/* Header Bar */}
// //         <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 24px', borderBottom: '1px solid #27272a', backgroundColor: '#18181b' }}>
// //           <div>
// //             <h2 style={{ margin: 0, fontSize: '14px', fontWeight: 'bold', textTransform: 'uppercase', color: '#f4f4f5', display: 'flex', alignItems: 'center', gap: '8px' }}>
// //               <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#f59e0b' }} />
// //               Classification Workbench — {targetSubcategory || 'Suspense Account'}
// //             </h2>
// //             <p style={{ margin: '4px 0 0 0', fontSize: '11px', color: '#71717a' }}>
// //               Reviewing merchant clusters under <strong style={{ color: '#e4e4e7' }}>{targetSubcategory || 'Suspense Account'}</strong>.
// //             </p>
// //           </div>
// //           <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#71717a', fontSize: '18px', cursor: 'pointer', padding: '4px 8px', borderRadius: '6px' }}>
// //             ✕
// //           </button>
// //         </div>

// //         {/* Workspace Body */}
// //         <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
// //           <ClusterListPanel
// //             loading={loading}
// //             filteredClusters={filteredClusters}
// //             selectedTxnIds={selectedTxnIds}
// //             visibleTxnIds={visibleTxnIds}
// //             activePreviewCluster={activePreviewCluster}
// //             searchQuery={searchQuery}
// //             setSearchQuery={setSearchQuery}
// //             setActivePreviewCluster={setActivePreviewCluster}
// //             toggleIndividualTxn={toggleIndividualTxn}
// //             toggleClusterTxns={toggleClusterTxns}
// //             toggleSelectAllVisible={toggleSelectAllVisible}
// //             clearAllSelections={clearAllSelections}
// //           />

// //           <TaxonomyMapperPanel
// //             targetSubcategoryContext={targetSubcategory}
// //             selectedSummary={selectedSummary}
// //             activePreviewCluster={activePreviewCluster}
// //             taxonomyTree={taxonomyTree}
// //             availableSubcategories={availableSubcategories}
// //             selectedCategory={selectedCategory}
// //             setSelectedCategory={setSelectedCategory}
// //             selectedSubcategory={selectedSubcategory}
// //             setSelectedSubcategory={setSelectedSubcategory}
// //             isCreatingNew={isCreatingNew}
// //             setIsCreatingNew={setIsCreatingNew}
// //             newCatInput={newCatInput}
// //             setNewCatInput={setNewCatInput}
// //             newSubInput={newSubInput}
// //             setNewSubInput={setNewSubInput}
// //             savingNewTaxonomy={savingNewTaxonomy}
// //             handleCreateTaxonomy={handleCreateTaxonomy}
// //             saveRule={saveRule}
// //             setSaveRule={setSaveRule}
// //             submitting={submitting}
// //             handleApplyClassification={handleApplyClassification}
// //             onClose={onClose}
// //           />
// //         </div>
// //       </div>
// //     </div>,
// //     document.body
// //   );
// // };




// // // import React, { useState, useEffect, useMemo } from 'react';
// // // import { createPortal } from 'react-dom';
// // // import { 
// // //   getSuspenseClusters, 
// // //   applyReclassification, 
// // //   getTaxonomyTree, 
// // //   addTaxonomyNode,
// // //   type TaxonomyOption, 
// // //   type ExtendedCluster,
// // //   type Cluster,
// // // } from '../api';

// // // import { calculateSelectedMetrics, filterClustersByQuery } from '../utils/classificationHelpers';
// // // import { ClusterListPanel } from '../components/classification/ClusterlistPanel.tsx';
// // // import { TaxonomyMapperPanel } from '../components/classification/TaxonomyMapperPanel.tsx';

// // // interface ModalProps {
// // //   isOpen: boolean;
// // //   onClose: () => void;
// // //   onSuccess: () => void;
// // //   targetSubcategory?: string;
// // //   accountId?: number;
// // // }

// // // export const ClassificationWorkbenchModal: React.FC<ModalProps> = ({
// // //   isOpen,
// // //   onClose,
// // //   onSuccess,
// // //   targetSubcategory = 'Suspense Account',
// // //   accountId,
// // // }) => {
// // //   const [clusters, setClusters] = useState<ExtendedCluster[]>([]);
// // //   const [loading, setLoading] = useState<boolean>(false);
// // //   const [submitting, setSubmitting] = useState<boolean>(false);
// // //   const [searchQuery, setSearchQuery] = useState<string>('');

// // //   const [selectedTxnIds, setSelectedTxnIds] = useState<string[]>([]);
// // //   const [activePreviewCluster, setActivePreviewCluster] = useState<ExtendedCluster | Cluster | null>(null);
  
// // //   const [selectedCategory, setSelectedCategory] = useState<string>('Expense');
// // //   const [selectedSubcategory, setSelectedSubcategory] = useState<string>('Housing & Rent');
// // //   const [saveRule, setSaveRule] = useState<boolean>(true);

// // //   const [taxonomyTree, setTaxonomyTree] = useState<TaxonomyOption[]>([]);

// // //   const [isCreatingNew, setIsCreatingNew] = useState<boolean>(false);
// // //   const [newCatInput, setNewCatInput] = useState<string>('');
// // //   const [newSubInput, setNewSubInput] = useState<string>('');
// // //   const [savingNewTaxonomy, setSavingNewTaxonomy] = useState<boolean>(false);

// // //   useEffect(() => {
// // //     if (isOpen) {
// // //       fetchClusters(targetSubcategory, accountId);
// // //       loadTaxonomy();
// // //     }
// // //   }, [isOpen, targetSubcategory, accountId]);

// // //   const fetchClusters = async (subcategoryName: string = targetSubcategory || 'Suspense Account', currentAccountId?: number) => {
// // //     setLoading(true);
// // //     setSelectedTxnIds([]);
// // //     setActivePreviewCluster(null);

// // //     try {
// // //       const data = await getSuspenseClusters(subcategoryName, currentAccountId);
// // //       if (data?.status === 'success') {
// // //         const list = data.clusters || [];
// // //         setClusters(list);
// // //         if (list.length > 0) setActivePreviewCluster(list[0]);
// // //       }
// // //     } catch (err) {
// // //       console.error('Failed to load clusters:', err);
// // //     } finally {
// // //       setLoading(false);
// // //     }
// // //   };

// // //   const loadTaxonomy = async () => {
// // //     try {
// // //       const data = await getTaxonomyTree();
// // //       if (data && data.length > 0) {
// // //         setTaxonomyTree(data);
// // //         const defaultCatNode = data.find((t: TaxonomyOption) => t.category === 'Expense') || data[0];
// // //         setSelectedCategory(defaultCatNode.category);
// // //         if (defaultCatNode.subcategories && defaultCatNode.subcategories.length > 0) {
// // //           setSelectedSubcategory(defaultCatNode.subcategories[0]);
// // //         }
// // //       }
// // //     } catch (err) {
// // //       console.error('Failed to load dynamic taxonomy:', err);
// // //     }
// // //   };

// // //   const availableSubcategories = useMemo(() => {
// // //     if (!taxonomyTree || taxonomyTree.length === 0) return [];
// // //     const found = taxonomyTree.find((item: TaxonomyOption) => item.category === selectedCategory) || taxonomyTree[0];
// // //     return found ? found.subcategories || [] : [];
// // //   }, [taxonomyTree, selectedCategory]);

// // //   const filteredClusters = useMemo(() => filterClustersByQuery(clusters, searchQuery), [clusters, searchQuery]);
// // //   const visibleTxnIds = useMemo(() => filteredClusters.flatMap((c) => c.transaction_ids || []), [filteredClusters]);
// // //   const selectedSummary = useMemo(() => calculateSelectedMetrics(clusters, selectedTxnIds), [clusters, selectedTxnIds]);

// // //   const toggleIndividualTxn = (txnId: string, e: React.MouseEvent) => {
// // //     e.stopPropagation();
// // //     setSelectedTxnIds((prev) => (prev.includes(txnId) ? prev.filter((id) => id !== txnId) : [...prev, txnId]));
// // //   };

// // //   const toggleClusterTxns = (clusterTxnIds: string[], e: React.MouseEvent) => {
// // //     e.stopPropagation();
// // //     const allInClusterSelected = clusterTxnIds.every((id) => selectedTxnIds.includes(id));
// // //     if (allInClusterSelected) {
// // //       setSelectedTxnIds((prev) => prev.filter((id) => !clusterTxnIds.includes(id)));
// // //     } else {
// // //       setSelectedTxnIds((prev) => Array.from(new Set([...prev, ...clusterTxnIds])));
// // //     }
// // //   };

// // //   const toggleSelectAllVisible = () => {
// // //     const allVisibleSelected = visibleTxnIds.length > 0 && visibleTxnIds.every((id) => selectedTxnIds.includes(id));
// // //     if (allVisibleSelected) {
// // //       setSelectedTxnIds((prev) => prev.filter((id) => !visibleTxnIds.includes(id)));
// // //     } else {
// // //       setSelectedTxnIds((prev) => Array.from(new Set([...prev, ...visibleTxnIds])));
// // //     }
// // //   };

// // //   const clearAllSelections = () => setSelectedTxnIds([]);

// // //   const handleCreateTaxonomy = async () => {
// // //     if (!newCatInput.trim() || !newSubInput.trim()) return;
// // //     setSavingNewTaxonomy(true);
// // //     try {
// // //       const success = await addTaxonomyNode({
// // //         category: newCatInput.trim(),
// // //         subcategory: newSubInput.trim(),
// // //       });
// // //       if (success) {
// // //         await loadTaxonomy();
// // //         setSelectedCategory(newCatInput.trim());
// // //         setSelectedSubcategory(newSubInput.trim());
// // //         setNewCatInput('');
// // //         setNewSubInput('');
// // //         setIsCreatingNew(false);
// // //       }
// // //     } catch (err) {
// // //       console.error('Error creating new taxonomy node:', err);
// // //     } finally {
// // //       setSavingNewTaxonomy(false);
// // //     }
// // //   };

// // //   const handleApplyClassification = async () => {
// // //     if (selectedSummary.allTxnIds.length === 0) return;
// // //     setSubmitting(true);
// // //     try {
// // //       const selectedPatternsSet = new Set<string>();
// // //       clusters.forEach((cluster) => {
// // //         const clusterTxns = cluster.transaction_ids || [];
// // //         const hasSelectedTxn = clusterTxns.some((id) => selectedTxnIds.includes(id));
// // //         if (hasSelectedTxn && cluster.pattern && cluster.pattern !== 'UNCLASSIFIED_OTHER') {
// // //           selectedPatternsSet.add(cluster.pattern);
// // //         }
// // //       });

// // //       const patternsToSave = Array.from(selectedPatternsSet);
// // //       const data = await applyReclassification({
// // //         transaction_ids: selectedSummary.allTxnIds,
// // //         target_category: selectedCategory,
// // //         target_subcategory: selectedSubcategory,
// // //         patterns: patternsToSave,
// // //         save_rule: saveRule,
// // //       });

// // //       if (data?.status === 'success') {
// // //         await fetchClusters(targetSubcategory);
// // //         onSuccess();
// // //       }
// // //     } catch (err) {
// // //       console.error('Failed to apply reclassification:', err);
// // //     } finally {
// // //       setSubmitting(false);
// // //     }
// // //   };

// // //   if (!isOpen) return null;

// // //   return createPortal(
// // //     <div
// // //       style={{
// // //         position: 'fixed',
// // //         top: 0,
// // //         left: 0,
// // //         right: 0,
// // //         bottom: 0,
// // //         width: '100vw',
// // //         height: '100vh',
// // //         backgroundColor: 'rgba(0, 0, 0, 0.85)',
// // //         backdropFilter: 'blur(8px)',
// // //         zIndex: 999999,
// // //         display: 'flex',
// // //         alignItems: 'center',
// // //         justifyContent: 'center',
// // //         padding: '20px',
// // //         boxSizing: 'border-box',
// // //         fontFamily: 'monospace',
// // //       }}
// // //     >
// // //       <div
// // //         style={{
// // //           backgroundColor: '#09090b',
// // //           border: '1px solid #27272a',
// // //           borderRadius: '16px',
// // //           width: '100%',
// // //           maxWidth: '1100px',
// // //           height: '80vh',
// // //           display: 'flex',
// // //           flexDirection: 'column',
// // //           boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.75)',
// // //           overflow: 'hidden',
// // //           color: '#f4f4f5',
// // //         }}
// // //       >
// // //         {/* Header Bar */}
// // //         <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 24px', borderBottom: '1px solid #27272a', backgroundColor: '#18181b' }}>
// // //           <div>
// // //             <h2 style={{ margin: 0, fontSize: '14px', fontWeight: 'bold', textTransform: 'uppercase', color: '#f4f4f5', display: 'flex', alignItems: 'center', gap: '8px' }}>
// // //               <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#f59e0b' }} />
// // //               Classification Workbench — {targetSubcategory || 'Suspense Account'}
// // //             </h2>
// // //             <p style={{ margin: '4px 0 0 0', fontSize: '11px', color: '#71717a' }}>
// // //               Reviewing merchant clusters under <strong style={{ color: '#e4e4e7' }}>{targetSubcategory || 'Suspense Account'}</strong>.
// // //             </p>
// // //           </div>
// // //           <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#71717a', fontSize: '18px', cursor: 'pointer', padding: '4px 8px', borderRadius: '6px' }}>
// // //             ✕
// // //           </button>
// // //         </div>

// // //         {/* Workspace Body */}
// // //         <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
// // //           <ClusterListPanel
// // //             loading={loading}
// // //             filteredClusters={filteredClusters}
// // //             selectedTxnIds={selectedTxnIds}
// // //             visibleTxnIds={visibleTxnIds}
// // //             activePreviewCluster={activePreviewCluster}
// // //             searchQuery={searchQuery}
// // //             setSearchQuery={setSearchQuery}
// // //             setActivePreviewCluster={setActivePreviewCluster}
// // //             toggleIndividualTxn={toggleIndividualTxn}
// // //             toggleClusterTxns={toggleClusterTxns}
// // //             toggleSelectAllVisible={toggleSelectAllVisible}
// // //             clearAllSelections={clearAllSelections}
// // //           />

// // //           <TaxonomyMapperPanel
// // //                 selectedSummary={selectedSummary}
// // //                 activePreviewCluster={activePreviewCluster}
// // //                 taxonomyTree={taxonomyTree}
// // //                 availableSubcategories={availableSubcategories}
// // //                 selectedCategory={selectedCategory}
// // //                 setSelectedCategory={setSelectedCategory}
// // //                 selectedSubcategory={selectedSubcategory}
// // //                 setSelectedSubcategory={setSelectedSubcategory}
// // //                 isCreatingNew={isCreatingNew}
// // //                 setIsCreatingNew={setIsCreatingNew}
// // //                 newCatInput={newCatInput}
// // //                 setNewCatInput={setNewCatInput}
// // //                 newSubInput={newSubInput}
// // //                 setNewSubInput={setNewSubInput}
// // //                 savingNewTaxonomy={savingNewTaxonomy}
// // //                 handleCreateTaxonomy={handleCreateTaxonomy}
// // //                 saveRule={saveRule}
// // //                 setSaveRule={setSaveRule}
// // //                 submitting={submitting}
// // //                 handleApplyClassification={handleApplyClassification}
// // //                 onClose={onClose}
// // //               />
// // //         </div>
// // //       </div>
// // //     </div>,
// // //     document.body
// // //   );
// // // };






// // // // import React, { useState, useEffect, useMemo } from 'react';
// // // // import { createPortal } from 'react-dom';
// // // // import { 
// // // //   getSuspenseClusters, 
// // // //   applyReclassification, 
// // // //   getTaxonomyTree, 
// // // //   addTaxonomyNode,
// // // //   type TaxonomyOption, 
// // // //   type ExtendedCluster,
// // // //   type Cluster 
// // // // } from '../api';

// // // // interface ModalProps {
// // // //   isOpen: boolean;
// // // //   onClose: () => void;
// // // //   onSuccess: () => void;
// // // //   targetSubcategory?: string;
// // // //   accountId?: number;
// // // // }

// // // // export const ClassificationWorkbenchModal: React.FC<ModalProps> = ({
// // // //   isOpen,
// // // //   onClose,
// // // //   onSuccess,
// // // //   targetSubcategory = 'Suspense Account',
// // // //   accountId,
// // // // }) => {
// // // //   const [clusters, setClusters] = useState<ExtendedCluster[]>([]);
// // // //   const [loading, setLoading] = useState<boolean>(false);
// // // //   const [submitting, setSubmitting] = useState<boolean>(false);
// // // //   const [searchQuery, setSearchQuery] = useState<string>('');

// // // //   // Selected transaction IDs
// // // //   const [selectedTxnIds, setSelectedTxnIds] = useState<string[]>([]);
// // // //   const [activePreviewCluster, setActivePreviewCluster] = useState<ExtendedCluster | Cluster | null>(null);
  
// // // //   const [selectedCategory, setSelectedCategory] = useState<string>('Expense');
// // // //   const [selectedSubcategory, setSelectedSubcategory] = useState<string>('Housing & Rent');
// // // //   const [saveRule, setSaveRule] = useState<boolean>(true);

// // // //   const [taxonomyTree, setTaxonomyTree] = useState<TaxonomyOption[]>([]);

// // // //   // Adding Cat and Sub cat on the Go
// // // //   const [isCreatingNew, setIsCreatingNew] = useState<boolean>(false);
// // // //   const [newCatInput, setNewCatInput] = useState<string>('');
// // // //   const [newSubInput, setNewSubInput] = useState<string>('');
// // // //   const [savingNewTaxonomy, setSavingNewTaxonomy] = useState<boolean>(false);

// // // //   const inrFormatter = useMemo(
// // // //     () =>
// // // //       new Intl.NumberFormat('en-IN', {
// // // //         style: 'currency',
// // // //         currency: 'INR',
// // // //         maximumFractionDigits: 0,
// // // //       }),
// // // //     []
// // // //   );

// // // //   useEffect(() => {
// // // //     if (isOpen) {
// // // //       fetchClusters(targetSubcategory,accountId);
// // // //       loadTaxonomy();
// // // //     }
// // // //   }, [isOpen, targetSubcategory]);

// // // //   const fetchClusters = async (subcategoryName: string = targetSubcategory || 'Suspense Account',currentAccountId?: number) => {
// // // //     setLoading(true);
// // // //     setSelectedTxnIds([]);
// // // //     setActivePreviewCluster(null);

// // // //     try {
// // // //       const data = await getSuspenseClusters(subcategoryName,currentAccountId);
// // // //       if (data?.status === 'success') {
// // // //         const list = data.clusters || [];
// // // //         setClusters(list);
// // // //         if (list.length > 0) {
// // // //           setActivePreviewCluster(list[0]);
// // // //         }
// // // //       }
// // // //     } catch (err) {
// // // //       console.error('Failed to load clusters:', err);
// // // //     } finally {
// // // //       setLoading(false);
// // // //     }
// // // //   };

// // // //   const loadTaxonomy = async () => {
// // // //     try {
// // // //       const data = await getTaxonomyTree();
// // // //       if (data && data.length > 0) {
// // // //         setTaxonomyTree(data);

// // // //         // Default to "Expense" if present, otherwise pick the first category from DB
// // // //         const defaultCatNode = data.find((t: TaxonomyOption) => t.category === 'Expense') || data[0];

// // // //         setSelectedCategory(defaultCatNode.category);
// // // //         if (defaultCatNode.subcategories && defaultCatNode.subcategories.length > 0) {
// // // //           setSelectedSubcategory(defaultCatNode.subcategories[0]);
// // // //         }
// // // //       } else {
// // // //         console.warn('⚠️ Taxonomy API returned empty data array.');
// // // //       }
// // // //     } catch (err) {
// // // //       console.error('❌ Failed to load dynamic taxonomy:', err);
// // // //     }
// // // //   };

// // // //   // Dynamically derive available subcategories from the loaded DB taxonomy
// // // //   const availableSubcategories = useMemo(() => {
// // // //     if (!taxonomyTree || taxonomyTree.length === 0) return [];

// // // //     const found = taxonomyTree.find((item: TaxonomyOption) => item.category === selectedCategory) 
// // // //                || taxonomyTree[0];

// // // //     return found ? found.subcategories || [] : [];
// // // //   }, [taxonomyTree, selectedCategory]);

// // // //   const filteredClusters = useMemo(() => {
// // // //     if (!searchQuery.trim()) return clusters;
// // // //     const query = searchQuery.toLowerCase();
// // // //     return clusters.filter(
// // // //       (c) =>
// // // //         (c.pattern && c.pattern.toLowerCase().includes(query)) ||
// // // //         (c.sample_descriptions && c.sample_descriptions.some((d) => d.toLowerCase().includes(query)))
// // // //     );
// // // //   }, [clusters, searchQuery]);

// // // //   // Extract transaction IDs present in the current search view
// // // //   const visibleTxnIds = useMemo(() => {
// // // //     return filteredClusters.flatMap((c) => c.transaction_ids || []);
// // // //   }, [filteredClusters]);

// // // //   // Calculate selected metrics safely
// // // //   const selectedSummary = useMemo(() => {
// // // //     let totalTxns = 0;
// // // //     let totalAmount = 0;

// // // //     clusters.forEach((cluster) => {
// // // //       if (cluster.items && cluster.items.length > 0) {
// // // //         cluster.items.forEach((item) => {
// // // //           if (selectedTxnIds.includes(item.id)) {
// // // //             totalTxns += 1;
// // // //             totalAmount += item.amount || 0;
// // // //           }
// // // //         });
// // // //       } else {
// // // //         const selectedInCluster = (cluster.transaction_ids || []).filter((id) =>
// // // //           selectedTxnIds.includes(id)
// // // //         );
// // // //         if (selectedInCluster.length > 0) {
// // // //           totalTxns += selectedInCluster.length;
// // // //           const ratio = selectedInCluster.length / (cluster.count || 1);
// // // //           totalAmount += (cluster.total_amount || 0) * ratio;
// // // //         }
// // // //       }
// // // //     });

// // // //     return { totalTxns, totalAmount, allTxnIds: selectedTxnIds };
// // // //   }, [clusters, selectedTxnIds]);

// // // //   const toggleIndividualTxn = (txnId: string, e: React.MouseEvent) => {
// // // //     e.stopPropagation();
// // // //     setSelectedTxnIds((prev) =>
// // // //       prev.includes(txnId) ? prev.filter((id) => id !== txnId) : [...prev, txnId]
// // // //     );
// // // //   };

// // // //   const toggleClusterTxns = (clusterTxnIds: string[], e: React.MouseEvent) => {
// // // //     e.stopPropagation();
// // // //     const allInClusterSelected = clusterTxnIds.every((id) => selectedTxnIds.includes(id));

// // // //     if (allInClusterSelected) {
// // // //       setSelectedTxnIds((prev) => prev.filter((id) => !clusterTxnIds.includes(id)));
// // // //     } else {
// // // //       setSelectedTxnIds((prev) => Array.from(new Set([...prev, ...clusterTxnIds])));
// // // //     }
// // // //   };

// // // //   const toggleSelectAllVisible = () => {
// // // //     const allVisibleSelected = visibleTxnIds.length > 0 && visibleTxnIds.every((id) => selectedTxnIds.includes(id));

// // // //     if (allVisibleSelected) {
// // // //       setSelectedTxnIds((prev) => prev.filter((id) => !visibleTxnIds.includes(id)));
// // // //     } else {
// // // //       setSelectedTxnIds((prev) => Array.from(new Set([...prev, ...visibleTxnIds])));
// // // //     }
// // // //   };

// // // //   const clearAllSelections = () => {
// // // //     setSelectedTxnIds([]);
// // // //   };

// // // //   const handleCreateTaxonomy = async () => {
// // // //     if (!newCatInput.trim() || !newSubInput.trim()) return;

// // // //     setSavingNewTaxonomy(true);
// // // //     try {
// // // //       const success = await addTaxonomyNode({
// // // //         category: newCatInput.trim(),
// // // //         subcategory: newSubInput.trim(),
// // // //       });

// // // //       if (success) {
// // // //         await loadTaxonomy();
// // // //         setSelectedCategory(newCatInput.trim());
// // // //         setSelectedSubcategory(newSubInput.trim());
// // // //         setNewCatInput('');
// // // //         setNewSubInput('');
// // // //         setIsCreatingNew(false);
// // // //       }
// // // //     } catch (err) {
// // // //       console.error('Error creating new taxonomy node:', err);
// // // //     } finally {
// // // //       setSavingNewTaxonomy(false);
// // // //     }
// // // //   };

// // // //   const handleApplyClassification = async () => {
// // // //     if (selectedSummary.allTxnIds.length === 0) return;

// // // //     setSubmitting(true);
// // // //     try {
// // // //       const selectedPatternsSet = new Set<string>();

// // // //       clusters.forEach((cluster) => {
// // // //         const clusterTxns = cluster.transaction_ids || [];
// // // //         const hasSelectedTxn = clusterTxns.some((id) => selectedTxnIds.includes(id));

// // // //         if (hasSelectedTxn && cluster.pattern && cluster.pattern !== 'UNCLASSIFIED_OTHER') {
// // // //           selectedPatternsSet.add(cluster.pattern);
// // // //         }
// // // //       });

// // // //       const patternsToSave = Array.from(selectedPatternsSet);

// // // //       const data = await applyReclassification({
// // // //         transaction_ids: selectedSummary.allTxnIds,
// // // //         target_category: selectedCategory,
// // // //         target_subcategory: selectedSubcategory,
// // // //         patterns: patternsToSave,
// // // //         save_rule: saveRule,
// // // //       });

// // // //       if (data?.status === 'success') {
// // // //         await fetchClusters(targetSubcategory);
// // // //         onSuccess();
// // // //       }
// // // //     } catch (err) {
// // // //       console.error('Failed to apply reclassification:', err);
// // // //     } finally {
// // // //       setSubmitting(false);
// // // //     }
// // // //   };

// // // //   if (!isOpen) return null;

// // // //   return createPortal(
// // // //     <div
// // // //       style={{
// // // //         position: 'fixed',
// // // //         top: 0,
// // // //         left: 0,
// // // //         right: 0,
// // // //         bottom: 0,
// // // //         width: '100vw',
// // // //         height: '100vh',
// // // //         backgroundColor: 'rgba(0, 0, 0, 0.85)',
// // // //         backdropFilter: 'blur(8px)',
// // // //         zIndex: 999999,
// // // //         display: 'flex',
// // // //         alignItems: 'center',
// // // //         justifyContent: 'center',
// // // //         padding: '20px',
// // // //         boxSizing: 'border-box',
// // // //         fontFamily: 'monospace',
// // // //       }}
// // // //     >
// // // //       <div
// // // //         style={{
// // // //           backgroundColor: '#09090b',
// // // //           border: '1px solid #27272a',
// // // //           borderRadius: '16px',
// // // //           width: '100%',
// // // //           maxWidth: '1100px',
// // // //           height: '80vh',
// // // //           display: 'flex',
// // // //           flexDirection: 'column',
// // // //           boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.75)',
// // // //           overflow: 'hidden',
// // // //           color: '#f4f4f5',
// // // //         }}
// // // //       >
// // // //         {/* Header Bar */}
// // // //         <div
// // // //           style={{
// // // //             display: 'flex',
// // // //             justifyContent: 'space-between',
// // // //             alignItems: 'center',
// // // //             padding: '16px 24px',
// // // //             borderBottom: '1px solid #27272a',
// // // //             backgroundColor: '#18181b',
// // // //           }}
// // // //         >
// // // //           <div>
// // // //             <h2 style={{ margin: 0, fontSize: '14px', fontWeight: 'bold', textTransform: 'uppercase', color: '#f4f4f5', display: 'flex', alignItems: 'center', gap: '8px' }}>
// // // //               <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#f59e0b' }} />
// // // //               Classification Workbench — {targetSubcategory || 'Suspense Account'}
// // // //             </h2>
// // // //             <p style={{ margin: '4px 0 0 0', fontSize: '11px', color: '#71717a' }}>
// // // //               Reviewing merchant clusters under <strong style={{ color: '#e4e4e7' }}>{targetSubcategory || 'Suspense Account'}</strong>. Check individual line items to assign target taxonomy nodes.
// // // //             </p>
// // // //           </div>
// // // //           <button
// // // //             onClick={onClose}
// // // //             style={{
// // // //               background: 'none',
// // // //               border: 'none',
// // // //               color: '#71717a',
// // // //               fontSize: '18px',
// // // //               cursor: 'pointer',
// // // //               padding: '4px 8px',
// // // //               borderRadius: '6px',
// // // //             }}
// // // //           >
// // // //             ✕
// // // //           </button>
// // // //         </div>

// // // //         {/* Workspace Body */}
// // // //         <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          
// // // //           {/* LEFT PANEL: Merchant Clusters */}
// // // //           <div style={{ width: '58%', borderRight: '1px solid #27272a', display: 'flex', flexDirection: 'column', backgroundColor: '#09090b' }}>
            
// // // //             {/* Search & Select Bar */}
// // // //             <div style={{ padding: '12px', borderBottom: '1px solid #27272a', display: 'flex', alignItems: 'center', gap: '12px', backgroundColor: '#121215' }}>
// // // //               <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#a1a1aa', cursor: 'pointer', fontWeight: 'bold' }}>
// // // //                 <input
// // // //                   type="checkbox"
// // // //                   checked={visibleTxnIds.length > 0 && visibleTxnIds.every((id) => selectedTxnIds.includes(id))}
// // // //                   onChange={toggleSelectAllVisible}
// // // //                   style={{ width: '16px', height: '16px', accentColor: '#f59e0b', cursor: 'pointer' }}
// // // //                 />
// // // //                 Visible Lines
// // // //               </label>

// // // //               {selectedTxnIds.length > 0 && (
// // // //                 <button
// // // //                   onClick={clearAllSelections}
// // // //                   style={{
// // // //                     backgroundColor: '#27272a',
// // // //                     color: '#f4f4f5',
// // // //                     border: 'none',
// // // //                     borderRadius: '4px',
// // // //                     padding: '2px 8px',
// // // //                     fontSize: '10px',
// // // //                     cursor: 'pointer',
// // // //                   }}
// // // //                 >
// // // //                   Uncheck All ({selectedTxnIds.length})
// // // //                 </button>
// // // //               )}

// // // //               <input
// // // //                 type="text"
// // // //                 placeholder="Search vendor patterns, raw narrations..."
// // // //                 value={searchQuery}
// // // //                 onChange={(e) => setSearchQuery(e.target.value)}
// // // //                 style={{
// // // //                   flex: 1,
// // // //                   backgroundColor: '#18181b',
// // // //                   border: '1px solid #27272a',
// // // //                   borderRadius: '8px',
// // // //                   padding: '6px 12px',
// // // //                   fontSize: '12px',
// // // //                   color: '#f4f4f5',
// // // //                   outline: 'none',
// // // //                 }}
// // // //               />
// // // //             </div>

// // // //             {/* Scrollable Cluster List */}
// // // //             <div style={{ flex: 1, overflowY: 'auto', padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
// // // //               {loading ? (
// // // //                 <div style={{ textAlign: 'center', padding: '60px 0', color: '#71717a', fontSize: '12px' }}>
// // // //                   Parsing merchant anchors & building clusters...
// // // //                 </div>
// // // //               ) : filteredClusters.length === 0 ? (
// // // //                 <div style={{ textAlign: 'center', padding: '60px 0', color: '#71717a', fontSize: '12px' }}>
// // // //                   No matching patterns found.
// // // //                 </div>
// // // //               ) : (
// // // //                 filteredClusters.map((cluster, clusterIdx) => {
// // // //                   const clusterTxnIds: string[] = cluster.transaction_ids || [];
// // // //                   const selectedInClusterCount = clusterTxnIds.filter((id) => selectedTxnIds.includes(id)).length;
// // // //                   const isClusterFullySelected = clusterTxnIds.length > 0 && selectedInClusterCount === clusterTxnIds.length;
// // // //                   const isClusterPartiallySelected = selectedInClusterCount > 0 && !isClusterFullySelected;
// // // //                   const isActive = activePreviewCluster?.pattern === cluster.pattern;
// // // //                   const clusterKey = cluster.pattern ? `cluster-${cluster.pattern}-${clusterIdx}` : `cluster-idx-${clusterIdx}`;

// // // //                   const clusterOutflow = cluster.total_outflow ?? cluster.total_amount ?? 0;
// // // //                   const clusterInflow = cluster.total_inflow ?? 0;

// // // //                   return (
// // // //                     <div
// // // //                       key={clusterKey}
// // // //                       onClick={() => setActivePreviewCluster(cluster)}
// // // //                       style={{
// // // //                         padding: '12px',
// // // //                         borderRadius: '10px',
// // // //                         border: `1px solid ${isActive ? '#f59e0b' : selectedInClusterCount > 0 ? '#3f3f46' : '#27272a'}`,
// // // //                         backgroundColor: isActive ? '#18181b' : '#0f0f12',
// // // //                         cursor: 'pointer',
// // // //                         transition: 'all 0.15s ease',
// // // //                       }}
// // // //                     >
// // // //                       {/* Master Cluster Header Row */}
// // // //                       <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
// // // //                         <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
// // // //                           <input
// // // //                             type="checkbox"
// // // //                             checked={isClusterFullySelected}
// // // //                             ref={(el) => { if (el) el.indeterminate = isClusterPartiallySelected; }}
// // // //                             onClick={(e) => toggleClusterTxns(clusterTxnIds, e)}
// // // //                             onChange={() => {}}
// // // //                             style={{ width: '16px', height: '16px', accentColor: '#f59e0b', cursor: 'pointer' }}
// // // //                           />
// // // //                           <span style={{ fontWeight: 'bold', fontSize: '12px', color: '#f4f4f5' }}>
// // // //                             #{cluster.pattern || 'GENERAL_SUSPENSE'}
// // // //                           </span>
// // // //                         </div>
                        
// // // //                         {/* Cluster Totals & Inflow/Outflow Flags */}
// // // //                         <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
// // // //                           <span style={{ padding: '2px 6px', fontSize: '10px', backgroundColor: '#27272a', color: '#d4d4d8', borderRadius: '4px' }}>
// // // //                             {selectedInClusterCount} / {cluster.count || clusterTxnIds.length || 0} selected
// // // //                           </span>
                          
// // // //                           {clusterOutflow > 0 && (
// // // //                             <span style={{ fontSize: '11px', fontWeight: 'bold', color: '#fb7185', backgroundColor: '#88133722', padding: '2px 6px', borderRadius: '4px', border: '1px solid #f43f5e33' }}>
// // // //                               🔻 Out: {inrFormatter.format(clusterOutflow)}
// // // //                             </span>
// // // //                           )}
                          
// // // //                           {clusterInflow > 0 && (
// // // //                             <span style={{ fontSize: '11px', fontWeight: 'bold', color: '#34d399', backgroundColor: '#064e3b22', padding: '2px 6px', borderRadius: '4px', border: '1px solid #10b98133' }}>
// // // //                               🟢 In: {inrFormatter.format(clusterInflow)}
// // // //                             </span>
// // // //                           )}
// // // //                         </div>
// // // //                       </div>

// // // //                       {/* Line Items Array */}
// // // //                       <div style={{ paddingLeft: '8px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
// // // //                         {cluster.items && cluster.items.length > 0 ? (
// // // //                           cluster.items.map((item, itemIdx) => {
// // // //                             const isItemChecked = selectedTxnIds.includes(item.id);
// // // //                             const isOutflow = item.direction ? item.direction === 'OUTFLOW' : (item.debit ?? 0) > 0 || item.amount > 0;
// // // //                             const flagColor = isOutflow ? '#fb7185' : '#34d399';
// // // //                             const bgColor = isItemChecked ? '#27272a' : isOutflow ? '#1c1317' : '#111c18';
// // // //                             const itemKey = item.id ? `item-${item.id}` : `item-idx-${clusterIdx}-${itemIdx}`;

// // // //                             return (
// // // //                               <label
// // // //                                 key={itemKey}
// // // //                                 onClick={(e) => e.stopPropagation()}
// // // //                                 style={{
// // // //                                   display: 'flex',
// // // //                                   alignItems: 'center',
// // // //                                   gap: '8px',
// // // //                                   padding: '4px 8px',
// // // //                                   borderRadius: '6px',
// // // //                                   backgroundColor: bgColor,
// // // //                                   borderLeft: `3px solid ${flagColor}`,
// // // //                                   cursor: 'pointer',
// // // //                                   fontSize: '11px',
// // // //                                   color: isItemChecked ? '#f4f4f5' : '#a1a1aa',
// // // //                                 }}
// // // //                               >
// // // //                                 <input
// // // //                                   type="checkbox"
// // // //                                   checked={isItemChecked}
// // // //                                   onClick={(e) => toggleIndividualTxn(item.id, e)}
// // // //                                   onChange={() => {}}
// // // //                                   style={{ width: '14px', height: '14px', accentColor: '#f59e0b', cursor: 'pointer' }}
// // // //                                 />

// // // //                                 <span
// // // //                                   style={{
// // // //                                     fontSize: '9px',
// // // //                                     fontWeight: 'bold',
// // // //                                     padding: '1px 4px',
// // // //                                     borderRadius: '3px',
// // // //                                     backgroundColor: isOutflow ? '#88133744' : '#064e3b44',
// // // //                                     color: flagColor,
// // // //                                     border: `1px solid ${isOutflow ? '#f43f5e44' : '#10b98144'}`,
// // // //                                   }}
// // // //                                 >
// // // //                                   {isOutflow ? 'OUT' : 'IN'}
// // // //                                 </span>

// // // //                                 <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontFamily: 'monospace' }}>
// // // //                                   {item.narration || 'Unlabeled Transaction'}
// // // //                                 </span>

// // // //                                 <span style={{ fontSize: '11px', fontWeight: 'bold', color: flagColor, fontFamily: 'monospace' }}>
// // // //                                   {isOutflow ? `-₹${(item.amount || 0).toLocaleString('en-IN')}` : `+₹${(item.amount || 0).toLocaleString('en-IN')}`}
// // // //                                 </span>
// // // //                               </label>
// // // //                             );
// // // //                           })
// // // //                         ) : (
// // // //                           (cluster.sample_descriptions || []).map((desc: string, descIdx: number) => (
// // // //                             <div 
// // // //                               key={`desc-${clusterIdx}-${descIdx}`} 
// // // //                               style={{ fontSize: '10px', color: '#71717a', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontFamily: 'monospace' }}
// // // //                             >
// // // //                               • {desc}
// // // //                             </div>
// // // //                           ))
// // // //                         )}
// // // //                       </div>
// // // //                     </div>
// // // //                   );
// // // //                 })
// // // //               )}
// // // //             </div>
// // // //           </div>

// // // //           {/* RIGHT PANEL: Category Mapper & Execution */}
// // // //           <div style={{ width: '42%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '24px', backgroundColor: '#0f0f12' }}>
// // // //             <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              
// // // //               {/* Summary Card */}
// // // //               <div style={{ backgroundColor: '#18181b', border: '1px solid #27272a', padding: '16px', borderRadius: '12px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
// // // //                 <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', fontWeight: 'bold' }}>
// // // //                   Target Selection Summary
// // // //                 </span>
// // // //                 <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
// // // //                   <span style={{ fontSize: '13px', fontWeight: 'bold', color: selectedSummary.totalTxns > 0 ? '#f59e0b' : '#71717a' }}>
// // // //                     {selectedSummary.totalTxns} Line Item{selectedSummary.totalTxns !== 1 ? 's' : ''} Selected
// // // //                   </span>
// // // //                   <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f4f4f5' }}>
// // // //                     {inrFormatter.format(selectedSummary?.totalAmount || 0)}
// // // //                   </span>
// // // //                 </div>
// // // //               </div>

// // // //               {/* Category Dropdowns & On-The-Go Creator */}
// // // //               <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
// // // //                 <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #27272a', paddingBottom: '8px' }}>
// // // //                   <h3 style={{ margin: 0, fontSize: '11px', fontWeight: 'bold', textTransform: 'uppercase', color: '#a1a1aa' }}>
// // // //                     Assign Taxonomy Nodes
// // // //                   </h3>
// // // //                   <button
// // // //                     onClick={() => setIsCreatingNew(!isCreatingNew)}
// // // //                     style={{ background: 'none', border: 'none', color: '#f59e0b', fontSize: '11px', cursor: 'pointer', fontWeight: 'bold' }}
// // // //                   >
// // // //                     {isCreatingNew ? '← Back to Select' : '+ Create New Node'}
// // // //                   </button>
// // // //                 </div>

// // // //                 {!isCreatingNew ? (
// // // //                   /* STANDARD DROPDOWN SELECTORS */
// // // //                   <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
// // // //                     <div>
// // // //                       <label style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
// // // //                         Primary Category
// // // //                       </label>
// // // //                       <select
// // // //                         value={selectedCategory}
// // // //                         onChange={(e) => {
// // // //                           const newCat = e.target.value;
// // // //                           setSelectedCategory(newCat);
// // // //                           const found = taxonomyTree.find((t) => t.category === newCat);
// // // //                           if (found && found.subcategories && found.subcategories.length > 0) {
// // // //                             setSelectedSubcategory(found.subcategories[0]);
// // // //                           }
// // // //                         }}
// // // //                         style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', color: '#f4f4f5', outline: 'none' }}
// // // //                       >
// // // //                         {taxonomyTree.map((t, catIdx) => (
// // // //                           <option key={`cat-${t.category}-${catIdx}`} value={t.category}>
// // // //                             {t.category}
// // // //                           </option>
// // // //                         ))}
// // // //                       </select>
// // // //                     </div>

// // // //                     <div>
// // // //                       <label style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
// // // //                         Subcategory
// // // //                       </label>
// // // //                       <select
// // // //                         value={selectedSubcategory || ''}
// // // //                         onChange={(e) => setSelectedSubcategory(e.target.value)}
// // // //                         style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', color: '#f4f4f5', outline: 'none' }}
// // // //                       >
// // // //                         {(availableSubcategories || []).map((sub, subIdx) => (
// // // //                           <option key={`sub-${sub}-${subIdx}`} value={sub}>
// // // //                             {sub}
// // // //                           </option>
// // // //                         ))}
// // // //                       </select>
// // // //                     </div>
// // // //                   </div>
// // // //                 ) : (
// // // //                   /* INLINE CREATION FORM */
// // // //                   <div style={{ backgroundColor: '#18181b', border: '1px dashed #f59e0b', padding: '12px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
// // // //                     <span style={{ fontSize: '11px', color: '#f59e0b', fontWeight: 'bold' }}>
// // // //                       New Taxonomy Entry
// // // //                     </span>
// // // //                     <div>
// // // //                       <label style={{ fontSize: '10px', color: '#a1a1aa', display: 'block', marginBottom: '2px' }}>
// // // //                         Category Name (e.g. Expense, Asset)
// // // //                       </label>
// // // //                       <input
// // // //                         type="text"
// // // //                         placeholder="e.g. Expense"
// // // //                         value={newCatInput}
// // // //                         onChange={(e) => setNewCatInput(e.target.value)}
// // // //                         style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', fontSize: '12px', color: '#f4f4f5' }}
// // // //                       />
// // // //                     </div>

// // // //                     <div>
// // // //                       <label style={{ fontSize: '10px', color: '#a1a1aa', display: 'block', marginBottom: '2px' }}>
// // // //                         Subcategory Name
// // // //                       </label>
// // // //                       <input
// // // //                         type="text"
// // // //                         placeholder="e.g. Panchami Devi Temple"
// // // //                         value={newSubInput}
// // // //                         onChange={(e) => setNewSubInput(e.target.value)}
// // // //                         style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', fontSize: '12px', color: '#f4f4f5' }}
// // // //                       />
// // // //                     </div>

// // // //                     <button
// // // //                       onClick={handleCreateTaxonomy}
// // // //                       disabled={savingNewTaxonomy || !newCatInput.trim() || !newSubInput.trim()}
// // // //                       style={{
// // // //                         marginTop: '4px',
// // // //                         padding: '8px 12px',
// // // //                         borderRadius: '6px',
// // // //                         fontSize: '11px',
// // // //                         fontWeight: 'bold',
// // // //                         backgroundColor: '#f59e0b',
// // // //                         color: '#09090b',
// // // //                         border: 'none',
// // // //                         cursor: savingNewTaxonomy ? 'wait' : 'pointer',
// // // //                       }}
// // // //                     >
// // // //                       {savingNewTaxonomy ? 'Saving...' : 'Add & Select Node'}
// // // //                     </button>
// // // //                   </div>
// // // //                 )}
// // // //               </div>

// // // //               {/* Rule Learning Toggle */}
// // // //               <div style={{ backgroundColor: '#09090b', border: '1px solid #27272a', padding: '12px', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
// // // //                 <div>
// // // //                   <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f4f4f5', display: 'block' }}>
// // // //                     Save to Classification Rules
// // // //                   </span>
// // // //                   <span style={{ fontSize: '10px', color: '#71717a', display: 'block' }}>
// // // //                     Auto-classify future imports matching active vendor pattern
// // // //                   </span>
// // // //                 </div>
// // // //                 <input
// // // //                   type="checkbox"
// // // //                   checked={saveRule}
// // // //                   onChange={(e) => setSaveRule(e.target.checked)}
// // // //                   style={{ width: '16px', height: '16px', accentColor: '#f59e0b', cursor: 'pointer' }}
// // // //                 />
// // // //               </div>

// // // //             </div>

// // // //             {/* Footer Action Buttons */}
// // // //             <div style={{ borderTop: '1px solid #27272a', paddingTop: '16px', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
// // // //               <button
// // // //                 onClick={onClose}
// // // //                 style={{ padding: '8px 16px', borderRadius: '8px', fontSize: '12px', color: '#a1a1aa', background: 'none', border: 'none', cursor: 'pointer' }}
// // // //               >
// // // //                 Cancel
// // // //               </button>
// // // //               <button
// // // //                 disabled={submitting || selectedSummary.allTxnIds.length === 0}
// // // //                 onClick={handleApplyClassification}
// // // //                 style={{
// // // //                   padding: '10px 20px',
// // // //                   borderRadius: '8px',
// // // //                   fontSize: '12px',
// // // //                   fontWeight: 'bold',
// // // //                   backgroundColor: '#f59e0b',
// // // //                   color: '#09090b',
// // // //                   border: 'none',
// // // //                   cursor: submitting || selectedSummary.allTxnIds.length === 0 ? 'not-allowed' : 'pointer',
// // // //                   opacity: submitting || selectedSummary.allTxnIds.length === 0 ? 0.5 : 1,
// // // //                 }}
// // // //               >
// // // //                 {submitting ? 'Applying...' : `Reclassify ${selectedSummary.totalTxns} Selected Line${selectedSummary.totalTxns !== 1 ? 's' : ''}`}
// // // //               </button>
// // // //             </div>

// // // //           </div>

// // // //         </div>
// // // //       </div>
// // // //     </div>,
// // // //     document.body
// // // //   );
// // // // };