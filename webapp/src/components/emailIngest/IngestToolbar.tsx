// webapp/src/components/emailIngest/IngestToolbar.tsx

import React, { useMemo } from 'react';
import { type AccountOption, DATE_PRESET_OPTIONS } from '../../api/emailIngestApi';
import { Trash2 } from 'lucide-react';

interface Props {
  mode: 'INGEST' | 'VAULT';
  datePreset: string;
  onDatePresetChange: (preset: any) => void;
  startDate: string;
  endDate: string;
  onStartDateChange: (val: string) => void;
  onEndDateChange: (val: string) => void;
  selectedAccount?: string;
  accountOptions?: AccountOption[];
  onAccountChange?: (val: string) => void;
  onTriggerSync?: () => void;
  syncing?: boolean;
  onCommitSelected?: () => void;
  committing?: boolean;
  stagingSelectedCount?: number;
  onStageSelected?: () => void;
  stagingForMatching?: boolean;
  onUnstageSelected?: () => void;
  unstagingForMatching?: boolean;
  dbSelectedCount?: number;
  totalCount?: number;
  showStagedOnly?: boolean;
  onToggleStagedOnly?: (val: boolean) => void;
  stagingPayloads?: any[];
  hideDuplicates?: boolean;
  onToggleHideDuplicates?: () => void;
  onDiscardSelected?: () => void;
  isDiscarding?: boolean;
}

export const IngestToolbar: React.FC<Props> = ({
  mode,
  datePreset,
  onDatePresetChange,
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
  selectedAccount,
  accountOptions = [],
  onAccountChange,
  onTriggerSync,
  syncing,
  onCommitSelected,
  committing,
  stagingSelectedCount = 0,
  onStageSelected,
  stagingForMatching,
  onUnstageSelected,
  unstagingForMatching,
  dbSelectedCount = 0,
  totalCount = 0,
  showStagedOnly = false,
  onToggleStagedOnly,
  stagingPayloads = [],
  hideDuplicates = false,
  onToggleHideDuplicates,
  onDiscardSelected,
  isDiscarding = false,
}) => {
  const readyToCommitCount = useMemo(() => {
    return stagingPayloads.filter(
      (p) => p.status === 'PARSED' || p.status === 'PREVIEW_ONLY'
    ).length;
  }, [stagingPayloads]);

  const duplicateCount = useMemo(() => {
    return stagingPayloads.filter(
      (p) => p.status === 'DUPLICATE' || p.is_duplicate
    ).length;
  }, [stagingPayloads]);

  const handleSyncClick = async () => {
    if (!onTriggerSync) return;
    onTriggerSync();
  };

  const handleDiscardClick = () => {
    if (!onDiscardSelected || stagingSelectedCount === 0) return;
    if (window.confirm(`Discard ${stagingSelectedCount} selected item(s) from staging buffer?`)) {
      onDiscardSelected();
    }
  };

  return (
    <div className="flex flex-col md:flex-row justify-between items-start md:items-center bg-zinc-900/60 border border-zinc-800 p-3 rounded-xl gap-3 text-xs font-mono">
      {/* Date & Account Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={datePreset}
          onChange={(e) => onDatePresetChange(e.target.value)}
          className="bg-zinc-950 border border-zinc-800 text-zinc-300 rounded px-2.5 py-1.5 focus:border-indigo-500 focus:outline-none cursor-pointer"
        >
          {DATE_PRESET_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>

        {datePreset === 'CUSTOM' && (
          <div className="flex items-center gap-1.5">
            <input
              type="date"
              value={startDate}
              onChange={(e) => onStartDateChange(e.target.value)}
              className="bg-zinc-950 border border-zinc-800 text-zinc-300 rounded px-2 py-1"
            />
            <span className="text-zinc-600">to</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => onEndDateChange(e.target.value)}
              className="bg-zinc-950 border border-zinc-800 text-zinc-300 rounded px-2 py-1"
            />
          </div>
        )}

        {mode === 'VAULT' && accountOptions.length > 0 && onAccountChange && (
          <select
            value={selectedAccount}
            onChange={(e) => onAccountChange(e.target.value)}
            className="bg-zinc-950 border border-zinc-800 text-indigo-400 font-bold rounded px-2.5 py-1.5 focus:border-indigo-500 focus:outline-none cursor-pointer"
          >
            {accountOptions.map((acc) => (
              <option key={acc.value} value={acc.value}>
                {acc.label}
              </option>
            ))}
          </select>
        )}

        {/* View Toggle: Vault Records vs Staged Queue */}
        {mode === 'VAULT' && onToggleStagedOnly && (
          <div className="flex items-center bg-zinc-950 border border-zinc-800 rounded p-0.5 ml-1">
            <button
              onClick={() => onToggleStagedOnly(false)}
              className={`px-2.5 py-1 rounded text-[11px] font-bold cursor-pointer transition-colors ${
                !showStagedOnly
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              Vault Records
            </button>
            <button
              onClick={() => onToggleStagedOnly(true)}
              className={`px-2.5 py-1 rounded text-[11px] font-bold cursor-pointer transition-colors ${
                showStagedOnly
                  ? 'bg-amber-600 text-zinc-950 shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              🎯 Staged Queue
            </button>
          </div>
        )}

        {totalCount > 0 && (
          <div className="flex items-center gap-2 ml-1">
            <span className="text-zinc-500 text-[11px] self-center">
              ({totalCount} items)
            </span>

            {/* Interactive Filter Badges */}
            {mode === 'INGEST' && (
              <div className="flex items-center gap-1.5 text-[11px]">
                <span className="bg-emerald-950/80 border border-emerald-800/80 text-emerald-400 px-2 py-0.5 rounded font-bold shadow-sm">
                  📥 Ready: {readyToCommitCount}
                </span>

                {duplicateCount > 0 && (
                  <button
                    type="button"
                    onClick={onToggleHideDuplicates}
                    className={`px-2 py-0.5 rounded font-bold border transition-all cursor-pointer flex items-center gap-1 shadow-sm ${
                      hideDuplicates
                        ? 'bg-zinc-900 text-zinc-500 border-zinc-800 line-through opacity-70 hover:opacity-100'
                        : 'bg-amber-950/80 border-amber-800/80 text-amber-400 hover:bg-amber-900'
                    }`}
                    title={hideDuplicates ? 'Click to show duplicates' : 'Click to hide duplicates'}
                  >
                    <span>⚠️ Duplicates: {duplicateCount}</span>
                    <span className="text-[10px] ml-0.5">{hideDuplicates ? '🙈' : '👁️'}</span>
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex items-center gap-2">
        {mode === 'INGEST' && (
          <>
            {/* 🗑️ Discard / Remove Selected Button */}
            {stagingSelectedCount > 0 && onDiscardSelected && (
              <button
                type="button"
                onClick={handleDiscardClick}
                disabled={isDiscarding}
                className="px-3 py-1.5 bg-rose-950/80 hover:bg-rose-900 border border-rose-800/80 disabled:bg-zinc-800 text-rose-300 font-bold rounded transition-colors flex items-center gap-1.5 cursor-pointer shadow-md shadow-rose-950"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {isDiscarding ? 'Discarding...' : `Discard (${stagingSelectedCount})`}
              </button>
            )}

            {onTriggerSync && (
              <button
                onClick={handleSyncClick}
                disabled={syncing}
                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:bg-zinc-800 text-white font-bold rounded transition-colors flex items-center gap-1.5 cursor-pointer shadow-md shadow-emerald-950"
              >
                <span>{syncing ? '⏳' : '⚡'}</span>
                {syncing ? 'Syncing...' : 'Fetch Live Emails'}
              </button>
            )}

            {onCommitSelected && stagingSelectedCount > 0 && (
              <button
                onClick={onCommitSelected}
                disabled={committing}
                className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-800 text-white font-bold rounded transition-colors flex items-center gap-1.5 cursor-pointer shadow-md shadow-indigo-950"
              >
                <span>{committing ? '⏳' : '📥'}</span>
                {committing ? 'Committing...' : `Commit (${stagingSelectedCount}) to Vault`}
              </button>
            )}
          </>
        )}

        {mode === 'VAULT' && (
          <>
            {!showStagedOnly && dbSelectedCount > 0 && !!onStageSelected && (
              <button
                onClick={onStageSelected}
                disabled={stagingForMatching}
                className="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 disabled:bg-zinc-800 text-zinc-950 font-bold rounded transition-colors flex items-center gap-1.5 cursor-pointer shadow-lg shadow-amber-950"
              >
                <span>{stagingForMatching ? '⏳' : '🎯'}</span>
                {stagingForMatching ? 'Staging...' : `Stage (${dbSelectedCount}) for Matching`}
              </button>
            )}

            {showStagedOnly && dbSelectedCount > 0 && !!onUnstageSelected && (
              <button
                onClick={onUnstageSelected}
                disabled={unstagingForMatching}
                className="px-3 py-1.5 bg-rose-950/80 hover:bg-rose-900 border border-rose-800/80 text-rose-300 font-bold rounded transition-colors flex items-center gap-1.5 cursor-pointer shadow-lg shadow-rose-950"
              >
                <span>{unstagingForMatching ? '⏳' : '↩️'}</span>
                {unstagingForMatching ? 'Unstaging...' : `Unstage (${dbSelectedCount})`}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
};