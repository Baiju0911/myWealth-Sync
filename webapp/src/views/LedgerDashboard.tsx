import React, { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import { 
  CheckCircle2, 
  AlertTriangle, 
  Wallet, 
  TrendingUp, 
  TrendingDown, 
  HelpCircle, 
  Calendar, 
  RotateCcw, 
  Filter 
} from 'lucide-react';
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  Tooltip, 
  ResponsiveContainer, 
  CartesianGrid,
  Cell
} from 'recharts';

import { TableEngine } from '../components/ui/data-table/TableEngine';
import { CATEGORY_BREAKDOWN_COLUMNS } from '../components/ui/data-table/columns';

// Interfaces matching backend API
interface AccountNode {
  id: string | number;
  name: string;
  account_number: string;
}

interface DateBounds {
  min_date: string;
  max_date: string;
  applied_from_date: string;
  applied_to_date: string;
}

interface KPISummary {
  net_liquidity: number;
  total_income: number;
  total_expense: number;
  suspense_count: number;
  suspense_amount: number;
}

interface SymmetryProof {
  bank_account_id: number;
  taxonomy_account_id: number;
  bank_net: number;
  taxonomy_net: number;
  variance: number;
  is_balanced: boolean;
}

export interface CategoryRow {
  category: string | null;
  subcategory: string | null;
  transaction_count: number;
  total_debit: string;
  total_credit: string;
  net_balance: string;
}

interface DashboardData {
  date_bounds: DateBounds;
  kpis: KPISummary;
  symmetry_proof: SymmetryProof;
  category_breakdown: CategoryRow[];
}

export const LedgerDashboard: React.FC = () => {
  // Accounts State
  const [accounts, setAccounts] = useState<AccountNode[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('3');

  // Dashboard Metrics State
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filter States
  const [fromDate, setFromDate] = useState<string>('');
  const [toDate, setToDate] = useState<string>('');

  // 1. Fetch Accounts List
  useEffect(() => {
    const fetchAccounts = async () => {
      try {
        const response = await axios.get<AccountNode[]>('http://127.0.0.1:8000/api/accounts/');
        setAccounts(response.data);
      } catch (err) {
        console.error('Failed to load accounts list:', err);
      }
    };
    fetchAccounts();
  }, []);

  // 2. Fetch Dashboard Metrics
  const fetchDashboardData = async (from?: string, to?: string, accountId: string = '3') => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string | number> = {
        bank_account_id: accountId,
        taxonomy_account_id: 99,
      };
      if (from) params.from_date = from;
      if (to) params.to_date = to;

      const response = await axios.get<DashboardData>('http://127.0.0.1:8000/api/dashboard/summary/', { params });
      
      setData(response.data);
      if (!from) setFromDate(response.data.date_bounds.applied_from_date);
      if (!to) setToDate(response.data.date_bounds.applied_to_date);
    } catch (err: any) {
      console.error('Failed to fetch ledger dashboard data:', err);
      setError('Failed to connect to Django API. Ensure backend server is running on port 8000.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedAccountId) {
      fetchDashboardData(fromDate || undefined, toDate || undefined, selectedAccountId);
    }
  }, [selectedAccountId]);

  const handleApplyFilter = (e: React.FormEvent) => {
    e.preventDefault();
    fetchDashboardData(fromDate, toDate, selectedAccountId);
  };

  const handleResetFilter = () => {
    if (data) {
      setFromDate(data.date_bounds.min_date);
      setToDate(data.date_bounds.max_date);
      fetchDashboardData(data.date_bounds.min_date, data.date_bounds.max_date, selectedAccountId);
    }
  };

  const formatINR = (val: number | string) => {
    const num = typeof val === 'string' ? parseFloat(val) : val;
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(num || 0);
  };

  // Chart Visual Dataset
  const chartData = useMemo(() => {
    if (!data?.category_breakdown) return [];
    return data.category_breakdown
      .filter((row) => (row.category || 'Uncategorized') === 'Expense')
      .map((row) => ({
        subcategory: row.subcategory || 'Suspense',
        amount: parseFloat(row.total_debit || '0'),
        isSuspense: row.subcategory === 'Suspense Account',
      }))
      .sort((a, b) => b.amount - a.amount)
      .slice(0, 8);
  }, [data]);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6 bg-zinc-950 min-h-screen text-zinc-100 font-sans">
      
      {/* 1. Account Selector Context Bar */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center bg-zinc-900 border border-zinc-800 p-4 rounded-xl gap-4">
        <div>
          <h1 className="text-sm font-mono uppercase tracking-wider text-zinc-200 font-bold">Project Sync-Shield</h1>
          <p className="text-xs text-zinc-500 font-mono">Select target isolation account context to run evaluation gates.</p>
        </div>
        <div className="w-full sm:w-72 font-mono text-xs">
          <select
            value={selectedAccountId}
            onChange={(e) => setSelectedAccountId(e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-800 p-2.5 rounded-lg text-zinc-100 font-bold focus:outline-hidden focus:border-zinc-700 cursor-pointer"
          >
            <option value="">-- Select Active Ledger Account --</option>
            {accounts.map((acc) => (
              <option key={acc.id} value={acc.id}>
                {acc.name} ({acc.account_number ? acc.account_number.slice(-4) : acc.id})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* 2. Double-Entry Symmetry & Status Banner */}
      {data && (
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center bg-zinc-900/50 p-4 rounded-xl border border-zinc-800 gap-4">
          <div className="text-xs text-zinc-400 font-mono">
            Active Context: <span className="text-zinc-200 font-bold">Node ID {data.symmetry_proof.bank_account_id}</span> | Target Node: <span className="text-zinc-200 font-bold">Account 99</span>
          </div>

          <div className="flex items-center space-x-3">
            <div className={`px-3 py-1.5 rounded-full text-xs font-semibold font-mono flex items-center space-x-1.5 border ${
              data.symmetry_proof.is_balanced 
                ? 'bg-emerald-950/80 text-emerald-400 border-emerald-800/60' 
                : 'bg-rose-950/80 text-rose-400 border-rose-800/60'
            }`}>
              {data.symmetry_proof.is_balanced ? (
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              ) : (
                <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
              )}
              <span>{data.symmetry_proof.is_balanced ? 'DOUBLE-ENTRY BALANCED' : 'LEDGER IMBALANCE'}</span>
            </div>
            <span className="text-xs text-zinc-500 font-mono">
              Variance: ₹{data.symmetry_proof.variance.toFixed(2)}
            </span>
          </div>
        </div>
      )}

      {/* 3. Date Filter Control Bar */}
      {data && (
        <form onSubmit={handleApplyFilter} className="bg-zinc-900/40 p-4 rounded-xl border border-zinc-800 flex flex-wrap items-center justify-between gap-4 font-mono text-xs">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center space-x-2">
              <Calendar className="w-3.5 h-3.5 text-zinc-500" />
              <label className="text-zinc-400 uppercase">From:</label>
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
              <label className="text-zinc-400 uppercase">To:</label>
              <input 
                type="date" 
                value={toDate}
                min={data.date_bounds.min_date}
                max={data.date_bounds.max_date}
                onChange={(e) => setToDate(e.target.value)}
                className="bg-zinc-950 border border-zinc-800 px-3 py-1.5 rounded-lg text-zinc-200 outline-none focus:border-zinc-700"
              />
            </div>

            <span className="text-zinc-500">
              Bounds: <span className="text-zinc-300">{data.date_bounds.min_date}</span> to <span className="text-zinc-300">{data.date_bounds.max_date}</span>
            </span>
          </div>

          <div className="flex items-center space-x-2">
            <button 
              type="submit" 
              disabled={loading}
              className="flex items-center space-x-1 px-4 py-1.5 bg-zinc-100 hover:bg-white text-zinc-950 font-bold rounded-lg shadow-sm transition-colors disabled:opacity-50"
            >
              <Filter className="w-3.5 h-3.5" />
              <span>{loading ? 'Filtering...' : 'Apply Filter'}</span>
            </button>
            <button 
              type="button" 
              onClick={handleResetFilter}
              className="flex items-center space-x-1 px-3 py-1.5 border border-zinc-800 text-zinc-400 hover:bg-zinc-800 rounded-lg transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Full Range</span>
            </button>
          </div>
        </form>
      )}

      {/* Loading Overlay */}
      {loading && !data && (
        <div className="flex flex-col justify-center items-center h-64 text-zinc-500 font-mono gap-2">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-zinc-200"></div>
          <p className="text-xs">Evaluating Double-Entry Matrix...</p>
        </div>
      )}

      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800 rounded-xl text-rose-300 font-mono text-xs">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-rose-400" />
            <span className="font-bold">Evaluation Engine Exception:</span>
          </div>
          <p className="mt-1 text-rose-400">{error}</p>
        </div>
      )}

      {data && (
        <>
          {/* 4. KPI Cards Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-zinc-900 border border-zinc-800 p-5 rounded-xl">
              <div className="flex items-center justify-between text-zinc-400 font-mono text-xs">
                <span>NET LIQUIDITY</span>
                <Wallet className="w-4 h-4 text-zinc-500" />
              </div>
              <p className={`text-2xl font-bold font-mono mt-2 ${data.kpis.net_liquidity >= 0 ? 'text-blue-400' : 'text-amber-400'}`}>
                {formatINR(data.kpis.net_liquidity)}
              </p>
              <p className="text-xs text-zinc-500 font-mono mt-1">Period Net Cash Movement</p>
            </div>

            <div className="bg-zinc-900 border border-zinc-800 p-5 rounded-xl">
              <div className="flex items-center justify-between text-zinc-400 font-mono text-xs">
                <span>TOTAL REVENUE</span>
                <TrendingUp className="w-4 h-4 text-emerald-500" />
              </div>
              <p className="text-2xl font-bold font-mono text-emerald-400 mt-2">
                {formatINR(data.kpis.total_income)}
              </p>
              <p className="text-xs text-zinc-500 font-mono mt-1">Recognized Revenue</p>
            </div>

            <div className="bg-zinc-900 border border-zinc-800 p-5 rounded-xl">
              <div className="flex items-center justify-between text-zinc-400 font-mono text-xs">
                <span>TOTAL EXPENSES</span>
                <TrendingDown className="w-4 h-4 text-rose-500" />
              </div>
              <p className="text-2xl font-bold font-mono text-rose-400 mt-2">
                {formatINR(data.kpis.total_expense)}
              </p>
              <p className="text-xs text-zinc-500 font-mono mt-1">Operating & Charges</p>
            </div>

            <div className="bg-zinc-900 border border-zinc-800 p-5 rounded-xl">
              <div className="flex items-center justify-between text-zinc-400 font-mono text-xs">
                <span>UNCLASSIFIED SUSPENSE</span>
                <HelpCircle className="w-4 h-4 text-amber-500" />
              </div>
              <p className="text-2xl font-bold font-mono text-amber-400 mt-2">
                {data.kpis.suspense_count} <span className="text-xs font-normal text-zinc-500">txns</span>
              </p>
              <p className="text-xs text-amber-500/80 font-mono mt-1">{formatINR(data.kpis.suspense_amount)} pending</p>
            </div>
          </div>

          {/* 5. Expense Bar Chart */}
          <div className="bg-zinc-900 border border-zinc-800 p-6 rounded-xl">
            <div className="mb-4">
              <h2 className="text-sm font-mono uppercase tracking-wider text-zinc-200 font-bold">Major Expense Breakdown</h2>
              <p className="text-xs text-zinc-500 font-mono">Visual analysis of leading expense subcategories for selected date range.</p>
            </div>
            
            <div className="h-72 w-full pt-2">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 10, right: 10, left: 20, bottom: 25 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                  <XAxis 
                    dataKey="subcategory" 
                    stroke="#71717a" 
                    fontSize={11} 
                    tickLine={false}
                    interval={0}
                    angle={-15}
                    textAnchor="end"
                  />
                  <YAxis 
                    stroke="#71717a" 
                    fontSize={11} 
                    tickLine={false}
                    tickFormatter={(value: number) => `₹${(value / 100000).toFixed(1)}L`} 
                  />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#09090b', borderColor: '#27272a', borderRadius: '0.5rem', color: '#f4f4f5' }}
                    formatter={(value: any) => [formatINR(Number(value)), 'Expense Amount']}
                  />
                  <Bar dataKey="amount" radius={[4, 4, 0, 0]}>
                    {chartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.isSuspense ? '#f59e0b' : '#3b82f6'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* 6. TableEngine using ColumnConfig */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
            <div className="mb-4">
              <h2 className="text-sm font-mono uppercase tracking-wider text-zinc-200 font-bold">Taxonomy Breakdown Matrix</h2>
              <p className="text-xs text-zinc-500 font-mono">Double-entry audit breakdown across primary classes and subcategories.</p>
            </div>

            <TableEngine 
              columns={CATEGORY_BREAKDOWN_COLUMNS} 
              data={data.category_breakdown} 
            />
          </div>
        </>
      )}

    </div>
  );
};

export default LedgerDashboard;