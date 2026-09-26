import React, { useState } from 'react';
import { type InboxItem } from '../../api/statementInboxApi';
import { TableEngine } from '../ui/data-table/TableEngine';
import { ATTACHMENT_INBOX_COLUMNS } from '../ui/data-table/columns';

interface AttachmentInboxTabProps {
  inboxItems: InboxItem[];
  inboxLoading: boolean;
  activeInboxItemId: string | null;
  loading: boolean;
  onRefresh: () => void;
  onPreviewItem: (itemId: string) => void;
}

export const AttachmentInboxTab: React.FC<AttachmentInboxTabProps> = ({
  inboxItems,
  inboxLoading,
  activeInboxItemId,
  loading,
  onRefresh,
  onPreviewItem,
}) => {
  const [isInboxCollapsed, setIsInboxCollapsed] = useState(false);
  const [inboxPage, setInboxPage] = useState(1);
  const INBOX_PAGE_SIZE = 10;

  const totalInboxPages = Math.max(1, Math.ceil(inboxItems.length / INBOX_PAGE_SIZE));
  const paginatedInboxItems = inboxItems.slice((inboxPage - 1) * INBOX_PAGE_SIZE, inboxPage * INBOX_PAGE_SIZE);
  const activeInboxItem = inboxItems.find((i) => i.id === activeInboxItemId);

  return (
    <div className="w-full bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl overflow-hidden transition-all">
      <div className="p-3 bg-zinc-900/90 flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800/60">
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono font-bold uppercase tracking-wider text-zinc-300">
            Attachment Inbox
          </span>
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-zinc-800 text-emerald-400 border border-zinc-700">
            {inboxItems.length} queued
          </span>

          {isInboxCollapsed && activeInboxItem && (
            <div className="flex items-center gap-2 px-2.5 py-1 bg-emerald-950/30 border border-emerald-500/30 rounded text-xs font-mono text-emerald-300">
              <span className="text-[10px] text-emerald-500 font-bold uppercase">Staged:</span>
              <span className="font-bold">{activeInboxItem.bank_name}</span>
              <span className="text-emerald-400">•••• {activeInboxItem.account_hint}</span>
              <span className="text-zinc-400 text-[11px] truncate max-w-xs" title={activeInboxItem.filename}>
                ({activeInboxItem.filename})
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onRefresh}
            disabled={inboxLoading}
            className="px-2.5 py-1 bg-zinc-950 hover:bg-zinc-800 border border-zinc-800 text-zinc-300 font-mono text-[11px] rounded transition-all cursor-pointer"
          >
            {inboxLoading ? '...' : '🔄 Refresh'}
          </button>

          <button
            type="button"
            onClick={() => setIsInboxCollapsed(!isInboxCollapsed)}
            className="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-200 font-mono text-[11px] font-bold rounded transition-all cursor-pointer flex items-center gap-1.5"
          >
            <span>{isInboxCollapsed ? '🔽 Show Inbox List' : '🔼 Minimize List'}</span>
          </button>
        </div>
      </div>

      {!isInboxCollapsed && (
        <div className="p-3 space-y-2">
          {inboxItems.length === 0 ? (
            <div className="p-6 text-center text-xs font-mono text-zinc-600 border border-dashed border-zinc-800 rounded-lg bg-zinc-950/20">
              No pending statements in inbox.
            </div>
          ) : (
            <>
              <div className="border border-zinc-800 rounded-lg shadow-inner overflow-hidden">
                <TableEngine
                  columns={ATTACHMENT_INBOX_COLUMNS}
                  data={paginatedInboxItems}
                  meta={{
                    activeItemId: activeInboxItemId,
                    loading: loading,
                    onPreviewItem: onPreviewItem,
                  }}
                />
              </div>

              <div className="flex items-center justify-between px-1 pt-2 text-[11px] font-mono text-zinc-400">
                <div>
                  Showing {(inboxPage - 1) * INBOX_PAGE_SIZE + 1} to{' '}
                  {Math.min(inboxPage * INBOX_PAGE_SIZE, inboxItems.length)} of {inboxItems.length} attachments
                </div>

                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    disabled={inboxPage <= 1}
                    onClick={() => setInboxPage((p) => Math.max(1, p - 1))}
                    className="px-2.5 py-1 rounded bg-zinc-950 border border-zinc-800 text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-zinc-800 cursor-pointer"
                  >
                    Previous
                  </button>

                  <span className="px-3 py-1 rounded bg-zinc-950 border border-zinc-800/80 text-emerald-400 font-bold">
                    {inboxPage} / {totalInboxPages}
                  </span>

                  <button
                    type="button"
                    disabled={inboxPage >= totalInboxPages}
                    onClick={() => setInboxPage((p) => Math.min(totalInboxPages, p + 1))}
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
    </div>
  );
};