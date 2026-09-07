import React, { useState, useEffect, useCallback } from 'react';
import {
  emailIngestApi,
  type EmailPayload,
  type AccountOption,
  type TaxonomyOption,
  type DatePresetType,
  type IngestStats,
} from '../../api/emailIngestApi';
import { IngestToolbar } from './IngestToolbar';
import { PayloadTable } from './PayloadTable';

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
  const [dbPayloads, setDbPayloads] = useState<EmailPayload[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [showStagedOnly, setShowStagedOnly] = useState(false);
  const [stagingForMatching, setStagingForMatching] = useState(false);
  const [unstagingForMatching, setUnstagingForMatching] = useState(false);

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
      console.error(err);
      setDbPayloads([]);
    } finally {
      setLoading(false);
    }
  }, [datePreset, selectedAccount, showStagedOnly, startDate, endDate, onStatsLoaded]);

  useEffect(() => {
    fetchVaultData();
  }, [fetchVaultData]);

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

  return (
    <div className="space-y-4">
      <IngestToolbar
        mode="VAULT"
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
        <div className="py-20 text-center font-mono text-xs text-zinc-400">Loading vault...</div>
      ) : (
        <PayloadTable
          payloads={dbPayloads}
          selectedIds={selectedIds}
          taxonomyTree={taxonomyTree}
          onSelectPayload={onSelectPayload}
          onToggleSelectAll={() => setSelectedIds(selectedIds.length === dbPayloads.length ? [] : dbPayloads.map((p) => p.id || (p as any).payload_hash))}
          onToggleSelectOne={(id) => setSelectedIds((prev) => prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id])}
          onBatchSaveTaxonomy={handleBatchSaveTaxonomy}
        />
      )}
    </div>
  );
};