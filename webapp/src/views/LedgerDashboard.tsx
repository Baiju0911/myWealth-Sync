import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { AlertTriangle } from 'lucide-react';
import { 
  CandidateMatcherModal, 
  type TaxonomyMatchContext 
} from '../components/subledger/CandidateMatcherModal';

import { LedgerHeaderFilter } from '../components/Stage3/LedgerHeaderFilter';
import { ExecutiveKpiSection } from '../components/Stage3/ExecutiveKpiSection';
import { ExpenseIncomeDistributionChart } from '../components/Stage3/ExpenseIncomeDistributionChart';
import { TaxonomyMatrixSection } from '../components/Stage3/TaxonomyMatrixSection';

import { ClassificationWorkbenchModal } from '../components/Stage3/Workbench/ClassificationWorkbenchModal';
import BulkSweephubModal from './BulkSweepHubModal';
import { SubledgerBreakdownDrawer } from '../components/subledger/SubledgerBreakdownDrawer';

import {
  getDashboardSummary,
  getAccounts,
  type DashboardSummaryResponse,
  type DashboardParams,
  type AccountNode,
} from '../api/api';
import { subledgerApi } from '../api/subledger';

export const LedgerDashboard: React.FC = () => {
  const [accounts, setAccounts] = useState<AccountNode[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('99');

  const [data, setData] = useState<DashboardSummaryResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [isCandidateMatcherOpen, setIsCandidateMatcherOpen] = useState<boolean>(false);
  const [taxonomyMatchContext, setTaxonomyMatchContext] = useState<TaxonomyMatchContext | null>(null);

  const [fromDate, setFromDate] = useState<string>('');
  const [toDate, setToDate] = useState<string>('');
  const [activeChartTab, setActiveChartTab] = useState<'Expense' | 'Income'>('Expense');

  const [isWorkbenchOpen, setIsWorkbenchOpen] = useState<boolean>(false);
  const [selectedSubcategoryForWorkbench, setSelectedSubcategoryForWorkbench] = useState<string>('Suspense Account');

  const [isSweepHubOpen, setIsSweepHubOpen] = useState<boolean>(false);

  const [isSubledgerDrawerOpen, setIsSubledgerDrawerOpen] = useState<boolean>(false);
  const [selectedSubcategoryForSubledger, setSelectedSubcategoryForSubledger] = useState<string | null>(null);
  const [subledgerCapableSet, setSubledgerCapableSet] = useState<Set<string>>(new Set());

  const exportToCSV = (exportData: any[], filenamePrefix: string) => {
    if (!exportData || !exportData.length) return;
    const headers = Object.keys(exportData[0]).join(',');
    const rows = exportData.map((row) =>
      Object.values(row)
        .map((val) => `"${String(val ?? '').replace(/"/g, '""')}"`)
        .join(',')
    );
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers, ...rows].join('\n');
    const link = document.createElement('a');
    link.setAttribute('href', encodeURI(csvContent));
    link.setAttribute('download', `${filenamePrefix}_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  useEffect(() => {
    let isMounted = true;
    const fetchInitialMetadata = async () => {
      try {
        const [accs, meta] = await Promise.all([
          getAccounts(),
          subledgerApi.getSubledgerMetadata().catch(() => ({ subledger_capable_subcategories: [] })),
        ]);
        if (isMounted) {
          setAccounts(accs);
          if (meta?.subledger_capable_subcategories) {
            setSubledgerCapableSet(new Set(meta.subledger_capable_subcategories));
          }
        }
      } catch (err) {
        console.error('Failed to load initial ledger metadata:', err);
      }
    };
    fetchInitialMetadata();
    return () => { isMounted = false; };
  }, []);

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
      to_date: toDate,
    }, false);
  };

  const handleResetFilter = () => {
    if (data?.date_bounds) {
      const min = data.date_bounds.min_date;
      const max = data.date_bounds.max_date;
      setFromDate(min);
      setToDate(max);
      fetchSummary({
        bank_account_id: selectedAccountId,
        taxonomy_account_id: 99,
        from_date: min,
        to_date: max,
      }, false);
    }
  };

  const handleTaxonomyRowClick = useCallback((row: any) => {
    const subcategory = row?.subcategory || row?.name || row?.payload?.subcategory || row?.payload?.name;
    if (!subcategory) return;

    setSelectedSubcategoryForWorkbench(subcategory);
    setIsWorkbenchOpen(true);
  }, []);

  const handleWorkbenchSuccess = () => {
    fetchSummary({
      bank_account_id: selectedAccountId,
      taxonomy_account_id: 99,
      from_date: fromDate,
      to_date: toDate,
    }, false);
  };

  const kpiTableData = useMemo(() => {
    if (!data?.kpis || !data?.category_breakdown) return [];

    let totalRevenueDr = 0, totalRevenueCr = 0, totalRevenueCount = 0;
    let totalExpenseDr = 0, totalExpenseCr = 0, totalExpenseCount = 0;
    let totalAssetDr = 0, totalAssetCr = 0, totalAssetCount = 0;
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
      } else if (row.category === 'Asset') {
        totalAssetDr += dr;
        totalAssetCr += cr;
        totalAssetCount += txns;
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
        id: 'total_assets',
        kpi_name: 'Asset Deployments & Holdings',
        description: 'Investments, precious metals, and capital acquisitions',
        count: totalAssetCount,
        debit: totalAssetDr,
        credit: totalAssetCr,
        net_flow: (totalAssetDr - totalAssetCr).toFixed(2),
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

  return (
    <div className="p-4 w-full max-w-none space-y-4 bg-zinc-950 min-h-screen text-zinc-100 font-sans">
      <LedgerHeaderFilter
        accounts={accounts}
        selectedAccountId={selectedAccountId}
        onSelectAccount={setSelectedAccountId}
        fromDate={fromDate}
        toDate={toDate}
        onFromDateChange={setFromDate}
        onToDateChange={setToDate}
        onApplyFilter={handleApplyFilter}
        onResetFilter={handleResetFilter}
        loading={loading}
        dateBounds={data?.date_bounds}
      />

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
          <ExecutiveKpiSection
            kpiTableData={kpiTableData}
            selectedAccountId={selectedAccountId}
            onExportCsv={exportToCSV}
            onOpenSweepHub={() => setIsSweepHubOpen(true)}
          />

          <ExpenseIncomeDistributionChart
            categoryBreakdown={data.category_breakdown}
            activeChartTab={activeChartTab}
            onTabChange={setActiveChartTab}
            onRowClick={handleTaxonomyRowClick}
          />

          <TaxonomyMatrixSection
            categoryBreakdown={data.category_breakdown}
            selectedAccountId={selectedAccountId}
            subledgerCapableSet={subledgerCapableSet}
            onRowClick={handleTaxonomyRowClick}
            onOpenSubledgerDrawer={(subcategory: string) => {
              setSelectedSubcategoryForSubledger(subcategory);
              setIsSubledgerDrawerOpen(true);
            }}
            onExportCsv={exportToCSV}
          />
        </>
      )}

      <ClassificationWorkbenchModal
        isOpen={isWorkbenchOpen && !isSubledgerDrawerOpen}
        targetSubcategory={selectedSubcategoryForWorkbench}
        onClose={() => setIsWorkbenchOpen(false)}
        onSuccess={handleWorkbenchSuccess}
        accountId={selectedAccountId ? Number(selectedAccountId) : undefined}
        subledgerCapableSet={subledgerCapableSet}
        onOpenSubledgerDrawer={(subcategory: string, matchContext?: any) => {
          console.log('📬 [WORKBENCH -> DASHBOARD] Opening Operations Hub with context:', { subcategory, matchContext });
          setTaxonomyMatchContext(matchContext || null);
          setSelectedSubcategoryForSubledger(subcategory);
          setIsSubledgerDrawerOpen(true);
        }}
      />

      {/* Operations Hub: Renders the asset list with valuations & action buttons */}
      <SubledgerBreakdownDrawer
        isOpen={isSubledgerDrawerOpen}
        accountId={selectedAccountId}
        subcategory={selectedSubcategoryForSubledger}
        workbenchItems={taxonomyMatchContext?.stagedItems || []}
        onClose={() => {
          setIsSubledgerDrawerOpen(false);
          setTaxonomyMatchContext(null);
        }}
      />

      {/* 3. Candidate Matcher: Direct scan / attribution modal */}
      {isCandidateMatcherOpen && (
        <CandidateMatcherModal
          isOpen={isCandidateMatcherOpen}
          accountId={selectedAccountId}
          onClose={() => {
            setIsCandidateMatcherOpen(false);
            setTaxonomyMatchContext(null);
          }}
          taxonomyContext={taxonomyMatchContext}
          onSuccess={() => {
            handleWorkbenchSuccess();
            setIsCandidateMatcherOpen(false);
            setTaxonomyMatchContext(null);
          }}
        />
      )}

      {/* 4. Bulk Sweep Hub */}
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