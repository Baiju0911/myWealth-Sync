import React, { useState, useEffect, useCallback } from 'react';
import {
  fetchAccountOptions,
  fetchTaxonomyOptions,
  DEFAULT_ACCOUNT_OPTIONS,
  type AccountOption,
  type EmailPayload,
  type IngestStats,
  type TaxonomyOption,
  type DatePresetType,
} from '../api/emailIngestApi';

import { useLiveIngestStream } from '../hooks/useLiveIngestStream';
import { useMultiYearSync } from '../hooks/useMultiYearSync';
import { PayloadInspectorModal } from '../components/emailIngest/PayloadInspectorModal';
import { LiveBufferTab } from '../components/emailIngest/LiveBufferTab';
import { DatabaseVaultTab } from '../components/emailIngest/DatabaseVaultTab';

type ActiveTab = 'INGEST' | 'VAULT';

export const EmailIngestView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ActiveTab>('INGEST');
  const [accountOptions, setAccountOptions] = useState<AccountOption[]>(DEFAULT_ACCOUNT_OPTIONS);
  const [selectedAccount, setSelectedAccount] = useState('0060');
  const [taxonomyTree, setTaxonomyTree] = useState<TaxonomyOption[]>([]);
  const [stats, setStats] = useState<IngestStats | null>(null);

  const [datePreset, setDatePreset] = useState<DatePresetType>('THIS_WEEK');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [isLivePollingEnabled, setIsLivePollingEnabled] = useState(true);

  const [selectedPayload, setSelectedPayload] = useState<EmailPayload | null>(null);
  const [notification, setNotification] = useState<{ type: 'info' | 'success' | 'error'; message: string } | null>(null);

  const { tunnel, stagingPayloads, setStagingPayloads, isLiveFetching, lastSyncedAt, updateLastSyncedTimestamp } =
    useLiveIngestStream(activeTab, isLivePollingEnabled, false, false);

  const notify = useCallback((n: any) => setNotification(n), []);

  const { syncing, syncProgress, triggerSync } = useMultiYearSync(
    selectedAccount,
    datePreset,
    startDate,
    endDate,
    async () => {
      updateLastSyncedTimestamp();
    },
    notify
  );

  useEffect(() => {
    Promise.all([fetchAccountOptions(), fetchTaxonomyOptions()]).then(([opts, tree]) => {
      if (opts?.length > 0) setAccountOptions(opts);
      setTaxonomyTree(tree || []);
    });
  }, []);

  return (
    <div className="p-6 space-y-5 bg-zinc-950 min-h-screen text-zinc-100 font-sans">
      {/* Top Header */}
      <div className="flex justify-between items-center border-b border-zinc-800/80 pb-4">
        <div>
          <h1 className="text-lg font-bold font-mono text-zinc-100 flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)]" />
            Transaction Vault & Stream Ingest
          </h1>
          <span className="text-[11px] text-zinc-500 font-mono">Tunnel: {tunnel.status}</span>
        </div>

        <div className="flex items-center gap-2.5">
          {activeTab === 'INGEST' && (
            <label className="flex items-center gap-2 text-xs font-mono bg-zinc-900 border border-zinc-800 px-3 py-1.5 rounded-lg cursor-pointer">
              <input
                type="checkbox"
                checked={isLivePollingEnabled}
                onChange={(e) => setIsLivePollingEnabled(e.target.checked)}
                className="rounded border-zinc-700 bg-zinc-800 text-emerald-500 focus:ring-0"
              />
              <span>Auto-Poll (4s)</span>
              {isLiveFetching && <span className="h-2 w-2 rounded-full bg-emerald-400 animate-ping" />}
            </label>
          )}
          {lastSyncedAt && <span className="text-[11px] font-mono text-zinc-500">Updated: {lastSyncedAt}</span>}
        </div>
      </div>

      {/* Sync Telemetry Banner */}
      {syncing && (
        <div className="bg-zinc-900 border border-emerald-500/30 p-3.5 rounded-xl flex justify-between items-center text-xs font-mono">
          <div className="flex items-center gap-2.5">
            <span className="animate-spin text-emerald-400">⏳</span>
            <span>
              Streaming Gmail Bank Ingest {syncProgress.activeYear ? `(Year ${syncProgress.activeYear})` : ''}...
            </span>
          </div>
          <div className="text-zinc-400">
            Discovered: <span className="text-emerald-400 font-bold">{syncProgress.itemsDiscovered}</span> | Time:{' '}
            <span className="text-zinc-200">{syncProgress.elapsedSeconds}s</span>
          </div>
        </div>
      )}

      {/* Primary Navigation Tabs */}
      <div className="flex border-b border-zinc-800 gap-6 font-mono text-xs">
        <button
          onClick={() => setActiveTab('INGEST')}
          className={`pb-3 font-bold border-b-2 flex items-center gap-2 cursor-pointer ${
            activeTab === 'INGEST' ? 'text-emerald-400 border-emerald-500' : 'text-zinc-500 border-transparent hover:text-zinc-300'
          }`}
        >
          <span>⚡ Live Staging Buffer</span>
          <span className="bg-zinc-900 border border-zinc-700 px-2 py-0.5 rounded-full text-[10px]">
            {stagingPayloads.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab('VAULT')}
          className={`pb-3 font-bold border-b-2 flex items-center gap-2 cursor-pointer ${
            activeTab === 'VAULT' ? 'text-indigo-400 border-indigo-500' : 'text-zinc-500 border-transparent hover:text-zinc-300'
          }`}
        >
          <span>💾 Database Vault</span>
          <span className="bg-zinc-900 border border-zinc-700 px-2 py-0.5 rounded-full text-[10px]">
            {stats?.total || 0}
          </span>
        </button>
      </div>

      {notification && (
        <div
          className={`p-3 rounded-xl border text-xs font-mono flex justify-between items-center ${
            notification.type === 'success'
              ? 'bg-emerald-950/80 border-emerald-700/80 text-emerald-200'
              : notification.type === 'error'
              ? 'bg-rose-950/80 border-rose-700/80 text-rose-200'
              : 'bg-zinc-900 border-zinc-700 text-zinc-200'
          }`}
        >
          <span>{notification.message}</span>
          <button onClick={() => setNotification(null)} className="text-zinc-400 hover:text-white px-2 cursor-pointer font-bold">
            ✕
          </button>
        </div>
      )}

      {/* Tab 1: Live Staging Buffer (Emails + PDF Statements) */}
      {activeTab === 'INGEST' && (
        <LiveBufferTab
          stagingPayloads={stagingPayloads}
          setStagingPayloads={setStagingPayloads}
          onTriggerSync={triggerSync}
          syncing={syncing}
          datePreset={datePreset}
          setDatePreset={setDatePreset}
          startDate={startDate}
          setStartDate={setStartDate}
          endDate={endDate}
          setEndDate={setEndDate}
          selectedAccount={selectedAccount}
          setSelectedAccount={setSelectedAccount}
          accountOptions={accountOptions}
          onSelectPayload={setSelectedPayload}
          onNotification={notify}
        />
      )}

      {/* Tab 2: Database Vault (Alerts + Statement Vault) */}
      {activeTab === 'VAULT' && (
        <DatabaseVaultTab
          selectedAccount={selectedAccount}
          setSelectedAccount={setSelectedAccount}
          accountOptions={accountOptions}
          taxonomyTree={taxonomyTree}
          datePreset={datePreset}
          setDatePreset={setDatePreset}
          startDate={startDate}
          setStartDate={setStartDate}
          endDate={endDate}
          setEndDate={setEndDate}
          onSelectPayload={setSelectedPayload}
          onNotification={notify}
          onStatsLoaded={setStats}
        />
      )}

      <PayloadInspectorModal payload={selectedPayload} onClose={() => setSelectedPayload(null)} />
    </div>
  );
};