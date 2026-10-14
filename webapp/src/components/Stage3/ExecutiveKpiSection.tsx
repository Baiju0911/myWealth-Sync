import React from 'react';
import { Download, Zap, TrendingUp, TrendingDown, Wallet, AlertOctagon } from 'lucide-react';

interface ExecutiveKpiSectionProps {
  kpiTableData: any[];
  selectedAccountId: string;
  onExportCsv: (data: any[], filenamePrefix: string) => void;
  onOpenSweepHub: () => void;
}

const formatINR = (val: number | string) => {
  const num = typeof val === 'string' ? parseFloat(val) : val;
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(num || 0);
};

export const ExecutiveKpiSection: React.FC<ExecutiveKpiSectionProps> = ({
  kpiTableData,
  selectedAccountId,
  onExportCsv,
  onOpenSweepHub,
}) => {
  // Extract key metrics from the structured summary array
  const netLiquidityItem = kpiTableData.find((item) => item.id === 'net_liquidity');
  const revenueItem = kpiTableData.find((item) => item.id === 'total_revenue');
  const expenseItem = kpiTableData.find((item) => item.id === 'total_expenses');
  const suspenseItem = kpiTableData.find((item) => item.id === 'suspense_unclassified');

  const netLiquidity = parseFloat(netLiquidityItem?.net_flow || '0');
  const totalRevenue = parseFloat(revenueItem?.net_flow || revenueItem?.credit || '0');
  const totalExpenses = parseFloat(expenseItem?.net_flow || expenseItem?.debit || '0');
  const suspenseAmount = parseFloat(suspenseItem?.net_flow || suspenseItem?.debit || '0');
  const suspenseCount = suspenseItem?.count || 0;

  return (
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4 shadow-md space-y-3">
      {/* Section Header Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-zinc-800/60 pb-3 gap-2">
        <div>
          <h2 className="text-xs font-mono uppercase tracking-wider text-zinc-100 font-bold">
            Executive KPI Summary Matrix
          </h2>
          <p className="text-[11px] text-zinc-500 font-mono">
            Audited financial health, period net liquidity, volume trends, and suspense clearance status.
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => onExportCsv(kpiTableData, `KPI_Summary_Node_${selectedAccountId}`)}
            className="flex items-center gap-1.5 bg-zinc-950 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 px-2.5 py-1 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer shadow-xs"
            title="Export KPI Summary to CSV"
          >
            <Download className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
            <span>Export KPIs</span>
          </button>

          <button
            type="button"
            onClick={onOpenSweepHub}
            className="flex items-center gap-1.5 bg-linear-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-zinc-950 px-3 py-1 rounded-lg text-xs font-mono font-bold shadow-lg transition-all cursor-pointer z-10"
          >
            <Zap className="w-3.5 h-3.5 fill-zinc-950 shrink-0" />
            <span>Node 99 Rule Sweep Hub</span>
          </button>
        </div>
      </div>

      {/* 4-Card Responsive Metric Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 font-mono">
        {/* Card 1: Net Liquidity */}
        <div className="bg-zinc-950/70 border border-zinc-800/90 p-3.5 rounded-xl space-y-2 relative overflow-hidden shadow-inner">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-semibold">
              Net Liquidity
            </span>
            <Wallet className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <div>
            <div className={`text-base sm:text-lg font-bold tabular-nums tracking-tight ${
              netLiquidity >= 0 ? 'text-zinc-100' : 'text-rose-400'
            }`}>
              {formatINR(netLiquidity)}
            </div>
            <div className="text-[10px] text-zinc-500 mt-0.5 truncate">
              {netLiquidityItem?.count || 0} active double-entry records
            </div>
          </div>
          <div className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950/60 text-cyan-300 border border-cyan-800/50 inline-block font-sans">
            Inflows vs Outflows Flow
          </div>
        </div>

        {/* Card 2: Total Revenue & Income */}
        <div className="bg-zinc-950/70 border border-zinc-800/90 p-3.5 rounded-xl space-y-2 relative overflow-hidden shadow-inner">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-semibold">
              Total Revenue
            </span>
            <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div>
            <div className="text-base sm:text-lg font-bold tabular-nums text-emerald-400 tracking-tight">
              {formatINR(totalRevenue)}
            </div>
            <div className="text-[10px] text-zinc-500 mt-0.5 truncate">
              {revenueItem?.count || 0} credited inflows
            </div>
          </div>
          <div className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800/50 inline-block font-sans">
            Statements & Returns
          </div>
        </div>

        {/* Card 3: Operating Expenses */}
        <div className="bg-zinc-950/70 border border-zinc-800/90 p-3.5 rounded-xl space-y-2 relative overflow-hidden shadow-inner">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-semibold">
              Operating Expenses
            </span>
            <TrendingDown className="w-3.5 h-3.5 text-rose-400" />
          </div>
          <div>
            <div className="text-base sm:text-lg font-bold tabular-nums text-rose-400 tracking-tight">
              {formatINR(totalExpenses)}
            </div>
            <div className="text-[10px] text-zinc-500 mt-0.5 truncate">
              {expenseItem?.count || 0} debited expenditures
            </div>
          </div>
          <div className="text-[9px] px-1.5 py-0.5 rounded bg-rose-950/60 text-rose-300 border border-rose-800/50 inline-block font-sans">
            Recognized Outflows
          </div>
        </div>

        {/* Card 4: Suspense Clearance Vault */}
        <div className={`p-3.5 rounded-xl space-y-2 relative overflow-hidden border transition-all ${
          suspenseCount > 0
            ? 'bg-amber-950/20 border-amber-800/70 shadow-[0_0_12px_rgba(245,158,11,0.15)] ring-1 ring-amber-500/20'
            : 'bg-zinc-950/70 border-zinc-800/90'
        }`}>
          <div className="flex items-center justify-between">
            <span className={`text-[10px] uppercase tracking-wider font-semibold ${
              suspenseCount > 0 ? 'text-amber-400' : 'text-zinc-400'
            }`}>
              Suspense Vault
            </span>
            <AlertOctagon className={`w-3.5 h-3.5 ${
              suspenseCount > 0 ? 'text-amber-400 animate-pulse' : 'text-zinc-500'
            }`} />
          </div>
          <div>
            <div className={`text-base sm:text-lg font-bold tabular-nums tracking-tight ${
              suspenseCount > 0 ? 'text-amber-300' : 'text-zinc-300'
            }`}>
              {formatINR(suspenseAmount)}
            </div>
            <div className="text-[10px] text-amber-500/80 mt-0.5 truncate">
              {suspenseCount} unclassified transaction nodes
            </div>
          </div>
          <div className="text-[9px] px-1.5 py-0.5 rounded bg-amber-950/60 text-amber-300 border border-amber-800/60 inline-block font-sans">
            Pending Rule Learning
          </div>
        </div>
      </div>
    </div>
  );
};