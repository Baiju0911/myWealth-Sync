import React, { useState, useEffect } from 'react';
import { accountApi } from '../api.ts';
import api from '../api/client';
import { type AccountEntity } from '../types/ledger';

interface StagingPreviewLine {
  id: string;
  post_date: string;
  value_date?: string;
  narration_description: string;
  tran_type?: string;      
  chq_ref?: string;               
  credit: number | null;
  debit: number | null;
  balance?: number;               
  amount?: number;                
  status: string;
  Hex?: string;
}

interface TemplateMetadata {
  id: number;
  template_name: string;
  is_universal: boolean;
}

interface ApiResponseMeta {
  fileType: string;
  decrypted: boolean;
  count: number;
  openingBalance: number;
  closingBalance: number;
  totalDebit: number;
  totalCredit: number;
  rawMatchCount: number;
  debitLineCount: number;
  creditLineCount: number;
  emptyMemoLineCount: number; // 📋 MAPS DIRECTLY TO API PIPELINE VALUES
  duplicateCount: number; 
  report_from_date?: string | null;
  report_to_date?: string | null;
}

export default function UniversalStatementIngestView() {
  const [accounts, setAccounts] = useState<AccountEntity[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  
  const [loading, setLoading] = useState(false);
  const [commitLoading, setCommitLoading] = useState(false);
  
  const [previewLines, setPreviewLines] = useState<StagingPreviewLine[]>([]);
  const [responseMeta, setResponseMeta] = useState<ApiResponseMeta | null>(null); 
  
  const [errorMsg, setErrorMsg] = useState('');
  const [commitSuccessMsg, setCommitSuccessMsg] = useState('');

  const [availableTemplates, setAvailableTemplates] = useState<TemplateMetadata[]>([]);
  const [forcedTemplateId, setForcedTemplateId] = useState<string>('');



  const downloadWorkableCSV = (rawStreamText: string) => {
    if (!rawStreamText) return;
    
    let cleanContent = rawStreamText;
    let exportFilename = "statement_export.csv";
    
    // 🎯 PARSE INJECTED METADATA BLOCK
    if (rawStreamText.startsWith("#FILENAME:")) {
      const lines = rawStreamText.split("\n");
      const metaLine = lines[0]; // Grab '#FILENAME:xyz.csv'
      
      // Extract everything after the colon
      exportFilename = metaLine.replace("#FILENAME:", "").trim() || "statement_export.csv";      
      // Remove the tracking row completely so it doesn't mess up your spreadsheet columns
      cleanContent = lines.slice(1).join("\n");
    }
    
    // Convert tildes to commas for standard excel processing
    const csvContent = cleanContent.replace(/ ~ /g, ",");
    
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    
    link.setAttribute("href", url);
    link.setAttribute("download", exportFilename);
    
    console.log("🎯 DOWNLOADING WORKABLE FILE AS:", exportFilename);
    
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };
  useEffect(() => {
    accountApi.getAccounts()
      .then(res => setAccounts(Array.isArray(res) ? res : res.results || []))
      .catch(() => setErrorMsg('Failed loading ledger workspace nodes.'));

    api.get('/statements/available/')
      .then((res) => setAvailableTemplates(res.data || []))
      .catch((err) => console.error("Failed loading configuration maps:", err));
  }, []);

  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = () => setIsDragging(false);
  
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const droppedFile = e.dataTransfer.files[0];
      setFile(droppedFile);
      if (selectedAccountId) {
        executeUploadDirectly(droppedFile, selectedAccountId);
      } else {
        setErrorMsg("Please select a target bank account channel first.");
      }
    }
  };
    
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      setFile(selectedFile);
      if (selectedAccountId) {
        executeUploadDirectly(selectedFile, selectedAccountId);
      } else {
        setErrorMsg("Please select a target bank account channel first.");
      }
    }
  };

  const executeUploadDirectly = async (targetFile: File, accountId: string) => {
    setLoading(true);
    setErrorMsg('');
    setCommitSuccessMsg('');
    setPreviewLines([]);
    setResponseMeta(null);

    const formData = new FormData();
    formData.append('statement_file', targetFile);
    formData.append('account_id', accountId);
    if (forcedTemplateId) {
      formData.append('forced_template_id', forcedTemplateId);
    }

    try {
      const res = await api.post('/statement/ingestbulk/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      if (res.data.status === 'SUCCESS') {
        const dataset = res.data.data?.preview_dataset || res.data.preview_dataset || [];
        setPreviewLines(dataset);
        
        setResponseMeta({
          fileType: res.data.data?.file_type || res.data.file_type || 'UNKNOWN',
          decrypted: res.data.data?.decrypted || res.data.decrypted || false,
          count: res.data.data?.count || res.data.count || 0,
          openingBalance: res.data.data?.opening_balance || res.data.opening_balance || 0,
          closingBalance: res.data.data?.closing_balance || res.data.closing_balance || 0,
          totalDebit: res.data.data?.total_debit || res.data.total_debit || 0,
          totalCredit: res.data.data?.total_credit || res.data.total_credit || 0,
          rawMatchCount: res.data.data?.raw_match_count || res.data.raw_match_count || 0,
          debitLineCount: res.data.data?.debit_line_count || res.data.debit_line_count || 0,
          creditLineCount: res.data.data?.credit_line_count || res.data.credit_line_count || 0,
          emptyMemoLineCount: res.data.data?.empty_memo_line_count || res.data.empty_memo_line_count || 0,
          duplicateCount: res.data.data?.duplicate_count || res.data.duplicate_count || 0, 
        });
        (window as any).__lastRawStream = res.data.data?.raw_csv_stream || res.data.raw_csv_stream || "";
      }
    } catch (err: any) {
      console.error(err);
      setErrorMsg(err.response?.data?.message || 'Staging engine processing failure.');
    } finally {
      setLoading(true); // Keeps layout stable until teardown completes
      setLoading(false);
    }
  };

  const handleCommitStaging = async () => {
    if (!selectedAccountId || !previewLines || previewLines.length === 0) return;
    setCommitLoading(true);
    try {
      const res = await api.post('/statement/commit-staging/', {
        account_id: selectedAccountId,
        preview_dataset: previewLines,
        file_name: file ? file.name : "9COL_STATEMENT.PDF", 
        meta_summary: responseMeta, 
      });
      if (res.data.status === 'SUCCESS') {
        setCommitSuccessMsg(res.data.message);
        setPreviewLines([]); setResponseMeta(null); setFile(null);
      }
    } catch (err: any) {
      setErrorMsg(err.response?.data?.message || 'Database commit error.');
    } finally { setCommitLoading(false); }
  };

  const opening = responseMeta?.openingBalance || 0;
  const totalCredit = responseMeta?.totalCredit || 0;
  const totalDebit = responseMeta?.totalDebit || 0;
  const statementClosing = responseMeta?.closingBalance || 0;
  const calculatedClosingValue = opening + totalCredit - totalDebit;
  
  const isBalanceVerified = responseMeta ? Math.abs(calculatedClosingValue - statementClosing) < 0.05 : false;
  const frontendRenderCount = previewLines.length;
  const isRowCountVerified = responseMeta ? responseMeta.count === frontendRenderCount : false;
  const isFileFullyStale = responseMeta ? responseMeta.count === 0 : false;
  const isDoubleTrustOk = isBalanceVerified && isRowCountVerified && !isFileFullyStale;

  return (
    <div className="space-y-6 text-white p-2 text-left">
      <div>
        <h2 className="text-2xl font-bold tracking-tight text-emerald-400">Universal 9-Column Ingestion Pipeline</h2>
        <p className="text-sm text-zinc-400 mt-1">Dynamic coordinate tracking processor capturing 100% of rows from multi-page JPEGs/PDFs.</p>
      </div>

      {commitSuccessMsg && <div className="p-4 bg-emerald-500/10 text-emerald-400 text-sm border border-emerald-500/20 rounded-xl font-medium shadow-lg">{commitSuccessMsg}</div>}

      <br/>

{/* 📊 High-Performance Summary Reconciliation & Double-Trust Matrix Deck */}
{responseMeta && (
  <div className="w-full bg-zinc-950 border border-zinc-800 rounded-xl p-6 shadow-2xl space-y-6 font-mono text-zinc-300 block clear-both" style={{ width: '100%', minWidth: '100%', display: 'block' }}>
    
    {/* 📋 SECTION HEADER */}
    <div className="w-full flex flex-row items-center justify-between border-b border-zinc-800 pb-3 gap-4" style={{ display: 'flex', flexDirection: 'row', justifyContent: 'space-between' }}>
      <div className="flex items-center gap-2 min-w-0" style={{ display: 'flex', alignItems: 'center' }}>
        <span className="text-emerald-400 text-base shrink-0">⚖️</span>
        <h3 className="text-sm tracking-wider uppercase truncate" style={{ fontWeight: 900, color: '#f3f4f6' }}>
          Automated Engine Verification Summary Deck
        </h3>
      </div>
      <div className="text-[10px] uppercase tracking-widest shrink-0 bg-zinc-900 px-2 py-0.5 border border-zinc-800 rounded hidden sm:inline-block" style={{ fontWeight: 700, color: '#9ca3af' }}>
        File Mode: {responseMeta.fileType}
      </div>
    </div>

    {/* 📡 GRID LAYER 1: TELEMETRY MATRIX STRIPS */}
    <div className="w-full block" style={{ display: 'block', width: '100%' }}>
      <div className="text-[10px] uppercase tracking-wider mb-3" style={{ fontWeight: 900, color: '#f3f4f6' }}>
        Telemetry Stream Metrics
      </div>
      
      {/* Expanded Horizontal Grid: Now split into 6 explicit structural slots */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, minmax(0, 1fr))', gap: '12px', width: '100%' }}>
        
        {/* ACTIVE DEBITS CARD */}
        <div className="bg-zinc-900/40 border border-zinc-800 rounded-lg p-3 col-span-2 sm:col-span-1" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', minWidth: '0' }}>
          <div className="text-[10px] uppercase tracking-wider truncate" style={{ fontWeight: 900, color: '#9ca3af' }}>
            <span style={{ display: 'inline-block', width: '6px', height: '6px', backgroundColor: '#f87171', borderRadius: '50%', marginRight: '6px' }}></span> Debits
          </div>
          <div className="text-lg font-bold text-red-400 mt-2 font-mono tabular-nums">
            {responseMeta.debitLineCount} <span style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#6b7280', fontSize: '10px' }}>Rows</span>
          </div>
        </div>

        {/* ACTIVE CREDITS CARD */}
        <div className="bg-zinc-900/40 border border-zinc-800 rounded-lg p-3 col-span-2 sm:col-span-1" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', minWidth: '0' }}>
          <div className="text-[10px] uppercase tracking-wider truncate" style={{ fontWeight: 900, color: '#9ca3af' }}>
            <span style={{ display: 'inline-block', width: '6px', height: '6px', backgroundColor: '#34d399', borderRadius: '50%', marginRight: '6px' }}></span> Credits
          </div>
          <div className="text-lg font-bold text-emerald-400 mt-2 font-mono tabular-nums">
            {responseMeta.creditLineCount} <span style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#6b7280', fontSize: '10px' }}>Rows</span>
          </div>
        </div>

        {/* 🚥 NEW FIELD: LIVE FRESH/NEW LEDGER COUNTER */}
        <div className="bg-cyan-950/20 border border-cyan-800/30 rounded-lg p-3 col-span-2 sm:col-span-1" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', minWidth: '0' }}>
          <div className="text-[10px] uppercase tracking-wider truncate" style={{ fontWeight: 900, color: '#22d3ee' }}>
            ✨ New Records
          </div>
          <div className="text-lg font-bold text-cyan-400 mt-2 font-mono tabular-nums">
            {previewLines.filter(tx => tx.status === 'NEW').length} <span style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#0891b2', fontSize: '10px' }}>Rows</span>
          </div>
        </div>

        {/* 🚥 NEW FIELD: LIVE DUPLICATE/STALE COLLISION COUNTER */}
        <div className="bg-amber-950/20 border border-amber-800/30 rounded-lg p-3 col-span-2 sm:col-span-1" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', minWidth: '0' }}>
          <div className="text-[10px] uppercase tracking-wider truncate" style={{ fontWeight: 900, color: '#fbbf24' }}>
            ⏳ Stale / Dup
          </div>
          <div className="text-lg font-bold text-amber-400 mt-2 font-mono tabular-nums">
            {previewLines.filter(tx => tx.status === 'DUPLICATE' || tx.status === 'STALE').length} <span style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#d97706', fontSize: '10px' }}>Rows</span>
          </div>
        </div>

        {/* ADMINISTRATIVE NOTES CARD */}
        <div className="bg-zinc-900/40 border border-zinc-800 rounded-lg p-3 col-span-2 sm:col-span-1" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', minWidth: '0' }}>
          <div className="text-[10px] uppercase tracking-wider truncate" style={{ fontWeight: 900, color: '#9ca3af' }}>
            <span>📝</span> Admin Notes
          </div>
          <div className="text-lg font-bold text-amber-500 mt-2 font-mono tabular-nums">
            {responseMeta.emptyMemoLineCount} <span style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#6b7280', fontSize: '10px' }}>Row</span>
          </div>
        </div>

        {/* GLOBAL SUM TOTAL CARD */}
        <div className="bg-zinc-900/80 border border-zinc-700/60 rounded-lg p-3 shadow-inner col-span-4 sm:col-span-1" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', minWidth: '0' }}>
          <div className="text-[10px] uppercase tracking-wider truncate" style={{ fontWeight: 900, color: '#e4e4e7' }}>
            📦 Global Total
          </div>
          <div className="text-lg font-mono tabular-nums" style={{ fontWeight: 900, color: '#f3f4f6' }}>
            {previewLines.length} <span style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#a1a1aa', fontSize: '10px' }}>Total</span>
          </div>
        </div>

      </div>
    </div>

    {/* 💰 GRID LAYER 2: LEDGER ACCUMULATOR MATH COMPILER */}
    <div className="w-full block space-y-2.5">
      <div className="text-[10px] uppercase tracking-wider" style={{ fontWeight: 900, color: '#f3f4f6' }}>
        Financial Liquidity Ledger Blocks
      </div>
      
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))', gap: '12px', width: '100%' }}>
        
        {/* OPENING BASE */}
        <div className="bg-zinc-900/20 border border-zinc-800 rounded-lg p-3.5 min-w-0">
          <div className="text-[12px] uppercase tracking-wider truncate" style={{ fontWeight: 900, color: '#f3f4f6' }}>Opening Balance</div>
          <div style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#6b7280', fontSize: '11px', letterSpacing: '0.05em', marginTop: '4px' }}>Baseline Anchor</div>
          <div className="text-sm font-bold text-zinc-200 mt-1 font-mono tabular-nums truncate">
            ₹{opening?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </div>
        </div>

        {/* TOTAL DEBITS */}
        <div className="bg-zinc-900/20 border border-zinc-800 rounded-lg p-3.5 min-w-0">
          <div className="text-[12px] text-red-400 uppercase tracking-wider truncate" style={{ fontWeight: 900 }}>Total Debits (-)</div>
          <div style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#ef4444', opacity: 0.5, fontSize: '11px', letterSpacing: '0.05em', marginTop: '4px' }}>Cash Vol Outflow</div>
          <div className="text-sm font-bold text-red-400 mt-1 font-mono tabular-nums truncate">
            ₹{totalDebit?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </div>
        </div>

        {/* TOTAL CREDITS */}
        <div className="bg-zinc-900/20 border border-zinc-800 rounded-lg p-3.5 min-w-0">
          <div className="text-[12px] text-emerald-400 uppercase tracking-wider truncate" style={{ fontWeight: 900 }}>Total Credits (+)</div>
          <div style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#10b981', opacity: 0.5, fontSize: '11px', letterSpacing: '0.05em', marginTop: '4px' }}>Cash Vol Inflow</div>
          <div className="text-sm font-bold text-emerald-400 mt-1 font-mono tabular-nums truncate">
            ₹{totalCredit?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </div>
        </div>

        {/* STATEMENT CLOSING */}
        <div className="bg-zinc-900/20 border border-zinc-800 rounded-lg p-3.5 min-w-0">
          <div className="text-[12px] uppercase tracking-wider truncate" style={{ fontWeight: 900, color: '#f3f4f6' }}>Statement Closing</div>
          <div style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#6b7280', fontSize: '11px', letterSpacing: '0.05em', marginTop: '4px' }}>Document Target</div>
          <div className="text-sm font-bold text-zinc-200 mt-1 font-mono tabular-nums truncate">
            ₹{statementClosing?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </div>
        </div>

        {/* COMPUTED RUN */}
        <div className="bg-zinc-900/20 border border-zinc-800 rounded-lg p-3.5 min-w-0">
          <div className="text-[10px] text-cyan-400 uppercase tracking-wider truncate" style={{ fontWeight: 900 }}>Computed Run</div>
          <div style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#06b6d4', opacity: 0.5, fontSize: '9px', letterSpacing: '0.05em', marginTop: '4px' }}>Calculated Result</div>
          <div className="text-sm font-bold text-cyan-400 mt-1 font-mono tabular-nums truncate">
            ₹{calculatedClosingValue?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </div>
        </div>
      </div>
    </div>

    {/* 🚥 SAFETY SECURITY AUDIT CHECK PANEL */}
    <div className="w-full p-4 rounded-lg border flex flex-col sm:flex-row items-center justify-between gap-4 text-[10px] font-bold tracking-wider"
         style={{ 
           backgroundColor: isDoubleTrustOk ? 'rgba(16, 185, 129, 0.05)' : 'rgba(239, 68, 68, 0.05)',
           borderColor: isDoubleTrustOk ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)',
           color: isDoubleTrustOk ? '#34d399' : '#f87171',
           display: 'flex'
         }}>
      <div className="flex items-center gap-2 uppercase shrink-0" style={{ color: '#f3f4f6' }}>
        <span className="text-xs">🛡️</span> Security Pipeline Verification Status:
      </div>
      <div className="flex flex-row flex-wrap gap-2 justify-end w-full sm:w-auto" style={{ display: 'flex' }}>
        <span className="px-2.5 py-1 rounded border uppercase font-mono font-bold tracking-wide shadow-sm"
              style={{ backgroundColor: isBalanceVerified ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)', borderColor: isBalanceVerified ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)' }}>
          {isBalanceVerified ? "🟢 Balance: MATCHED" : isFileFullyStale ? "⏳ RE-PARSE" : "🔴 Balance: DRIFTED"}
        </span>
        <span className="px-2.5 py-1 rounded border uppercase font-mono font-bold tracking-wide shadow-sm"
              style={{ backgroundColor: isRowCountVerified ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)', borderColor: isRowCountVerified ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)' }}>
          {isRowCountVerified ? `🟢 Parsing: ${previewLines.length} Rows Whole` : "🔴 SIZE MISMATCH"}
        </span>
      </div>
    </div>

  </div>
)}


      <br/>
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
        <div className="xl:col-span-4 p-5 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl space-y-4">
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Target Bank Account</label>
              <select value={selectedAccountId} onChange={(e) => setSelectedAccountId(e.target.value)} className="w-full px-4 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-emerald-500">
                <option value="">-- Select Target Account Channel --</option>
                {accounts.map((acc) => <option key={acc.id} value={acc.id}>{acc.name} {acc.account_number ? `(•••• ${acc.account_number})` : ''}</option>)}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Parsing Engine Execution Blueprint</label>
              <select value={forcedTemplateId} onChange={(e) => setForcedTemplateId(e.target.value)} className="w-full px-4 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-xs text-emerald-400 font-mono focus:outline-none focus:border-emerald-500">
                <option value="">⚡ [AUTOMATED ENGINE ROUTING MODE]</option>
                {availableTemplates.map((t) => <option key={t.id} value={t.id}>⚙️ {t.template_name}</option>)}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Statement Document (PDF or CSV)</label>
              <div onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop} className={`border-2 border-dashed rounded-xl p-6 text-center transition-all ${isDragging ? 'border-emerald-500 bg-emerald-500/5' : 'border-zinc-800 bg-zinc-950/40 hover:border-zinc-700'}`}>
                <input type="file" id="uniFileInput" className="w-full text-xs text-zinc-400 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-mono file:font-semibold file:bg-zinc-800 file:text-emerald-400 hover:file:bg-zinc-700 cursor-pointer" accept=".csv,.pdf" onChange={handleFileChange} />
                <p className="text-[11px] text-zinc-500 mt-2 font-mono">Or drop file into box area wrapper.</p>
              </div>
            </div>

            {errorMsg && <div className="p-3 bg-red-500/10 text-red-400 text-xs border border-red-500/20 rounded-lg">⚠️ {errorMsg}</div>}
            
            {loading && (
              <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-lg text-xs font-mono font-bold animate-pulse text-center">
                ⏳ Processing Multi-Page Matrix Stream...
              </div>
            )}
          </div>
        </div>

        <div className="xl:col-span-8 p-5 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl min-h-[440px] flex flex-col">
         {/* <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-zinc-800 gap-4 mb-4">
            <div><h3 className="text-base font-semibold text-white">Persistent Workspace Staging Floor (9-Column Review Deck)</h3></div>
            {previewLines.length > 0 && (
              <button type="button" onClick={handleCommitStaging} disabled={commitLoading} className="bg-emerald-600 border border-emerald-500 hover:bg-emerald-500 text-white font-mono font-bold text-xs uppercase px-4 py-2 rounded-lg shadow-md transition-all">
                {commitLoading ? 'Saving Ledger Run...' : '🔒 Save Reconciled Statement'}
              </button>
            )}
          </div> */}

          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-zinc-800 gap-4 mb-4">
            <div><h3 className="text-base font-semibold text-white">Persistent Workspace Staging Floor (9-Column Review Deck)</h3></div>
            
            {previewLines.length > 0 && (
              <div className="flex items-center gap-3">
                {/* 📊 NEW UTILITY: EXPORT INTERMEDIATE CSV RUN FOR MANUAL TOOLING */}
                <button 
                  type="button" 
                  onClick={() => 
                        downloadWorkableCSV(
                          (window as any).__lastRawStream || "", 
                          // (window as any).__lastExportFilename || "statement_export.csv"
                        )
                      }
                  className="bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-emerald-400 font-mono font-bold text-xs uppercase px-4 py-2 rounded-lg shadow-md transition-all"
                >
                  📥 Export Workable CSV
                </button>

                <button type="button" onClick={handleCommitStaging} disabled={commitLoading} className="bg-emerald-600 border border-emerald-500 hover:bg-emerald-500 text-white font-mono font-bold text-xs uppercase px-4 py-2 rounded-lg shadow-md transition-all">
                  {commitLoading ? 'Saving Ledger Run...' : '🔒 Save Reconciled Statement'}
                </button>
              </div>
            )}
          </div>


          {previewLines.length === 0 ? (
            <div className="flex-1 flex items-center justify-center p-12 text-center text-sm text-zinc-500 border border-dashed border-zinc-800 rounded-lg">No active 9-column entries extracted into staging floor yet.</div>
          ) : (
            <div className="overflow-x-auto w-full max-h-[600px]">
              <table className="w-full text-left text-xs text-zinc-300 table-fixed border-collapse" style={{ minWidth: "1100px" }}>
                <thead className="sticky top-0 bg-zinc-900 z-10 shadow-md">
                  <tr className="border-b border-zinc-800 text-zinc-500 font-mono text-[10px] uppercase tracking-wider bg-zinc-900">
                    <th className="py-3 font-semibold" style={{ width: "9%" }}>Txn Date</th>
                    <th className="py-3 font-semibold text-orange-400" style={{ width: "9%" }}>Val Date</th>
                    <th className="py-3 font-semibold" style={{ width: "30%" }}>Narration Description</th>
                    <th className="py-3 font-semibold text-center text-indigo-400" style={{ width: "6%" }}>Type</th>
                    <th className="py-3 font-semibold text-sky-400" style={{ width: "9%" }}>Chq/Ref</th>
                    <th className="py-3 font-semibold text-right text-red-400" style={{ width: "9%" }}>Debit (-)</th>
                    <th className="py-3 font-semibold text-right text-emerald-400" style={{ width: "9%" }}>Credit (+)</th>
                    <th className="py-3 font-semibold text-right text-cyan-400" style={{ width: "9%" }}>Balance</th>
                    <th className="py-3 font-semibold text-center" style={{ width: "5%" }}>Status</th>
                  </tr>
                </thead>
                
                <tbody className="divide-y divide-zinc-800/40 font-sans">
                  {previewLines.map((line, index) => {
                    const isDuplicate = line.status === "DUPLICATE";
                    
                    const safeDebit = line.debit ?? null;
                    const safeCredit = line.credit ?? null;
                    const safeBalance = line.balance ?? line.amount ?? 0;

                    return (
                      <tr 
                        key={line.id || index} 
                        className={`transition-colors border-b border-zinc-800/30 ${
                          isDuplicate 
                            ? 'bg-zinc-950/20 text-zinc-500 hover:bg-zinc-950/30 border-l-2 border-zinc-700' 
                            : 'hover:bg-zinc-950/40 text-zinc-300'
                        }`}
                        style={{ 
                          opacity: isDuplicate ? 0.65 : 1,
                          contentVisibility: 'auto', // 🚀 NATIVE CSS VIRTUAL DOM OPTIMIZATION
                          containIntrinsicSize: 'auto 45px'
                        }}
                      >
                        <td className="py-3 font-mono text-zinc-400 align-top">{line.post_date}</td>
                        <td className="py-3 font-mono text-orange-400/80 align-top">{line.value_date || '-'}</td>
                        
                        <td className="py-3 font-medium pr-4 align-top leading-relaxed text-[12px]">
                          <div className="flex flex-wrap items-center gap-1.5 mb-1">
                            {line.tran_type && (
                              <span className="px-1 py-0.5 bg-zinc-800 text-zinc-400 border border-zinc-700/50 font-mono text-[9px] rounded uppercase font-bold tracking-wider shadow-inner">
                                {line.tran_type}
                              </span>
                            )}
                          </div>
                          <span className={isDuplicate ? 'text-zinc-600 line-through decoration-zinc-800/60' : 'text-zinc-200'}>
                            {line.narration_description}
                          </span>
                        </td>

                        <td className="py-3 text-center align-top">
                          {line.tran_type ? <span className="px-1 py-0.5 bg-zinc-800 border border-zinc-700 text-indigo-300 text-[8px] font-bold rounded uppercase">{line.tran_type}</span> : '-'}
                        </td>

                        <td className="py-3 font-mono text-sky-400 align-top truncate">
                          {line.chq_ref ? (
                            <span className="px-1 py-0.5 bg-sky-950/40 text-sky-400 border border-sky-900/30 text-[9px] rounded font-bold tracking-wider">
                              {line.chq_ref}
                            </span>
                          ) : '-'}
                        </td>

                        <td className={`py-3 text-right font-mono font-bold align-top text-[13px] ${isDuplicate ? 'text-zinc-800' : 'text-red-400'}`}>
                          {safeDebit !== null ? `₹${safeDebit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : <span className="text-zinc-800 opacity-40 font-normal">-</span>}
                        </td>

                        <td className={`py-3 text-right font-mono font-bold align-top text-[13px] ${isDuplicate ? 'text-zinc-800' : 'text-emerald-400'}`}>
                          {safeCredit !== null ? `₹${safeCredit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : <span className="text-zinc-800 opacity-40 font-normal">-</span>}
                        </td>

                        <td className="py-3 text-right font-mono font-bold align-top text-[13px] text-cyan-400/90">
                          ₹{safeBalance.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>

                        <td className="py-3 text-center align-top font-mono font-bold text-[10px] tracking-wider select-none">
                          {isDuplicate ? (
                            <span className="text-zinc-600 uppercase">STALE</span>
                          ) : (
                            <span className="text-emerald-400 uppercase drop-shadow-[0_0_6px_rgba(52,211,153,0.2)]">NEW</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}