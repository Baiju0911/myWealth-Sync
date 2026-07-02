import React, { useState, useEffect } from 'react';
import { TableEngine } from '../components/ui/data-table/TableEngine';
import { ACCOUNTING_HEADER_COLUMNS, SELF_TRANSFER_COLUMNS } from '../components/ui/data-table/columns';
import { 
  accountingHeaderApi, 
  selfTransferApi, 
  balanceSheetApi, 
  goldenRuleApi
} from '../api';
import type { AccountingHeaderPayload, SelfTransferPayload } from '../api';
import api from '../api/client';

type TabType = 'known-headers' | 'self-transfer' | 'balance-sheet' | 'golden-rule';

export default function AccountingHeaders() {
  const [activeTab, setActiveTab] = useState<TabType>('known-headers');
  
  // Data States
  const [headers, setHeaders] = useState<any[]>([]);
  const [selfTransfers, setSelfTransfers] = useState<any[]>([]);
  const [balanceSheet, setBalanceSheet] = useState<any>({ total_assets: 0, total_liabilities: 0, total_equity: 0 });
  const [engineRules, setEngineRules] = useState<any[]>([]);
  
  // Modal / Form UI Toggle States
  const [showHeaderForm, setShowHeaderForm] = useState(false);
  const [showTransferForm, setShowTransferForm] = useState(false);
  
  // Form Payloads
  const [newHeader, setNewHeader] = useState<AccountingHeaderPayload>({ account_name: '', account_code: '', type: 'Asset' });
  const [newTransfer, setNewTransfer] = useState<SelfTransferPayload>({ source_account_id: '', destination_account_id: '', transfer_type: 'INT', is_active: true });

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const synchronizationWorkflow = async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      // 1. Fetch the unified ledger raw master dataset and balance metric concurrently
      const [masterDatasetRes, matrixData] = await Promise.all([
        api.get('/accounting/ledger-mastercategory/'), 
        balanceSheetApi.getMatrix()
      ]);

      const rawRows = Array.isArray(masterDatasetRes.data) 
        ? masterDatasetRes.data 
        : masterDatasetRes.data.results || [];

      // 2. Extract and Map Tab 1: Known Headers (Chart of Accounts)
      // Filters out self-transfers to show clean asset/liability/expense nodes
      const mappedHeaders = rawRows
        .filter((row: any) => row.category_type !== 'SELF_TRANSFER')
        .map((h: any) => ({
          ...h,
          id: h.id,
          account_code: h.sno || h.id,
          narration_description: h.categories_items || h.act_subcategory, // Displays cleanly under "Account Name"
          tran_type: h.category_type?.toUpperCase(),                    // Displays inside center classification pill
          balance: parseFloat(h.transfer_value || '0')
        }));
      setHeaders(mappedHeaders);

      // 3. Extract and Map Tab 2: Self Transfers
      // Filters on 'SELF_TRANSFER' type and unpacks your JSON structures
      const mappedTransfers = rawRows
        .filter((row: any) => row.category_type === 'SELF_TRANSFER')
        .map((st: any) => {
          // Parse your custom inline bank metadata blocks safely
          let bankMeta = { from_bank: '-', to_bank: '-' };
          try {
            if (st.bank_types) {
              bankMeta = typeof st.bank_types === 'string' ? JSON.parse(st.bank_types) : st.bank_types;
            }
          } catch (e) {
            console.error("Failed parsing bank_types JSON payload structural matrix", e);
          }

          return {
            ...st,
            id: st.id,
            source_account_name: bankMeta.from_bank || `Origin node: ${st.sno}`,
            destination_account_name: bankMeta.to_bank || 'Target Node',
            tran_type: st.dashboard_cat?.toUpperCase() || 'TRANSFER',
            status: st.self_account?.toUpperCase() === 'SELF' ? 'ACTIVE' : 'DISABLED'
          };
        });
      setSelfTransfers(mappedTransfers);

      // 4. Set Balance Matrix & Control Gate intercepts
      setBalanceSheet(matrixData || { total_assets: 0, total_liabilities: 0, total_equity: 0 });
      
      // Fallback fallback parsing mock for rules engine if it shares the table scope
      const ruleNodes = rawRows.filter((row: any) => row.category_type === 'SYSTEM_RULE');
      setEngineRules(ruleNodes.length ? ruleNodes : [{ id: 1, rule_name: 'Double-Entry Ledger Balance Interceptor', is_enabled: true }]);

    } catch (err: any)  {
      setErrorMsg('Failed sorting ledger mastercategory data layout vectors across workspace tabs.');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    synchronizationWorkflow();
  }, []);

  const handleCreateHeader = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await accountingHeaderApi.createHeader(newHeader);
      setNewHeader({ account_name: '', account_code: '', type: 'Asset' });
      setShowHeaderForm(false);
      await synchronizationWorkflow();
    } catch (err) {
      setErrorMsg('Failed to commit new accounting ledger block.');
    }
  };

  const handleCreateTransferRoute = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await selfTransferApi.createRoute(newTransfer);
      setNewTransfer({ source_account_id: '', destination_account_id: '', transfer_type: 'INT', is_active: true });
      setShowTransferForm(false);
      await synchronizationWorkflow();
    } catch (err) {
      setErrorMsg('Failed to initialize clear self-transfer entity node.');
    }
  };

  const handleToggleRule = async (id: string | number, currentStatus: boolean) => {
    try {
      await goldenRuleApi.updateRuleConstraint(id, { is_enabled: !currentStatus });
      await synchronizationWorkflow();
    } catch (err) {
      setErrorMsg('Failed to update system interceptor state.');
    }
  };

  const tabs = [
    { id: 'known-headers', label: 'Known Headers (COA)' },
    { id: 'self-transfer', label: 'Self Transfers' },
    { id: 'balance-sheet', label: 'Balance Sheet Matrix' },
    { id: 'golden-rule', label: 'Golden Rule Engine' },
  ] as const;

  if (isLoading) {
    return <div className="p-12 text-center text-xs font-mono text-zinc-500 tracking-widest bg-zinc-950 min-h-screen">RE-INDEXING WORKSPACE NODES...</div>;
  }

  return (
    <div className="w-full bg-zinc-950 text-zinc-100 min-h-screen p-6 space-y-6">
      {errorMsg && (
        <div className="bg-red-950/40 border border-red-900/60 text-red-400 p-4 rounded-lg text-xs font-mono flex justify-between items-center">
          <span>[CRITICAL EXCEPTION] // {errorMsg}</span>
          <button onClick={() => setErrorMsg(null)} className="text-zinc-500 hover:text-zinc-200">clear</button>
        </div>
      )}

      {/* Tabs Row */}
      <div className="border-b border-zinc-800">
        <nav className="flex space-x-6">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`py-3 px-1 border-b-2 font-mono text-xs uppercase tracking-wider transition-all
                ${activeTab === tab.id ? 'border-cyan-500 text-cyan-400 font-bold' : 'border-transparent text-zinc-500 hover:text-zinc-300'}
              `}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Panels */}
      <div className="min-h-[400px]">
        
        {/* TAB 1: KNOWN HEADERS */}
        {activeTab === 'known-headers' && (
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-sm font-mono uppercase tracking-wider text-zinc-400">Chart of Accounts Matrix</h2>
              <button 
                onClick={() => setShowHeaderForm(!showHeaderForm)}
                className="bg-cyan-600 hover:bg-cyan-700 text-zinc-950 font-mono text-xs font-bold py-1.5 px-3 rounded transition-colors"
              >
                {showHeaderForm ? 'CLOSE ROW' : '+ INITIALIZE COA NODE'}
              </button>
            </div>

            {showHeaderForm && (
              <form onSubmit={handleCreateHeader} className="bg-zinc-900/60 border border-zinc-800 p-4 rounded-lg grid grid-cols-4 gap-3 items-end font-mono text-xs">
                <div>
                  <label className="block text-zinc-500 mb-1">ACCOUNT CODE</label>
                  <input type="text" required placeholder="e.g. 1010" value={newHeader.account_code} onChange={e => setNewHeader({...newHeader, account_code: e.target.value})} className="w-full bg-zinc-950 border border-zinc-800 rounded p-2 text-zinc-200 focus:outline-none focus:border-cyan-500" />
                </div>
                <div>
                  <label className="block text-zinc-500 mb-1">ACCOUNT NAME</label>
                  <input type="text" required placeholder="e.g. Citibank Operating" value={newHeader.account_name} onChange={e => setNewHeader({...newHeader, account_name: e.target.value})} className="w-full bg-zinc-950 border border-zinc-800 rounded p-2 text-zinc-200 focus:outline-none focus:border-cyan-500" />
                </div>
                <div>
                  <label className="block text-zinc-500 mb-1">CLASSIFICATION TYPE</label>
                  <select value={newHeader.type} onChange={e => setNewHeader({...newHeader, type: e.target.value as any})} className="w-full bg-zinc-950 border border-zinc-800 rounded p-2 text-zinc-200 focus:outline-none focus:border-cyan-500">
                    <option value="Asset">Asset</option>
                    <option value="Liability">Liability</option>
                    <option value="Equity">Equity</option>
                    <option value="Revenue">Revenue</option>
                    <option value="Expense">Expense</option>
                  </select>
                </div>
                <button type="submit" className="w-full bg-emerald-600 hover:bg-emerald-700 text-zinc-950 font-bold p-2 rounded transition-colors uppercase">Commit Node</button>
              </form>
            )}

            <TableEngine columns={ACCOUNTING_HEADER_COLUMNS} data={headers} />
          </div>
        )}

        {/* TAB 2: SELF TRANSFERS */}
        {activeTab === 'self-transfer' && (
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-sm font-mono uppercase tracking-wider text-zinc-400">Inter-Entity Clearing Matrix</h2>
              <button 
                onClick={() => setShowTransferForm(!showTransferForm)}
                className="bg-cyan-600 hover:bg-cyan-700 text-zinc-950 font-mono text-xs font-bold py-1.5 px-3 rounded transition-colors"
              >
                {showTransferForm ? 'CLOSE ROW' : '+ MAP CLEARING PATH'}
              </button>
            </div>

            {showTransferForm && (
              <form onSubmit={handleCreateTransferRoute} className="bg-zinc-900/60 border border-zinc-800 p-4 rounded-lg grid grid-cols-4 gap-3 items-end font-mono text-xs">
                <div>
                  <label className="block text-zinc-500 mb-1">SOURCE LEDGER ID</label>
                  <input type="text" required placeholder="Source Acc UUID / Int ID" value={newTransfer.source_account_id} onChange={e => setNewTransfer({...newTransfer, source_account_id: e.target.value})} className="w-full bg-zinc-950 border border-zinc-800 rounded p-2 text-zinc-200 focus:outline-none focus:border-cyan-500" />
                </div>
                <div>
                  <label className="block text-zinc-500 mb-1">DESTINATION LEDGER ID</label>
                  <input type="text" required placeholder="Dest Acc UUID / Int ID" value={newTransfer.destination_account_id} onChange={e => setNewTransfer({...newTransfer, destination_account_id: e.target.value})} className="w-full bg-zinc-950 border border-zinc-800 rounded p-2 text-zinc-200 focus:outline-none focus:border-cyan-500" />
                </div>
                <div>
                  <label className="block text-zinc-500 mb-1">ROUTE CODE</label>
                  <input type="text" placeholder="INT" value={newTransfer.transfer_type} onChange={e => setNewTransfer({...newTransfer, transfer_type: e.target.value})} className="w-full bg-zinc-950 border border-zinc-800 rounded p-2 text-zinc-200 focus:outline-none focus:border-cyan-500" />
                </div>
                <button type="submit" className="w-full bg-emerald-600 hover:bg-emerald-700 text-zinc-950 font-bold p-2 rounded transition-colors uppercase">Deploy Path</button>
              </form>
            )}

            <TableEngine columns={SELF_TRANSFER_COLUMNS} data={selfTransfers} />
          </div>
        )}

        {/* TAB 3: BALANCE SHEET MATRIX */}
        {activeTab === 'balance-sheet' && (
          <div className="space-y-6">
            <h2 className="text-sm font-mono uppercase tracking-wider text-zinc-400">Equation Ledger Status</h2>
            <div className="grid grid-cols-3 gap-4 font-mono">
              <div className="border border-zinc-800/80 bg-zinc-900/40 p-4 rounded-lg">
                <span className="text-[10px] text-zinc-500 uppercase">Total Assets</span>
                <p className="text-xl font-bold text-emerald-400 mt-1">${Number(balanceSheet.total_assets || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</p>
              </div>
              <div className="border border-zinc-800/80 bg-zinc-900/40 p-4 rounded-lg">
                <span className="text-[10px] text-zinc-500 uppercase">Total Liabilities</span>
                <p className="text-xl font-bold text-red-400 mt-1">${Number(balanceSheet.total_liabilities || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</p>
              </div>
              <div className="border border-zinc-800/80 bg-zinc-900/40 p-4 rounded-lg">
                <span className="text-[10px] text-zinc-500 uppercase">Owner Equity</span>
                <p className="text-xl font-bold text-cyan-400 mt-1">${Number(balanceSheet.total_equity || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</p>
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: GOLDEN RULE INTERCEPTORS */}
        {activeTab === 'golden-rule' && (
          <div className="space-y-4">
            <h2 className="text-sm font-mono uppercase tracking-wider text-zinc-400">System Constraint Gates</h2>
            <div className="border border-zinc-800/80 bg-zinc-900/40 p-4 rounded-lg font-mono text-xs text-zinc-300 divide-y divide-zinc-800/40">
              {engineRules.map((rule: any) => (
                <div key={rule.id} className="flex justify-between items-center py-3 first:pt-0 last:pb-0">
                  <span>{rule.rule_name || 'Double-Entry Validation Active'}</span>
                  <button 
                    type="button"
                    onClick={() => handleToggleRule(rule.id, rule.is_enabled)}
                    className={`px-3 py-1 rounded text-[10px] font-bold transition-all ${rule.is_enabled ? "bg-emerald-950 text-emerald-400 border border-emerald-800" : "bg-red-950 text-red-400 border border-red-900"}`}
                  >
                    {rule.is_enabled ? "ENFORCED (TOGGLE)" : "BYPASSED (TOGGLE)"}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}