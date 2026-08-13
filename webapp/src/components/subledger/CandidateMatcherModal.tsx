import React, { useState, useEffect } from 'react';
import {
  subledgerApi,
  type CandidateMatchResult,
  type AssetComplianceSchedule,
  type AssetSubLedgerNode,
  type AssetOperationalAccount,
} from '../../api/subledger';

interface CandidateMatcherModalProps {
  isOpen: boolean;
  onClose: () => void;
  asset: AssetSubLedgerNode;
  schedule?: AssetComplianceSchedule | null;
  utility?: AssetOperationalAccount | null;
  onSuccess: () => void;
}

export const CandidateMatcherModal: React.FC<CandidateMatcherModalProps> = ({
  isOpen,
  onClose,
  asset,
  schedule,
  utility,
  onSuccess,
}) => {
  // Query Form State
  const [documentDate, setDocumentDate] = useState<string>('');
  const [targetAmount, setTargetAmount] = useState<number | string>('');
  const [keywords, setKeywords] = useState<string>('');
  const [dayWindow, setDayWindow] = useState<number>(10);

  // Engine State
  const [loading, setLoading] = useState<boolean>(false);
  const [binding, setBinding] = useState<boolean>(false);
  const [candidates, setCandidates] = useState<CandidateMatchResult[]>([]);
  const [selectedRowIds, setSelectedRowIds] = useState<string[]>([]);
  const [isCash, setIsCash] = useState<boolean>(false);
  const [userNote, setUserNote] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  // 🎯 Auto-initialize defaults and trigger candidate scan when modal opens
  useEffect(() => {
    if (isOpen && asset) {
      const initialDate =
        schedule?.due_date ||
        asset.acquisition_date ||
        new Date().toISOString().split('T')[0];

      const initialAmount =
        schedule?.expected_amount ||
        (utility ? '' : asset.acquisition_cost) ||
        '';

      const initialKeywords = utility?.matching_keyword
        ? utility.matching_keyword
        : asset.name;

      setDocumentDate(initialDate);
      setTargetAmount(initialAmount);
      setKeywords(initialKeywords);
      setError(null);
      setIsCash(false);
      setUserNote('');
      setSelectedRowIds([]);

      runScan(initialDate, initialAmount, initialKeywords, dayWindow);
    } else {
      setCandidates([]);
      setSelectedRowIds([]);
      setError(null);
    }
  }, [isOpen, asset?.id, schedule?.id, utility?.id]);

  // 🔍 Core Candidate Matcher Request Runner
  const runScan = async (
    docDate: string,
    amt: number | string,
    kwString: string,
    windowDays: number
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
    const cleanAmount =
      !isNaN(parsedAmount) && parsedAmount > 0 ? parsedAmount : null;

    // 🎯 Pass asset_id so backend pulls already-bound records directly
    const payload = {
      asset_id: asset.id,
      document_date: formattedDate,
      target_amount: cleanAmount,
      day_window: windowDays,
      keywords: kwArray,
    };

    try {
      const response = await subledgerApi.findCandidates(payload);
      const candidateList = response.candidates || [];
      setCandidates(candidateList);
    } catch (err: any) {
      console.error('Candidate fetch failed:', err.response?.data || err);
      const serverDetails = err.response?.data
        ? typeof err.response.data === 'object'
          ? JSON.stringify(err.response.data)
          : String(err.response.data)
        : null;

      setError(
        serverDetails
          ? `Scan Failed: ${serverDetails}`
          : 'Failed to fetch matching candidate rows from staging.'
      );
      setCandidates([]);
    } finally {
      setLoading(false);
    }
  };

  // ⚡ Handle Unmapping an already-bound transaction
  const handleUnmap = async (cand: CandidateMatchResult) => {
    if (!cand.mapping_info?.mapping_id) return;
    setBinding(true);
    setError(null);

    try {
      await subledgerApi.unmapTransaction({
        mapping_id: cand.mapping_info.mapping_id,
      });

      // Refresh list after unmapping
      runScan(documentDate, targetAmount, keywords, dayWindow);
      onSuccess();
    } catch (err: any) {
      console.error('Unmapping failed:', err);
      setError('Failed to unmap transaction.');
    } finally {
      setBinding(false);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    runScan(documentDate, targetAmount, keywords, dayWindow);
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

  // 🧮 Compute total sum of checked candidate rows
  const selectedTotalSum = candidates
    .filter((c) => selectedRowIds.includes(c.row_identifier))
    .reduce((acc, curr) => acc + Number(curr.debit || curr.credit || 0), 0);

  // ⚡ Single or Multi-Row Batch Bind Handler
  const handleBatchBind = async (targetCandidate?: CandidateMatchResult) => {
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
        let formattedDate = cand.transaction_date || documentDate;
        if (formattedDate.includes('-')) {
          const parts = formattedDate.split('-');
          if (parts[0].length === 2 && parts[2].length === 4) {
            formattedDate = `${parts[2]}-${parts[1]}-${parts[0]}`;
          }
        }

        await subledgerApi.bindTransaction({
          asset_id: asset.id,
          schedule_id: schedule?.id || null,
          operational_account_id:
            utility?.id || asset.operational_accounts?.[0]?.id || null,
          row_identifier: isCash ? null : cand.row_identifier,
          is_cash_entry: isCash,
          transaction_date: formattedDate,
          amount: cand.debit || cand.credit || Number(targetAmount) || 0,
          transaction_purpose: schedule?.schedule_type || 'SUB_LEDGER_PAYMENT',
          user_note: userNote || `Reconciled via Candidate Matcher UI`,
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

      setError(
        serverDetails
          ? `Binding Failed: ${serverDetails}`
          : 'Failed to bind transaction(s). Please check server logs.'
      );
    } finally {
      setBinding(false);
    }
  };

  if (!isOpen) return null;

  const unmappedCandidates = candidates.filter((c) => !c.is_mapped_to_this_asset);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm">
      <div className="w-full max-w-3xl rounded-xl border border-slate-800 bg-slate-900 p-6 shadow-2xl text-slate-100">
        {/* Modal Header */}
        <div className="flex items-start justify-between border-b border-slate-800 pb-4">
          <div>
            <span className="text-xs font-semibold tracking-wider text-emerald-400 uppercase">
              Sub-Ledger Post-Facto Reconciler
            </span>
            <h2 className="text-xl font-bold text-white">
              {schedule?.title || utility?.provider_name || asset.name}
            </h2>
            <p className="text-xs text-slate-400">
              Asset Code: <span className="font-mono text-slate-200">{asset.asset_code}</span>
              {utility && (
                <span className="ml-2 text-emerald-400">
                  • Target Utility: {utility.provider_name} ({utility.consumer_identifier})
                </span>
              )}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
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
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
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
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
            />
          </div>

          <div className="col-span-12 md:col-span-4">
            <label className="block text-xs font-medium text-slate-400">Matching Keywords</label>
            <input
              type="text"
              placeholder="e.g. KSEB, ULLOOR, TAX"
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
            />
          </div>

          <div className="col-span-12 md:col-span-2 flex items-end">
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
            >
              {loading ? 'Scanning...' : 'Re-Scan'}
            </button>
          </div>

          {/* Sliding Day Window Slider */}
          <div className="col-span-12 flex items-center justify-between rounded-lg bg-slate-800/50 px-3 py-2">
            <div className="flex items-center gap-3">
              <span className="text-xs text-slate-400">Sliding Date Window:</span>
              <input
                type="range"
                min="3"
                max="30"
                value={dayWindow}
                onChange={(e) => {
                  const val = Number(e.target.value);
                  setDayWindow(val);
                  runScan(documentDate, targetAmount, keywords, val);
                }}
                className="accent-emerald-500 cursor-pointer"
              />
              <span className="font-mono text-xs text-emerald-400">±{dayWindow} days</span>
            </div>
            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={isCash}
                onChange={(e) => setIsCash(e.target.checked)}
                className="rounded accent-emerald-500"
              />
              Direct Cash / Manual Payment
            </label>
          </div>
        </form>

        {error && (
          <div className="mt-3 rounded-lg bg-rose-500/10 p-3 text-xs text-rose-400 border border-rose-500/20 font-mono">
            {error}
          </div>
        )}

        {/* Results Area */}
        <div className="mt-4 max-h-72 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950 p-3">
          {isCash ? (
            <div className="p-4 text-center">
              <p className="text-sm font-semibold text-amber-400">Manual Cash Entry Mode Selected</p>
              <p className="text-xs text-slate-400 mt-1">
                This transaction will be logged directly to the asset sub-ledger without linking to bank statement staging lines.
              </p>
              <button
                onClick={() => handleBatchBind()}
                disabled={binding}
                className="mt-4 rounded-lg bg-amber-600 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-500 disabled:opacity-50"
              >
                {binding ? 'Binding Cash Entry...' : 'Confirm Cash Payment & Clear Due'}
              </button>
            </div>
          ) : loading ? (
            <div className="p-8 text-center text-sm text-slate-400">
              ⚡ Running candidate lookup & staging matcher...
            </div>
          ) : candidates.length === 0 ? (
            <div className="p-8 text-center text-sm text-slate-400">
              No matching bank staging rows found for "{keywords}" within ±{dayWindow} days.
              <br />
              <span className="text-xs text-slate-500">
                Try broadening keywords or increasing the sliding date window.
              </span>
            </div>
          ) : (
            <div>
              {/* Batch Action Header Bar */}
              <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800 text-xs px-1">
                <label className="flex items-center gap-2 cursor-pointer select-none text-slate-400">
                  <input
                    type="checkbox"
                    checked={
                      unmappedCandidates.length > 0 &&
                      selectedRowIds.length === unmappedCandidates.length
                    }
                    onChange={toggleSelectAll}
                    className="rounded accent-emerald-500"
                  />
                  <span>
                    Select Unmapped ({selectedRowIds.length}/{unmappedCandidates.length})
                  </span>
                </label>

                {/* Live Selected Total */}
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
                    onClick={() => handleBatchBind()}
                    disabled={binding}
                    className="rounded bg-emerald-600 px-3 py-1 text-[11px] font-bold text-white hover:bg-emerald-500 disabled:opacity-50 transition-colors"
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
                        return (
                          parsed.display_text ||
                          parsed.narration ||
                          parsed.payee ||
                          cand.remarks
                        );
                      } catch {
                        return cand.remarks;
                      }
                    }
                    return (
                      cand.remarks.display_text ||
                      cand.remarks.narration ||
                      cand.remarks.payee ||
                      JSON.stringify(cand.remarks)
                    );
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
                      {/* Checkbox + Metadata */}
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
                              <span className="text-[10px] text-slate-500">
                                ({cand.date_offset_days > 0 ? `+${cand.date_offset_days}` : cand.date_offset_days}d offset)
                              </span>
                            )}
                          </div>

                          <p
                            className="font-mono text-[11px] text-slate-200 line-clamp-2 break-all leading-tight"
                            title={cleanNarration}
                          >
                            {cleanNarration}
                          </p>
                        </div>
                      </div>

                      {/* Right Side: Amount & Actions */}
                      <div className="flex shrink-0 flex-col items-end justify-between pl-2 border-l border-slate-800">
                        <div className="font-mono text-xs font-bold text-emerald-400">
                          ₹{amountVal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </div>

                        {isBoundToAsset ? (
                          <button
                            onClick={() => handleUnmap(cand)}
                            disabled={binding}
                            className="mt-1.5 rounded bg-rose-600/80 px-2.5 py-1 text-[10px] font-bold text-white hover:bg-rose-500 disabled:opacity-50 transition-colors"
                          >
                            {binding ? 'Working...' : 'Disconnect'}
                          </button>
                        ) : (
                          <button
                            onClick={() => handleBatchBind(cand)}
                            disabled={binding}
                            className="mt-1.5 rounded bg-emerald-600 px-2.5 py-1 text-[10px] font-bold text-white hover:bg-emerald-500 disabled:opacity-50 transition-colors"
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

        {/* User Note Field */}
        <div className="mt-4">
          <input
            type="text"
            placeholder="Audit Note (e.g. Cleared via KSEB Online Portal / Trivandrum Corp)"
            value={userNote}
            onChange={(e) => setUserNote(e.target.value)}
            className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
          />
        </div>
      </div>
    </div>
  );
};