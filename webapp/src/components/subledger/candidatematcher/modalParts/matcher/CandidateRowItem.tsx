import React, { useMemo } from 'react';
import type { CandidateMatchResult } from '../../../../../api/subledger';
import { inrFormatter } from '../../../../../utils/classificationHelpers';

const HighlightedText: React.FC<{ text: string; keywords: string }> = ({ text, keywords }) => {
  if (!keywords || !text) return <>{text}</>;

  const combinedRegex = useMemo(() => {
    const searchTerms = keywords
      .split(',')
      .map((k) => k.trim())
      .filter((k) => k.length > 1);

    if (searchTerms.length === 0) return null;

    const escapedPatterns = searchTerms
      .map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
      .filter(Boolean);

    if (escapedPatterns.length === 0) return null;

    return new RegExp(`(${escapedPatterns.join('|')})`, 'gi');
  }, [keywords]);

  if (!combinedRegex) return <>{text}</>;

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

interface CandidateRowItemProps {
  cand: CandidateMatchResult;
  isSelected: boolean;
  keywords: string;
  binding: boolean;
  onToggleSelect: (rowId: string) => void;
  onSingleBind: (cand: CandidateMatchResult) => void;
  onUnmap: (cand: CandidateMatchResult) => void;
}

export const CandidateRowItem: React.FC<CandidateRowItemProps> = ({
  cand,
  isSelected,
  keywords,
  binding,
  onToggleSelect,
  onSingleBind,
  onUnmap,
}) => {
  // 1. Resilient Narration Extraction (handles Workbench items + API candidates)
  const cleanNarration = useMemo(() => {
    const raw = (cand as any).remarks ?? (cand as any).narration ?? (cand as any).description;
    if (!raw) return 'No narration details';

    if (typeof raw === 'object' && raw !== null) {
      return raw.display_text || raw.target_account_name || raw.narration || raw.payee || JSON.stringify(raw);
    }

    if (typeof raw === 'string') {
      try {
        const parsed = JSON.parse(raw);
        if (typeof parsed === 'object' && parsed !== null) {
          return parsed.display_text || parsed.target_account_name || parsed.narration || parsed.payee || raw;
        }
      } catch {
        return raw;
      }
    }

    return String(raw);
  }, [cand]);

  // 2. Uniform Amount Handling
  const amountVal = useMemo(() => {
    const raw =
      Number(cand.debit || 0) ||
      Number(cand.credit || 0) ||
      Number((cand as any).amount || 0) ||
      Number((cand as any).total_amount || 0);
    return Math.abs(raw);
  }, [cand]);

  // 3. Fallback Row Identifier & Date
  const rowId = cand.row_identifier || String((cand as any).id || (cand as any).journal_id || '');
  const displayDate = cand.transaction_date || (cand as any).date || 'N/A';
  const isBoundToAsset = Boolean(cand.is_mapped_to_this_asset);

  const handleRowClick = () => {
    if (!isBoundToAsset && rowId) {
      onToggleSelect(rowId);
    }
  };

  return (
    <div
      onClick={handleRowClick}
      className={`flex items-center justify-between gap-3 rounded border p-2 transition-all cursor-pointer ${
        isBoundToAsset
          ? 'border-cyan-500/50 bg-cyan-500/5 cursor-default'
          : isSelected
          ? 'border-emerald-500 bg-emerald-500/10 shadow-sm'
          : 'border-slate-800 bg-slate-900 hover:border-slate-700 hover:bg-slate-850'
      }`}
    >
      <div className="flex items-start gap-2.5 min-w-0 flex-1">
        {!isBoundToAsset && (
          <div onClick={(e) => e.stopPropagation()} className="pt-0.5">
            <input
              type="checkbox"
              checked={isSelected}
              onChange={() => onToggleSelect(rowId)}
              className="rounded accent-emerald-500 cursor-pointer"
            />
          </div>
        )}

        <div className="min-w-0 flex-1 space-y-0.5">
          <div className="flex items-center gap-2">
            {isBoundToAsset ? (
              <span className="rounded px-1.5 py-0.5 text-[9px] font-bold bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">
                BOUND TO FOLIO
              </span>
            ) : typeof cand.probability_score === 'number' && cand.probability_score > 0 ? (
              <span
                className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${
                  cand.probability_score >= 80
                    ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                    : 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                }`}
              >
                {cand.probability_score}% MATCH
              </span>
            ) : (
              <span className="rounded px-1.5 py-0.5 text-[9px] font-bold bg-slate-800 text-slate-300 border border-slate-700">
                GL UNMAPPED
              </span>
            )}

            <span className="text-[11px] font-semibold text-slate-300">
              {displayDate}
            </span>

            {!isBoundToAsset && typeof cand.date_offset_days === 'number' && cand.date_offset_days !== 0 && (
              <span className="text-[10px] text-slate-500">
                ({cand.date_offset_days > 0 ? `+${cand.date_offset_days}` : cand.date_offset_days}d offset)
              </span>
            )}
          </div>

          <p className="text-[11px] text-slate-200 line-clamp-1 break-all" title={cleanNarration}>
            <HighlightedText text={cleanNarration} keywords={keywords} />
          </p>
        </div>
      </div>

      <div
        className="flex shrink-0 flex-col items-end justify-between pl-2 border-l border-slate-800"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="text-xs font-bold text-emerald-400 font-mono">
          {inrFormatter.format(amountVal)}
        </div>

        {isBoundToAsset ? (
          <button
            type="button"
            onClick={() => onUnmap(cand)}
            disabled={binding}
            className="mt-1 rounded bg-rose-600/80 px-2 py-0.5 text-[10px] font-bold text-white hover:bg-rose-500 disabled:opacity-50 cursor-pointer"
          >
            {binding ? '...' : 'Disconnect'}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => onSingleBind(cand)}
            disabled={binding}
            className="mt-1 rounded bg-emerald-600 px-2 py-0.5 text-[10px] font-bold text-white hover:bg-emerald-500 disabled:opacity-50 cursor-pointer"
          >
            {binding ? '...' : '⚡ Bind'}
          </button>
        )}
      </div>
    </div>
  );
};