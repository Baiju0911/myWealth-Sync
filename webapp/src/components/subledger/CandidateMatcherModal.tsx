import React, { useState, useEffect, useMemo } from 'react';
import {
  subledgerApi,
  type CandidateMatchResult,
  type AssetComplianceSchedule,
  type AssetSubLedgerNode,
  type AssetOperationalAccount,
} from '../../api/subledger';

// 🎯 Payload passed when launching directly from Taxonomy/Ledger Dashboard
export interface TaxonomyMatchContext {
  category: string;
  subcategory: string;
  defaultAmount?: number | string;
  defaultKeyword?: string;
  rowIdentifier?: string;
}

interface CandidateMatcherModalProps {
  isOpen: boolean;
  onClose: () => void;
  // Asset is optional so the modal can open from Taxonomy Dashboard without a pre-bound asset
  asset?: AssetSubLedgerNode | null;
  taxonomyContext?: TaxonomyMatchContext | null;
  schedule?: AssetComplianceSchedule | null;
  utility?: AssetOperationalAccount | null;
  onSuccess: () => void;
}

export const CandidateMatcherModal: React.FC<CandidateMatcherModalProps> = ({
  isOpen,
  onClose,
  asset,
  taxonomyContext,
  schedule,
  utility,
  onSuccess,
}) => {
  // Query Form State
  const [documentDate, setDocumentDate] = useState<string>('');
  const [targetAmount, setTargetAmount] = useState<number | string>('');
  const [keywords, setKeywords] = useState<string>('');
  const [dayWindow, setDayWindow] = useState<number>(30); // Default to 30D

  // Target Node Resolution State
  const [availableNodes, setAvailableNodes] = useState<AssetSubLedgerNode[]>([]);
  const [selectedBindingAsset, setSelectedBindingAsset] = useState<AssetSubLedgerNode | null>(asset || null);

  // Cost Basis Sync State
  const [syncAcquisitionCost, setSyncAcquisitionCost] = useState<boolean>(true);

  // Engine State
  const [loading, setLoading] = useState<boolean>(false);
  const [binding, setBinding] = useState<boolean>(false);
  const [candidates, setCandidates] = useState<CandidateMatchResult[]>([]);
  const [selectedRowIds, setSelectedRowIds] = useState<string[]>([]);
  const [isCash, setIsCash] = useState<boolean>(false);
  const [userNote, setUserNote] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  // Preset search horizon definitions
  const horizonPresets = [
    { label: '30D', value: 30 },
    { label: '60D', value: 60 },
    { label: '90D', value: 90 },
    { label: '6M', value: 180 },
    { label: '1Y', value: 365 },
    { label: '2Y', value: 730 },
    { label: 'Till Today', value: 1825 },
  ];

  // Derive active subcategory dynamically from either source
  const activeSubcategory = useMemo(() => {
    if (taxonomyContext?.subcategory) return taxonomyContext.subcategory.trim();
    if (asset?.linked_gl_account) return String(asset.linked_gl_account).trim();
    return null;
  }, [taxonomyContext, asset]);

  // ESC Key Listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    if (isOpen) window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);


  // 🎯 Fuzzy Keyword Highlighter Component
const HighlightedText: React.FC<{ text: string; keywords: string }> = ({ text, keywords }) => {
  if (!keywords || !text) return <>{text}</>;

  // Split comma-separated search terms
  const searchTerms = keywords
    .split(',')
    .map((k) => k.trim())
    .filter(Boolean);

  if (searchTerms.length === 0) return <>{text}</>;

  // Build fuzzy regex patterns allowing optional spaces/dashes between letters
  // e.g. "SUN" -> /S[\s\-]*U[\s\-]*N/gi
  const patterns = searchTerms.map((term) => {
    const escaped = term.replace(/[^A-Za-z0-9]/g, '');
    if (!escaped) return null;
    const fuzzyPattern = escaped.split('').join('[\\s\\-]*');
    return fuzzyPattern;
  }).filter(Boolean);

  if (patterns.length === 0) return <>{text}</>;

  const combinedRegex = new RegExp(`(${patterns.join('|')})`, 'gi');
  const parts = text.split(combinedRegex);

  return (
    <>
      {parts.map((part, i) =>
        combinedRegex.test(part) ? (
          <mark key={i} className="bg-amber-400/30 text-amber-200 font-bold px-0.5 rounded border border-amber-400/40">
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  );
};

  // Core Candidate Matcher Request Runner
  const runScan = async (
    docDate: string,
    amt: number | string,
    kwString: string,
    windowDays: number,
    targetAssetId?: string
  ) => {
    setLoading(true);
    setError(null);
    setSelectedRowIds([]);

    let formattedDate = docDate;
    if (docDate && docDate.includes('-')) {
      const parts = docDate.split('-');
      if (parts[0].length === 2 && parts[2].length === 4) {
        formattedDate = `${parts[2]}-${parts[1]}-${parts[0]}`;
      }
    }

    const kwArray = kwString
      ? kwString
          .split(',')
          .map((k) => k.trim())
          .filter(Boolean)
      : [];

    const parsedAmount = Number(amt);
    const cleanAmount = !isNaN(parsedAmount) && parsedAmount > 0 ? parsedAmount : null;
    const effectiveAssetId = targetAssetId || selectedBindingAsset?.id || asset?.id;

    if (!effectiveAssetId) {
      setError(`No subledger node available under '${activeSubcategory}'. Please register a subledger node first.`);
      setLoading(false);
      setCandidates([]);
      return;
    }

    const payload = {
      asset_id: effectiveAssetId,
      document_date: formattedDate,
      target_amount: cleanAmount,
      day_window: windowDays,
      keywords: kwArray,
    };

    try {
      const response = await subledgerApi.findCandidates(payload);
      setCandidates(response.candidates || []);
    } catch (err: any) {
      console.error('Candidate fetch failed:', err.response?.data || err);
      const serverDetails = err.response?.data
        ? typeof err.response.data === 'object'
          ? JSON.stringify(err.response.data)
          : String(err.response.data)
        : null;

      setError(serverDetails ? `Scan Failed: ${serverDetails}` : 'Failed to fetch matching candidate rows from staging.');
      setCandidates([]);
    } finally {
      setLoading(false);
    }
  };

  // Dual-Entry Initialization
  useEffect(() => {
    if (!isOpen) return;

    const initialDate =
      schedule?.due_date ||
      asset?.acquisition_date ||
      new Date().toISOString().split('T')[0];

    const initialAmount =
      schedule?.expected_amount ||
      taxonomyContext?.defaultAmount ||
      (utility ? '' : asset?.acquisition_cost) ||
      '';

    const initialKeywords =
      utility?.matching_keyword ||
      taxonomyContext?.defaultKeyword ||
      taxonomyContext?.subcategory ||
      asset?.name ||
      '';

    const existingAssetNote = (asset as any)?.user_note || asset?.metadata_payload?.user_note || '';

    setDocumentDate(initialDate);
    setTargetAmount(initialAmount);
    setKeywords(initialKeywords);
    setUserNote(existingAssetNote);
    setError(null);
    setIsCash(false);
    setSelectedRowIds([]);
    setSyncAcquisitionCost(true);

    if (activeSubcategory) {
      subledgerApi
        .getAssets(activeSubcategory)
        .then((nodes) => {
          setAvailableNodes(nodes);
          const activeNode = asset || (nodes.length > 0 ? nodes[0] : null);
          setSelectedBindingAsset(activeNode);

          if (activeNode?.id) {
            runScan(initialDate, initialAmount, initialKeywords, dayWindow, activeNode.id);
          }
        })
        .catch((err) => console.error('Failed to load subledger nodes:', err));
    } else if (asset?.id) {
      setSelectedBindingAsset(asset);
      runScan(initialDate, initialAmount, initialKeywords, dayWindow, asset.id);
    }
  }, [isOpen, asset?.id, schedule?.id, utility?.id, taxonomyContext]);

  const handleUnmap = async (cand: CandidateMatchResult) => {
    if (!cand.mapping_info?.mapping_id) return;
    setBinding(true);
    setError(null);

    try {
      await subledgerApi.unmapTransaction({ mapping_id: cand.mapping_info.mapping_id });
      const currentTargetId = selectedBindingAsset?.id || asset?.id;
      runScan(documentDate, targetAmount, keywords, dayWindow, currentTargetId);
      onSuccess();
    } catch (err: any) {
      console.error('Unmapping failed:', err);
      setError('Failed to unmap transaction.');
    } finally {
      setBinding(false);
    }
  };

  const handleSaveAndSync = async () => {
    const activeTargetNode = selectedBindingAsset || asset;
    if (!activeTargetNode) return;

    setBinding(true);
    setError(null);
    try {
      const finalAmount = Number(targetAmount) || 0;
      const noteToSave = userNote.trim();

      await subledgerApi.updateAsset(activeTargetNode.id, {
        acquisition_cost: syncAcquisitionCost && finalAmount > 0 ? finalAmount : activeTargetNode.acquisition_cost,
        current_valuation: syncAcquisitionCost && finalAmount > 0 ? finalAmount : activeTargetNode.current_valuation,
        user_note: noteToSave,
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

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const currentTargetId = selectedBindingAsset?.id || asset?.id;
    runScan(documentDate, targetAmount, keywords, dayWindow, currentTargetId);
  };

  const toggleSelectRow = (rowId: string) => {
    setSelectedRowIds((prev) =>
      prev.includes(rowId) ? prev.filter((id) => id !== rowId) : [...prev, rowId]
    );
  };

  const toggleSelectAll = () => {
    const unmappedCandidates = candidates.filter((c) => !c.is_mapped_to_this_asset);
    if (selectedRowIds.length === unmappedCandidates.length) {
      setSelectedRowIds([]);
    } else {
      setSelectedRowIds(unmappedCandidates.map((c) => c.row_identifier));
    }
  };

  const selectedTotalSum = candidates
    .filter((c) => selectedRowIds.includes(c.row_identifier))
    .reduce((acc, curr) => acc + Number(curr.debit || curr.credit || 0), 0);

  const handleBatchBind = async (targetCandidate?: CandidateMatchResult) => {
    const activeTargetNode = selectedBindingAsset || asset;

    if (!activeTargetNode) {
      setError('Please select a target subledger node before binding.');
      return;
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
      for (const cand of rowsToBind) {
        let formattedDate = cand?.transaction_date || documentDate;
        if (formattedDate.includes('-')) {
          const parts = formattedDate.split('-');
          if (parts[0].length === 2 && parts[2].length === 4) {
            formattedDate = `${parts[2]}-${parts[1]}-${parts[0]}`;
          }
        }

        const finalAmount = cand
          ? Number(cand.debit || cand.credit || 0)
          : Number(targetAmount) || 0;

        await subledgerApi.bindTransaction({
          asset_id: activeTargetNode.id,
          schedule_id: schedule?.id || null,
          operational_account_id: utility?.id || activeTargetNode.operational_accounts?.[0]?.id || null,
          row_identifier: isCash ? null : cand.row_identifier,
          is_cash_entry: isCash,
          transaction_date: formattedDate,
          amount: finalAmount,
          transaction_purpose: schedule?.schedule_type || 'SUB_LEDGER_PAYMENT',
          user_note: userNote || `Reconciled via Candidate Matcher UI`,
          sync_acquisition_cost: syncAcquisitionCost,
        });
      }

      onSuccess();
      onClose();
    } catch (err: any) {
      console.error('Binding failed:', err.response?.data || err);
      const serverDetails = err.response?.data
        ? typeof err.response.data === 'object'
          ? JSON.stringify(err.response.data)
          : String(err.response.data)
        : null;

      setError(serverDetails ? `Binding Failed: ${serverDetails}` : 'Failed to bind transaction(s).');
    } finally {
      setBinding(false);
    }
  };

  if (!isOpen) return null;

  const unmappedCandidates = candidates.filter((c) => !c.is_mapped_to_this_asset);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
      onClick={(e) => {
        e.stopPropagation();
        onClose();
      }}
    >
      

      <div
        className="w-full h-full  max-w-5xl rounded-xl border border-slate-800 bg-slate-900 p-6 shadow-2xl text-slate-100 font-sans"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-start justify-between border-b border-slate-800 pb-4">
          <div>
            <span className="text-xs font-semibold tracking-wider text-emerald-400 uppercase font-mono">
              Sub-Ledger Post-Facto Reconciler 
            </span>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              {schedule?.title || utility?.provider_name || selectedBindingAsset?.name || activeSubcategory || 'Staging Scanner'}
            </h2>

            {/* Target Node Selector Bar when called from Taxonomy/Ledger Dashboard */}
            {taxonomyContext && availableNodes.length > 0 && (
              <div className="mt-2 flex items-center gap-2 font-mono text-xs">
                <span className="text-slate-400">Target Entity:</span>
                <select
                  value={selectedBindingAsset?.id || ''}
                  onChange={(e) => {
                    const found = availableNodes.find((n) => String(n.id) === e.target.value);
                    if (found) {
                      setSelectedBindingAsset(found);
                      runScan(documentDate, targetAmount, keywords, dayWindow, found.id);
                    }
                  }}
                  className="rounded border border-slate-700 bg-slate-800 p-1 text-emerald-400 font-bold focus:border-emerald-500 focus:outline-none cursor-pointer"
                >
                  {availableNodes.map((n) => (
                    <option key={n.id} value={n.id}>
                      [{n.asset_code}] {n.name} (Valuation: ₹{Number(n.current_valuation || 0).toLocaleString('en-IN')})
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onClose();
            }}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white cursor-pointer transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Form Controls */}
        <form onSubmit={handleSearchSubmit} className="mt-4 grid grid-cols-12 gap-3">
          <div className="col-span-12 md:col-span-3">
            <label className="block text-xs font-medium text-slate-400">Document Date</label>
            <input
              type="date"
              value={documentDate}
              onChange={(e) => setDocumentDate(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none font-mono"
            />
          </div>

          <div className="col-span-12 md:col-span-3">
            <label className="block text-xs font-medium text-slate-400">Target Amount (₹)</label>
            <input
              type="number"
              step="0.01"
              placeholder="0.00"
              value={targetAmount}
              onChange={(e) => setTargetAmount(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none font-mono"
            />
          </div>

          <div className="col-span-12 md:col-span-4">
            <label className="block text-xs font-medium text-slate-400">Matching Keywords</label>
            <input
              type="text"
              placeholder="e.g. KSEB, ULLOOR, TAX"
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none font-mono"
            />
          </div>

          <div className="col-span-12 md:col-span-2 flex items-end">
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 cursor-pointer transition-colors"
            >
              {loading ? 'Scanning...' : 'Re-Scan'}
            </button>
          </div>

          {/* Horizon Presets & Manual Toggles Bar */}
          <div className="col-span-12 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-800/50 px-3 py-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-slate-400 font-medium">Search Horizon:</span>
              <div className="flex flex-wrap items-center gap-1">
                {horizonPresets.map((preset) => (
                  <button
                    key={preset.value}
                    type="button"
                    onClick={() => {
                      setDayWindow(preset.value);
                      const activeId = selectedBindingAsset?.id || asset?.id;
                      runScan(documentDate, targetAmount, keywords, preset.value, activeId);
                    }}
                    className={`rounded px-2.5 py-1 font-mono text-[11px] font-bold cursor-pointer transition-all ${
                      dayWindow === preset.value
                        ? 'bg-emerald-500 text-slate-950 shadow-sm scale-105'
                        : 'bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white'
                    }`}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-4">
              <label className="flex items-center gap-1.5 text-xs text-emerald-400 font-mono cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={syncAcquisitionCost}
                  onChange={(e) => setSyncAcquisitionCost(e.target.checked)}
                  className="rounded accent-emerald-500 cursor-pointer"
                />
                <span>Sync Acquisition Cost</span>
              </label>

              <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={isCash}
                  onChange={(e) => setIsCash(e.target.checked)}
                  className="rounded accent-emerald-500 cursor-pointer"
                />
                <span>Direct Cash / Manual</span>
              </label>
            </div>
          </div>
        </form>

        {error && (
          <div className="mt-3 rounded-lg bg-rose-500/10 p-3 text-xs text-rose-400 border border-rose-500/20 font-mono">
            {error}
          </div>
        )}

        {/* Results Area */}
        <div className="mt-4 max-w-5xl max-h-165 h-full w-full overflow-y-auto rounded-xl border border-slate-800 bg-slate-950 p-3">
          {isCash ? (
            <div className="p-4 text-center">
              <p className="text-sm font-semibold text-amber-400">Manual Cash Entry Mode Selected</p>
              <p className="text-xs text-slate-400 mt-1">
                This transaction will be logged directly to the target asset subledger without linking to bank staging lines.
              </p>
              <button
                type="button"
                onClick={() => handleBatchBind()}
                disabled={binding}
                className="mt-4 rounded-lg bg-amber-600 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-500 disabled:opacity-50 cursor-pointer transition-colors"
              >
                {binding ? 'Binding Cash Entry...' : 'Confirm Cash Payment & Clear Due'}
              </button>
            </div>
          ) : loading ? (
            <div className="p-8 text-center text-sm text-slate-400 font-mono">
              ⚡ Running candidate lookup & staging matcher...
            </div>
          ) : candidates.length === 0 ? (
            <div className="p-8 text-center text-sm text-slate-400 font-mono">
              No matching bank staging rows found for "{keywords}" within the selected window.
              <br />
              <span className="text-xs text-slate-500">
                Try broadening keywords or selecting a larger search horizon (e.g. 6M, 1Y, Till Today).
              </span>
            </div>
          ) : (
            <div>
              {/* Batch Action Header Bar */}
              <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800 text-xs px-1">
                <label className="flex items-center gap-2 cursor-pointer select-none text-slate-400 font-mono">
                  <input
                    type="checkbox"
                    checked={
                      unmappedCandidates.length > 0 &&
                      selectedRowIds.length === unmappedCandidates.length
                    }
                    onChange={toggleSelectAll}
                    className="rounded accent-emerald-500 cursor-pointer"
                  />
                  <span>
                    Select Unmapped ({selectedRowIds.length}/{unmappedCandidates.length})
                  </span>
                </label>

                {selectedRowIds.length > 0 && (
                  <div className="flex items-center gap-2 font-mono text-emerald-400 font-semibold">
                    <span>Selected Total:</span>
                    <span className="bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded">
                      ₹{selectedTotalSum.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                )}

                {selectedRowIds.length > 0 && (
                  <button
                    type="button"
                    onClick={() => handleBatchBind()}
                    disabled={binding}
                    className="rounded bg-emerald-600 px-3 py-1 text-[11px] font-bold text-white hover:bg-emerald-500 disabled:opacity-50 transition-colors cursor-pointer"
                  >
                    {binding ? 'Binding...' : `⚡ Bind Selected (${selectedRowIds.length})`}
                  </button>
                )}
              </div>

              {/* Candidate Cards */}
              <div className="space-y-2">
                {candidates.map((cand) => {
                  const getCleanNarration = () => {
                    if (!cand.remarks) return 'No narration details';
                    if (typeof cand.remarks === 'string') {
                      try {
                        const parsed = JSON.parse(cand.remarks);
                        return parsed.display_text || parsed.narration || parsed.payee || cand.remarks;
                      } catch {
                        return cand.remarks;
                      }
                    }
                    return cand.remarks.display_text || cand.remarks.narration || cand.remarks.payee || JSON.stringify(cand.remarks);
                  };

                  const cleanNarration = getCleanNarration();
                  const amountVal = Number(cand.debit || cand.credit || 0);
                  const isChecked = selectedRowIds.includes(cand.row_identifier);
                  const isBoundToAsset = cand.is_mapped_to_this_asset;

                  return (
                    <div
                      key={cand.row_identifier}
                      className={`flex items-center justify-between gap-3 rounded-lg border p-2.5 transition-colors ${
                        isBoundToAsset
                          ? 'border-cyan-500/50 bg-cyan-500/5'
                          : isChecked
                          ? 'border-emerald-500 bg-emerald-500/5'
                          : 'border-slate-800 bg-slate-900 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-start gap-2.5 min-w-0 flex-1">
                        {!isBoundToAsset && (
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={() => toggleSelectRow(cand.row_identifier)}
                            className="mt-1 rounded accent-emerald-500 cursor-pointer"
                          />
                        )}

                        <div className="min-w-0 flex-1 space-y-1">
                          <div className="flex items-center gap-2">
                            {isBoundToAsset ? (
                              <span className="rounded px-1.5 py-0.5 font-mono text-[10px] font-bold bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">
                                BOUND TO ASSET
                              </span>
                            ) : (
                              <span
                                className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-bold ${
                                  cand.probability_score >= 80
                                    ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                    : 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                                }`}
                              >
                                {cand.probability_score}% MATCH
                              </span>
                            )}

                            <span className="font-mono text-[11px] font-semibold text-slate-300">
                              {cand.transaction_date}
                            </span>

                            {!isBoundToAsset && (
                              <span className="text-[10px] text-slate-500 font-mono">
                                ({cand.date_offset_days > 0 ? `+${cand.date_offset_days}` : cand.date_offset_days}d offset)
                              </span>
                            )}
                          </div>

                          {/* <p
                            className="font-mono text-[11px] text-slate-200 line-clamp-2 break-all leading-tight"
                            title={cleanNarration}
                          >
                            {cleanNarration}

                          </p> */}

                          <p className="font-mono text-[11px] text-slate-200 line-clamp-2 break-all leading-tight" title={cleanNarration}>
  <HighlightedText text={cleanNarration} keywords={keywords} />
</p>
                        </div>
                      </div>

                      <div className="flex shrink-0 flex-col items-end justify-between pl-2 border-l border-slate-800">
                        <div className="font-mono text-xs font-bold text-emerald-400">
                          ₹{amountVal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </div>

                        {isBoundToAsset ? (
                          <button
                            type="button"
                            onClick={() => handleUnmap(cand)}
                            disabled={binding}
                            className="mt-1.5 rounded bg-rose-600/80 px-2.5 py-1 text-[10px] font-bold text-white hover:bg-rose-500 disabled:opacity-50 cursor-pointer transition-colors font-mono"
                          >
                            {binding ? 'Working...' : 'Disconnect'}
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => handleBatchBind(cand)}
                            disabled={binding}
                            className="mt-1.5 rounded bg-emerald-600 px-2.5 py-1 text-[10px] font-bold text-white hover:bg-emerald-500 disabled:opacity-50 cursor-pointer transition-colors font-mono"
                          >
                            {binding ? 'Binding...' : '⚡ Bind'}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Bottom Action Footer */}
        <div className="mt-4 flex items-center justify-between border-t border-slate-800 pt-3">
          <div className="flex-1 mr-3">
            <input
              type="text"
              placeholder="Audit Note (e.g. Cleared via KSEB Online Portal / Trivandrum Corp)"
              value={userNote}
              onChange={(e) => setUserNote(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none font-mono"
            />
          </div>

          <button
            type="button"
            onClick={handleSaveAndSync}
            disabled={binding}
            className="rounded-lg bg-emerald-600 px-4 py-1.5 text-xs font-bold text-white hover:bg-emerald-500 disabled:opacity-50 transition-colors cursor-pointer font-mono whitespace-nowrap"
          >
            {binding ? 'Updating...' : '💾 Save & Sync Cost Basis'}
          </button>
        </div>
      </div>
    </div>
  );
};


// import React, { useState, useEffect } from 'react';
// import {
//   subledgerApi,
//   type CandidateMatchResult,
//   type AssetComplianceSchedule,
//   type AssetSubLedgerNode,
//   type AssetOperationalAccount,
// } from '../../api/subledger';

// interface CandidateMatcherModalProps {
//   isOpen: boolean;
//   onClose: () => void;
//   asset: AssetSubLedgerNode;
//   schedule?: AssetComplianceSchedule | null;
//   utility?: AssetOperationalAccount | null;
//   onSuccess: () => void;
// }

// export const CandidateMatcherModal: React.FC<CandidateMatcherModalProps> = ({
//   isOpen,
//   onClose,
//   asset,
//   schedule,
//   utility,
//   onSuccess,
// }) => {
//   // Query Form State
//   const [documentDate, setDocumentDate] = useState<string>('');
//   const [targetAmount, setTargetAmount] = useState<number | string>('');
//   const [keywords, setKeywords] = useState<string>('');
//   const [dayWindow, setDayWindow] = useState<number>(30); // Default to 30D

//   // Cost Basis Sync State
//   const [syncAcquisitionCost, setSyncAcquisitionCost] = useState<boolean>(true);

//   // Engine State
//   const [loading, setLoading] = useState<boolean>(false);
//   const [binding, setBinding] = useState<boolean>(false);
//   const [candidates, setCandidates] = useState<CandidateMatchResult[]>([]);
//   const [selectedRowIds, setSelectedRowIds] = useState<string[]>([]);
//   const [isCash, setIsCash] = useState<boolean>(false);
//   const [userNote, setUserNote] = useState<string>('');
//   const [error, setError] = useState<string | null>(null);

//   // Preset search horizon definitions
//   const horizonPresets = [
//     { label: '30D', value: 30 },
//     { label: '60D', value: 60 },
//     { label: '90D', value: 90 },
//     { label: '6M', value: 180 },
//     { label: '1Y', value: 365 },
//     { label: '2Y', value: 730 },
//     { label: 'Till Today', value: 1825 }, // ~5 years
//   ];

//   // Isolated ESC Key Listener
//   useEffect(() => {
//     const handleKeyDown = (e: KeyboardEvent) => {
//       if (e.key === 'Escape') {
//         e.stopPropagation();
//         onClose();
//       }
//     };
//     if (isOpen) window.addEventListener('keydown', handleKeyDown);
//     return () => window.removeEventListener('keydown', handleKeyDown);
//   }, [isOpen, onClose]);

//   // Auto-initialize defaults and trigger candidate scan when modal opens
//   // useEffect(() => {
//   //   if (isOpen && asset) {
//   //     const initialDate =
//   //       schedule?.due_date ||
//   //       asset.acquisition_date ||
//   //       new Date().toISOString().split('T')[0];

//   //     const initialAmount =
//   //       schedule?.expected_amount ||
//   //       (utility ? '' : asset.acquisition_cost) ||
//   //       '';

//   //     const initialKeywords = utility?.matching_keyword
//   //       ? utility.matching_keyword
//   //       : asset.name;

//   //     setDocumentDate(initialDate);
//   //     setTargetAmount(initialAmount);
//   //     setKeywords(initialKeywords);
//   //     setError(null);
//   //     setIsCash(false);
//   //     setUserNote('');
//   //     setSelectedRowIds([]);
//   //     setSyncAcquisitionCost(true);

//   //     runScan(initialDate, initialAmount, initialKeywords, dayWindow);
//   //   } else {
//   //     setCandidates([]);
//   //     setSelectedRowIds([]);
//   //     setError(null);
//   //   }
//   // }, [isOpen, asset?.id, schedule?.id, utility?.id]);

//   useEffect(() => {
//   if (isOpen && asset) {
//     const initialDate =
//       schedule?.due_date ||
//       asset.acquisition_date ||
//       new Date().toISOString().split('T')[0];

//     const initialAmount =
//       schedule?.expected_amount ||
//       (utility ? '' : asset.acquisition_cost) ||
//       '';

//     const initialKeywords = utility?.matching_keyword
//       ? utility.matching_keyword
//       : asset.name;

//     // 🎯 Pre-fill note from master asset payload
//     const existingAssetNote =
//       (asset as any).user_note ||
//       asset.metadata_payload?.user_note ||
//       '';

//     setDocumentDate(initialDate);
//     setTargetAmount(initialAmount);
//     setKeywords(initialKeywords);
//     setUserNote(existingAssetNote); // 👈 Set note from master sub-ledger
//     setError(null);
//     setIsCash(false);
//     setSelectedRowIds([]);
//     setSyncAcquisitionCost(true);

//     runScan(initialDate, initialAmount, initialKeywords, dayWindow);
//   }
// }, [isOpen, asset?.id, schedule?.id, utility?.id]);

//   // Core Candidate Matcher Request Runner
//   const runScan = async (
//     docDate: string,
//     amt: number | string,
//     kwString: string,
//     windowDays: number
//   ) => {
//     setLoading(true);
//     setError(null);
//     setSelectedRowIds([]);

//     let formattedDate = docDate;
//     if (docDate && docDate.includes('-')) {
//       const parts = docDate.split('-');
//       if (parts[0].length === 2 && parts[2].length === 4) {
//         formattedDate = `${parts[2]}-${parts[1]}-${parts[0]}`;
//       }
//     }

//     const kwArray = kwString
//       ? kwString
//           .split(',')
//           .map((k) => k.trim())
//           .filter(Boolean)
//       : [];

//     const parsedAmount = Number(amt);
//     const cleanAmount =
//       !isNaN(parsedAmount) && parsedAmount > 0 ? parsedAmount : null;

//     const payload = {
//       asset_id: asset.id,
//       document_date: formattedDate,
//       target_amount: cleanAmount,
//       day_window: windowDays,
//       keywords: kwArray,
//     };

//     try {
//       const response = await subledgerApi.findCandidates(payload);
//       const candidateList = response.candidates || [];
//       setCandidates(candidateList);
//     } catch (err: any) {
//       console.error('Candidate fetch failed:', err.response?.data || err);
//       const serverDetails = err.response?.data
//         ? typeof err.response.data === 'object'
//           ? JSON.stringify(err.response.data)
//           : String(err.response.data)
//         : null;

//       setError(
//         serverDetails
//           ? `Scan Failed: ${serverDetails}`
//           : 'Failed to fetch matching candidate rows from staging.'
//       );
//       setCandidates([]);
//     } finally {
//       setLoading(false);
//     }
//   };

//   // Handle Unmapping an already-bound transaction
//   const handleUnmap = async (cand: CandidateMatchResult) => {
//     if (!cand.mapping_info?.mapping_id) return;
//     setBinding(true);
//     setError(null);

//     try {
//       await subledgerApi.unmapTransaction({
//         mapping_id: cand.mapping_info.mapping_id,
//       });

//       runScan(documentDate, targetAmount, keywords, dayWindow);
//       onSuccess();
//     } catch (err: any) {
//       console.error('Unmapping failed:', err);
//       setError('Failed to unmap transaction.');
//     } finally {
//       setBinding(false);
//     }
//   };

// const handleSaveAndSync = async () => {
//   setBinding(true);
//   setError(null);
//   try {
//     const finalAmount = Number(targetAmount) || 0;
//     const noteToSave = userNote.trim();

//     // 🎯 Update Master Asset Sub-Ledger (saves to metadata_payload)
//     await subledgerApi.updateAsset(asset.id, {
//       acquisition_cost:
//         syncAcquisitionCost && finalAmount > 0
//           ? finalAmount
//           : asset.acquisition_cost,
//       current_valuation:
//         syncAcquisitionCost && finalAmount > 0
//           ? finalAmount
//           : asset.current_valuation,
//       user_note: noteToSave,
//     });

//     onSuccess();
//     onClose();
//   } catch (err) {
//     console.error('Failed to update asset baseline:', err);
//     setError('Failed to save reconciliation updates.');
//   } finally {
//     setBinding(false);
//   }
// };

//   const handleSearchSubmit = (e: React.FormEvent) => {
//     e.preventDefault();
//     runScan(documentDate, targetAmount, keywords, dayWindow);
//   };

//   const toggleSelectRow = (rowId: string) => {
//     setSelectedRowIds((prev) =>
//       prev.includes(rowId) ? prev.filter((id) => id !== rowId) : [...prev, rowId]
//     );
//   };

//   const toggleSelectAll = () => {
//     const unmappedCandidates = candidates.filter((c) => !c.is_mapped_to_this_asset);
//     if (selectedRowIds.length === unmappedCandidates.length) {
//       setSelectedRowIds([]);
//     } else {
//       setSelectedRowIds(unmappedCandidates.map((c) => c.row_identifier));
//     }
//   };

//   const selectedTotalSum = candidates
//     .filter((c) => selectedRowIds.includes(c.row_identifier))
//     .reduce((acc, curr) => acc + Number(curr.debit || curr.credit || 0), 0);

//   const handleBatchBind = async (targetCandidate?: CandidateMatchResult) => {
//     setBinding(true);
//     setError(null);

//     const rowsToBind = targetCandidate
//       ? [targetCandidate]
//       : candidates.filter((c) => selectedRowIds.includes(c.row_identifier));

//     if (rowsToBind.length === 0 && !isCash) {
//       setError('Please select at least one candidate row to bind.');
//       setBinding(false);
//       return;
//     }

//     try {
//       for (const cand of rowsToBind) {
//         let formattedDate = cand?.transaction_date || documentDate;
//         if (formattedDate.includes('-')) {
//           const parts = formattedDate.split('-');
//           if (parts[0].length === 2 && parts[2].length === 4) {
//             formattedDate = `${parts[2]}-${parts[1]}-${parts[0]}`;
//           }
//         }

//         // Determine final binding amount (prefers candidate debit/credit, falls back to targetAmount)
//         const finalAmount = cand
//           ? Number(cand.debit || cand.credit || 0)
//           : Number(targetAmount) || 0;

//         await subledgerApi.bindTransaction({
//           asset_id: asset.id,
//           schedule_id: schedule?.id || null,
//           operational_account_id:
//             utility?.id || asset.operational_accounts?.[0]?.id || null,
//           row_identifier: isCash ? null : cand.row_identifier,
//           is_cash_entry: isCash,
//           transaction_date: formattedDate,
//           amount: finalAmount,
//           transaction_purpose: schedule?.schedule_type || 'SUB_LEDGER_PAYMENT',
//           user_note: userNote || `Reconciled via Candidate Matcher UI`,
//           sync_acquisition_cost: syncAcquisitionCost, 
//         });
//       }

//       onSuccess();
//       onClose();
//     } catch (err: any) {
//       console.error('Binding failed:', err.response?.data || err);
//       const serverDetails = err.response?.data
//         ? typeof err.response.data === 'object'
//           ? JSON.stringify(err.response.data)
//           : String(err.response.data)
//         : null;

//       setError(
//         serverDetails
//           ? `Binding Failed: ${serverDetails}`
//           : 'Failed to bind transaction(s). Please check server logs.'
//       );
//     } finally {
//       setBinding(false);
//     }
//   };

//   if (!isOpen) return null;

//   const unmappedCandidates = candidates.filter((c) => !c.is_mapped_to_this_asset);

//   return (
//     <div 
//       className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
//       onClick={(e) => {
//         e.stopPropagation();
//         onClose();
//       }}
//     >
//       <div 
//         className="w-full max-w-3xl rounded-xl border border-slate-800 bg-slate-900 p-6 shadow-2xl text-slate-100 font-sans"
//         onClick={(e) => e.stopPropagation()}
//       >
//         {/* Modal Header */}
//         <div className="flex items-start justify-between border-b border-slate-800 pb-4">
//           <div>
//             <span className="text-xs font-semibold tracking-wider text-emerald-400 uppercase font-mono">
//               Sub-Ledger Post-Facto Reconciler
//             </span>
//             <h2 className="text-xl font-bold text-white">
//               {schedule?.title || utility?.provider_name || asset.name}
//             </h2>
//             <p className="text-xs text-slate-400">
//               Asset Code: <span className="font-mono text-slate-200">{asset.asset_code}</span>
//               {utility && (
//                 <span className="ml-2 text-emerald-400 font-mono">
//                   • Target Utility: {utility.provider_name} ({utility.consumer_identifier})
//                 </span>
//               )}
//             </p>
//           </div>
//           <button
//             type="button"
//             onClick={(e) => {
//               e.stopPropagation();
//               onClose();
//             }}
//             className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white cursor-pointer transition-colors"
//           >
//             ✕
//           </button>
//         </div>

//         {/* Form Controls */}
//         <form onSubmit={handleSearchSubmit} className="mt-4 grid grid-cols-12 gap-3">
//           <div className="col-span-12 md:col-span-3">
//             <label className="block text-xs font-medium text-slate-400">Document Date</label>
//             <input
//               type="date"
//               value={documentDate}
//               onChange={(e) => setDocumentDate(e.target.value)}
//               className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none font-mono"
//             />
//           </div>

//           <div className="col-span-12 md:col-span-3">
//             <label className="block text-xs font-medium text-slate-400">Target Amount (₹)</label>
//             <input
//               type="number"
//               step="0.01"
//               placeholder="0.00"
//               value={targetAmount}
//               onChange={(e) => setTargetAmount(e.target.value)}
//               className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none font-mono"
//             />
//           </div>

//           <div className="col-span-12 md:col-span-4">
//             <label className="block text-xs font-medium text-slate-400">Matching Keywords</label>
//             <input
//               type="text"
//               placeholder="e.g. KSEB, ULLOOR, TAX"
//               value={keywords}
//               onChange={(e) => setKeywords(e.target.value)}
//               className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none font-mono"
//             />
//           </div>

//           <div className="col-span-12 md:col-span-2 flex items-end">
//             <button
//               type="submit"
//               disabled={loading}
//               className="w-full rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 cursor-pointer transition-colors"
//             >
//               {loading ? 'Scanning...' : 'Re-Scan'}
//             </button>
//           </div>

//           {/* Horizon Presets & Manual Toggles Bar */}
//           <div className="col-span-12 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-800/50 px-3 py-2">
//             <div className="flex flex-wrap items-center gap-2">
//               <span className="text-xs text-slate-400 font-medium">Search Horizon:</span>
//               <div className="flex flex-wrap items-center gap-1">
//                 {horizonPresets.map((preset) => (
//                   <button
//                     key={preset.value}
//                     type="button"
//                     onClick={() => {
//                       setDayWindow(preset.value);
//                       runScan(documentDate, targetAmount, keywords, preset.value);
//                     }}
//                     className={`rounded px-2.5 py-1 font-mono text-[11px] font-bold cursor-pointer transition-all ${
//                       dayWindow === preset.value
//                         ? 'bg-emerald-500 text-slate-950 shadow-sm scale-105'
//                         : 'bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white'
//                     }`}
//                   >
//                     {preset.label}
//                   </button>
//                 ))}
//               </div>
//             </div>

//             <div className="flex items-center gap-4">
//               {/* Sync Cost Basis Toggle */}
//               <label className="flex items-center gap-1.5 text-xs text-emerald-400 font-mono cursor-pointer select-none">
//                 <input
//                   type="checkbox"
//                   checked={syncAcquisitionCost}
//                   onChange={(e) => setSyncAcquisitionCost(e.target.checked)}
//                   className="rounded accent-emerald-500 cursor-pointer"
//                 />
//                 <span>Sync Acquisition Cost</span>
//               </label>

//               {/* Direct Cash / Manual Entry Toggle */}
//               <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer select-none">
//                 <input
//                   type="checkbox"
//                   checked={isCash}
//                   onChange={(e) => setIsCash(e.target.checked)}
//                   className="rounded accent-emerald-500 cursor-pointer"
//                 />
//                 <span>Direct Cash / Manual</span>
//               </label>
//             </div>
//           </div>
//         </form>

//         {error && (
//           <div className="mt-3 rounded-lg bg-rose-500/10 p-3 text-xs text-rose-400 border border-rose-500/20 font-mono">
//             {error}
//           </div>
//         )}

//         {/* Results Area */}
//         <div className="mt-4 max-h-72 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950 p-3">
//           {isCash ? (
//             <div className="p-4 text-center">
//               <p className="text-sm font-semibold text-amber-400">Manual Cash Entry Mode Selected</p>
//               <p className="text-xs text-slate-400 mt-1">
//                 This transaction will be logged directly to the asset sub-ledger without linking to bank statement staging lines.
//               </p>
//               <button
//                 type="button"
//                 onClick={() => handleBatchBind()}
//                 disabled={binding}
//                 className="mt-4 rounded-lg bg-amber-600 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-500 disabled:opacity-50 cursor-pointer transition-colors"
//               >
//                 {binding ? 'Binding Cash Entry...' : 'Confirm Cash Payment & Clear Due'}
//               </button>
//             </div>
//           ) : loading ? (
//             <div className="p-8 text-center text-sm text-slate-400 font-mono">
//               ⚡ Running candidate lookup & staging matcher...
//             </div>
//           ) : candidates.length === 0 ? (
//             <div className="p-8 text-center text-sm text-slate-400 font-mono">
//               No matching bank staging rows found for "{keywords}" within the selected window.
//               <br />
//               <span className="text-xs text-slate-500">
//                 Try broadening keywords or selecting a larger search horizon (e.g. 6M, 1Y, Till Today).
//               </span>
//             </div>
//           ) : (
//             <div>
//               {/* Batch Action Header Bar */}
//               <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800 text-xs px-1">
//                 <label className="flex items-center gap-2 cursor-pointer select-none text-slate-400 font-mono">
//                   <input
//                     type="checkbox"
//                     checked={
//                       unmappedCandidates.length > 0 &&
//                       selectedRowIds.length === unmappedCandidates.length
//                     }
//                     onChange={toggleSelectAll}
//                     className="rounded accent-emerald-500 cursor-pointer"
//                   />
//                   <span>
//                     Select Unmapped ({selectedRowIds.length}/{unmappedCandidates.length})
//                   </span>
//                 </label>

//                 {selectedRowIds.length > 0 && (
//                   <div className="flex items-center gap-2 font-mono text-emerald-400 font-semibold">
//                     <span>Selected Total:</span>
//                     <span className="bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded">
//                       ₹{selectedTotalSum.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
//                     </span>
//                   </div>
//                 )}

//                 {selectedRowIds.length > 0 && (
//                   <button
//                     type="button"
//                     onClick={() => handleBatchBind()}
//                     disabled={binding}
//                     className="rounded bg-emerald-600 px-3 py-1 text-[11px] font-bold text-white hover:bg-emerald-500 disabled:opacity-50 transition-colors cursor-pointer"
//                   >
//                     {binding ? 'Binding...' : `⚡ Bind Selected (${selectedRowIds.length})`}
//                   </button>
//                 )}
//               </div>

//               {/* Candidate Cards */}
//               <div className="space-y-2">
//                 {candidates.map((cand) => {
//                   const getCleanNarration = () => {
//                     if (!cand.remarks) return 'No narration details';
//                     if (typeof cand.remarks === 'string') {
//                       try {
//                         const parsed = JSON.parse(cand.remarks);
//                         return (
//                           parsed.display_text ||
//                           parsed.narration ||
//                           parsed.payee ||
//                           cand.remarks
//                         );
//                       } catch {
//                         return cand.remarks;
//                       }
//                     }
//                     return (
//                       cand.remarks.display_text ||
//                       cand.remarks.narration ||
//                       cand.remarks.payee ||
//                       JSON.stringify(cand.remarks)
//                     );
//                   };

//                   const cleanNarration = getCleanNarration();
//                   const amountVal = Number(cand.debit || cand.credit || 0);
//                   const isChecked = selectedRowIds.includes(cand.row_identifier);
//                   const isBoundToAsset = cand.is_mapped_to_this_asset;

//                   return (
//                     <div
//                       key={cand.row_identifier}
//                       className={`flex items-center justify-between gap-3 rounded-lg border p-2.5 transition-colors ${
//                         isBoundToAsset
//                           ? 'border-cyan-500/50 bg-cyan-500/5'
//                           : isChecked
//                           ? 'border-emerald-500 bg-emerald-500/5'
//                           : 'border-slate-800 bg-slate-900 hover:border-slate-700'
//                       }`}
//                     >
//                       <div className="flex items-start gap-2.5 min-w-0 flex-1">
//                         {!isBoundToAsset && (
//                           <input
//                             type="checkbox"
//                             checked={isChecked}
//                             onChange={() => toggleSelectRow(cand.row_identifier)}
//                             className="mt-1 rounded accent-emerald-500 cursor-pointer"
//                           />
//                         )}

//                         <div className="min-w-0 flex-1 space-y-1">
//                           <div className="flex items-center gap-2">
//                             {isBoundToAsset ? (
//                               <span className="rounded px-1.5 py-0.5 font-mono text-[10px] font-bold bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">
//                                 BOUND TO ASSET
//                               </span>
//                             ) : (
//                               <span
//                                 className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-bold ${
//                                   cand.probability_score >= 80
//                                     ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
//                                     : 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
//                                 }`}
//                               >
//                                 {cand.probability_score}% MATCH
//                               </span>
//                             )}

//                             <span className="font-mono text-[11px] font-semibold text-slate-300">
//                               {cand.transaction_date}
//                             </span>
                            
//                             {!isBoundToAsset && (
//                               <span className="text-[10px] text-slate-500 font-mono">
//                                 ({cand.date_offset_days > 0 ? `+${cand.date_offset_days}` : cand.date_offset_days}d offset)
//                               </span>
//                             )}
//                           </div>

//                           <p
//                             className="font-mono text-[11px] text-slate-200 line-clamp-2 break-all leading-tight"
//                             title={cleanNarration}
//                           >
//                             {cleanNarration}
//                           </p>
//                         </div>
//                       </div>

//                       <div className="flex shrink-0 flex-col items-end justify-between pl-2 border-l border-slate-800">
//                         <div className="font-mono text-xs font-bold text-emerald-400">
//                           ₹{amountVal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
//                         </div>

//                         {isBoundToAsset ? (
//                           <button
//                             type="button"
//                             onClick={() => handleUnmap(cand)}
//                             disabled={binding}
//                             className="mt-1.5 rounded bg-rose-600/80 px-2.5 py-1 text-[10px] font-bold text-white hover:bg-rose-500 disabled:opacity-50 cursor-pointer transition-colors font-mono"
//                           >
//                             {binding ? 'Working...' : 'Disconnect'}
//                           </button>
//                         ) : (
//                           <button
//                             type="button"
//                             onClick={() => handleBatchBind(cand)}
//                             disabled={binding}
//                             className="mt-1.5 rounded bg-emerald-600 px-2.5 py-1 text-[10px] font-bold text-white hover:bg-emerald-500 disabled:opacity-50 cursor-pointer transition-colors font-mono"
//                           >
//                             {binding ? 'Binding...' : '⚡ Bind'}
//                           </button>
//                         )}
//                       </div>
//                     </div>
//                   );
//                 })}
//               </div>
//             </div>
//           )}
//         </div>

//         {/* User Note Field */}
// {/* Bottom Action Footer */}
// <div className="mt-4 flex items-center justify-between border-t border-slate-800 pt-3">
//   <div className="flex-1 mr-3">
//     <input
//       type="text"
//       placeholder="Audit Note (e.g. Cleared via KSEB Online Portal / Trivandrum Corp)"
//       value={userNote}
//       onChange={(e) => setUserNote(e.target.value)}
//       className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none font-mono"
//     />
//   </div>

//   <button
//     type="button"
//     onClick={handleSaveAndSync}
//     disabled={binding}
//     className="rounded-lg bg-emerald-600 px-4 py-1.5 text-xs font-bold text-white hover:bg-emerald-500 disabled:opacity-50 transition-colors cursor-pointer font-mono whitespace-nowrap"
//   >
//     {binding ? 'Updating...' : '💾 Save & Sync Cost Basis'}
//   </button>
// </div>
//       </div>
//     </div>
//   );
// };


// import React, { useState, useEffect } from 'react';
// import {
//   subledgerApi,
//   type CandidateMatchResult,
//   type AssetComplianceSchedule,
//   type AssetSubLedgerNode,
//   type AssetOperationalAccount,
// } from '../../api/subledger';

// interface CandidateMatcherModalProps {
//   isOpen: boolean;
//   onClose: () => void;
//   asset: AssetSubLedgerNode;
//   schedule?: AssetComplianceSchedule | null;
//   utility?: AssetOperationalAccount | null;
//   onSuccess: () => void;
// }

// export const CandidateMatcherModal: React.FC<CandidateMatcherModalProps> = ({
//   isOpen,
//   onClose,
//   asset,
//   schedule,
//   utility,
//   onSuccess,
// }) => {
//   // Query Form State
//   const [documentDate, setDocumentDate] = useState<string>('');
//   const [targetAmount, setTargetAmount] = useState<number | string>('');
//   const [keywords, setKeywords] = useState<string>('');
//   const [dayWindow, setDayWindow] = useState<number>(30); // Default to 30D

//   // Engine State
//   const [loading, setLoading] = useState<boolean>(false);
//   const [binding, setBinding] = useState<boolean>(false);
//   const [candidates, setCandidates] = useState<CandidateMatchResult[]>([]);
//   const [selectedRowIds, setSelectedRowIds] = useState<string[]>([]);
//   const [isCash, setIsCash] = useState<boolean>(false);
//   const [userNote, setUserNote] = useState<string>('');
//   const [error, setError] = useState<string | null>(null);

//   // Preset search horizon definitions
//   const horizonPresets = [
//     { label: '30D', value: 30 },
//     { label: '60D', value: 60 },
//     { label: '90D', value: 90 },
//     { label: '6M', value: 180 },
//     { label: '1Y', value: 365 },
//     { label: '2Y', value: 730 },
//     { label: 'Till Today', value: 1825 }, // ~5 years
//   ];

//   // Isolated ESC Key Listener
//   useEffect(() => {
//     const handleKeyDown = (e: KeyboardEvent) => {
//       if (e.key === 'Escape') {
//         e.stopPropagation();
//         onClose();
//       }
//     };
//     if (isOpen) window.addEventListener('keydown', handleKeyDown);
//     return () => window.removeEventListener('keydown', handleKeyDown);
//   }, [isOpen, onClose]);

//   // 🎯 Auto-initialize defaults and trigger candidate scan when modal opens
//   useEffect(() => {
//     if (isOpen && asset) {
//       const initialDate =
//         schedule?.due_date ||
//         asset.acquisition_date ||
//         new Date().toISOString().split('T')[0];

//       const initialAmount =
//         schedule?.expected_amount ||
//         (utility ? '' : asset.acquisition_cost) ||
//         '';

//       const initialKeywords = utility?.matching_keyword
//         ? utility.matching_keyword
//         : asset.name;

//       setDocumentDate(initialDate);
//       setTargetAmount(initialAmount);
//       setKeywords(initialKeywords);
//       setError(null);
//       setIsCash(false);
//       setUserNote('');
//       setSelectedRowIds([]);

//       runScan(initialDate, initialAmount, initialKeywords, dayWindow);
//     } else {
//       setCandidates([]);
//       setSelectedRowIds([]);
//       setError(null);
//     }
//   }, [isOpen, asset?.id, schedule?.id, utility?.id]);

//   // 🔍 Core Candidate Matcher Request Runner
//   const runScan = async (
//     docDate: string,
//     amt: number | string,
//     kwString: string,
//     windowDays: number
//   ) => {
//     setLoading(true);
//     setError(null);
//     setSelectedRowIds([]);

//     let formattedDate = docDate;
//     if (docDate && docDate.includes('-')) {
//       const parts = docDate.split('-');
//       if (parts[0].length === 2 && parts[2].length === 4) {
//         formattedDate = `${parts[2]}-${parts[1]}-${parts[0]}`;
//       }
//     }

//     const kwArray = kwString
//       ? kwString
//           .split(',')
//           .map((k) => k.trim())
//           .filter(Boolean)
//       : [];

//     const parsedAmount = Number(amt);
//     const cleanAmount =
//       !isNaN(parsedAmount) && parsedAmount > 0 ? parsedAmount : null;

//     const payload = {
//       asset_id: asset.id,
//       document_date: formattedDate,
//       target_amount: cleanAmount,
//       day_window: windowDays,
//       keywords: kwArray,
//     };

//     try {
//       const response = await subledgerApi.findCandidates(payload);
//       const candidateList = response.candidates || [];
//       setCandidates(candidateList);
//     } catch (err: any) {
//       console.error('Candidate fetch failed:', err.response?.data || err);
//       const serverDetails = err.response?.data
//         ? typeof err.response.data === 'object'
//           ? JSON.stringify(err.response.data)
//           : String(err.response.data)
//         : null;

//       setError(
//         serverDetails
//           ? `Scan Failed: ${serverDetails}`
//           : 'Failed to fetch matching candidate rows from staging.'
//       );
//       setCandidates([]);
//     } finally {
//       setLoading(false);
//     }
//   };

//   // ⚡ Handle Unmapping an already-bound transaction
//   const handleUnmap = async (cand: CandidateMatchResult) => {
//     if (!cand.mapping_info?.mapping_id) return;
//     setBinding(true);
//     setError(null);

//     try {
//       await subledgerApi.unmapTransaction({
//         mapping_id: cand.mapping_info.mapping_id,
//       });

//       runScan(documentDate, targetAmount, keywords, dayWindow);
//       onSuccess();
//     } catch (err: any) {
//       console.error('Unmapping failed:', err);
//       setError('Failed to unmap transaction.');
//     } finally {
//       setBinding(false);
//     }
//   };

//   const handleSearchSubmit = (e: React.FormEvent) => {
//     e.preventDefault();
//     runScan(documentDate, targetAmount, keywords, dayWindow);
//   };

//   const toggleSelectRow = (rowId: string) => {
//     setSelectedRowIds((prev) =>
//       prev.includes(rowId) ? prev.filter((id) => id !== rowId) : [...prev, rowId]
//     );
//   };

//   const toggleSelectAll = () => {
//     const unmappedCandidates = candidates.filter((c) => !c.is_mapped_to_this_asset);
//     if (selectedRowIds.length === unmappedCandidates.length) {
//       setSelectedRowIds([]);
//     } else {
//       setSelectedRowIds(unmappedCandidates.map((c) => c.row_identifier));
//     }
//   };

//   const selectedTotalSum = candidates
//     .filter((c) => selectedRowIds.includes(c.row_identifier))
//     .reduce((acc, curr) => acc + Number(curr.debit || curr.credit || 0), 0);

//   const handleBatchBind = async (targetCandidate?: CandidateMatchResult) => {
//     setBinding(true);
//     setError(null);

//     const rowsToBind = targetCandidate
//       ? [targetCandidate]
//       : candidates.filter((c) => selectedRowIds.includes(c.row_identifier));

//     if (rowsToBind.length === 0 && !isCash) {
//       setError('Please select at least one candidate row to bind.');
//       setBinding(false);
//       return;
//     }

//     try {
//       for (const cand of rowsToBind) {
//         let formattedDate = cand.transaction_date || documentDate;
//         if (formattedDate.includes('-')) {
//           const parts = formattedDate.split('-');
//           if (parts[0].length === 2 && parts[2].length === 4) {
//             formattedDate = `${parts[2]}-${parts[1]}-${parts[0]}`;
//           }
//         }

//         await subledgerApi.bindTransaction({
//           asset_id: asset.id,
//           schedule_id: schedule?.id || null,
//           operational_account_id:
//             utility?.id || asset.operational_accounts?.[0]?.id || null,
//           row_identifier: isCash ? null : cand.row_identifier,
//           is_cash_entry: isCash,
//           transaction_date: formattedDate,
//           amount: cand.debit || cand.credit || Number(targetAmount) || 0,
//           transaction_purpose: schedule?.schedule_type || 'SUB_LEDGER_PAYMENT',
//           user_note: userNote || `Reconciled via Candidate Matcher UI`,
//         });
//       }

//       onSuccess();
//       onClose();
//     } catch (err: any) {
//       console.error('Binding failed:', err.response?.data || err);
//       const serverDetails = err.response?.data
//         ? typeof err.response.data === 'object'
//           ? JSON.stringify(err.response.data)
//           : String(err.response.data)
//         : null;

//       setError(
//         serverDetails
//           ? `Binding Failed: ${serverDetails}`
//           : 'Failed to bind transaction(s). Please check server logs.'
//       );
//     } finally {
//       setBinding(false);
//     }
//   };

//   if (!isOpen) return null;

//   const unmappedCandidates = candidates.filter((c) => !c.is_mapped_to_this_asset);

//   return (
//     <div 
//       className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
//       onClick={(e) => {
//         e.stopPropagation();
//         onClose();
//       }}
//     >
//       <div 
//         className="w-full max-w-3xl rounded-xl border border-slate-800 bg-slate-900 p-6 shadow-2xl text-slate-100 font-sans"
//         onClick={(e) => e.stopPropagation()}
//       >
//         {/* Modal Header */}
//         <div className="flex items-start justify-between border-b border-slate-800 pb-4">
//           <div>
//             <span className="text-xs font-semibold tracking-wider text-emerald-400 uppercase font-mono">
//               Sub-Ledger Post-Facto Reconciler
//             </span>
//             <h2 className="text-xl font-bold text-white">
//               {schedule?.title || utility?.provider_name || asset.name}
//             </h2>
//             <p className="text-xs text-slate-400">
//               Asset Code: <span className="font-mono text-slate-200">{asset.asset_code}</span>
//               {utility && (
//                 <span className="ml-2 text-emerald-400 font-mono">
//                   • Target Utility: {utility.provider_name} ({utility.consumer_identifier})
//                 </span>
//               )}
//             </p>
//           </div>
//           <button
//             type="button"
//             onClick={(e) => {
//               e.stopPropagation();
//               onClose();
//             }}
//             className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white cursor-pointer transition-colors"
//           >
//             ✕
//           </button>
//         </div>

//         {/* Form Controls */}
//         <form onSubmit={handleSearchSubmit} className="mt-4 grid grid-cols-12 gap-3">
//           <div className="col-span-12 md:col-span-3">
//             <label className="block text-xs font-medium text-slate-400">Document Date</label>
//             <input
//               type="date"
//               value={documentDate}
//               onChange={(e) => setDocumentDate(e.target.value)}
//               className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none font-mono"
//             />
//           </div>

//           <div className="col-span-12 md:col-span-3">
//             <label className="block text-xs font-medium text-slate-400">Target Amount (₹)</label>
//             <input
//               type="number"
//               step="0.01"
//               placeholder="0.00"
//               value={targetAmount}
//               onChange={(e) => setTargetAmount(e.target.value)}
//               className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none font-mono"
//             />
//           </div>

//           <div className="col-span-12 md:col-span-4">
//             <label className="block text-xs font-medium text-slate-400">Matching Keywords</label>
//             <input
//               type="text"
//               placeholder="e.g. KSEB, ULLOOR, TAX"
//               value={keywords}
//               onChange={(e) => setKeywords(e.target.value)}
//               className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none font-mono"
//             />
//           </div>

//           <div className="col-span-12 md:col-span-2 flex items-end">
//             <button
//               type="submit"
//               disabled={loading}
//               className="w-full rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 cursor-pointer transition-colors"
//             >
//               {loading ? 'Scanning...' : 'Re-Scan'}
//             </button>
//           </div>

//           {/* Preset Horizon Pill Bar */}
//           <div className="col-span-12 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-800/50 px-3 py-2">
//             <div className="flex flex-wrap items-center gap-2">
//               <span className="text-xs text-slate-400 font-medium">Search Horizon:</span>
//               <div className="flex flex-wrap items-center gap-1">
//                 {horizonPresets.map((preset) => (
//                   <button
//                     key={preset.value}
//                     type="button"
//                     onClick={() => {
//                       setDayWindow(preset.value);
//                       runScan(documentDate, targetAmount, keywords, preset.value);
//                     }}
//                     className={`rounded px-2.5 py-1 font-mono text-[11px] font-bold cursor-pointer transition-all ${
//                       dayWindow === preset.value
//                         ? 'bg-emerald-500 text-slate-950 shadow-sm scale-105'
//                         : 'bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white'
//                     }`}
//                   >
//                     {preset.label}
//                   </button>
//                 ))}
//               </div>
//             </div>

//             <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer select-none">
//               <input
//                 type="checkbox"
//                 checked={isCash}
//                 onChange={(e) => setIsCash(e.target.checked)}
//                 className="rounded accent-emerald-500 cursor-pointer"
//               />
//               Direct Cash / Manual Payment
//             </label>
//           </div>
//         </form>

//         {error && (
//           <div className="mt-3 rounded-lg bg-rose-500/10 p-3 text-xs text-rose-400 border border-rose-500/20 font-mono">
//             {error}
//           </div>
//         )}

//         {/* Results Area */}
//         <div className="mt-4 max-h-72 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950 p-3">
//           {isCash ? (
//             <div className="p-4 text-center">
//               <p className="text-sm font-semibold text-amber-400">Manual Cash Entry Mode Selected</p>
//               <p className="text-xs text-slate-400 mt-1">
//                 This transaction will be logged directly to the asset sub-ledger without linking to bank statement staging lines.
//               </p>
//               <button
//                 type="button"
//                 onClick={() => handleBatchBind()}
//                 disabled={binding}
//                 className="mt-4 rounded-lg bg-amber-600 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-500 disabled:opacity-50 cursor-pointer transition-colors"
//               >
//                 {binding ? 'Binding Cash Entry...' : 'Confirm Cash Payment & Clear Due'}
//               </button>
//             </div>
//           ) : loading ? (
//             <div className="p-8 text-center text-sm text-slate-400 font-mono">
//               ⚡ Running candidate lookup & staging matcher...
//             </div>
//           ) : candidates.length === 0 ? (
//             <div className="p-8 text-center text-sm text-slate-400 font-mono">
//               No matching bank staging rows found for "{keywords}" within the selected window.
//               <br />
//               <span className="text-xs text-slate-500">
//                 Try broadening keywords or selecting a larger search horizon (e.g. 6M, 1Y, Till Today).
//               </span>
//             </div>
//           ) : (
//             <div>
//               {/* Batch Action Header Bar */}
//               <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800 text-xs px-1">
//                 <label className="flex items-center gap-2 cursor-pointer select-none text-slate-400 font-mono">
//                   <input
//                     type="checkbox"
//                     checked={
//                       unmappedCandidates.length > 0 &&
//                       selectedRowIds.length === unmappedCandidates.length
//                     }
//                     onChange={toggleSelectAll}
//                     className="rounded accent-emerald-500 cursor-pointer"
//                   />
//                   <span>
//                     Select Unmapped ({selectedRowIds.length}/{unmappedCandidates.length})
//                   </span>
//                 </label>

//                 {selectedRowIds.length > 0 && (
//                   <div className="flex items-center gap-2 font-mono text-emerald-400 font-semibold">
//                     <span>Selected Total:</span>
//                     <span className="bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded">
//                       ₹{selectedTotalSum.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
//                     </span>
//                   </div>
//                 )}

//                 {selectedRowIds.length > 0 && (
//                   <button
//                     type="button"
//                     onClick={() => handleBatchBind()}
//                     disabled={binding}
//                     className="rounded bg-emerald-600 px-3 py-1 text-[11px] font-bold text-white hover:bg-emerald-500 disabled:opacity-50 transition-colors cursor-pointer"
//                   >
//                     {binding ? 'Binding...' : `⚡ Bind Selected (${selectedRowIds.length})`}
//                   </button>
//                 )}
//               </div>

//               {/* Candidate Cards */}
//               <div className="space-y-2">
//                 {candidates.map((cand) => {
//                   const getCleanNarration = () => {
//                     if (!cand.remarks) return 'No narration details';
//                     if (typeof cand.remarks === 'string') {
//                       try {
//                         const parsed = JSON.parse(cand.remarks);
//                         return (
//                           parsed.display_text ||
//                           parsed.narration ||
//                           parsed.payee ||
//                           cand.remarks
//                         );
//                       } catch {
//                         return cand.remarks;
//                       }
//                     }
//                     return (
//                       cand.remarks.display_text ||
//                       cand.remarks.narration ||
//                       cand.remarks.payee ||
//                       JSON.stringify(cand.remarks)
//                     );
//                   };

//                   const cleanNarration = getCleanNarration();
//                   const amountVal = Number(cand.debit || cand.credit || 0);
//                   const isChecked = selectedRowIds.includes(cand.row_identifier);
//                   const isBoundToAsset = cand.is_mapped_to_this_asset;

//                   return (
//                     <div
//                       key={cand.row_identifier}
//                       className={`flex items-center justify-between gap-3 rounded-lg border p-2.5 transition-colors ${
//                         isBoundToAsset
//                           ? 'border-cyan-500/50 bg-cyan-500/5'
//                           : isChecked
//                           ? 'border-emerald-500 bg-emerald-500/5'
//                           : 'border-slate-800 bg-slate-900 hover:border-slate-700'
//                       }`}
//                     >
//                       <div className="flex items-start gap-2.5 min-w-0 flex-1">
//                         {!isBoundToAsset && (
//                           <input
//                             type="checkbox"
//                             checked={isChecked}
//                             onChange={() => toggleSelectRow(cand.row_identifier)}
//                             className="mt-1 rounded accent-emerald-500 cursor-pointer"
//                           />
//                         )}

//                         <div className="min-w-0 flex-1 space-y-1">
//                           <div className="flex items-center gap-2">
//                             {isBoundToAsset ? (
//                               <span className="rounded px-1.5 py-0.5 font-mono text-[10px] font-bold bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">
//                                 BOUND TO ASSET
//                               </span>
//                             ) : (
//                               <span
//                                 className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-bold ${
//                                   cand.probability_score >= 80
//                                     ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
//                                     : 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
//                                 }`}
//                               >
//                                 {cand.probability_score}% MATCH
//                               </span>
//                             )}

//                             <span className="font-mono text-[11px] font-semibold text-slate-300">
//                               {cand.transaction_date}
//                             </span>
                            
//                             {!isBoundToAsset && (
//                               <span className="text-[10px] text-slate-500 font-mono">
//                                 ({cand.date_offset_days > 0 ? `+${cand.date_offset_days}` : cand.date_offset_days}d offset)
//                               </span>
//                             )}
//                           </div>

//                           <p
//                             className="font-mono text-[11px] text-slate-200 line-clamp-2 break-all leading-tight"
//                             title={cleanNarration}
//                           >
//                             {cleanNarration}
//                           </p>
//                         </div>
//                       </div>

//                       <div className="flex shrink-0 flex-col items-end justify-between pl-2 border-l border-slate-800">
//                         <div className="font-mono text-xs font-bold text-emerald-400">
//                           ₹{amountVal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
//                         </div>

//                         {isBoundToAsset ? (
//                           <button
//                             type="button"
//                             onClick={() => handleUnmap(cand)}
//                             disabled={binding}
//                             className="mt-1.5 rounded bg-rose-600/80 px-2.5 py-1 text-[10px] font-bold text-white hover:bg-rose-500 disabled:opacity-50 cursor-pointer transition-colors font-mono"
//                           >
//                             {binding ? 'Working...' : 'Disconnect'}
//                           </button>
//                         ) : (
//                           <button
//                             type="button"
//                             onClick={() => handleBatchBind(cand)}
//                             disabled={binding}
//                             className="mt-1.5 rounded bg-emerald-600 px-2.5 py-1 text-[10px] font-bold text-white hover:bg-emerald-500 disabled:opacity-50 cursor-pointer transition-colors font-mono"
//                           >
//                             {binding ? 'Binding...' : '⚡ Bind'}
//                           </button>
//                         )}
//                       </div>
//                     </div>
//                   );
//                 })}
//               </div>
//             </div>
//           )}
//         </div>

//         {/* User Note Field */}
//         <div className="mt-4">
//           <input
//             type="text"
//             placeholder="Audit Note (e.g. Cleared via KSEB Online Portal / Trivandrum Corp)"
//             value={userNote}
//             onChange={(e) => setUserNote(e.target.value)}
//             className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none font-mono"
//           />
//         </div>
//       </div>
//     </div>
//   );
// };