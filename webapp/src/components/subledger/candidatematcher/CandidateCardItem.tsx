// webapp/src/components/subledger/candidatematcher/CandidateCardItem.tsx
import React from 'react';
import type { CandidateMatchResult } from '../../../api/subledger';
import { resolveCandidateNarration } from '../../../utils/classificationHelpers';

interface CandidateCardItemProps {
  cand: CandidateMatchResult & {
    bank_name?: string;
    bank_last4?: string;
    bank_account_id?: number | string;
  };
  isSelected: boolean;
  keywords: string;
  binding: boolean;
  onToggleSelect: (rowId: string) => void;
  onSingleBind: (cand: CandidateMatchResult) => void;
  onUnmap: (cand: CandidateMatchResult) => void;
}

export const CandidateCardItem: React.FC<CandidateCardItemProps> = ({
  cand,
  isSelected,
  binding,
  onToggleSelect,
  onSingleBind,
  onUnmap,
}) => {
  const isBoundToAnotherAsset = cand.is_mapped && !cand.is_mapped_to_this_asset;

  // Safely resolve displayable string from remarks payload or string
  const displayNarration =
    typeof cand.remarks === 'string'
      ? cand.remarks
      : resolveCandidateNarration(cand.remarks, (cand as any).narration || '');

  return (
    <div
      onClick={() => {
        if (!cand.is_mapped) onToggleSelect(cand.row_identifier);
      }}
      className={`group relative rounded-lg border p-3 font-mono transition-all select-none ${
        cand.is_mapped_to_this_asset
          ? 'border-emerald-500/40 bg-emerald-950/20 shadow-sm'
          : isBoundToAnotherAsset
          ? 'border-amber-500/20 bg-amber-950/10 opacity-75'
          : isSelected
          ? 'border-emerald-500/80 bg-slate-900 shadow-md ring-1 ring-emerald-500/30 cursor-pointer'
          : 'border-slate-800 bg-slate-900/60 hover:border-slate-700 hover:bg-slate-900 cursor-pointer'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5 flex-1 min-w-0">
          {!cand.is_mapped && (
            <input
              type="checkbox"
              checked={isSelected}
              onChange={() => onToggleSelect(cand.row_identifier)}
              onClick={(e) => e.stopPropagation()}
              className="mt-0.5 rounded accent-emerald-500 cursor-pointer w-3.5 h-3.5 shrink-0"
            />
          )}

          <div className="flex-1 min-w-0">
            {/* Top Row: Probability, Date, Originating Bank Badge, and Offset */}
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-bold text-amber-400 border border-amber-500/20 font-mono">
                {cand.probability_score}% MATCH
              </span>

              <span className="text-[10px] font-mono text-zinc-300 font-semibold">
                {cand.transaction_date}
              </span>

              {/* 🏦 Originating Bank Account Badge */}
              {cand.bank_name ? (
                <span className="inline-flex items-center gap-1 rounded bg-sky-950/80 border border-sky-700/60 px-1.5 py-0.2 text-[9px] font-mono text-sky-300 font-bold shrink-0">
                  <span>🏦</span>
                  <span>{cand.bank_name}</span>
                  {cand.bank_last4 && (
                    <span className="text-sky-400/80 font-normal">••{cand.bank_last4}</span>
                  )}
                </span>
              ) : cand.bank_account_id ? (
                <span className="inline-flex items-center rounded bg-zinc-800 border border-zinc-700 px-1 py-0.2 text-[9px] font-mono text-zinc-300 shrink-0">
                  Acc #{cand.bank_account_id}
                </span>
              ) : null}

              {cand.date_offset_days !== 0 && (
                <span className="text-[9px] text-zinc-500 font-mono">
                  ({cand.date_offset_days > 0 ? `+${cand.date_offset_days}` : cand.date_offset_days}d offset)
                </span>
              )}
            </div>

            {/* Narration String with canonical Tailwind class */}
            <p className="text-xs text-slate-200 font-mono leading-relaxed wrap-break-word">
              {displayNarration || 'Unlabeled Bank Line'}
            </p>
          </div>
        </div>

        {/* Right Column: Amount & Action Button */}
        <div className="text-right shrink-0 flex flex-col items-end gap-1.5">
          <span className="text-xs font-bold text-emerald-400 font-mono tabular-nums">
            ₹{Number(cand.debit || cand.credit).toLocaleString('en-IN', {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>

          {cand.is_mapped_to_this_asset ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onUnmap(cand);
              }}
              disabled={binding}
              className="rounded bg-rose-500/10 border border-rose-500/20 px-2 py-0.5 text-[10px] font-bold text-rose-400 hover:bg-rose-500/20 cursor-pointer"
            >
              Unmap
            </button>
          ) : isBoundToAnotherAsset ? (
            <span className="text-[10px] text-amber-400/80 font-bold">
              Bound to {cand.mapping_info?.asset_code}
            </span>
          ) : (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onSingleBind(cand);
              }}
              disabled={binding}
              className="rounded bg-emerald-600 hover:bg-emerald-500 px-2.5 py-0.5 text-[10px] font-bold text-white transition-colors cursor-pointer"
            >
              ⚡ Bind
            </button>
          )}
        </div>
      </div>
    </div>
  );
};