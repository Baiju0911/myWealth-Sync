// webapp/src/components/Stage3/Workbench/TaxonomyMapperPanel.tsx
import React, { useEffect, useMemo, useState } from 'react';
import type { TaxonomyOption, ExtendedCluster, Cluster, SuggestedRule } from '../../../api/api';
import { subledgerApi, type SubcategoryBreakdownResponse, type AssetSubLedgerNode } from '../../../api/subledger';
import { inrFormatter } from '../../../utils/classificationHelpers';
import { Lightbulb, Plus, ArrowLeft, Layers, ExternalLink, ShieldCheck, Loader2, Wallet } from 'lucide-react';
import type { TaxonomyMatchContext } from '../../../components/subledger/CandidateMatcherModal';

interface Props {
  targetSubcategoryContext?: string;
  selectedSummary: { totalTxns: number; totalAmount: number; allTxnIds: string[] };
  activePreviewCluster: ExtendedCluster | Cluster | null;
  taxonomyTree: TaxonomyOption[];
  availableSubcategories: string[];
  selectedCategory: string;
  setSelectedCategory: (cat: string) => void;
  selectedSubcategory: string;
  setSelectedSubcategory: (sub: string) => void;
  isCreatingNew: boolean;
  setIsCreatingNew: (val: boolean) => void;
  newCatInput: string;
  setNewCatInput: (v: string) => void;
  newSubInput: string;
  setNewSubInput: (v: string) => void;
  savingNewTaxonomy: boolean;
  handleCreateTaxonomy: () => void;
  saveRule: boolean;
  setSaveRule: (val: boolean) => void;
  upiStrategy: 'vendor' | 'auto_consolidate';
  setUpiStrategy: (val: 'vendor' | 'auto_consolidate') => void;
  vectorType: 'Debit' | 'Credit';
  submitting: boolean;
  handleApplyClassification: (targetAssetId?: string) => void;
  onClose: () => void;
  suggestedRule?: SuggestedRule | null;
  subledgerCapableSet?: Set<string>;
  onOpenSubledgerDrawer?: (subcategory: string, matchContext?: TaxonomyMatchContext) => void;
  onOpenNewFolioModal?: (subcategory: string) => void;
}

const ROOT_ACCOUNT_CLASSES = ['Asset', 'Expense', 'Income', 'Liability', 'Transfer'] as const;

const subledgerBreakdownCache = new Map<string, SubcategoryBreakdownResponse>();

export const clearSubledgerBreakdownCache = (subcategory?: string) => {
  if (subcategory) {
    subledgerBreakdownCache.delete(subcategory);
  } else {
    subledgerBreakdownCache.clear();
  }
};

export const TaxonomyMapperPanel: React.FC<Props> = ({
  targetSubcategoryContext,
  selectedSummary,
  activePreviewCluster,
  taxonomyTree,
  availableSubcategories,
  selectedCategory,
  setSelectedCategory,
  selectedSubcategory,
  setSelectedSubcategory,
  isCreatingNew,
  setIsCreatingNew,
  newCatInput,
  setNewCatInput,
  newSubInput,
  setNewSubInput,
  savingNewTaxonomy,
  handleCreateTaxonomy,
  saveRule,
  setSaveRule,
  upiStrategy,
  setUpiStrategy,
  vectorType,
  submitting,
  handleApplyClassification,
  onClose,
  suggestedRule = null,
  subledgerCapableSet = new Set([
    'Suspense Account',
    'Gold & Precious Metals',
    'ShareMarket & Mutual Funds',
    'Real Estate',
    'Fixed Deposits',
    'Insurance Assets',
    'Loans & Advances',
    'Sundry Debtors',
    'Sundry Creditors',
  ]),
  onOpenSubledgerDrawer,
  onOpenNewFolioModal,
}) => {
  const [subledgerInfo, setSubledgerInfo] = useState<SubcategoryBreakdownResponse | null>(null);
  const [loadingSubledgerInfo, setLoadingSubledgerInfo] = useState<boolean>(false);
  const [selectedFolioId, setSelectedFolioId] = useState<string>('');

  // 🎯 Fetch all active cash float folios so you can attribute expenses to them
  const [allCashFolios, setAllCashFolios] = useState<AssetSubLedgerNode[]>([]);

  useEffect(() => {
    subledgerApi
      .getAssets()
      .then((assets) => {
        const cashFolios = assets.filter((a: any) => {
          const cat = String(a.category || '').toUpperCase();
          const gl = String(a.linked_gl_account || '').toLowerCase();
          return cat.includes('CASH') || cat.includes('FLOAT') || gl.includes('cash') || gl.includes('float');
        });
        setAllCashFolios(cashFolios);
      })
      .catch((err) => console.error('Failed to load cash folios for attribution:', err));
  }, []);

  useEffect(() => {
    if (activePreviewCluster?.pattern) {
      const cleanPattern = activePreviewCluster.pattern.replace(/^#+/, '');
      if (!['YESB', 'SBIN', 'HDFC', 'ICIC', 'PAYTM'].includes(cleanPattern.toUpperCase())) {
        setUpiStrategy('vendor');
      }
    }
  }, [activePreviewCluster, setUpiStrategy]);

  const isUpiSelection = (cluster: ExtendedCluster | Cluster | null, items: any[] = []): boolean => {
    if (cluster?.pattern) {
      const pattern = cluster.pattern.toUpperCase();
      if (pattern.includes('UPI') || pattern.includes('PAYTM') || pattern.includes('YBL')) return true;
    }
    if (items && items.length > 0) {
      return items.some((item) => {
        const narration = (item.narration || '').toUpperCase();
        return narration.startsWith('UPI/') || narration.includes('/UPI/') || narration.includes('@');
      });
    }
    return false;
  };

  const handleSelectRootClass = (categoryName: string) => {
    setSelectedCategory(categoryName);
    setSelectedFolioId('');

    const foundNode = (taxonomyTree || []).find(
      (t) => String(t?.category).toLowerCase() === categoryName.toLowerCase()
    );

    if (foundNode && Array.isArray(foundNode.subcategories) && foundNode.subcategories.length > 0) {
      const subNames = foundNode.subcategories
        .map((sub: any) =>
          typeof sub === 'object' && sub !== null
            ? String(sub.subcategory || sub.name || sub.title || '')
            : String(sub || '')
        )
        .filter(Boolean);

      if (targetSubcategoryContext && subNames.includes(targetSubcategoryContext)) {
        setSelectedSubcategory(targetSubcategoryContext);
        return;
      }

      if (selectedSubcategory && subNames.includes(selectedSubcategory)) {
        setSelectedSubcategory(selectedSubcategory);
        return;
      }

      setSelectedSubcategory(subNames[0] || '');
    } else {
      setSelectedSubcategory('');
    }
  };

  const activeHeaderMetadata = useMemo(() => {
    const foundCat = (taxonomyTree || []).find(
      (t) => String(t?.category).toLowerCase() === selectedCategory.toLowerCase()
    );
    if (!foundCat || !Array.isArray(foundCat.subcategories)) return null;

    const matchedItem: any = foundCat.subcategories.find((sub: any) => {
      const name =
        typeof sub === 'object' && sub !== null
          ? String(sub.subcategory || sub.name || '')
          : String(sub || '');
      return name.toLowerCase() === selectedSubcategory.toLowerCase();
    });

    const isCapable =
      Boolean(matchedItem?.is_subledger_capable) || subledgerCapableSet.has(selectedSubcategory);

    if (typeof matchedItem === 'object' && matchedItem !== null) {
      return {
        header: matchedItem.header || matchedItem.group || matchedItem.parent_header || selectedCategory,
        isSubledgerCapable: isCapable,
        code: matchedItem.code || matchedItem.account_code || null,
      };
    }

    return {
      header: selectedCategory,
      isSubledgerCapable: isCapable,
      code: null,
    };
  }, [taxonomyTree, selectedCategory, selectedSubcategory, subledgerCapableSet]);

  const isSubledgerTarget = useMemo(() => {
    return (
      Boolean(activeHeaderMetadata?.isSubledgerCapable) &&
      selectedSubcategory !== 'Suspense Account'
    );
  }, [activeHeaderMetadata, selectedSubcategory]);

  const lastFetchedSubcategoryRef = React.useRef<string | null>(null);

  useEffect(() => {
    if (!isSubledgerTarget || !selectedSubcategory) {
      setSubledgerInfo(null);
      setSelectedFolioId('');
      lastFetchedSubcategoryRef.current = null;
      return;
    }

    if (lastFetchedSubcategoryRef.current === selectedSubcategory && subledgerInfo) {
      return;
    }

    if (subledgerBreakdownCache.has(selectedSubcategory)) {
      const cachedData = subledgerBreakdownCache.get(selectedSubcategory)!;
      setSubledgerInfo(cachedData);
      lastFetchedSubcategoryRef.current = selectedSubcategory;
      return;
    }

    let isMounted = true;
    lastFetchedSubcategoryRef.current = selectedSubcategory;
    setLoadingSubledgerInfo(true);

    subledgerApi
      .getSubcategoryBreakdown(selectedSubcategory)
      .then((data) => {
        if (isMounted) {
          subledgerBreakdownCache.set(selectedSubcategory, data);
          setSubledgerInfo(data);
        }
      })
      .catch(() => {
        if (isMounted) {
          setSubledgerInfo(null);
          lastFetchedSubcategoryRef.current = null;
        }
      })
      .finally(() => {
        if (isMounted) setLoadingSubledgerInfo(false);
      });

    return () => {
      isMounted = false;
    };
  }, [selectedSubcategory, isSubledgerTarget, subledgerInfo]);

  const buildContextualBridge = (): TaxonomyMatchContext => {
    let cleanKw = '';
    let txnDate = '';
    let rowId = '';

    if (activePreviewCluster) {
      const firstItem = (activePreviewCluster as any).items?.[0];
      if (firstItem) {
        cleanKw = firstItem.payee || firstItem.narration || '';
        txnDate = firstItem.transaction_date || firstItem.date || '';
        rowId = firstItem.row_identifier || firstItem.id || '';
      }

      if (!cleanKw && activePreviewCluster.pattern) {
        cleanKw = activePreviewCluster.pattern.replace(/^#+/, '').replace(/_/g, ' ');
      }
    }

    cleanKw = cleanKw
      .replace(/TRANSFER:\s*TO\s*DEPOSIT\s*\d*/gi, '')
      .replace(/TRANSFER:\s*TO/gi, '')
      .replace(/NEFT|RTGS|IMPS|UPI/gi, '')
      .replace(/[/\\-]/g, ' ')
      .trim()
      .split(/\s+/)
      .slice(0, 3)
      .join(', ');

    return {
      category: selectedCategory,
      subcategory: selectedSubcategory,
      defaultAmount: selectedSummary.totalAmount || undefined,
      defaultKeyword: cleanKw || undefined,
      rowIdentifier: rowId || undefined,
      transactionDate: txnDate || undefined,
    };
  };

  const handleLaunchScanOutflows = () => {
    if (!onOpenSubledgerDrawer) return;
    const matchContext = buildContextualBridge();
    onOpenSubledgerDrawer(selectedSubcategory, matchContext);
  };

  return (
    <div className="w-[42%] flex flex-col justify-between p-5 bg-zinc-950 overflow-y-auto font-mono text-xs text-zinc-100 border-l border-zinc-800">
      <div className="flex flex-col gap-3.5">
        {/* Active Pattern Banner */}
        {activePreviewCluster ? (
          <div className="bg-zinc-900/80 border border-zinc-800 p-3 rounded-xl flex justify-between items-center">
            <div>
              <span className="text-[10px] text-zinc-500 uppercase font-bold block">
                Inspecting Pattern
              </span>
              <span className="text-xs font-bold text-amber-400 font-mono">
                #{(activePreviewCluster.pattern || 'UNCLASSIFIED').replace(/^#+/, '')}
              </span>
            </div>
            <span className="text-[10px] bg-zinc-800 text-zinc-300 px-2 py-1 rounded font-bold">
              {activePreviewCluster.count || activePreviewCluster.transaction_ids?.length || 0} Total Rows
            </span>
          </div>
        ) : (
          <div className="bg-zinc-900/40 border border-dashed border-zinc-800 p-3.5 rounded-xl text-center text-zinc-500 text-[11px]">
            👈 Select a cluster on the left to inspect patterns.
          </div>
        )}

        {/* Suggested Rule Pill */}
        {suggestedRule && (
          <div className="bg-indigo-950/40 border border-indigo-800/60 p-3 rounded-xl flex flex-col gap-1.5">
            <div className="flex justify-between items-center">
              <span className="text-[10px] text-indigo-400 font-bold uppercase flex items-center gap-1">
                <Lightbulb className="w-3.5 h-3.5" />
                <span>Suggested Rule</span>
              </span>
              <button
                type="button"
                onClick={() => {
                  const ruleAny = suggestedRule as any;
                  const cat = ruleAny.suggested_category || ruleAny.target_category || 'Expense';
                  const sub = ruleAny.suggested_subcategory || ruleAny.target_subcategory || '';
                  setSelectedCategory(cat);
                  setSelectedSubcategory(sub);
                }}
                className="bg-indigo-600 hover:bg-indigo-500 text-white px-2 py-0.5 rounded text-[10px] font-bold transition-colors cursor-pointer"
              >
                Apply Suggestion
              </button>
            </div>
            <span className="text-[11px] text-indigo-200">
              {(suggestedRule as any).suggested_category || (suggestedRule as any).target_category} ➔{' '}
              <strong className="text-white">
                {(suggestedRule as any).suggested_subcategory ||
                  (suggestedRule as any).target_subcategory}
              </strong>
            </span>
          </div>
        )}

        {/* Batch Selection Telemetry */}
        <div className="bg-zinc-900/60 border border-zinc-800 p-3 rounded-xl flex flex-col gap-1">
          <span className="text-[10px] text-zinc-500 uppercase font-bold">
            Batch Reclassification Selection
          </span>
          <div className="flex justify-between items-center">
            <span
              className={`text-xs font-bold ${
                selectedSummary.totalTxns > 0 ? 'text-amber-400' : 'text-zinc-500'
              }`}
            >
              {selectedSummary.totalTxns} Item{selectedSummary.totalTxns !== 1 ? 's' : ''} Selected
            </span>
            <span className="text-xs font-bold text-zinc-100 tabular-nums">
              {inrFormatter.format(selectedSummary?.totalAmount || 0)}
            </span>
          </div>
        </div>

        {/* Taxonomy Target Inputs */}
        <div className="flex flex-col gap-2.5">
          <div className="flex justify-between items-center border-b border-zinc-800 pb-1.5">
            <h3 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
              Assign Destination Node
            </h3>
            <button
              type="button"
              onClick={() => setIsCreatingNew(!isCreatingNew)}
              className="text-amber-400 hover:text-amber-300 text-[11px] font-bold flex items-center gap-1 cursor-pointer transition-colors"
            >
              {isCreatingNew ? (
                <>
                  <ArrowLeft className="w-3 h-3" /> Select Node
                </>
              ) : (
                <>
                  <Plus className="w-3 h-3" /> New Node
                </>
              )}
            </button>
          </div>

          {!isCreatingNew ? (
            <div className="space-y-3">
              {/* Root Account Class Pills */}
              <div className="space-y-1.5">
                <label className="text-[10px] text-zinc-500 uppercase font-bold block">
                  Root Account Class
                </label>
                <div className="grid grid-cols-5 gap-1 bg-zinc-950 p-1 rounded-lg border border-zinc-800">
                  {ROOT_ACCOUNT_CLASSES.map((cls) => {
                    const isSelected = selectedCategory.toLowerCase() === cls.toLowerCase();
                    return (
                      <button
                        key={cls}
                        type="button"
                        onClick={() => handleSelectRootClass(cls)}
                        className={`py-1 rounded text-center font-bold text-[10px] transition-all cursor-pointer ${
                          isSelected
                            ? 'bg-zinc-800 text-amber-400 border border-zinc-700 shadow-xs'
                            : 'text-zinc-500 hover:text-zinc-300'
                        }`}
                      >
                        {cls}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Subcategory Select */}
              <div className="space-y-1">
                <div className="flex justify-between items-center">
                  <label className="text-[10px] text-zinc-500 uppercase font-bold block">
                    Account Head ({selectedCategory})
                  </label>
                  <span className="text-[10px] text-zinc-500">
                    {(availableSubcategories || []).length} available
                  </span>
                </div>
                <select
                  value={typeof selectedSubcategory === 'string' ? selectedSubcategory : ''}
                  onChange={(e) => {
                    setSelectedSubcategory(e.target.value);
                    setSelectedFolioId('');
                  }}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-xs text-zinc-200 outline-none focus:border-amber-500/60 cursor-pointer shadow-inner"
                >
                  {(availableSubcategories || []).length === 0 ? (
                    <option value="" disabled>
                      No subcategories under {selectedCategory}
                    </option>
                  ) : (
                    (availableSubcategories || []).map((sub: any, subIdx: number) => {
                      const displayLabel =
                        typeof sub === 'object' && sub !== null
                          ? sub.subcategory || sub.name || sub.title || String(sub)
                          : String(sub || '');
                      if (!displayLabel) return null;
                      return (
                        <option key={`sub-opt-${subIdx}-${displayLabel}`} value={displayLabel}>
                          {displayLabel}
                        </option>
                      );
                    })
                  )}
                </select>
              </div>

              {/* 🎯 SUBLEDGER FOLIO ATTRIBUTION (WORKS FOR BOTH CAPITAL ASSETS & EXPENSES ON CASH FLOATS) */}
              <div className="bg-zinc-900/60 border border-emerald-500/30 rounded-xl p-3 space-y-2 mt-2">
                <div className="flex items-center justify-between">
                  <label className="text-[10px] font-bold text-emerald-400 uppercase flex items-center gap-1.5">
                    <Wallet className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Subledger Folio Attribution (Optional)</span>
                  </label>
                  {onOpenNewFolioModal && (
                    <button
                      type="button"
                      onClick={() => onOpenNewFolioModal(selectedSubcategory)}
                      className="text-[10px] text-cyan-400 hover:underline cursor-pointer"
                    >
                      + New Folio
                    </button>
                  )}
                </div>

                <select
                  value={selectedFolioId}
                  onChange={(e) => setSelectedFolioId(e.target.value)}
                  className="w-full bg-zinc-950 border border-emerald-500/40 rounded-lg px-2.5 py-1.5 text-[11px] text-emerald-300 font-bold outline-none focus:border-emerald-400 cursor-pointer"
                >
                  <option value="">-- Direct General Ledger (No Folio Deducted) --</option>
                  
                  {/* Category-specific folios (e.g. Real estate, Gold) */}
                  {subledgerInfo?.assets && subledgerInfo.assets.length > 0 && (
  <optgroup label={`${selectedSubcategory} Folios`}>
    {subledgerInfo.assets.map((ast: any) => {
      const assetKey = ast.asset_id || ast.id;
      return (
        <option key={assetKey} value={assetKey}>
          [{ast.asset_code}] {ast.name}
        </option>
      );
    })}
  </optgroup>
)}

                  {/* Cash Float Folios (Always available to attribute expenses) */}
                  {allCashFolios.length > 0 && (
  <optgroup label="Operating Floats & Cash Pools">
    {allCashFolios.map((folio: any) => {
      const folioKey = folio.asset_id || folio.id;
      return (
        <option key={folioKey} value={folioKey}>
          [{folio.asset_code}] {folio.name}
        </option>
      );
    })}
  </optgroup>
)}
                </select>

                <p className="text-[10px] text-zinc-400 leading-normal">
                  {selectedFolioId
                    ? `⚡ Reclassifies line to ${selectedSubcategory} AND binds outflow directly to this folio.`
                    : 'Filing as a normal General Ledger expense will not affect any cash float balance.'}
                </p>
              </div>

              {/* SUBLEDGER BRIDGE CARD */}
              {isSubledgerTarget && (
                <div className="bg-zinc-900/60 border border-cyan-800/50 rounded-xl p-3 space-y-2.5 mt-2 shadow-xs">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="p-1 rounded bg-cyan-950 border border-cyan-800 text-cyan-400">
                        <Layers className="w-3.5 h-3.5" />
                      </div>
                      <div>
                        <span className="text-[10px] font-bold text-cyan-400 uppercase tracking-wider block">
                          Subledger-Linked Account Head
                        </span>
                        <span className="text-[9px] text-zinc-400">
                          {selectedCategory} ➔ {selectedSubcategory}
                        </span>
                      </div>
                    </div>

                    {onOpenSubledgerDrawer && (
                      <button
                        type="button"
                        onClick={handleLaunchScanOutflows}
                        className="text-[10px] bg-cyan-950/90 hover:bg-cyan-900 border border-cyan-700 text-cyan-300 px-2.5 py-1 rounded flex items-center gap-1.5 font-bold transition-all cursor-pointer shadow-xs"
                        title="Open Subledger Operations Hub with contextual candidate search"
                      >
                        <span>Operations Hub</span>
                        <ExternalLink className="w-3 h-3 text-cyan-400" />
                      </button>
                    )}
                  </div>

                  <div className="bg-zinc-950/80 border border-zinc-800/80 rounded-lg p-2 flex items-center justify-between text-[10px]">
                    <div className="flex items-center gap-1.5 text-zinc-400">
                      <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                      <span>Registered Folios:</span>
                      {loadingSubledgerInfo ? (
                        <Loader2 className="w-3 h-3 text-cyan-400 animate-spin" />
                      ) : (
                        <strong className="text-zinc-200">
                          {subledgerInfo?.asset_count ?? subledgerInfo?.assets?.length ?? 0} Folios
                        </strong>
                      )}
                    </div>

                    {!loadingSubledgerInfo && subledgerInfo && (
                      <div className="text-zinc-500 font-sans text-[10px]">
                        Unmapped: <span className="text-amber-400 font-mono font-bold">{inrFormatter.format(subledgerInfo.unmapped_variance || 0)}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-zinc-900/80 border border-dashed border-amber-500/60 p-3 rounded-xl flex flex-col gap-2">
              <span className="text-[11px] text-amber-400 font-bold uppercase">
                New Taxonomy Entry
              </span>
              <input
                type="text"
                placeholder="Category (e.g., Asset)"
                value={newCatInput}
                onChange={(e) => setNewCatInput(e.target.value)}
                className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-2.5 py-1.5 text-xs text-zinc-100 outline-none focus:border-amber-500"
              />
              <input
                type="text"
                placeholder="Subcategory (e.g., Gold & Precious Metals)"
                value={newSubInput}
                onChange={(e) => setNewSubInput(e.target.value)}
                className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-2.5 py-1.5 text-xs text-zinc-100 outline-none focus:border-amber-500"
              />
              <button
                type="button"
                onClick={handleCreateTaxonomy}
                disabled={savingNewTaxonomy || !newCatInput.trim() || !newSubInput.trim()}
                className="py-1.5 rounded-lg text-xs font-bold bg-amber-500 hover:bg-amber-400 text-zinc-950 transition-colors disabled:opacity-50 cursor-pointer"
              >
                {savingNewTaxonomy ? 'Saving...' : 'Add & Select Node'}
              </button>
            </div>
          )}
        </div>

        {/* Learn Rules Toggle */}
        <div className="bg-zinc-900/60 border border-zinc-800 p-3 rounded-xl flex flex-col gap-2.5">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-xs font-bold text-zinc-200 block">
                Save to Classification Rules
              </span>
              <span className="text-[10px] text-zinc-500 block">
                Enables Node 99 Sweep Hub to auto-clear future matches
              </span>
            </div>
            <input
              type="checkbox"
              checked={saveRule}
              onChange={(e) => setSaveRule(e.target.checked)}
              className="w-4 h-4 accent-amber-500 cursor-pointer rounded"
            />
          </div>

          {saveRule &&
            vectorType === 'Debit' &&
            selectedSummary.totalTxns > 0 &&
            isUpiSelection(activePreviewCluster, (activePreviewCluster as any)?.items) && (
              <div className="border-t border-zinc-800 pt-2 flex flex-col gap-1.5">
                <span className="text-[10px] text-zinc-400 font-bold uppercase">
                  UPI Rule Matching Strategy
                </span>
                <label className="flex items-center gap-2 text-[11px] text-zinc-300 cursor-pointer">
                  <input
                    type="radio"
                    name="upiStrategy"
                    value="auto_consolidate"
                    checked={upiStrategy === 'auto_consolidate'}
                    onChange={() => setUpiStrategy('auto_consolidate')}
                    className="accent-amber-500"
                  />
                  <span>⚡ Auto-Consolidate as UPI Merchant (Apply Normalizer)</span>
                </label>
                <label className="flex items-center gap-2 text-[11px] text-zinc-300 cursor-pointer">
                  <input
                    type="radio"
                    name="upiStrategy"
                    value="vendor"
                    checked={upiStrategy === 'vendor'}
                    onChange={() => setUpiStrategy('vendor')}
                    className="accent-amber-500"
                  />
                  <span>🏷️ Anchor to Clean Vendor Name Only</span>
                </label>
              </div>
            )}
        </div>
      </div>

      {/* Footer Submit Buttons */}
      <div className="border-t border-zinc-800 pt-3 flex justify-end items-center gap-2.5">
        <button
          type="button"
          onClick={onClose}
          className="px-3 py-2 text-xs text-zinc-400 hover:text-zinc-200 font-bold transition-colors cursor-pointer"
        >
          Cancel
        </button>
        <button
          type="button"
          disabled={submitting || selectedSummary.allTxnIds.length === 0}
          onClick={() => handleApplyClassification(selectedFolioId || undefined)}
          className="px-4 py-2 text-xs font-bold bg-amber-500 hover:bg-amber-400 text-zinc-950 rounded-lg shadow-md transition-colors disabled:opacity-50 cursor-pointer"
        >
          {submitting
            ? 'Applying...'
            : selectedFolioId
            ? `Reclassify & Bind ${selectedSummary.totalTxns} Line${selectedSummary.totalTxns !== 1 ? 's' : ''}`
            : `Reclassify ${selectedSummary.totalTxns} Line${selectedSummary.totalTxns !== 1 ? 's' : ''}`}
        </button>
      </div>
    </div>
  );
};