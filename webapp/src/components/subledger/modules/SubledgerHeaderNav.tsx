import React from 'react';

interface SubledgerHeaderNavProps {
  activeTab: 'ASSET' | 'INCOME' | 'EXPENSE';
  onSelectTab: (tab: 'ASSET' | 'INCOME' | 'EXPENSE') => void;
  assetCount: number;
  incomeCount: number;
  expenseCount: number;
  isModal: boolean;
  onCreateAsset: () => void;
  onRefresh: () => void;
}

export const SubledgerHeaderNav: React.FC<SubledgerHeaderNavProps> = ({
  activeTab,
  onSelectTab,
  assetCount,
  incomeCount,
  expenseCount,
  isModal,
  onCreateAsset,
  onRefresh,
}) => {
  return (
    <div className="flex flex-wrap items-center justify-between border-b border-slate-800 pb-4 gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white">
          Sub-Ledger & Compliance Engine
        </h1>
        <p className="text-xs text-slate-400 font-mono mt-0.5">
          Manage balance sheet assets, income yield streams, vendor cost centers, and transaction bindings.
        </p>
      </div>

      {/* Domain Switcher */}
      <div className="flex items-center gap-1 bg-slate-900 p-1 rounded-xl border border-slate-800 font-mono">
        <button
          type="button"
          onClick={() => onSelectTab('ASSET')}
          className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all cursor-pointer ${
            activeTab === 'ASSET' ? 'bg-emerald-600 text-white shadow-md' : 'text-slate-400 hover:text-white'
          }`}
        >
          📦 Assets ({assetCount})
        </button>
        <button
          type="button"
          onClick={() => onSelectTab('INCOME')}
          className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all cursor-pointer ${
            activeTab === 'INCOME' ? 'bg-cyan-600 text-white shadow-md' : 'text-slate-400 hover:text-white'
          }`}
        >
          💰 Income ({incomeCount})
        </button>
        <button
          type="button"
          onClick={() => onSelectTab('EXPENSE')}
          className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all cursor-pointer ${
            activeTab === 'EXPENSE' ? 'bg-rose-600 text-white shadow-md' : 'text-slate-400 hover:text-white'
          }`}
        >
          📊 Expenses ({expenseCount})
        </button>
      </div>

      {!isModal && (
        <div className="flex items-center gap-2 font-mono">
          <button
            type="button"
            onClick={onCreateAsset}
            className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-500 transition-colors cursor-pointer shadow-md"
          >
            + New Sub-Ledger
          </button>
          <button
            type="button"
            onClick={onRefresh}
            className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-bold text-slate-300 hover:bg-slate-700 transition-colors cursor-pointer"
          >
            🔄 Refresh
          </button>
        </div>
      )}
    </div>
  );
};