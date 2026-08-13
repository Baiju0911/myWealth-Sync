import React, { useState, useEffect } from 'react';
import { TableEngine } from '../components/ui/data-table/TableEngine';
import { 
  ACCOUNTING_HEADER_COLUMNS, 
  SELF_TRANSFER_COLUMNS,
  BALANCE_SHEET_COLUMNS // 📊 Import new columns layout
} from '../components/ui/data-table/columns';
import { ledgerMasterApi } from '../api/api';


type TabType = 'known-headers' | 'self-transfer' | 'balance-sheet';

export default function AccountingHeaders() {
  const [activeTab, setActiveTab] = useState<TabType>('known-headers');
  
  // Data Vectors
  const [headers, setHeaders] = useState<any[]>([]);
  const [selfTransfers, setSelfTransfers] = useState<any[]>([]);
  const [balanceSheetRows, setBalanceSheetRows] = useState<any[]>([]); // 🎯 FIXED: Proper raw rows state array
  
  // Workspace Mutation Toggles
  const [showHeaderForm, setShowHeaderForm] = useState(false);
  const [showTransferForm, setShowTransferForm] = useState(false);
  const [showBalanceForm, setShowBalanceForm] = useState(false); // New form toggle
  
  // Input Forms States
  const [newHeader, setNewHeader] = useState({ sno: '', type: 'KNOWN_DEFAULT', cat: 'Account Transfer', subcat: 'Transfer', item: 'Account Transfer', remarks: '' });
  const [newTransfer, setNewTransfer] = useState({ sno: '', from_bank: '', to_bank: '', remarks: '' });
  const [newBalanceRow, setNewBalanceRow] = useState({ sno: '', cat: 'Assets', subcat: '', item: '', dashCat: 'Investments', remarks: '' }); // Form state

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);


  /* ==========================================================================
     1. MUTATION CRUD HANDLERS
     ========================================================================== */
  
  const handleDeleteRow = async (id: string | number) => {
    if (!window.confirm(`Permanently remove master entry index row ${id}?`)) return;
    try {
      await ledgerMasterApi.deleteMasterCategory(id);
      await synchronizationWorkflow();
    } catch (err) {
      setErrorMsg('Failed to drop requested data node.');
    }
  };

  const handleCreateHeader = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload = {
        category_type: newHeader.type, // Maps to 'REGULAR' or 'KNOWN_DEFAULT'
        sno: newHeader.sno,
        act_category: newHeader.cat,
        act_subcategory: newHeader.subcat,
        categories_items: newHeader.item,
        dashboard_cat: 'Auto Routed',
        remarks: newHeader.remarks,
        transfer_value: null,
        monthly_expense: '0',
        bank_types: '{}',
        keys: '{}'
      };

      // 🎯 FIXED: Direct routing to unified api configuration wrapper method
      await ledgerMasterApi.createMasterCategory(payload);
      
      setNewHeader({ sno: '', type: 'KNOWN_DEFAULT', cat: 'Account Transfer', subcat: 'Transfer', item: 'Account Transfer', remarks: '' });
      setShowHeaderForm(false);
      await synchronizationWorkflow();
    } catch (err) {
      setErrorMsg('Failed creating master category item reference inside Known Headers.');
    }
  };

  const handleCreateTransfer = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload = {
        category_type: 'SELF_TRANSFER',
        sno: newTransfer.sno,
        act_category: 'Assets',
        act_subcategory: 'Self Inter-Account Transfer',
        categories_items: `By ${newTransfer.from_bank} To ${newTransfer.to_bank}`,
        dashboard_cat: 'Transfers',
        self_account: 'Self',
        remarks: newTransfer.remarks,
        transfer_value: null,
        monthly_expense: '0',
        bank_types: JSON.stringify({ to_bank: newTransfer.to_bank, from_bank: newTransfer.from_bank }),
        keys: '{}'
      };

      // 🎯 FIXED: Direct routing to unified api configuration wrapper method
      await ledgerMasterApi.createMasterCategory(payload);
      
      setNewTransfer({ sno: '', from_bank: '', to_bank: '', remarks: '' });
      setShowTransferForm(false);
      await synchronizationWorkflow();
    } catch (err) {
      setErrorMsg('Failed writing self-transfer configuration record.');
    }
  };

  const handleCreateBalanceRow = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload = {
        category_type: 'REGULAR',
        sno: newBalanceRow.sno,
        act_category: newBalanceRow.cat,
        act_subcategory: newBalanceRow.subcat,
        categories_items: newBalanceRow.item,
        dashboard_cat: newBalanceRow.dashCat,
        remarks: newBalanceRow.remarks,
        transfer_value: null,
        monthly_expense: '0',
        bank_types: '{}',
        keys: '{}'
      };

      // 🎯 FIXED: Direct routing to unified api configuration wrapper method
      await ledgerMasterApi.createMasterCategory(payload);
      
      setNewBalanceRow({ sno: '', cat: 'Assets', subcat: '', item: '', dashCat: 'Investments', remarks: '' });
      setShowBalanceForm(false);
      await synchronizationWorkflow();
    } catch (err) {
      setErrorMsg('Failed writing balance sheet header entry.');
    }
  };


  /* ==========================================================================
     2. DATA LAYOUT SYNCHRONIZER
     ========================================================================== */
  
  const synchronizationWorkflow = async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const data = await ledgerMasterApi.getMasterCategories();
      
      const rawRows = Array.isArray(data) 
        ? data 
        : data.results || data.data || [];

      if (!Array.isArray(rawRows)) {
        throw new Error(`Data field is not iterable. Received type: ${typeof rawRows}`);
      }

      // 🛠️ 1. Tab 1: Known Defaults & Operational Headers
      const mappedHeaders = rawRows
        .filter((row: any) => row && row.category_type === 'KNOWN_DEFAULT')
        .map((h: any) => ({
          ...h,
          id: h.id,
          narration_description: h.categories_items || h.act_subcategory || 'Unnamed Node',
          tran_type: h.category_type, 
          onDelete: handleDeleteRow
        }));
      setHeaders(mappedHeaders);

      // 🛠️ 2. Tab 2: Self Transfers
      const mappedTransfers = rawRows
        .filter((row: any) => row && row.category_type === 'SELF_TRANSFER')
        .map((st: any) => {
          let parsedBanks = { from_bank: 'Unknown Node', to_bank: 'Unknown Target' };
          try {
            if (st.bank_types) {
              const cleaned = typeof st.bank_types === 'string' ? JSON.parse(st.bank_types) : st.bank_types;
              parsedBanks.from_bank = cleaned.from_bank || parsedBanks.from_bank;
              parsedBanks.to_bank = cleaned.to_bank || parsedBanks.to_bank;
            }
          } catch (err) {}

          return {
            ...st,
            id: st.id,
            source_account_name: parsedBanks.from_bank,
            destination_account_name: parsedBanks.to_bank,
            narration_description: st.categories_items || 'Inter-account movement', 
            tran_type: 'SELF',
            onDelete: handleDeleteRow
          };
        });
      setSelfTransfers(mappedTransfers);

      // 🛠️ 3. Tab 3: Balance Sheet Core Structural Headers (REGULAR)
      const mappedBalanceSheet = rawRows
        .filter((row: any) => row && row.category_type === 'REGULAR')
        .map((b: any) => ({
          ...b,
          id: b.id,
          narration_description: b.categories_items || b.act_subcategory,
          onDelete: handleDeleteRow
        }));
      setBalanceSheetRows(mappedBalanceSheet);

    } catch (err: any) {
      setErrorMsg(`[VECTORS ERROR]: ${err.message || err}. Check console logs.`);
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    synchronizationWorkflow();
  }, []);

  const tabs = [
    { id: 'known-headers', label: 'Known Headers (COA)' },
    { id: 'self-transfer', label: 'Self Transfers' },
    { id: 'balance-sheet', label: 'Balance Sheet Matrix' }
  ] as const;

  if (isLoading) {
    return <div className="p-12 text-center text-xs font-mono text-zinc-500 bg-zinc-950 min-h-screen">RE-INDEXING WORKSPACE NODES...</div>;
  }

  return (
    <div className="w-full bg-zinc-950 text-zinc-100 min-h-screen p-6 space-y-6">
      {errorMsg && (
        <div className="bg-red-950/40 border border-red-900/60 text-red-400 p-4 rounded text-xs font-mono flex justify-between">
          <span>[CRITICAL EXCEPTION] // {errorMsg}</span>
          <button onClick={() => setErrorMsg(null)} className="text-zinc-500 hover:text-zinc-300">clear</button>
        </div>
      )}

      {/* Navigation Headers */}
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

      {/* Content Panels */}
      <div className="min-h-[400px]">
        {activeTab === 'known-headers' && (
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-sm font-mono uppercase text-zinc-400">Chart of Accounts Matrix</h2>
              <button onClick={() => setShowHeaderForm(!showHeaderForm)} className="bg-cyan-600 hover:bg-cyan-700 text-zinc-950 font-mono text-xs font-bold py-1.5 px-3 rounded">
                {showHeaderForm ? 'CLOSE Form' : '+ INITIALIZE COA ROW'}
              </button>
            </div>

            {showHeaderForm && (
              <form onSubmit={handleCreateHeader} className="bg-zinc-900/40 border border-zinc-800 p-4 rounded-lg grid grid-cols-3 gap-3 font-mono text-xs">
                <input type="text" placeholder="SNO (e.g. 1709)" value={newHeader.sno} onChange={e => setNewHeader({...newHeader, sno: e.target.value})} className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200" required />
                <input type="text" placeholder="CATEGORY (e.g. Account Transfer)" value={newHeader.cat} onChange={e => setNewHeader({...newHeader, cat: e.target.value})} className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200" required />
                <input type="text" placeholder="SUBCATEGORY (e.g. Transfer)" value={newHeader.subcat} onChange={e => setNewHeader({...newHeader, subcat: e.target.value})} className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200" required />
                <input type="text" placeholder="ITEM NAME" value={newHeader.item} onChange={e => setNewHeader({...newHeader, item: e.target.value})} className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200" required />
                <input type="text" placeholder="REMARKS" value={newHeader.remarks} onChange={e => setNewHeader({...newHeader, remarks: e.target.value})} className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200" />
                <button type="submit" className="bg-emerald-600 text-zinc-950 font-bold p-2 rounded uppercase">Deploy Header</button>
              </form>
            )}

            <TableEngine columns={ACCOUNTING_HEADER_COLUMNS} data={headers} />
          </div>
        )}

        {activeTab === 'self-transfer' && (
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-sm font-mono uppercase text-zinc-400">Inter-Entity Clearing Matrix</h2>
              <button onClick={() => setShowTransferForm(!showTransferForm)} className="bg-cyan-600 hover:bg-cyan-700 text-zinc-950 font-mono text-xs font-bold py-1.5 px-3 rounded">
                {showTransferForm ? 'CLOSE Form' : '+ DEPLOY ROUTING VECTOR'}
              </button>
            </div>

            {showTransferForm && (
              <form onSubmit={handleCreateTransfer} className="bg-zinc-900/40 border border-zinc-800 p-4 rounded-lg grid grid-cols-4 gap-3 font-mono text-xs">
                <input type="text" placeholder="SNO CODE (e.g. 369)" value={newTransfer.sno} onChange={e => setNewTransfer({...newTransfer, sno: e.target.value})} className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200" required />
                <input type="text" placeholder="FROM BANK CODE" value={newTransfer.from_bank} onChange={e => setNewTransfer({...newTransfer, from_bank: e.target.value})} className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200" required />
                <input type="text" placeholder="TO BANK CODE" value={newTransfer.to_bank} onChange={e => setNewTransfer({...newTransfer, to_bank: e.target.value})} className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200" required />
                <input type="text" placeholder="REMARKS" value={newTransfer.remarks} onChange={e => setNewTransfer({...newTransfer, remarks: e.target.value})} className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200" />
                <button type="submit" className="bg-emerald-600 text-zinc-950 font-bold p-2 rounded uppercase">Commit Route</button>
              </form>
            )}

            <TableEngine columns={SELF_TRANSFER_COLUMNS} data={selfTransfers} />
          </div>
        )}

        {/* 📊 TAB 3: PROPER BALANCE SHEET CRUD ROW PANEL */}
        {activeTab === 'balance-sheet' && (
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-sm font-mono uppercase text-zinc-400">Balance Sheet Layout Config</h2>
              <button onClick={() => setShowBalanceForm(!showBalanceForm)} className="bg-cyan-600 hover:bg-cyan-700 text-zinc-950 font-mono text-xs font-bold py-1.5 px-3 rounded">
                {showBalanceForm ? 'CLOSE Form' : '+ INITIALIZE BALANCE ITEM'}
              </button>
            </div>

            {showBalanceForm && (
              <form onSubmit={handleCreateBalanceRow} className="bg-zinc-900/40 border border-zinc-800 p-4 rounded-lg grid grid-cols-3 gap-3 font-mono text-xs">
                <input type="text" placeholder="SNO (e.g. 1655)" value={newBalanceRow.sno} onChange={e => setNewBalanceRow({...newBalanceRow, sno: e.target.value})} className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200" required />
                <select value={newBalanceRow.cat} onChange={e => setNewBalanceRow({...newBalanceRow, cat: e.target.value})} className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200">
                  <option value="Assets">Assets</option>
                  <option value="Liabilities">Liabilities</option>
                  <option value="Equity">Equity</option>
                </select>
                <input type="text" placeholder="SUBCATEGORY (e.g. Gold & Investments)" value={newBalanceRow.subcat} onChange={e => setNewBalanceRow({...newBalanceRow, subcat: e.target.value})} className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200" required />
                <input type="text" placeholder="ITEM LABEL (e.g. AG Asset)" value={newBalanceRow.item} onChange={e => setNewBalanceRow({...newBalanceRow, item: e.target.value})} className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200" required />
                <input type="text" placeholder="DASHBOARD CAT (e.g. Investments)" value={newBalanceRow.dashCat} onChange={e => setNewBalanceRow({...newBalanceRow, dashCat: e.target.value})} className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200" required />
                <input type="text" placeholder="REMARKS" value={newBalanceRow.remarks} onChange={e => setNewBalanceRow({...newBalanceRow, remarks: e.target.value})} className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200" />
                <button type="submit" className="bg-emerald-600 text-zinc-950 font-bold p-2 rounded uppercase col-span-3">Commit Balance Sheet Row</button>
              </form>
            )}

            <TableEngine columns={BALANCE_SHEET_COLUMNS} data={balanceSheetRows} />
          </div>
        )}
      </div>
    </div>
  );
}