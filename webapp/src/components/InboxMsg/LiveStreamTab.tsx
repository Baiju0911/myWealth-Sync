import React, { useState } from 'react';
import { type EnrichedAuditRecord } from '../../api/statementInboxApi';
import { TableEngine } from '../ui/data-table/TableEngine';
import { LIVE_STREAM_COLUMNS, type LiveStreamPayloadItem } from '../ui/data-table/columns';
import { DonorInspectorModal } from './DonorInspectorModal';
import { ReconciliationInspectorModal } from './ReconciliationInspectorModal';

interface LiveStreamTabProps {
  liveStreamItems: LiveStreamPayloadItem[];
  liveStreamLoading: boolean;
  liveStreamTotalCount: number;
  auditItems: EnrichedAuditRecord[];
  auditLoading: boolean;
  auditTotalCount: number;
  onRefreshLive: () => void;
  onRefreshAudit: () => void;
  onCommitLiveEnrichment: () => void;
}

export const LiveStreamTab: React.FC<LiveStreamTabProps> = ({
  liveStreamItems,
  liveStreamLoading,
  liveStreamTotalCount,
  auditItems,
  auditLoading,
  auditTotalCount,
  onRefreshLive,
  onRefreshAudit,
  onCommitLiveEnrichment,
}) => {
  const [liveStreamSubTab, setLiveStreamSubTab] = useState<'staged' | 'audit'>('staged');
  const [liveStreamPage, setLiveStreamPage] = useState(1);
  const LIVE_PAGE_SIZE = 10;

  const [auditPage, setAuditPage] = useState(1);
  const AUDIT_PAGE_SIZE = 10;

  // Modals
  const [inspectingDonor, setInspectingDonor] = useState<LiveStreamPayloadItem | null>(null);
  const [inspectingAudit, setInspectingAudit] = useState<EnrichedAuditRecord | null>(null);

  const totalLivePages = Math.max(1, Math.ceil(liveStreamItems.length / LIVE_PAGE_SIZE));
  const paginatedLiveItems = liveStreamItems.slice(
    (liveStreamPage - 1) * LIVE_PAGE_SIZE,
    liveStreamPage * LIVE_PAGE_SIZE
  );

  const totalAuditPages = Math.max(1, Math.ceil(auditItems.length / AUDIT_PAGE_SIZE));
  const paginatedAuditItems = auditItems.slice((auditPage - 1) * AUDIT_PAGE_SIZE, auditPage * AUDIT_PAGE_SIZE);

  return (
    <div className="w-full bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl overflow-hidden transition-all text-left">
      {/* Sub-Tab Navigation Header */}
      <div className="p-3 bg-zinc-900/95 flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setLiveStreamSubTab('staged')}
            className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold flex items-center gap-2 transition-all cursor-pointer ${
              liveStreamSubTab === 'staged'
                ? 'bg-purple-600/20 text-purple-300 border border-purple-500/40 shadow-sm'
                : 'bg-zinc-950/60 text-zinc-400 hover:text-zinc-200 border border-zinc-800'
            }`}
          >
            <span>⚡ Staged Backlog</span>
            <span className="px-1.5 py-0.2 rounded text-[10px] bg-purple-500/20 text-purple-400 border border-purple-500/30">
              {liveStreamTotalCount}
            </span>
          </button>

          <button
            type="button"
            onClick={() => {
              setLiveStreamSubTab('audit');
              onRefreshAudit();
            }}
            className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold flex items-center gap-2 transition-all cursor-pointer ${
              liveStreamSubTab === 'audit'
                ? 'bg-emerald-600/20 text-emerald-300 border border-emerald-500/40 shadow-sm'
                : 'bg-zinc-950/60 text-zinc-400 hover:text-zinc-200 border border-zinc-800'
            }`}
          >
            <span>🛡️ Enriched Audit Matrix</span>
            <span className="px-1.5 py-0.2 rounded text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              {auditTotalCount}
            </span>
          </button>
        </div>

        <div className="flex items-center gap-2">
          {liveStreamSubTab === 'staged' ? (
            <>
              <span className="hidden xl:inline px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-purple-500/10 text-purple-400 border border-purple-500/20">
                Ready to check {liveStreamItems.length} batch out of {liveStreamTotalCount} staged
              </span>

              <button
                type="button"
                onClick={onRefreshLive}
                disabled={liveStreamLoading}
                className="px-2.5 py-1 bg-zinc-950 hover:bg-zinc-800 border border-zinc-800 text-zinc-300 font-mono text-[11px] rounded transition-all cursor-pointer"
              >
                {liveStreamLoading ? '...' : '🔄 Refresh'}
              </button>

              <button
                type="button"
                disabled={liveStreamLoading || liveStreamItems.length === 0}
                onClick={onCommitLiveEnrichment}
                className={`px-3 py-1 font-mono text-[11px] font-bold rounded transition-all cursor-pointer flex items-center gap-1.5 border shadow-sm select-none ${
                  liveStreamLoading || liveStreamItems.length === 0
                    ? 'bg-zinc-800 border-zinc-700 text-zinc-500 cursor-not-allowed'
                    : 'bg-purple-600/20 hover:bg-purple-600 border-purple-500/30 hover:border-purple-500 text-purple-300 hover:text-white'
                }`}
              >
                <span className={liveStreamLoading ? 'animate-spin' : ''}>
                  {liveStreamLoading ? '⏳' : '⚡'}
                </span>
                <span>{liveStreamLoading ? 'Enriching...' : 'Commit & Enrich Staging'}</span>
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={onRefreshAudit}
              disabled={auditLoading}
              className="px-2.5 py-1 bg-zinc-950 hover:bg-zinc-800 border border-zinc-800 text-zinc-300 font-mono text-[11px] rounded transition-all cursor-pointer"
            >
              {auditLoading ? '...' : '🔄 Refresh Audit'}
            </button>
          )}
        </div>
      </div>

      {/* SUB-VIEW A: STAGED PAYLOADS QUEUE */}
      {liveStreamSubTab === 'staged' && (
        <div className="p-3 space-y-2">
          {liveStreamItems.length === 0 ? (
            <div className="p-6 text-center text-xs font-mono text-zinc-600 border border-dashed border-zinc-800 rounded-lg bg-zinc-950/20">
              No active live stream payloads queued.
            </div>
          ) : (
            <>
              <div className="border border-zinc-800 rounded-lg shadow-inner overflow-hidden">
                <TableEngine
                  columns={LIVE_STREAM_COLUMNS}
                  data={paginatedLiveItems}
                  onRowClick={(row: LiveStreamPayloadItem) => setInspectingDonor(row)}
                />
              </div>

              <div className="flex items-center justify-between px-1 pt-2 text-[11px] font-mono text-zinc-400">
                <div>
                  Showing {(liveStreamPage - 1) * LIVE_PAGE_SIZE + 1} to{' '}
                  {Math.min(liveStreamPage * LIVE_PAGE_SIZE, liveStreamItems.length)} of {liveStreamItems.length} payloads
                </div>

                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    disabled={liveStreamPage <= 1}
                    onClick={() => setLiveStreamPage((p) => Math.max(1, p - 1))}
                    className="px-2.5 py-1 rounded bg-zinc-950 border border-zinc-800 text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-zinc-800 cursor-pointer"
                  >
                    Previous
                  </button>

                  <span className="px-3 py-1 rounded bg-zinc-950 border border-zinc-800/80 text-purple-400 font-bold">
                    {liveStreamPage} / {totalLivePages}
                  </span>

                  <button
                    type="button"
                    disabled={liveStreamPage >= totalLivePages}
                    onClick={() => setLiveStreamPage((p) => Math.min(totalLivePages, p + 1))}
                    className="px-2.5 py-1 rounded bg-zinc-950 border border-zinc-800 text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-zinc-800 cursor-pointer"
                  >
                    Next
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* SUB-VIEW B: TWO-SIDED RECONCILIATION AUDIT MATRIX */}
      {liveStreamSubTab === 'audit' && (
        <div className="p-3 space-y-2">
          {auditItems.length === 0 ? (
            <div className="p-6 text-center text-xs font-mono text-zinc-600 border border-dashed border-zinc-800 rounded-lg bg-zinc-950/20">
              No enriched statement lines recorded yet. Click "Commit & Enrich Staging" in the backlog to match.
            </div>
          ) : (
            <>
              <div className="border border-zinc-800 rounded-lg shadow-inner overflow-x-auto">
                <table className="w-full text-left text-xs font-mono border-collapse">
                  <thead>
                    <tr className="bg-zinc-950/80 text-zinc-400 border-b border-zinc-800 text-[10px] uppercase tracking-wider">
                      <th className="p-2.5 font-bold">Date & Bank</th>
                      <th className="p-2.5 font-bold">Original Statement Narration</th>
                      <th className="p-2.5 font-bold text-right">Amount</th>
                      <th className="p-2.5 font-bold text-center">Reconciliation Matrix</th>
                      <th className="p-2.5 font-bold">Donor Stream Payload</th>
                      <th className="p-2.5 font-bold">Enriched At</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60">
                    {paginatedAuditItems.map((item) => (
                      <tr
                        key={item.statement_id}
                        onClick={() => setInspectingAudit(item)}
                        className="hover:bg-zinc-800/50 transition-colors cursor-pointer"
                        title="Click to inspect two-sided merge audit"
                      >
                        <td className="p-2.5 whitespace-nowrap">
                          <div className="text-zinc-200 font-bold">{item.statement_date}</div>
                          <div className="text-[10px] text-zinc-500">
                            {item.bank_name} •••• {item.account_last4}
                          </div>
                        </td>

                        <td className="p-2.5 max-w-xs truncate text-zinc-300" title={item.raw_narration}>
                          {item.raw_narration}
                        </td>

                        <td className="p-2.5 text-right font-bold text-emerald-400 whitespace-nowrap">
                          ₹{Number(item.statement_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>

                        <td className="p-2.5 text-center whitespace-nowrap">
                          <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                            ⚡ ENRICHED
                          </span>
                        </td>

                        <td className="p-2.5">
                          <div className="flex items-center gap-1.5 mb-1">
                            <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">
                              {item.stream_source}
                            </span>
                            <span className="text-zinc-200 font-bold">{item.resolved_merchant}</span>
                          </div>
                          <div className="text-[10px] text-zinc-500">
                            RRN: <span className="text-purple-400 font-bold">{item.live_upi_rrn || '-'}</span>
                          </div>
                        </td>

                        <td className="p-2.5 text-zinc-500 text-[10px] whitespace-nowrap">
                          {item.enriched_at ? new Date(item.enriched_at).toLocaleString('en-GB') : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center justify-between px-1 pt-2 text-[11px] font-mono text-zinc-400">
                <div>
                  Showing {(auditPage - 1) * AUDIT_PAGE_SIZE + 1} to{' '}
                  {Math.min(auditPage * AUDIT_PAGE_SIZE, auditItems.length)} of {auditItems.length} audited pairs
                </div>

                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    disabled={auditPage <= 1}
                    onClick={() => setAuditPage((p) => Math.max(1, p - 1))}
                    className="px-2.5 py-1 rounded bg-zinc-950 border border-zinc-800 text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-zinc-800 cursor-pointer"
                  >
                    Previous
                  </button>

                  <span className="px-3 py-1 rounded bg-zinc-950 border border-zinc-800/80 text-emerald-400 font-bold">
                    {auditPage} / {totalAuditPages}
                  </span>

                  <button
                    type="button"
                    disabled={auditPage >= totalAuditPages}
                    onClick={() => setAuditPage((p) => Math.min(totalAuditPages, p + 1))}
                    className="px-2.5 py-1 rounded bg-zinc-950 border border-zinc-800 text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-zinc-800 cursor-pointer"
                  >
                    Next
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      )}

{/* MODALS */}
      {inspectingDonor && (
        <DonorInspectorModal
          payload={inspectingDonor}
          onClose={() => setInspectingDonor(null)}
        />
      )}

      {inspectingAudit && (
        <ReconciliationInspectorModal
          record={inspectingAudit}
          onClose={() => setInspectingAudit(null)}
        />
      )}
    </div>
  );
};