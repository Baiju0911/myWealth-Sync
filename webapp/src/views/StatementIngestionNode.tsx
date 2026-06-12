import React, { useState, useEffect } from 'react';
import { accountApi } from '../api.ts';
import api from '../api/client';
import { type AccountEntity } from '../types/ledger';
import type { DragEvent } from 'react';

interface ParsedTxnRow {
  date: string;
  value_date: string;
  narration_description: string; 
  type: string;
  chq_ref: string;               
  debit: string;                 
  credit: string;                
  balance: string;
  status: string;                
}

interface TemplateMetadata {
  id: number;
  template_name: string;
  is_universal: boolean;
}

// ─── 🟢 UNIFIED METRIC OBJECT INTERFACE ───
interface AuditSummaryDeck {
  calculated_opening: number;
  calculated_debit: number;
  calculated_credit: number;
  calculated_closing: number;
  document_opening: number | null;
  document_debit: number | null;
  document_credit: number | null;
  document_closing: number | null;
  audit_passed: boolean;
}

interface IngestionNodeProps {
  onRedirectToMapper?: () => void;
}

export default function StatementIngestionNode({ onRedirectToMapper }: IngestionNodeProps) {
  const [accounts, setAccounts] = useState<AccountEntity[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  
  const [availableTemplates, setAvailableTemplates] = useState<TemplateMetadata[]>([]);
  const [forcedTemplateId, setForcedTemplateId] = useState<string>('');

  // Response States
  const [statusMode, setStatusMode] = useState<'IDLE' | 'PARSED_SUCCESS' | 'REQUIRES_MAPPING' | 'ERROR'>('IDLE');
  const [appliedTemplate, setAppliedTemplate] = useState<string>('');
  const [transactions, setTransactions] = useState<ParsedTxnRow[]>([]);
  const [debitLineCount, setDebitLineCount] = useState<number>(0);
  const [creditLineCount, setCreditLineCount] = useState<number>(0);
  const [errorMessage, setErrorMessage] = useState<string>('');
  
  // ─── 🟢 ACTIVE BALANCE VERIFICATION STATE MATRIX ───
  const [auditDeck, setAuditDeck] = useState<AuditSummaryDeck | null>(null);

  useEffect(() => {
    accountApi.getAccounts()
      .then((res: any) => {
        const extracted = Array.isArray(res) ? res : res.results || [];
        setAccounts(extracted);
      })
      .catch((err) => console.error("Failed loading account profiles:", err));

    api.get('/statements/available/')
      .then((res) => setAvailableTemplates(res.data || []))
      .catch((err) => console.error("Failed downloading configuration blueprints:", err));
  }, []);

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!loading) setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile) {
      processFileIngestion(droppedFile);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      processFileIngestion(selectedFile);
    }
  };

  const processFileIngestion = async (targetFile: File) => {
    if (!selectedAccountId) {
      alert("Please designate a target ledger banking channel before staging operations.");
      return;
    }
    setFile(targetFile);
    loadingStateReset();
    
    const formData = new FormData();
    formData.append('file', targetFile);
    formData.append('account_id', selectedAccountId);
    
    if (forcedTemplateId) {
      formData.append('forced_template_id', forcedTemplateId);
    }

    try {
      setLoading(true);
      const response = await api.post('/statements/ingestDynamic/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      const data = response.data;

      if (data.status === 'SUCCESS' || data.status === 'PARSED_SUCCESS') {
        setStatusMode('PARSED_SUCCESS');
        setAppliedTemplate(data.applied_template || 'Universal Engine Parser');
       // setTransactions(data.preview_dataset || []);
        setTransactions(data.preview_dataset || data.transactions || []);
        setDebitLineCount(data.debit_line_count || 0);
        setCreditLineCount(data.credit_line_count || 0);
        
        // Map payload calculations metrics down into the audit layout deck hooks
        if (data.data) {
          setAuditDeck({
            calculated_opening: data.data.calculated_opening || 0,
            calculated_debit: data.data.calculated_debit || 0,
            calculated_credit: data.data.calculated_credit || 0,
            calculated_closing: data.data.calculated_closing || 0,
            document_opening: data.data.document_opening,
            document_debit: data.data.document_debit,
            document_credit: data.data.document_credit,
            document_closing: data.data.document_closing,
            audit_passed: data.data.audit_passed || false,
          });
        }
      } else if (data.status === 'REQUIRES_MAPPING') {
        setStatusMode('REQUIRES_MAPPING');
      } else {
        throw new Error(data.error || "Unexpected response structure from ingestion engine.");
      }
    } catch (err: any) {
      setStatusMode('ERROR');
      setErrorMessage(err.response?.data?.error || err.message || "Network pipeline rejection.");
    } finally {
      setLoading(false);
    }
  };

  const loadingStateReset = () => {
    setStatusMode('IDLE');
    setErrorMessage('');
    setTransactions([]);
    setAuditDeck(null);
  };

  const formatCurrency = (val: number | null | undefined) => {
    if (val === null || val === undefined) return '₹-';
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(val);
  };

  return (
    <div className="w-full space-y-5 text-zinc-100 px-1 text-left animate-fade-in">
      <div>
        <h2 className="text-xl font-bold tracking-tight text-white">Automated Ledger Ingestion Node</h2>
        <p className="text-xs text-zinc-400 mt-1">Ingest binary document streams to parse transactions directly into ledger states using dynamic layout blue-printing templates.</p>
      </div>

      <hr className="border-zinc-800" />

      {/* ─── 🟢 SECURITY STATUS SUMMATION DECK BLOCK ─── */}
      {statusMode === 'PARSED_SUCCESS' && auditDeck && (
        <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-4 space-y-4 animate-fade-in shadow-2xl">
          <div className="flex justify-between items-center border-b border-zinc-900 pb-2.5">
            <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
              ⚖️ Automated Engine Verification Summary Deck
            </h3>
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-tight ${
              auditDeck.audit_passed ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-amber-950 text-amber-400 border border-amber-800'
            }`}>
              {auditDeck.audit_passed ? '🟢 Balance: MATCHED' : '🟡 Audit Variance Detected'}
            </span>
          </div>
          
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs font-mono">
            <div className="p-3 bg-zinc-900/50 rounded-lg border border-zinc-800/60">
              <span className="text-[10px] uppercase font-bold tracking-tight text-zinc-500 block mb-1">Opening Balance</span>
              <div className="text-sm font-bold text-blue-400">{formatCurrency(auditDeck.calculated_opening)}</div>
              <span className="text-[9px] text-zinc-500 block mt-0.5">Baseline Anchor</span>
            </div>
            
            <div className="p-3 bg-zinc-900/50 rounded-lg border border-zinc-800/60">
              <span className="text-[10px] uppercase font-bold tracking-tight text-zinc-500 block mb-1">Total Debits (-)</span>
              <div className="text-sm font-bold text-red-400">{formatCurrency(auditDeck.calculated_debit)}</div>
              <span className="text-[9px] text-zinc-400 block mt-0.5">📂 {debitLineCount} debits</span>
            </div>
            
            <div className="p-3 bg-zinc-900/50 rounded-lg border border-zinc-800/60">
              <span className="text-[10px] uppercase font-bold tracking-tight text-zinc-500 block mb-1">Total Credits (+)</span>
              <div className="text-sm font-bold text-emerald-400">{formatCurrency(auditDeck.calculated_credit)}</div>
              <span className="text-[9px] text-zinc-400 block mt-0.5">📂 {creditLineCount} credits</span>
            </div>
            
            <div className="p-3 bg-zinc-900/50 rounded-lg border border-zinc-800/60">
              <span className="text-[10px] uppercase font-bold tracking-tight text-zinc-500 block mb-1">Statement Closing</span>
              <div className="text-sm font-bold text-cyan-400">{formatCurrency(auditDeck.calculated_closing)}</div>
              <span className="text-[9px] text-zinc-500 block mt-0.5">Mathematical Result</span>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Left Control Column Panel */}
        <div className="space-y-4">
          <div className="p-4 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl space-y-4">
            <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-wider">Ingestion Controls</h3>
            
            {/* Account Selector */}
            <div>
              <label className="block text-[11px] font-medium text-zinc-400 mb-1.5">Target Bank Account Channel</label>
              <select
                value={selectedAccountId}
                onChange={(e) => setSelectedAccountId(e.target.value)}
                disabled={loading}
                className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-xs text-zinc-200 focus:outline-none focus:border-emerald-500 disabled:opacity-50 transition-all"
              >
                <option value="">-- Select Active Channel Node --</option>
                {accounts.map((acc) => (
                  <option key={acc.id} value={acc.id}>{acc.name} {acc.account_number ? `(•••• ${acc.account_number})` : ''}</option>
                ))}
              </select>
            </div>

            {/* Blueprint Selector */}
            <div>
              <div className="flex justify-between items-center mb-1.5">
                <label className="block text-[11px] font-medium text-zinc-400">Parsing Engine Execution Blueprint</label>
                <span className="text-[9px] font-mono text-zinc-500 uppercase tracking-tight">Optional Override</span>
              </div>
              <select
                value={forcedTemplateId}
                onChange={(e) => setForcedTemplateId(e.target.value)}
                disabled={loading}
                className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-xs text-emerald-400 font-mono focus:outline-none focus:border-emerald-500 disabled:opacity-50 transition-all"
              >
                <option value="" className="text-zinc-400 font-sans">⚡ [AUTOMATED ENGINE ROUTING MODE]</option>
                {availableTemplates.map((tmpl) => (
                  <option key={tmpl.id} value={tmpl.id} className="font-mono text-zinc-300">
                    ⚙️ {tmpl.template_name} {tmpl.is_universal ? '(9-Col Univ)' : '(Legacy)'}
                  </option>
                ))}
              </select>
            </div>

            {/* Dropzone File Entry Port */}
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => !loading && document.getElementById('ingestFileInput')?.click()}
              className={`border border-dashed rounded-xl p-5 text-center transition-all ${
                isDragging ? 'border-emerald-500 bg-emerald-950/10' : 'border-zinc-800 bg-zinc-950/40'
              } ${!selectedAccountId ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer hover:border-zinc-600'}`}
            >
              <input 
                type="file" id="ingestFileInput" className="hidden" accept=".pdf,.csv" disabled={!selectedAccountId || loading}
                onChange={handleFileChange} 
              />
              <div className="space-y-2">
                <div className="text-xl">📥</div>
                <div className="text-xs font-medium text-zinc-300">
                  {file ? <span className="text-emerald-400 font-mono break-all">{file.name}</span> : 'Drop bank document PDF / CSV here'}
                </div>
                <p className="text-[10px] text-zinc-500">Click to locate filesystem paths directly</p>
              </div>
            </div>
          </div>
        </div>

        {/* Right Output Viewport Engine Status Monitor Block */}
        <div className="lg:col-span-2">
          <div className="p-4 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl min-h-[300px] flex flex-col justify-between">
            
            {statusMode === 'IDLE' && !loading && (
              <div className="my-auto text-center p-6 space-y-2">
                <div className="text-2xl opacity-40">🧬</div>
                <h4 className="text-xs font-bold text-zinc-400 uppercase tracking-wide">Awaiting Data Ingestion Stream</h4>
                <p className="text-[11px] text-zinc-500 max-w-xs mx-auto">Select a target financial ledger node channel and supply an extraction object to activate automated schema template execution passes.</p>
              </div>
            )}

            {loading && (
              <div className="my-auto text-center p-6 space-y-3">
                <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto"></div>
                <h4 className="text-xs font-mono text-emerald-400 animate-pulse">Running Server Template Matching Pipeline Engine...</h4>
              </div>
            )}

            {statusMode === 'ERROR' && (
              <div className="my-auto p-4 bg-red-950/20 border border-red-900/50 rounded-xl space-y-2 text-center max-w-md mx-auto">
                <div className="text-lg">⚠️</div>
                <h4 className="text-xs font-bold text-red-400 uppercase tracking-wider">Ingestion Pipeline Exception Blocked</h4>
                <p className="text-[11px] font-mono text-red-300/80 break-all">{errorMessage}</p>
              </div>
            )}

            {statusMode === 'REQUIRES_MAPPING' && (
              <div className="my-auto text-center p-6 space-y-4 max-w-sm mx-auto animate-fade-in">
                <div className="text-3xl">🧩</div>
                <div>
                  <h4 className="text-sm font-bold text-amber-400">Layout Coordinate Blueprint Missing</h4>
                  <p className="text-[11px] text-zinc-400 mt-1">This document structure matches no recorded profiles. We need to create a custom geometric cutting matrix layer blueprint for this format before processing.</p>
                </div>
                <button
                  type="button" onClick={onRedirectToMapper}
                  className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-xs font-bold rounded-lg text-black transition-all shadow-md cursor-pointer"
                >
                  Launch Universal Coordinate Box Mapper
                </button>
              </div>
            )}

            {statusMode === 'PARSED_SUCCESS' && (
              <div className="space-y-3 w-full animate-fade-in">
                <div className="flex justify-between items-center bg-zinc-950 p-2.5 rounded-lg border border-zinc-800">
                  <div>
                    <span className="text-[10px] uppercase font-bold text-zinc-500 tracking-wider block">Executed Blueprint Model</span>
                    <span className="text-xs font-mono font-bold text-emerald-400">✨ {appliedTemplate}</span>
                  </div>
                  <div className="text-right">
                    <span className="text-[10px] uppercase font-bold text-zinc-500 tracking-wider block">Extracted Transactions</span>
                    <span className="text-xs font-mono font-bold text-white">{transactions.length} Rows</span>
                  </div>
                </div>

                {/* SCROLLABLE TABLE CONTAINMENT LANE */}
                <div className="overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-950 w-full custom-scrollbar">
                  <table className="text-left text-xs font-mono table-fixed border-collapse" style={{ width: '1200px', minWidth: '1200px' }}>
                    <thead className="sticky top-0 z-10 bg-zinc-900 text-[10px] uppercase font-bold border-b border-zinc-800 text-zinc-400">
                      <tr>
                        <th className="p-2 border-r border-zinc-800/60" style={{ width: '100px' }}>Txn Date</th>
                        <th className="p-2 border-r border-zinc-800/60 text-orange-400" style={{ width: '100px' }}>Val Date</th>
                        <th className="p-2 border-r border-zinc-800/60 text-purple-400" style={{ width: '420px' }}>Narration Description</th>
                        <th className="p-2 border-r border-zinc-800/60 text-center text-indigo-400" style={{ width: '80px' }}>Type</th>
                        <th className="p-2 border-r border-zinc-800/60 text-sky-400" style={{ width: '120px' }}>Chq/Ref</th>
                        <th className="p-2 border-r border-zinc-800/60 text-right text-red-400" style={{ width: '115px' }}>Debit (-)</th>
                        <th className="p-2 border-r border-zinc-800/60 text-right text-emerald-400" style={{ width: '115px' }}>Credit (+)</th>
                        <th className="p-2 border-r border-zinc-800/60 text-right text-cyan-400" style={{ width: '120px' }}>Balance</th>
                        <th className="p-2 text-center text-zinc-500" style={{ width: '50px' }}>Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-900 text-zinc-300">
                      {transactions.map((tx: any, idx) => (
                        <tr key={idx} className="hover:bg-zinc-900/40 transition-colors">
                          <td className="p-2 border-r border-zinc-900/60 text-blue-300 font-medium whitespace-nowrap">{tx.date || '-'}</td>
                          <td className="p-2 border-r border-zinc-900/60 text-orange-300/90 whitespace-nowrap">{tx.value_date || '-'}</td>
                          <td className="p-2 border-r border-zinc-900/60 truncate text-zinc-200" title={tx.narration_description}>{tx.narration_description || '-'}</td>
                          <td className="p-2 border-r border-zinc-900/60 text-center" style={{ textAlign: 'center' }}>
                            {tx.type ? (
                              <span className="inline-block px-1 py-0.5 text-[8px] bg-indigo-900/40 border border-indigo-700/40 text-indigo-300 rounded font-bold uppercase">{tx.type}</span>
                            ) : (
                              <span className="text-zinc-800 opacity-20">-</span>
                            )}
                          </td>
                          <td className="p-2 border-r border-zinc-900/60 text-sky-300 font-mono truncate">{tx.chq_ref || '-'}</td>
                          <td className="p-2 border-r border-zinc-900/60 text-right text-red-400 font-bold whitespace-nowrap" style={{ textAlign: 'right' }}>{tx.debit || '-'}</td>
                          <td className="p-2 border-r border-zinc-900/60 text-right text-emerald-400 font-bold whitespace-nowrap" style={{ textAlign: 'right' }}>{tx.credit || '-'}</td>
                          <td className="p-2 border-r border-zinc-900/60 text-right text-cyan-300 font-bold whitespace-nowrap" style={{ textAlign: 'right' }}>{tx.balance || '-'}</td>
                          <td className="p-1 text-center font-bold text-zinc-400" style={{ textAlign: 'center' }}>{tx.status || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

          </div>
        </div>

      </div>
    </div>
  );
}
