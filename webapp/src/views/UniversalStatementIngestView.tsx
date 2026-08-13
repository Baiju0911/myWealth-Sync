import React, { useState, useEffect } from 'react';
import { accountApi } from '../api/api.ts';
import api from '../api/client';
import { type AccountEntity, type StagingPreviewLine, type TemplateMetadata, type ApiResponseMeta } from '../types/ledger';

// 🚀 Dynamic Pipeline Engines Linked
import { TableEngine } from '../components/ui/data-table/TableEngine';
import { VerificationDeck } from '../components/ui/data-table/VerificationDeck';
import { LEDGER_COLUMNS } from '../components/ui/data-table/columns';

export interface UniversalStatementIngestViewProps {
  onIngestionComplete?: () => void;
}

export function UniversalStatementIngestView({ onIngestionComplete }: UniversalStatementIngestViewProps) {
  const [accounts, setAccounts] = useState<AccountEntity[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  
  const [loading, setLoading] = useState(false);
  const [commitLoading, setCommitLoading] = useState(false);
  
  const [previewLines, setPreviewLines] = useState<StagingPreviewLine[]>([]);
  const [responseMeta, setResponseMeta] = useState<ApiResponseMeta | null>(null); 
  
  // 🎯 STRATEGY & CONFIDENCE TRACKING STATES
  const [strategyExecuted, setStrategyExecuted] = useState<string>('');
  const [confidenceScore, setConfidenceScore] = useState<number | null>(null);
  
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
    setStrategyExecuted('');
    setConfidenceScore(null);

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
        console.log("🚀 FULL BACKEND INGESTION RESPONSE PAYLOAD:", res.data);
        
        const dataset = res.data.preview_dataset || res.data.data?.preview_dataset || [];
        setPreviewLines(dataset);

        // 🎯 CALCULATE FILE CLASSIFICATION TYPE FROM THE EXPORT_FILENAME EXTENSION
        let detectedType = 'UNKNOWN';
        const filename = res.data.export_filename || '';
        if (filename.toLowerCase().endsWith('.csv')) {
          detectedType = 'CSV';
        } else if (filename.toLowerCase().endsWith('.xlsx') || filename.toLowerCase().endsWith('.xls')) {
          detectedType = 'EXCEL';
        } else if (filename.toLowerCase().endsWith('.pdf')) {
          detectedType = 'PDF';
        }

        setStrategyExecuted(res.data.strategy_processed || res.data.engine_strategy_executed || 'STRICT_MATRIX');
        setConfidenceScore(typeof res.data.confidence_score !== 'undefined' ? res.data.confidence_score : null);
        
        setResponseMeta({
          fileType: detectedType, 
          decrypted: res.data.decrypted || res.data.data?.decrypted || false,
          count: typeof res.data.count !== 'undefined' ? res.data.count : (dataset.length || 0),
          openingBalance: res.data.opening_balance || 0,
          closingBalance: res.data.closing_balance || 0,
          totalDebit: res.data.total_debit || 0,
          totalCredit: res.data.total_credit || 0,
          rawMatchCount: res.data.count || 0,
          debitLineCount: res.data.debit_line_count || 0,
          creditLineCount: res.data.credit_line_count || 0,
          emptyMemoLineCount: res.data.empty_memo_line_count || res.data.system_noise_records_cleared || 0,
          duplicateCount: res.data.duplicate_count || 0, 
        });
        
        (window as any).__lastRawStream = res.data.raw_csv_stream || res.data.generated_raw_csv_stream || "";
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
      await api.post('/statement/commit-staging/', {
        account_id: selectedAccountId,
        preview_dataset: previewLines,
        file_name: file ? file.name : "9COL_STATEMENT.PDF", 
        strategy_used: strategyExecuted,
        meta_summary: {
          ...responseMeta,
          strategy_used: strategyExecuted
        }, 
      });
      setCommitSuccessMsg("Pipeline run committed to core ledger successfully.");
      setPreviewLines([]); 
      setResponseMeta(null); 
      setFile(null);
      setStrategyExecuted('');
      setConfidenceScore(null);

      // 💡 AUTO-ADVANCE PIPELINE STEP CALL
      if (onIngestionComplete) {
        onIngestionComplete();
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

  const getStrategyBadgeStyles = (strat: string) => {
    if (strat.includes("PADDLE_OCR")) return "bg-amber-500/10 text-amber-400 border-amber-500/20";
    if (strat.includes("UNIVERSAL_CSV")) return "bg-blue-500/10 text-blue-400 border-blue-500/20";
    return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
  };

  return (
    <div className="space-y-6 text-white p-2 text-left">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div></div>
        
        {strategyExecuted && (
          <div className={`px-4 py-2 rounded-xl text-xs font-mono font-bold border flex items-center gap-2 tracking-wide shadow-md transition-all ${getStrategyBadgeStyles(strategyExecuted)}`}>
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-current opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-current"></span>
            </span>
            ACTIVE ENGINE: {strategyExecuted}
          </div>
        )}
      </div>

      {commitSuccessMsg && (
        <div className="p-4 bg-emerald-500/10 text-emerald-400 text-sm border border-emerald-500/20 rounded-xl font-medium shadow-lg">
          {commitSuccessMsg}
        </div>
      )}

      <br/>

      {/* 📊 Summary Reconciliation Deck */}
      {responseMeta && (
        <div className="space-y-4">
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
            strategyExecuted={strategyExecuted}
            confidenceScore={confidenceScore}
            frontendRenderCount={frontendRenderCount}
          />
        </div>
      )}

      <br/>
      
      {/* 🎛️ HORIZONTAL INGESTION PIPELINE CONTROL BAR */}
      <div className="w-full p-4 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl mb-6">
        <div 
          style={{ 
            display: 'flex', 
            flexDirection: 'row', 
            alignItems: 'flex-start', 
            justifyContent: 'space-between', 
            gap: '16px',
            flexWrap: 'wrap'
          }}
        >
          {/* CONTROL FIELD 1: Target Bank Account Dropdown */}
          <div className="flex-1 min-w-[240px]">
            <label className="block text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-1.5 font-mono">
              Target Bank Account
            </label>
            <select 
              value={selectedAccountId} 
              onChange={(e) => setSelectedAccountId(e.target.value)} 
              className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-xs font-mono text-zinc-200 focus:outline-none focus:border-emerald-500 h-10 transition-colors"
            >
              <option value="">-- Select Channel --</option>
              {accounts.map((acc) => (
                <option key={acc.id} value={acc.id}>
                  💳 {acc.name} {acc.account_number ? `(•••• ${acc.account_number})` : ''}
                </option>
              ))}
            </select>
          </div>

          {/* CONTROL FIELD 2: Execution Engine Dropdown */}
          <div className="flex-1 min-w-[260px]">
            <label className="block text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-1.5 font-mono">
              Parsing Engine Execution Blueprint
            </label>
            <select 
              value={forcedTemplateId} 
              onChange={(e) => setForcedTemplateId(e.target.value)}
              className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-xs text-emerald-400 font-mono focus:outline-none focus:border-emerald-500 h-10 transition-colors"
            >
              <option value="">⚡ [AUTOMATED ENGINE ROUTING MODE]</option>
              {availableTemplates && availableTemplates.map((t: any) => (
                <option key={t.id} value={t.id}>
                  ⚙️ {t.template_name || t.name}
                </option>
              ))}
            </select>
          </div>

          {/* CONTROL FIELD 3: Compact File Drop Strip Container */}
          <div className="flex-1 min-w-[280px]">
            <label className="block text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-1.5 font-mono">
              Statement Document (PDF or CSV)
            </label>
            <div 
              onDragOver={handleDragOver} 
              onDragLeave={handleDragLeave} 
              onDrop={handleDrop} 
              className={`border border-dashed rounded-lg px-3 flex items-center justify-between transition-all h-10 ${
                isDragging 
                  ? 'border-emerald-500 bg-emerald-500/5' 
                  : 'border-zinc-800 bg-zinc-950/40 hover:border-zinc-700'
              }`}
            >
              <input 
                type="file" 
                id="uniFileInput" 
                className="w-full text-[11px] text-zinc-400 file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-[10px] file:font-mono file:font-bold file:bg-zinc-800 file:text-emerald-400 hover:file:bg-zinc-700 cursor-pointer" 
                accept=".csv,.pdf" 
                onChange={handleFileChange} 
              />
              <span className="text-[9px] text-zinc-600 font-mono hidden xl:inline whitespace-nowrap select-none pl-2 border-l border-zinc-800/80">
                Drop here
              </span>
            </div>
          </div>
        </div>

        {/* ⚠️ SYSTEM ERROR AND WAITING STATES CONSOLE FOOTERS */}
        {(errorMsg || loading) && (
          <div className="w-full pt-3 mt-3 border-t border-zinc-800/60 flex flex-col gap-2">
            {errorMsg && (
              <div className="p-2.5 bg-red-500/10 text-red-400 text-xs border border-red-500/20 rounded-lg font-mono">
                ⚠️ {errorMsg}
              </div>
            )}
            
            {loading && (
              <div className="p-2.5 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-lg text-xs font-mono font-bold animate-pulse text-center tracking-wide">
                ⏳ Processing Multi-Page Matrix Stream Data Array...
              </div>
            )}
          </div>
        )}

        {/* 🚀 PERSISTENT WORKSPACE STAGING FLOOR */}
        <div className="xl:col-span-8 p-5 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl min-h-[440px] flex flex-col mt-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-zinc-800 gap-4 mb-4">
            <div>
              <h3 className="text-sm font-bold tracking-wider text-zinc-100 uppercase font-mono">
                Staging Floor
              </h3>
            </div>
            
            {previewLines.length > 0 && (
              <div 
                className="self-end sm:self-auto"
                style={{ 
                  display: 'flex', 
                  flexDirection: 'row', 
                  alignItems: 'center', 
                  gap: '12px' 
                }}
              >
                {/* 📊 ACTION 1: EXPORT CSV */}
                <button 
                  type="button" 
                  onClick={() => downloadWorkableCSV((window as any).__lastRawStream || "")}
                  className="px-4 flex flex-row items-center justify-center gap-2 bg-zinc-950 hover:bg-zinc-900 border border-zinc-800 hover:border-emerald-600/40 text-emerald-400 font-mono rounded-lg transition-all shadow-inner cursor-pointer"
                  style={{ height: '36px', minHeight: '36px' }}
                  title="Export Ingested Dataset as Flat CSV"
                >
                  <span style={{ fontSize: '12px' }}>📥</span>
                  <span className="text-[10px] font-bold uppercase tracking-wider leading-none">
                    Export CSV
                  </span>
                </button>

                {/* 🔒 ACTION 2: ATOMIC COMMIT */}
                <button 
                  type="button" 
                  onClick={handleCommitStaging} 
                  disabled={commitLoading} 
                  className={`px-4 flex flex-row items-center justify-center gap-2 border rounded-lg transition-all shadow-md select-none font-mono ${
                    commitLoading 
                      ? 'bg-zinc-800 border-zinc-700 text-zinc-500 cursor-not-allowed' 
                      : 'bg-emerald-600/10 hover:bg-emerald-600 border-emerald-500/30 hover:border-emerald-500 text-emerald-400 hover:text-white cursor-pointer'
                  }`}
                  style={{ height: '36px', minHeight: '36px' }}
                  title={commitLoading ? 'Saving Ledger Run...' : 'Save Reconciled Statement to Ledger'}
                >
                  <span 
                    className={`${commitLoading ? 'animate-spin' : ''}`}
                    style={{ display: 'inline-flex', alignItems: 'center', fontSize: '13px', lineHeight: '1' }}
                  >
                    {commitLoading ? '⏳' : '🛡️'}
                  </span>
                  <span className="text-[10px] font-bold uppercase tracking-wider leading-none">
                    {commitLoading ? 'Saving...' : 'Commit Run'}
                  </span>
                </button>
              </div>
            )}
          </div>

          {/* 📊 DYNAMIC REVIEW PANEL TARGET AGGREGATION VIEWPORTS */}
          {previewLines.length === 0 ? (
            <div className="flex-1 flex items-center justify-center p-12 text-center text-xs font-mono text-zinc-600 border border-dashed border-zinc-800 rounded-lg bg-zinc-950/20">
              No active 9-column entries extracted into staging floor yet.
            </div>
          ) : (
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

export default UniversalStatementIngestView;


// import React, { useState, useEffect } from 'react';
// import { accountApi } from '../api.ts';
// import api from '../api/client';
// import { type AccountEntity, type StagingPreviewLine, type TemplateMetadata, type ApiResponseMeta } from '../types/ledger';

// // 🚀 Dynamic Pipeline Engines Linked
// import { TableEngine } from '../components/ui/data-table/TableEngine';
// import { VerificationDeck } from '../components/ui/data-table/VerificationDeck';
// import { LEDGER_COLUMNS } from '../components/ui/data-table/columns';

// export default function UniversalStatementIngestView() {
//   const [accounts, setAccounts] = useState<AccountEntity[]>([]);
//   const [selectedAccountId, setSelectedAccountId] = useState('');
//   const [file, setFile] = useState<File | null>(null);
//   const [isDragging, setIsDragging] = useState(false);
  
//   const [loading, setLoading] = useState(false);
//   const [commitLoading, setCommitLoading] = useState(false);
  
//   const [previewLines, setPreviewLines] = useState<StagingPreviewLine[]>([]);
//   const [responseMeta, setResponseMeta] = useState<ApiResponseMeta | null>(null); 
  
//   // 🎯 STRATEGY & CONFIDENCE TRACKING STATES
//   const [strategyExecuted, setStrategyExecuted] = useState<string>('');
//   const [confidenceScore, setConfidenceScore] = useState<number | null>(null);
  
//   const [errorMsg, setErrorMsg] = useState('');
//   const [commitSuccessMsg, setCommitSuccessMsg] = useState('');

//   const [availableTemplates, setAvailableTemplates] = useState<TemplateMetadata[]>([]);
//   const [forcedTemplateId, setForcedTemplateId] = useState<string>('');

//   const downloadWorkableCSV = (rawStreamText: string) => {
//     if (!rawStreamText) return;
    
//     let cleanContent = rawStreamText;
//     let exportFilename = "statement_export.csv";
    
//     if (rawStreamText.startsWith("#FILENAME:")) {
//       const lines = rawStreamText.split("\n");
//       const metaLine = lines[0]; 
      
//       exportFilename = metaLine.replace("#FILENAME:", "").trim() || "statement_export.csv";      
//       cleanContent = lines.slice(1).join("\n");
//     }
    
//     const csvContent = cleanContent.replace(/ ~ /g, ",");
//     const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
//     const url = URL.createObjectURL(blob);
//     const link = document.createElement("a");
    
//     link.setAttribute("href", url);
//     link.setAttribute("download", exportFilename);
    
//     document.body.appendChild(link);
//     link.click();
//     document.body.removeChild(link);
//   };

//   useEffect(() => {
//     accountApi.getAccounts()
//       .then(res => setAccounts(Array.isArray(res) ? res : res.results || []))
//       .catch(() => setErrorMsg('Failed loading ledger workspace nodes.'));

//     api.get('/statements/available/')
//       .then((res) => setAvailableTemplates(res.data || []))
//       .catch((err) => console.error("Failed loading configuration maps:", err));
//   }, []);

//   const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); };
//   const handleDragLeave = () => setIsDragging(false);
  
//   const handleDrop = (e: React.DragEvent) => {
//     e.preventDefault();
//     setIsDragging(false);
//     if (e.dataTransfer.files && e.dataTransfer.files[0]) {
//       const droppedFile = e.dataTransfer.files[0];
//       setFile(droppedFile);
//       if (selectedAccountId) {
//         executeUploadDirectly(droppedFile, selectedAccountId);
//       } else {
//         setErrorMsg("Please select a target bank account channel first.");
//       }
//     }
//   };
    
//   const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
//     if (e.target.files && e.target.files[0]) {
//       const selectedFile = e.target.files[0];
//       setFile(selectedFile);
//       if (selectedAccountId) {
//         executeUploadDirectly(selectedFile, selectedAccountId);
//       } else {
//         setErrorMsg("Please select a target bank account channel first.");
//       }
//     }
//   };

//   const executeUploadDirectly = async (targetFile: File, accountId: string) => {
//     setLoading(true);
//     setErrorMsg('');
//     setCommitSuccessMsg('');
//     setPreviewLines([]);
//     setResponseMeta(null);
//     setStrategyExecuted('');
//     setConfidenceScore(null);

//     const formData = new FormData();
//     formData.append('statement_file', targetFile);
//     formData.append('account_id', accountId);
//     if (forcedTemplateId) {
//       formData.append('forced_template_id', forcedTemplateId);
//     }

//     try {
//       const res = await api.post('/statement/ingestbulk/', formData, {
//         headers: { 'Content-Type': 'multipart/form-data' },
//       });

//       if (res.data.status === 'SUCCESS') {
//             console.log("🚀 FULL BACKEND INGESTION RESPONSE PAYLOAD:", res.data);
            
//             const dataset = res.data.preview_dataset || res.data.data?.preview_dataset || [];
//             setPreviewLines(dataset);

//             // 🎯 CALCULATE FILE CLASSIFICATION TYPE FROM THE EXPORT_FILENAME EXTENSION
//             let detectedType = 'UNKNOWN';
//             const filename = res.data.export_filename || '';
//             if (filename.toLowerCase().endsWith('.csv')) {
//               detectedType = 'CSV';
//             } else if (filename.toLowerCase().endsWith('.xlsx') || filename.toLowerCase().endsWith('.xls')) {
//               detectedType = 'EXCEL';
//             } else if (filename.toLowerCase().endsWith('.pdf')) {
//               detectedType = 'PDF';
//             }

//             setStrategyExecuted(res.data.strategy_processed || res.data.engine_strategy_executed || 'STRICT_MATRIX');
//             setConfidenceScore(typeof res.data.confidence_score !== 'undefined' ? res.data.confidence_score : null);
            
//             setResponseMeta({
//               // 🔥 FIX: Assigns the dynamic parsed string instead of hitting the hardcoded fallback
//               fileType: detectedType, 
              
//               decrypted: res.data.decrypted || res.data.data?.decrypted || false,
//               count: typeof res.data.count !== 'undefined' ? res.data.count : (dataset.length || 0),
//               openingBalance: res.data.opening_balance || 0,
//               closingBalance: res.data.closing_balance || 0,
//               totalDebit: res.data.total_debit || 0,
//               totalCredit: res.data.total_credit || 0,
//               rawMatchCount: res.data.count || 0,
//               debitLineCount: res.data.debit_line_count || 0,
//               creditLineCount: res.data.credit_line_count || 0,
//               emptyMemoLineCount: res.data.empty_memo_line_count || res.data.system_noise_records_cleared || 0,
//               duplicateCount: res.data.duplicate_count || 0, 
//             });
            
//             (window as any).__lastRawStream = res.data.raw_csv_stream || res.data.generated_raw_csv_stream || "";
//           }
//     } catch (err: any) {
//       console.error(err);
//       setErrorMsg(err.response?.data?.message || 'Staging engine processing failure.');
//     } finally {
//       setLoading(false);
//     }
//   };

//   const handleCommitStaging = async () => {
//     if (!selectedAccountId || !previewLines || previewLines.length === 0) return;
//     setCommitLoading(true);
//     try {
//       await api.post('/statement/commit-staging/', {
//         account_id: selectedAccountId,
//         preview_dataset: previewLines,
//         file_name: file ? file.name : "9COL_STATEMENT.PDF", 
//         strategy_used: strategyExecuted,
//         meta_summary: {
//           ...responseMeta,
//           strategy_used: strategyExecuted
//         }, 
//       });
//       setCommitSuccessMsg("Pipeline run committed to core ledger successfully.");
//       setPreviewLines([]); 
//       setResponseMeta(null); 
//       setFile(null);
//       setStrategyExecuted('');
//       setConfidenceScore(null);
//     } catch (err: any) {
//       setErrorMsg(err.response?.data?.message || 'Database commit error.');
//     } finally { setCommitLoading(false); }
//   };

//   const opening = responseMeta?.openingBalance || 0;
//   const totalCredit = responseMeta?.totalCredit || 0;
//   const totalDebit = responseMeta?.totalDebit || 0;
//   const statementClosing = responseMeta?.closingBalance || 0;
//   const calculatedClosingValue = opening + totalCredit - totalDebit;
  
//   const isBalanceVerified = responseMeta ? Math.abs(calculatedClosingValue - statementClosing) < 0.05 : false;
//   const frontendRenderCount = previewLines.length;
//   const isRowCountVerified = responseMeta ? responseMeta.count === frontendRenderCount : false;
//   const isFileFullyStale = responseMeta ? responseMeta.count === 0 : false;
//   const isDoubleTrustOk = isBalanceVerified && isRowCountVerified && !isFileFullyStale;

//   const getStrategyBadgeStyles = (strat: string) => {
//     if (strat.includes("PADDLE_OCR")) return "bg-amber-500/10 text-amber-400 border-amber-500/20";
//     if (strat.includes("UNIVERSAL_CSV")) return "bg-blue-500/10 text-blue-400 border-blue-500/20";
//     return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
//   };

//   return (
//     <div className="space-y-6 text-white p-2 text-left">
//       <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
//         <div>
//           {/* <h2 className="text-2xl font-bold tracking-tight text-emerald-400">Universal 9-Column Ingestion Pipeline</h2>
//           <p className="text-sm text-zinc-400 mt-1">Dynamic coordinate tracking processor capturing 100% of rows from multi-page JPEGs/PDFs.</p> */}
//         </div>
        
//         {strategyExecuted && (
//           <div className={`px-4 py-2 rounded-xl text-xs font-mono font-bold border flex items-center gap-2 tracking-wide shadow-md transition-all ${getStrategyBadgeStyles(strategyExecuted)}`}>
//             <span className="relative flex h-2 w-2">
//               <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-current opacity-75"></span>
//               <span className="relative inline-flex rounded-full h-2 w-2 bg-current"></span>
//             </span>
//             ACTIVE ENGINE: {strategyExecuted}
//           </div>
//         )}
//       </div>

//       {commitSuccessMsg && (
//         <div className="p-4 bg-emerald-500/10 text-emerald-400 text-sm border border-emerald-500/20 rounded-xl font-medium shadow-lg">
//           {commitSuccessMsg}
//         </div>
//       )}

//       <br/>

//       {/* 📊 Summary Reconciliation Deck */}
//       {responseMeta && (
//         <div className="space-y-4">
//           <VerificationDeck 
//             responseMeta={responseMeta}
//             previewLines={previewLines}
//             opening={opening}
//             totalDebit={totalDebit}
//             totalCredit={totalCredit}
//             statementClosing={statementClosing}
//             calculatedClosingValue={calculatedClosingValue}
//             isDoubleTrustOk={isDoubleTrustOk}
//             isBalanceVerified={isBalanceVerified}
//             isFileFullyStale={isFileFullyStale}
//             isRowCountVerified={isRowCountVerified}
//             strategyExecuted={strategyExecuted}
//             confidenceScore={confidenceScore}
//             frontendRenderCount={frontendRenderCount}
//           />
     
//         </div>
//       )}






//       <br/>
      
//       {/* 🎛️ HORIZONTAL INGESTION PIPELINE CONTROL BAR */}
//           <div className="w-full p-4 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl mb-6">
//             <div 
//               style={{ 
//                 display: 'flex', 
//                 flexDirection: 'row', 
//                 alignItems: 'flex-start', 
//                 justifyContent: 'space-between', 
//                 gap: '16px',
//                 flexWrap: 'wrap' // Gracefully drops to a double row on small tablet displays
//               }}
//             >
              
//               {/* CONTROL FIELD 1: Target Bank Account Dropdown */}
//                 <div className="flex-1 min-w-[240px]">
//                   <label className="block text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-1.5 font-mono">
//                     Target Bank Account
//                   </label>
//                   <select 
//                     value={selectedAccountId} 
//                     onChange={(e) => setSelectedAccountId(e.target.value)} 
//                     className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-xs font-mono text-zinc-200 focus:outline-none focus:border-emerald-500 h-10 transition-colors"
//                   >
//                     <option value="">-- Select Channel --</option>
//                     {accounts.map((acc) => (
//                       <option key={acc.id} value={acc.id}>
//                         💳 {acc.name} {acc.account_number ? `(•••• ${acc.account_number})` : ''}
//                       </option>
//                     ))}
//                   </select>
//                 </div>
//               </div>


           
//           </div>

//             {/* CONTROL FIELD 2: Execution Engine Dropdown (Preserved for Mapper Integration) */}
//               <div className="flex-1 min-w-[260px]">
//                 <label className="block text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-1.5 font-mono">
//                   Parsing Engine Execution Blueprint
//                 </label>
//                 <select 
//                   value={forcedTemplateId} 
//                   onChange={(e) => setForcedTemplateId(e.target.value)} // 🎯 Read/Write hooks used here!
//                   className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-xs text-emerald-400 font-mono focus:outline-none focus:border-emerald-500 h-10 transition-colors"
//                 >
//                   <option value="">⚡ [AUTOMATED ENGINE ROUTING MODE]</option>
//                   {/* 🎯 availableTemplates array mapped here! */}
//                   {availableTemplates && availableTemplates.map((t: any) => (
//                     <option key={t.id} value={t.id}>
//                       ⚙️ {t.template_name || t.name}
//                     </option>
//                   ))}
//                 </select>
//               </div>


//           {/* CONTROL FIELD 3: Compact File Drop Strip Container */}
//               <div className="flex-1 min-w-[280px]">
//                 <label className="block text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-1.5 font-mono">
//                   Statement Document (PDF or CSV)
//                 </label>
//                 <div 
//                   onDragOver={handleDragOver} 
//                   onDragLeave={handleDragLeave} 
//                   onDrop={handleDrop} 
//                   className={`border border-dashed rounded-lg px-3 flex items-center justify-between transition-all h-10 ${
//                     isDragging 
//                       ? 'border-emerald-500 bg-emerald-500/5' 
//                       : 'border-zinc-800 bg-zinc-950/40 hover:border-zinc-700'
//                   }`}
//                 >
//                   <input 
//                     type="file" 
//                     id="uniFileInput" 
//                     className="w-full text-[11px] text-zinc-400 file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-[10px] file:font-mono file:font-bold file:bg-zinc-800 file:text-emerald-400 hover:file:bg-zinc-700 cursor-pointer" 
//                     accept=".csv,.pdf" 
//                     onChange={handleFileChange} 
//                   />
//                   <span className="text-[9px] text-zinc-600 font-mono hidden xl:inline whitespace-nowrap select-none pl-2 border-l border-zinc-800/80">
//                     Drop here
//                   </span>
//                 </div>


                
//               </div>

//  {/* ⚠️ SYSTEM ERROR AND WAITING STATES CONSOLE FOOTERS */}
//             {(errorMsg || loading) && (
//               <div className="w-full pt-3 mt-3 border-t border-zinc-800/60 flex flex-col gap-2">
//                 {errorMsg && (
//                   <div className="p-2.5 bg-red-500/10 text-red-400 text-xs border border-red-500/20 rounded-lg font-mono">
//                     ⚠️ {errorMsg}
//                   </div>
//                 )}
                
//                 {loading && (
//                   <div className="p-2.5 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-lg text-xs font-mono font-bold animate-pulse text-center tracking-wide">
//                     ⏳ Processing Multi-Page Matrix Stream Data Array...
//                   </div>
//                 )}
//               </div>
//             )}

//         {/* 🚀 PERSISTENT WORKSPACE STAGING FLOOR */}
//         <div className="xl:col-span-8 p-5 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl min-h-[440px] flex flex-col">
//           <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-zinc-800 gap-4 mb-4">
//             <div>
//               <h3 className="text-sm font-bold tracking-wider text-zinc-100 uppercase font-mono">
//                Staging Floor
//               </h3>

//             </div>
            
//           {previewLines.length > 0 && (
//   <div 
//     className="self-end sm:self-auto"
//     style={{ 
//       display: 'flex', 
//       flexDirection: 'row', 
//       alignItems: 'center', 
//       gap: '12px' 
//     }}
//   >
    
//     {/* 📊 ACTION 1: EMBODIED EXCEL/CSV FILE DOWNLOAD DISPATCH */}
//     <button 
//       type="button" 
//       onClick={() => downloadWorkableCSV((window as any).__lastRawStream || "")}
//       className="px-4 flex flex-row items-center justify-center gap-2 bg-zinc-950 hover:bg-zinc-900 border border-zinc-800 hover:border-emerald-600/40 text-emerald-400 font-mono rounded-lg transition-all shadow-inner cursor-pointer"
//       style={{ height: '36px', minHeight: '36px' }}
//       title="Export Ingested Dataset as Flat CSV"
//     >
//       <span style={{ fontSize: '12px' }}>📥</span>
//       <span className="text-[10px] font-bold uppercase tracking-wider leading-none">
//         Export CSV
//       </span>
//     </button>

//     {/* 🔒 ACTION 2: PIPELINE TRANSACTION ATOMIC COMMIT ENGINE */}
//     <button 
//       type="button" 
//       onClick={handleCommitStaging} 
//       disabled={commitLoading} 
//       className={`px-4 flex flex-row items-center justify-center gap-2 border rounded-lg transition-all shadow-md select-none font-mono ${
//         commitLoading 
//           ? 'bg-zinc-800 border-zinc-700 text-zinc-500 cursor-not-allowed' 
//           : 'bg-emerald-600/10 hover:bg-emerald-600 border-emerald-500/30 hover:border-emerald-500 text-emerald-400 hover:text-white cursor-pointer'
//       }`}
//       style={{ height: '36px', minHeight: '36px' }}
//       title={commitLoading ? 'Saving Ledger Run...' : 'Save Reconciled Statement to Ledger'}
//     >
//       <span 
//         className={`${commitLoading ? 'animate-spin' : ''}`}
//         style={{ display: 'inline-flex', alignItems: 'center', fontSize: '13px', lineHeight: '1' }}
//       >
//         {commitLoading ? '⏳' : '🛡️'}
//       </span>
//       <span className="text-[10px] font-bold uppercase tracking-wider leading-none">
//         {commitLoading ? 'Saving...' : 'Commit Run'}
//       </span>
//     </button>

//   </div>
//             )}

//             </div> {/* Closes the conditional header layout sub-wrapper block cleanly */}

//             {/* 📊 DYNAMIC REVIEW PANEL TARGET AGGREGATION VIEWPORTS */}
//             {previewLines.length === 0 ? (
//               <div className="flex-1 flex items-center justify-center p-12 text-center text-xs font-mono text-zinc-600 border border-dashed border-zinc-800 rounded-lg bg-zinc-950/20">
//                 No active 9-column entries extracted into staging floor yet.
//               </div>
//             ) : (
//               /* 🚀 COMPACT GENERATOR CORE HOOK ENGINE */
//               <TableEngine 
//                 columns={LEDGER_COLUMNS} 
//                 data={previewLines} 
//                 isDuplicateRow={(row) => row.status === 'DUPLICATE'}
//               />
//             )}

//             </div> 
//             </div>
//   )}