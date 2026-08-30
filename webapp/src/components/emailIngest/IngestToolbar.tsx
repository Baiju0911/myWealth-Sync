import React from 'react';
import { type AccountOption } from '../../api/emailIngestApi';

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
  onRunAudit?: () => void;
  isAuditing?: boolean;
  auditStats?: { count: number } | null;
  onStageSelected?: () => void;
  stagingForMatching?: boolean;
  dbSelectedCount?: number;
  totalCount?: number;
  // 🎯 New Staging Filter Toggle Props
  showStagedOnly?: boolean;
  onToggleStagedOnly?: (val: boolean) => void;
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
  onRunAudit,
  isAuditing,
  auditStats,
  onStageSelected,
  stagingForMatching,
  dbSelectedCount = 0,
  totalCount = 0,
  showStagedOnly = false,
  onToggleStagedOnly,
}) => {
  return (
    <div className="flex flex-col md:flex-row justify-between items-start md:items-center bg-zinc-900/60 border border-zinc-800 p-3 rounded-xl gap-3 text-xs font-mono">
      {/* Date & Account Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={datePreset}
          onChange={(e) => onDatePresetChange(e.target.value)}
          className="bg-zinc-950 border border-zinc-800 text-zinc-300 rounded px-2.5 py-1.5 focus:border-indigo-500 focus:outline-none cursor-pointer"
        >
          <option value="THIS_WEEK">This Week</option>
          <option value="THIS_MONTH">This Month</option>
          <option value="LAST_MONTH">Last Month</option>
          <option value="LAST_6_MONTHS">Last 6 Months</option>
          <option value="ALL">All Time</option>
          <option value="CUSTOM">Custom Range...</option>
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

        {/* 🎯 View Toggle: Unstaged vs Staged Queue */}
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
          <span className="text-zinc-500 text-[11px] self-center ml-1">
            ({totalCount} items)
          </span>
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex items-center gap-2">
        {mode === 'INGEST' && (
          <>
            {onTriggerSync && (
              <button
                onClick={onTriggerSync}
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
            {onRunAudit && (
              <div className="flex items-center gap-2">
                <button
                  onClick={onRunAudit}
                  disabled={isAuditing}
                  className="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 disabled:bg-zinc-800 text-zinc-950 font-bold rounded transition-colors flex items-center gap-1.5 cursor-pointer shadow-md shadow-amber-950"
                >
                  <span>{isAuditing ? '⏳' : '🔍'}</span>
                  {isAuditing ? 'Auditing...' : 'Run Balance Audit'}
                </button>
                {auditStats && (
                  <span className="px-2 py-1 rounded bg-amber-950/80 text-amber-400 border border-amber-800/80 font-bold">
                    {auditStats.count} gaps
                  </span>
                )}
              </div>
            )}

            {!showStagedOnly && dbSelectedCount > 0 && onStageSelected && (
              <button
                onClick={onStageSelected}
                disabled={stagingForMatching}
                className="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 disabled:bg-zinc-800 text-zinc-950 font-bold rounded transition-colors flex items-center gap-1.5 cursor-pointer shadow-lg shadow-amber-950"
              >
                <span>{stagingForMatching ? '⏳' : '🎯'}</span>
                {stagingForMatching ? 'Staging...' : `Stage (${dbSelectedCount}) for Matching`}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
};