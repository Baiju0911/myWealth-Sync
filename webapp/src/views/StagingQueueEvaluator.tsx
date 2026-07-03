// src/views/StagingQueueEvaluator.tsx
import React, { useState, useEffect } from 'react';
import { TableEngine } from '../components/ui/data-table/TableEngine';
import { BULK_APPROVAL_COLUMNS, UNCATEGORIZED_VAULT_COLUMNS } from '../components/ui/data-table/columns';

// 🎯 FIX 1: Enforce explicit 'import type' syntax for verbatimModuleSyntax compliance
import { stagingQueueApi, ledgerMasterApi } from '../api';
import type { WorkspaceNode, SplitAllocationPayload } from '../api';

type WorkspaceTab = 'bulk-high' | 'uncategorized-zero';

interface SplitStateRow {
  categoryId: string;
  subcat: string;
  amount: number;
}

export default function StagingQueueEvaluator({ accountId }: { accountId: string }) {
  // 🎯 FIX 2: Restored all missing scoped state hooks to eliminate 'Cannot find name' blocks
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('bulk-high');
  const [workspaceRows, setWorkspaceRows] = useState<WorkspaceNode[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [selectedRowToSplit, setSelectedRowToSplit] = useState<WorkspaceNode | null>(null);
  const [splitLines, setSplitLines] = useState<SplitStateRow[]>([
    { categoryId: '', subcat: '', amount: 0 }
  ]);
  const [availableCategories, setAvailableCategories] = useState<any[]>([]);

  const loadWorkspaceMatrix = async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const data = await stagingQueueApi.evaluateWorkspace(accountId);
      setWorkspaceRows(data.workspace_queue || []);
    } catch (err: any) {
      setErrorMsg('Failed running verification pipeline over staging collection.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadWorkspaceMatrix();
    ledgerMasterApi.getMasterCategories().then((res: any) => {
      setAvailableCategories(res.results || res.data || res);
    });
  }, [accountId]);

  // 🎯 FIX 3: Explicitly calculated baselines ensuring no unexpected zero divisions
  const originalTxnValue = selectedRowToSplit ? (selectedRowToSplit.debit || selectedRowToSplit.credit) : 0;
  
  // 🎯 FIX 4: Strong type declarations appended to (.reduce) parameters to clear implicit 'any' flags
  const currentSplitSum = splitLines.reduce((acc: number, curr: SplitStateRow) => acc + curr.amount, 0);
  const mathematicallyBalanced = parseFloat(originalTxnValue.toFixed(2)) === parseFloat(currentSplitSum.toFixed(2));

  const handleBulkClearance = async (rowsToApprove: WorkspaceNode[]) => {
    try {
      await stagingQueueApi.bulkCommitLedger(accountId, rowsToApprove.map(r => r.wip_id));
      await loadWorkspaceMatrix();
    } catch (err) {
      setErrorMsg('Atomic bulk write failed or rejected by schema validation models.');
    }
  };

  const handleCommitSplit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!mathematicallyBalanced || !selectedRowToSplit) return;

    try {
      const payload: SplitAllocationPayload[] = splitLines.map(line => ({
        categoryId: line.categoryId,
        subcat: line.subcat,
        amount: line.amount
      }));
      await stagingQueueApi.commitSplitAllocation(selectedRowToSplit.wip_id, payload);
      setSelectedRowToSplit(null);
      setSplitLines([{ categoryId: '', subcat: '', amount: 0 }]);
      await loadWorkspaceMatrix();
    } catch (err) {
      setErrorMsg('Failed writing split items allocation.');
    }
  };

  const highConfidenceRows = workspaceRows
    .filter(r => r.confidence === 'HIGH')
    .map(r => ({
      ...r,
      category_item: r.analysis.category_item,
      rule_code: r.analysis.rule_code,
      actions: (
        <button 
          onClick={() => handleBulkClearance([r])} 
          className="text-xs bg-emerald-950 text-emerald-400 px-2 py-1 rounded border border-emerald-800 hover:bg-emerald-900"
        >
          Clear
        </button>
      )
    }));

  const zeroConfidenceRows = workspaceRows
    .filter(r => r.confidence === 'ZERO')
    .map(r => ({
      ...r,
      errors: r.errors.join(' | '),
      actions: (
        <button 
          onClick={() => { 
            setSelectedRowToSplit(r); 
            setSplitLines([{ categoryId: '', subcat: '', amount: r.debit || r.credit }]); 
          }} 
          className="text-xs bg-cyan-950 text-cyan-400 px-2 py-1 rounded border border-cyan-800 hover:bg-cyan-900"
        >
          Split / Assign
        </button>
      )
    }));

  if (isLoading) return <div className="p-12 text-center text-xs font-mono text-zinc-500 bg-zinc-950">RUNNING RECONCILIATION ENGINE CRITERIA...</div>;

  return (
    <div className="bg-zinc-950 text-zinc-100 p-6 space-y-6 min-h-screen font-sans">
      {errorMsg && (
        <div className="bg-red-950/30 border border-red-900 text-red-400 p-3 rounded text-xs font-mono flex justify-between">
          <span>[PIPELINE EXCEPTION] // {errorMsg}</span>
          <button onClick={() => setErrorMsg(null)} className="text-zinc-500 hover:text-zinc-300">clear</button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 font-mono text-xs">
        <div 
          onClick={() => setActiveTab('bulk-high')} 
          className={`p-4 rounded-lg border cursor-pointer transition-all ${activeTab === 'bulk-high' ? 'bg-zinc-900 border-emerald-500' : 'bg-zinc-900/40 border-zinc-800 opacity-60'}`}
        >
          <div className="text-zinc-500 uppercase">Staged For Bulk High Clearance</div>
          <div className="text-xl font-bold text-emerald-400 mt-1">{highConfidenceRows.length} Nodes Passed</div>
        </div>
        <div 
          onClick={() => setActiveTab('uncategorized-zero')} 
          className={`p-4 rounded-lg border cursor-pointer transition-all ${activeTab === 'uncategorized-zero' ? 'bg-zinc-900 border-red-500' : 'bg-zinc-900/40 border-zinc-800 opacity-60'}`}
        >
          <div className="text-zinc-500 uppercase">Uncategorized Vault (Zero Confidence)</div>
          <div className="text-xl font-bold text-red-400 mt-1">{zeroConfidenceRows.length} Nodes Failed</div>
        </div>
      </div>

      <div className="bg-zinc-900/20 border border-zinc-800 rounded-lg p-4 space-y-4">
        <div className="flex justify-between items-center">
          <h2 className="text-xs uppercase font-mono text-zinc-400 font-bold tracking-wider">
            {activeTab === 'bulk-high' ? 'Auto Clearance Validation Desk' : 'Uncategorized Operations Ledger'}
          </h2>
          {activeTab === 'bulk-high' && highConfidenceRows.length > 0 && (
            <button 
              onClick={() => handleBulkClearance(workspaceRows.filter(r => r.confidence === 'HIGH'))} 
              className="bg-emerald-600 hover:bg-emerald-700 text-zinc-950 font-mono font-bold text-xs px-3 py-1.5 rounded uppercase tracking-wider"
            >
              ⚡ Execute Bulk Sync Release ({highConfidenceRows.length} Rows)
            </button>
          )}
        </div>

        <TableEngine 
          columns={activeTab === 'bulk-high' ? BULK_APPROVAL_COLUMNS : UNCATEGORIZED_VAULT_COLUMNS} 
          data={activeTab === 'bulk-high' ? highConfidenceRows : zeroConfidenceRows} 
        />
      </div>

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
              {/* 🎯 FIX 5: Explicit type signature tags attached directly inside maps parameters */}
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