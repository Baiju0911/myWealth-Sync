import React, { useEffect, useState, useRef } from 'react';
import {
  fetchCandidatePatterns,
  validatePatternAnchor,
  type PatternValidationResponse,
} from '../../../api/api';
import { X, ShieldAlert, Sparkles } from 'lucide-react';

interface Props {
  isOpen: boolean;
  selectedTxnIds: string[];
  targetCategory: string;
  targetSubcategory: string;
  activeVendorName?: string;
  upiStrategy?: 'vendor' | 'auto_consolidate';
  onClose: () => void;
  onConfirm: (selectedPatterns: string[]) => void;
  isSubmitting?: boolean;
}

const cleanCandidatePattern = (rawPattern: string): string => {
  if (!rawPattern) return '';
  let cleaned = rawPattern.trim();
  cleaned = cleaned.replace(/^UPI\//i, '');
  cleaned = cleaned.replace(/\/NO REMARKS?/i, '');
  if (cleaned.includes('@')) {
    cleaned = cleaned.split('@')[0];
  }
  return cleaned.trim().toUpperCase();
};

export const PatternSelectionModal: React.FC<Props> = ({
  isOpen,
  selectedTxnIds,
  targetCategory,
  targetSubcategory,
  activeVendorName = '',
  upiStrategy = 'vendor',
  onClose,
  onConfirm,
  isSubmitting = false,
}) => {
  const [loading, setLoading] = useState<boolean>(false);
  const [selectablePatterns, setSelectablePatterns] = useState<string[]>([]);
  const [disabledPatterns, setDisabledPatterns] = useState<string[]>([]);
  const [chosenPatterns, setChosenPatterns] = useState<string[]>([]);

  const [customInput, setCustomInput] = useState<string>('');
  const [validating, setValidating] = useState<boolean>(false);
  const [evaluation, setEvaluation] = useState<PatternValidationResponse | null>(null);

  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!isOpen || !selectedTxnIds || selectedTxnIds.length === 0) {
      setSelectablePatterns([]);
      setDisabledPatterns([]);
      setChosenPatterns([]);
      setCustomInput('');
      setEvaluation(null);
      return;
    }

    if (upiStrategy === 'auto_consolidate') {
      const genericChips = ['⚡ P2M_UPI_MERCHANT_SWEEP', 'GENERIC_QR_NORMALIZER'];
      setSelectablePatterns(genericChips);
      setChosenPatterns([genericChips[0]]);
      setDisabledPatterns([]);
      setLoading(false);
      return;
    }

    let isMounted = true;
    setLoading(true);

    fetchCandidatePatterns(selectedTxnIds)
      .then((data) => {
        if (!isMounted) return;

        const rawClean = data.selectable_patterns || [];
        const disabled = data.disabled_patterns || [];

        const cleanedCandidates = Array.from(
          new Set(
            rawClean
              .map(cleanCandidatePattern)
              .filter((pat) => pat.length > 1)
          )
        );

        const cleanVendor = cleanCandidatePattern(activeVendorName);
        if (cleanedCandidates.length === 0 && cleanVendor) {
          cleanedCandidates.push(cleanVendor);
        }

        setSelectablePatterns(cleanedCandidates);
        setDisabledPatterns(disabled);

        if (cleanedCandidates.length > 0) {
          setChosenPatterns([cleanedCandidates[0]]);
        }
      })
      .catch((err) => {
        console.error('Error fetching pattern suggestions:', err);
        const cleanVendor = cleanCandidatePattern(activeVendorName);
        if (isMounted && cleanVendor) {
          setSelectablePatterns([cleanVendor]);
          setChosenPatterns([cleanVendor]);
        }
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [isOpen, selectedTxnIds, upiStrategy, activeVendorName]);

  const handleInputChange = (value: string) => {
    setCustomInput(value);
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);

    const trimmed = value.trim();
    if (!trimmed || trimmed.length < 2) {
      setEvaluation(null);
      setValidating(false);
      return;
    }

    setValidating(true);
    debounceTimerRef.current = setTimeout(() => {
      validatePatternAnchor(trimmed)
        .then((res) => setEvaluation(res))
        .catch((err) => {
          console.error('Pattern validation error:', err);
          setEvaluation(null);
        })
        .finally(() => setValidating(false));
    }, 400);
  };

  if (!isOpen) return null;

  const handleTogglePattern = (pattern: string) => {
    setChosenPatterns((prev) =>
      prev.includes(pattern) ? prev.filter((p) => p !== pattern) : [...prev, pattern]
    );
  };

  const handleAddCustomPattern = () => {
    if (!evaluation || !evaluation.is_valid || !evaluation.clean_pattern) return;
    const targetPattern = cleanCandidatePattern(evaluation.clean_pattern);

    if (!selectablePatterns.includes(targetPattern)) {
      setSelectablePatterns((prev) => [...prev, targetPattern]);
    }
    if (!chosenPatterns.includes(targetPattern)) {
      setChosenPatterns((prev) => [...prev, targetPattern]);
    }

    setCustomInput('');
    setEvaluation(null);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAddCustomPattern();
    }
  };

  const isAddDisabled = !evaluation || !evaluation.is_valid || validating;

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 bg-black/85 z-9999 flex items-center justify-center p-4 backdrop-blur-xs font-mono"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-zinc-900 border border-zinc-700 rounded-2xl p-6 max-w-lg w-full text-zinc-100 shadow-2xl space-y-4"
      >
        {/* Header */}
        <div className="flex justify-between items-center border-b border-zinc-800 pb-3">
          <div>
            <h3 className="text-xs sm:text-sm font-bold text-amber-400 uppercase tracking-wider">
              Confirm Reclassification & Learned Rule
            </h3>
            <span className="text-[11px] text-zinc-400 font-sans block mt-0.5">
              Reclassifying {selectedTxnIds.length} item(s) to <strong className="text-zinc-200">{targetCategory} ➔ {targetSubcategory}</strong>
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-zinc-400 hover:text-zinc-100 p-1 rounded hover:bg-zinc-800"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Pattern Selection Box */}
        <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-4 space-y-3">
          <div className="flex items-center gap-1.5 text-cyan-400 text-[11px] font-bold uppercase tracking-wider">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Select Rule Anchors ({upiStrategy === 'auto_consolidate' ? 'Rail Sweep Mode' : 'Clean Entity Mode'})</span>
          </div>

          {loading ? (
            <div className="text-xs text-zinc-400 py-3 text-center">
              ⏳ Extracting clean vendor phrases from narrations...
            </div>
          ) : (
            <>
              {/* Selectable Clean Chips */}
              <div className="flex flex-wrap gap-2">
                {selectablePatterns.length === 0 ? (
                  <span className="text-[11px] text-zinc-500 font-sans">
                    No specific vendor anchor detected. Type a custom keyword below or reclassify without learning.
                  </span>
                ) : (
                  selectablePatterns.map((pat) => {
                    const isChecked = chosenPatterns.includes(pat);
                    return (
                      <label
                        key={pat}
                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-bold border cursor-pointer transition-colors ${
                          isChecked
                            ? 'bg-indigo-950/80 text-indigo-300 border-indigo-600'
                            : 'bg-zinc-900 text-zinc-400 border-zinc-700 hover:border-zinc-500'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => handleTogglePattern(pat)}
                          className="accent-indigo-500 w-3.5 h-3.5 rounded"
                        />
                        <span>{pat}</span>
                      </label>
                    );
                  })
                )}
              </div>

              {/* Custom Tag Input */}
              {upiStrategy === 'vendor' && (
                <div className="border-t border-zinc-800 pt-3 space-y-2">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={customInput}
                      onChange={(e) => handleInputChange(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder="Type custom keyword anchor (e.g. SAJULAL, CHERUKARA)..."
                      className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-100 outline-none focus:border-indigo-500 font-sans"
                    />
                    <button
                      type="button"
                      onClick={handleAddCustomPattern}
                      disabled={isAddDisabled}
                      className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-bold transition-colors disabled:opacity-50 cursor-pointer"
                    >
                      + Add Tag
                    </button>
                  </div>

                  {/* Engine Feedback Container */}
                  <div className="min-h-6">
                    {validating && (
                      <span className="text-[10px] text-zinc-500">Checking engine rules...</span>
                    )}
                    {!validating && evaluation && (
                      <div className={`text-[11px] px-2.5 py-1 rounded-lg border font-semibold ${
                        evaluation.status === 'GOOD'
                          ? 'bg-emerald-950/40 text-emerald-300 border-emerald-800/60'
                          : evaluation.status === 'BAD'
                          ? 'bg-amber-950/40 text-amber-300 border-amber-800/60'
                          : 'bg-rose-950/40 text-rose-300 border-rose-800/60'
                      }`}>
                        {evaluation.message}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Blocked Noise Tokens */}
              {upiStrategy === 'vendor' && disabledPatterns.length > 0 && (
                <div className="border-t border-zinc-800 pt-2 space-y-1.5">
                  <span className="text-[10px] text-zinc-500 font-bold uppercase flex items-center gap-1">
                    <ShieldAlert className="w-3.5 h-3.5" />
                    <span>Auto-Filtered System Noise (Blocked):</span>
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {disabledPatterns.map((token) => (
                      <span
                        key={`disabled-${token}`}
                        className="px-2 py-0.5 rounded-full text-[10px] bg-zinc-900 text-zinc-600 border border-zinc-800 line-through select-none"
                      >
                        {token}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer Actions */}
        <div className="flex gap-2.5 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="flex-1 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs rounded-lg font-bold transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(chosenPatterns)}
            disabled={isSubmitting || loading}
            className="flex-[1.5] py-2 bg-amber-500 hover:bg-amber-400 text-zinc-950 text-xs rounded-lg font-bold transition-colors disabled:opacity-50 cursor-pointer"
          >
            {isSubmitting ? 'Applying Reclassification...' : 'Confirm & Apply'}
          </button>
        </div>
      </div>
    </div>
  );
};