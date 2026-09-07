import React from 'react';

interface Props {
  stagedCount: number;
  selectedCount: number;
  onHarvest: () => void;
  isHarvesting: boolean;
  onCommit: () => void;
  isCommitting: boolean;
}

export const StatementToolbar: React.FC<Props> = ({
  stagedCount,
  selectedCount,
  onHarvest,
  isHarvesting,
  onCommit,
  isCommitting,
}) => {
  return (
    <div className="flex flex-col md:flex-row justify-between items-start md:items-center bg-zinc-900/60 border border-zinc-800 p-3 rounded-xl gap-3 text-xs font-mono">
      {/* Metric Counters */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5">
          <span className="text-zinc-500 text-[11px]">STAGED:</span>
          <span className="bg-amber-950/80 border border-amber-800/80 text-amber-400 px-2 py-0.5 rounded font-bold shadow-sm">
            {stagedCount}
          </span>
        </div>
        <span className="text-zinc-700">|</span>
        <div className="flex items-center gap-1.5">
          <span className="text-zinc-500 text-[11px]">SELECTED:</span>
          <span className="bg-emerald-950/80 border border-emerald-800/80 text-emerald-400 px-2 py-0.5 rounded font-bold shadow-sm">
            {selectedCount}
          </span>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex items-center gap-2 w-full md:w-auto justify-end">
        <button
          type="button"
          onClick={onHarvest}
          disabled={isHarvesting}
          className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 disabled:bg-zinc-900 border border-zinc-700 disabled:border-zinc-800 text-zinc-200 disabled:text-zinc-600 font-bold rounded transition-colors flex items-center gap-1.5 cursor-pointer shadow-md"
        >
          {isHarvesting ? (
            <span className="h-3.5 w-3.5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
          ) : (
            <span>⚡</span>
          )}
          <span>{isHarvesting ? 'Scanning Gmail...' : 'Scan Gmail for PDFs'}</span>
        </button>

        <button
          type="button"
          onClick={onCommit}
          disabled={isCommitting || selectedCount === 0}
          className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:bg-zinc-800 text-white disabled:text-zinc-500 font-bold rounded transition-colors flex items-center gap-1.5 cursor-pointer shadow-md shadow-emerald-950 disabled:shadow-none"
        >
          {isCommitting ? (
            <span className="h-3.5 w-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
          ) : (
            <span>💾</span>
          )}
          <span>Commit Selected ({selectedCount}) to Inbox</span>
        </button>
      </div>
    </div>
  );
};