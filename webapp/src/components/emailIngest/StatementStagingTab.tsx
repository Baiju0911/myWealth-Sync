import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  emailIngestApi,
  type AccountOption,
  type StagedStatementItem,
} from '../../api/emailIngestApi';
import { StatementToolbar } from './StatementToolbar';
import { TableEngine } from '../ui/data-table/TableEngine';
import { STATEMENT_STAGING_COLUMNS } from '../ui/data-table/columns';
import { StatementPreviewModal } from './StatementPreviewmodal';

interface Props {
  accountOptions: AccountOption[];
  onNotification: (notif: { type: 'success' | 'error' | 'info'; message: string }) => void;
}

export const StatementStagingTab: React.FC<Props> = ({ accountOptions, onNotification }) => {
  const [stagedStatements, setStagedStatements] = useState<StagedStatementItem[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [harvesting, setHarvesting] = useState<boolean>(false);
  const [committing, setCommitting] = useState<boolean>(false);
  const [accountOverrides, setAccountOverrides] = useState<Record<string, string>>({});
  const [previewStatement, setPreviewStatement] = useState<StagedStatementItem | null>(null);

  const fetchStagedStatements = useCallback(async () => {
    setLoading(true);
    try {
      const res = await emailIngestApi.getStagedStatements();
      const list = res?.results || [];
      setStagedStatements(list);
      setSelectedIds(list.map((item: any) => item.stage_id));
    } catch (err) {
      console.error('Failed to load staged statements:', err);
      onNotification({ type: 'error', message: 'Failed to load staged statements manifest.' });
    } finally {
      setLoading(false);
    }
  }, [onNotification]);

  useEffect(() => {
    fetchStagedStatements();
  }, [fetchStagedStatements]);

  const handleHarvest = async () => {
    setHarvesting(true);
    try {
      const res = await emailIngestApi.harvestBankStatements(25);
      onNotification({
        type: 'success',
        message: res.message || `Harvested ${res.staged_count} statements to manifest.`,
      });
      await fetchStagedStatements();
    } catch (err: any) {
      console.error('Statement harvest failed:', err);
      onNotification({
        type: 'error',
        message: err?.response?.data?.message || 'Error harvesting statements from Gmail.',
      });
    } finally {
      setHarvesting(false);
    }
  };

  const handleCommit = async () => {
    if (selectedIds.length === 0) return;
    setCommitting(true);
    try {
      const overrides: Record<string, { account_hint: string }> = {};
      Object.entries(accountOverrides).forEach(([id, acc]) => {
        if (acc) overrides[id] = { account_hint: acc };
      });

      const res = await emailIngestApi.commitSelectedStatements({
        selected_ids: selectedIds,
        overrides,
      });

      onNotification({
        type: 'success',
        message: res.message || 'Statements successfully saved to database inbox.',
      });
      setAccountOverrides({});
      await fetchStagedStatements();
    } catch (err: any) {
      console.error('Commit failed:', err);
      onNotification({
        type: 'error',
        message: err?.response?.data?.message || 'Failed to commit statements to database.',
      });
    } finally {
      setCommitting(false);
    }
  };

  const handleToggleSelectOne = useCallback((id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  }, []);

  const handleToggleSelectAll = useCallback(() => {
    setSelectedIds((prev) =>
      prev.length === stagedStatements.length ? [] : stagedStatements.map((item) => item.stage_id)
    );
  }, [stagedStatements]);

  const statementColumns = useMemo(() => {
    const isAllSelected =
      stagedStatements.length > 0 && selectedIds.length === stagedStatements.length;

    return STATEMENT_STAGING_COLUMNS.map((col) => {
      if (col.key === 'select') {
        return {
          ...col,
          label: (
            <input
              type="checkbox"
              checked={isAllSelected}
              onChange={handleToggleSelectAll}
              className="rounded border-zinc-700 bg-zinc-800 text-emerald-500 focus:ring-0 cursor-pointer"
            />
          ),
        };
      }
      return col;
    });
  }, [stagedStatements.length, selectedIds.length, handleToggleSelectAll]);

  return (
    <div className="space-y-4">
      <StatementToolbar
        stagedCount={stagedStatements.length}
        selectedCount={selectedIds.length}
        onHarvest={handleHarvest}
        isHarvesting={harvesting}
        onCommit={handleCommit}
        isCommitting={committing}
      />

      {loading ? (
        <div className="py-20 text-center font-mono text-xs text-zinc-400 bg-zinc-900/40 rounded-xl border border-zinc-800/60 flex flex-col items-center justify-center gap-3">
          <span className="h-5 w-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
          <span>Loading staged PDF manifest...</span>
        </div>
      ) : stagedStatements.length === 0 ? (
        <div className="py-20 text-center font-mono text-xs text-zinc-500 bg-zinc-900/30 rounded-xl border border-dashed border-zinc-800 flex flex-col items-center justify-center gap-2">
          <span>No statements currently staged in the inbox manifest.</span>
          <span className="text-[11px] text-zinc-600">
            Click &quot;Scan Gmail for PDFs&quot; to discover bank statements.
          </span>
        </div>
      ) : (
        <TableEngine
          columns={statementColumns}
          data={stagedStatements}
          meta={{
            selectedIds,
            accountOptions,
            accountOverrides,
            onOpenPreview: (item: StagedStatementItem) => setPreviewStatement(item),
            onToggleSelectOne: handleToggleSelectOne,
            onAccountOverrideChange: (stageId: string, account: string) => {
              setAccountOverrides((prev) => ({ ...prev, [stageId]: account }));
            },
          }}
        />
      )}

      <StatementPreviewModal
        statement={previewStatement}
        onClose={() => setPreviewStatement(null)}
        onConfirm={(id) => {
          if (!selectedIds.includes(id)) {
            setSelectedIds((prev) => [...prev, id]);
          }
        }}
        onDeselect={(id) => {
          setSelectedIds((prev) => prev.filter((item) => item !== id));
        }}
      />
    </div>
  );
};