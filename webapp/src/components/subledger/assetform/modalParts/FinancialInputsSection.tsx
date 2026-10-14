import React from 'react';

export const FUNDING_SOURCE_OPTIONS = [
  { value: 'BANK_STAGING', label: '🏦 Bank Line (Reconciled via Staging)' },
  { value: 'DIRECT_CASH', label: '💵 Direct Cash / Manual (Bank Row Missing)' },
  { value: 'HISTORICAL_OPENING', label: '📜 Historical / Opening Balance (Pre-System Asset)' },
  { value: 'GIFTS_INHERITANCE', label: '🎁 Gift / Family Inheritance (Non-Cash Capital)' },
  { value: 'OTHER', label: '📁 Other / Manual Adjustment' },
];

interface FinancialInputsSectionProps {
  currentMode: string;
  acquisitionDate: string;
  setAcquisitionDate: (date: string) => void;
  acquisitionCost: number | string;
  setAcquisitionCost: (cost: string) => void;
  currentValuation: number | string;
  setCurrentValuation: (val: string) => void;
  acquisitionFundingSource: string;
  setAcquisitionFundingSource: (src: string) => void;
  isMatured: boolean;
}

export const FinancialInputsSection: React.FC<FinancialInputsSectionProps> = ({
  currentMode,
  acquisitionDate,
  setAcquisitionDate,
  acquisitionCost,
  setAcquisitionCost,
  currentValuation,
  setCurrentValuation,
  acquisitionFundingSource,
  setAcquisitionFundingSource,
  isMatured,
}) => {
  return (
    <>
      <div className="col-span-4">
        <label className="block text-xs text-slate-400 font-mono">Start / Acquisition Date</label>
        <input
          type="date"
          required
          value={acquisitionDate}
          onChange={(e) => setAcquisitionDate(e.target.value)}
          className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none font-mono"
        />
      </div>

      <div className="col-span-4">
        <label className="block text-xs text-slate-400 font-mono">
          {currentMode === 'INCOME' ? 'Base Yield (₹)' : currentMode === 'EXPENSE' ? 'Initial Spend (₹)' : 'Acquisition Cost (₹)'}
        </label>
        <input
          type="number"
          required
          value={acquisitionCost}
          onChange={(e) => setAcquisitionCost(e.target.value)}
          className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none font-mono"
        />
      </div>

      <div className="col-span-4">
        <label className="block text-xs text-slate-400 font-mono">
          {currentMode === 'INCOME' ? 'Target Annual (₹)' : currentMode === 'EXPENSE' ? 'Budget Cap (₹)' : 'Current Valuation (₹)'}
        </label>
        <input
          type="number"
          required
          disabled={isMatured}
          value={isMatured ? '0.00' : currentValuation}
          onChange={(e) => setCurrentValuation(e.target.value)}
          className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none font-mono disabled:opacity-50"
        />
      </div>

      <div className="col-span-12">
        <label className="block text-xs font-semibold text-emerald-400 font-mono mb-1">
          Acquisition Funding Origin / Bank Row Status
        </label>
        <select
          value={acquisitionFundingSource}
          onChange={(e) => setAcquisitionFundingSource(e.target.value)}
          className="w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-emerald-300 font-bold focus:border-emerald-500 focus:outline-none font-mono cursor-pointer"
        >
          {FUNDING_SOURCE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <p className="text-[10px] text-slate-500 mt-1 font-mono">
          {acquisitionFundingSource === 'BANK_STAGING'
            ? 'Cost baseline is backed by imported bank staging statements.'
            : 'Flags this node with `is_bank_row_missing = True` for direct cash or opening balance mapping.'}
        </p>
      </div>
    </>
  );
};