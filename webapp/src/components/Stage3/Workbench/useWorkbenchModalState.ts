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
  const [selectedRowsMap, setSelectedRowsMap] = useState<Record<string, any>>(
    {}
  );

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

  const [lastAppliedMapping, setLastAppliedMapping] = useState<{
    txnIds: string[];
    asset_id?: string | number;
    asset_code?: string;
    asset_name?: string;
  } | null>(null);

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
      setSelectedRowsMap({});
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
    (txnId: string, e: React.MouseEvent, txnItem?: any) => {
      e.stopPropagation();
      setSelectedTxnIds((prev) => {
        const next = prev.includes(txnId)
          ? prev.filter((id) => id !== txnId)
          : [...prev, txnId];

        // Maintain the real row object map
        setSelectedRowsMap((prevMap) => {
          const newMap = { ...prevMap };
          if (next.includes(txnId)) {
            if (txnItem) newMap[txnId] = txnItem;
          } else {
            delete newMap[txnId];
          }
          return newMap;
        });

        return next;
      });
    },
    []
  );

  // const toggleClusterTxns = useCallback(
  //   (clusterTxnIds: string[], e: React.MouseEvent) => {
  //     e.stopPropagation();
  //     const allSelected =
  //       clusterTxnIds.length > 0 &&
  //       clusterTxnIds.every((id) => selectedTxnIds.includes(id));
  //     if (allSelected) {
  //       setSelectedTxnIds((prev) =>
  //         prev.filter((id) => !clusterTxnIds.includes(id))
  //       );
  //     } else {
  //       setSelectedTxnIds((prev) =>
  //         Array.from(new Set([...prev, ...clusterTxnIds]))
  //       );
  //     }
  //   },
  //   [selectedTxnIds]
  // );

  const toggleClusterTxns = useCallback(
    (clusterTxnIds: string[], e: React.MouseEvent, items: any[] = []) => {
      e.stopPropagation();
      const allSelected =
        clusterTxnIds.length > 0 &&
        clusterTxnIds.every((id) => selectedTxnIds.includes(id));

      if (allSelected) {
        setSelectedTxnIds((prev) =>
          prev.filter((id) => !clusterTxnIds.includes(id))
        );
        setSelectedRowsMap((prev) => {
          const next = { ...prev };
          clusterTxnIds.forEach((id) => delete next[id]);
          return next;
        });
      } else {
        setSelectedTxnIds((prev) =>
          Array.from(new Set([...prev, ...clusterTxnIds]))
        );
        setSelectedRowsMap((prev) => {
          const next = { ...prev };
          items.forEach((it) => {
            if (it && it.id) next[it.id] = it;
          });
          return next;
        });
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

  // 🎯 Resolve the actual transaction objects for all currently checked row IDs
  // const selectedTransactions = useMemo(() => {
  //   if (!clusters || selectedTxnIds.length === 0) return [];

  //   // 🔍 Print the exact structure of clusters and activePreviewCluster
  //   console.log('🔍 [CLUSTER SCHEMA DUMP]', {
  //     clustersLength: clusters.length,
  //     firstClusterKeys: clusters[0] ? Object.keys(clusters[0]) : [],
  //     firstClusterSample: clusters[0],
  //     activePreviewKeys: activePreviewCluster
  //       ? Object.keys(activePreviewCluster)
  //       : [],
  //     selectedTxnIds,
  //   });

  //   const allItems: any[] = [];

  //   // Exhaustive tree scanner
  //   const scanNode = (node: any) => {
  //     if (!node || typeof node !== 'object') return;

  //     // Check all possible row collection property names
  //     const candidates = [
  //       node.items,
  //       node.transactions,
  //       node.txns,
  //       node.lines,
  //       node.records,
  //       node.staging_lines,
  //       node.statement_lines,
  //       node.data,
  //     ];

  //     for (const list of candidates) {
  //       if (Array.isArray(list) && list.length > 0) {
  //         // Verify if elements look like transaction rows
  //         if (
  //           list[0] &&
  //           typeof list[0] === 'object' &&
  //           (list[0].narration ||
  //             list[0].raw_narration ||
  //             list[0].amount ||
  //             list[0].id ||
  //             list[0].row_identifier)
  //         ) {
  //           allItems.push(...list);
  //         }
  //       }
  //     }

  //     // Check all possible child collections
  //     const childCollections = [
  //       node.subclusters,
  //       node.children,
  //       node.groups,
  //       node.subgroups,
  //       node.clusters,
  //       node.vendors,
  //       node.vendor_clusters,
  //     ];

  //     for (const sub of childCollections) {
  //       if (Array.isArray(sub)) {
  //         sub.forEach(scanNode);
  //       } else if (sub && typeof sub === 'object') {
  //         Object.values(sub).forEach(scanNode);
  //       }
  //     }
  //   };

  //   clusters.forEach(scanNode);
  //   if (activePreviewCluster) {
  //     scanNode(activePreviewCluster);
  //   }

  //   console.log('🔍 [ALL ITEMS HARVESTED]', {
  //     totalFound: allItems.length,
  //     sampleFirstItem: allItems[0],
  //     selectedTxnIds,
  //   });

  //   const matched = allItems.filter((item) => {
  //     const candidates = [
  //       item.id,
  //       item.row_identifier,
  //       item.staging_line_id,
  //       item.txn_id,
  //       item.statement_line_id,
  //       item.uuid,
  //       item.line_id,
  //     ]
  //       .filter((val) => val !== undefined && val !== null)
  //       .map(String);

  //     return selectedTxnIds.some((selectedId) =>
  //       candidates.includes(String(selectedId))
  //     );
  //   });

  //   console.log('🎯 [ID MATCH RESULT]', {
  //     selectedCount: selectedTxnIds.length,
  //     matchedCount: matched.length,
  //     matchedSample: matched[0],
  //   });

  //   return matched;
  // }, [clusters, activePreviewCluster, selectedTxnIds]);

  // const selectedTransactions = useMemo(() => {
  //   if (!clusters || selectedTxnIds.length === 0) return [];

  //   const allItems: any[] = [];
  //   const visitedNodes = new Set<any>();

  //   // Recursively walk every node and inspect 'items'
  //   const extractRows = (node: any) => {
  //     if (!node || typeof node !== 'object' || visitedNodes.has(node)) return;
  //     visitedNodes.add(node);

  //     if (Array.isArray(node.items) && node.items.length > 0) {
  //       for (const element of node.items) {
  //         if (!element || typeof element !== 'object') continue;

  //         // If this element has nested items, traverse deeper (sub-cluster)
  //         if (Array.isArray(element.items) && element.items.length > 0) {
  //           extractRows(element);
  //         } else {
  //           // It is an actual statement line row
  //           allItems.push(element);
  //         }
  //       }
  //     }

  //     // Check other potential grouping arrays
  //     const otherGroupKeys = ['subclusters', 'children', 'groups', 'vendors'];
  //     for (const k of otherGroupKeys) {
  //       if (Array.isArray(node[k])) {
  //         node[k].forEach(extractRows);
  //       }
  //     }
  //   };

  //   clusters.forEach(extractRows);
  //   if (activePreviewCluster) {
  //     extractRows(activePreviewCluster);
  //   }

  //   console.log('🔍 [COLLECTED TRANSACTIONS TOTAL]:', allItems.length);
  //   if (allItems.length > 0) {
  //     console.log('🔍 [FIRST ROW SAMPLE]:', allItems[0]);
  //   }

  //   // Match collected rows against selectedTxnIds
  //   const matched = allItems.filter((item) => {
  //     const candidates = [
  //       item.id,
  //       item.row_identifier,
  //       item.staging_line_id,
  //       item.txn_id,
  //       item.statement_line_id,
  //       item.uuid,
  //       item.line_id,
  //     ]
  //       .filter((val) => val !== undefined && val !== null)
  //       .map(String);

  //     return selectedTxnIds.some((selectedId) =>
  //       candidates.includes(String(selectedId))
  //     );
  //   });

  //   console.log('🎯 [FINAL MATCHED ROWS]:', {
  //     selectedCount: selectedTxnIds.length,
  //     matchedCount: matched.length,
  //     matchedRows: matched,
  //   });

  //   return matched;
  // }, [clusters, activePreviewCluster, selectedTxnIds]);
  // 🎯 Zero crawling needed: Grab directly from selectedRowsMap
  const selectedTransactions = useMemo(() => {
    return Object.values(selectedRowsMap);
  }, [selectedRowsMap]);

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

  // const handleFinalReclassificationSubmit = async (
  //   chosenPatterns: string[]
  // ) => {
  //   if (selectedSummary.allTxnIds.length === 0) return;
  //   setSubmitting(true);

  //   try {
  //     const data = await applyReclassification({
  //       transaction_ids: selectedSummary.allTxnIds,
  //       target_category: selectedCategory,
  //       target_subcategory: selectedSubcategory,
  //       patterns: chosenPatterns,
  //       save_rule: saveRule && chosenPatterns.length > 0,
  //       entry_type: vectorType,
  //       upi_strategy: vectorType === 'Debit' ? upiStrategy : 'vendor',
  //       subledger_asset_id: selectedSubledgerFolioId || undefined,
  //     } as any);

  //     // If user selected a folio, bind transactions directly to it
  //     if (data?.status === 'success' && selectedSubledgerFolioId) {
  //       try {
  //         const selectedItems = clusters
  //           .flatMap((c) => (c as any).items || (c as any).transactions || [])
  //           .filter((item) =>
  //             selectedSummary.allTxnIds.includes(
  //               String(item.id || item.row_identifier)
  //             )
  //           );

  //         for (const item of selectedItems) {
  //           await subledgerApi.bindTransaction({
  //             asset_id: selectedSubledgerFolioId,
  //             row_identifier: item.row_identifier || item.id,
  //             transaction_date:
  //               item.transaction_date ||
  //               item.date ||
  //               new Date().toISOString().split('T')[0],
  //             amount: Number(item.debit || item.credit || item.amount || 0),
  //             transaction_purpose: 'OPERATING_SPEND',
  //             user_note: `Classified & Bound via Workbench (${selectedSubcategory})`,
  //           });
  //         }
  //         clearSubledgerBreakdownCache(selectedSubcategory);
  //       } catch (bindErr) {
  //         console.error('Folio direct auto-binding failed:', bindErr);
  //       }
  //     }

  //     if (data?.status === 'success') {
  //       setIsPatternModalOpen(false);
  //       setSelectedTxnIds([]);
  //       setSelectedSubledgerFolioId('');
  //       await loadClusters(targetSubcategory, accountId, searchQuery);
  //       onSuccess();
  //     }
  //   } catch (err) {
  //     console.error('Failed to apply reclassification:', err);
  //   } finally {
  //     setSubmitting(false);
  //   }
  // };

  const handleFinalReclassificationSubmit = async (
    chosenPatterns: string[]
  ) => {
    if (selectedSummary.allTxnIds.length === 0) return;
    setSubmitting(true);

    try {
      const appliedTxnIds = [...selectedSummary.allTxnIds];

      // 🛡️ Resolve clean identifier if composite string was provided (e.g. "[EXP-SUNH-008] SUN MEDANATA MMC")
      let folioIdToBind = selectedSubledgerFolioId;
      const bracketMatch = folioIdToBind?.match(/\[(.*?)\]/);
      const cleanFolioCode = bracketMatch
        ? bracketMatch[1].trim()
        : folioIdToBind;

      const data = await applyReclassification({
        transaction_ids: appliedTxnIds,
        target_category: selectedCategory,
        target_subcategory: selectedSubcategory,
        patterns: chosenPatterns,
        save_rule: saveRule && chosenPatterns.length > 0,
        entry_type: vectorType,
        upi_strategy: vectorType === 'Debit' ? upiStrategy : 'vendor',
        subledger_asset_id: folioIdToBind || undefined,
      } as any);

      let boundAssetMeta: {
        id?: string;
        asset_code?: string;
        name?: string;
      } | null = null;

      if (data?.status === 'success' && folioIdToBind) {
        try {
          const selectedItems = clusters
            .flatMap((c) => (c as any).items || (c as any).transactions || [])
            .filter((item) =>
              appliedTxnIds.includes(String(item.id || item.row_identifier))
            );

          // Fetch asset info for immediate optimistic badge display
          try {
            // If backend returns the verified UUID or asset code in response
            const targetIdForLookup =
              data.subledger_asset_id || data.asset_id || folioIdToBind;
            const assetObj = await subledgerApi.getAssetById(targetIdForLookup);
            boundAssetMeta = assetObj;
          } catch {
            boundAssetMeta = {
              id: folioIdToBind,
              asset_code: cleanFolioCode || 'FLT',
            };
          }

          // If backend already bound it in apply_reclassification_and_learn, skip manual re-bind
          if (!data.subledger_bound) {
            for (const item of selectedItems) {
              await subledgerApi.bindTransaction({
                asset_id: boundAssetMeta?.id || folioIdToBind,
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

        // 🎯 Dispatch in-place update so the row stays and turns green!
        if (boundAssetMeta) {
          setLastAppliedMapping({
            txnIds: appliedTxnIds,
            asset_id: boundAssetMeta.id,
            asset_code: boundAssetMeta.asset_code,
            asset_name: boundAssetMeta.name,
          });
        } else {
          // Only reload if we didn't map in-place
          await loadClusters(targetSubcategory, accountId, searchQuery);
        }

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
      lastAppliedMapping,
      selectedTransactions,
    },
    actions: {
      setSearchQuery,
      handleSelectCluster,
      toggleIndividualTxn,
      toggleClusterTxns,
      toggleSelectAllVisible,
      clearAllSelections: () => {
        setSelectedTxnIds([]);
        setSelectedRowsMap({});
      },
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
