import { useState, useEffect, useMemo, useCallback } from 'react';
import { TableEngine } from '../components/ui/data-table/TableEngine';
import { EVALUATOR_5TIER_COLUMNS } from '../components/ui/data-table/columns';
import { stagingQueueApi, accountApi } from '../api/api';
import { PipelineMetricsHeader } from '../components/Stage2/PipelineMetricsHeader';
import { NarrationCellRenderer } from '../components/Stage2/NarrationCellRenderer';
import { EvaluationTierCellRenderer } from '../components/Stage2/EvaluationTierCellRenderer';

export function StagingQueueEvaluator({ onSweepComplete }: { onSweepComplete?: () => void }) {
  const [accounts, setAccounts] = useState<any[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [workspaceRows, setWorkspaceRows] = useState<any[]>([]);
  const [matrixStats, setMatrixStats] = useState<any>({
    t1_system: { real: 0, suspense: 0 },
    t2_internal: { real: 0, suspense: 0 },
    t3_layout: { real: 0, suspense: 0 },
    t4_rulebook: { real: 0, suspense: 0 },
    t5_ai: { real: 0, suspense: 0 },
    total_processed: 0,
  });
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(25);

  useEffect(() => {
    accountApi.getAccounts().then((res: any) => setAccounts(res.results || res.data || res)).catch(() => {});
  }, []);

  const loadWorkspaceMatrix = useCallback(async (targetId: string) => {
    if (!targetId?.trim()) {
      setWorkspaceRows([]);
      return;
    }
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const data = await stagingQueueApi.evaluateWorkspace(targetId) as any;
      setWorkspaceRows(data.workspace_queue || []);
      if (data.matrix_summary_stats) setMatrixStats(data.matrix_summary_stats);
    } catch {
      setErrorMsg('Failed running verification pipeline over staging collection.');
      setWorkspaceRows([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedAccountId) loadWorkspaceMatrix(selectedAccountId);
  }, [selectedAccountId, loadWorkspaceMatrix]);

  const handleBulkClearance = async (rowsToApprove?: any[]) => {
    try {
      const targetIds = rowsToApprove ? rowsToApprove.map(r => r.wip_id) : [];
      await stagingQueueApi.bulkCommitLedger(selectedAccountId, targetIds);
      await loadWorkspaceMatrix(selectedAccountId);
      if (onSweepComplete) onSweepComplete();
    } catch {
      setErrorMsg('Atomic bulk write failed or rejected by schema validation models.');
    }
  };

  const processedRows = useMemo(() => {
    return workspaceRows.map(r => {
      const matrix = r.matrix_evaluation || {};
      const t4Hit = matrix.t4?.hit;
      const t5Hit = matrix.t5?.hit;

      const drVal = Number(r.debit || 0);
      const crVal = Number(r.credit || 0);

      return {
        ...r,
        // Standard String formatting
        raw_statement_date: (
          <span className="font-mono text-zinc-400 text-xs whitespace-nowrap">
            {r.raw_statement_date}
          </span>
        ),
        debit: (
          <span className="font-mono text-amber-400 text-xs font-semibold whitespace-nowrap">
            {drVal > 0 ? `₹${drVal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : "-"}
          </span>
        ),
        credit: (
          <span className="font-mono text-emerald-400 text-xs font-semibold whitespace-nowrap">
            {crVal > 0 ? `₹${crVal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : "-"}
          </span>
        ),
        assigned_header: (
          <span className="font-mono text-cyan-400 text-xs font-semibold whitespace-nowrap">
            {t4Hit ? matrix.t4?.category : (t5Hit ? matrix.t5?.category : (matrix.t1?.category || r.transaction_type || "Transfer"))}
          </span>
        ),

        // Custom Cell Renderers attached to keys matching ColumnConfig
        narration: <NarrationCellRenderer row={r} />,
        tiers_evaluation: <EvaluationTierCellRenderer row={r} />,
        actions: (
          <button 
            onClick={(e) => { e.stopPropagation(); handleBulkClearance([r]); }}
            className="text-xs bg-emerald-950 text-emerald-400 px-2.5 py-1 rounded border border-emerald-800 hover:bg-emerald-900 font-mono font-bold cursor-pointer"
          >
            Clear
          </button>
        )
      };
    });
  }, [workspaceRows, selectedAccountId]);

  const paginatedData = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return processedRows.slice(start, start + pageSize);
  }, [processedRows, currentPage, pageSize]);

  const totalPages = Math.ceil(processedRows.length / pageSize) || 1;

  return (
    <div className="space-y-6 p-6 bg-zinc-950 min-h-screen text-zinc-100 font-sans w-full overflow-x-hidden">
      <PipelineMetricsHeader 
        matrixStats={matrixStats} 
        totalNodes={matrixStats.total_processed || 0} 
        isAudited={matrixStats.total_processed > 0} 
      />

      <div className="flex justify-between items-center bg-zinc-900 border border-zinc-800 p-4 rounded-xl">
        <div>
          <h1 className="text-xs font-mono uppercase tracking-wider text-zinc-200 font-bold">Account Context</h1>
          <p className="text-xs text-zinc-400 font-mono">Select target account to run evaluation gates.</p>
        </div>
        <select
          value={selectedAccountId}
          onChange={(e) => { setSelectedAccountId(e.target.value); setCurrentPage(1); }}
          className="bg-zinc-950 border border-zinc-800 p-2 rounded-lg text-xs font-mono font-bold text-zinc-100 cursor-pointer"
        >
          <option value="">-- Select Active Ledger Account --</option>
          {accounts.map((acc) => (
            <option key={acc.id} value={acc.id}>{acc.name} ({acc.account_number?.slice(-4)})</option>
          ))}
        </select>
      </div>

      {errorMsg && (
        <div className="bg-red-950/30 border border-red-900 text-red-400 p-3 rounded text-xs font-mono">
          [PIPELINE EXCEPTION] // {errorMsg}
        </div>
      )}

      {isLoading ? (
        <div className="p-12 text-center text-xs font-mono text-zinc-500 bg-zinc-950 border border-zinc-900 rounded-xl">
          EVALUATING STAGING NODES...
        </div>
      ) : (
        <div className="bg-zinc-900/20 border border-zinc-800 rounded-lg p-4 space-y-4">
          <div className="flex justify-between items-center border-b border-zinc-800 pb-3">
            <h2 className="text-xs uppercase font-mono text-zinc-400 font-bold tracking-wider">
              Auto Clearance Validation Desk
            </h2>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5 text-zinc-400 font-mono text-xs">
                <span>Rows:</span>
                <select
                  value={pageSize}
                  onChange={(e) => { setPageSize(Number(e.target.value)); setCurrentPage(1); }}
                  className="bg-zinc-950 border border-zinc-800 text-zinc-200 px-2 py-1 rounded"
                >
                  <option value={10}>10</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                </select>
              </div>

              {processedRows.length > 0 && (
                <button 
                  onClick={() => handleBulkClearance(workspaceRows)} 
                  className="bg-emerald-600 hover:bg-emerald-700 text-zinc-950 font-mono font-bold text-xs px-3 py-1.5 rounded uppercase tracking-wider cursor-pointer"
                >
                  ⚡ Execute Bulk Sync Release ({processedRows.length} Rows)
                </button>
              )}
            </div>
          </div>

          <div className="w-full overflow-x-auto">
            <TableEngine columns={EVALUATOR_5TIER_COLUMNS} data={paginatedData} />
          </div>

          <div className="flex justify-between items-center text-xs font-mono text-zinc-400 pt-2 border-t border-zinc-800/50">
            <div>
              Showing <b className="text-zinc-200">{(currentPage - 1) * pageSize + 1}</b> to <b className="text-zinc-200">{Math.min(currentPage * pageSize, processedRows.length)}</b> of <b className="text-emerald-400">{processedRows.length}</b> nodes
            </div>
            <div className="flex items-center gap-2">
              <button disabled={currentPage === 1} onClick={() => setCurrentPage(p => p - 1)} className="px-2 py-1 border rounded disabled:opacity-40">‹</button>
              <span>{currentPage} / {totalPages}</span>
              <button disabled={currentPage === totalPages} onClick={() => setCurrentPage(p => p + 1)} className="px-2 py-1 border rounded disabled:opacity-40">›</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default StagingQueueEvaluator;