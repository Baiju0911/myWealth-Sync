// webapp/src/hooks/useCandidateMatching.ts
import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  subledgerApi,
  type CandidateMatchResult,
  type AssetComplianceSchedule,
  type AssetSubLedgerNode,
  type AssetOperationalAccount,
} from '../api/subledger';
import {
  toIsoDateString,
  cleanVendorKeyword,
  extractVendorTokenFromNode,
  resolveCandidateNarration,
} from '../utils/classificationHelpers';
import {
  transformWorkbenchRowsToCandidates,
  deduplicateAndAnnotateCandidates,
} from '../components/subledger/candidatematcher/candidateMatchingUtils';
import type { TaxonomyMatchContext } from '../components/subledger/CandidateMatcherModal';

interface UseCandidateMatchingProps {
  isOpen: boolean;
  asset?: AssetSubLedgerNode | null;
  accountId?: number | string | null;
  taxonomyContext?: TaxonomyMatchContext | null;
  schedule?: AssetComplianceSchedule | null;
  utility?: AssetOperationalAccount | null;
  onSuccess: () => void;
  onClose: () => void;
}

export function useCandidateMatching({
  isOpen,
  asset,
  accountId,
  taxonomyContext,
  schedule,
  utility,
  onSuccess,
  onClose,
}: UseCandidateMatchingProps) {
  const [documentDate, setDocumentDate] = useState<string>('');
  const [targetAmount, setTargetAmount] = useState<number | string>('');
  const [keywords, setKeywords] = useState<string>('');
  const [dayWindow, setDayWindow] = useState<number>(1825);
  const [syncAcquisitionCost, setSyncAcquisitionCost] = useState<boolean>(true);

  const [loading, setLoading] = useState<boolean>(false);
  const [binding, setBinding] = useState<boolean>(false);

  const [workbenchCandidates, setWorkbenchCandidates] = useState<
    CandidateMatchResult[]
  >([]);
  const [scannedCandidates, setScannedCandidates] = useState<
    CandidateMatchResult[]
  >([]);

  const [selectedRowIds, setSelectedRowIds] = useState<string[]>([]);
  const [locallyBoundMap, setLocallyBoundMap] = useState<Map<string, string>>(
    new Map()
  );
  const [globalBoundMap, setGlobalBoundMap] = useState<Map<string, any>>(
    new Map()
  );

  const [isCash, setIsCash] = useState<boolean>(false);
  const [userNote, setUserNote] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  const [availableNodes, setAvailableNodes] = useState<AssetSubLedgerNode[]>(
    []
  );
  const [selectedBindingAsset, setSelectedBindingAsset] =
    useState<AssetSubLedgerNode | null>(asset || null);

  const activeSubcategory = useMemo(() => {
    return (
      taxonomyContext?.subcategory?.trim() ||
      (asset?.linked_gl_account ? String(asset.linked_gl_account).trim() : null)
    );
  }, [taxonomyContext?.subcategory, asset?.linked_gl_account]);

  const extractSpecificTerm = useCallback(
    (targetNode?: AssetSubLedgerNode | null) => {
      const node = targetNode || asset;
      const extracted = extractVendorTokenFromNode(node);
      if (extracted) return extracted;

      if (taxonomyContext?.defaultKeyword && !targetNode) {
        return cleanVendorKeyword(taxonomyContext.defaultKeyword);
      }
      if (utility?.matching_keyword) {
        return cleanVendorKeyword(utility.matching_keyword);
      }
      return '';
    },
    [taxonomyContext?.defaultKeyword, utility?.matching_keyword, asset]
  );

  const fetchMappedTransactions = useCallback(
    async (assetId: string | number) => {
      try {
        const res = await subledgerApi.getMappedTransactions(assetId);
        const list = res?.mapped_transactions || [];

        const mappedMap = new Map<string, string>();
        const mappedCandidateRows: CandidateMatchResult[] = [];

        list.forEach((m: any) => {
          const rowId = m.row_identifier ? String(m.row_identifier) : '';
          const journalId =
            m.journal_id || m.id ? String(m.journal_id || m.id) : '';

          if (m.mapping_id) {
            if (rowId) mappedMap.set(rowId, String(m.mapping_id));
            if (journalId) mappedMap.set(journalId, String(m.mapping_id));
          }

          mappedCandidateRows.push({
            account_id: Number(m.account_id || 0),
            row_identifier: rowId || journalId,
            journal_id: journalId,
            transaction_date: toIsoDateString(m.transaction_date || m.date),
            debit: Number(m.amount || m.debit || 0),
            credit: Number(m.credit || 0),
            remarks: resolveCandidateNarration(
              m.remarks,
              m.narration || m.description || ''
            ),
            probability_score: 100,
            date_offset_days: 0,
            amount_difference: 0,
            is_mapped: true,
            is_mapped_to_this_asset: true,
            mapping_info: {
              mapping_id: String(m.mapping_id),
              asset_id: String(assetId),
              asset_code: m.asset_code,
              asset_name: m.asset_name,
              vendor_name: m.vendor_name,
            },
          } as CandidateMatchResult);
        });

        setLocallyBoundMap(mappedMap);
        setScannedCandidates((prev) => [...mappedCandidateRows, ...prev]);
        return mappedMap;
      } catch (err) {
        console.error('Failed to fetch mapped transactions for asset:', err);
        setLocallyBoundMap(new Map());
        return new Map<string, string>();
      }
    },
    []
  );

  const checkCandidateMappings = useCallback(
    async (candidateList: CandidateMatchResult[]) => {
      const keysToSend = new Set<string>();
      candidateList.forEach((c) => {
        if (c.row_identifier) keysToSend.add(String(c.row_identifier));
        if (c.journal_id) keysToSend.add(String(c.journal_id));
      });

      if (keysToSend.size === 0) return;

      try {
        const res = await subledgerApi.checkMappedRows({
          row_identifiers: Array.from(keysToSend),
        });
        const incomingMap = res?.mapped_map || {};

        setGlobalBoundMap((prev) => {
          const incomingKeys = Object.keys(incomingMap);
          if (prev.size === incomingKeys.length) {
            let identical = true;
            for (const key of incomingKeys) {
              if (prev.get(key)?.mapping_id !== incomingMap[key]?.mapping_id) {
                identical = false;
                break;
              }
            }
            if (identical) return prev;
          }

          const nextMap = new Map<string, any>();
          Object.entries(incomingMap).forEach(([key, info]) => {
            nextMap.set(key, info);
          });
          return nextMap;
        });
      } catch (err) {
        console.error('Failed to check mapped rows:', err);
      }
    },
    []
  );

  const displayedNodes = useMemo(() => {
    if (!asset) return availableNodes;
    const targetVendor = extractVendorTokenFromNode(asset).toLowerCase();
    if (!targetVendor) return availableNodes;

    return availableNodes.filter((n) => {
      const v = extractVendorTokenFromNode(n).toLowerCase();
      return (
        (v && (v.includes(targetVendor) || targetVendor.includes(v))) ||
        String(n.id) === String(asset.id)
      );
    });
  }, [availableNodes, asset]);

  const candidates = useMemo(() => {
    return deduplicateAndAnnotateCandidates(
      workbenchCandidates,
      scannedCandidates,
      selectedBindingAsset || asset,
      locallyBoundMap,
      globalBoundMap
    );
  }, [
    workbenchCandidates,
    scannedCandidates,
    selectedBindingAsset,
    asset,
    locallyBoundMap,
    globalBoundMap,
  ]);

  const unmappedCandidates = useMemo(
    () => candidates.filter((c) => !c.is_mapped && !c.is_mapped_to_this_asset),
    [candidates]
  );

  useEffect(() => {
    const rawPool = [...workbenchCandidates, ...scannedCandidates];
    if (rawPool.length > 0) {
      checkCandidateMappings(rawPool);
    }
  }, [
    workbenchCandidates.length,
    scannedCandidates.length,
    checkCandidateMappings,
  ]);

  useEffect(() => {
    if (selectedRowIds.length > 0) {
      const allowedUnmappedKeys = new Set(
        unmappedCandidates.map((c) => c.row_identifier)
      );
      setSelectedRowIds((prev) => {
        const sanitized = prev.filter((id) => allowedUnmappedKeys.has(id));
        return sanitized.length !== prev.length ? sanitized : prev;
      });
    }
  }, [unmappedCandidates, selectedRowIds.length]);

  const runScan = async (
    targetAssetId: string | null | undefined,
    docDate: string,
    amt: number | string,
    kwString: string,
    windowDays: number,
    bankHint?: string
  ) => {
    setLoading(true);
    setError(null);

    const formattedDate = toIsoDateString(docDate);
    const kwArray = kwString
      ? kwString
          .split(',')
          .map((k) => cleanVendorKeyword(k))
          .filter(Boolean)
      : [];
    const parsedAmount = Number(amt);
    const cleanAmount =
      !isNaN(parsedAmount) && parsedAmount > 0 ? parsedAmount : null;

    try {
      const payload: any = {
        document_date: formattedDate,
        target_amount: cleanAmount,
        day_window: windowDays,
        keywords: kwArray,
        account_id: accountId ? Number(accountId) : undefined,
      };

      if (bankHint !== undefined && bankHint !== '') {
        payload.bank_account_hint = bankHint;
      }

      if (targetAssetId) {
        payload.asset_id = targetAssetId;
        fetchMappedTransactions(targetAssetId);
      } else if (activeSubcategory) {
        payload.subcategory = activeSubcategory;
      }

      const response = await subledgerApi.findCandidates(payload);
      setScannedCandidates(response.candidates || []);
    } catch (err: any) {
      console.error('Candidate fetch failed:', err.response?.data || err);
      setError('Failed to fetch matching candidate rows from staging.');
      setScannedCandidates([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isOpen) return;

    let isMounted = true;
    const activeNodeId = asset?.id || (asset as any)?.asset_id;
    if (activeNodeId) {
      fetchMappedTransactions(activeNodeId);
    }

    const initialDate = toIsoDateString(
      schedule?.due_date ||
        asset?.acquisition_date ||
        taxonomyContext?.transactionDate
    );

    const initialAmount =
      schedule?.expected_amount || taxonomyContext?.defaultAmount || '';

    // Check if asset is a cash float to suppress defaulting to generic vendor strings
    const isCashAsset =
      String(asset?.category || '')
        .toUpperCase()
        .includes('CASH') ||
      String(asset?.category || '')
        .toUpperCase()
        .includes('FLOAT') ||
      String(asset?.linked_gl_account || '')
        .toLowerCase()
        .includes('cash');

    const initialKeywords = isCashAsset
      ? ''
      : asset
        ? extractSpecificTerm(asset) ||
          cleanVendorKeyword(taxonomyContext?.defaultKeyword || '')
        : '';

    const existingAssetNote =
      (asset as any)?.user_note || asset?.metadata_payload?.user_note || '';

    setDocumentDate(initialDate);
    setTargetAmount(initialAmount);
    setKeywords(initialKeywords);
    setUserNote(existingAssetNote);
    setError(null);
    setIsCash(false);
    setSyncAcquisitionCost(true);
    setDayWindow(1825);

    const rawStaged = taxonomyContext?.stagedItems || [];
    const hasWorkbenchPool = rawStaged.length > 0;

    if (hasWorkbenchPool) {
      const mappedStaged = transformWorkbenchRowsToCandidates(
        rawStaged,
        asset || null,
        accountId
      );
      setWorkbenchCandidates(mappedStaged);
      setSelectedRowIds([]);
    } else {
      setWorkbenchCandidates([]);
    }

    if (activeSubcategory) {
      subledgerApi
        .getAssets(activeSubcategory)
        .then((nodes) => {
          if (!isMounted) return;
          setAvailableNodes(nodes);

          const activeNode = asset
            ? nodes.find(
                (n) =>
                  String(n.id) === String(asset.id || (asset as any).asset_id)
              ) || asset
            : null;

          setSelectedBindingAsset((prev) => prev || activeNode);

          if (!hasWorkbenchPool && activeNode?.id) {
            runScan(
              activeNode.id,
              initialDate,
              initialAmount,
              initialKeywords,
              1825
            );
          }
        })
        .catch((err) => {
          console.error('Failed to load asset nodes:', err);
          if (!hasWorkbenchPool && asset?.id) {
            runScan(
              asset.id,
              initialDate,
              initialAmount,
              initialKeywords,
              1825
            );
          }
        });
    } else if (!hasWorkbenchPool && asset?.id) {
      runScan(asset.id, initialDate, initialAmount, initialKeywords, 1825);
    }

    return () => {
      isMounted = false;
    };
  }, [
    isOpen,
    asset?.id,
    activeSubcategory,
    taxonomyContext?.stagedItems?.length,
    taxonomyContext?.defaultKeyword,
    taxonomyContext?.defaultAmount,
    extractSpecificTerm,
    fetchMappedTransactions,
    accountId,
  ]);

  const handleFolioChange = (targetNodeId: string) => {
    setLocallyBoundMap(new Map());

    if (!targetNodeId) {
      setSelectedBindingAsset(null);
      setKeywords('');
      return;
    }

    const found =
      availableNodes.find((n) => String(n.id) === targetNodeId) || null;
    setSelectedBindingAsset(found);

    if (found?.id) {
      fetchMappedTransactions(found.id);
    }

    const isCashTarget =
      String(found?.category || '')
        .toUpperCase()
        .includes('CASH') ||
      String(found?.linked_gl_account || '')
        .toLowerCase()
        .includes('cash');

    const newKw = isCashTarget ? '' : found ? extractSpecificTerm(found) : '';
    setKeywords(newKw);

    const rawStaged = taxonomyContext?.stagedItems || [];
    if (rawStaged.length === 0) {
      runScan(found?.id, documentDate, targetAmount, newKw, dayWindow);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    runScan(
      selectedBindingAsset?.id,
      documentDate,
      targetAmount,
      keywords,
      dayWindow
    );
  };

  const handleUnmap = async (cand: CandidateMatchResult) => {
    if (!cand.mapping_info?.mapping_id) return;
    setBinding(true);
    setError(null);

    try {
      await subledgerApi.unmapTransaction({
        mapping_id: cand.mapping_info.mapping_id,
      });

      const removeKey = (prev: Map<string, any>) => {
        const next = new Map(prev);
        if (cand.row_identifier) next.delete(String(cand.row_identifier));
        if (cand.journal_id) next.delete(String(cand.journal_id));
        return next;
      };

      setLocallyBoundMap(removeKey);
      setGlobalBoundMap(removeKey);

      const unmapList = (list: CandidateMatchResult[]) =>
        list.map((c) =>
          c.row_identifier === cand.row_identifier
            ? {
                ...c,
                is_mapped: false,
                is_mapped_to_this_asset: false,
                mapping_info: null,
              }
            : c
        );

      setWorkbenchCandidates(unmapList);
      setScannedCandidates(unmapList);
      onSuccess();
    } catch (err: any) {
      console.error('Unmapping failed:', err);
      setError('Failed to unmap transaction.');
    } finally {
      setBinding(false);
    }
  };

  const handleSaveAndSync = async () => {
    if (!selectedBindingAsset) {
      setError('Please select a target folio before saving updates.');
      return;
    }
    setBinding(true);
    setError(null);
    try {
      const finalAmount = Number(targetAmount) || 0;
      await subledgerApi.updateAsset(selectedBindingAsset.id, {
        acquisition_cost:
          syncAcquisitionCost && finalAmount > 0
            ? finalAmount
            : selectedBindingAsset.acquisition_cost,
        current_valuation:
          syncAcquisitionCost && finalAmount > 0
            ? finalAmount
            : selectedBindingAsset.current_valuation,
        user_note: userNote.trim(),
      });
      onSuccess();
      onClose();
    } catch (err) {
      console.error('Failed to update asset baseline:', err);
      setError('Failed to save reconciliation updates.');
    } finally {
      setBinding(false);
    }
  };

  const toggleSelectRow = (rowId: string) => {
    setSelectedRowIds((prev) =>
      prev.includes(rowId)
        ? prev.filter((id) => id !== rowId)
        : [...prev, rowId]
    );
  };

  const toggleSelectAll = () => {
    if (selectedRowIds.length === unmappedCandidates.length) {
      setSelectedRowIds([]);
    } else {
      setSelectedRowIds(unmappedCandidates.map((c) => c.row_identifier));
    }
  };

  const selectedTotalSum = useMemo(
    () =>
      unmappedCandidates
        .filter((c) => selectedRowIds.includes(c.row_identifier))
        .reduce((acc, curr) => acc + Number(curr.debit || curr.credit || 0), 0),
    [unmappedCandidates, selectedRowIds]
  );

  const handleBatchBind = async (targetCandidate?: CandidateMatchResult) => {
    let targetAsset = selectedBindingAsset;

    if (!targetAsset && !isCash) {
      if (displayedNodes.length > 0) {
        targetAsset = displayedNodes[0];
        setSelectedBindingAsset(targetAsset);
      } else {
        setError(
          'Please select a Target Folio from the dropdown before binding.'
        );
        return;
      }
    }

    setBinding(true);
    setError(null);

    const rowsToBind = targetCandidate
      ? [targetCandidate]
      : candidates.filter((c) => selectedRowIds.includes(c.row_identifier));

    if (rowsToBind.length === 0 && !isCash) {
      setError('Please select at least one candidate row to bind.');
      setBinding(false);
      return;
    }

    try {
      const newlyBoundMap = new Map<string, string>();

      for (const cand of rowsToBind) {
        const formattedDate = toIsoDateString(
          cand?.transaction_date || documentDate
        );
        const finalAmount = cand
          ? Number(cand.debit || cand.credit || 0)
          : Number(targetAmount) || 0;

        const res: any = await subledgerApi.bindTransaction({
          asset_id: targetAsset!.id,
          schedule_id: schedule?.id || null,
          operational_account_id:
            utility?.id || targetAsset!.operational_accounts?.[0]?.id || null,
          row_identifier: isCash ? null : cand.row_identifier,
          is_cash_entry: isCash,
          transaction_date: formattedDate,
          amount: finalAmount,
          transaction_purpose: schedule?.schedule_type || 'SUB_LEDGER_PAYMENT',
          user_note: userNote || `Reconciled via Candidate Matcher UI`,
          sync_acquisition_cost: syncAcquisitionCost,
        });

        if (cand?.row_identifier && res?.mapping_id) {
          newlyBoundMap.set(
            String(cand.row_identifier),
            String(res.mapping_id)
          );
        }
      }

      setLocallyBoundMap((prev) => {
        const next = new Map(prev);
        newlyBoundMap.forEach((v, k) => next.set(k, v));
        return next;
      });

      const markBound = (list: CandidateMatchResult[]) =>
        list.map((c) => {
          if (newlyBoundMap.has(c.row_identifier)) {
            const mId = newlyBoundMap.get(c.row_identifier)!;
            return {
              ...c,
              is_mapped: true,
              is_mapped_to_this_asset: true,
              mapping_info: {
                mapping_id: mId,
                asset_id: targetAsset!.id,
                asset_code: targetAsset!.asset_code,
                asset_name: targetAsset!.name,
              },
            };
          }
          return c;
        });

      setWorkbenchCandidates(markBound);
      setScannedCandidates(markBound);
      setSelectedRowIds((prev) => prev.filter((id) => !newlyBoundMap.has(id)));

      onSuccess();
      if (!targetCandidate) {
        onClose();
      }
    } catch (err: any) {
      console.error('Binding failed:', err.response?.data || err);
      setError('Failed to bind transaction(s). Please check server logs.');
    } finally {
      setBinding(false);
    }
  };

  return {
    documentDate,
    setDocumentDate,
    targetAmount,
    setTargetAmount,
    keywords,
    setKeywords,
    dayWindow,
    setDayWindow,
    syncAcquisitionCost,
    setSyncAcquisitionCost,
    loading,
    binding,
    candidates,
    unmappedCandidates,
    selectedRowIds,
    isCash,
    setIsCash,
    userNote,
    setUserNote,
    error,
    displayedNodes,
    selectedBindingAsset,
    selectedTotalSum,
    handleFolioChange,
    handleSearchSubmit,
    handleUnmap,
    handleSaveAndSync,
    toggleSelectRow,
    toggleSelectAll,
    handleBatchBind,
    runScan,
  };
}
