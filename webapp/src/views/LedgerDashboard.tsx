import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { 
  CheckCircle2, 
  AlertTriangle, 
  Wallet, 
  TrendingUp, 
  TrendingDown, 
  HelpCircle, 
  Calendar, 
  RotateCcw, 
  Filter,
  Layers
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
import { CATEGORY_BREAKDOWN_COLUMNS } from '../components/ui/data-table/columns';
import { ClassificationWorkbenchModal } from './classificationWorkbenchmodal';

import { 
  getDashboardSummary, 
  getAccounts,
  type DashboardSummaryResponse, 
  type DashboardParams,
  type AccountNode 
} from '../api';

export const LedgerDashboard: React.FC = () => {
  const [accounts, setAccounts] = useState<AccountNode[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('3');

  const [data, setData] = useState<DashboardSummaryResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [fromDate, setFromDate] = useState<string>('');
  const [toDate, setToDate] = useState<string>('');

  const [isWorkbenchOpen, setIsWorkbenchOpen] = useState<boolean>(false);
  
  const [selectedSubcategoryForWorkbench, setSelectedSubcategoryForWorkbench] = useState<string>('Suspense Account');

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
      console.error('Failed to fetch ledger dashboard data:', err);
      setError('Failed to connect to Django API. Ensure backend server is running on port 8000.');
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


  const handleBarClick = (data: any) => {
      console.log('Bar item clicked:', data);

      // Extract name/subcategory from Recharts click payload
      const subcategoryName =
        data?.subcategory ||
        data?.name ||
        data?.payload?.subcategory ||
        data?.payload?.name;

      if (subcategoryName) {
        setSelectedSubcategoryForWorkbench(subcategoryName);
      }

      setIsWorkbenchOpen(true);
    };

  const handleWorkbenchSuccess = () => {
    // Re-fetch dashboard & chart data so graph updates in real time!
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

  // Top Expense Subcategories Dataset with pre-calculated metrics & colors
  const { chartData, topCategoryName, topCategoryPct, totalExpenseSum } = useMemo(() => {
    if (!data?.category_breakdown) {
      return { chartData: [], topCategoryName: 'N/A', topCategoryPct: 0, totalExpenseSum: 0 };
    }

    const expenses = data.category_breakdown.filter(
      (row) => (row.category || 'Uncategorized') === 'Expense'
    );

    const totalSum = expenses.reduce((acc, row) => acc + parseFloat(row.total_debit || '0'), 0);

    const formattedData = expenses
      .map((row) => {
        const amt = parseFloat(row.total_debit || '0');
        const pct = totalSum > 0 ? (amt / totalSum) * 100 : 0;
        return {
          subcategory: row.subcategory || 'Suspense',
          amount: amt,
          count: row.transaction_count,
          percentage: pct.toFixed(1),
          fill: row.subcategory === 'Suspense Account' ? '#f59e0b' : '#38bdf8',
        };
      })
      .sort((a, b) => b.amount - a.amount)
      .slice(0, 8);

    const topItem = formattedData[0];

    return {
      chartData: formattedData,
      topCategoryName: topItem ? topItem.subcategory : 'N/A',
      topCategoryPct: topItem ? topItem.percentage : '0',
      totalExpenseSum: totalSum,
    };
  }, [data]);

  const inrFormatter = new Intl.NumberFormat('en-IN', { 
    style: 'currency', 
    currency: 'INR',
    maximumFractionDigits: 2 
  });

  const CustomChartTooltip = ({ active, payload }: any) => {
    if (!active || !payload || !payload.length) return null;

    const data = payload[0].payload;
    const isSuspense = data.subcategory === 'Suspense Account';
    const amount = data.amount || 0;
    const count = data.count || 0;
    const avgAmount = count > 0 ? amount / count : 0;

    return (
      <div 
        className="bg-zinc-950/95 backdrop-blur-md border border-zinc-700/80 p-3.5 rounded-xl shadow-2xl font-mono text-xs space-y-2.5 min-w-[245px]"
        style={{
          backgroundColor: '#09090b',
          border: '1px solid #3f3f46',
          color: '#f4f4f5'
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between pb-2 gap-2" style={{ borderBottom: '1px solid #27272a' }}>
          <div className="flex items-center space-x-2 truncate">
            <span 
              className="w-2.5 h-2.5 rounded-full flex-shrink-0 animate-pulse shadow-sm" 
              style={{ backgroundColor: data.fill || (isSuspense ? '#f59e0b' : '#38bdf8') }} 
            />
            <span className="font-bold text-zinc-100 truncate text-xs">{data.subcategory} : </span>
          
            <span
              className={`px-2 py-0.5 text-[10px] rounded-md font-bold shrink-0 uppercase tracking-wider ${
                isSuspense
                  ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                  : 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30'
              }`}
            >
              {data.percentage}% Share
            </span>
          </div>
        </div>

        {/* Metrics Breakdown */}
        <div className="space-y-1.5 text-[11px]">
          {/* Total Outflow */}
          <div className="flex justify-between items-center bg-rose-950/20 border border-rose-900/30 px-2.5 py-1.5 rounded-lg">
            <span className="text-zinc-400 font-medium">Total Outflow : </span>
            <span className={`font-bold tabular-nums ${isSuspense ? 'text-amber-400' : 'text-rose-400'}`}>
              {inrFormatter.format(amount)}
            </span>
          </div>

          {/* Transaction Volume */}
          <div className="flex justify-between items-center bg-zinc-900/80 border border-zinc-800/80 px-2.5 py-1 rounded-lg">
            <span className="text-zinc-400">Total Volume : </span>
            <span className="font-bold text-cyan-400 tabular-nums">
              {count} <span className="text-[10px] text-zinc-500 font-normal"> txns</span>
            </span>
          </div>

          {/* Average per Transaction */}
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
    <div className="p-6 max-w-7xl mx-auto space-y-6 bg-zinc-950 min-h-screen text-zinc-100 font-sans">
      
      {/* 1. Integrated Header & Context Switcher */}
      <div className="bg-zinc-900/80 border border-zinc-800/80 p-5 rounded-2xl shadow-xl backdrop-blur-sm space-y-4">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <Layers className="w-4 h-4 text-cyan-400" />
              <h1 className="text-sm font-mono uppercase tracking-wider text-zinc-100 font-bold">
                Project Sync-Shield
              </h1>
            </div>
            <p className="text-xs text-zinc-400 font-mono">
              Target Ledger Node: <span className="text-cyan-400 font-semibold">{activeAccountName}</span>
            </p>
          </div>

          <div className="w-full md:w-80 font-mono text-xs">
            <select
              value={selectedAccountId}
              onChange={(e) => setSelectedAccountId(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 p-2.5 rounded-xl text-zinc-100 font-bold focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/50 cursor-pointer shadow-inner"
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

        {/* Symmetry Status Banner */}
        {data && (
          <div className="pt-3 border-t border-zinc-800/60 flex flex-wrap justify-between items-center text-xs font-mono gap-3">
            <div className="text-zinc-400 flex items-center space-x-2">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
              <span>Active Context Node ID: <strong className="text-zinc-200">{data.symmetry_proof.bank_account_id}</strong></span>
              <span className="text-zinc-600">|</span>
              <span>Taxonomy Integration Node: <strong className="text-zinc-200">Account 99</strong></span>
            </div>

            <div className="flex items-center space-x-3">
              <div className={`px-3 py-1 rounded-full text-[11px] font-bold flex items-center space-x-1.5 border ${
                data.symmetry_proof.is_balanced 
                  ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800/80' 
                  : 'bg-rose-950/60 text-rose-400 border-rose-800/80'
              }`}>
                {data.symmetry_proof.is_balanced ? (
                  <CheckCircle2 className="w-3.5 h-3.5" />
                ) : (
                  <AlertTriangle className="w-3.5 h-3.5" />
                )}
                <span>{data.symmetry_proof.is_balanced ? 'DOUBLE-ENTRY BALANCED' : 'LEDGER IMBALANCE'}</span>
              </div>
              <span className="text-zinc-500">
                Variance: <strong className="text-zinc-300">₹{data.symmetry_proof.variance.toFixed(2)}</strong>
              </span>
            </div>
          </div>
        )}
      </div>

      {/* 2. Date Filter Control Bar */}
      {data && (
        <form onSubmit={handleApplyFilter} className="bg-zinc-900/50 p-4 rounded-xl border border-zinc-800/80 flex flex-wrap items-center justify-between gap-4 font-mono text-xs shadow-sm">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center space-x-2">
              <Calendar className="w-3.5 h-3.5 text-zinc-500" />
              <label className="text-zinc-400 uppercase tracking-wider text-[11px]">From:</label>
              <input 
                type="date" 
                value={fromDate}
                min={data.date_bounds.min_date}
                max={data.date_bounds.max_date}
                onChange={(e) => setFromDate(e.target.value)}
                className="bg-zinc-950 border border-zinc-800 px-3 py-1.5 rounded-lg text-zinc-200 outline-none focus:border-zinc-700"
              />
            </div>

            <div className="flex items-center space-x-2">
              <label className="text-zinc-400 uppercase tracking-wider text-[11px]">To:</label>
              <input 
                type="date" 
                value={toDate}
                min={data.date_bounds.min_date}
                max={data.date_bounds.max_date}
                onChange={(e) => setToDate(e.target.value)}
                className="bg-zinc-950 border border-zinc-800 px-3 py-1.5 rounded-lg text-zinc-200 outline-none focus:border-zinc-700"
              />
            </div>

            <span className="text-zinc-500 hidden sm:inline">
              Data Bounds: <span className="text-zinc-300">{data.date_bounds.min_date}</span> to <span className="text-zinc-300">{data.date_bounds.max_date}</span>
            </span>
          </div>

          <div className="flex items-center space-x-2">
            <button 
              type="submit" 
              disabled={loading}
              className="flex items-center space-x-1.5 px-4 py-1.5 bg-zinc-100 hover:bg-white text-zinc-950 font-bold rounded-lg shadow transition-colors disabled:opacity-50"
            >
              <Filter className="w-3.5 h-3.5" />
              <span>{loading ? 'Evaluating...' : 'Apply Filter'}</span>
            </button>
            <button 
              type="button" 
              onClick={handleResetFilter}
              className="flex items-center space-x-1.5 px-3 py-1.5 border border-zinc-800 text-zinc-400 hover:bg-zinc-800 rounded-lg transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Full Range</span>
            </button>
          </div>
        </form>
      )}

      {/* Loading Overlay */}
      {loading && (
        <div className="flex flex-col justify-center items-center h-64 text-zinc-500 font-mono gap-3">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-400"></div>
          <p className="text-xs tracking-wider">EVALUATING DOUBLE-ENTRY MATRIX...</p>
        </div>
      )}

      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800/80 rounded-xl text-rose-300 font-mono text-xs">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-rose-400" />
            <span className="font-bold">Evaluation Engine Exception:</span>
          </div>
          <p className="mt-1 text-rose-400">{error}</p>
        </div>
      )}

      {/* Empty State */}
      {!loading && data && data.category_breakdown.length === 0 && (
        <div className="p-12 bg-zinc-900/60 border border-zinc-800 rounded-2xl text-center text-zinc-400 font-mono text-xs my-6">
          <p className="text-zinc-200 font-bold text-sm mb-1">No Ledger Activity Found</p>
          <p className="text-zinc-500">
            Account Node #{selectedAccountId} has no recorded double-entry transactions within the selected parameters.
          </p>
        </div>
      )}

      {data && data.category_breakdown.length > 0 && (
        <>
          {/* 3. Refined KPI Cards Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-zinc-900/80 border border-zinc-800 p-5 rounded-2xl shadow-md relative overflow-hidden group hover:border-zinc-700 transition-colors">
              <div className="flex items-center justify-between text-zinc-400 font-mono text-xs">
                <span className="tracking-wider uppercase">Net Liquidity</span>
                <Wallet className="w-4 h-4 text-zinc-500 group-hover:text-cyan-400 transition-colors" />
              </div>
              <p className={`text-2xl font-bold font-mono mt-3 ${data.kpis.net_liquidity >= 0 ? 'text-cyan-400' : 'text-amber-400'}`}>
                {formatINR(data.kpis.net_liquidity)}
              </p>
              <p className="text-[11px] text-zinc-500 font-mono mt-1">Period Net Cash Flow</p>
            </div>

            <div className="bg-zinc-900/80 border border-zinc-800 p-5 rounded-2xl shadow-md relative overflow-hidden group hover:border-zinc-700 transition-colors">
              <div className="flex items-center justify-between text-zinc-400 font-mono text-xs">
                <span className="tracking-wider uppercase">Total Revenue</span>
                <TrendingUp className="w-4 h-4 text-emerald-500" />
              </div>
              <p className="text-2xl font-bold font-mono text-emerald-400 mt-3">
                {formatINR(data.kpis.total_income)}
              </p>
              <p className="text-[11px] text-zinc-500 font-mono mt-1">Recognized Inflow</p>
            </div>

            <div className="bg-zinc-900/80 border border-zinc-800 p-5 rounded-2xl shadow-md relative overflow-hidden group hover:border-zinc-700 transition-colors">
              <div className="flex items-center justify-between text-zinc-400 font-mono text-xs">
                <span className="tracking-wider uppercase">Total Expenses</span>
                <TrendingDown className="w-4 h-4 text-rose-500" />
              </div>
              <p className="text-2xl font-bold font-mono text-rose-400 mt-3">
                {formatINR(data.kpis.total_expense)}
              </p>
              <p className="text-[11px] text-zinc-500 font-mono mt-1">Operating & Charges</p>
            </div>

            <div className="bg-zinc-900/80 border border-zinc-800 p-5 rounded-2xl shadow-md relative overflow-hidden group hover:border-zinc-700 transition-colors">
              <div className="flex items-center justify-between text-zinc-400 font-mono text-xs">
                <span className="tracking-wider uppercase">Unclassified Suspense</span>
                <HelpCircle className="w-4 h-4 text-amber-500" />
              </div>
              <p className="text-2xl font-bold font-mono text-amber-400 mt-3">
                {data.kpis.suspense_count} <span className="text-xs font-normal text-zinc-500">txns</span>
              </p>
              <p className="text-[11px] text-amber-500/80 font-mono mt-1">{formatINR(data.kpis.suspense_amount)} pending</p>
            </div>
          </div>

          
          {/* Polished Recharts Major Expense Bar Chart */}
          <div className="bg-zinc-900/80 border border-zinc-800 p-6 rounded-2xl shadow-md space-y-4">
            
            {/* Header with Quick Stat Pill Callouts */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-zinc-800/60 pb-4">
              <div>
                <h2 className="text-sm font-mono uppercase tracking-wider text-zinc-100 font-bold">
                  Major Expense Distribution
                </h2>
                <p className="text-xs text-zinc-500 font-mono">
                  Visual concentration analysis of top operating spend categories.
                </p>
              </div>

              {chartData.length > 0 && (
                <div className="flex items-center space-x-2 font-mono text-xs">
                  <div className="bg-zinc-950 border border-zinc-800 px-3 py-1.5 rounded-xl">
                    <span className="text-zinc-500 text-[10px] block uppercase">Top Outflow Category</span>
                    <span className="text-cyan-400 font-bold">{topCategoryName} ({topCategoryPct}%)</span>
                  </div>
                  <div className="bg-zinc-950 border border-zinc-800 px-3 py-1.5 rounded-xl">
                    <span className="text-zinc-500 text-[10px] block uppercase">Analyzed Spend</span>
                    <span className="text-zinc-200 font-bold">{formatINR(totalExpenseSum)}</span>
                  </div>
                </div>
              )}
            </div>
            
            {/* Chart Canvas */}
            <div className="w-full pt-2 min-h-[340px]">
              <ResponsiveContainer width="100%" height={320}>
                <BarChart 
                  data={chartData} 
                  margin={{ top: 25, right: 10, left: 10, bottom: 45 }} 
                  onClick={(state: any) => {
                    if (state && state.activePayload && state.activePayload.length) {
                      console.log('Chart clicked:', state.activePayload[0].payload);
                      setIsWorkbenchOpen(true);
                    }
                  }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                  <XAxis 
                    dataKey="subcategory" 
                    stroke="#71717a" 
                    fontSize={11} 
                    tickLine={false}
                    interval={0}
                    angle={-20}
                    textAnchor="end"
                  />
                  <YAxis 
                    stroke="#71717a" 
                    fontSize={11} 
                    tickLine={false}
                    tickFormatter={(value: number) => `₹${(value / 100000).toFixed(1)}L`} 
                  />
                  <Tooltip 
                    content={<CustomChartTooltip />} 
                    cursor={{ fill: 'rgba(255, 255, 255, 0.05)' }} 
                  />
                        <Bar 
                          dataKey="amount" 
                          radius={[6, 6, 0, 0]} 
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
                      style={{ fill: '#22f50f', fontSize: '10px', fontFamily: 'monospace', fontWeight: 'bold' }} 
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          

          {/* 5. TableEngine Section */}
          <div className="bg-zinc-900/80 border border-zinc-800 rounded-2xl p-6 shadow-md">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-mono uppercase tracking-wider text-zinc-100 font-bold">Taxonomy Breakdown Matrix</h2>
                <p className="text-xs text-zinc-500 font-mono">Audited double-entry class breakdown across primary groups and subcategories.</p>
              </div>
              <span className="text-xs font-mono bg-zinc-950 border border-zinc-800 px-3 py-1 rounded-lg text-zinc-400">
                {data.category_breakdown.length} line items
              </span>
            </div>

            <TableEngine 
              columns={CATEGORY_BREAKDOWN_COLUMNS} 
              data={data.category_breakdown} 
            />
          </div>
        </>
      )}

      {/* Classification Workbench Modal — Placed Safely at Root Level */}
      <ClassificationWorkbenchModal
        isOpen={isWorkbenchOpen}
        targetSubcategory={selectedSubcategoryForWorkbench}
        onClose={() => setIsWorkbenchOpen(false)}
        onSuccess= {handleWorkbenchSuccess
          
        }
      />

    </div>
  );
};

export default LedgerDashboard;