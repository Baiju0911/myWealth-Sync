import React, { useState, useEffect } from 'react';
import { accountApi } from '../api.ts';
import api from '../api/client';
import { type AccountEntity, type StagingPreviewLine, type TemplateMetadata, type ApiResponseMeta } from '../types/ledger';

// 🚀 Dynamic Pipeline Engines Linked
import { TableEngine } from '../components/ui/data-table/TableEngine';
import { VerificationDeck } from '../components/ui/data-table/VerificationDeck';
import { LEDGER_COLUMNS } from '../components/ui/data-table/columns';




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
    
    if (rawStreamText.startsWith("#FILENAME:")) {
      const lines = rawStreamText.split("\n");
      const metaLine = lines[0]; 
      
      exportFilename = metaLine.replace("#FILENAME:", "").trim() || "statement_export.csv";      
      cleanContent = lines.slice(1).join("\n");
    }
    
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

      {commitSuccessMsg && (
        <div className="p-4 bg-emerald-500/10 text-emerald-400 text-sm border border-emerald-500/20 rounded-xl font-medium shadow-lg">
          {commitSuccessMsg}
        </div>
      )}

      <br/>

      {/* 📊 High-Performance Summary Reconciliation Deck */}
      {responseMeta && (
        <VerificationDeck 
          responseMeta={responseMeta}
          previewLines={previewLines}
          opening={opening}
          totalDebit={totalDebit}
          totalCredit={totalCredit}
          statementClosing={statementClosing}
          calculatedClosingValue={calculatedClosingValue}
          isDoubleTrustOk={isDoubleTrustOk}
          isBalanceVerified={isBalanceVerified}
          isFileFullyStale={isFileFullyStale}
          isRowCountVerified={isRowCountVerified}
        />
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
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-zinc-800 gap-4 mb-4">
            <div><h3 className="text-base font-semibold text-white">Persistent Workspace Staging Floor (9-Column Review Deck)</h3></div>
            
            {previewLines.length > 0 && (
              <div className="flex items-center gap-3">
                <button 
                  type="button" 
                  onClick={() => downloadWorkableCSV((window as any).__lastRawStream || "")}
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
            <div className="flex-1 flex items-center justify-center p-12 text-center text-sm text-zinc-500 border border-dashed border-zinc-800 rounded-lg">
              No active 9-column entries extracted into staging floor yet.
            </div>
          ) : (
            /* 🚀 COMPACT GENERATOR CORE HOOK */
            <TableEngine 
              columns={LEDGER_COLUMNS} 
              data={previewLines} 
              isDuplicateRow={(row) => row.status === 'DUPLICATE'}
            />
          )}
        </div>
      </div>
    </div>
  );
}