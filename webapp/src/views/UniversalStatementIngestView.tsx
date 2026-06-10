import React, { useState, useEffect } from 'react';
import { accountApi } from '../api.ts';
import api from '../api/client';
import { type AccountEntity } from '../types/ledger';


interface StagingPreviewLine {
  id: string;
  date: string;
  value_date?: string; // 🟢 Added for 9-Col contract
  description: string;
  tran_type?: string;     
  cheque_ref?: string;    
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

interface IngestionNodeProps {
  onRedirectToMapper?: () => void;
}

export default function UniversalStatementIngestView()  {
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

  // 🟢 NEW: Override Template Pool Tracking
  const [availableTemplates, setAvailableTemplates] = useState<TemplateMetadata[]>([]);
  const [forcedTemplateId, setForcedTemplateId] = useState<string>('');

  useEffect(() => {
    accountApi.getAccounts()
      .then(res => setAccounts(Array.isArray(res) ? res : res.results || []))
      .catch(() => setErrorMsg('Failed loading ledger workspace nodes.'));

    // Fetch blueprints dropdown pool
    api.get('/statements/available/')
      .then((res) => setAvailableTemplates(res.data || []))
      .catch((err) => console.error("Failed loading configuration maps:", err));
  }, []);

  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = () => setIsDragging(false);
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]);
  };
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) setFile(e.target.files[0]);
  };

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
    if (forcedTemplateId) {
      formData.append('forced_template_id', forcedTemplateId);
    }

    try {
      // 🚀 Hits our brand new high-capacity multi-page production endpoint view
      const res = await api.post('/statement/ingestbulk/', formData, {
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

  return (
    <div className="space-y-8 animate-fade-in text-white p-2 text-left">
      <div>
        <h2 className="text-2xl font-bold tracking-tight text-emerald-400">Universal 9-Column Ingestion Pipeline</h2>
        <p className="text-sm text-zinc-400 mt-1">Dynamic coordinate tracking processor capturing 100% of rows from multi-page JPEGs/PDFs.</p>
      </div>

      {commitSuccessMsg && <div className="p-4 bg-emerald-500/10 text-emerald-400 text-sm border border-emerald-500/20 rounded-xl font-medium shadow-lg">{commitSuccessMsg}</div>}

      {/* Live Balance Summary Metrics */}
      {responseMeta && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 animate-fade-in">
          <div className="bg-zinc-900 border border-zinc-800 p-4 rounded-xl">
            <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 font-bold">Opening Balance</div>
            <div className="text-lg font-mono font-bold text-zinc-200 mt-1">₹{opening.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 p-4 rounded-xl">
            <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 font-bold">Total Debits</div>
            <div className="text-lg font-mono font-bold text-red-400 mt-1">₹{totalDebit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 p-4 rounded-xl">
            <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 font-bold">Total Credits</div>
            <div className="text-lg font-mono font-bold text-emerald-400 mt-1">₹{totalCredit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 p-4 rounded-xl">
            <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 font-bold">Statement Closing</div>
            <div className="text-lg font-mono font-bold text-zinc-200 mt-1">₹{statementClosing.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
          </div>
          <div className={`p-4 rounded-xl border flex flex-col justify-center font-mono text-[11px] font-bold ${isBalanceVerified ? 'bg-emerald-950/30 border-emerald-500/40 text-emerald-400' : 'bg-rose-950/20 border-rose-800/40 text-rose-400'}`}>
            <div>{isBalanceVerified ? "🟢 BALANCE VERIFIED" : "🔴 BALANCE DRIFT DETECTED"}</div>
            <div className="text-zinc-500 text-[10px] mt-1">Parsed Rows: {previewLines.length}</div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-8 items-start">
        {/* Left Input Control Dashboard */}
        <div className="xl:col-span-4 p-6 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl space-y-4">
          <form onSubmit={handleUploadSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Target Bank Account</label>
              <select value={selectedAccountId} onChange={(e) => setSelectedAccountId(e.target.value)} className="w-full px-4 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-emerald-500">
                <option value="">-- Select Target Account Channel --</option>
                {accounts.map((acc) => <option key={acc.id} value={acc.id}>{acc.name} {acc.account_number ? `(•••• ${acc.account_number})` : ''}</option>)}
              </select>
            </div>

            {/* Manual Blueprint Selection Override Option */}
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Parsing Engine Execution Blueprint</label>
              <select value={forcedTemplateId} onChange={(e) => setForcedTemplateId(e.target.value)} className="w-full px-4 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-xs text-emerald-400 font-mono focus:outline-none focus:border-emerald-500">
                <option value="">⚡ [AUTOMATED ENGINE ROUTING MODE]</option>
                {availableTemplates.map((t) => <option key={t.id} value={t.id}>⚙️ {t.template_name}</option>)}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Statement Document (PDF or CSV)</label>
              <div onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop} onClick={() => document.getElementById('uniFileInput')?.click()} className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${isDragging ? 'border-emerald-500 bg-emerald-500/5' : 'border-zinc-800 bg-zinc-950/40 hover:border-zinc-700'}`}>
                <input type="file" id="uniFileInput" className="hidden" accept=".csv,.pdf" onChange={handleFileChange} />
                <div className="text-zinc-400 text-sm">{file ? <span>📄 <span className="text-emerald-400 font-semibold font-mono break-all">{file.name}</span></span> : 'Drag and drop file here or click to browse'}</div>
              </div>
            </div>

            {errorMsg && <div className="p-3 bg-red-500/10 text-red-400 text-xs border border-red-500/20 rounded-lg">⚠️ {errorMsg}</div>}

            <button type="submit" disabled={loading || !file || !selectedAccountId} className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:bg-zinc-800 text-white font-medium text-sm rounded-lg shadow-lg transition-all">
              {loading ? 'Processing Multi-Page Matrix...' : 'Run Universal Extraction'}
            </button>
          </form>
        </div>

        {/* Right Card Viewport Grid */}
        <div className="xl:col-span-8 p-6 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl min-h-[440px] flex flex-col">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-zinc-800 gap-4 mb-6">
            <div><h3 className="text-base font-semibold text-white">Persistent Workspace Staging Floor (9-Column Review Deck)</h3></div>
            {previewLines.length > 0 && (
              <button type="button" onClick={handleCommitStaging} disabled={commitLoading} className="bg-emerald-600 border border-emerald-500 hover:bg-emerald-500 text-white font-mono font-bold text-xs uppercase px-4 py-2 rounded-lg shadow-md transition-all">
                {commitLoading ? 'Saving Ledger Run...' : '🔒 Save Reconciled Statement'}
              </button>
            )}
          </div>

          {previewLines.length === 0 ? (
            <div className="flex-1 flex items-center justify-center p-16 text-center text-sm text-zinc-500 border border-dashed border-zinc-800 rounded-lg">No active 9-column entries extracted into staging floor yet.</div>
          ) : (
            <div className="overflow-x-auto w-full">
              <table className="w-full text-left text-xs text-zinc-300 table-fixed border-collapse" style={{ minWidth: "1000px" }}>
                <thead>
                  <tr className="border-b border-zinc-800 text-zinc-500 font-mono text-[10px] uppercase tracking-wider">
                    <th className="pb-3 font-semibold" style={{ width: "10%" }}>Txn Date</th>
                    <th className="pb-3 font-semibold text-orange-400" style={{ width: "10%" }}>Val Date</th>
                    <th className="pb-3 font-semibold" style={{ width: "34%" }}>Narration Description</th>
                    <th className="pb-3 font-semibold text-center text-indigo-400" style={{ width: "6%" }}>Type</th>
                    <th className="pb-3 font-semibold text-sky-400" style={{ width: "10%" }}>Chq/Ref</th>
                    <th className="pb-3 font-semibold text-right text-red-400" style={{ width: "10%" }}>Debit (-)</th>
                    <th className="pb-3 font-semibold text-right text-emerald-400" style={{ width: "10%" }}>Credit (+)</th>
                    <th className="pb-3 font-semibold text-right text-cyan-400" style={{ width: "10%" }}>Balance</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/30">
                  {previewLines.map((line, index) => (
                    <tr key={index} className="hover:bg-zinc-950/40 text-zinc-300">
                      <td className="py-3 font-mono text-zinc-400">{line.date}</td>
                      <td className="py-3 font-mono text-orange-400/80">{line.value_date || '-'}</td>
                      <td className="py-3 text-[12px] font-medium pr-2 truncate" title={line.description}>{line.description}</td>
                      <td className="py-3 text-center">
                        {line.tran_type ? <span className="px-1 py-0.5 bg-zinc-800 border border-zinc-700 text-indigo-300 text-[8px] font-bold rounded uppercase">{line.tran_type}</span> : '-'}
                      </td>
                      <td className="py-3 font-mono text-sky-400 truncate">{line.cheque_ref || '-'}</td>
                      <td className="py-3 text-right font-mono font-bold text-red-400">{line.debit ? `₹${line.debit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : '-'}</td>
                      <td className="py-3 text-right font-mono font-bold text-emerald-400">{line.credit ? `₹${line.credit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : '-'}</td>
                      <td className="py-3 text-right font-mono font-bold text-cyan-400">₹{line.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-zinc-950/40 border-t border-zinc-800 text-[11px] font-mono text-zinc-500">
                    <td colSpan={3} className="p-3 font-bold uppercase">Statement Opening Balance</td>
                    <td colSpan={5} className="p-3 text-right font-bold text-zinc-300 text-sm">₹{opening.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                  </tr>
                  <tr className="bg-zinc-950/20 text-[11px] font-mono border-t border-zinc-800/50">
                    <td colSpan={5} className="p-3 font-bold text-zinc-500 uppercase">Live Vol Aggregation ({previewLines.length} Rows)</td>
                    <td className="p-3 text-right font-bold text-red-400">-₹{totalDebit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                    <td className="p-3 text-right font-bold text-emerald-400">+₹{totalCredit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                    <td className="p-3"></td>
                  </tr>
                  <tr className="bg-zinc-950/60 border-t-2 border-zinc-800 text-[11px] font-mono text-cyan-400 font-bold">
                    <td colSpan={3} className="p-3 uppercase">Computed Closing Balance Run</td>
                    <td colSpan={5} className="p-3 text-right text-sm">₹{calculatedClosingValue.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
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