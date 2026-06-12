import React, { useState, useEffect } from 'react';
import { accountApi } from '../api.ts';
import api from '../api/client';
import { type AccountEntity } from '../types/ledger';

interface StagingPreviewLine {
  id: string;
  date: string;
  value_date?: string;
  narration_description: string; // 🟢 UNIFIED FROM description
  tran_type?: string;      
  chq_ref?: string;               // 🟢 UNIFIED FROM cheque_ref
  credit: number | null;
  debit: number | null;
  amount: number;
  status: string;
  Hex: string;
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
          duplicateCount: res.data.data?.duplicate_count || res.data.duplicate_count || 0, 
        });
      }
    } catch (err: any) {
      console.error(err);
      setErrorMsg(err.response?.data?.message || 'Staging engine processing failure.');
    } finally {
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
  
  const isBalanceVerified = responseMeta ? Math.abs(calculatedClosingValue - statementClosing) < 0.01 : false;
  const frontendRenderCount = previewLines.length;
  const isRowCountVerified = responseMeta ? responseMeta.count === frontendRenderCount : false;
  const isFileFullyStale = responseMeta ? responseMeta.count === 0 : false;
  const isDoubleTrustOk = isBalanceVerified && isRowCountVerified && !isFileFullyStale;

  return (
    <div className="space-y-6 animate-fade-in text-white p-2 text-left">
      <div>
        <h2 className="text-2xl font-bold tracking-tight text-emerald-400">Universal 9-Column Ingestion Pipeline</h2>
        <p className="text-sm text-zinc-400 mt-1">Dynamic coordinate tracking processor capturing 100% of rows from multi-page JPEGs/PDFs.</p>
      </div>

      {commitSuccessMsg && <div className="p-4 bg-emerald-500/10 text-emerald-400 text-sm border border-emerald-500/20 rounded-xl font-medium shadow-lg">{commitSuccessMsg}</div>}

      <br/>

      {/* 📊 Beautiful Summary Reconciliation & Double-Trust Matrix Table */}
      {responseMeta && (
        <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-4 shadow-xl overflow-x-auto animate-fade-in space-y-4">
          
          {/* 🚥 LIVE TRAFFIC LIGHT COLLISION MATRIX TABLE */}
          {(() => {
            const totalRows = previewLines.length;
            const staleCount = previewLines.filter(l => l.status === "DUPLICATE").length;
            const newCount = totalRows - staleCount;
            const isFullyStale = staleCount === totalRows;

            return (
              <div className="overflow-x-auto w-full">
                <table className="w-full text-left font-mono text-[11px] border-collapse">
                  <thead>
                    <tr className="border-b border-zinc-900 text-zinc-500 uppercase tracking-wider text-[10px]">
                      <th className="pb-2 font-medium" style={{ width: '40%' }}>Telemetry Stream Metrics</th>
                      <th className="pb-2 font-medium text-right" style={{ width: '30%' }}>Volume count</th>
                      <th className="pb-2 font-medium text-right" style={{ width: '30%' }}>Pipeline Action Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-900/40">
                    {/* Row 1: Total Volume */}
                    <tr className="hover:bg-zinc-900/20 transition-colors">
                      <td className="py-2.5 text-zinc-400 flex items-center gap-1.5">
                        <span>📦</span> TOTAL STREAMS EXTRACTED
                      </td>
                      <td className="py-2.5 text-right font-bold text-zinc-300">{totalRows}</td>
                      <td className="py-2.5 text-right text-zinc-500 text-[10px] uppercase font-bold">Processed</td>
                    </tr>

                    {/* Row 2: Net Fresh Records */}
                    <tr className={`transition-all ${newCount > 0 ? 'bg-emerald-950/5 text-emerald-400/90' : 'text-zinc-600'}`}>
                      <td className="py-2.5 flex items-center gap-1.5 font-medium">
                        <span>✨</span> NET FRESH RECORDS
                      </td>
                      <td className={`py-2.5 text-right font-bold ${newCount > 0 ? 'text-emerald-400' : 'text-zinc-600'}`}>
                        +{newCount}
                      </td>
                      <td className="py-2.5 text-right font-bold text-[10px] uppercase tracking-wider">
                        {newCount > 0 ? (
                          <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                            READY
                          </span>
                        ) : (
                          <span className="text-zinc-600">-</span>
                        )}
                      </td>
                    </tr>

                    {/* Row 3: Historical Collisions */}
                    <tr className={`transition-all ${staleCount > 0 ? 'bg-amber-950/5 text-amber-400/90' : 'text-zinc-600'}`}>
                      <td className="py-2.5 font-medium">
                        <div className="flex flex-col">
                          <div className="flex items-center gap-1.5">
                            <span>🛡️</span> HISTORICAL COLLISIONS
                          </div>
                          {isFullyStale && totalRows > 0 && (
                            <span className="text-[9px] text-amber-500/50 normal-case font-normal pl-5">
                              engine will safely pass commit run
                            </span>
                          )}
                        </div>
                      </td>
                      <td className={`py-2.5 text-right font-bold align-top ${staleCount > 0 ? 'text-amber-400' : 'text-zinc-600'}`}>
                        {staleCount}
                      </td>
                      <td className="py-2.5 text-right font-bold text-[10px] uppercase tracking-wider align-top">
                        {staleCount > 0 ? (
                          <span className="px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-500/20 text-amber-400">
                            BLOCKED
                          </span>
                        ) : (
                          <span className="text-zinc-600">-</span>
                        )}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            );
          })()}

          {/* Line Break Separation Line */}
          <div className="border-t border-zinc-800/60 my-2" />

          <div className="text-xs font-mono font-bold tracking-wider text-zinc-400 mb-3 uppercase flex items-center justify-between">
            <span>⚖️ Automated Engine Verification Summary Deck</span>
            <span className="text-[10px] text-zinc-500 normal-case font-normal">File Mode: {responseMeta.fileType}</span>
          </div>
          <table className="w-full text-left font-mono text-xs text-zinc-300 border-collapse">
            <thead>
              <tr className="border-b border-zinc-800 text-[10px] text-zinc-500 uppercase">
                <th className="py-2 font-semibold">Opening Balance</th>
                <th className="py-2 font-semibold text-red-400">Total Debits (-)</th>
                <th className="py-2 font-semibold text-emerald-400">Total Credits (+)</th>
                <th className="py-2 font-semibold">Statement Closing</th>
                <th className="py-2 font-semibold text-cyan-400">Computed Run</th>
                <th className="py-2 font-semibold text-center">Security Status Check</th>
              </tr>
            </thead>
            <tbody>
              <tr className="text-sm font-bold bg-zinc-900/30 align-top">
                {/* Opening Balance */}
                <td className="py-3 px-1 text-zinc-200">
                  <div>₹{opening.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
                  <div className="text-[10px] font-normal text-zinc-500 mt-0.5">Baseline Anchor</div>
                </td>
                
                {/* Total Debits Sum & Count */}
                <td className="py-3 text-red-400">
                  <div>₹{totalDebit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
                  <div className="text-[10px] font-mono font-normal text-red-400/60 mt-0.5">
                    📂 {responseMeta.debitLineCount} debits
                  </div>
                </td>
                
                {/* Total Credits Sum & Count */}
                <td className="py-3 text-emerald-400">
                  <div>₹{totalCredit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
                  <div className="text-[10px] font-mono font-normal text-emerald-400/60 mt-0.5">
                    📂 {responseMeta.creditLineCount} credits
                  </div>
                </td>
                
                {/* Statement Closing Balance */}
                <td className="py-3 text-zinc-200">
                  <div>₹{statementClosing.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
                  <div className="text-[10px] font-normal text-zinc-500 mt-0.5">Target Document Value</div>
                </td>
                
                {/* Computed Running Ledger Value */}
                <td className="py-3 text-cyan-400">
                  <div>₹{calculatedClosingValue.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
                  <div className="text-[10px] font-normal text-cyan-500/60 mt-0.5">Mathematical Result</div>
                </td>
                
                {/* Security Validation Status Tags */}
                <td className="py-1">
                  <div className={`mx-auto max-w-[210px] p-1.5 rounded-lg border text-center flex flex-col gap-0.5 text-[10px] uppercase font-bold tracking-wide ${
                    isDoubleTrustOk ? 'bg-emerald-950/40 border-emerald-500/30 text-emerald-400' : 'bg-rose-950/30 border-rose-800/30 text-rose-400'
                  }`}>
                    <div>{isBalanceVerified ? "🟢 Balance: MATCHED" : isFileFullyStale ? "⏳ RE-PARSE TIMELINE" : "🔴 Balance: DRIFT"}</div>
                    <div>{isRowCountVerified ? `🟢 Parsing: ${frontendRenderCount} Rows Verified` : "🔴 Integrity: MISMATCH"}</div>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      <br/>
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
        {/* Left Input Configuration Controller */}
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

        {/* Right Card Viewport Table Grid Layout */}
        <div className="xl:col-span-8 p-5 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl min-h-[440px] flex flex-col">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-zinc-800 gap-4 mb-4">
            <div><h3 className="text-base font-semibold text-white">Persistent Workspace Staging Floor (9-Column Review Deck)</h3></div>
            {previewLines.length > 0 && (
              <button type="button" onClick={handleCommitStaging} disabled={commitLoading} className="bg-emerald-600 border border-emerald-500 hover:bg-emerald-500 text-white font-mono font-bold text-xs uppercase px-4 py-2 rounded-lg shadow-md transition-all">
                {commitLoading ? 'Saving Ledger Run...' : '🔒 Save Reconciled Statement'}
              </button>
            )}
          </div>

          {previewLines.length === 0 ? (
            <div className="flex-1 flex items-center justify-center p-12 text-center text-sm text-zinc-500 border border-dashed border-zinc-800 rounded-lg">No active 9-column entries extracted into staging floor yet.</div>
          ) : (
            <div className="overflow-x-auto w-full">
              <table className="w-full text-left text-xs text-zinc-300 table-fixed border-collapse" style={{ minWidth: "1100px" }}>
                <thead>
                  <tr className="border-b border-zinc-800 text-zinc-500 font-mono text-[10px] uppercase tracking-wider">
                    {/* ─── 🟢 HEADERS UNIFIED EVERYWHERE ─── */}
                    <th className="pb-3 font-semibold" style={{ width: "9%" }}>Txn Date</th>
                    <th className="pb-3 font-semibold text-orange-400" style={{ width: "9%" }}>Val Date</th>
                    <th className="pb-3 font-semibold" style={{ width: "30%" }}>Narration Description</th>
                    <th className="pb-3 font-semibold text-center text-indigo-400" style={{ width: "6%" }}>Type</th>
                    <th className="pb-3 font-semibold text-sky-400" style={{ width: "9%" }}>Chq/Ref</th>
                    <th className="pb-3 font-semibold text-right text-red-400" style={{ width: "9%" }}>Debit (-)</th>
                    <th className="pb-3 font-semibold text-right text-emerald-400" style={{ width: "9%" }}>Credit (+)</th>
                    <th className="pb-3 font-semibold text-right text-cyan-400" style={{ width: "9%" }}>Balance</th>
                    <th className="pb-3 font-semibold text-center" style={{ width: "5%" }}>Status</th>
                  </tr>
                </thead>
                
                <tbody className="divide-y divide-zinc-800/40 font-sans">
                  {previewLines.map((line, index) => {
                    const isDuplicate = line.status === "DUPLICATE";

                    return (
                      <tr 
                        key={line.id || index} 
                        className={`transition-colors border-b border-zinc-800/30 ${
                          isDuplicate 
                            ? 'bg-zinc-950/20 text-zinc-500 hover:bg-zinc-950/30 border-l-2 border-zinc-700' 
                            : 'hover:bg-zinc-950/40 text-zinc-300'
                        }`}
                        style={{ opacity: isDuplicate ? 0.65 : 1 }}
                      >
                        {/* 1. Transaction Date */}
                        <td className="py-3 font-mono text-zinc-400 align-top">{line.date}</td>
                        
                        {/* 2. Value Date */}
                        <td className="py-3 font-mono text-orange-400/80 align-top">{line.value_date || '-'}</td>
                        
                        {/* 3. Narration Description Block */}
                        <td className="py-3 font-medium pr-4 align-top leading-relaxed text-[12px]">
                          <div className="flex flex-wrap items-center gap-1.5 mb-1">
                            {line.tran_type && (
                              <span className="px-1 py-0.5 bg-zinc-800 text-zinc-400 border border-zinc-700/50 font-mono text-[9px] rounded uppercase font-bold tracking-wider shadow-inner">
                                {line.tran_type}
                              </span>
                            )}
                          </div>
                          {/* ─── 🟢 BIND DATA TO UNIFIED FIELD STRING KEY ─── */}
                          <span className={isDuplicate ? 'text-zinc-600 line-through decoration-zinc-800/60' : 'text-zinc-200'}>
                            {line.narration_description}
                          </span>
                        </td>

                        {/* 4. Type Code */}
                        <td className="py-3 text-center align-top">
                          {line.tran_type ? <span className="px-1 py-0.5 bg-zinc-800 border border-zinc-700 text-indigo-300 text-[8px] font-bold rounded uppercase">{line.tran_type}</span> : '-'}
                        </td>

                        {/* 5. Chq/Ref Column */}
                        {/* ─── 🟢 BIND DATA TO UNIFIED FIELD STRING KEY ─── */}
                        <td className="py-3 font-mono text-sky-400 align-top truncate">
                          {line.chq_ref ? (
                            <span className="px-1 py-0.5 bg-sky-950/40 text-sky-400 border border-sky-900/30 text-[9px] rounded font-bold tracking-wider">
                              REF:{line.chq_ref}
                            </span>
                          ) : '-'}
                        </td>

                        {/* 6. Debit Value */}
                        <td className={`py-3 text-right font-mono font-bold align-top text-[13px] ${isDuplicate ? 'text-zinc-800' : 'text-red-400'}`}>
                          {line.debit ? `₹${line.debit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : <span className="text-zinc-800 opacity-40 font-normal">-</span>}
                        </td>

                        {/* 7. Credit Value */}
                        <td className={`py-3 text-right font-mono font-bold align-top text-[13px] ${isDuplicate ? 'text-zinc-800' : 'text-emerald-400'}`}>
                          {line.credit ? `₹${line.credit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : <span className="text-zinc-800 opacity-40 font-normal">-</span>}
                        </td>

                        {/* 8. Running Balance */}
                        <td className="py-3 text-right font-mono font-bold align-top text-[13px] text-cyan-400/90">
                          ₹{line.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>

                        {/* 9. Live Status Flag Badge Component */}
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