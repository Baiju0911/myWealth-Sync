// webapp/src/components/Stage3/Workbench/useWorkbenchModalState.ts
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
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
} from '../../../api/api';
import { subledgerApi } from '../../../api/subledger';
import { calculateSelectedMetrics } from '../../../utils/classificationHelpers';
import { clearSubledgerBreakdownCache } from './TaxonomyMapperPanel';

interface UseWorkbenchModalStateProps {
  isOpen: boolean;
  targetSubcategory: string;
  accountId?: number;
  onSuccess: () => void;
}

export function useWorkbenchModalState({
  isOpen,
  targetSubcategory = 'Suspense Account',
  accountId,
  onSuccess,
}: UseWorkbenchModalStateProps) {
  const [clusters, setClusters] = useState<ExtendedCluster[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');

  const [selectedTxnIds, setSelectedTxnIds] = useState<string[]>([]);
  const [activePreviewCluster, setActivePreviewCluster] = useState<
    ExtendedCluster | Cluster | null
  >(null);

  const [vectorType, setVectorType] = useState<'Debit' | 'Credit'>('Debit');
  const [isPatternModalOpen, setIsPatternModalOpen] = useState<boolean>(false);
  const [suggestedRule, setSuggestedRule] = useState<SuggestedRule | null>(
    null
  );

  const [selectedCategory, setSelectedCategory] = useState<string>('Expense');
  const [selectedSubcategory, setSelectedSubcategory] =
    useState<string>('Housing & Rent');
  const [saveRule, setSaveRule] = useState<boolean>(true);
  const [upiStrategy, setUpiStrategy] = useState<'vendor' | 'auto_consolidate'>(
    'auto_consolidate'
  );

  // 🎯 Track the chosen Subledger Folio ID (e.g., CASH-FLT-8822 or '')
  const [selectedSubledgerFolioId, setSelectedSubledgerFolioId] =
    useState<string>('');

  const [taxonomyTree, setTaxonomyTree] = useState<TaxonomyOption[]>([]);
  const [isCreatingNew, setIsCreatingNew] = useState<boolean>(false);
  const [newCatInput, setNewCatInput] = useState<string>('');
  const [newSubInput, setNewSubInput] = useState<string>('');
  const [savingNewTaxonomy, setSavingNewTaxonomy] = useState<boolean>(false);

  // Direct Folio Creation Modal
  const [isFolioModalOpen, setIsFolioModalOpen] = useState<boolean>(false);
  const [pendingTargetSubcategory, setPendingTargetSubcategory] =
    useState<string>('');

  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastExecutedSearchRef = useRef<string>('');
  const isFirstMountRef = useRef<boolean>(true);

  const loadClusters = useCallback(
    async (
      subcategoryName: string,
      currentAccountId?: number,
      query?: string
    ) => {
      setLoading(true);
      try {
        const data = await getSuspenseClusters(
          subcategoryName,
          currentAccountId,
          query
        );
        if (data?.status === 'success') {
          const list = (data.clusters || []) as ExtendedCluster[];
          setClusters(list);

          if (list.length > 0) {
            setActivePreviewCluster((prev) => {
              if (!prev) {
                const first = list[0];
                const outflow =
                  (first.total_outflow ?? first.total_amount ?? 0) > 0;
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
    },
    []
  );

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
          (t.subcategories || []).some(
            (s: any) => getSubName(s).toLowerCase() === targetName.toLowerCase()
          )
        );

        if (!matchedCatNode) {
          const lower = targetName.toLowerCase();
          if (
            lower.includes('gold') ||
            lower.includes('asset') ||
            lower.includes('share') ||
            lower.includes('deposit') ||
            lower.includes('real estate')
          ) {
            matchedCatNode = data.find(
              (t: TaxonomyOption) => t.category === 'Asset'
            );
          }
        }

        if (!matchedCatNode) {
          matchedCatNode =
            data.find((t: TaxonomyOption) => t.category === 'Expense') ||
            data[0];
        }

        setSelectedCategory(matchedCatNode.category);

        const currentSubs = (matchedCatNode.subcategories || [])
          .map(getSubName)
          .filter(Boolean);
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
      setSelectedSubledgerFolioId('');

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
      const cleanPattern = activePreviewCluster.pattern.replace(/^#+/, '');
      const suggestion = await getSuggestedRule(cleanPattern, vectorType);

      if (isMounted && suggestion) {
        setSuggestedRule(suggestion);
        const targetCat =
          (suggestion as any).target_category || suggestion.suggested_category;
        const targetSub =
          (suggestion as any).target_subcategory ||
          suggestion.suggested_subcategory;

        if (targetCat) setSelectedCategory(targetCat);
        if (targetSub) setSelectedSubcategory(targetSub);
      }
    };

    fetchSuggestion();
    return () => {
      isMounted = false;
    };
  }, [activePreviewCluster?.pattern, vectorType]);

  const availableSubcategories = useMemo(() => {
    if (!taxonomyTree || taxonomyTree.length === 0) return [];
    const found =
      taxonomyTree.find(
        (item: TaxonomyOption) => item.category === selectedCategory
      ) || taxonomyTree[0];
    const rawList = found ? found.subcategories || [] : [];

    return rawList
      .map((sub: any) =>
        typeof sub === 'object' && sub !== null
          ? String(sub.subcategory || sub.name || sub.title || '')
          : String(sub || '')
      )
      .filter(Boolean);
  }, [taxonomyTree, selectedCategory]);

  const visibleTxnIds = useMemo(
    () => clusters.flatMap((c) => c.transaction_ids || []),
    [clusters]
  );
  const selectedSummary = useMemo(
    () => calculateSelectedMetrics(clusters, selectedTxnIds),
    [clusters, selectedTxnIds]
  );
  const activeVendorName = useMemo(
    () => (activePreviewCluster?.pattern || '').replace(/^#+/, '').trim(),
    [activePreviewCluster]
  );

  const handleSelectCluster = useCallback(
    (cluster: ExtendedCluster | Cluster) => {
      setActivePreviewCluster(cluster);
      const ext = cluster as ExtendedCluster;
      const isOutflow = (ext.total_outflow ?? ext.total_amount ?? 0) > 0;
      setVectorType(isOutflow ? 'Debit' : 'Credit');
    },
    []
  );

  const toggleIndividualTxn = useCallback(
    (txnId: string, e: React.MouseEvent) => {
      e.stopPropagation();
      setSelectedTxnIds((prev) =>
        prev.includes(txnId)
          ? prev.filter((id) => id !== txnId)
          : [...prev, txnId]
      );
    },
    []
  );

  const toggleClusterTxns = useCallback(
    (clusterTxnIds: string[], e: React.MouseEvent) => {
      e.stopPropagation();
      const allSelected =
        clusterTxnIds.length > 0 &&
        clusterTxnIds.every((id) => selectedTxnIds.includes(id));
      if (allSelected) {
        setSelectedTxnIds((prev) =>
          prev.filter((id) => !clusterTxnIds.includes(id))
        );
      } else {
        setSelectedTxnIds((prev) =>
          Array.from(new Set([...prev, ...clusterTxnIds]))
        );
      }
    },
    [selectedTxnIds]
  );

  const toggleSelectAllVisible = useCallback(() => {
    const allSelected =
      visibleTxnIds.length > 0 &&
      visibleTxnIds.every((id) => selectedTxnIds.includes(id));
    if (allSelected) {
      setSelectedTxnIds((prev) =>
        prev.filter((id) => !visibleTxnIds.includes(id))
      );
    } else {
      setSelectedTxnIds((prev) =>
        Array.from(new Set([...prev, ...visibleTxnIds]))
      );
    }
  }, [visibleTxnIds, selectedTxnIds]);

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
    } finally {
      setSavingNewTaxonomy(false);
    }
  };

  const handleFinalReclassificationSubmit = async (
    chosenPatterns: string[]
  ) => {
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
        subledger_asset_id: selectedSubledgerFolioId || undefined,
      } as any);

      // If user selected a folio, bind transactions directly to it
      if (data?.status === 'success' && selectedSubledgerFolioId) {
        try {
          const selectedItems = clusters
            .flatMap((c) => (c as any).items || (c as any).transactions || [])
            .filter((item) =>
              selectedSummary.allTxnIds.includes(
                String(item.id || item.row_identifier)
              )
            );

          for (const item of selectedItems) {
            await subledgerApi.bindTransaction({
              asset_id: selectedSubledgerFolioId,
              row_identifier: item.row_identifier || item.id,
              transaction_date:
                item.transaction_date ||
                item.date ||
                new Date().toISOString().split('T')[0],
              amount: Number(item.debit || item.credit || item.amount || 0),
              transaction_purpose: 'OPERATING_SPEND',
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
        setSelectedSubledgerFolioId('');
        await loadClusters(targetSubcategory, accountId, searchQuery);
        onSuccess();
      }
    } catch (err) {
      console.error('Failed to apply reclassification:', err);
    } finally {
      setSubmitting(false);
    }
  };

  return {
    state: {
      clusters,
      loading,
      submitting,
      searchQuery,
      selectedTxnIds,
      activePreviewCluster,
      vectorType,
      isPatternModalOpen,
      suggestedRule,
      selectedCategory,
      selectedSubcategory,
      selectedSubledgerFolioId,
      saveRule,
      upiStrategy,
      taxonomyTree,
      availableSubcategories,
      visibleTxnIds,
      selectedSummary,
      activeVendorName,
      isCreatingNew,
      newCatInput,
      newSubInput,
      savingNewTaxonomy,
      isFolioModalOpen,
      pendingTargetSubcategory,
    },
    actions: {
      setSearchQuery,
      handleSelectCluster,
      toggleIndividualTxn,
      toggleClusterTxns,
      toggleSelectAllVisible,
      clearAllSelections: () => setSelectedTxnIds([]),
      setSelectedCategory,
      setSelectedSubcategory,
      setSelectedSubledgerFolioId,
      setSaveRule,
      setUpiStrategy,
      setIsCreatingNew,
      setNewCatInput,
      setNewSubInput,
      handleCreateTaxonomy,
      setIsPatternModalOpen,
      handleOpenPatternSelectionFlow: (targetFolioId?: string) => {
        if (selectedSummary.allTxnIds.length === 0) return;
        if (targetFolioId) setSelectedSubledgerFolioId(targetFolioId);
        setIsPatternModalOpen(true);
      },
      handleFinalReclassificationSubmit,
      setIsFolioModalOpen,
      setPendingTargetSubcategory,
      loadClusters,
    },
  };
}

// // webapp/src/components/Stage3/Workbench/useWorkbenchModalState.ts
// import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
// import {
//   getSuspenseClusters,
//   applyReclassification,
//   getTaxonomyTree,
//   addTaxonomyNode,
//   getSuggestedRule,
//   type SuggestedRule,
//   type TaxonomyOption,
//   type ExtendedCluster,
//   type Cluster,
// } from '../../../api/api';
// import { subledgerApi } from '../../../api/subledger';
// import { calculateSelectedMetrics } from '../../../utils/classificationHelpers';
// import { clearSubledgerBreakdownCache } from './TaxonomyMapperPanel';

// interface UseWorkbenchModalStateProps {
//   isOpen: boolean;
//   targetSubcategory: string;
//   accountId?: number;
//   onSuccess: () => void;
// }

// export function useWorkbenchModalState({
//   isOpen,
//   targetSubcategory = 'Suspense Account',
//   accountId,
//   onSuccess,
// }: UseWorkbenchModalStateProps) {
//   const [clusters, setClusters] = useState<ExtendedCluster[]>([]);
//   const [loading, setLoading] = useState<boolean>(false);
//   const [submitting, setSubmitting] = useState<boolean>(false);
//   const [searchQuery, setSearchQuery] = useState<string>('');

//   const [selectedTxnIds, setSelectedTxnIds] = useState<string[]>([]);
//   const [activePreviewCluster, setActivePreviewCluster] = useState<
//     ExtendedCluster | Cluster | null
//   >(null);

//   const [vectorType, setVectorType] = useState<'Debit' | 'Credit'>('Debit');
//   const [isPatternModalOpen, setIsPatternModalOpen] = useState<boolean>(false);
//   const [suggestedRule, setSuggestedRule] = useState<SuggestedRule | null>(
//     null
//   );

//   const [selectedCategory, setSelectedCategory] = useState<string>('Expense');
//   const [selectedSubcategory, setSelectedSubcategory] =
//     useState<string>('Housing & Rent');
//   const [saveRule, setSaveRule] = useState<boolean>(true);
//   const [upiStrategy, setUpiStrategy] = useState<'vendor' | 'auto_consolidate'>(
//     'auto_consolidate'
//   );

//   const [taxonomyTree, setTaxonomyTree] = useState<TaxonomyOption[]>([]);
//   const [isCreatingNew, setIsCreatingNew] = useState<boolean>(false);
//   const [newCatInput, setNewCatInput] = useState<string>('');
//   const [newSubInput, setNewSubInput] = useState<string>('');
//   const [savingNewTaxonomy, setSavingNewTaxonomy] = useState<boolean>(false);

//   // Direct Folio Creation Modal
//   const [isFolioModalOpen, setIsFolioModalOpen] = useState<boolean>(false);
//   const [pendingTargetSubcategory, setPendingTargetSubcategory] =
//     useState<string>('');
//   const [pendingFolioBindId, setPendingFolioBindId] = useState<string | null>(
//     null
//   );

//   const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
//   const lastExecutedSearchRef = useRef<string>('');
//   const isFirstMountRef = useRef<boolean>(true);

//   const loadClusters = useCallback(
//     async (
//       subcategoryName: string,
//       currentAccountId?: number,
//       query?: string
//     ) => {
//       setLoading(true);
//       try {
//         const data = await getSuspenseClusters(
//           subcategoryName,
//           currentAccountId,
//           query
//         );
//         if (data?.status === 'success') {
//           const list = (data.clusters || []) as ExtendedCluster[];
//           setClusters(list);

//           if (list.length > 0) {
//             setActivePreviewCluster((prev) => {
//               if (!prev) {
//                 const first = list[0];
//                 const outflow =
//                   (first.total_outflow ?? first.total_amount ?? 0) > 0;
//                 setVectorType(outflow ? 'Debit' : 'Credit');
//                 return first;
//               }
//               return prev;
//             });
//           }
//         }
//       } catch (err) {
//         console.error('Failed to load clusters:', err);
//       } finally {
//         setLoading(false);
//       }
//     },
//     []
//   );

//   const loadTaxonomy = useCallback(async () => {
//     try {
//       const data = await getTaxonomyTree();
//       if (data && data.length > 0) {
//         setTaxonomyTree(data);

//         const getSubName = (sub: any): string =>
//           typeof sub === 'object' && sub !== null
//             ? String(sub.subcategory || sub.name || sub.title || '')
//             : String(sub || '');

//         const targetName = String(targetSubcategory || 'Suspense Account');

//         let matchedCatNode = data.find((t: TaxonomyOption) =>
//           (t.subcategories || []).some(
//             (s: any) => getSubName(s).toLowerCase() === targetName.toLowerCase()
//           )
//         );

//         if (!matchedCatNode) {
//           const lower = targetName.toLowerCase();
//           if (
//             lower.includes('gold') ||
//             lower.includes('asset') ||
//             lower.includes('share') ||
//             lower.includes('deposit') ||
//             lower.includes('real estate')
//           ) {
//             matchedCatNode = data.find(
//               (t: TaxonomyOption) => t.category === 'Asset'
//             );
//           }
//         }

//         if (!matchedCatNode) {
//           matchedCatNode =
//             data.find((t: TaxonomyOption) => t.category === 'Expense') ||
//             data[0];
//         }

//         setSelectedCategory(matchedCatNode.category);

//         const currentSubs = (matchedCatNode.subcategories || [])
//           .map(getSubName)
//           .filter(Boolean);
//         if (currentSubs.length > 0) {
//           setSelectedSubcategory(
//             currentSubs.includes(targetName) ? targetName : currentSubs[0]
//           );
//         }
//       }
//     } catch (err) {
//       console.error('Failed to load dynamic taxonomy:', err);
//     }
//   }, [targetSubcategory]);

//   useEffect(() => {
//     if (isOpen) {
//       isFirstMountRef.current = true;
//       lastExecutedSearchRef.current = '';
//       setSearchQuery('');
//       setSelectedTxnIds([]);
//       setActivePreviewCluster(null);

//       loadClusters(targetSubcategory, accountId, '');
//       loadTaxonomy();
//     }
//   }, [isOpen, targetSubcategory, accountId, loadClusters, loadTaxonomy]);

//   useEffect(() => {
//     if (!isOpen) return;

//     if (isFirstMountRef.current) {
//       isFirstMountRef.current = false;
//       return;
//     }

//     const trimmed = searchQuery.trim();
//     if (trimmed === lastExecutedSearchRef.current) return;

//     if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);

//     searchDebounceRef.current = setTimeout(() => {
//       lastExecutedSearchRef.current = trimmed;
//       loadClusters(targetSubcategory, accountId, trimmed);
//     }, 350);

//     return () => {
//       if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
//     };
//   }, [searchQuery, isOpen, targetSubcategory, accountId, loadClusters]);

//   useEffect(() => {
//     let isMounted = true;
//     const fetchSuggestion = async () => {
//       if (!activePreviewCluster?.pattern) {
//         if (isMounted) setSuggestedRule(null);
//         return;
//       }
//       const cleanPattern = activePreviewCluster.pattern.replace(/^#+/, '');
//       const suggestion = await getSuggestedRule(cleanPattern, vectorType);

//       if (isMounted && suggestion) {
//         setSuggestedRule(suggestion);
//         const targetCat =
//           (suggestion as any).target_category || suggestion.suggested_category;
//         const targetSub =
//           (suggestion as any).target_subcategory ||
//           suggestion.suggested_subcategory;

//         if (targetCat) setSelectedCategory(targetCat);
//         if (targetSub) setSelectedSubcategory(targetSub);
//       }
//     };

//     fetchSuggestion();
//     return () => {
//       isMounted = false;
//     };
//   }, [activePreviewCluster?.pattern, vectorType]);

//   const availableSubcategories = useMemo(() => {
//     if (!taxonomyTree || taxonomyTree.length === 0) return [];
//     const found =
//       taxonomyTree.find(
//         (item: TaxonomyOption) => item.category === selectedCategory
//       ) || taxonomyTree[0];
//     const rawList = found ? found.subcategories || [] : [];

//     return rawList
//       .map((sub: any) =>
//         typeof sub === 'object' && sub !== null
//           ? String(sub.subcategory || sub.name || sub.title || '')
//           : String(sub || '')
//       )
//       .filter(Boolean);
//   }, [taxonomyTree, selectedCategory]);

//   const visibleTxnIds = useMemo(
//     () => clusters.flatMap((c) => c.transaction_ids || []),
//     [clusters]
//   );
//   const selectedSummary = useMemo(
//     () => calculateSelectedMetrics(clusters, selectedTxnIds),
//     [clusters, selectedTxnIds]
//   );
//   const activeVendorName = useMemo(
//     () => (activePreviewCluster?.pattern || '').replace(/^#+/, '').trim(),
//     [activePreviewCluster]
//   );

//   const handleSelectCluster = useCallback(
//     (cluster: ExtendedCluster | Cluster) => {
//       setActivePreviewCluster(cluster);
//       const ext = cluster as ExtendedCluster;
//       const isOutflow = (ext.total_outflow ?? ext.total_amount ?? 0) > 0;
//       setVectorType(isOutflow ? 'Debit' : 'Credit');
//     },
//     []
//   );

//   const toggleIndividualTxn = useCallback(
//     (txnId: string, e: React.MouseEvent) => {
//       e.stopPropagation();
//       setSelectedTxnIds((prev) =>
//         prev.includes(txnId)
//           ? prev.filter((id) => id !== txnId)
//           : [...prev, txnId]
//       );
//     },
//     []
//   );

//   const toggleClusterTxns = useCallback(
//     (clusterTxnIds: string[], e: React.MouseEvent) => {
//       e.stopPropagation();
//       const allSelected =
//         clusterTxnIds.length > 0 &&
//         clusterTxnIds.every((id) => selectedTxnIds.includes(id));
//       if (allSelected) {
//         setSelectedTxnIds((prev) =>
//           prev.filter((id) => !clusterTxnIds.includes(id))
//         );
//       } else {
//         setSelectedTxnIds((prev) =>
//           Array.from(new Set([...prev, ...clusterTxnIds]))
//         );
//       }
//     },
//     [selectedTxnIds]
//   );

//   const toggleSelectAllVisible = useCallback(() => {
//     const allSelected =
//       visibleTxnIds.length > 0 &&
//       visibleTxnIds.every((id) => selectedTxnIds.includes(id));
//     if (allSelected) {
//       setSelectedTxnIds((prev) =>
//         prev.filter((id) => !visibleTxnIds.includes(id))
//       );
//     } else {
//       setSelectedTxnIds((prev) =>
//         Array.from(new Set([...prev, ...visibleTxnIds]))
//       );
//     }
//   }, [visibleTxnIds, selectedTxnIds]);

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
//     } finally {
//       setSavingNewTaxonomy(false);
//     }
//   };

//   const handleFinalReclassificationSubmit = async (
//     chosenPatterns: string[]
//   ) => {
//     if (selectedSummary.allTxnIds.length === 0) return;
//     setSubmitting(true);

//     try {
//       const data = await applyReclassification({
//         transaction_ids: selectedSummary.allTxnIds,
//         target_category: selectedCategory,
//         target_subcategory: selectedSubcategory,
//         patterns: chosenPatterns,
//         save_rule: saveRule && chosenPatterns.length > 0,
//         entry_type: vectorType,
//         upi_strategy: vectorType === 'Debit' ? upiStrategy : 'vendor',
//         subledger_asset_id: pendingFolioBindId || undefined,
//       } as any);

//       // Bind transactions directly if user selected a folio
//       if (data?.status === 'success' && pendingFolioBindId) {
//         try {
//           const selectedItems = clusters
//             .flatMap((c) => (c as any).items || (c as any).transactions || [])
//             .filter((item) =>
//               selectedSummary.allTxnIds.includes(
//                 String(item.id || item.row_identifier)
//               )
//             );

//           for (const item of selectedItems) {
//             await subledgerApi.bindTransaction({
//               asset_id: pendingFolioBindId,
//               row_identifier: item.row_identifier || item.id,
//               transaction_date:
//                 item.transaction_date ||
//                 item.date ||
//                 new Date().toISOString().split('T')[0],
//               amount: Number(item.debit || item.credit || item.amount || 0),
//               transaction_purpose: 'OPERATING_SPEND',
//               user_note: `Classified & Bound via Workbench (${selectedSubcategory})`,
//             });
//           }
//           clearSubledgerBreakdownCache(selectedSubcategory);
//         } catch (bindErr) {
//           console.error('Folio direct auto-binding failed:', bindErr);
//         }
//       }

//       if (data?.status === 'success') {
//         setIsPatternModalOpen(false);
//         setSelectedTxnIds([]);
//         setPendingFolioBindId(null);
//         await loadClusters(targetSubcategory, accountId, searchQuery);
//         onSuccess();
//       }
//     } catch (err) {
//       console.error('Failed to apply reclassification:', err);
//     } finally {
//       setSubmitting(false);
//     }
//   };

//   return {
//     state: {
//       clusters,
//       loading,
//       submitting,
//       searchQuery,
//       selectedTxnIds,
//       activePreviewCluster,
//       vectorType,
//       isPatternModalOpen,
//       suggestedRule,
//       selectedCategory,
//       selectedSubcategory,
//       saveRule,
//       upiStrategy,
//       taxonomyTree,
//       availableSubcategories,
//       visibleTxnIds,
//       selectedSummary,
//       activeVendorName,
//       isCreatingNew,
//       newCatInput,
//       newSubInput,
//       savingNewTaxonomy,
//       isFolioModalOpen,
//       pendingTargetSubcategory,
//     },
//     actions: {
//       setSearchQuery,
//       handleSelectCluster,
//       toggleIndividualTxn,
//       toggleClusterTxns,
//       toggleSelectAllVisible,
//       clearAllSelections: () => setSelectedTxnIds([]),
//       setSelectedCategory,
//       setSelectedSubcategory,
//       setSaveRule,
//       setUpiStrategy,
//       setIsCreatingNew,
//       setNewCatInput,
//       setNewSubInput,
//       handleCreateTaxonomy,
//       setIsPatternModalOpen,
//       handleOpenPatternSelectionFlow: (targetFolioId?: string) => {
//         if (selectedSummary.allTxnIds.length === 0) return;
//         setPendingFolioBindId(targetFolioId || null);
//         setIsPatternModalOpen(true);
//       },
//       handleFinalReclassificationSubmit,
//       setIsFolioModalOpen,
//       setPendingTargetSubcategory,
//       loadClusters,
//     },
//   };
// }
