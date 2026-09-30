import React, { useState } from 'react';
import {
  ShieldCheck,
  ArrowRight,
  Zap,
  CheckCircle2,
  FileText,
  Database,
  GitMerge,
  Copy,
  Check,
  Tag,
  Wallet,
  ArrowUpRight,
  ArrowDownLeft,
} from 'lucide-react';
import { type EnrichedAuditRecord } from '../../api/statementInboxApi';

interface ExtendedAuditRecord extends EnrichedAuditRecord {
  running_balance?: number | null;
  debit?: number | null;
  credit?: number | null;
  remark?: string | null;
  resolved_narration?: string | null;
  routing_status?: string;
}

interface ReconciliationInspectorModalProps {
  record: ExtendedAuditRecord | null;
  onClose: () => void;
}

export const ReconciliationInspectorModal: React.FC<ReconciliationInspectorModalProps> = ({
  record,
  onClose,
}) => {
  const [copied, setCopied] = useState(false);
  if (!record) return null;

  const handleCopyId = (val: string) => {
    navigator.clipboard.writeText(val);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const formatEnrichedTime = (rawTs?: string | null) => {
    if (!rawTs || rawTs === '-') return 'N/A';
    try {
      const parsed = new Date(rawTs);
      return isNaN(parsed.getTime())
        ? rawTs
        : parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return rawTs;
    }
  };

  const isDebit = record.debit !== null && record.debit !== undefined ? Number(record.debit) > 0 : true;
  const matchTier = (record as any).match_tier || (record.live_upi_rrn ? 'TIER 1 (RRN Exact Match)' : 'TIER 2 (Hex Fingerprint)');
  const remark = (record as any).remark;
  const payloadId = (record as any).payload_id;

  // Extract routing bank handle from narration (e.g., CBIN from UPI/CBIN/...)
  const routeBankMatch = record.raw_narration?.match(/UPI\/([A-Z0-9]+)\//i);
  const routeBank = routeBankMatch ? routeBankMatch[1] : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm p-4 animate-in fade-in duration-150">
      <div className="relative w-full max-w-3xl rounded-2xl border border-neutral-800 bg-[#0d0f12] p-6 shadow-2xl text-neutral-200">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b border-neutral-800 pb-4 mb-4">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-emerald-950/70 p-2.5 border border-emerald-500/30">
              <ShieldCheck className="h-6 w-6 text-emerald-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-neutral-100">
                  Dual-Stream Reconciliation & Auto-Sweep Inspector
                </h2>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-950/70 border border-cyan-500/40 text-cyan-300 font-bold">
                  {matchTier}
                </span>
              </div>
              <p className="text-xs font-mono text-neutral-500 mt-0.5 flex items-center gap-2">
                Statement Line ID: <span className="text-neutral-300">{record.statement_id}</span>
                <button
                  onClick={() => handleCopyId(record.statement_id)}
                  className="text-neutral-500 hover:text-neutral-300 cursor-pointer"
                  title="Copy ID"
                >
                  {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
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

        {/* 2-Column Proof Comparison */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
          
          {/* Card 1: Bank Statement Physical Truth */}
          <div className="rounded-xl border border-neutral-800/80 bg-neutral-900/40 p-4">
            <div className="flex items-center justify-between mb-2.5">
              <div className="flex items-center gap-2 text-[11px] font-semibold text-emerald-400 uppercase tracking-wider">
                <Database className="h-3.5 w-3.5" />
                Physical Bank Statement
              </div>
              <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold font-mono ${
                isDebit ? 'bg-rose-950/60 text-rose-300 border border-rose-800/40' : 'bg-emerald-950/60 text-emerald-300 border border-emerald-800/40'
              }`}>
                {isDebit ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownLeft className="h-3 w-3" />}
                {isDebit ? 'DEBIT' : 'CREDIT'}
              </span>
            </div>

            <div className="space-y-1.5 text-xs">
              <div className="flex justify-between">
                <span className="text-neutral-500">Date:</span>
                <span className="font-mono text-neutral-200">{record.statement_date}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Bank:</span>
                <span className="text-neutral-200 font-medium">{record.bank_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Account:</span>
                <span className="font-mono text-neutral-200">•••• {record.account_last4}</span>
              </div>
              <div className="flex justify-between pt-1 border-t border-neutral-800/80">
                <span className="text-neutral-500">Amount:</span>
                <span className={`font-mono font-bold text-sm ${isDebit ? 'text-rose-400' : 'text-emerald-400'}`}>
                  ₹{Number(record.statement_amount).toFixed(2)}
                </span>
              </div>
              {record.running_balance !== null && record.running_balance !== undefined && (
                <div className="flex justify-between items-center pt-1 text-[11px] text-neutral-400">
                  <span className="flex items-center gap-1 text-neutral-500">
                    <Wallet className="h-3 w-3" /> Post Balance:
                  </span>
                  <span className="font-mono text-cyan-300 font-semibold">
                    ₹{Number(record.running_balance).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Card 2: Donor Stream Evidence */}
          <div className="rounded-xl border border-neutral-800/80 bg-neutral-900/40 p-4">
            <div className="flex items-center justify-between mb-2.5">
              <div className="flex items-center gap-2 text-[11px] font-semibold text-purple-400 uppercase tracking-wider">
                <Zap className="h-3.5 w-3.5" />
                Donor Alert Stream
              </div>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-purple-950/70 border border-purple-500/40 text-purple-300">
                {record.stream_source}
              </span>
            </div>

            <div className="space-y-1.5 text-xs">
              <div className="flex justify-between">
                <span className="text-neutral-500">Beneficiary:</span>
                <span className="font-semibold text-neutral-100">{record.resolved_merchant}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Rail Ref (RRN):</span>
                <span className="font-mono text-cyan-300 font-bold">{record.live_upi_rrn || 'N/A'}</span>
              </div>
              {routeBank && (
                <div className="flex justify-between">
                  <span className="text-neutral-500">Route Protocol:</span>
                  <span className="font-mono text-neutral-300">{routeBank} UPI Rail</span>
                </div>
              )}
              <div className="flex justify-between pt-1 border-t border-neutral-800/80">
                <span className="text-neutral-500">Alert Synced:</span>
                <span className="font-mono text-neutral-400">{formatEnrichedTime(record.enriched_at)}</span>
              </div>
              {payloadId && (
                <div className="flex justify-between items-center pt-1 text-[10px] font-mono text-neutral-500">
                  <span>Donor Payload:</span>
<span className="truncate max-w-32.5 text-neutral-400" title={payloadId}>                    {payloadId.slice(0, 8)}...{payloadId.slice(-4)}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Narration Transformation & Clean Entity Resolution */}
        <div className="rounded-xl border border-neutral-800 bg-neutral-900/30 p-3.5 mb-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2 text-[11px] font-semibold text-neutral-400 uppercase tracking-wider">
              <FileText className="h-3.5 w-3.5 text-neutral-400" />
              Narration & Identity Resolution
            </div>
            {remark && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono bg-cyan-950/60 border border-cyan-800/50 text-cyan-300">
                <Tag className="h-3 w-3" />
                Remark: <strong className="text-cyan-200">{remark}</strong>
              </span>
            )}
          </div>

          <div className="space-y-2 text-xs font-mono">
            {/* Raw Narration */}
            <div className="rounded-lg bg-black/60 p-2.5 text-neutral-300 border border-neutral-800/80 break-all leading-relaxed">
              <span className="text-neutral-500 select-none mr-2">RAW:</span>
              {record.raw_narration}
            </div>

            {/* Resolved Payee Entity */}
            <div className="flex flex-wrap items-center justify-between gap-2 p-2 rounded-lg bg-neutral-950/80 border border-neutral-800/60">
              <div className="flex items-center gap-2">
                <ArrowRight className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                <span className="text-neutral-500">Resolved Payee:</span>
                <span className="font-bold text-emerald-400 text-sm">
                  {record.resolved_merchant}
                </span>
              </div>
              <span className="text-[10px] text-emerald-400/80 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-800/40">
                Cleaned Entity
              </span>
            </div>
          </div>
        </div>

        {/* Step 2 Auto-Sweep / Node 99 Status */}
        {record.classification && (
          <div className="rounded-xl border border-cyan-900/40 bg-cyan-950/15 p-3 mb-3">
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-2 text-[11px] font-semibold text-cyan-400 uppercase tracking-wider">
                <GitMerge className="h-3.5 w-3.5" />
                Ledger Sweep: Node 99 → Target Account
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-500/30">
                {record.classification.status}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <span className="text-neutral-500 block text-[11px]">Destination Category:</span>
                <span className="font-semibold text-neutral-100">{record.classification.target_account}</span>
              </div>
              <div>
                <span className="text-neutral-500 block text-[11px]">Applied Rule:</span>
                <span className="font-mono text-cyan-300">{record.classification.rule_code}</span>
              </div>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between pt-2 border-t border-neutral-800">
          <div className="flex items-center gap-2 text-xs text-emerald-400 font-medium">
            <CheckCircle2 className="h-4 w-4" />
            <span>Dual-Stream Anchored & Permanently Reconciled</span>
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