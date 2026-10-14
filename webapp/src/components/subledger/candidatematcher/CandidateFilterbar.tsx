import React from 'react';

export interface HorizonPreset {
  label: string;
  value: number;
}

interface CandidateFilterBarProps {
  documentDate: string;
  setDocumentDate: (date: string) => void;
  targetAmount: number | string;
  setTargetAmount: (amt: number | string) => void;
  keywords: string;
  setKeywords: (kw: string) => void;
  dayWindow: number;
  onSelectHorizon: (days: number) => void;
  syncAcquisitionCost: boolean;
  setSyncAcquisitionCost: (sync: boolean) => void;
  isCash: boolean;
  setIsCash: (cash: boolean) => void;
  loading: boolean;
  onSearch: (e: React.FormEvent) => void;
}

const HORIZON_PRESETS: HorizonPreset[] = [
  { label: '30D', value: 30 },
  { label: '60D', value: 60 },
  { label: '90D', value: 90 },
  { label: '6M', value: 180 },
  { label: '1Y', value: 365 },
  { label: 'Till Today', value: 1825 },
];

export const CandidateFilterBar: React.FC<CandidateFilterBarProps> = ({
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
  return (
    <form onSubmit={onSearch} className="mt-3 grid grid-cols-12 gap-2.5 shrink-0">
      <div className="col-span-12 md:col-span-3">
        <label className="block text-[11px] font-medium text-slate-400 font-mono">Document Date</label>
        <input
          type="date"
          value={documentDate}
          onChange={(e) => setDocumentDate(e.target.value)}
          className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-white focus:border-emerald-500 focus:outline-none font-mono"
        />
      </div>

      <div className="col-span-12 md:col-span-3">
        <label className="block text-[11px] font-medium text-slate-400 font-mono">Target Amount (₹)</label>
        <input
          type="number"
          step="0.01"
          placeholder="0.00"
          value={targetAmount}
          onChange={(e) => setTargetAmount(e.target.value)}
          className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-white focus:border-emerald-500 focus:outline-none font-mono"
        />
      </div>

      <div className="col-span-12 md:col-span-4">
        <label className="block text-[11px] font-medium text-slate-400 font-mono">Matching Keywords</label>
        <input
          type="text"
          placeholder="e.g. BHIMA, KALYAN, COIN"
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
          className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-white focus:border-emerald-500 focus:outline-none font-mono"
        />
      </div>

      <div className="col-span-12 md:col-span-2 flex items-end">
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-500 disabled:opacity-50 cursor-pointer transition-colors font-mono"
        >
          {loading ? 'Scanning...' : 'Re-Scan'}
        </button>
      </div>

      <div className="col-span-12 flex flex-wrap items-center justify-between gap-2 rounded bg-slate-800/60 px-3 py-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] text-slate-400 font-mono">Search Horizon:</span>
          <div className="flex flex-wrap items-center gap-1">
            {HORIZON_PRESETS.map((preset) => (
              <button
                key={preset.value}
                type="button"
                onClick={() => onSelectHorizon(preset.value)}
                className={`rounded px-2 py-0.5 font-mono text-[10px] font-bold cursor-pointer transition-all ${
                  dayWindow === preset.value
                    ? 'bg-emerald-500 text-slate-950 shadow-sm'
                    : 'bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white'
                }`}
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-4">
          <label className="flex items-center gap-1.5 text-xs text-emerald-400 font-mono cursor-pointer select-none">
            <input
              type="checkbox"
              checked={syncAcquisitionCost}
              onChange={(e) => setSyncAcquisitionCost(e.target.checked)}
              className="rounded accent-emerald-500 cursor-pointer"
            />
            <span>Sync Acquisition Cost</span>
          </label>

          <label className="flex items-center gap-1.5 text-xs text-slate-300 font-mono cursor-pointer select-none">
            <input
              type="checkbox"
              checked={isCash}
              onChange={(e) => setIsCash(e.target.checked)}
              className="rounded accent-emerald-500 cursor-pointer"
            />
            <span>Direct Cash / Manual</span>
          </label>
        </div>
      </div>
    </form>
  );
};