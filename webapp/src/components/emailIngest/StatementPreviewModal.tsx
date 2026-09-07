import React, { useState, useEffect } from 'react';
import { type StagedStatementItem, emailIngestApi } from '../../api/emailIngestApi';
import { Lock, FileText, CheckCircle, XCircle, AlertCircle } from 'lucide-react';

interface Props {
  statement: StagedStatementItem | null;
  onClose: () => void;
  onConfirm: (stageId: string) => void;
  onDeselect: (stageId: string) => void;
}

export const StatementPreviewModal: React.FC<Props> = ({
  statement,
  onClose,
  onConfirm,
  onDeselect,
}) => {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [password, setPassword] = useState<string>('');
  const [isEncrypted, setIsEncrypted] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const loadPdf = async (pwd?: string) => {
    if (!statement) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const blob = await emailIngestApi.previewStagedPdf(statement.file_path, pwd);
      const url = URL.createObjectURL(blob);
      setBlobUrl(url);
      setIsEncrypted(false);
    } catch (err: any) {
      if (err?.response?.status === 423) {
        setIsEncrypted(true);
        setErrorMsg(pwd ? 'Invalid password. Please re-enter.' : 'This PDF statement is password-protected.');
      } else {
        setErrorMsg('Failed to render PDF document.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (statement) {
      setPassword('');
      setBlobUrl(null);
      loadPdf();
    }
    return () => {
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [statement]);

  if (!statement) return null;

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-in fade-in duration-200">
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl max-w-5xl w-full h-[88vh] flex flex-col shadow-2xl overflow-hidden font-mono text-xs">
        
        {/* Header */}
        <div className="flex justify-between items-center px-5 py-3.5 border-b border-zinc-800 bg-zinc-950/80">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400">
              <FileText className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-zinc-100 flex items-center gap-2">
                <span>{statement.bank_name}</span>
                <span className="text-[10px] text-zinc-500 bg-zinc-800 px-2 py-0.5 rounded">
                  A/c {statement.account_hint}
                </span>
              </h3>
              <p className="text-[11px] text-zinc-400 truncate max-w-md" title={statement.filename}>
                {statement.filename}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-200 font-bold px-2 py-1 rounded transition-colors cursor-pointer text-base"
          >
            ✕
          </button>
        </div>

        {/* Modal Body / Viewer */}
        <div className="flex-1 bg-zinc-950 flex flex-col items-center justify-center relative overflow-hidden">
          {loading && (
            <div className="flex flex-col items-center gap-3 text-zinc-400 font-mono">
              <span className="h-6 w-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
              <span>Decrypting & Loading PDF stream...</span>
            </div>
          )}

          {/* Password Prompt */}
          {!loading && isEncrypted && (
            <div className="bg-zinc-900 border border-zinc-800 p-6 rounded-xl max-w-sm w-full mx-4 shadow-xl space-y-4">
              <div className="flex items-center gap-3 text-amber-400">
                <Lock className="w-5 h-5" />
                <h4 className="font-bold text-sm">Protected PDF Statement</h4>
              </div>

              <p className="text-zinc-400 text-[11px] leading-relaxed">
                Bank statements commonly use your date of birth (e.g. <code className="text-zinc-300">DDMMYYYY</code>) or last 4 digits of PAN/Card.
              </p>

              {errorMsg && (
                <div className="bg-rose-950/40 border border-rose-800/80 text-rose-300 p-2 rounded text-[11px] flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{errorMsg}</span>
                </div>
              )}

              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  loadPdf(password);
                }}
                className="space-y-3"
              >
                <input
                  type="password"
                  placeholder="Enter statement password..."
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-700 text-zinc-200 px-3 py-2 rounded focus:outline-none focus:border-amber-500 font-mono"
                  autoFocus
                />
                <button
                  type="submit"
                  className="w-full bg-amber-600 hover:bg-amber-500 text-zinc-950 font-bold py-2 rounded transition-colors cursor-pointer"
                >
                  Unlock Document
                </button>
              </form>
            </div>
          )}

          {/* Render PDF Iframe */}
          {!loading && !isEncrypted && blobUrl && (
            <iframe
              src={`${blobUrl}#toolbar=0&navpanes=0`}
              className="w-full h-full border-none"
              title="Statement Preview"
            />
          )}
        </div>

        {/* Footer Review Bar */}
        <div className="px-5 py-3 border-t border-zinc-800 bg-zinc-950 flex justify-between items-center">
          <div className="text-[11px] text-zinc-500">
            Period: <span className="text-zinc-300 font-medium">{statement.period_start || '—'}</span> to <span className="text-zinc-300 font-medium">{statement.period_end || '—'}</span>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                onDeselect(statement.stage_id);
                onClose();
              }}
              className="px-3.5 py-1.5 rounded-lg border border-zinc-700 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors flex items-center gap-1.5 cursor-pointer"
            >
              <XCircle className="w-4 h-4 text-rose-400" />
              <span>Exclude from Batch</span>
            </button>

            <button
              onClick={() => {
                onConfirm(statement.stage_id);
                onClose();
              }}
              className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold transition-all shadow-md shadow-emerald-950 flex items-center gap-1.5 cursor-pointer"
            >
              <CheckCircle className="w-4 h-4" />
              <span>Confirm & Keep</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};