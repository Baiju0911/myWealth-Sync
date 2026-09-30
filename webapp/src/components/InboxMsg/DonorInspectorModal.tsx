import React, { useState } from 'react';
import {
  Zap,
  Clock,
  FileText,
  Copy,
  Check,
  Tag,
  Hash,
  ArrowUpRight,
  ArrowDownLeft,
  Smartphone,
  Calendar,
} from 'lucide-react';
import { type LiveStreamPayloadItem } from '../ui/data-table/columns';

export type ExtendedPayloadItem = Partial<LiveStreamPayloadItem> & {
  id: string;
  sender?: string | null;
  raw_body?: string | null;
  decrypted_body?: string | null;
  clean_beneficiary?: string | null;
  direction?: string | null;
  payment_protocol?: string | null;
  balance?: number | string | null;
  txn_fingerprint?: string | null;
  txn_date?: string | null;
  amount?: number | string | null;
  bank_name?: string | null;
  account_last4?: string | null;
  upi_ref?: string | null;
  merchant?: string | null;
  full_narration?: string | null;
  source?: string | null;
  created_at?: string | null;
};

interface DonorInspectorModalProps {
  payload: ExtendedPayloadItem | null;
  onClose: () => void;
}

export const DonorInspectorModal: React.FC<DonorInspectorModalProps> = ({ payload, onClose }) => {
  const [copied, setCopied] = useState<string | null>(null);
  if (!payload) return null;

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 1500);
  };

  const rawMerchant = (payload.merchant || '').trim();
  let cleanMerchant = rawMerchant;
  let isMandate = false;
  if (/NETFLIX/i.test(rawMerchant)) {
    cleanMerchant = 'NETFLIX';
    isMandate = true;
  } else if (/AUTO (FOR|PAY)/i.test(rawMerchant)) {
    const parts = rawMerchant.split(/AUTO (?:FOR|PAY) (?:FOR )?/i);
    if (parts[1]) cleanMerchant = parts[1].split(' ')[0];
    isMandate = true;
  }

  const authenticBody =
    payload.raw_body ||
    payload.decrypted_body ||
    (payload.full_narration && payload.full_narration !== 'UPI/REF/Direct Payment' ? payload.full_narration : '') ||
    payload.merchant ||
    '';

  const scheduledMatch = authenticBody.match(/scheduled on\s+([0-9]{1,2}[\/\-][0-9]{1,2}[\/\-][0-9]{2,4})/i);
  const scheduledDate = scheduledMatch ? scheduledMatch[1] : payload.txn_date;

  const isDebit = payload.direction ? payload.direction.toUpperCase() === 'DEBIT' : true;
  const formattedAmount = isNaN(Number(payload.amount))
    ? payload.amount
    : Number(payload.amount).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm p-4 animate-in fade-in duration-150">
      <div className="relative w-full max-w-2xl rounded-2xl border border-neutral-800 bg-[#0d0f12] p-6 shadow-2xl text-neutral-200">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b border-neutral-800 pb-4 mb-4">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-purple-950/70 p-2.5 border border-purple-500/30">
              <Zap className="h-6 w-6 text-purple-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-neutral-100">
                  Live Donor Stream Inspector
                </h2>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-950/80 border border-purple-500/40 text-purple-300 font-bold">
                  {payload.source || 'LIVE_ALERT'}
                </span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-950/70 border border-amber-600/40 text-amber-300 font-semibold">
                  ⚡ STAGED (AWAITING MATCH)
                </span>
              </div>
              <p className="text-xs font-mono text-neutral-500 mt-0.5 flex items-center gap-2">
                Payload UUID: <span className="text-neutral-300">{payload.id}</span>
                <button
                  onClick={() => handleCopy(payload.id, 'id')}
                  className="text-neutral-500 hover:text-neutral-300 cursor-pointer"
                  title="Copy ID"
                >
                  {copied === 'id' ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3 text-neutral-400" />}
                </button>
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100 transition cursor-pointer"
          >
            ✕
          </button>
        </div>

        {/* Financial & Telecom Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mb-4">
          <div className="rounded-xl border border-neutral-800/80 bg-neutral-900/40 p-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-mono uppercase tracking-wider text-neutral-500">Amount</span>
              <span className={`inline-flex items-center text-[9px] font-bold font-mono px-1 py-0.2 rounded ${
                isDebit ? 'bg-rose-950/60 text-rose-300 border border-rose-800/40' : 'bg-emerald-950/60 text-emerald-300 border border-emerald-800/40'
              }`}>
                {isDebit ? <ArrowUpRight className="h-2.5 w-2.5 mr-0.5" /> : <ArrowDownLeft className="h-2.5 w-2.5 mr-0.5" />}
                {isDebit ? 'DEBIT' : 'CREDIT'}
              </span>
            </div>
            <span className="text-base font-mono font-bold text-emerald-400">
              ₹{formattedAmount}
            </span>
          </div>

          <div className="rounded-xl border border-neutral-800/80 bg-neutral-900/40 p-3">
            <span className="text-[10px] font-mono uppercase tracking-wider text-neutral-500 block mb-1">Sender Route</span>
            <div className="flex items-center gap-1 text-xs font-semibold text-neutral-200 truncate">
              <Smartphone className="h-3.5 w-3.5 text-purple-400 shrink-0" />
              <span>{payload.sender || 'SIBSMS-S'}</span>
            </div>
            <span className="text-[10px] text-neutral-500 block truncate mt-0.5">
              {payload.bank_name || 'South Indian Bank'}
            </span>
          </div>

          <div className="rounded-xl border border-neutral-800/80 bg-neutral-900/40 p-3">
            <span className="text-[10px] font-mono uppercase tracking-wider text-neutral-500 block mb-1">Rail Ref (RRN)</span>
            <span className="font-mono text-xs font-bold text-cyan-300">
              {payload.upi_ref || 'NO_RRN'}
            </span>
            <span className="text-[10px] text-neutral-500 block mt-0.5">
              {payload.upi_ref ? 'Tier 1 Anchor' : 'Hex Fingerprint'}
            </span>
          </div>

          <div className="rounded-xl border border-neutral-800/80 bg-neutral-900/40 p-3">
            <span className="text-[10px] font-mono uppercase tracking-wider text-neutral-500 block mb-1">Effective Date</span>
            <div className="flex items-center gap-1 text-xs font-mono text-neutral-200">
              <Calendar className="h-3.5 w-3.5 text-neutral-400 shrink-0" />
              <span>{scheduledDate || (payload.created_at ? new Date(payload.created_at).toLocaleDateString('en-GB') : 'Recent')}</span>
            </div>
            <span className="text-[10px] text-neutral-500 block mt-0.5">
              {scheduledDate ? 'Mandate Scheduled' : 'Ingest Timestamp'}
            </span>
          </div>
        </div>

        {/* Harvested Payee Resolution */}
        <div className="rounded-xl border border-neutral-800 bg-neutral-900/30 p-3.5 mb-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2 text-[11px] font-semibold text-neutral-400 uppercase tracking-wider">
              <Tag className="h-3.5 w-3.5 text-neutral-400" />
              Extracted Merchant / Payee
            </div>
            {isMandate && (
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-purple-950/70 border border-purple-500/40 text-purple-300">
                🔄 Recurring Mandate Auto-Debit
              </span>
            )}
          </div>
          <div className="flex items-center justify-between p-2.5 rounded-lg bg-neutral-950/80 border border-neutral-800/80">
            <div>
              <span className="text-[10px] text-neutral-500 block uppercase">Cleaned Beneficiary</span>
              <span className="text-sm font-bold text-purple-300">{cleanMerchant}</span>
            </div>
            {payload.payment_protocol && (
              <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-neutral-900 border border-neutral-800 text-neutral-300">
                {payload.payment_protocol}
              </span>
            )}
          </div>
        </div>

        {/* Authentic Ingested SMS / Email Body */}
        <div className="rounded-xl border border-neutral-800 bg-neutral-900/40 p-3.5 mb-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2 text-[11px] font-semibold text-neutral-400 uppercase tracking-wider">
              <FileText className="h-3.5 w-3.5 text-neutral-400" />
              Authentic Alert Message Payload
            </div>
            <button
              onClick={() => handleCopy(authenticBody, 'body')}
              className="text-[10px] font-mono text-neutral-400 hover:text-neutral-200 flex items-center gap-1 cursor-pointer"
            >
              {copied === 'body' ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3 text-neutral-400" />}
              <span>Copy Message</span>
            </button>
          </div>
          <div className="rounded-lg bg-black/60 p-3 text-xs font-mono text-neutral-300 border border-neutral-800/80 wrap-break-word leading-relaxed max-h-32 overflow-y-auto">
            {authenticBody}
          </div>
        </div>

        {/* Hex Fingerprint Hash */}
        {payload.txn_fingerprint && (
          <div className="rounded-lg bg-neutral-950/60 border border-neutral-800/60 p-2.5 mb-4 flex items-center justify-between text-[11px] font-mono text-neutral-500">
            <span className="flex items-center gap-1.5 shrink-0">
              <Hash className="h-3 w-3 text-neutral-400" /> Match Hash:
            </span>
            <span className="truncate max-w-90 text-neutral-400" title={payload.txn_fingerprint}>
              {payload.txn_fingerprint}
            </span>
            <button
              onClick={() => handleCopy(payload.txn_fingerprint || '', 'hash')}
              className="hover:text-neutral-200 cursor-pointer ml-2"
              title="Copy Hash"
            >
              {copied === 'hash' ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3 text-neutral-400" />}
            </button>
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between pt-2 border-t border-neutral-800">
          <div className="flex items-center gap-2 text-xs text-amber-400/90 font-medium">
            <Clock className="h-4 w-4" />
            <span>Standing by in memory for physical statement matching</span>
          </div>
          <button
            onClick={onClose}
            className="rounded-xl bg-neutral-800 hover:bg-neutral-700 px-5 py-2 text-xs font-semibold text-neutral-100 transition cursor-pointer"
          >
            Close
          </button>
        </div>

      </div>
    </div>
  );
};