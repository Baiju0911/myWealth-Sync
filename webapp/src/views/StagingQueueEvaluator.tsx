import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { TableEngine } from '../components/ui/data-table/TableEngine';
import { BULK_APPROVAL_COLUMNS, UNCATEGORIZED_VAULT_COLUMNS } from '../components/ui/data-table/columns';
import { stagingQueueApi, ledgerMasterApi, accountApi } from '../api';
import type { WorkspaceNode as BaseWorkspaceNode, SplitAllocationPayload } from '../api';

type WorkspaceTab = 'bulk-high' | 'uncategorized-zero';

interface SplitStateRow {
  categoryId: string;
  subcat: string;
  amount: number;
}

interface AccountOption {
  id: string | number;
  name: string;
  account_number: string;
}

interface TierMetric {
  real: number;
  suspense: number;
}

interface MatrixStats {
  t1_system: TierMetric;
  t2_internal: TierMetric; 
  t3_layout: TierMetric;
  t4_rulebook: TierMetric;  
  total_processed: number;
}

interface WorkspaceNode extends BaseWorkspaceNode {
  confidence: 'HIGH' | 'MEDIUM' | 'LOW' | 'ZERO';
  pipeline_trace: {
    stop1_known_default: any;
    stop2_self_transfer: any;
    stop3_balance_sheet: any;
    stop4_accounting_rule: any;
  };
  matrix_evaluation?: {
    system_certainty_score: number;
    t1: { category: string; subcategory: string; weight: number };
    t2: { category: string; subcategory: string; weight: number };
    t3: { category: string; subcategory: string; weight: number };
    t4: { category: string; subcategory: string; hit: boolean };
  };
}

export default function StagingQueueEvaluator() {
  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('bulk-high');
  const [workspaceRows, setWorkspaceRows] = useState<WorkspaceNode[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [selectedRowToSplit, setSelectedRowToSplit] = useState<WorkspaceNode | null>(null);
  const [splitLines, setSplitLines] = useState<SplitStateRow[]>([]);
  const [availableCategories, setAvailableCategories] = useState<any[]>([]);

  const [matrixStats, setMatrixStats] = useState<MatrixStats>({
    t1_system: { real: 0, suspense: 0 },
    t2_internal: { real: 0, suspense: 0 }, 
    t3_layout: { real: 0, suspense: 0 },
    t4_rulebook: { real: 0, suspense: 0 },
    total_processed: 0
  });

  useEffect(() => {
    accountApi.getAccounts().then((res: any) => {
      setAccounts(res.results || res.data || res);
    }).catch(() => setErrorMsg('Failed loading registered accounts metadata vector.'));

    ledgerMasterApi.getMasterCategories().then((res: any) => {
      setAvailableCategories(res.results || res.data || res);
    });
  }, []);

  const auditState = useMemo(() => {
    const totalRecords = matrixStats?.total_processed || 0;
    const t1Total = (matrixStats?.t1_system?.real || 0) + (matrixStats?.t1_system?.suspense || 0);
    const t2Total = (matrixStats?.t2_internal?.real || 0) + (matrixStats?.t2_internal?.suspense || 0);
    const t3Total = (matrixStats?.t3_layout?.real || 0) + (matrixStats?.t3_layout?.suspense || 0);
    const t4Total = (matrixStats?.t4_rulebook?.real || 0) + (matrixStats?.t4_rulebook?.suspense || 0);

    const isMatrixAudited = totalRecords > 0 && 
      t1Total === totalRecords && 
      t2Total === totalRecords && 
      t3Total === totalRecords && 
      t4Total === totalRecords;

    return { totalRecords, t1Total, t2Total, t3Total, t4Total, isMatrixAudited };
  }, [matrixStats]);

  const loadWorkspaceMatrix = useCallback(async (targetId: string) => {
    if (!targetId || !targetId.trim()) {
      setWorkspaceRows([]); 
      return;
    }
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const data = await stagingQueueApi.evaluateWorkspace(targetId) as any;
      setWorkspaceRows(data.workspace_queue || []);
      if (data.matrix_summary_stats) {
        setMatrixStats(data.matrix_summary_stats);
      }
    } catch (err: any) {
      setErrorMsg('Failed running verification pipeline over staging collection.');
      setWorkspaceRows([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedAccountId) {
      loadWorkspaceMatrix(selectedAccountId);
    }
  }, [selectedAccountId, loadWorkspaceMatrix]);

  const handleBulkClearance = async (rowsToApprove: any[]) => {
    try {
      await stagingQueueApi.bulkCommitLedger(selectedAccountId, rowsToApprove.map(r => r.wip_id));
      await loadWorkspaceMatrix(selectedAccountId);
    } catch (err) {
      setErrorMsg('Atomic bulk write failed or rejected by schema validation models.');
    }
  };

  const handleCommitSplit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedRowToSplit) return;
    try {
      const payload: SplitAllocationPayload[] = splitLines.map(line => ({
        categoryId: line.categoryId,
        subcat: line.subcat,
        amount: line.amount
      }));
      await stagingQueueApi.commitSplitAllocation(selectedRowToSplit.wip_id, payload);
      setSelectedRowToSplit(null);
      await loadWorkspaceMatrix(selectedAccountId);
    } catch (err) {
      setErrorMsg('Failed writing split items allocation.');
    }
  };

  const processRowMapping = useCallback((r: any) => {
    const matrix = (r.matrix_evaluation || {}) as any;
    const t4Hit = matrix.t4?.hit || false;
    
    let statusText = "ACCOUNTING RULE FALLBACK";
    let statusColor = "text-cyan-500 font-bold";
    let badgeColor = "border-cyan-950 bg-cyan-950/20";
    let winnerToken = `Institutional Gate -> ${matrix.t4?.category || 'Expenses'} Suspense`;
    let confidenceLevel = 90;
    
    if (t4Hit === true) {
      statusText = "MASTER RULEBOOK HIT";
      statusColor = "text-yellow-500 font-bold";
      badgeColor = "border-yellow-950 bg-yellow-950/20";
      winnerToken = `Supervisor Verified (${matrix.t4?.subcategory})`;
      confidenceLevel = 98;
    }

    return {
      ...r,
      category_item: t4Hit ? matrix.t4?.category : (matrix.t1?.category || "None"),
      subcategory_item: t4Hit ? matrix.t4?.subcategory : (matrix.t1?.subcategory || "None"),
      rule_code: winnerToken,
      T1_item: `${matrix.t1?.category || 'None'}→${matrix.t1?.subcategory || 'None'}`,
      T2_item: `${matrix.t2?.category || 'None'}→${matrix.t2?.subcategory || 'None'}`,
      T3_item: `${matrix.t3?.category || 'None'}→${matrix.t3?.subcategory || 'None'}`,
      T4_item: `${matrix.t4?.category || 'None'}→${matrix.t4?.subcategory || 'None'}`,
      narration: (
        <div className="space-y-1.5 py-1 font-mono">
          <div className="text-zinc-100 font-sans font-medium text-xs break-words">{r.narration}</div>
          <div className={`text-[10px] text-zinc-400 p-1.5 rounded-lg border w-full grid grid-cols-1 sm:grid-cols-3 gap-2 items-center tracking-tight ${badgeColor}`}>
            <div>
              <span className="text-zinc-500 uppercase font-bold text-[9px] mr-1">Winner:</span>
              <b className={statusColor}>{statusText}</b>
            </div>
            <div className="truncate">
              <span className="text-zinc-500 uppercase font-bold text-[9px] mr-1">Token:</span>
              <b className="text-zinc-300">"{winnerToken}"</b>
            </div>
            <div className="sm:text-right">
              <span className="text-zinc-500 uppercase font-bold text-[9px] mr-1">Conf:</span>
              <b className="text-zinc-300">{confidenceLevel}%</b>
            </div>
          </div>
        </div>
      ),
      actions: (
        <button 
          onClick={(e) => { e.stopPropagation(); handleBulkClearance([r]); }}
          className="text-xs bg-emerald-950 text-emerald-400 px-2.5 py-1 rounded border border-emerald-800 hover:bg-emerald-900 font-mono font-bold cursor-pointer"
        >
          Clear
        </button>
      )
    };
  }, [selectedAccountId]);

  const distributedData = useMemo(() => {
    const high = workspaceRows
      .filter(r => ((r.matrix_evaluation as any)?.system_certainty_score || 0) >= 0)
      .map(processRowMapping);

    const low = workspaceRows
      .filter(() => false)
      .map(r => {
        const mapped = processRowMapping(r);
        return {
          ...mapped,
          actions: (
            <button 
              onClick={(e) => {
                e.stopPropagation();
                setSelectedRowToSplit(r); 
                setSplitLines([{ categoryId: '', subcat: '', amount: r.debit || r.credit }]); 
              }} 
              className="text-xs bg-cyan-950 text-cyan-400 px-2.5 py-1 rounded border border-cyan-800 hover:bg-cyan-900 font-mono font-bold cursor-pointer"
            >
              Split / Assign
            </button>
          )
        };
      });

    return { high, low };
  }, [workspaceRows, processRowMapping]);

  const originalTxnValue = selectedRowToSplit ? (selectedRowToSplit.debit || selectedRowToSplit.credit) : 0;
  const currentSplitSum = splitLines.reduce((acc, curr) => acc + curr.amount, 0);
  const mathematicallyBalanced = parseFloat(originalTxnValue.toFixed(2)) === parseFloat(currentSplitSum.toFixed(2));

  return (
    <div className="space-y-6 p-6 bg-zinc-950 min-h-screen text-zinc-100 font-sans w-full max-w-full">
      
      {/* 🏛️ COMBINED PIPELINE AUDIT SHIELD BAR */}
      <div 
        style={{ display: 'flex', flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}
        className={`p-4 rounded-xl border gap-6 transition-all duration-300 ${
          auditState.isMatrixAudited ? "border-emerald-500/30 bg-emerald-950/10" : "border-rose-500/30 bg-rose-950/10"
        }`}
      >
        <div style={{ flexShrink: 0 }}>
          <div className="text-xs font-mono uppercase tracking-wider text-zinc-400">Pipeline Balance Status</div>
          <h2 className="text-base font-bold tracking-tight mt-0.5 whitespace-nowrap">
            Staged For Bulk High Clearance: <span className="text-emerald-400 font-mono">{auditState.totalRecords} Nodes Passed</span>
          </h2>
          
        </div>

        {/* 📊 STRICT INLINE HORIZONTAL TICKER STRIP */}
        <div style={{ display: 'flex', flexDirection: 'row', gap: '12px', flexGrow: 1, justifyContent: 'flex-end', alignItems: 'stretch' }}>
          
          {/* T1 */}
          <div style={{ position: 'relative', padding: '8px 12px 8px 16px', backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: '8px', minWidth: '180px' }}>
            <div style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: '4px', backgroundColor: 'rgba(59, 130, 246, 0.5)' }} />
            <div className="text-zinc-500 text-[9px] font-bold font-mono uppercase tracking-wider">T1 System Rules</div>
            {/* <div className="text-zinc-200 font-bold font-mono text-[13px] mt-0.5">{auditState.t1Total} Rows</div> */}
            <div className="text-[10px] font-mono text-zinc-400 mt-0.5">
              <span className="text-emerald-500">M:{matrixStats.t1_system.real}</span> · <span className="text-amber-500">S:{matrixStats.t1_system.suspense}</span>
            </div>
          </div>

          {/* T2 */}
          <div style={{ position: 'relative', padding: '8px 12px 8px 16px', backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: '8px', minWidth: '180px' }}>
            <div style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: '4px', backgroundColor: 'rgba(168, 85, 247, 0.5)' }} />
            <div className="text-zinc-500 text-[9px] font-bold font-mono uppercase tracking-wider">T2 Transfer Tunnels</div>
            {/* <div className="text-zinc-200 font-bold font-mono text-[13px] mt-0.5">{auditState.t2Total} Rows</div> */}
            <div className="text-[10px] font-mono text-zinc-400 mt-0.5">
              <span className="text-emerald-500">I:{matrixStats.t2_internal.real}</span> · <span className="text-zinc-500">N:{matrixStats.t2_internal.suspense}</span>
            </div>
          </div>

          {/* T3 */}
          <div style={{ position: 'relative', padding: '8px 12px 8px 16px', backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: '8px', minWidth: '180px' }}>
            <div style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: '4px', backgroundColor: 'rgba(6, 182, 212, 0.5)' }} />
            <div className="text-zinc-500 text-[9px] font-bold font-mono uppercase tracking-wider">T3 Ledger Mappings</div>
            {/* <div className="text-zinc-200 font-bold font-mono text-[13px] mt-0.5">{auditState.t3Total} Rows</div> */}
            <div className="text-[10px] font-mono text-zinc-400 mt-0.5">
              <span className="text-emerald-500">M:{matrixStats.t3_layout.real}</span> · <span className="text-amber-500">S:{matrixStats.t3_layout.suspense}</span>
            </div>
          </div>

          {/* T4 */}
          <div style={{ position: 'relative', padding: '8px 12px 8px 16px', backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: '8px', minWidth: '180px' }}>
            <div style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: '4px', backgroundColor: 'rgba(234, 179, 8, 0.5)' }} />
            <div className="text-yellow-500/80 text-[9px] font-bold font-mono uppercase tracking-wider">T4 Master Rulebook</div>
            {/* <div className="text-zinc-200 font-bold font-mono text-[13px] mt-0.5">{auditState.t4Total} Rows</div> */}
            <div className="text-[10px] font-mono text-zinc-400 mt-0.5">
              <span className="text-yellow-500">A:{matrixStats.t4_rulebook.real}</span> · <span className="text-cyan-400">F:{matrixStats.t4_rulebook.suspense}</span>
            </div>
          </div>

        </div>
      </div>

      {/* DROPDOWN CONTEXT BAR */}
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
                {acc.name} ({acc.account_number.slice(-4)})
              </option>
            ))}
          </select>
        </div>
      </div>

      {errorMsg && (
        <div className="bg-red-950/30 border border-red-900 text-red-400 p-3 rounded text-xs font-mono flex justify-between">
          <span>[PIPELINE EXCEPTION] // {errorMsg}</span>
          <button onClick={() => setErrorMsg(null)} className="text-zinc-500 hover:text-zinc-300">clear</button>
        </div>
      )}

      {isLoading ? (
        <div className="p-12 text-center text-xs font-mono text-zinc-500 bg-zinc-950 border border-zinc-900 rounded-xl">
          RUNNING RECONCILIATION ENGINE CRITERIA OVER TARGET NODE MATRIX...
        </div>
      ) : (
        <>
       <div 
              onClick={() => setActiveTab('bulk-high')} 
              className={`p-4 rounded-xl border cursor-pointer transition-all duration-200 ${
                activeTab === 'bulk-high' 
                  ? 'bg-zinc-900 border-emerald-500/80 shadow-[0_0_15px_rgba(16,185,129,0.03)]' 
                  : 'bg-zinc-900/40 border-zinc-800/80 opacity-50 hover:opacity-80'
              }`}
            >
              <div className="flex items-center gap-2 font-mono whitespace-nowrap">
                  {/* Nodes Count Display */}
                  <span className="text-sm font-black text-emerald-400 font-sans tracking-tight">
                    {distributedData.high.length} Nodes Mapped →
                  </span>
                  
                
                  
                  {/* High-Contrast Tiers Equation Matrix */}
                  <span className="text-[14px] text-zinc-500 font-bold tracking-wide">
                     T1: <b className="text-zinc-100 font-extrabold">{auditState.t1Total}</b> → T2: <b className="text-zinc-100 font-extrabold">{auditState.t2Total}</b> → T3: <b className="text-zinc-100 font-extrabold">{auditState.t3Total}</b> → T4: <b className="text-zinc-100 font-extrabold">{auditState.t4Total}</b> 
                  </span>
                </div>
              </div>

          <div className="bg-zinc-900/20 border border-zinc-800 rounded-lg p-4 space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-xs uppercase font-mono text-zinc-400 font-bold tracking-wider">
                {activeTab === 'bulk-high' ? 'Auto Clearance Validation Desk' : 'Uncategorized Operations Ledger'}
              </h2>
              {activeTab === 'bulk-high' && distributedData.high.length > 0 && (
                <button 
                  onClick={() => handleBulkClearance(workspaceRows)} 
                  className="bg-emerald-600 hover:bg-emerald-700 text-zinc-950 font-mono font-bold text-xs px-3 py-1.5 rounded uppercase tracking-wider cursor-pointer"
                >
                  ⚡ Execute Bulk Sync Release ({distributedData.high.length} Rows)
                </button>
              )}
            </div>

            <TableEngine 
              columns={activeTab === 'bulk-high' ? BULK_APPROVAL_COLUMNS : UNCATEGORIZED_VAULT_COLUMNS} 
              data={activeTab === 'bulk-high' ? distributedData.high : distributedData.low} 
            />
          </div>
        </>
      )}

      {/* Split Modal Render Layer */}
      {selectedRowToSplit && (
        <div className="fixed inset-0 bg-zinc-950/80 flex items-center justify-center p-4 backdrop-blur-xs z-50">
          <form onSubmit={handleCommitSplit} className="bg-zinc-900 border border-zinc-800 p-6 rounded-xl w-full max-w-2xl space-y-4 font-mono text-xs">
            <div className="flex justify-between items-center border-b border-zinc-800 pb-3">
              <span className="text-zinc-400 uppercase font-bold">Split Allocation Interface</span>
              <button type="button" onClick={() => setSelectedRowToSplit(null)} className="text-zinc-500 hover:text-zinc-300">Close</button>
            </div>
            
            <div className="bg-zinc-950 p-3 rounded text-[11px] text-zinc-400 border border-zinc-800/60">
              <span className="text-zinc-500 font-bold">TARGET:</span> {selectedRowToSplit.narration}<br />
              <span className="text-zinc-500 font-bold">VALUE DEPLOYED:</span> <span className="text-zinc-200 font-bold">₹{originalTxnValue}</span>
            </div>

            <div className="space-y-2 max-h-[200px] overflow-y-auto pr-2">
              {splitLines.map((line: SplitStateRow, index: number) => (
                <div key={index} className="grid grid-cols-3 gap-2 items-center">
                  <select 
                    value={line.categoryId} 
                    onChange={e => { const updated = [...splitLines]; updated[index].categoryId = e.target.value; setSplitLines(updated); }}
                    className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200" required
                  >
                    <option value="">Select Balance Sheet Group</option>
                    {availableCategories.map((c: any) => (
                      <option key={c.id} value={c.id}>{c.act_category} → {c.categories_items}</option>
                    ))}
                  </select>
                  <input 
                    type="text" placeholder="Subcategory target label" value={line.subcat} 
                    onChange={e => { const updated = [...splitLines]; updated[index].subcat = e.target.value; setSplitLines(updated); }}
                    className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200" required 
                  />
                  <input 
                    type="number" step="0.01" placeholder="Amount" value={line.amount || ''} 
                    onChange={e => { const updated = [...splitLines]; updated[index].amount = parseFloat(e.target.value) || 0; setSplitLines(updated); }}
                    className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200 text-right" required 
                  />
                </div>
              ))}
            </div>

            <div className="flex justify-between items-center border-t border-zinc-800 pt-4 font-bold">
              <button 
                type="button" 
                onClick={() => setSplitLines([...splitLines, { categoryId: '', subcat: '', amount: 0 }])} 
                className="text-cyan-400 hover:text-cyan-300"
              >
                + Add Allocated Segment Row
              </button>
              
              <div className="text-right space-y-1">
                <div className={`text-[11px] ${mathematicallyBalanced ? 'text-emerald-400' : 'text-amber-500'}`}>
                  Allocated: ₹{currentSplitSum.toFixed(2)} / ₹{parseFloat(originalTxnValue.toString()).toFixed(2)}
                </div>
                <button 
                  type="submit" 
                  disabled={!mathematicallyBalanced}
                  className={`px-4 py-2 rounded text-zinc-950 uppercase font-bold transition-all
                    ${mathematicallyBalanced ? 'bg-emerald-500 hover:bg-emerald-600 cursor-pointer' : 'bg-zinc-800 text-zinc-500 cursor-not-allowed'}
                  `}
                >
                  Commit Entry Split Matrix
                </button>
              </div>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}