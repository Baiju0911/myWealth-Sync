import React from 'react';
import type { CandidateMatchResult } from '../../../api/subledger';
import {
  resolveCandidateNarration,
  highlightKeywords,
} from '../../../utils/classificationHelpers';

interface CandidateCardItemProps {
  cand: CandidateMatchResult;
  isSelected: boolean;
  keywords: string;
  binding: boolean;
  onToggleSelect: (id: string) => void;
  onSingleBind: (cand: CandidateMatchResult) => void;
  onUnmap: (cand: CandidateMatchResult) => void;
}

export const CandidateCardItem: React.FC<CandidateCardItemProps> = ({
  cand,
  isSelected,
  keywords,
  binding,
  onToggleSelect,
  onSingleBind,
  onUnmap,
}) => {
  const isBoundToCurrentAsset = Boolean(cand.is_mapped_to_this_asset);
  
  // Bound to another asset if mapped, but not to the current active asset
  const isBoundToOtherAsset =
    !isBoundToCurrentAsset &&
    Boolean(cand.is_mapped || (cand.mapping_info && cand.mapping_info.mapping_id));

  const vendorTag = cand.mapping_info?.vendor_name ? ` [${cand.mapping_info.vendor_name}]` : '';
  const boundFolioName = cand.mapping_info?.asset_name
    ? `${cand.mapping_info.asset_name}${vendorTag}`
    : cand.mapping_info?.asset_code || 'Another Folio';

  const amountVal = Number(cand.debit || cand.credit || 0);
  const cleanNarration = resolveCandidateNarration(cand.remarks);
  const highlightedParts = highlightKeywords(cleanNarration, keywords);

  console.log(`🔎 [CARD RENDER] ${cand.row_identifier?.slice(0, 10)}:`, {
    debit: cand.debit,
    is_mapped: cand.is_mapped,
    is_mapped_to_this_asset: cand.is_mapped_to_this_asset,
    boundAssetName: cand.mapping_info?.asset_name,
    status: isBoundToCurrentAsset
      ? 'BOUND TO CURRENT FOLIO'
      : isBoundToOtherAsset
      ? `LOCKED TO ${boundFolioName}`
      : 'AVAILABLE FOR BINDING',
  });

  return (
    <div
      className={`flex items-center justify-between gap-3 rounded border p-2 transition-colors ${
        isBoundToCurrentAsset
          ? 'border-cyan-500/50 bg-cyan-500/5'
          : isBoundToOtherAsset
          ? 'border-slate-800 bg-slate-900/40 opacity-70'
          : isSelected
          ? 'border-emerald-500 bg-emerald-500/5'
          : 'border-slate-800 bg-slate-900/80 hover:border-slate-700'
      }`}
    >
      <div className="flex items-start gap-2.5 min-w-0 flex-1">
        {/* Checkbox enabled only for unmapped items */}
        {!isBoundToCurrentAsset && !isBoundToOtherAsset && (
          <input
            type="checkbox"
            checked={isSelected}
            onChange={() => onToggleSelect(cand.row_identifier)}
            className="mt-1 rounded accent-emerald-500 cursor-pointer"
          />
        )}

        {isBoundToOtherAsset && (
          <span className="mt-1 text-slate-500 text-xs">🔒</span>
        )}

        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-center gap-2">
            {isBoundToCurrentAsset ? (
              <span className="rounded px-1.5 py-0.5 font-mono text-[10px] font-bold bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">
                BOUND TO THIS FOLIO
              </span>
            ) : isBoundToOtherAsset ? (
              <span className="rounded px-1.5 py-0.5 font-mono text-[10px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30">
                LOCKED: BOUND TO {boundFolioName.toUpperCase()}
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

            {!isBoundToCurrentAsset && !isBoundToOtherAsset && cand.date_offset_days !== 0 && (
              <span className="text-[10px] text-slate-500 font-mono">
                ({cand.date_offset_days > 0 ? `+${cand.date_offset_days}` : cand.date_offset_days}d offset)
              </span>
            )}
          </div>

          <p
            className="font-mono text-[11px] text-slate-200 line-clamp-2 break-all leading-tight"
            title={cleanNarration}
          >
            {highlightedParts.map((part, index) =>
              part.isMatch ? (
                <mark key={index} className="bg-amber-400 text-slate-950 px-0.5 rounded font-bold">
                  {part.text}
                </mark>
              ) : (
                <React.Fragment key={index}>{part.text}</React.Fragment>
              )
            )}
          </p>
        </div>
      </div>

      <div className="flex shrink-0 flex-col items-end justify-between pl-3 border-l border-slate-800">
        <div className="font-mono text-xs font-bold text-emerald-400">
          ₹{amountVal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
        </div>

        {isBoundToCurrentAsset ? (
          <button
            type="button"
            onClick={() => onUnmap(cand)}
            disabled={binding}
            className="mt-1 rounded bg-rose-600/80 px-2 py-0.5 text-[10px] font-bold text-white hover:bg-rose-500 disabled:opacity-50 cursor-pointer font-mono"
          >
            {binding ? '...' : 'Disconnect'}
          </button>
        ) : isBoundToOtherAsset ? (
          <span className="mt-1 font-mono text-[10px] font-bold text-slate-500 uppercase">
            Unavailable
          </span>
        ) : (
          <button
            type="button"
            onClick={() => onSingleBind(cand)}
            disabled={binding}
            className="mt-1 rounded bg-emerald-600 px-2.5 py-0.5 text-[10px] font-bold text-white hover:bg-emerald-500 disabled:opacity-50 cursor-pointer font-mono"
          >
            {binding ? '...' : '⚡ Bind'}
          </button>
        )}
      </div>
    </div>
  );
};