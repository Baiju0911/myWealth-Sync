import React, { useState } from 'react';
import { subledgerApi } from '../../api/subledger';

interface CandidateRow {
  journal_id: string;
  row_identifier: string;
  account_id: number;
  transaction_date: string;
  date_offset_days: number;
  debit: number;
  credit: number;
  remarks: string;
  probability_score: number;
}

interface AssetCandidateScanModalProps {
  isOpen: boolean;
  onClose: () => void;
  assetId: string;
  assetName: string;
  acquisitionDate: string;
  candidates: CandidateRow[];
  onSuccess: () => void;
}

export const AssetCandidateScanModal: React.FC<AssetCandidateScanModalProps> = ({
  isOpen,
  onClose,
  assetId,
  assetName,
  acquisitionDate,
  candidates,
  onSuccess,
}) => {
  const [selectedRowIds, setSelectedRowIds] = useState<string[]>([]);
  const [binding, setBinding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const toggleSelectRow = (rowIdentifier: string) => {
    setSelectedRowIds((prev) =>
      prev.includes(rowIdentifier)
        ? prev.filter((id) => id !== rowIdentifier)
        : [...prev, rowIdentifier]
    );
  };

  const handleBindSelected = async () => {
    if (selectedRowIds.length === 0) return;
    setBinding(true);
    setError(null);

    try {
      // Loop through selected candidates and bind each row to the asset
      for (const rowId of selectedRowIds) {
        const candidate = candidates.find((c) => c.row_identifier === rowId);
        if (!candidate) continue;

        const amount = candidate.debit > 0 ? candidate.debit : candidate.credit;

        await subledgerApi.bindTransaction({
          asset_id: assetId,
          row_identifier: candidate.row_identifier,
          transaction_date: candidate.transaction_date,
          amount: amount,
          transaction_purpose: 'ACQUISITION_PAYMENT',
          user_note: `Linked acquisition payment from ${candidate.remarks}`,
        });
      }

      onSuccess();
      onClose();
    } catch (err: any) {
      console.error('Binding failed:', err);
      setError('Failed to bind selected rows to asset.');
    } finally {
      setBinding(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm">
      <div className="w-full max-w-3xl rounded-xl border border-slate-800 bg-slate-900 p-6 shadow-2xl text-slate-100">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              🔍 Candidate Bank Rows for <span className="text-emerald-400">{assetName}</span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Anchor Acquisition Date: <span className="font-mono text-slate-300">{acquisitionDate}</span> (±10 Day Window)
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white">✕</button>
        </div>

        {/* Candidate Rows Table */}
        <div className="mt-4 max-h-96 overflow-y-auto border border-slate-800 rounded-lg">
          {candidates.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-500">
              No matching bank or journal entries found within the ±10 day window.
            </div>
          ) : (
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-950 text-slate-400 uppercase font-mono text-[10px] sticky top-0 border-b border-slate-800">
                <tr>
                  <th className="p-2.5 text-center">Select</th>
                  <th className="p-2.5">Date</th>
                  <th className="p-2.5">Remarks / Narration</th>
                  <th className="p-2.5 text-right">Amount (₹)</th>
                  <th className="p-2.5 text-center">Score</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 bg-slate-900/50">
                {candidates.map((row) => {
                  const isSelected = selectedRowIds.includes(row.row_identifier);
                  const amount = row.debit > 0 ? row.debit : row.credit;

                  return (
                    <tr
                      key={row.row_identifier}
                      onClick={() => toggleSelectRow(row.row_identifier)}
                      className={`cursor-pointer transition-colors ${
                        isSelected ? 'bg-emerald-950/40 text-emerald-200' : 'hover:bg-slate-800/50'
                      }`}
                    >
                      <td className="p-2.5 text-center" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelectRow(row.row_identifier)}
                          className="rounded border-slate-700 bg-slate-800 text-emerald-500 focus:ring-0"
                        />
                      </td>
                      <td className="p-2.5 font-mono text-slate-300">{row.transaction_date}</td>
                      <td className="p-2.5 max-w-xs truncate text-slate-200" title={row.remarks}>
                        {row.remarks || '—'}
                      </td>
                      <td className="p-2.5 text-right font-mono font-semibold text-emerald-400">
                        ₹{amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="p-2.5 text-center font-mono">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            row.probability_score >= 70
                              ? 'bg-emerald-500/20 text-emerald-400'
                              : 'bg-amber-500/20 text-amber-400'
                          }`}
                        >
                          {row.probability_score}%
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {error && (
          <p className="mt-3 text-xs text-rose-400 font-mono bg-rose-500/10 p-2 rounded border border-rose-500/20">
            {error}
          </p>
        )}

        <div className="mt-4 flex items-center justify-between border-t border-slate-800 pt-3">
          <span className="text-xs text-slate-400">
            Selected: <strong className="text-white">{selectedRowIds.length}</strong> row(s)
          </span>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="rounded bg-slate-800 px-4 py-2 text-xs text-slate-300 hover:bg-slate-700"
            >
              Cancel
            </button>
            <button
              onClick={handleBindSelected}
              disabled={selectedRowIds.length === 0 || binding}
              className="rounded bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
            >
              {binding ? 'Mapping Rows...' : `Map Selected (${selectedRowIds.length})`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};