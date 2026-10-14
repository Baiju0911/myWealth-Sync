// webapp/src/components/subledger/CandidateMatcherModal.tsx
import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import type {
  AssetComplianceSchedule,
  AssetSubLedgerNode,
  AssetOperationalAccount,
} from '../../api/subledger';
import { CandidateFilterBar } from './candidatematcher/CandidateFilterbar';
import { CandidateBatchToolbar } from './candidatematcher/CandidateBatchToolbar';
import { CandidateCardItem } from './candidatematcher/CandidateCardItem';
import { extractVendorTokenFromNode } from '../../utils/classificationHelpers';
import { useCandidateMatching } from '../../hooks/useCandidatematching';

export interface TaxonomyMatchContext {
  category: string;
  subcategory: string;
  defaultAmount?: number | string;
  defaultKeyword?: string;
  rowIdentifier?: string;
  transactionDate?: string;
  stagedItems?: any[];
  selectedRowIds?: string[];
}

interface CandidateMatcherModalProps {
  isOpen: boolean;
  onClose: () => void;
  asset?: AssetSubLedgerNode | null;
  accountId?: number | string | null;
  taxonomyContext?: TaxonomyMatchContext | null;
  schedule?: AssetComplianceSchedule | null;
  utility?: AssetOperationalAccount | null;
  onSuccess: () => void;
}

export const CandidateMatcherModal: React.FC<CandidateMatcherModalProps> = (props) => {
  const { isOpen, onClose, asset, schedule, utility, taxonomyContext } = props;

  const {
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
  } = useCandidateMatching(props);

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

  if (!isOpen) return null;

  const activeNode = selectedBindingAsset || asset;
  const activeVendorName =
    (typeof activeNode?.vendor === 'object' && activeNode?.vendor !== null
      ? (activeNode.vendor as { name?: string }).name
      : typeof activeNode?.vendor === 'string'
      ? activeNode.vendor
      : '') ||
    (activeNode ? extractVendorTokenFromNode(activeNode) : '');

  return createPortal(
    <div
      className="fixed inset-0 z-10000 flex items-center justify-center bg-slate-950/85 p-4 backdrop-blur-md"
      onClick={(e) => {
        e.stopPropagation();
        onClose();
      }}
    >
      <div
        className="w-full max-w-4xl rounded-xl border border-slate-800 bg-slate-900 p-6 shadow-2xl text-slate-100 font-sans max-h-[92vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-800 pb-3 shrink-0">
          <div>
            <span className="text-xs font-semibold tracking-wider text-emerald-400 uppercase font-mono">
              Subledger Attribution & Reconciliation
            </span>

            <div className="flex items-center gap-2 mt-0.5">
              <h2 className="text-lg font-bold text-white">
                {schedule?.title ||
                  utility?.provider_name ||
                  activeNode?.name ||
                  taxonomyContext?.subcategory ||
                  'Attribution Scanner'}
              </h2>
              {activeVendorName && (
                <span className="rounded bg-emerald-500/10 px-2 py-0.5 text-xs font-semibold text-emerald-400 border border-emerald-500/30 font-mono">
                  {activeVendorName}
                </span>
              )}
            </div>

            {displayedNodes.length > 0 && (
              <div className="mt-2 flex items-center gap-2 text-xs">
                <span className="text-slate-400 font-mono">Target Folio:</span>
                <select
                  value={selectedBindingAsset?.id || ''}
                  onChange={(e) => handleFolioChange(e.target.value)}
                  className="rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-emerald-300 font-bold font-mono focus:border-emerald-500 focus:outline-none cursor-pointer"
                >
                  {!asset && <option value="">── All Folios (Unfiltered) ──</option>}
                  {displayedNodes.map((n) => {
                    const vName = extractVendorTokenFromNode(n);
                    return (
                      <option key={n.id} value={n.id}>
                        [{n.asset_code}] {n.name} {vName ? `[${vName}]` : ''} — ₹
                        {Number(n.current_valuation || 0).toLocaleString('en-IN')}
                      </option>
                    );
                  })}
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

        {/* Filter Bar */}
        <CandidateFilterBar
          documentDate={documentDate}
          setDocumentDate={setDocumentDate}
          targetAmount={targetAmount}
          setTargetAmount={setTargetAmount}
          keywords={keywords}
          setKeywords={setKeywords}
          dayWindow={dayWindow}
          onSelectHorizon={(d) => {
            setDayWindow(d);
            runScan(selectedBindingAsset?.id, documentDate, targetAmount, keywords, d);
          }}
          syncAcquisitionCost={syncAcquisitionCost}
          setSyncAcquisitionCost={setSyncAcquisitionCost}
          isCash={isCash}
          setIsCash={setIsCash}
          loading={loading}
          onSearch={handleSearchSubmit}
        />

        {error && (
          <div className="mt-2 rounded bg-rose-500/10 p-2 text-xs text-rose-400 border border-rose-500/20 font-mono shrink-0">
            {error}
          </div>
        )}

        {/* Results Body: Scrollable container holding sticky toolbar and list */}
        <div className="mt-3 flex-1 overflow-y-auto rounded-lg border border-slate-800 bg-slate-950 min-h-0 relative">
          {isCash ? (
            <div className="p-4 text-center font-mono">
              <p className="text-sm font-semibold text-amber-400">Manual Cash Entry Mode Selected</p>
              <p className="text-xs text-slate-400 mt-1">
                This transaction will be logged directly to the asset sub-ledger without linking to bank statement staging lines.
              </p>
              <button
                type="button"
                onClick={() => handleBatchBind()}
                disabled={binding}
                className="mt-3 rounded bg-amber-600 px-3.5 py-1.5 text-xs font-bold text-white hover:bg-amber-500 disabled:opacity-50 cursor-pointer font-mono"
              >
                {binding ? 'Binding Cash Entry...' : 'Confirm Cash Payment & Clear Due'}
              </button>
            </div>
          ) : loading ? (
            <div className="p-8 text-center text-xs text-slate-400 font-mono">
              ⚡ Running candidate lookup & staging matcher...
            </div>
          ) : candidates.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-400 font-mono">
              No matching bank staging rows found for "{keywords}" within the selected window.
            </div>
          ) : (
            <div>
              {/* Sticky Batch Toolbar */}
              <CandidateBatchToolbar
                unmappedCount={unmappedCandidates.length}
                selectedCount={
                  selectedRowIds.filter((id) =>
                    unmappedCandidates.some((c) => c.row_identifier === id)
                  ).length
                }
                allUnmappedSelected={
                  unmappedCandidates.length > 0 &&
                  unmappedCandidates.every((c) => selectedRowIds.includes(c.row_identifier))
                }
                selectedTotalSum={selectedTotalSum}
                binding={binding}
                onToggleSelectAll={toggleSelectAll}
                onBatchBind={() => handleBatchBind()}
              />

              {/* Scrollable Candidate Cards */}
              <div className="p-3 space-y-1.5">
                {candidates.map((cand) => (
                  <CandidateCardItem
                    key={cand.row_identifier}
                    cand={cand}
                    isSelected={selectedRowIds.includes(cand.row_identifier)}
                    keywords={keywords}
                    binding={binding}
                    onToggleSelect={toggleSelectRow}
                    onSingleBind={(c) => handleBatchBind(c)}
                    onUnmap={handleUnmap}
                  />
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="mt-3 flex items-center justify-between border-t border-slate-800 pt-2.5 shrink-0">
          <div className="flex-1 mr-3">
            <input
              type="text"
              placeholder={`Audit Note (e.g. Attributed to ${selectedBindingAsset?.name || 'subledger'} via Bank Staging line)...`}
              value={userNote}
              onChange={(e) => setUserNote(e.target.value)}
              className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-1 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none font-mono"
            />
          </div>

          <button
            type="button"
            onClick={handleSaveAndSync}
            disabled={binding}
            className="rounded bg-emerald-600 px-3.5 py-1 text-xs font-bold text-white hover:bg-emerald-500 disabled:opacity-50 transition-colors cursor-pointer font-mono whitespace-nowrap"
          >
            {binding ? 'Saving...' : '💾 Save & Sync Cost Basis'}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};