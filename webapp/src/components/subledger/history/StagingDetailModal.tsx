// webapp/src/components/subledger/history/StagingDetailModal.tsx
import React from 'react';
import type { MappedTransaction } from './useHistoryDrawerData';

interface StagingDetailModalProps {
  tx: MappedTransaction | null;
  onClose: () => void;
}

export const StagingDetailModal: React.FC<StagingDetailModalProps> = ({ tx, onClose }) => {
  if (!tx) return null;

  return (
    <div
      className="fixed inset-0 z-60 bg-black/80 flex items-center justify-center p-4 font-sans"
      onClick={onClose}
    >
      <div
        className="bg-slate-900 border border-slate-700 p-5 rounded-xl max-w-lg w-full font-mono text-xs space-y-3 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center border-b border-slate-800 pb-2">
          <span className="font-bold text-cyan-400">Raw Staging Metadata</span>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-white cursor-pointer">
            ✕
          </button>
        </div>

        <div className="space-y-1.5 text-slate-300">
          <div>
            <span className="text-slate-500">Row Identifier:</span>{' '}
            <span className="break-all">{tx.row_identifier || 'N/A (Cash Entry)'}</span>
          </div>
          <div>
            <span className="text-slate-500">Journal ID:</span> {tx.journal_id}
          </div>
          <div>
            <span className="text-slate-500">Transaction Date:</span> {tx.transaction_date}
          </div>
          <div>
            <span className="text-slate-500">Amount:</span> ₹
            {Number(tx.credit || tx.debit || tx.amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </div>
          {tx.user_note && (
            <div>
              <span className="text-slate-500">Audit Note:</span>{' '}
              <span className="text-emerald-400">{tx.user_note}</span>
            </div>
          )}
          <div className="p-2.5 bg-slate-950 rounded border border-slate-800 text-[11px] break-all leading-relaxed">
            <span className="text-slate-500 block mb-1">Payload:</span>
            {tx.narration || (typeof tx.remarks === 'object' ? JSON.stringify(tx.remarks, null, 2) : tx.remarks)}
          </div>
        </div>
      </div>
    </div>
  );
};