
import React from 'react';
import { type StagedStatementItem } from '../../api/emailIngestApi';
import { FileText, Eye, Trash2, CheckCircle2, Clock } from 'lucide-react';

interface Props {
  documents: StagedStatementItem[];
  onOpenPreview: (item: StagedStatementItem) => void;
  onDeleteDocument: (item: StagedStatementItem) => void;
}

export const StatementVault: React.FC<Props> = ({
  documents,
  onOpenPreview,
  onDeleteDocument,
}) => {
  return (
    <div className="overflow-x-auto border border-zinc-800/90 rounded-xl bg-zinc-900/50 shadow-2xl">
      <table className="w-full text-left font-mono text-xs border-collapse">
        <thead>
          <tr className="border-b border-zinc-800 bg-zinc-900/90 text-zinc-400 text-[11px] select-none">
            <th className="py-3 px-4">DOCUMENT / FILENAME</th>
            <th className="py-3 px-4">ACCOUNT</th>
            <th className="py-3 px-4">AUDIT PERIOD</th>
            <th className="py-3 px-4">FILE SIZE</th>
            <th className="py-3 px-4">INGEST STATUS</th>
            <th className="py-3 px-4">COMMITTED AT</th>
            <th className="py-3 px-4 text-center">ACTIONS</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/50 text-zinc-300">
          {documents.length === 0 ? (
            <tr>
              <td colSpan={7} className="py-12 text-center text-zinc-500 font-mono">
                No committed statements found in vault inbox.
              </td>
            </tr>
          ) : (
            documents.map((doc: any) => (
              <tr key={doc.id || doc.stage_id} className="hover:bg-zinc-800/30 transition-colors">
                <td className="py-3 px-4">
                  <div className="flex items-center gap-2.5">
                    <div className="p-1.5 rounded bg-zinc-800 text-amber-400">
                      <FileText className="w-3.5 h-3.5" />
                    </div>
                    <div>
                      <div className="font-semibold text-zinc-200">{doc.bank_name}</div>
                      <div className="text-[11px] text-zinc-500 truncate max-w-sm" title={doc.filename}>
                        {doc.filename}
                      </div>
                    </div>
                  </div>
                </td>
                <td className="py-3 px-4">
                  <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded border border-emerald-500/30 bg-emerald-950/30 text-emerald-400 text-[11px] font-semibold">
                    A/c X{doc.account_hint}
                  </span>
                </td>
                <td className="py-3 px-4 text-zinc-300 whitespace-nowrap">
                  {doc.period_start && doc.period_end ? (
                    <span>
                      {doc.period_start} <span className="text-zinc-600">→</span> {doc.period_end}
                    </span>
                  ) : (
                    <span className="text-zinc-600 italic">Unspecified</span>
                  )}
                </td>
                <td className="py-3 px-4 text-zinc-400 text-[11px] whitespace-nowrap">
                  {(Number(doc.file_size || 0) / 1024).toFixed(0)} KB
                </td>
                <td className="py-3 px-4">
                  {doc.status === 'PROCESSED' ? (
                    <span className="inline-flex items-center gap-1 text-emerald-400 bg-emerald-950/50 border border-emerald-800/60 px-2 py-0.5 rounded text-[10px] font-bold">
                      <CheckCircle2 className="w-3 h-3" /> PROCESSED
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-sky-400 bg-sky-950/50 border border-sky-800/60 px-2 py-0.5 rounded text-[10px] font-bold">
                      <Clock className="w-3 h-3" /> INBOX_STAGED
                    </span>
                  )}
                </td>
                <td className="py-3 px-4 text-zinc-400 text-[11px] whitespace-nowrap">
                  {doc.created_at ? new Date(doc.created_at).toLocaleDateString() : '—'}
                </td>
                <td className="py-3 px-4 text-center">
                  <div className="flex items-center justify-center gap-2">
                    <button
                      type="button"
                      onClick={() => onOpenPreview(doc)}
                      className="p-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white transition-colors cursor-pointer"
                      title="Preview Statement PDF"
                    >
                      <Eye className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => onDeleteDocument(doc)}
                      className="p-1 rounded bg-zinc-800 hover:bg-rose-950 text-zinc-400 hover:text-rose-300 transition-colors cursor-pointer"
                      title="Remove Record"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
};