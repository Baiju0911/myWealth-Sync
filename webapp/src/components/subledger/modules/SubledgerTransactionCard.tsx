// webapp/src/components/subledger/modules/SubledgerTransactionCard.tsx
import React from 'react';
import { ExternalLink } from 'lucide-react';

interface SubledgerTransactionCardProps {
  tx: any;
  isMaturedOrClosed: boolean;
  unmappingId: string | null;
  onUnmap: (mappingId: string) => void;
  onInspect: (tx: any) => void;
}

export const SubledgerTransactionCard: React.FC<SubledgerTransactionCardProps> = ({
  tx,
  isMaturedOrClosed,
  unmappingId,
  onUnmap,
  onInspect,
}) => {
  // 🎯 PURE LEDGER CONTRACT: Trust explicit backend direction or net credit vs debit balance
  const isCredit = tx.direction ? tx.direction === 'INFLOW' : Number(tx.credit || 0) > 0;

  const isCash = tx.is_cash_entry || !tx.row_identifier;
  const isDisconnecting = unmappingId === tx.mapping_id;
  const txAmount = Math.abs(Number(tx.amount || tx.credit || tx.debit || 0));

  const rawNarration =
    tx.narration ||
    (typeof tx.remarks === 'string'
      ? tx.remarks
      : tx.remarks?.display_text ||
        tx.remarks?.narration ||
        tx.remarks?.payee ||
        'Unlabeled Bank Line');

  return (
    <div
      className={`rounded-lg border p-3 font-mono space-y-2 transition-all ${
        tx.is_child_tx
          ? 'bg-slate-950/90 border-emerald-500/30'
          : 'bg-slate-950 border-slate-800 hover:border-slate-700'
      }`}
    >
      {/* ROW 1: Date, Originating Bank Badge, Vector Tag, and Right-Aligned Amount */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] font-mono text-zinc-300 font-semibold">
            {tx.transaction_date}
          </span>

          {/* 🏦 Originating Bank Account Badge */}
          {tx.bank_name ? (
            <span className="inline-flex items-center gap-1 rounded bg-sky-950/80 border border-sky-700/60 px-1.5 py-0.2 text-[9px] font-mono text-sky-300 font-bold shrink-0">
              <span>🏦</span>
              <span>{tx.bank_name}</span>
              {tx.bank_last4 && (
                <span className="text-sky-400/80 font-normal">••{tx.bank_last4}</span>
              )}
            </span>
          ) : (
            <span
              className={`inline-flex items-center gap-1 rounded px-1.5 py-0.2 text-[9px] font-bold border ${
                isCash
                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                  : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
              }`}
            >
              {isCash ? '💵 DIRECT CASH' : 'BANK STAGING'}
            </span>
          )}

          {/* Vector Tag */}
          <span
            className={`text-[8px] font-bold px-1.5 py-0.2 rounded uppercase border shrink-0 ${
              isCredit
                ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800/40'
                : 'bg-rose-950/60 text-rose-300 border-rose-800/40'
            }`}
          >
            {isCredit ? 'INFLOW (CREDIT)' : 'OUTFLOW (DEBIT)'}
          </span>

          {tx.is_child_tx ? (
            <span className="rounded bg-cyan-950/90 border border-cyan-500/40 px-2 py-0.2 text-[8px] font-bold text-cyan-300">
              ↳ SUB-ASSET: [{tx.source_asset_code}] {tx.source_asset_name}
            </span>
          ) : (
            <span className="rounded bg-slate-800 border border-slate-700 px-1.5 py-0.2 text-[8px] font-bold text-slate-300">
              🏛️ MASTER ASSET DIRECT
            </span>
          )}
        </div>

        {/* Amount & Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <span
            className={`text-xs font-bold tabular-nums ${
              isCredit ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {isCredit ? '+' : '-'}₹
            {txAmount.toLocaleString('en-IN', {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>

          <button
            type="button"
            onClick={() => onInspect(tx)}
            className="text-slate-400 hover:text-cyan-300 text-[10px] p-0.5 transition-colors cursor-pointer"
            title="Inspect raw staging details"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </button>

          {tx.mapping_id && !isMaturedOrClosed && (
            <button
              type="button"
              onClick={() => onUnmap(tx.mapping_id)}
              disabled={isDisconnecting}
              className="rounded bg-rose-600/20 text-rose-400 border border-rose-500/30 px-2 py-0.5 text-[10px] font-bold hover:bg-rose-600 hover:text-white transition-colors disabled:opacity-50 cursor-pointer font-mono"
            >
              {isDisconnecting ? 'Removing...' : 'Unmap'}
            </button>
          )}
        </div>
      </div>

      {/* ROW 2: Raw Statement Narration */}
      <p
        className="text-xs text-slate-200 font-mono leading-relaxed wrap-break-word cursor-pointer hover:text-cyan-300 transition-colors"
        title={rawNarration}
        onClick={() => onInspect(tx)}
      >
        {rawNarration}
      </p>

      {/* ROW 3: User Audit Note */}
      {tx.user_note && (
        <div className="text-[10px] text-slate-400 border-t border-slate-800/60 pt-1.5 flex items-center gap-1.5">
          <span className="text-slate-500 font-bold shrink-0">Note:</span>
          <span className="truncate">{tx.user_note}</span>
        </div>
      )}
    </div>
  );
};