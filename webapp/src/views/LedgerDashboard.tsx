import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { 
  //CheckCircle2, 
  AlertTriangle, 
  Calendar, 
  RotateCcw, 
  Filter,
  Layers,
  ArrowUpRight,
  ArrowDownRight,
  Zap,
  Download
} from 'lucide-react';
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  Tooltip, 
  ResponsiveContainer, 
  CartesianGrid,
  LabelList
} from 'recharts';

import { TableEngine } from '../components/ui/data-table/TableEngine';
import { CATEGORY_BREAKDOWN_COLUMNS, KPI_SUMMARY_COLUMNS } from '../components/ui/data-table/columns';
import { ClassificationWorkbenchModal } from './classificationWorkbenchmodal';
import BulkSweephubModal from './BulkSweepHubModal';

import { 
  getDashboardSummary, 
  getAccounts,
  type DashboardSummaryResponse, 
  type DashboardParams,
  type AccountNode 
} from '../api/api';

export const LedgerDashboard: React.FC = () => {
  const [accounts, setAccounts] = useState<AccountNode[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('99');

  const [data, setData] = useState<DashboardSummaryResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [fromDate, setFromDate] = useState<string>('');
  const [toDate, setToDate] = useState<string>('');

  // Tab State for Chart Visuals
  const [activeChartTab, setActiveChartTab] = useState<'Expense' | 'Income'>('Expense');

  const [isWorkbenchOpen, setIsWorkbenchOpen] = useState<boolean>(false);
  const [selectedSubcategoryForWorkbench, setSelectedSubcategoryForWorkbench] = useState<string>('Suspense Account');

  // State for Smart Sweep Hub Modal
  const [isSweepHubOpen, setIsSweepHubOpen] = useState<boolean>(false);

  // 🟢 CSV Export Utility
  const exportToCSV = (exportData: any[], filenamePrefix: string) => {
    if (!exportData || !exportData.length) return;

    // Extract headers
    const headers = Object.keys(exportData[0]).join(',');

    // Format rows safely with quotes and line returns
    const rows = exportData.map((row) =>
      Object.values(row)
        .map((val) => `"${String(val ?? '').replace(/"/g, '""')}"`)
        .join(',')
    );

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers, ...rows].join('\n');
    const encodedUri = encodeURI(csvContent);

    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `${filenamePrefix}_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // 1. Initial Accounts List Fetch
  useEffect(() => {
    let isMounted = true;
    const fetchAccountsList = async () => {
      try {
        const accs = await getAccounts();
        if (isMounted) setAccounts(accs);
      } catch (err) {
        console.error('Failed to load accounts list:', err);
      }
    };
    fetchAccountsList();
    return () => { isMounted = false; };
  }, []);

  // 2. Fetch Dashboard Summary
  const fetchSummary = useCallback(async (params: DashboardParams, updateDateInputs: boolean = false) => {
    setLoading(true);
    setError(null);
    try {
      const summaryData = await getDashboardSummary(params);
      setData(summaryData);

      if (updateDateInputs && summaryData?.date_bounds) {
        setFromDate(summaryData.date_bounds.applied_from_date || '');
        setToDate(summaryData.date_bounds.applied_to_date || '');
      }
    } catch (err: any) {
      if (err.name !== 'AbortError' && err.message !== 'canceled') {
        console.error('Failed to fetch ledger dashboard data:', err);
        setError('Failed to connect to Django API. Ensure backend server is running on port 8000.');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  // 3. Reset State & Fetch New Context on Account Selection
  useEffect(() => {
    if (!selectedAccountId) return;

    setData(null);
    setFromDate('');
    setToDate('');

    fetchSummary({ bank_account_id: selectedAccountId, taxonomy_account_id: 99 }, true);
  }, [selectedAccountId, fetchSummary]);

  const handleApplyFilter = (e: React.FormEvent) => {
    e.preventDefault();
    fetchSummary({
      bank_account_id: selectedAccountId,
      taxonomy_account_id: 99,
      from_date: fromDate,
      to_date: toDate
    }, false);
  };

  const kpiTableData = useMemo(() => {
    if (!data?.kpis || !data?.category_breakdown) return [];

    let totalRevenueDr = 0, totalRevenueCr = 0, totalRevenueCount = 0;
    let totalExpenseDr = 0, totalExpenseCr = 0, totalExpenseCount = 0;
    let suspenseDr = 0, suspenseCr = 0, suspenseCount = 0;

    data.category_breakdown.forEach((row) => {
      const dr = parseFloat(row.total_debit || '0');
      const cr = parseFloat(row.total_credit || '0');
      const txns = typeof row.transaction_count === 'number' 
        ? row.transaction_count 
        : parseInt(row.transaction_count || '0', 10);

      if (row.category === 'Income') {
        totalRevenueDr += dr;
        totalRevenueCr += cr;
        totalRevenueCount += txns;
      } else if (row.category === 'Expense') {
        totalExpenseDr += dr;
        totalExpenseCr += cr;
        totalExpenseCount += txns;
      }

      if (row.subcategory === 'Suspense Account') {
        suspenseDr += dr;
        suspenseCr += cr;
        suspenseCount += txns;
      }
    });

    return [
      {
        id: 'net_liquidity',
        kpi_name: 'Net Liquidity (Net Cash Flow)',
        description: 'Period Net Recognized Movement (Inflows vs Outflows)',
        count: totalRevenueCount + totalExpenseCount,
        debit: totalExpenseDr,
        credit: totalRevenueCr,
        net_flow: data.kpis.net_liquidity,
      },
      {
        id: 'total_revenue',
        kpi_name: 'Total Revenue & Recognized Income',
        description: 'Total credited inflows across Statements & returns',
        count: totalRevenueCount,
        debit: totalRevenueDr,
        credit: totalRevenueCr,
        net_flow: data.kpis.total_income,
      },
      {
        id: 'total_expenses',
        kpi_name: 'Total Operating Expenses',
        description: 'Total debited outflows across all expense heads',
        count: totalExpenseCount,
        debit: totalExpenseDr,
        credit: totalExpenseCr,
        net_flow: data.kpis.total_expense,
      },
      {
        id: 'suspense_unclassified',
        kpi_name: 'Unclassified Suspense Vault',
        description: 'Transactions pending manual or automated rules learning',
        count: data.kpis.suspense_count,
        debit: suspenseDr,
        credit: suspenseCr,
        net_flow: data.kpis.suspense_amount,
        status: 'ENRI', 
      },
    ];
  }, [data]);

  const handleResetFilter = () => {
    if (data) {
      const min = data.date_bounds.min_date;
      const max = data.date_bounds.max_date;
      setFromDate(min);
      setToDate(max);
      fetchSummary({
        bank_account_id: selectedAccountId,
        taxonomy_account_id: 99,
        from_date: min,
        to_date: max
      }, false);
    }
  };

  const handleBarClick = (item: any) => {
    const subcategoryName =
      item?.subcategory ||
      item?.name ||
      item?.payload?.subcategory ||
      item?.payload?.name;

    if (subcategoryName) {
      setSelectedSubcategoryForWorkbench(subcategoryName);
      setIsWorkbenchOpen(true);
    }
  };

  const handleWorkbenchSuccess = () => {
    fetchSummary({
      bank_account_id: selectedAccountId,
      taxonomy_account_id: 99,
      from_date: fromDate,
      to_date: toDate
    }, false);
  };

  const formatINR = (val: number | string) => {
    const num = typeof val === 'string' ? parseFloat(val) : val;
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(num || 0);
  };

  const { chartData, topCategoryName, topCategoryPct, totalSum } = useMemo(() => {
    if (!data?.category_breakdown) {
      return { chartData: [], topCategoryName: 'N/A', topCategoryPct: '0', totalSum: 0 };
    }

    const filteredRows = data.category_breakdown.filter(
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
        
        let barColor = activeChartTab === 'Expense' ? '#38bdf8' : '#34d399';
        if (row.subcategory === 'Suspense Account') barColor = '#f59e0b';

        return {
          subcategory: row.subcategory || 'Suspense',
          amount: amt,
          count: row.transaction_count,
          percentage: pct.toFixed(1),
          fill: barColor,
        };
      })
      .sort((a, b) => b.amount - a.amount)
      .slice(0, 8);

    const topItem = formattedData[0];

    return {
      chartData: formattedData,
      topCategoryName: topItem ? topItem.subcategory : 'N/A',
      topCategoryPct: topItem ? topItem.percentage : '0',
      totalSum: calcTotalSum,
    };
  }, [data, activeChartTab]);

  const inrFormatter = new Intl.NumberFormat('en-IN', { 
    style: 'currency', 
    currency: 'INR',
    maximumFractionDigits: 2 
  });

  const CustomChartTooltip = ({ active, payload }: any) => {
    if (!active || !payload || !payload.length) return null;

    const tooltipData = payload[0].payload;
    const isSuspense = tooltipData.subcategory === 'Suspense Account';
    const amount = tooltipData.amount || 0;
    const count = tooltipData.count || 0;
    const avgAmount = count > 0 ? amount / count : 0;

    return (
      <div 
        className="bg-zinc-950/95 backdrop-blur-md border border-zinc-700/80 p-3 rounded-xl shadow-2xl font-mono text-xs space-y-2 min-w-60"
        style={{
          backgroundColor: '#09090b',
          border: '1px solid #3f3f46',
          color: '#f4f4f5'
        }}
      >
        <div className="flex items-center justify-between pb-1.5 gap-2" style={{ borderBottom: '1px solid #27272a' }}>
          <div className="flex items-center space-x-2 truncate">
            <span 
              className="w-2.5 h-2.5 rounded-full shrink-0 animate-pulse shadow-sm" 
              style={{ backgroundColor: tooltipData.fill }} 
            />
            <span className="font-bold text-zinc-100 truncate text-xs">{tooltipData.subcategory} : </span>
          
            <span
              className={`px-2 py-0.5 text-[10px] rounded-md font-bold shrink-0 uppercase tracking-wider ${
                isSuspense
                  ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                  : activeChartTab === 'Expense'
                    ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30'
                    : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
              }`}
            >
              {tooltipData.percentage}% Share
            </span>
          </div>
        </div>

        <div className="space-y-1.5 text-[11px]">
          <div className="flex justify-between items-center bg-zinc-900/60 border border-zinc-800/80 px-2.5 py-1 rounded-lg">
            <span className="text-zinc-400 font-medium">
              {activeChartTab === 'Expense' ? 'Total Outflow :' : 'Total Inflow :'} 
            </span>
            <span className={`font-bold tabular-nums ${
              activeChartTab === 'Expense' ? 'text-rose-400' : 'text-emerald-400'
            }`}>
              {inrFormatter.format(amount)}
            </span>
          </div>

          <div className="flex justify-between items-center bg-zinc-900/80 border border-zinc-800/80 px-2.5 py-1 rounded-lg">
            <span className="text-zinc-400">Total Volume : </span>
            <span className="font-bold text-cyan-400 tabular-nums">
              {count} <span className="text-[10px] text-zinc-500 font-normal"> txns</span>
            </span>
          </div>

          <div className="flex justify-between items-center bg-zinc-900/80 border border-zinc-800/80 px-2.5 py-1 rounded-lg">
            <span className="text-zinc-400">Avg / Transaction : </span>
            <span className="font-semibold text-emerald-400 tabular-nums">
              {inrFormatter.format(avgAmount)}
            </span>
          </div>
        </div>
      </div>
    );
  };

  const activeAccountName = useMemo(() => {
    const acc = accounts.find((a) => String(a.id) === String(selectedAccountId));
    return acc ? acc.name : `Node #${selectedAccountId}`;
  }, [accounts, selectedAccountId]);

  return (
    <div className="p-4 w-full max-w-none space-y-4 bg-zinc-950 min-h-screen text-zinc-100 font-sans">
      
      {/* 1. Header & Context Switcher */}
      <div className="flex flex-col md:flex-row items-start md:items-center gap-4 w-full">
        {/* Left Title Info */}
        <div className="space-y-0.5">
          <div className="flex items-center space-x-2">
            <Layers className="w-4 h-4 text-cyan-400" />
            <h1 className="text-xs font-mono uppercase tracking-wider text-zinc-100 font-bold">
              Project Sync-Shield
            </h1>
          </div>
          <p className="text-[11px] text-zinc-400 font-mono">
            Target Ledger Node: <span className="text-cyan-400 font-semibold">{activeAccountName}</span>
          </p>
        </div>

        {/* Select Dropdown */}
        <div className="w-full md:w-72 font-mono text-xs ml-0 md:ml-6">
          <select
            value={selectedAccountId}
            onChange={(e) => setSelectedAccountId(e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-800 p-2 rounded-lg text-zinc-100 font-bold focus:outline-none focus:border-cyan-500/50 cursor-pointer shadow-inner"
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

      {/* 2. Date Filter Control Bar */}
      {data && (
        <form onSubmit={handleApplyFilter} className="bg-zinc-900/50 p-3 rounded-xl border border-zinc-800/80 flex flex-wrap items-center justify-between gap-3 font-mono text-xs shadow-sm">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center space-x-2">
              <Calendar className="w-3.5 h-3.5 text-zinc-500" />
              <label className="text-zinc-400 uppercase tracking-wider text-[10px]">From:</label>
              <input 
                type="date" 
                value={fromDate}
                min={data.date_bounds.min_date}
                max={data.date_bounds.max_date}
                onChange={(e) => setFromDate(e.target.value)}
                className="bg-zinc-950 border border-zinc-800 px-2.5 py-1 rounded-lg text-zinc-200 outline-none focus:border-zinc-700 text-xs"
              />
            
              <label className="text-zinc-400 uppercase tracking-wider text-[10px]"> To:</label>
              <input 
                type="date" 
                value={toDate}
                min={data.date_bounds.min_date}
                max={data.date_bounds.max_date}
                onChange={(e) => setToDate(e.target.value)}
                className="bg-zinc-950 border border-zinc-800 px-2.5 py-1 rounded-lg text-zinc-200 outline-none focus:border-zinc-700 text-xs"
              />
            </div>

            <span className="text-zinc-500 hidden sm:inline text-[11px]">
              Data Bounds: <span className="text-zinc-300">{data.date_bounds.min_date}</span> to <span className="text-zinc-300">{data.date_bounds.max_date}</span>
            </span>
          </div>

          <div className="flex items-center space-x-2">
            <button 
              type="submit" 
              disabled={loading}
              className="flex items-center space-x-1.5 px-3 py-1 bg-zinc-100 hover:bg-white text-zinc-950 font-bold rounded-lg shadow transition-colors disabled:opacity-50 cursor-pointer text-xs"
            >
              <Filter className="w-3.5 h-3.5" />
              <span>{loading ? 'Evaluating...' : 'Apply Filter'}</span>
            </button>
            <button 
              type="button" 
              onClick={handleResetFilter}
              className="flex items-center space-x-1.5 px-2.5 py-1 border border-zinc-800 text-zinc-400 hover:bg-zinc-800 rounded-lg transition-colors cursor-pointer text-xs"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Full Range</span>
            </button>
          </div>
        </form>
      )}

      {/* Loading Overlay */}
      {loading && (
        <div className="flex flex-col justify-center items-center h-48 text-zinc-500 font-mono gap-2">
          <div className="animate-spin rounded-full h-7 w-7 border-b-2 border-cyan-400"></div>
          <p className="text-xs tracking-wider">EVALUATING DOUBLE-ENTRY MATRIX...</p>
        </div>
      )}

      {error && (
        <div className="p-3 bg-rose-950/40 border border-rose-800/80 rounded-xl text-rose-300 font-mono text-xs">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-rose-400" />
            <span className="font-bold">Evaluation Engine Exception:</span>
          </div>
          <p className="mt-1 text-rose-400">{error}</p>
        </div>
      )}

      {/* Empty State */}
      {!loading && data && data.category_breakdown.length === 0 && (
        <div className="p-8 bg-zinc-900/60 border border-zinc-800 rounded-xl text-center text-zinc-400 font-mono text-xs my-4">
          <p className="text-zinc-200 font-bold text-sm mb-1">No Ledger Activity Found</p>
          <p className="text-zinc-500">
            Account Node #{selectedAccountId} has no recorded double-entry transactions within the selected parameters.
          </p>
        </div>
      )}

      {data && data.category_breakdown.length > 0 && (
        <>
          {/* Executive KPI Summary TableEngine */}
          <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4 shadow-md space-y-2">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-zinc-800/60 pb-2 gap-2">
              <div>
                <h2 className="text-xs font-mono uppercase tracking-wider text-zinc-100 font-bold">
                  Executive KPI Summary Matrix
                </h2>
                <p className="text-[11px] text-zinc-500 font-mono">
                  Detailed breakdown of high-level net liquidity, inflows, outflows, and pending suspense.
                </p>
              </div>

              {/* ⚡ SMART CLEARANCE HUB & KPI CSV EXPORT */}
              <div className="flex items-center gap-2 shrink-0">
                <button
                  type="button"
                  onClick={() => exportToCSV(kpiTableData, `KPI_Summary_Node_${selectedAccountId}`)}
                  className="flex items-center gap-1.5 bg-zinc-950 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 px-2.5 py-1 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer shadow-sm"
                  title="Export KPI Summary Matrix to CSV"
                >
                  <Download className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                  <span>Export KPIs</span>
                </button>

                <button
                  type="button"
                  onClick={() => setIsSweepHubOpen(true)}
                  className="flex items-center gap-1.5 bg-linear-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-zinc-950 px-3 py-1 rounded-lg text-xs font-mono font-bold shadow-lg transition-all cursor-pointer z-10"
                >
                  <Zap className="w-3.5 h-3.5 fill-zinc-950 shrink-0" />
                  <span>Node 99 Rule Sweep Hub</span>
                </button>
              </div>
            </div>

            <TableEngine 
              columns={KPI_SUMMARY_COLUMNS} 
              data={kpiTableData} 
              showFooter={false}
            />
          </div>

          {/* Interactive Inflow/Outflow Distribution Bar Chart */}
          <div className="bg-zinc-900/80 border border-zinc-800 p-4 rounded-xl shadow-md space-y-3">
            
            {/* Header with Class Selector Tabs */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-zinc-800/80 pb-3">
              
              <div className="space-y-0.5">
                <div className="flex items-center space-x-2">
                  <span className={`w-2 h-2 rounded-full animate-pulse ${
                    activeChartTab === 'Expense' ? 'bg-cyan-400' : 'bg-emerald-400'
                  }`} />
                  <h2 className="text-xs font-mono uppercase tracking-wider text-zinc-100 font-extrabold" style={{ fontWeight: 800 }}>
                    Major {activeChartTab === 'Expense' ? 'Expense' : 'Income'} Distribution
                  </h2>
                </div>
                <p className="text-[11px] text-zinc-400 font-mono">
                  Visual concentration analysis of top {activeChartTab.toLowerCase()} categories.
                </p>
              </div>

              {/* Segmented Control & Stat Pills */}
              <div className="flex flex-wrap items-center gap-2 font-mono">
                
                {/* Outflow vs Inflow Toggle Controls */}
                <div className="bg-zinc-950 border border-zinc-800 p-0.5 rounded-lg flex items-center space-x-1 shadow-inner">
                  <button
                    type="button"
                    onClick={() => setActiveChartTab('Expense')}
                    className={`px-2.5 py-1 rounded-md text-xs font-bold transition-all flex items-center space-x-1 cursor-pointer ${
                      activeChartTab === 'Expense'
                        ? 'bg-rose-950/80 text-rose-300 border border-rose-800/80 shadow'
                        : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    <ArrowDownRight className="w-3 h-3 text-rose-400" />
                    <span>Outflows (Expenses)</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setActiveChartTab('Income')}
                    className={`px-2.5 py-1 rounded-md text-xs font-bold transition-all flex items-center space-x-1 cursor-pointer ${
                      activeChartTab === 'Income'
                        ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-800/80 shadow'
                        : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    <ArrowUpRight className="w-3 h-3 text-emerald-400" />
                    <span>Inflows (Income)</span>
                  </button>
                </div>

                {/* Stat Pill: Top Category */}
                {chartData.length > 0 && (
                  <div className="bg-zinc-950/90 border border-zinc-800/90 px-3 py-1 rounded-lg flex flex-col justify-center space-y-0.5 shadow-inner">
                    <span className="text-zinc-500 text-[9px] uppercase tracking-wider block" style={{ fontWeight: 600 }}>
                      Top {activeChartTab === 'Expense' ? 'Outflow' : 'Inflow'}
                    </span>
                    <div className="flex items-center space-x-1">
                      <span className="text-cyan-300 text-xs font-bold">
                        {topCategoryName}
                      </span>
                      <span className="px-1 py-0.2 bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 rounded text-[9px] font-bold">
                        {topCategoryPct}%
                      </span>
                    </div>
                  </div>
                )}

                {/* Stat Pill: Total Analyzed */}
                {chartData.length > 0 && (
                  <div className="bg-zinc-950/90 border border-zinc-800/90 px-3 py-1 rounded-lg flex flex-col justify-center space-y-0.5 shadow-inner">
                    <span className="text-zinc-500 text-[9px] uppercase tracking-wider block" style={{ fontWeight: 600 }}>
                      Analyzed {activeChartTab}
                    </span>
                    <span className={`text-xs tabular-nums font-black ${
                      activeChartTab === 'Expense' ? 'text-rose-400' : 'text-emerald-400'
                    }`}>
                      {formatINR(totalSum)}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Chart Canvas */}
            <div className="w-full pt-1 h-70">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart 
                  data={chartData} 
                  margin={{ top: 20, right: 10, left: 10, bottom: 35 }} 
                  onClick={(state: any) => {
                    if (state && state.activePayload && state.activePayload.length) {
                      handleBarClick(state.activePayload[0].payload);
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
                    angle={-15}
                    textAnchor="end"
                  />
                  <YAxis 
                    stroke="#71717a" 
                    fontSize={10} 
                    tickLine={false}
                    tickFormatter={(value: number) => `₹${(value / 100000).toFixed(1)}L`} 
                  />
                  <Tooltip 
                    content={<CustomChartTooltip />} 
                    cursor={{ fill: 'rgba(255, 255, 255, 0.05)' }} 
                  />
                  <Bar 
                    dataKey="amount" 
                    radius={[4, 4, 0, 0]} 
                    className="cursor-pointer"
                    onClick={(entry: any) => handleBarClick(entry)}
                  >
                    <LabelList 
                      dataKey="amount" 
                      position="top" 
                      formatter={(val: any) => {
                        const num = typeof val === 'number' ? val : parseFloat(val || '0');
                        return num > 0 ? `₹${(num / 100000).toFixed(1)}L` : '';
                      }} 
                      style={{ 
                        fill: activeChartTab === 'Expense' ? '#22f50f' : '#34d399', 
                        fontSize: '9px', 
                        fontFamily: 'monospace', 
                        fontWeight: 'bold' 
                      }} 
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* TableEngine Section */}
          <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4 shadow-md">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h2 className="text-xs font-mono uppercase tracking-wider text-zinc-100 font-bold">Taxonomy Breakdown Matrix</h2>
                <p className="text-[11px] text-zinc-500 font-mono">Audited double-entry class breakdown across primary groups and subcategories.</p>
              </div>

              {/* 🟢 CSV Export Button for Taxonomy Matrix */}
              <div className="flex items-center gap-2 shrink-0">
                <button
                  type="button"
                  onClick={() => exportToCSV(data.category_breakdown, `Taxonomy_Breakdown_Node_${selectedAccountId}`)}
                  className="flex items-center gap-1.5 bg-zinc-950 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 px-3 py-1 rounded-lg text-xs font-mono font-bold transition-all cursor-pointer shadow-sm"
                  title="Export Taxonomy Breakdown Matrix to CSV"
                >
                  <Download className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                  <span>Export CSV</span>
                </button>

                <span className="text-xs font-mono bg-zinc-950 border border-zinc-800 px-2.5 py-1 rounded-lg text-zinc-400">
                  {data.category_breakdown.length} line items
                </span>
              </div>
            </div>

            <TableEngine 
              columns={CATEGORY_BREAKDOWN_COLUMNS} 
              data={data.category_breakdown} 
              showFooter={true}
              onRowClick={(row: any) => {
                if (row?.subcategory) {
                  setSelectedSubcategoryForWorkbench(row.subcategory);
                  setIsWorkbenchOpen(true);
                }
              }}
            />
          </div>
        </>
      )}

      {/* 🟢 1. Classification Workbench Modal */}
      <ClassificationWorkbenchModal
        isOpen={isWorkbenchOpen}
        targetSubcategory={selectedSubcategoryForWorkbench}
        onClose={() => setIsWorkbenchOpen(false)}
        onSuccess={handleWorkbenchSuccess}
        accountId={selectedAccountId ? Number(selectedAccountId) : undefined}
      />

      {/* 🟢 2. Bulk Smart Rule Clearance Hub Modal */}
      <BulkSweephubModal
        isOpen={isSweepHubOpen}
        onClose={() => setIsSweepHubOpen(false)}
        accountId="99"
        onSweepComplete={handleWorkbenchSuccess}
      />

    </div>
  );
};

export default LedgerDashboard;