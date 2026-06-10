// src/components/upload/StatementUpload.tsx
import React, { useState, useRef } from 'react';
import api from '../../api/client';

export default function StatementUpload() {
  const [dragActive, setDragActive] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedBank, setSelectedBank] = useState('');
  const [statusMsg, setStatusMsg] = useState({ text: '', isError: false });
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 🖱️ Intercept standard browser drag overlays
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  // 🫳 Intercept the manual drop actions
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  // 📂 Intercept standard click-to-file selections
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  const validateAndSetFile = (selectedFile: File) => {
    const extension = selectedFile.name.split('.').pop()?.toLowerCase();
    if (extension === 'pdf' || extension === 'csv' || extension === 'xlsx') {
      setFile(selectedFile);
      setStatusMsg({ text: '', isError: false });
    } else {
      setStatusMsg({ text: 'Unsupported format. Please supply a clean PDF, CSV, or XLSX statement file.', isError: true });
    }
  };

  // 🚀 SHIP PAYLOAD: Dispatch the raw multi-part form file binaries straight to Django
  const processStatement = async () => {
    if (!file || !selectedBank) {
      setStatusMsg({ text: 'Please choose the corresponding bank layout anchor first.', isError: true });
      return;
    }

    setLoading(true);
    setStatusMsg({ text: '', isError: false });

    const formData = new FormData();
    formData.append('statement_file', file);
    formData.append('bank_name', selectedBank);

    try {
      // We will map this backend processing URL path next!
      const response = await api.post('/parse-statement/', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      setStatusMsg({ text: `Success! Processed ${response.data.count || 0} multi-line transactions into your double-entry ledger.`, isError: false });
      setFile(null);
    } catch (err: any) {
      setStatusMsg({ 
        text: err.response?.data?.message || 'The ingestion engine encountered an issue parsing this file format pattern.', 
        isError: true 
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-xl font-bold text-white">Statement Ingestion Clearinghouse</h3>
        <p className="text-sm text-zinc-400 mt-1">
          Drop your unformatted, password-locked bank statements here. Our parser handles multiline descriptions and automatically extracts balanced entries.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Control Side Inputs panel */}
        <div className="bg-zinc-950 p-5 rounded-xl border border-zinc-800 space-y-4 h-fit">
          <h4 className="text-xs font-mono uppercase text-emerald-400 tracking-wider">Pipeline Controllers</h4>
          
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">Target Formatting Template</label>
            <select
              value={selectedBank}
              onChange={(e) => setSelectedBank(e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
            >
             <option value="">Auto-Detect Layout Strategy...</option>
    <option value="SBI_GENERIC">SBI (Adaptive Auto-Matcher)</option>
    <option value="HDFC_CC">HDFC Consolidated Statement</option>
            </select>
          </div>

          {file && (
            <div className="bg-zinc-900/50 p-3 rounded-lg border border-zinc-800 text-xs flex flex-col gap-1">
              <span className="text-zinc-500 block font-mono uppercase tracking-tight text-[10px]">Staged Binary Asset:</span>
              <span className="text-white font-medium truncate font-mono">{file.name}</span>
              <span className="text-zinc-400 font-mono">{(file.size / 1024).toFixed(1)} KB</span>
            </div>
          )}

          <button
            onClick={processStatement}
            disabled={loading || !file}
            className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:hover:bg-emerald-600 text-white text-sm font-medium py-2 rounded-lg transition shadow-md shadow-emerald-950/20"
          >
            {loading ? 'Executing "Magic" Ingestion...' : 'Process Statement File'}
          </button>

          {statusMsg.text && (
            <div className={`p-3 text-xs font-medium rounded-lg border ${statusMsg.isError ? 'bg-red-950/30 text-red-400 border-red-900/40' : 'bg-emerald-950/30 text-emerald-400 border-emerald-900/40'}`}>
              {statusMsg.text}
            </div>
          )}
        </div>

        {/* The Drag & Drop Workspace Matrix Zone */}
        <div className="md:col-span-2">
          <div
            onDragEnter={handleDrag}
            onDragOver={handleDrag}
            onDragLeave={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`w-full h-64 border-2 border-dashed rounded-xl flex flex-col justify-center items-center p-6 text-center transition duration-200 cursor-pointer select-none ${
              dragActive 
                ? 'border-emerald-500 bg-emerald-950/10' 
                : file 
                  ? 'border-zinc-700 bg-zinc-900/20' 
                  : 'border-zinc-800 bg-zinc-900/40 hover:border-zinc-700 hover:bg-zinc-900/60'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.csv,.xlsx"
              className="hidden"
              onChange={handleFileChange}
            />
            
            <div className="w-12 h-12 rounded-full bg-zinc-800/80 border border-zinc-700 flex items-center justify-center text-xl mb-4 shadow-sm shadow-black">
              {file ? '📄' : '📥'}
            </div>

            {file ? (
              <div>
                <p className="text-sm font-semibold text-emerald-400">File attached successfully!</p>
                <p className="text-xs text-zinc-400 mt-1">Click or drag another target profile asset sheet to change selection parameters.</p>
              </div>
            ) : (
              <div>
                <p className="text-sm font-medium text-zinc-200">Drag & drop your statement asset profile anywhere here</p>
                <p className="text-xs text-zinc-500 mt-1.5 font-mono">Accepts native PDF, bank .CSV exports, or unformatted Excel tables</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}