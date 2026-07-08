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

// 🎯 Pipeline stats structural shape definition
interface PipelineStats {
  systemRules: number;
  internalTransfers: number;
  masterRulebook: number;
  ledgerLayout: number;
  fallback: number;
}

interface WorkspaceNode extends BaseWorkspaceNode {
  confidence: 'HIGH' | 'MEDIUM' | 'LOW' | 'ZERO';
  pipeline_trace: {
    stop1_known_default: any;
    stop2_self_transfer: any;
    stop3_balance_sheet: any;
    stop4_accounting_rule: any;
  };
  tier1_metrics?: {
    active_tier_level: number;
    matched_keyword_token: string;
    execution_weight: number;
    confidence_level: number;
    t1_category: string;
    t1_subcategory: string;
    t2_category: string;
    t2_subcategory: string;
    t3_category: string;
    t3_subcategory: string;
    t4_category: string;
    t4_subcategory: string;
    elected_category: string;
    elected_subcategory: string;
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

  // 🎯 ADDED HOOK: Local state tracking for source-of-truth backend statistics
  const [stats, setStats] = useState<PipelineStats>({
    systemRules: 0,
    internalTransfers: 0,
    masterRulebook: 0,
    ledgerLayout: 0,
    fallback: 0
  });


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

  const loadWorkspaceMatrix = async (targetId: string) => {
    if (!targetId || !targetId.trim()) {
      setWorkspaceRows([]); 
      // 🎯 RESET CODES: Clear back to zero state when no account is selected
      setStats({ systemRules: 0, internalTransfers: 0, ledgerLayout: 0, masterRulebook: 0, fallback: 0 });
      return;
    }
    setIsLoading(true);
    setErrorMsg(null);
    try {
      // 🎯 THE FIX: Force 'any' here so TS lets us access the new payload attributes seamlessly
      const data = await stagingQueueApi.evaluateWorkspace(targetId) as any;
      setWorkspaceRows(data.workspace_queue || []);
      
      // 🎯 THE SOURCE OF TRUTH COMMIT: Bind the backend stats directly to React state
      if (data.summary_stats) {
        setStats(data.summary_stats);
      }
    } catch (err: any) {
      setErrorMsg('Failed running verification pipeline over staging collection.');
      setWorkspaceRows([]);
      // 🎯 RESET CODES: Clear back to zero state on pipeline crash
      setStats({ systemRules: 0, internalTransfers: 0, ledgerLayout: 0, masterRulebook: 0, fallback: 0 });
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

  // 🎯 ELECTED TIER PROXY MAPPING: Displays pure voting metrics and parallel data lines cleanly
  const processRowMapping = (r: any) => {
    const t1 = r.tier1_metrics || {};
    const tier = t1.active_tier_level || 0;
    
    let statusText = "FALLBACK SUSPENSE";
    let statusColor = "text-amber-500";
    let badgeColor = "border-zinc-900/80 bg-zinc-950/60";
    
    if (tier === 1) {
      statusText = "SYSTEM RULES HIT";
      statusColor = "text-emerald-500 font-bold";
      badgeColor = "border-emerald-950 bg-emerald-950/20";
    } else if (tier === 2) {
      statusText = "INTERNAL TRANSFER HIT";
      statusColor = "text-cyan-400 font-bold";
      badgeColor = "border-cyan-950 bg-cyan-950/30";
    } else if (tier === 3) {
      statusText = "LEDGER LAYOUT HIT";
      statusColor = "text-fuchsia-400 font-bold";
      badgeColor = "border-fuchsia-950 bg-fuchsia-950/20";
    } else if (tier === 4) {
      statusText = "MASTER RULEBOOK HIT";
      statusColor = "text-yellow-500 font-bold";
      badgeColor = "border-yellow-950 bg-yellow-950/20";
    }

    return {
      ...r,
      // Bind main rows to the election winner outputs calculated by backend voting mechanics
      category_item: t1.elected_category || "None",
      subcategory_item: t1.elected_subcategory || "None",
      rule_code: t1.matched_keyword_token || "Unassigned",
      
      // Explicitly map all parallel tracks to their independent verification slots
      T1_item: t1.t1_category && t1.t1_category !== "None" ? `${t1.t1_category}→${t1.t1_subcategory}` : "None→None",
      T2_item: t1.t2_category && t1.t2_category !== "None" ? `${t1.t2_category}→${t1.t2_subcategory}` : "None→None",
      T3_item: t1.t3_category && t1.t3_category !== "None" ? `${t1.t3_category}→${t1.t3_subcategory}` : "None→None",
      T4_item: t1.t4_category && t1.t4_category !== "None" ? `${t1.t4_category}→${t1.t4_subcategory}` : "None→None",
      
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
              <b className="text-zinc-300">"{t1.matched_keyword_token || 'None'}"</b>
            </div>

            <div className="sm:text-right">
              <span className="text-zinc-500 uppercase font-bold text-[9px] mr-1">Conf:</span>
              <b className="text-zinc-300">{t1.confidence_level}%</b>
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

  // Filter lists based on whether they matched a specific rule vs dropping to fallback zero level
  const highConfidenceRows = workspaceRows
    .filter(r => (r.tier1_metrics?.active_tier_level || 0) > 0)
    .map(processRowMapping);

  const zeroConfidenceRows = workspaceRows
    .filter(r => (r.tier1_metrics?.active_tier_level || 0) === 0)
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

        {/* 🚀 FIXED HORIZONTAL ENGINE TICKER BAR VIA INLINE FLEX */}
        <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-xl p-4 font-mono text-xs shadow-md">
          <div style={{ display: 'flex', flexDirection: 'row', width: '100%', alignItems: 'center', justifyContent: 'space-between' }}>
            
            {/* 1. Internal Transfers */}
            <div style={{ flex: 1, textAlign: 'center', padding: '0 8px' }} className="flex flex-col justify-center items-center gap-1">
              <span className="text-[9px] font-bold uppercase tracking-wider text-cyan-400">Internal Transfers</span>
              <div className="text-sm font-bold text-zinc-100 flex items-baseline justify-center gap-1">
                {stats.internalTransfers} <span className="text-[10px] font-normal text-zinc-500">Rows</span>
              </div>
              <span className="hidden lg:inline text-[9px] text-zinc-600 tracking-tight">Self-account tunnels</span>
            </div>

            {/* 2. System Rules */}
            <div style={{ flex: 1, textAlign: 'center', padding: '0 8px', borderLeft: '1px solid rgba(63, 63, 70, 0.4)' }} className="flex flex-col justify-center items-center gap-1">
              <span className="text-[9px] font-bold uppercase tracking-wider text-emerald-400">System Rules</span>
              <div className="text-sm font-bold text-zinc-100 flex items-baseline justify-center gap-1">
                {stats.systemRules} <span className="text-[10px] font-normal text-zinc-500">Rows</span>
              </div>
              <span className="hidden lg:inline text-[9px] text-zinc-600 tracking-tight">High precision filters</span>
            </div>

            {/* 3. Master Rulebook */}
            <div style={{ flex: 1, textAlign: 'center', padding: '0 8px', borderLeft: '1px solid rgba(63, 63, 70, 0.4)' }} className="flex flex-col justify-center items-center gap-1">
              <span className="text-[9px] font-bold uppercase tracking-wider text-yellow-500">Master Rulebook</span>
              <div className="text-sm font-bold text-zinc-100 flex items-baseline justify-center gap-1">
                {stats.masterRulebook} <span className="text-[10px] font-normal text-zinc-500">Rows</span>
              </div>
              <span className="hidden lg:inline text-[9px] text-zinc-600 tracking-tight">Golden rules</span>
            </div>

            {/* 4. Ledger Layout */}
            <div style={{ flex: 1, textAlign: 'center', padding: '0 8px', borderLeft: '1px solid rgba(63, 63, 70, 0.4)' }} className="flex flex-col justify-center items-center gap-1">
              <span className="text-[9px] font-bold uppercase tracking-wider text-fuchsia-400">Ledger Layout</span>
              <div className="text-sm font-bold text-zinc-100 flex items-baseline justify-center gap-1">
                {stats.ledgerLayout} <span className="text-[10px] font-normal text-zinc-500">Rows</span>
              </div>
              <span className="hidden lg:inline text-[9px] text-zinc-600 tracking-tight">Dynamic macro paths</span>
            </div>

            {/* 5. Golden Fallback */}
            <div style={{ flex: 1, textAlign: 'center', padding: '0 8px', borderLeft: '1px solid rgba(63, 63, 70, 0.4)' }} className="flex flex-col justify-center items-center gap-1">
              <span className="text-[9px] font-bold uppercase tracking-wider text-amber-500">Golden Fallback</span>
              <div className="text-sm font-bold text-zinc-100 flex items-baseline justify-center gap-1">
                {stats.fallback} <span className="text-[10px] font-normal text-zinc-500">Rows</span>
              </div>
              <span className="hidden lg:inline text-[9px] text-zinc-600 tracking-tight">Directional suspense</span>
            </div>

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
                    onClick={() => handleBulkClearance(workspaceRows.filter(r => (r.tier1_metrics?.active_tier_level || 0) > 0))} 
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