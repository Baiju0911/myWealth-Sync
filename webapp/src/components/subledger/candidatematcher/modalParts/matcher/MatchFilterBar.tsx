import React from 'react';

export const HORIZON_PRESETS = [
  { label: '30D', value: 30 },
  { label: '60D', value: 60 },
  { label: '90D', value: 90 },
  { label: '6M', value: 180 },
  { label: '1Y', value: 365 },
  { label: '2Y', value: 730 },
  { label: 'Till Today', value: 1825 },
];

interface MatcherFilterBarProps {
  documentDate: string;
  setDocumentDate: (val: string) => void;
  targetAmount: number | string;
  setTargetAmount: (val: string) => void;
  keywords: string;
  setKeywords: (val: string) => void;
  dayWindow: number;
  onSelectHorizon: (days: number) => void;
  syncAcquisitionCost: boolean;
  setSyncAcquisitionCost: (val: boolean) => void;
  isCash: boolean;
  setIsCash: (val: boolean) => void;
  loading: boolean;
  onSearch: (e: React.FormEvent) => void;
}

export const MatcherFilterBar: React.FC<MatcherFilterBarProps> = ({
  documentDate,
  setDocumentDate,
  targetAmount,
  setTargetAmount,
  keywords,
  setKeywords,
  dayWindow,
  onSelectHorizon,
  syncAcquisitionCost,
  setSyncAcquisitionCost,
  isCash,
  setIsCash,
  loading,
  onSearch,
}) => {
  const handleClearKeywords = () => {
    setKeywords('');
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch(e);
  };

  return (
    <form onSubmit={handleFormSubmit} className="mt-3 grid grid-cols-12 gap-2.5 shrink-0">
      {/* 1. Document Date */}
      <div className="col-span-12 sm:col-span-3">
        <label className="block text-[11px] text-slate-400">Document Date</label>
        <input
          type="date"
          value={documentDate}
          onChange={(e) => setDocumentDate(e.target.value)}
          className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-white focus:border-emerald-500 focus:outline-none transition-colors"
        />
      </div>

      {/* 2. Target Amount */}
      <div className="col-span-12 sm:col-span-3">
        <label className="block text-[11px] text-slate-400">Target Amount (₹)</label>
        <input
          type="number"
          step="any"
          placeholder="0.00"
          value={targetAmount === '' ? '' : targetAmount}
          onChange={(e) => setTargetAmount(e.target.value)}
          className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-white focus:border-emerald-500 focus:outline-none font-mono transition-colors"
        />
      </div>

      {/* 3. Search Keywords with Inline Clear */}
      <div className="col-span-12 sm:col-span-4">
        <label className="block text-[11px] text-slate-400">Search Keywords</label>
        <div className="relative mt-1">
          <input
            type="text"
            placeholder="e.g. Bhima, Kalyan, 39491419965"
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-800 pl-2.5 pr-7 py-1 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none transition-colors"
          />
          {keywords && (
            <button
              type="button"
              onClick={handleClearKeywords}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white text-xs cursor-pointer p-0.5 rounded"
              title="Clear keyword"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* 4. Action Button */}
      <div className="col-span-12 sm:col-span-2 flex items-end">
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 cursor-pointer transition-colors"
        >
          {loading ? 'Scanning...' : 'Re-Scan'}
        </button>
      </div>

      {/* 5. Horizon Presets & Toggles */}
      <div className="col-span-12 flex flex-wrap items-center justify-between gap-2 rounded bg-slate-800/40 px-2.5 py-1.5 text-xs border border-slate-800/80">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-slate-400 text-[11px]">Horizon:</span>
          {HORIZON_PRESETS.map((preset) => (
            <button
              key={preset.value}
              type="button"
              onClick={() => onSelectHorizon(preset.value)}
              className={`rounded px-2 py-0.5 text-[10px] font-bold cursor-pointer transition-all ${
                dayWindow === preset.value
                  ? 'bg-emerald-500 text-slate-950 shadow-sm'
                  : 'bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-750'
              }`}
            >
              {preset.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1 text-[11px] text-emerald-400 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={syncAcquisitionCost}
              onChange={(e) => setSyncAcquisitionCost(e.target.checked)}
              className="rounded accent-emerald-500 cursor-pointer"
            />
            <span>Sync Valuation</span>
          </label>

          <label className="flex items-center gap-1 text-[11px] text-slate-400 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={isCash}
              onChange={(e) => setIsCash(e.target.checked)}
              className="rounded accent-emerald-500 cursor-pointer"
            />
            <span>Cash / Manual</span>
          </label>
        </div>
      </div>
    </form>
  );
};