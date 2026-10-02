import React, { useState } from 'react';
import type { SplitAllocationPayload } from '../../api/api';

interface SplitStateRow {
  categoryId: string;
  subcat: string;
  amount: number;
}

interface SplitAllocationModalProps {
  selectedRow: any;
  availableCategories: any[];
  onClose: () => void;
  onCommit: (wipId: string, payload: SplitAllocationPayload[]) => Promise<void>;
}

export const SplitAllocationModal: React.FC<SplitAllocationModalProps> = ({
  selectedRow,
  availableCategories,
  onClose,
  onCommit,
}) => {
  const originalTxnValue = selectedRow ? (selectedRow.debit || selectedRow.credit || 0) : 0;
  const [splitLines, setSplitLines] = useState<SplitStateRow[]>([
    { categoryId: '', subcat: '', amount: originalTxnValue }
  ]);

  const currentSplitSum = splitLines.reduce((acc, curr) => acc + curr.amount, 0);
  const mathematicallyBalanced = parseFloat(originalTxnValue.toFixed(2)) === parseFloat(currentSplitSum.toFixed(2));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!mathematicallyBalanced) return;
    const payload: SplitAllocationPayload[] = splitLines.map(line => ({
      categoryId: line.categoryId,
      subcat: line.subcat,
      amount: line.amount,
    }));
    await onCommit(selectedRow.wip_id, payload);
  };

  return (
    <div className="fixed inset-0 bg-zinc-950/80 flex items-center justify-center p-4 backdrop-blur-xs z-50">
      <form onSubmit={handleSubmit} className="bg-zinc-900 border border-zinc-800 p-6 rounded-xl w-full max-w-2xl space-y-4 font-mono text-xs">
        <div className="flex justify-between items-center border-b border-zinc-800 pb-3">
          <span className="text-zinc-400 uppercase font-bold">Split Allocation Interface</span>
          <button type="button" onClick={onClose} className="text-zinc-500 hover:text-zinc-300">Close</button>
        </div>

        <div className="bg-zinc-950 p-3 rounded text-[11px] text-zinc-400 border border-zinc-800/60">
          <span className="text-zinc-500 font-bold">TARGET:</span> {selectedRow.narration}<br />
          <span className="text-zinc-500 font-bold">VALUE DEPLOYED:</span> <span className="text-zinc-200 font-bold">₹{originalTxnValue}</span>
        </div>

        <div className="space-y-2 max-h-52 overflow-y-auto pr-2">
          {splitLines.map((line, index) => (
            <div key={index} className="grid grid-cols-3 gap-2 items-center">
              <select
                value={line.categoryId}
                onChange={e => {
                  const updated = [...splitLines];
                  updated[index].categoryId = e.target.value;
                  setSplitLines(updated);
                }}
                className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200"
                required
              >
                <option value="">Select Balance Sheet Group</option>
                {availableCategories.map((c: any) => (
                  <option key={c.id} value={c.id}>{c.act_category} → {c.categories_items}</option>
                ))}
              </select>
              <input
                type="text"
                placeholder="Subcategory target label"
                value={line.subcat}
                onChange={e => {
                  const updated = [...splitLines];
                  updated[index].subcat = e.target.value;
                  setSplitLines(updated);
                }}
                className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200"
                required
              />
              <input
                type="number"
                step="0.01"
                placeholder="Amount"
                value={line.amount || ''}
                onChange={e => {
                  const updated = [...splitLines];
                  updated[index].amount = parseFloat(e.target.value) || 0;
                  setSplitLines(updated);
                }}
                className="bg-zinc-950 border border-zinc-800 p-2 rounded text-zinc-200 text-right"
                required
              />
            </div>
          ))}
        </div>

        <div className="flex justify-between items-center border-t border-zinc-800 pt-4 font-bold">
          <button
            type="button"
            onClick={() => setSplitLines([...splitLines, { categoryId: '', subcat: '', amount: 0 }])}
            className="text-cyan-400 hover:text-cyan-300"
          >
            + Add Allocated Segment Row
          </button>

          <div className="text-right space-y-1">
            <div className={`text-[11px] ${mathematicallyBalanced ? 'text-emerald-400' : 'text-amber-500'}`}>
              Allocated: ₹{currentSplitSum.toFixed(2)} / ₹{parseFloat(originalTxnValue.toString()).toFixed(2)}
            </div>
            <button
              type="submit"
              disabled={!mathematicallyBalanced}
              className={`px-4 py-2 rounded text-zinc-950 uppercase font-bold transition-all ${
                mathematicallyBalanced
                  ? 'bg-emerald-500 hover:bg-emerald-600 cursor-pointer'
                  : 'bg-zinc-800 text-zinc-500 cursor-not-allowed'
              }`}
            >
              Commit Entry Split Matrix
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};