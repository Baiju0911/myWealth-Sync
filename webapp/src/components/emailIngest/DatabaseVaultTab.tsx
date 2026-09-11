import React, { useState, useEffect, useCallback } from 'react';
import {
  emailIngestApi,
  type EmailPayload,
  type AccountOption,
  type TaxonomyOption,
  type DatePresetType,
  type IngestStats,
  type StagedStatementItem,
} from '../../api/emailIngestApi';
import { IngestToolbar } from './IngestToolbar';
import { PayloadTable } from './PayloadTable';
import { StatementVault } from './StatementVault';
import { StatementPreviewModal } from './StatementPreviewModal';
import { Layers, FileSpreadsheet, Building2 } from 'lucide-react';

interface Props {
  selectedAccount: string;
  setSelectedAccount: (acc: string) => void;
  accountOptions: AccountOption[];
  taxonomyTree: TaxonomyOption[];
  datePreset: DatePresetType;
  setDatePreset: (p: DatePresetType) => void;
  startDate: string;
  setStartDate: (s: string) => void;
  endDate: string;
  setEndDate: (e: string) => void;
  onSelectPayload: (payload: EmailPayload) => void;
  onNotification: (n: { type: 'success' | 'error' | 'info'; message: string }) => void;
  onStatsLoaded?: (stats: IngestStats | null) => void;
}

export const DatabaseVaultTab: React.FC<Props> = ({
  selectedAccount,
  setSelectedAccount,
  accountOptions,
  taxonomyTree,
  datePreset,
  setDatePreset,
  startDate,
  setStartDate,
  endDate,
  setEndDate,
  onSelectPayload,
  onNotification,
  onStatsLoaded,
}) => {
  const [subView, setSubView] = useState<'ALERTS' | 'STATEMENTS'>('ALERTS');

  // Transaction Payloads State
  const [dbPayloads, setDbPayloads] = useState<EmailPayload[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [showStagedOnly, setShowStagedOnly] = useState(false);
  const [stagingForMatching, setStagingForMatching] = useState(false);
  const [unstagingForMatching, setUnstagingForMatching] = useState(false);

  // Committed Statements State
  const [committedStatements, setCommittedStatements] = useState<StagedStatementItem[]>([]);
  const [loadingStatements, setLoadingStatements] = useState(false);
  const [previewStatement, setPreviewStatement] = useState<StagedStatementItem | null>(null);

  const fetchVaultData = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = { date_preset: datePreset, account: selectedAccount, staged_only: showStagedOnly };
      if (datePreset === 'CUSTOM' && startDate.length === 10 && endDate.length === 10) {
        params.start_date = startDate;
        params.end_date = endDate;
      }

      const [payloadRes, statsRes] = await Promise.all([
        emailIngestApi.getPayloads(params),
        emailIngestApi.getStats(params),
      ]);

      const rawList = payloadRes?.results || payloadRes?.data || payloadRes || [];
      setDbPayloads(Array.isArray(rawList) ? rawList : []);
      onStatsLoaded?.(statsRes || null);
      setSelectedIds([]);
    } catch (err) {
      console.error('Failed to load transaction alerts:', err);
      setDbPayloads([]);
    } finally {
      setLoading(false);
    }
  }, [datePreset, selectedAccount, showStagedOnly, startDate, endDate, onStatsLoaded]);

  const fetchCommittedStatements = useCallback(async () => {
    setLoadingStatements(true);
    try {
      const docs = await emailIngestApi.getCommittedInboxDocuments(
        selectedAccount === 'ALL' ? undefined : selectedAccount
      );
      setCommittedStatements(docs);
    } catch (err) {
      console.error('Failed to load committed statements:', err);
      onNotification({ type: 'error', message: 'Failed to fetch statement documents from vault.' });
    } finally {
      setLoadingStatements(false);
    }
  }, [selectedAccount, onNotification]);

  useEffect(() => {
    if (subView === 'ALERTS') {
      fetchVaultData();
    } else {
      fetchCommittedStatements();
    }
  }, [subView, fetchVaultData, fetchCommittedStatements]);

  const handleStageForMatching = async () => {
    if (selectedIds.length === 0) return;
    setStagingForMatching(true);
    try {
      const selectedGaps = dbPayloads.filter((i: any) => i.is_synthetic_gap && selectedIds.includes(i.id));
      const stdIds = selectedIds.filter((id) => !id.startsWith('gap_'));
      await emailIngestApi.stageForMatching(stdIds, selectedGaps);
      onNotification({ type: 'success', message: `Staged ${selectedIds.length} item(s) for balance reconciliation.` });
      setSelectedIds([]);
      fetchVaultData();
    } finally {
      setStagingForMatching(false);
    }
  };

  const handleUnstageSelected = async () => {
    if (selectedIds.length === 0) return;
    setUnstagingForMatching(true);
    try {
      await emailIngestApi.unstageFromMatching(selectedIds);
      onNotification({ type: 'success', message: 'Unstaged records successfully.' });
      setSelectedIds([]);
      fetchVaultData();
    } finally {
      setUnstagingForMatching(false);
    }
  };

  const handleBatchSaveTaxonomy = async (updates: Array<{ payloadId: string; categoryName: string; subcategoryName: string }>) => {
    try {
      await emailIngestApi.batchUpdateTaxonomy(updates);
      onNotification({ type: 'success', message: `Updated taxonomy for ${updates.length} item(s).` });
      fetchVaultData();
    } catch {
      onNotification({ type: 'error', message: 'Failed to save taxonomy.' });
    }
  };

  const handleDeleteStatement = async (doc: any) => {
    if (!window.confirm(`Remove statement record "${doc.filename}" from vault inbox?`)) return;
    try {
      await emailIngestApi.deleteCommittedDocument(doc.id || doc.stage_id);
      onNotification({ type: 'info', message: `Statement ${doc.filename} removed.` });
      fetchCommittedStatements();
    } catch {
      onNotification({ type: 'error', message: 'Failed to delete statement record.' });
    }
  };

  return (
    <div className="space-y-4">
      {/* Top Bar: Sub-View Toggle (Left) + Unified Account Selector (Right) */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-zinc-900/60 p-2 rounded-xl border border-zinc-800/80 font-mono text-xs">
        {/* Left: View Tabs */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setSubView('ALERTS')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg font-bold transition-all cursor-pointer ${
              subView === 'ALERTS'
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-950'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Transaction Alerts ({dbPayloads.length})</span>
          </button>

          <button
            type="button"
            onClick={() => setSubView('STATEMENTS')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg font-bold transition-all cursor-pointer ${
              subView === 'STATEMENTS'
                ? 'bg-amber-600 text-zinc-950 shadow-md shadow-amber-950'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
            }`}
          >
            <FileSpreadsheet className="w-3.5 h-3.5" />
            <span>Statement Documents ({committedStatements.length})</span>
          </button>
        </div>

        {/* Right: Global Account Filter */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 bg-zinc-950/80 border border-zinc-800 px-2.5 py-1 rounded-lg">
            <Building2 className="w-3.5 h-3.5 text-zinc-500" />
            <span className="text-zinc-500 text-[11px] font-semibold">ACCOUNT:</span>
            <select
              value={selectedAccount}
              onChange={(e) => setSelectedAccount(e.target.value)}
              className="bg-transparent text-zinc-200 font-semibold focus:outline-none cursor-pointer text-xs"
            >
              <option value="ALL" className="bg-zinc-900 text-zinc-300">All Accounts</option>
              {accountOptions.map((opt) => (
                <option key={opt.id} value={opt.value} className="bg-zinc-900 text-zinc-300">
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {subView === 'STATEMENTS' && (
            <span className="text-[11px] text-zinc-500 hidden md:inline-block px-1">
              <code>backend/documents/inbox/</code>
            </span>
          )}
        </div>
      </div>

      {/* Sub-View 1: Transaction Alerts */}
      {subView === 'ALERTS' && (
        <>
          <IngestToolbar
            mode="VAULT"
            hideAccountSelector={true}
            datePreset={datePreset}
            onDatePresetChange={setDatePreset}
            startDate={startDate}
            endDate={endDate}
            onStartDateChange={setStartDate}
            onEndDateChange={setEndDate}
            selectedAccount={selectedAccount}
            accountOptions={accountOptions}
            onAccountChange={setSelectedAccount}
            onStageSelected={handleStageForMatching}
            stagingForMatching={stagingForMatching}
            onUnstageSelected={handleUnstageSelected}
            unstagingForMatching={unstagingForMatching}
            dbSelectedCount={selectedIds.length}
            totalCount={dbPayloads.length}
            showStagedOnly={showStagedOnly}
            onToggleStagedOnly={setShowStagedOnly}
          />

          {loading ? (
            <div className="py-20 text-center font-mono text-xs text-zinc-400">Loading alerts vault...</div>
          ) : (
            <PayloadTable
              payloads={dbPayloads}
              selectedIds={selectedIds}
              taxonomyTree={taxonomyTree}
              onSelectPayload={onSelectPayload}
              onToggleSelectAll={() =>
                setSelectedIds(
                  selectedIds.length === dbPayloads.length
                    ? []
                    : dbPayloads.map((p) => p.id || (p as any).payload_hash)
                )
              }
              onToggleSelectOne={(id) =>
                setSelectedIds((prev) => (prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]))
              }
              onBatchSaveTaxonomy={handleBatchSaveTaxonomy}
            />
          )}
        </>
      )}

      {/* Sub-View 2: Committed PDF Statements Inbox */}
      {subView === 'STATEMENTS' && (
        <>
          {loadingStatements ? (
            <div className="py-20 text-center font-mono text-xs text-zinc-400">Loading committed statements...</div>
          ) : (
            <StatementVault
              documents={committedStatements}
              onOpenPreview={(doc) => setPreviewStatement(doc)}
              onDeleteDocument={handleDeleteStatement}
            />
          )}
        </>
      )}

      {/* Document Review / PDF Decryption Modal */}
      <StatementPreviewModal
        statement={previewStatement}
        onClose={() => setPreviewStatement(null)}
        onConfirm={() => setPreviewStatement(null)}
        onDeselect={() => setPreviewStatement(null)}
      />
    </div>
  );
};