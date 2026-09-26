import React from 'react';
import { type LiveStreamPayloadItem } from '../ui/data-table/columns';

interface DonorInspectorModalProps {
  payload: LiveStreamPayloadItem | null;
  onClose: () => void;
}

export const DonorInspectorModal: React.FC<DonorInspectorModalProps> = ({ payload, onClose }) => {
  if (!payload) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 text-left">
      <div className="relative w-full max-w-2xl rounded-xl border border-zinc-800 bg-zinc-950 p-6 text-zinc-200 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-zinc-800 pb-4">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-purple-500/10 text-purple-400 font-bold border border-purple-500/20">
              ⚡
            </span>
            <div>
              <h3 className="text-sm font-semibold text-zinc-100 font-mono">
                Donor Ingest Inspector (Uncommitted Stream)
              </h3>
              <p className="text-xs text-zinc-500 font-mono">
                Payload ID: <span className="text-zinc-400">{payload.id}</span>
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
          {/* Metadata Badges: 4-Column Grid with Dual Dates */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-2.5">
              <span className="text-amber-500/80 block uppercase tracking-wider text-[10px] font-bold">
                Bank Txn Date
              </span>
              <span className="font-semibold text-amber-300">
                {payload.txn_date || 'Same Day'}
              </span>
            </div>
<div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2.5">
  <span className="text-zinc-500 block uppercase tracking-wider text-[10px]">
    Alert Ingested
  </span>
  <div className="font-semibold text-zinc-300 text-[11px] leading-tight">
    <div>{payload.created_at ? new Date(payload.created_at).toLocaleDateString('en-GB') : '-'}</div>
    <div className="text-[10px] text-zinc-500">
      {payload.created_at ? new Date(payload.created_at).toLocaleTimeString('en-GB') : ''}
    </div>
  </div>
</div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2.5">
              <span className="text-zinc-500 block uppercase tracking-wider text-[10px]">
                Payment Protocol
              </span>
              <span className={`font-semibold ${payload.direction === 'CREDIT' ? 'text-emerald-400' : 'text-cyan-400'}`}>
                {payload.payment_protocol || 'TRANSFER'}
              </span>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2.5">
              <span className="text-zinc-500 block uppercase tracking-wider text-[10px]">
                Source Rail
              </span>
              <span className="font-semibold text-purple-400">{payload.source}</span>
            </div>
          </div>

          {/* Sender & Subject */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-2.5 space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-zinc-500 text-[10px] uppercase">Sender:</span>
              <span className="text-zinc-300 font-semibold">{payload.sender || 'System Gateway'}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-zinc-500 text-[10px] uppercase">Subject:</span>
              <span className="text-zinc-300 truncate">{payload.subject || 'NO_SUBJECT'}</span>
            </div>
          </div>

          {/* Raw Body Evidence */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
            <span className="text-zinc-500 block uppercase tracking-wider text-[10px] mb-1">
              Raw Alert Body (Source Evidence)
            </span>
            <p className="font-mono text-xs text-zinc-300 leading-relaxed whitespace-pre-wrap break-words bg-zinc-950 p-2.5 rounded border border-zinc-800">
              {payload.raw_body || payload.full_narration || 'No raw body captured.'}
            </p>
          </div>

          {/* Smart Extracted Attributes */}
          <div className="rounded-lg border border-emerald-900/30 bg-emerald-950/10 p-3.5 space-y-2">
            <div className="flex items-center justify-between text-emerald-400 text-xs font-medium mb-1">
              <div className="flex items-center gap-1.5">
                <span>✨</span>
                <span>Smart Extracted Attributes (Ready for Staging)</span>
              </div>
              <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                Verified
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="bg-zinc-900 p-2 rounded border border-zinc-800">
                <span className="text-zinc-500 text-[10px] block">
                  {payload.amount_label || 'Target Amount'}
                </span>
                <span className={`font-bold text-sm ${payload.direction === 'CREDIT' ? 'text-emerald-400' : 'text-zinc-100'}`}>
                  ₹{Number(payload.amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
              </div>

              <div className="bg-zinc-900 p-2 rounded border border-zinc-800">
                <span className="text-zinc-500 text-[10px] block">Post-Txn Available Balance</span>
                <span className="font-bold text-emerald-300 text-sm">
                  {payload.balance
                    ? `₹${Number(payload.balance).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
                    : 'Not Reported'}
                </span>
              </div>

              <div className="bg-zinc-900 p-2 rounded border border-zinc-800">
                <span className="text-zinc-500 text-[10px] block">Target Account</span>
                <span className="font-bold text-zinc-200">
                  {payload.bank_name || 'Bank'} {payload.account_last4 ? `•••• ${payload.account_last4}` : ''}
                </span>
              </div>

              <div className="bg-zinc-900 p-2 rounded border border-zinc-800">
                <span className="text-zinc-500 text-[10px] block">UPI Ref / RRN Anchor</span>
                <span className="text-purple-400 font-bold">{payload.upi_ref || 'None Detected'}</span>
              </div>
            </div>

            {/* Resolved Payee Card */}
            <div className="bg-zinc-900 p-2.5 rounded border border-zinc-800 flex items-center justify-between">
              <div>
                <span className="text-zinc-500 text-[10px] block uppercase">Clean Beneficiary / Payee</span>
                <span className="text-zinc-100 font-bold text-sm">
                  {payload.clean_beneficiary || payload.merchant || 'None'}
                </span>
              </div>
              <span className="text-[10px] text-zinc-500">Auto-Cleaned</span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-5 flex items-center justify-between border-t border-zinc-800 pt-3 font-mono">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-purple-500/10 px-2.5 py-0.5 text-[11px] font-medium text-purple-400 border border-purple-500/20">
            ● Status: {payload.status} (Staged for Matching)
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