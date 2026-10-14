import React from 'react';
import { Layers, Calendar, Filter, RotateCcw } from 'lucide-react';
import { type AccountNode } from '../../api/api';

interface LedgerHeaderFilterProps {
  accounts: AccountNode[];
  selectedAccountId: string;
  onSelectAccount: (id: string) => void;
  fromDate: string;
  toDate: string;
  onFromDateChange: (val: string) => void;
  onToDateChange: (val: string) => void;
  onApplyFilter: (e: React.FormEvent) => void;
  onResetFilter: () => void;
  loading: boolean;
  dateBounds?: {
    min_date: string;
    max_date: string;
  };
}

export const LedgerHeaderFilter: React.FC<LedgerHeaderFilterProps> = ({
  accounts,
  selectedAccountId,
  onSelectAccount,
  fromDate,
  toDate,
  onFromDateChange,
  onToDateChange,
  onApplyFilter,
  onResetFilter,
  loading,
  dateBounds,
}) => {
  return (
    <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-xl p-3 shadow-sm backdrop-blur-xs flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3 font-mono text-xs">
      {/* Node Brand & Account Selector */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center space-x-2 shrink-0">
          <Layers className="w-4 h-4 text-cyan-400" />
          <span className="font-bold text-zinc-100 uppercase tracking-wider text-[11px]">
            Sync-Shield
          </span>
        </div>

        <div className="h-4 w-px bg-zinc-800 hidden sm:block" />

        <div className="w-full sm:w-72">
          <select
            value={selectedAccountId}
            onChange={(e) => onSelectAccount(e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-800 px-2.5 py-1.5 rounded-lg text-zinc-200 font-bold focus:outline-none focus:border-cyan-500/50 cursor-pointer shadow-inner text-xs"
          >
            <option value="">-- Select Target Ledger Account --</option>
            {accounts.map((acc) => (
              <option key={acc.id} value={acc.id}>
                {acc.name} ({acc.account_number ? acc.account_number.slice(-4) : acc.id})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Date Pickers & Actions */}
      {dateBounds && (
        <form onSubmit={onApplyFilter} className="flex flex-wrap items-center justify-end gap-2">
          <div className="flex items-center gap-1.5 bg-zinc-950 border border-zinc-800 px-2 py-1 rounded-lg">
            <Calendar className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
            <span className="text-[10px] text-zinc-500 uppercase">From:</span>
            <input
              type="date"
              value={fromDate}
              min={dateBounds.min_date}
              max={dateBounds.max_date}
              onChange={(e) => onFromDateChange(e.target.value)}
              className="bg-transparent text-zinc-200 outline-none text-[11px] cursor-pointer"
            />
            <span className="text-[10px] text-zinc-500 uppercase ml-1">To:</span>
            <input
              type="date"
              value={toDate}
              min={dateBounds.min_date}
              max={dateBounds.max_date}
              onChange={(e) => onToDateChange(e.target.value)}
              className="bg-transparent text-zinc-200 outline-none text-[11px] cursor-pointer"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-zinc-100 hover:bg-white text-zinc-950 font-bold rounded-lg shadow-sm transition-colors disabled:opacity-50 cursor-pointer text-xs"
          >
            <Filter className="w-3.5 h-3.5" />
            <span>{loading ? 'Evaluating...' : 'Filter'}</span>
          </button>

          <button
            type="button"
            onClick={onResetFilter}
            className="flex items-center space-x-1 px-2.5 py-1.5 border border-zinc-800 text-zinc-400 hover:bg-zinc-800 rounded-lg transition-colors cursor-pointer text-xs"
            title="Reset to Full Historical Range"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Reset</span>
          </button>
        </form>
      )}
    </div>
  );
};