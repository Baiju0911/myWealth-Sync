import React from 'react';
import type { AssetComplianceSchedule, AssetSubLedgerNode } from '../../../api/subledger';
import { inrFormatter } from '../../../utils/classificationHelpers';

interface ComplianceFeedProps {
  pendingDues: AssetComplianceSchedule[];
  assets: AssetSubLedgerNode[];
  onOpenMatcher: (asset: AssetSubLedgerNode, sch: AssetComplianceSchedule) => void;
}

export const ComplianceFeed: React.FC<ComplianceFeedProps> = ({
  pendingDues,
  assets,
  onOpenMatcher,
}) => {
  return (
    <div className="space-y-4">
      <h2 className="text-xs font-bold tracking-wider text-slate-400 uppercase font-mono">
        Upcoming Dues & Reminders ({pendingDues.length})
      </h2>

      <div className="rounded-xl border border-slate-800/80 bg-slate-900/90 p-4 space-y-3 shadow-xl">
        {pendingDues.length === 0 ? (
          <p className="text-xs text-slate-500 text-center py-6 font-mono">
            🎉 No pending dues in queue!
          </p>
        ) : (
          pendingDues.map((due) => {
            const targetAsset = assets.find((a) => a.id === due.asset);
            return (
              <div
                key={due.id}
                className="rounded-lg border border-slate-800 bg-slate-950 p-3 space-y-2.5 shadow-inner"
              >
                <div className="flex justify-between items-start gap-2">
                  <div className="min-w-0 font-mono">
                    <p className="text-xs font-bold text-white truncate">{due.title}</p>
                    <p className="text-[10px] text-slate-400 mt-0.5">
                      Due Date: <span className="text-amber-400 font-bold">{due.due_date}</span>
                    </p>
                  </div>
                  <span className="font-mono text-xs font-bold text-emerald-400 whitespace-nowrap">
                    {inrFormatter.format(Number(due.expected_amount || 0))}
                  </span>
                </div>

                {targetAsset && (
                  <button
                    type="button"
                    onClick={() => onOpenMatcher(targetAsset, due)}
                    className="w-full rounded bg-emerald-600 py-1 text-xs font-bold font-mono text-white hover:bg-emerald-500 transition-colors cursor-pointer shadow-md"
                  >
                    ⚡ Scan Staging & Resolve
                  </button>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};