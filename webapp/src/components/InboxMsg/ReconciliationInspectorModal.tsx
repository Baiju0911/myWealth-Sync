import React from 'react';
import { type EnrichedAuditRecord } from '../../api/statementInboxApi';

interface ReconciliationInspectorModalProps {
  record: EnrichedAuditRecord | null;
  onClose: () => void;
}

export const ReconciliationInspectorModal: React.FC<ReconciliationInspectorModalProps> = ({ record, onClose }) => {
  if (!record) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 text-left">
      <div className="relative w-full max-w-2xl rounded-xl border border-zinc-800 bg-zinc-950 p-6 text-zinc-200 shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-800 pb-4">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400 font-bold border border-emerald-500/20">
              🛡️
            </span>
            <div>
              <h3 className="text-sm font-semibold text-zinc-100 font-mono">
                Dual-Stream Reconciliation Inspector
              </h3>
              <p className="text-xs text-zinc-500 font-mono">
                Statement Line ID: <span className="text-zinc-400">{record.statement_id}</span>
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition cursor-pointer"
          >
            ✕
          </button>
        </div>

        <div className="mt-4 space-y-4 max-h-[75vh] overflow-y-auto pr-1 font-mono text-xs">
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3 space-y-1">
              <span className="text-emerald-500 block uppercase tracking-wider text-[10px] font-bold">
                🏦 Physical Bank Statement
              </span>
              <div>Date: <span className="text-zinc-200 font-bold">{record.statement_date}</span></div>
              <div>Bank: <span className="text-zinc-200">{record.bank_name}</span></div>
              <div>Account: <span className="text-zinc-200">•••• {record.account_last4}</span></div>
              <div>
                Amount:{' '}
                <span className="text-emerald-400 font-bold">
                  ₹{Number(record.statement_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
              </div>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3 space-y-1">
              <span className="text-purple-400 block uppercase tracking-wider text-[10px] font-bold">
                📡 Donor Stream Alert
              </span>
              <div>Rail: <span className="text-purple-300 font-bold">{record.stream_source}</span></div>
              <div>Merchant: <span className="text-zinc-200 font-bold">{record.resolved_merchant}</span></div>
              <div>RRN: <span className="text-purple-400 font-bold">{record.live_upi_rrn}</span></div>
              <div>
                Enriched At:{' '}
                <span className="text-zinc-400 text-[11px]">
                  {record.enriched_at ? new Date(record.enriched_at).toLocaleTimeString() : '-'}
                </span>
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3 space-y-2">
            <span className="text-zinc-500 block uppercase tracking-wider text-[10px] font-bold">
              🔄 Narration Transformation
            </span>
            <div className="bg-zinc-950 p-2.5 rounded border border-zinc-800 space-y-1 text-[11px]">
              <div>
                <span className="text-zinc-500">Original: </span>
                <span className="text-zinc-300">{record.raw_narration}</span>
              </div>
              <div>
                <span className="text-emerald-500 font-bold">Resolved Payee: </span>
                <span className="text-emerald-300 font-bold">{record.resolved_merchant}</span>
              </div>
            </div>
          </div>

          {record.has_warning && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-amber-300 text-xs">
              ⚠️ Note: Enriched with single-digit decimal / paise variance tolerance.
            </div>
          )}
        </div>

        <div className="mt-5 flex items-center justify-between border-t border-zinc-800 pt-3 font-mono">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-medium text-emerald-400 border border-emerald-500/20">
            ⚡ Matched & Permanently Enriched
          </span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-zinc-800 px-4 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-700 transition cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};