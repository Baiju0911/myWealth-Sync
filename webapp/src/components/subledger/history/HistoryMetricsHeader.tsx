// webapp/src/components/subledger/history/HistoryMetricsHeader.tsx
import React from 'react';

interface HistoryMetricsHeaderProps {
  isCashFloat: boolean;
  baseAcquisitionCost: number;
  totalInflows: number;
  totalOutflows: number;
  calculatedValuation: number;
}

export const HistoryMetricsHeader: React.FC<HistoryMetricsHeaderProps> = ({
  isCashFloat,
  baseAcquisitionCost,
  totalInflows,
  totalOutflows,
  calculatedValuation,
}) => {
  const format = (num: number) =>
    num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 font-mono">
      {/* Tile 1: Baseline Float / Acquisition Cost */}
      <div className="rounded-lg bg-slate-950/80 p-3 border border-slate-800 flex flex-col justify-between">
        <span className="text-[10px] text-slate-500 uppercase tracking-wider">
          {isCashFloat ? 'Baseline Float' : 'Acquisition Cost'}
        </span>
        <span className="text-sm font-bold text-amber-400 mt-1 tabular-nums">
          ₹{format(baseAcquisitionCost)}
        </span>
      </div>

      {/* Tile 2: Top-ups / Inflows */}
      <div className="rounded-lg bg-slate-950/80 p-3 border border-slate-800 flex flex-col justify-between">
        <span className="text-[10px] text-slate-500 uppercase tracking-wider">
          {isCashFloat ? 'Total Top-ups' : 'Cumulative Inflows'}
        </span>
        <span className="text-sm font-bold text-cyan-400 mt-1 tabular-nums">
          ₹{format(totalInflows)}
        </span>
      </div>

      {/* Tile 3: Spends / Outflows */}
      <div className="rounded-lg bg-slate-950/80 p-3 border border-slate-800 flex flex-col justify-between">
        <span className="text-[10px] text-slate-500 uppercase tracking-wider">
          {isCashFloat ? 'Total Spends' : 'Operating Outflows'}
        </span>
        <span className="text-sm font-bold text-rose-400 mt-1 tabular-nums">
          ₹{format(totalOutflows)}
        </span>
      </div>

      {/* Tile 4: Active Net Available Float Balance */}
      <div className="rounded-lg bg-emerald-950/30 p-3 border border-emerald-500/40 flex flex-col justify-between">
        <span className="text-[10px] text-emerald-400/90 uppercase tracking-wider font-bold">
          {isCashFloat ? 'Live Float Balance' : 'Current Valuation'}
        </span>
        <span className="text-sm font-bold text-emerald-300 mt-1 tabular-nums">
          ₹{format(calculatedValuation)}
        </span>
      </div>
    </div>
  );
};