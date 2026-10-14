// webapp/src/components/subledger/candidatematcher/CandidateBatchToolbar.tsx
import React from 'react';

interface CandidateBatchToolbarProps {
  unmappedCount: number;
  selectedCount: number;
  allUnmappedSelected: boolean;
  selectedTotalSum: number;
  binding: boolean;
  onToggleSelectAll: () => void;
  onBatchBind: () => void;
}

export const CandidateBatchToolbar: React.FC<CandidateBatchToolbarProps> = ({
  unmappedCount,
  selectedCount,
  allUnmappedSelected,
  selectedTotalSum,
  binding,
  onToggleSelectAll,
  onBatchBind,
}) => {
  return (
    <div className="sticky top-0 z-20 flex items-center justify-between px-3 py-2.5 bg-slate-950/95 backdrop-blur-md border-b border-slate-800 text-[11px] font-mono shrink-0 shadow-sm">
      <label
        className={`flex items-center gap-2 select-none ${
          unmappedCount === 0
            ? 'text-slate-600 cursor-not-allowed'
            : 'text-slate-300 cursor-pointer hover:text-slate-200'
        }`}
      >
        <input
          type="checkbox"
          disabled={unmappedCount === 0}
          checked={unmappedCount > 0 && allUnmappedSelected}
          onChange={onToggleSelectAll}
          className="rounded accent-emerald-500 cursor-pointer w-3.5 h-3.5 disabled:cursor-not-allowed disabled:opacity-30"
        />
        <span>
          Select Unmapped ({selectedCount}/{unmappedCount})
        </span>
      </label>

      <div className="flex items-center gap-3">
        {selectedCount > 0 && (
          <div className="flex items-center gap-1.5 text-emerald-400 font-semibold">
            <span className="text-slate-400">Total:</span>
            <span className="bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 rounded font-bold text-emerald-300">
              ₹{selectedTotalSum.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
        )}

        <button
          type="button"
          onClick={onBatchBind}
          disabled={binding || selectedCount === 0}
          className="rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-30 disabled:cursor-not-allowed px-3 py-1 text-xs font-bold text-white transition-all shadow-sm cursor-pointer flex items-center gap-1"
        >
          <span>⚡ Bind Selected</span>
          <span>({selectedCount})</span>
        </button>
      </div>
    </div>
  );
};