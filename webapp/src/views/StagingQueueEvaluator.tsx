import React, { useState, useEffect } from 'react';
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

interface WorkspaceNode extends BaseWorkspaceNode {
  confidence: 'HIGH' | 'MEDIUM' | 'LOW' | 'ZERO';
  pipeline_trace: {
    stop1_known_default: any;
    stop2_self_transfer: any;
    stop3_balance_sheet: any;
    stop4_accounting_rule: any;
  };
}

export default function StagingQueueEvaluator() {
  // 🎛️ Account Selector Workspace States
  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');

  const [activeTab, setActiveTab] = useState<WorkspaceTab>('bulk-high');
  const [workspaceRows, setWorkspaceRows] = useState<WorkspaceNode[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [selectedRowToSplit, setSelectedRowToSplit] = useState<WorkspaceNode | null>(null);
  const [splitLines, setSplitLines] = useState<SplitStateRow[]>([
    { categoryId: '', subcat: '', amount: 0 }
  ]);
  const [availableCategories, setAvailableCategories] = useState<any[]>([]);

  // 📥 Fetch Accounts Dropdown Collection First
  useEffect(() => {
    accountApi.getAccounts().then((res: any) => {
      const accountData = res.results || res.data || res;
      setAccounts(accountData);
    }).catch(() => setErrorMsg('Failed loading registered accounts metadata vector.'));

    ledgerMasterApi.getMasterCategories().then((res: any) => {
      setAvailableCategories(res.results || res.data || res);
    });
  }, []);

  // 🔄 Trigger Evaluator Sweeper Payload when selectedAccountId changes
  const loadWorkspaceMatrix = async (targetId: string) => {
    if (!targetId || !targetId.trim()) {
      setWorkspaceRows([]); 
      return;
    }
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const data = await stagingQueueApi.evaluateWorkspace(targetId);
      setWorkspaceRows(data.workspace_queue || []);
    } catch (err: any) {
      setErrorMsg('Failed running verification pipeline over staging collection.');
      setWorkspaceRows([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (selectedAccountId) {
      setErrorMsg("");
      loadWorkspaceMatrix(selectedAccountId);
    }
  }, [selectedAccountId]);

  // Math Interceptor Baselines
  const originalTxnValue = selectedRowToSplit ? (selectedRowToSplit.debit || selectedRowToSplit.credit) : 0;
  const currentSplitSum = splitLines.reduce((acc: number, curr: SplitStateRow) => acc + curr.amount, 0);
  const mathematicallyBalanced = parseFloat(originalTxnValue.toFixed(2)) === parseFloat(currentSplitSum.toFixed(2));

  const handleBulkClearance = async (rowsToApprove: WorkspaceNode[]) => {
    try {
      await stagingQueueApi.bulkCommitLedger(selectedAccountId, rowsToApprove.map(r => r.wip_id));
      await loadWorkspaceMatrix(selectedAccountId);
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
      await loadWorkspaceMatrix(selectedAccountId);
    } catch (err) {
      setErrorMsg('Failed writing split items allocation.');
    }
  };

// 🎯 INLINE TIER 1 PROXY MAPPING: Displays pure Tier 1 keyword metric lines cleanly


  const processRowMapping = (r: any) => {
  const t1 = r.tier1_metrics || {};
  const tier = t1.active_tier_level || 0;
  
  let statusText = "FALLBACK MISS";
  let statusColor = "text-amber-500";
  let badgeColor = "border-zinc-900/80 bg-zinc-950/60";
  
  // Choose which target path to show on the final table column based on the tier rank
  const displayCategory = tier === 2 ? t1.t2_category : t1.t1_category;
  const displaySubcategory = tier === 2 ? t1.t2_subcategory : t1.t1_subcategory;

  if (tier === 1) {
    statusText = "TIER 1: KEYWORD HIT";
    statusColor = "text-emerald-500";
    badgeColor = "border-emerald-950 bg-emerald-950/20";
  } else if (tier === 2) {
    statusText = "TIER 2: SELF TRANSFER HIT";
    statusColor = "text-cyan-400 font-bold";
    badgeColor = "border-cyan-950 bg-cyan-950/30";
  }

  return {
    ...r,
    category_item: displayCategory,
    rule_code: tier > 0 ? `T${tier} KW: ${t1.matched_keyword_token}` : 'Fallback Default',
    
    // 🎯 FIX: Explicitly map table grid keys with clean string fallbacks to avoid undefined leaks
    T1_item: t1.t1_category ? `${t1.t1_category}→${t1.t1_subcategory}` : "None→None",
    T2_item: t1.t2_category && t1.t2_category !== "None" ? `${t1.t2_category}→${t1.t2_subcategory}` : "None→None",
    T3_item: t1.t3_category ? `${t1.t3_category}→${t1.t3_subcategory}` : "None→None",
    T4_item: t1.t4_category ? `${t1.t4_category}→${t1.t4_subcategory}` : "None→None",
    
    narration: (
      <div className="space-y-1.5 py-1 font-mono">
        <div className="text-zinc-100 font-sans font-medium text-xs break-words">{r.narration}</div>
        
        <div className={`text-[10px] text-zinc-400 p-1.5 rounded-lg border w-full grid grid-cols-2 md:grid-cols-6 gap-2 items-center tracking-tight ${badgeColor}`}>
          {/* Tier Status */}
          <div className="col-span-1">
            <span className="text-zinc-500 uppercase font-bold text-[9px] mr-1">Pipeline:</span>
            <b className={statusColor}>{statusText}</b>
          </div>
          
          {/* Keyword Token */}
          <div className="truncate col-span-1">
            <span className="text-zinc-500 uppercase font-bold text-[9px] mr-1">Token:</span>
            <b className="text-zinc-300">"{t1.matched_keyword_token || 'None'}"</b>
          </div>

          {/* Weights & Confidence */}
          <div className="col-span-1">
            <span className="text-zinc-500 uppercase font-bold text-[9px] mr-1">W/C:</span>
            <b className="text-zinc-300">{t1.execution_weight}% / {t1.confidence_level}%</b>
          </div>

          {/* FULL GRANULAR PATH DISPLAY */}
          <div className="col-span-3 text-right border-l border-zinc-700/50 pl-2">
            <span className="text-zinc-500 uppercase font-bold text-[9px] mr-2">Target:</span>
            <b className="text-cyan-400">{displayCategory}</b>
            <span className="text-zinc-600 mx-1">/</span>
            <b className="text-zinc-200">{displaySubcategory}</b>
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
};


  const highConfidenceRows1 = workspaceRows
      .filter(r => r.confidence === 'HIGH' ||  r.confidence === 'MEDIUM')
      .map(processRowMapping);

  const zeroConfidenceRows1 = workspaceRows
    .filter(r => r.confidence === 'LOW' || r.confidence === 'ZERO')
    .map(r => ({
      ...r,
      errors: r.errors.join(' | '),
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
    }));

    // ⚡ UNFILTERED TIER 1 CAPTURE MATRIX: Direct array mapping with no data loss!
  const highConfidenceRows = workspaceRows.map(processRowMapping);
  const zeroConfidenceRows = workspaceRows.map(processRowMapping);


  return (
    <div className="bg-zinc-950 text-zinc-100 p-6 space-y-6 min-h-screen font-sans">
      {/* TOP CONTROL BAR: Dropdown Context Switcher */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center bg-zinc-900 border border-zinc-800 p-4 rounded-xl gap-4">
        <div>
          <h1 className="text-sm font-mono uppercase tracking-wider text-zinc-200 font-bold">Project Sync-Shield</h1>
          <p className="text-xs text-zinc-500 font-mono">Select target isolation account context to run evaluation gates.</p>
        </div>
        <div className="w-full sm:w-72 font-mono text-xs">
          <select
            value={selectedAccountId}
            onChange={(e) => setSelectedAccountId(e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-800 p-2.5 rounded-lg text-zinc-100 font-bold tracking-wide focus:outline-hidden focus:border-zinc-700 cursor-pointer"
          >
            <option value="">
              -- Select Active Ledger Account --
            </option>
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
              <div className="text-zinc-500 uppercase">Uncategorized Vault (Suspense / Low Confidence)</div>
              <div className="text-xl font-bold text-red-400 mt-1">{zeroConfidenceRows.length} Nodes Contained</div>
            </div>
          </div>

          <div className="bg-zinc-900/20 border border-zinc-800 rounded-lg p-4 space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-xs uppercase font-mono text-zinc-400 font-bold tracking-wider">
                {activeTab === 'bulk-high' ? 'Auto Clearance Validation Desk' : 'Uncategorized Operations Ledger'}
              </h2>
              {activeTab === 'bulk-high' && highConfidenceRows.length > 0 && (
                <button 
                  onClick={() => handleBulkClearance(workspaceRows.filter(r => r.confidence === 'HIGH' || r.confidence === 'MEDIUM'))} 
                  className="bg-emerald-600 hover:bg-emerald-700 text-zinc-950 font-mono font-bold text-xs px-3 py-1.5 rounded uppercase tracking-wider cursor-pointer"
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