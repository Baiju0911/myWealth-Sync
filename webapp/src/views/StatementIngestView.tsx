import React, { useState, useEffect } from 'react';
import { accountApi } from '../api.ts';
import api from '../api/client';
import { type AccountEntity } from '../types/ledger';

interface StagingPreviewLine {
  id: string;
  date: string;
  description: string;
  tran_type?: string;     
  cheque_ref?: string;    
  credit: number | null;
  debit: number | null;
  amount: number;
  status: string;
  Hex: string;
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

export default function StatementIngestView() {
  // ─── 1. LIFE-CYCLE HOOKS ───
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

  useEffect(() => {
    accountApi.getAccounts()
      .then(res => setAccounts(Array.isArray(res) ? res : res.results || []))
      .catch(() => setErrorMsg('Failed loading ledger workspace nodes.'));
  }, []);

  // ─── 2. DRAG AND DROP HANDLERS ───
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  // ─── 3. PIPELINE SERVICE ACTIONS ───
  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !selectedAccountId) {
      setErrorMsg('Please select a ledger account and drop a statement file.');
      return;
    }

    setLoading(true);
    setErrorMsg('');
    setCommitSuccessMsg('');
    setPreviewLines([]);
    setResponseMeta(null);

    const formData = new FormData();
    formData.append('statement_file', file);
    formData.append('account_id', selectedAccountId);

    try {
      const res = await api.post('/statement/ingest/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      if (res.data.status === 'SUCCESS') {
        setPreviewLines(res.data.preview_dataset || []);
        setResponseMeta({
          fileType: res.data.file_type || 'UNKNOWN',
          decrypted: res.data.decrypted || false,
          count: res.data.count || 0,
          openingBalance: res.data.opening_balance || 0,
          closingBalance: res.data.closing_balance || 0,
          totalDebit: res.data.total_debit || 0,
          totalCredit: res.data.total_credit || 0,
          rawMatchCount: res.data.raw_match_count || 0,
          debitLineCount: res.data.debit_line_count || 0,
          creditLineCount: res.data.credit_line_count || 0,
          duplicateCount: res.data.duplicate_count || 0, 
          report_from_date: res.data.report_from_date || null,
          report_to_date: res.data.report_to_date || null,
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
    if (isFileFullyStale) {
      setCommitSuccessMsg("Statement verified. All records are already reconciled in your history!");
      setPreviewLines([]);
      setResponseMeta(null);
      setFile(null);
      return;
    }
    setCommitLoading(true);
    const payloadBuffer = [...previewLines];
    const targetFileName = file ? file.name : "UNKNOWN_STATEMENT.PDF";

    try {
      const res = await api.post('/statement/commit-staging/', {
        account_id: selectedAccountId,
        preview_dataset: payloadBuffer,
        file_name: targetFileName, 
        meta_summary: responseMeta, 
        report_from_date: responseMeta?.report_from_date,
        report_to_date: responseMeta?.report_to_date,
      });

      if (res.data.status === 'SUCCESS') {
        setCommitSuccessMsg(res.data.message);
        setPreviewLines([]);
        setResponseMeta(null);
        setFile(null);
      }
    } catch (err: any) {
      console.error(err);
      setErrorMsg(err.response?.data?.message || 'Database commit processing breakdown.');
    } finally {
      setCommitLoading(false);
    }
  };

  // ─── 4. METRICS HARMONIZATION MATRIX ───
  const opening = responseMeta?.openingBalance || 0;
  const totalCredit = responseMeta?.totalCredit || 0;
  const totalDebit = responseMeta?.totalDebit || 0;
  const statementClosing = responseMeta?.closingBalance || 0;

  const drLineCount = responseMeta?.debitLineCount || 0;
  const crLineCount = responseMeta?.creditLineCount || 0;

  const calculatedClosingValue = opening + totalCredit - totalDebit;
  const isBalanceVerified = responseMeta ? Math.abs(calculatedClosingValue - statementClosing) < 0.01 : false;

  const backendRawCount = responseMeta?.rawMatchCount || 0;
  const frontendRenderCount = previewLines.length;
  
  const isRowCountVerified = responseMeta ? (backendRawCount === frontendRenderCount) : false;
  
  const totalDuplicates = previewLines.filter(l => l.status === "DUPLICATE").length;
  const isFileFullyStale = previewLines.length > 0 && totalDuplicates === previewLines.length;
  const isDoubleTrustOk = isBalanceVerified || isFileFullyStale;

  return (
    <div className="space-y-8 animate-fade-in text-white p-2 text-left">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Adaptive Ingestion Pipeline</h2>
        <p className="text-sm text-zinc-400 mt-1">Stream parsing engines directly into persistent database staging workspaces.</p>
      </div>

      {commitSuccessMsg && (
        <div className="p-4 bg-emerald-500/10 text-emerald-400 text-sm border border-emerald-500/20 rounded-xl font-medium animate-fade-in shadow-lg">
          {commitSuccessMsg}
        </div>
      )}

      {/* 📊 SECTION I: THE LIVE HEADER CARD ROW */}
      {responseMeta && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 animate-fade-in">
          {/* Opening Balance */}
          <div className="bg-zinc-900 border border-zinc-800 p-4 rounded-xl shadow-md">
            <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 font-bold">Opening Balance</div>
            <div className="text-lg font-mono font-bold text-zinc-200 mt-1">
              ₹{opening.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>

          {/* Total Debits */}
          <div className="bg-zinc-900 border border-zinc-800 p-4 rounded-xl shadow-md">
            <div className="flex justify-between items-start">
              <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 font-bold">Total Debits</div>
              <span className="text-[10px] font-mono font-bold text-red-400 bg-red-500/10 px-1.5 py-0.5 rounded">
                {drLineCount} rows
              </span>
            </div>
            <div className="text-lg font-mono font-bold text-red-400 mt-1">
              ₹{totalDebit.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>

          {/* Total Credits */}
          <div className="bg-zinc-900 border border-zinc-800 p-4 rounded-xl shadow-md">
            <div className="flex justify-between items-start">
              <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 font-bold">Total Credits</div>
              <span className="text-[10px] font-mono font-bold text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded">
                {crLineCount} rows
              </span>
            </div>
            <div className="text-lg font-mono font-bold text-emerald-400 mt-1">
              ₹{totalCredit.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>

          {/* Statement Closing */}
          <div className="bg-zinc-900 border border-zinc-800 p-4 rounded-xl shadow-md">
            <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 font-bold">Statement Closing</div>
            <div className="text-lg font-mono font-bold text-zinc-200 mt-1">
              ₹{statementClosing.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>

          {/* Double-Trust Status Shield */}
          <div className={`p-4 rounded-xl border flex flex-col justify-center shadow-md transition-all ${
            isDoubleTrustOk 
              ? 'bg-emerald-950/30 border-emerald-500/40 text-emerald-400' 
              : 'bg-rose-950/20 border-rose-800/40 text-rose-400'
          }`}>
            <div className="text-[10px] font-mono uppercase tracking-wider opacity-60 font-bold">Double-Trust Security</div>
            <div className="mt-2 space-y-0.5">
              <div className="text-[11px] font-bold flex items-center gap-1.5">
                {isBalanceVerified ? "🟢 Balance Math: MATCH" : isFileFullyStale ? "🟡 History Run: RE-PARSE" : "🔴 Balance Math: DRIFT"}
              </div>
              <div className="text-[11px] font-bold flex items-center gap-1.5">
                {isRowCountVerified ? `🟢 File Analysis: ${frontendRenderCount} Rows` : "🔴 Row Integrity: MISMATCH"}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION II: OPERATIONS WORKSPACE PANEL */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-8 items-start">
        {/* Left Card: Input Panel */}
        <div className="xl:col-span-4 p-6 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl space-y-6">
          <form onSubmit={handleUploadSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Target Bank Account</label>
              <select
                value={selectedAccountId}
                onChange={(e) => setSelectedAccountId(e.target.value)}
                className="w-full px-4 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-emerald-500 transition-colors"
                disabled={loading}
              >
                <option value="">-- Select Target Account Channel --</option>
                {accounts.map((acc) => (
                  <option key={acc.id} value={acc.id}>
                    {acc.name} {acc.account_number ? `(•••• ${acc.account_number})` : ''}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Statement Document (PDF or CSV)</label>
              <input
                type="file"
                id="fileInput"
                className="hidden"
                accept=".csv,.pdf"
                onChange={handleFileChange}
                disabled={loading}
              />
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => document.getElementById('fileInput')?.click()}
                className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
                  isDragging ? 'border-emerald-500 bg-emerald-500/5' : 'border-zinc-800 bg-zinc-950/40 hover:border-zinc-700'
                }`}
              >
                <div className="text-zinc-400 text-sm">
                  {file ? (
                    <span>
                      📄 <span className="text-emerald-400 font-semibold font-mono break-all">{file.name}</span>
                    </span>
                  ) : (
                    'Drag and drop statement file here or click to browse'
                  )}
                </div>
              </div>
            </div>

            {errorMsg && (
              <div className="p-3 bg-red-500/10 text-red-400 text-xs border border-red-500/20 rounded-lg font-semibold">
                ⚠️ {errorMsg}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !file || !selectedAccountId}
              className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:bg-zinc-800 disabled:text-zinc-500 text-white font-medium text-sm rounded-lg shadow-lg transition-all"
            >
              {loading ? 'Processing Decryption & Parsing...' : 'Run Extraction Engine'}
            </button>
          </form>

          {responseMeta && (
            <div className="p-4 bg-zinc-950 border border-zinc-800 rounded-lg space-y-2 text-xs font-mono">
              <div className="text-zinc-400 font-bold border-b border-zinc-800 pb-1.5 uppercase">Parsing Context Metrics</div>
              <div>Engine Match: <span className="text-emerald-400 font-bold">{responseMeta.fileType} Pipeline</span></div>
              <div>Vault Decryption: <span className={responseMeta.decrypted ? "text-emerald-400 font-bold" : "text-zinc-500"}>{responseMeta.decrypted ? "PASSED (Unlocked via Vault)" : "NONE (No pass needed)"}</span></div>
              <div>Staged Rows: <span className="text-sky-400 font-bold">{responseMeta.count} records loaded</span></div>
              
              <div className="pt-1.5 border-t border-zinc-800/60 mt-1 flex justify-between">
                <span className="text-zinc-500">Stale Duplicates:</span>
                <span className={`font-bold ${responseMeta.duplicateCount > 0 ? 'text-amber-400 animate-pulse' : 'text-zinc-400'}`}>
                  {responseMeta.duplicateCount} records skipped
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Right Card: Live Staging Floor Deck */}
        <div className="xl:col-span-8 p-6 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl min-h-[440px] flex flex-col">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-zinc-800 gap-4 mb-6">
            <div>
              <h3 className="text-base font-semibold text-white">
                Persistent Workspace Staging Floor (Review Deck)
              </h3>
              <p className="text-xs text-zinc-400 mt-0.5">Audit data lines manually below before triggering the system commit save.</p>
            </div>
            
            {previewLines.length > 0 && (
              <button
                type="button"
                onClick={handleCommitStaging}
                disabled={commitLoading || !isDoubleTrustOk}
                className={`node-submit px-4 py-2 text-xs font-mono font-bold uppercase rounded-lg border tracking-wider transition-all shadow-md flex items-center justify-center min-w-[190px] ${
                  isDoubleTrustOk
                    ? isFileFullyStale 
                      ? 'bg-zinc-800 border-zinc-700 hover:bg-zinc-700 text-zinc-300 cursor-pointer'
                      : 'bg-emerald-600 border-emerald-500 hover:bg-emerald-500 text-white active:scale-[0.98] cursor-pointer'
                    : 'bg-zinc-800 border-zinc-700 text-zinc-500 cursor-not-allowed'
                }`}
              >
                {commitLoading ? (
                  <span>Saving Ledger Run...</span>
                ) : isFileFullyStale ? (
                  <span>⏭️ Skip Upload (Stale)</span>
                ) : isDoubleTrustOk ? (
                  <span>🔒 Save Reconciled Statement</span>
                ) : (
                  <span>⚠️ Balance Drift Locked</span>
                )}
              </button>
            )}
          </div>

          {previewLines.length === 0 ? (
            <div className="flex-1 flex items-center justify-center p-16 text-center text-sm text-zinc-500 border border-dashed border-zinc-800 rounded-lg">
              No active statement line entries extracted into the workspace staging layer yet. Choose parameters and activate the parser engine.
            </div>
          ) : (
            <div className="overflow-x-auto w-full">
              {/* Enforced table layout structural fix to support column alignment */}
              <table className="w-full text-left text-xs text-zinc-300 table-fixed border-collapse" style={{ minWidth: "850px" }}>
                <thead>
                  <tr className="border-b border-zinc-800 text-zinc-500 font-mono text-[11px] uppercase tracking-wider">
                    <th className="pb-3 font-semibold" style={{ width: "12%" }}>Txn Date</th>
                    <th className="pb-3 font-semibold" style={{ width: "38%" }}>Narration Description</th>
                    <th className="pb-3 font-semibold text-right text-red-400" style={{ width: "12%" }}>Debit (-)</th>
                    <th className="pb-3 font-semibold text-right text-emerald-400" style={{ width: "12%" }}>Credit (+)</th>
                    <th className="pb-3 font-semibold text-right text-cyan-400" style={{ width: "12%" }}>Balance</th>
                    <th className="pb-3 font-semibold text-center text-zinc-400" style={{ width: "6%" }}>Hex</th>
                    <th className="pb-3 font-semibold text-center" style={{ width: "8%" }}>Status</th>
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
                        <td className="py-3 font-mono text-zinc-400 align-top">{line.date}</td>
                        
                        <td className="py-3 font-medium pr-4 align-top leading-relaxed text-[12px]">
                          <div className="flex flex-wrap items-center gap-1.5 mb-1">
                            {line.tran_type && (
                              <span className="px-1 py-0.5 bg-zinc-800 text-zinc-400 border border-zinc-700/50 font-mono text-[9px] rounded uppercase font-bold tracking-wider shadow-inner">
                                {line.tran_type}
                              </span>
                            )}
                            {line.cheque_ref && (
                              <span className="px-1 py-0.5 bg-sky-950/40 text-sky-400 border border-sky-900/30 font-mono text-[9px] rounded font-bold tracking-wider">
                                REF:{line.cheque_ref}
                              </span>
                            )}
                          </div>
                          <span className={isDuplicate ? 'text-zinc-600 line-through decoration-zinc-800/60' : 'text-zinc-200'}>
                            {line.description}
                          </span>
                        </td>

                        <td className={`py-3 text-right font-mono font-bold align-top text-[13px] ${isDuplicate ? 'text-zinc-800' : 'text-red-400'}`}>
                          {line.debit ? `₹${line.debit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : <span className="text-zinc-800 opacity-40 font-normal">-</span>}
                        </td>
                        <td className={`py-3 text-right font-mono font-bold align-top text-[13px] ${isDuplicate ? 'text-zinc-800' : 'text-emerald-400'}`}>
                          {line.credit ? `₹${line.credit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : <span className="text-zinc-800 opacity-40 font-normal">-</span>}
                        </td>
                        <td className={`py-3 text-right font-mono font-bold align-top text-[13px] text-cyan-400/90`}>
                          ₹{line.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>
                        <td className="py-3 text-center font-mono text-zinc-500 align-top text-[11px]">
                          {line.Hex ? <span className="bg-zinc-950 px-1 py-0.5 rounded border border-zinc-800/80 text-zinc-400">{line.Hex}</span> : <span className="text-zinc-800 opacity-30">-</span>}
                        </td>

                        <td className="py-3 text-center align-top">
                          {isDuplicate ? (
                            <span className="px-1.5 py-0.5 bg-zinc-800/80 text-zinc-500 border border-zinc-700/30 rounded font-mono text-[8px] font-bold inline-block uppercase tracking-wider">
                              ⏭️ STALE
                            </span>
                          ) : (
                            <span className="px-1.5 py-0.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded font-mono text-[8px] font-bold inline-block uppercase tracking-wider">
                              ✅ NEW
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>

                {/* ─── 🟢 INJECTED METRICS FOOTER ACCOUNT SUMMARY BLOCK ─── */}
                <tfoot>
                  {/* Row 1: Opening Balance Summary */}
                  <tr className="bg-zinc-950/40 border-t border-zinc-800 text-[11px] font-mono text-zinc-400">
                    <td colSpan={2} className="p-3 font-bold text-zinc-500 uppercase tracking-wide text-left">Statement Opening Summary</td>
                    <td colSpan={3} className="p-3 text-right font-bold text-zinc-300 text-sm">
                      ₹{opening.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td colSpan={2} className="p-3"></td>
                  </tr>

                  {/* Row 2: Live Accumulated Transaction Volume Runs */}
                  <tr className="bg-zinc-950/20 text-[11px] font-mono border-t border-zinc-800/50">
                    <td colSpan={2} className="p-3 font-bold text-zinc-500 uppercase tracking-wide text-left">Total Segment Changes Vol ({previewLines.length} rows)</td>
                    <td className="p-3 text-right font-bold text-red-400 text-xs">
                      -₹{totalDebit.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className="p-3 text-right font-bold text-emerald-400 text-xs">
                      +₹{totalCredit.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td colSpan={3} className="p-3"></td>
                  </tr>

                  {/* Row 3: Final Closing Balance Comparison Deck */}
                  <tr className="bg-zinc-950/60 border-t-2 border-zinc-800 text-[11px] font-mono">
                    <td colSpan={2} className="p-3 font-bold text-zinc-400 uppercase tracking-wide text-left">Computed Closing Balance Run</td>
                    <td colSpan={3} className="p-3 text-right font-bold text-cyan-400 text-sm">
                      ₹{calculatedClosingValue.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td colSpan={2} className="p-3 text-center">
                      {isBalanceVerified ? (
                        <span className="px-2 py-0.5 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-[9px] rounded font-bold uppercase tracking-wider">
                          Verified
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 bg-rose-500/10 border border-rose-500/30 text-rose-400 text-[9px] rounded font-bold uppercase tracking-wider">
                          Drift Warning
                        </span>
                      )}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}