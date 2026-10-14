import React, { useMemo } from 'react';
import { ArrowUpRight, ArrowDownRight, BarChart3, ChevronRight } from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from 'recharts';

interface ExpenseIncomeDistributionChartProps {
  categoryBreakdown: any[];
  activeChartTab: 'Expense' | 'Income';
  onTabChange: (tab: 'Expense' | 'Income') => void;
  onRowClick: (row: any) => void;
}

const inrFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 2,
});

const formatCompactINR = (value: number): string => {
  if (value >= 10000000) return `₹${(value / 10000000).toFixed(1)}Cr`;
  if (value >= 100000) return `₹${(value / 100000).toFixed(1)}L`;
  if (value >= 1000) return `₹${(value / 1000).toFixed(1)}K`;
  return `₹${value.toFixed(0)}`;
};

const formatXAxisLabel = (label: string): string => {
  if (!label) return '';
  if (label === 'General Operating Expenses') return 'Gen OpEx';
  if (label === 'Suspense Account') return 'Suspense';
  if (label === 'Groceries & Shopping') return 'Groceries';
  if (label === 'Bank Charges & Fees') return 'Bank Fees';
  if (label === 'Legal & Professional Services') return 'Legal/Prof';
  if (label === 'ShareMarket & Mutual Funds') return 'Mutual Funds';
  if (label.length > 11) return `${label.slice(0, 10)}…`;
  return label;
};

export const ExpenseIncomeDistributionChart: React.FC<ExpenseIncomeDistributionChartProps> = ({
  categoryBreakdown,
  activeChartTab,
  onTabChange,
  onRowClick,
}) => {
  const { chartData, totalSum } = useMemo(() => {
    if (!categoryBreakdown?.length) {
      return { chartData: [], totalSum: 0 };
    }

    const filteredRows = categoryBreakdown.filter(
      (row) => (row.category || 'Uncategorized') === activeChartTab
    );

    const calcTotalSum = filteredRows.reduce((acc, row) => {
      const val = activeChartTab === 'Expense'
        ? parseFloat(row.total_debit || '0')
        : parseFloat(row.total_credit || '0');
      return acc + val;
    }, 0);

    const formattedData = filteredRows
      .map((row) => {
        const amt = activeChartTab === 'Expense'
          ? parseFloat(row.total_debit || '0')
          : parseFloat(row.total_credit || '0');
        const pct = calcTotalSum > 0 ? (amt / calcTotalSum) * 100 : 0;

        let baseColor = activeChartTab === 'Expense' ? '#38bdf8' : '#34d399';
        if (row.subcategory === 'Suspense Account') baseColor = '#f59e0b';

        return {
          subcategory: row.subcategory || 'Suspense',
          amount: amt,
          count: typeof row.transaction_count === 'number'
            ? row.transaction_count
            : parseInt(row.transaction_count || '0', 10),
          percentage: pct.toFixed(1),
          fill: baseColor,
          rawRow: row,
        };
      })
      .sort((a, b) => b.amount - a.amount)
      .slice(0, 7);

    return {
      chartData: formattedData,
      totalSum: calcTotalSum,
    };
  }, [categoryBreakdown, activeChartTab]);

  const CustomChartTooltip = ({ active, payload }: any) => {
    if (!active || !payload || !payload.length) return null;
    const tooltipData = payload[0].payload;
    const isSuspense = tooltipData.subcategory === 'Suspense Account';
    const amount = tooltipData.amount || 0;
    const count = tooltipData.count || 0;
    const avgAmount = count > 0 ? amount / count : 0;

    return (
      <div className="bg-zinc-950/95 backdrop-blur-md border border-zinc-700/80 p-3 rounded-xl shadow-2xl font-mono text-xs space-y-2 min-w-56 text-zinc-100">
        <div className="flex items-center justify-between pb-1.5 gap-2 border-b border-zinc-800">
          <div className="flex items-center space-x-2 truncate">
            <span
              className="w-2.5 h-2.5 rounded-full shrink-0"
              style={{ backgroundColor: tooltipData.fill }}
            />
            <span className="font-bold text-zinc-100 truncate text-xs">{tooltipData.subcategory}</span>
          </div>
          <span
            className={`px-1.5 py-0.2 text-[9px] rounded font-bold uppercase tracking-wider ${
              isSuspense
                ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                : activeChartTab === 'Expense'
                  ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30'
                  : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
            }`}
          >
            {tooltipData.percentage}%
          </span>
        </div>

        <div className="space-y-1.5 text-[11px]">
          <div className="flex justify-between items-center bg-zinc-900/60 border border-zinc-800/80 px-2 py-1 rounded">
            <span className="text-zinc-400 font-medium">Total:</span>
            <span className={`font-bold tabular-nums ${
              activeChartTab === 'Expense' ? 'text-rose-400' : 'text-emerald-400'
            }`}>
              {inrFormatter.format(amount)}
            </span>
          </div>

          <div className="flex justify-between items-center bg-zinc-900/80 border border-zinc-800/80 px-2 py-1 rounded">
            <span className="text-zinc-400">Volume:</span>
            <span className="font-bold text-cyan-400 tabular-nums">
              {count} <span className="text-[10px] text-zinc-500 font-normal">txns</span>
            </span>
          </div>

          <div className="flex justify-between items-center bg-zinc-900/80 border border-zinc-800/80 px-2 py-1 rounded">
            <span className="text-zinc-400">Avg / Txn:</span>
            <span className="font-semibold text-zinc-200 tabular-nums">
              {inrFormatter.format(avgAmount)}
            </span>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4 shadow-md space-y-3 font-mono">
      {/* Header Controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-zinc-800/80 pb-3">
        <div className="space-y-0.5">
          <div className="flex items-center space-x-2">
            <BarChart3 className={`w-4 h-4 ${activeChartTab === 'Expense' ? 'text-cyan-400' : 'text-emerald-400'}`} />
            <h2 className="text-xs uppercase tracking-wider text-zinc-100 font-bold">
              Major {activeChartTab === 'Expense' ? 'Expense' : 'Income'} Concentration
            </h2>
          </div>
          <p className="text-[11px] text-zinc-400">
            Categorical analysis of highest velocity cash flow movements.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Outflow/Inflow Switcher */}
          <div className="bg-zinc-950 border border-zinc-800 p-0.5 rounded-lg flex items-center space-x-1 shadow-inner">
            <button
              type="button"
              onClick={() => onTabChange('Expense')}
              className={`px-2.5 py-1 rounded-md text-xs font-bold transition-all flex items-center space-x-1 cursor-pointer ${
                activeChartTab === 'Expense'
                  ? 'bg-rose-950/80 text-rose-300 border border-rose-800/80 shadow-xs'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              <ArrowDownRight className="w-3 h-3 text-rose-400" />
              <span>Outflows (Expenses)</span>
            </button>

            <button
              type="button"
              onClick={() => onTabChange('Income')}
              className={`px-2.5 py-1 rounded-md text-xs font-bold transition-all flex items-center space-x-1 cursor-pointer ${
                activeChartTab === 'Income'
                  ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-800/80 shadow-xs'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              <ArrowUpRight className="w-3 h-3 text-emerald-400" />
              <span>Inflows (Income)</span>
            </button>
          </div>

          {/* Quick Total Pill */}
          <div className="hidden sm:flex bg-zinc-950 border border-zinc-800 px-3 py-1 rounded-lg items-center gap-2">
            <span className="text-[10px] text-zinc-500 uppercase">Total:</span>
            <span className={`text-xs font-bold tabular-nums ${
              activeChartTab === 'Expense' ? 'text-rose-400' : 'text-emerald-400'
            }`}>
              {inrFormatter.format(totalSum)}
            </span>
          </div>
        </div>
      </div>

      {/* 2-Column Split: Chart (Left) + Top Ranking Cards (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-center">
        {/* Left: Recharts Canvas (7 of 12 cols) */}
        <div className="lg:col-span-7 h-72 w-full pt-2">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={chartData}
              margin={{ top: 15, right: 10, left: 10, bottom: 10 }}
              onClick={(state: any) => {
                if (state && state.activePayload && state.activePayload.length) {
                  onRowClick(state.activePayload[0].payload.rawRow || state.activePayload[0].payload);
                }
              }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
              <XAxis
                dataKey="subcategory"
                stroke="#71717a"
                fontSize={10}
                tickLine={false}
                interval={0}
                tickFormatter={formatXAxisLabel}
                tick={{ fill: '#a1a1aa' }}
              />
              <YAxis
                stroke="#71717a"
                fontSize={10}
                tickLine={false}
                tickFormatter={formatCompactINR}
                tick={{ fill: '#71717a' }}
              />
              <Tooltip
                content={<CustomChartTooltip />}
                cursor={{ fill: 'rgba(255, 255, 255, 0.04)' }}
              />
              <Bar
                dataKey="amount"
                maxBarSize={36}
                radius={[4, 4, 0, 0]}
                className="cursor-pointer"
                onClick={(entry: any) => onRowClick(entry.rawRow || entry)}
              >
                {chartData.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={entry.subcategory === 'Suspense Account' ? '#f59e0b' : (activeChartTab === 'Expense' ? '#38bdf8' : '#34d399')}
                    opacity={index === 0 ? 1 : 0.85}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Right: Ranked List with Visual Share Bars (5 of 12 cols) */}
        <div className="lg:col-span-5 space-y-1.5 bg-zinc-950/60 p-3 rounded-xl border border-zinc-800/80">
          <div className="flex justify-between items-center text-[10px] text-zinc-500 uppercase border-b border-zinc-800/80 pb-1.5">
            <span>Ranked Category</span>
            <span>Volume / Amount</span>
          </div>

          <div className="space-y-1">
            {chartData.slice(0, 5).map((item, idx) => (
              <div
                key={item.subcategory}
                onClick={() => onRowClick(item.rawRow || item)}
                className="group p-2 rounded-lg bg-zinc-900/40 hover:bg-zinc-800/60 border border-zinc-800/50 hover:border-zinc-700 transition-all cursor-pointer flex items-center justify-between"
              >
                <div className="space-y-1 flex-1 mr-3 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-zinc-500 font-bold">#{idx + 1}</span>
                    <span className="text-xs text-zinc-200 font-semibold truncate group-hover:text-cyan-400 transition-colors">
                      {item.subcategory}
                    </span>
                    {item.subcategory === 'Suspense Account' && (
                      <span className="px-1 text-[8px] bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded">
                        Action
                      </span>
                    )}
                  </div>

                  {/* Visual Share Bar */}
                  <div className="w-full bg-zinc-800 h-1 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        item.subcategory === 'Suspense Account'
                          ? 'bg-amber-400'
                          : activeChartTab === 'Expense'
                            ? 'bg-cyan-400'
                            : 'bg-emerald-400'
                      }`}
                      style={{ width: `${Math.min(parseFloat(item.percentage), 100)}%` }}
                    />
                  </div>
                </div>

                <div className="text-right shrink-0">
                  <div className={`text-xs font-bold tabular-nums ${
                    activeChartTab === 'Expense' ? 'text-zinc-200' : 'text-emerald-400'
                  }`}>
                    {formatCompactINR(item.amount)}
                  </div>
                  <div className="text-[9px] text-zinc-500 flex items-center justify-end gap-1">
                    <span>{item.percentage}%</span>
                    <span>•</span>
                    <span>{item.count} txns</span>
                    <ChevronRight className="w-3 h-3 text-zinc-600 group-hover:text-zinc-300 transition-colors" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};