import React, { useState, useMemo } from 'react';
import { emailIngestApi, type EmailPayload, type DatePresetType } from '../../api/emailIngestApi';
import { IngestToolbar } from './IngestToolbar';
import { PayloadTable } from './PayloadTable';

interface Props {
  stagingPayloads: EmailPayload[];
  setStagingPayloads: React.Dispatch<React.SetStateAction<EmailPayload[]>>;
  onTriggerSync: () => void;
  syncing: boolean;
  datePreset: DatePresetType;
  setDatePreset: (preset: DatePresetType) => void;
  startDate: string;
  setStartDate: (d: string) => void;
  endDate: string;
  setEndDate: (d: string) => void;
  onSelectPayload: (payload: EmailPayload) => void;
  onNotification: (n: { type: 'success' | 'error' | 'info'; message: string }) => void;
}

export const LiveBufferTab: React.FC<Props> = ({
  stagingPayloads,
  setStagingPayloads,
  onTriggerSync,
  syncing,
  datePreset,
  setDatePreset,
  startDate,
  setStartDate,
  endDate,
  setEndDate,
  onSelectPayload,
  onNotification,
}) => {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [committing, setCommitting] = useState(false);
  const [isDiscarding, setIsDiscarding] = useState(false);
  const [hideDuplicates, setHideDuplicates] = useState(false);

  const displayedPayloads = useMemo(() => {
    if (!hideDuplicates) return stagingPayloads;
    return stagingPayloads.filter((p) => p.status !== 'DUPLICATE' && !(p as any).is_duplicate);
  }, [stagingPayloads, hideDuplicates]);

  const handleCommitSelected = async () => {
    if (selectedIds.length === 0) return;
    setCommitting(true);
    try {
      const items = stagingPayloads.filter((p) => selectedIds.includes(p.id)).map((p: any) => p.raw_item || p);
      const res = await emailIngestApi.commitSelectedPayloads(items);
      setStagingPayloads((prev) => prev.filter((p) => !selectedIds.includes(p.id)));
      setSelectedIds([]);
      onNotification({ type: 'success', message: `Committed ${res?.committed_count || 0} alerts to Vault.` });
    } catch {
      onNotification({ type: 'error', message: 'Failed to commit selected items.' });
    } finally {
      setCommitting(false);
    }
  };

  const handleDiscardSelected = async () => {
    if (selectedIds.length === 0) return;
    setIsDiscarding(true);
    try {
      await emailIngestApi.discardStagingPayloads(selectedIds);
      setStagingPayloads((prev) => prev.filter((p) => !selectedIds.includes(p.id)));
      setSelectedIds([]);
      onNotification({ type: 'info', message: 'Selected items discarded.' });
    } catch {
      onNotification({ type: 'error', message: 'Failed to discard items.' });
    } finally {
      setIsDiscarding(false);
    }
  };

  return (
    <div className="space-y-4">
      <IngestToolbar
        mode="INGEST"
        datePreset={datePreset}
        onDatePresetChange={setDatePreset}
        startDate={startDate}
        endDate={endDate}
        onStartDateChange={setStartDate}
        onEndDateChange={setEndDate}
        onTriggerSync={onTriggerSync}
        syncing={syncing}
        onCommitSelected={handleCommitSelected}
        committing={committing}
        onDiscardSelected={handleDiscardSelected}
        isDiscarding={isDiscarding}
        stagingSelectedCount={selectedIds.length}
        totalCount={stagingPayloads.length}
        stagingPayloads={stagingPayloads}
        hideDuplicates={hideDuplicates}
        onToggleHideDuplicates={() => setHideDuplicates((prev) => !prev)}
      />

      <PayloadTable
        payloads={displayedPayloads}
        selectedIds={selectedIds}
        hideTaxonomy={true}
        onSelectPayload={onSelectPayload}
        onToggleSelectAll={() => setSelectedIds(selectedIds.length === displayedPayloads.length ? [] : displayedPayloads.map((p) => p.id))}
        onToggleSelectOne={(id) => setSelectedIds((prev) => prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id])}
      />
    </div>
  );
};