import React, { useState } from 'react';
import {
  type EmailPayload,
  type AccountOption,
  type DatePresetType,
  DATE_PRESET_OPTIONS,
} from '../../api/emailIngestApi';
import { IngestToolbar } from './IngestToolbar';
import { PayloadTable } from './PayloadTable';
import { StatementStagingTab } from './StatementStagingTab';
import { Layers, FileSpreadsheet, Calendar } from 'lucide-react';

interface Props {
  stagingPayloads: EmailPayload[];
  setStagingPayloads?: React.Dispatch<React.SetStateAction<EmailPayload[]>>;
  onTriggerSync: () => void;
  syncing: boolean;
  datePreset: DatePresetType;
  setDatePreset: (p: DatePresetType) => void;
  startDate: string;
  setStartDate: (s: string) => void;
  endDate: string;
  setEndDate: (e: string) => void;
  selectedAccount: string;
  setSelectedAccount: (acc: string) => void;
  accountOptions: AccountOption[];
  onSelectPayload: (payload: EmailPayload) => void;
  onNotification: (n: { type: 'success' | 'error' | 'info'; message: string }) => void;
}

export const LiveBufferTab: React.FC<Props> = ({
  stagingPayloads,
  onTriggerSync,
  syncing,
  datePreset,
  setDatePreset,
  startDate,
  setStartDate,
  endDate,
  setEndDate,
  accountOptions,
  onSelectPayload,
  onNotification,
}) => {
  const [ingestMode, setIngestMode] = useState<'ALERTS' | 'STATEMENTS'>('ALERTS');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [hideDuplicates, setHideDuplicates] = useState(false);

  return (
    <div className="space-y-4">
      {/* Top Bar: Sub-View Toggle (Left) + Common Date Range Filter (Right) */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-zinc-900/60 p-2.5 rounded-xl border border-zinc-800/80 font-mono text-xs">
        {/* Left: View Tabs */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setIngestMode('ALERTS')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg font-bold transition-all cursor-pointer ${
              ingestMode === 'ALERTS'
                ? 'bg-emerald-600 text-white shadow-md shadow-emerald-950'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Email Alert Stream ({stagingPayloads.length})</span>
          </button>

          <button
            type="button"
            onClick={() => setIngestMode('STATEMENTS')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg font-bold transition-all cursor-pointer ${
              ingestMode === 'STATEMENTS'
                ? 'bg-amber-600 text-zinc-950 shadow-md shadow-amber-950'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
            }`}
          >
            <FileSpreadsheet className="w-3.5 h-3.5" />
            <span>PDF Statements Harvest</span>
          </button>
        </div>

        {/* Right: Common Date Range Filter */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 bg-zinc-950/80 border border-zinc-800 px-2.5 py-1.5 rounded-lg">
            <Calendar className="w-3.5 h-3.5 text-zinc-500" />
            <select
              value={datePreset}
              onChange={(e) => setDatePreset(e.target.value as DatePresetType)}
              className="bg-transparent text-zinc-200 font-semibold focus:outline-none cursor-pointer text-xs"
            >
              {DATE_PRESET_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value} className="bg-zinc-900 text-zinc-300">
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {datePreset === 'CUSTOM' && (
            <div className="flex items-center gap-1.5 bg-zinc-950/80 border border-zinc-800 px-2.5 py-1 rounded-lg">
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="bg-transparent text-zinc-200 text-xs focus:outline-none"
              />
              <span className="text-zinc-600">→</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="bg-transparent text-zinc-200 text-xs focus:outline-none"
              />
            </div>
          )}
        </div>
      </div>

      {/* Sub-view 1: Email Alert Stream */}
      {ingestMode === 'ALERTS' && (
        <>
          <IngestToolbar
            mode="INGEST"
            hideAccountSelector={true}
            hideDateSelector={true} // 👈 hides duplicate date dropdown from inner toolbar
            datePreset={datePreset}
            onDatePresetChange={setDatePreset}
            startDate={startDate}
            endDate={endDate}
            onStartDateChange={setStartDate}
            onEndDateChange={setEndDate}
            onTriggerSync={onTriggerSync}
            syncing={syncing}
            stagingSelectedCount={selectedIds.length}
            stagingPayloads={stagingPayloads}
            hideDuplicates={hideDuplicates}
            onToggleHideDuplicates={() => setHideDuplicates((prev) => !prev)}
          />

          <PayloadTable
            payloads={stagingPayloads}
            selectedIds={selectedIds}
            onSelectPayload={onSelectPayload}
            onToggleSelectAll={() =>
              setSelectedIds(
                selectedIds.length === stagingPayloads.length
                  ? []
                  : stagingPayloads.map((p) => p.id || (p as any).payload_hash)
              )
            }
            onToggleSelectOne={(id: string) =>
              setSelectedIds((prev) =>
                prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
              )
            }
          />
        </>
      )}

      {/* Sub-view 2: Harvested PDF Statements */}
      {ingestMode === 'STATEMENTS' && (
        <StatementStagingTab
          accountOptions={accountOptions}
          datePreset={datePreset}
          startDate={startDate}
          endDate={endDate}
          onNotification={onNotification}
        />
      )}
    </div>
  );
};