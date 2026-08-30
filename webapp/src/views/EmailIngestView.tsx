import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  emailIngestApi,
  fetchAccountOptions,
  fetchTaxonomyOptions,
  DEFAULT_ACCOUNT_OPTIONS,
  type AccountOption,
  type EmailPayload,
  type IngestStats,
  type GetPayloadsParams,
  type BalanceAuditResponse,
  type TaxonomyOption,
} from '../api/emailIngestApi';

import { useLiveIngestStream } from '../hooks/useLiveIngestStream';
import { PayloadTable } from '../components/emailIngest/PayloadTable';
import { PayloadInspectorModal } from '../components/emailIngest/PayloadInspectorModal';
import { IngestToolbar } from '../components/emailIngest/IngestToolbar';

type ActiveTab = 'INGEST' | 'VAULT' | 'PROCESS_STAGING';
type DatePresetType = 'ALL' | 'THIS_WEEK' | 'THIS_MONTH' | 'LAST_MONTH' | 'LAST_6_MONTHS' | 'CUSTOM';

export const EmailIngestView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ActiveTab>('INGEST');
  const [accountOptions, setAccountOptions] = useState<AccountOption[]>(DEFAULT_ACCOUNT_OPTIONS);
  const [selectedAccount, setSelectedAccount] = useState<string>('0060');

  const [isAuditing, setIsAuditing] = useState<boolean>(false);
  const [auditStats, setAuditStats] = useState<{ count: number } | null>(null);

  const [isLivePollingEnabled, setIsLivePollingEnabled] = useState<boolean>(true);
  const [syncing, setSyncing] = useState<boolean>(false);
  const [committing, setCommitting] = useState<boolean>(false);

  const {
    tunnel,
    stagingPayloads,
    setStagingPayloads,
    isLiveFetching,
    lastSyncedAt,
    updateLastSyncedTimestamp,
    isSyncingRef,
  } = useLiveIngestStream(activeTab, isLivePollingEnabled, syncing, committing);

  const [stagingSelectedIds, setStagingSelectedIds] = useState<string[]>([]);
  const [dbPayloads, setDbPayloads] = useState<EmailPayload[]>([]);
  const [dbSelectedIds, setDbSelectedIds] = useState<string[]>([]);
  const [stats, setStats] = useState<IngestStats | null>(null);
  const [loadingDb, setLoadingDb] = useState<boolean>(false);
  
  // 🎯 Updated State: Staging for Reconciliation
  const [stagingForMatching, setStagingForMatching] = useState<boolean>(false);

  const [selectedPayload, setSelectedPayload] = useState<EmailPayload | null>(null);
  const [notification, setNotification] = useState<string | null>(null);

  const [datePreset, setDatePreset] = useState<DatePresetType>('THIS_WEEK');
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [taxonomyTree, setTaxonomyTree] = useState<TaxonomyOption[]>([]);

  const [showStagedOnly, setShowStagedOnly] = useState<boolean>(false);

  useEffect(() => {
    const init = async () => {
      const [options, tree] = await Promise.all([fetchAccountOptions(), fetchTaxonomyOptions()]);
      if (options?.length > 0) {
        setAccountOptions(options);
        const defaultAccExists = options.some((opt) => opt.value === '0060');
        setSelectedAccount(defaultAccExists ? '0060' : options[0].value);
      }
      setTaxonomyTree(tree || []);
    };
    init();
  }, []);

  const filterParams: GetPayloadsParams = useMemo(() => {
    const params: GetPayloadsParams & { account?: string } = { date_preset: datePreset, account: selectedAccount,staged_only: showStagedOnly, };
    if (datePreset === 'CUSTOM' && startDate.length === 10 && endDate.length === 10) {
      params.start_date = startDate;
      params.end_date = endDate;
      
    }
    return params;
  }, [datePreset, startDate, endDate, selectedAccount,showStagedOnly]);

  const handleTriggerSync = async () => {
    isSyncingRef.current = true;
    setSyncing(true);
    setNotification(null);
    try {
      const res = await emailIngestApi.triggerSync(filterParams);
      if (res?.previews && Array.isArray(res.previews)) {
        const uncommittedPreviews: EmailPayload[] = res.previews.map((item: any, index: number) => {
          const parsed = item.parsed_transaction || {};
          const raw = item.raw_payload || {};
          const isDup = parsed.is_duplicate || item.is_duplicate;

          return {
            id: item.payload_hash || `preview-${index}`,
            source: raw.source || 'GMAIL_API',
            bank_name: parsed.bank_name || 'SOUTH INDIAN BANK',
            merchant: parsed.merchant && parsed.merchant !== 'UNKNOWN VENDOR' ? parsed.merchant : raw.subject,
            amount: parsed.amount ? parseFloat(parsed.amount) : null,
            txn_type: parsed.txn_type || 'DEBIT',
            status: isDup ? 'DUPLICATE' : parsed.is_parsed ? 'PARSED' : 'UNPARSED',
            subject: raw.subject,
            email_from: raw.email_from,
            email_date: raw.email_date,
            created_at: raw.email_date || new Date().toISOString(),
            body: raw.decrypted_body,
            raw_item: item,
          } as any;
        });

        setStagingPayloads(uncommittedPreviews);
        const nonDuplicateIds = uncommittedPreviews.filter((p) => p.status !== 'DUPLICATE').map((p) => p.id);
        setStagingSelectedIds(nonDuplicateIds);
        updateLastSyncedTimestamp();

        const dupCount = uncommittedPreviews.length - nonDuplicateIds.length;
        setNotification(
          `Fetched ${uncommittedPreviews.length} email preview(s)${dupCount > 0 ? ` (${dupCount} already exist in Vault)` : ''}.`
        );
      }
    } catch (err) {
      console.error('Gmail sync failed:', err);
      setNotification('Failed to sync Gmail stream.');
    } finally {
      setSyncing(false);
      isSyncingRef.current = false;
    }
  };

  const handleCommitSelected = async () => {
    if (stagingSelectedIds.length === 0) return;
    setCommitting(true);
    setNotification(null);
    try {
      const selectedItemsToCommit = stagingPayloads
        .filter((p) => stagingSelectedIds.includes(p.id))
        .map((p: any) => p.raw_item || p);

      const res = await emailIngestApi.commitSelectedPayloads(selectedItemsToCommit);
      setStagingPayloads((prev) => prev.filter((p) => !stagingSelectedIds.includes(p.id)));
      setStagingSelectedIds([]);

      const dupCount = res?.duplicates_detected || 0;
      const committedCount = res?.committed_count || 0;

      setNotification(
        `Committed ${committedCount} item(s) to DB${dupCount > 0 ? ` (${dupCount} flagged as DUPLICATE)` : ''}.`
      );
    } catch (err) {
      console.error('Failed to commit selected payloads:', err);
      setNotification('Failed to commit selected items.');
    } finally {
      setCommitting(false);
    }
  };

  // 🎯 Action: Stage Selected Payload Rows for Statement Matching
  // const handleStageForMatching = async () => {
  //   if (dbSelectedIds.length === 0) return;
  //   setStagingForMatching(true);
  //   try {
  //     await emailIngestApi.stageForMatching(dbSelectedIds);

  //     // Locally update state to reflect "STAGED" status immediately
  //     setDbPayloads((prev) =>
  //       prev.map((item) =>
  //         dbSelectedIds.includes(item.id || (item as any).payload_hash)
  //           ? { ...item, status: 'STAGED', is_staged_for_matching: true }
  //           : item
  //       )
  //     );

  //     setNotification(`Marked ${dbSelectedIds.length} item(s) for Stagging.`);
  //     setDbSelectedIds([]);
  //   } catch (err) {
  //     console.error('Failed to stage payloads:', err);
  //     setNotification('Failed to stage selected records for matching.');
  //   } finally {
  //     setStagingForMatching(false);
  //   }
  // };

  const handleStageForMatching = async () => {
  if (dbSelectedIds.length === 0) return;
  setStagingForMatching(true);
  try {
    await emailIngestApi.stageForMatching(dbSelectedIds);

    // 🎯 Instantly remove staged rows from current view list
    setDbPayloads((prev) =>
      prev.filter((item) => !dbSelectedIds.includes(item.id || (item as any).payload_hash))
    );

    setNotification(`Staged ${dbSelectedIds.length} item(s) for statement upload matching.`);
    setDbSelectedIds([]);
  } catch (err) {
    console.error('Failed to stage payloads:', err);
    setNotification('Failed to stage selected records.');
  } finally {
    setStagingForMatching(false);
  }
};

  const handleBatchSaveTaxonomy = async (
    updates: Array<{ payloadId: string; categoryName: string; subcategoryName: string }>
  ) => {
    try {
      await emailIngestApi.batchUpdateTaxonomy(updates);

      setDbPayloads((prev) =>
        prev.map((item) => {
          const update = updates.find(
            (u) => u.payloadId === item.id || u.payloadId === (item as any).payload_hash
          );
          if (update) {
            return {
              ...item,
              taxonomy_payload: {
                ...item.taxonomy_payload,
                taxonomy: {
                  category_name: update.categoryName,
                  subcategory_name: update.subcategoryName,
                },
              },
            };
          }
          return item;
        })
      );

      setNotification(`Successfully saved taxonomy batch for ${updates.length} item(s).`);
    } catch (err) {
      console.error('Failed batch taxonomy update:', err);
      setNotification('Failed to save taxonomy updates.');
    }
  };

  const handleRunAudit = async () => {
    setIsAuditing(true);
    try {
      const data: BalanceAuditResponse = await emailIngestApi.runBalanceAudit(selectedAccount);
      const syntheticGaps = (data.results || []).filter((item: any) => item.is_synthetic_gap);

      setDbPayloads((prev) => {
        const cleanPrev = prev.filter((item: any) => !item.is_synthetic_gap);
        return [...cleanPrev, ...syntheticGaps].sort(
          (a: any, b: any) =>
            new Date(b.email_date || b.created_at).getTime() - new Date(a.email_date || a.created_at).getTime()
        );
      });

      setAuditStats({ count: data.discrepancies_found || 0 });
      setNotification(`Audit complete for A/c X${selectedAccount}. ${data.discrepancies_found || 0} gap(s) detected.`);
    } catch (err) {
      console.error('Failed audit:', err);
      setNotification('Failed to execute balance audit.');
    } finally {
      setIsAuditing(false);
    }
  };

  const handleToggleSelectAll = () => {
    if (activeTab === 'INGEST') {
      setStagingSelectedIds(
        stagingSelectedIds.length === stagingPayloads.length ? [] : stagingPayloads.map((p) => p.id)
      );
    } else if (activeTab === 'VAULT') {
      setDbSelectedIds(
        dbSelectedIds.length === dbPayloads.length ? [] : dbPayloads.map((p) => p.id || (p as any).payload_hash)
      );
    }
  };

  const handleToggleSelectOne = (id: string) => {
    if (activeTab === 'INGEST') {
      setStagingSelectedIds((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
    } else if (activeTab === 'VAULT') {
      setDbSelectedIds((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
    }
  };

  const fetchVaultData = useCallback(async () => {
    setLoadingDb(true);
    try {
      const [payloadRes, statsRes] = await Promise.all([
        emailIngestApi.getPayloads(filterParams),
        emailIngestApi.getStats(filterParams),
      ]);
      const rawList = payloadRes?.results || payloadRes?.data || payloadRes || [];
      const listArray = Array.isArray(rawList) ? rawList : [];

      const enrichedPayloads = listArray.map((item: any) => {
        let headers = item.headers_json || {};
        if (typeof headers === 'string') {
          try {
            headers = JSON.parse(headers);
          } catch (e) {
            headers = {};
          }
        }

        let taxonomyPayload = item.taxonomy_payload || {};
        if (typeof taxonomyPayload === 'string') {
          try {
            taxonomyPayload = JSON.parse(taxonomyPayload);
          } catch (e) {
            taxonomyPayload = {};
          }
        }

        const summary = headers.parsed_summary || {};

        return {
          ...item,
          headers_json: headers,
          taxonomy_payload: taxonomyPayload,
          balance: item.balance || summary.balance || null,
          upi_ref: item.upi_ref || summary.upi_ref || null,
          account_last4: item.account_last4 || summary.account || null,
          bank_name: item.bank_name || summary.bank || 'SOUTH INDIAN BANK',
        };
      });

      setDbPayloads(enrichedPayloads);
      setStats(statsRes || null);
      setDbSelectedIds([]);
      setAuditStats(null);
    } catch (err) {
      console.error('Failed to fetch DB items:', err);
      setDbPayloads([]);
    } finally {
      setLoadingDb(false);
    }
  }, [filterParams]);

  useEffect(() => {
    if (activeTab === 'VAULT') fetchVaultData();
  }, [activeTab, fetchVaultData]);

  return (
    <div className="p-6 space-y-6 bg-zinc-950 min-h-screen text-zinc-100 font-sans">
      <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center border-b border-zinc-800 pb-4 gap-4">
        <div>
          <h1 className="text-xl font-bold font-mono text-zinc-100">Email & Webhook Ingest Subsystem</h1>
          <p className="text-xs text-zinc-400">
            Multi-Stream Real-Time Ingestion (Tunnel Status: <span className={tunnel.status === 'ONLINE' ? 'text-emerald-400' : 'text-red-400'}>{tunnel.status}</span>)
          </p>
        </div>
        <div className="flex items-center gap-4">
          {activeTab === 'INGEST' && (
            <label className="flex items-center gap-2 cursor-pointer text-xs font-mono bg-zinc-900 border border-zinc-800 px-3 py-1.5 rounded select-none">
              <input
                type="checkbox"
                checked={isLivePollingEnabled}
                onChange={(e) => setIsLivePollingEnabled(e.target.checked)}
                className="rounded border-zinc-700 text-emerald-500 focus:ring-0 cursor-pointer"
              />
              <span className={isLivePollingEnabled ? 'text-emerald-400 font-bold' : 'text-zinc-500'}>
                Auto-Live Stream (5s)
              </span>
              {isLiveFetching && <span className="animate-pulse text-emerald-400">●</span>}
            </label>
          )}

          {stats && activeTab === 'VAULT' && (
            <div className="flex gap-2 text-xs font-mono">
              <div className="bg-zinc-900 border border-zinc-800 px-3 py-1.5 rounded">
                <span className="text-zinc-500">TOTAL: </span>
                <span className="text-zinc-200 font-bold">{stats.total}</span>
              </div>
              <div className="bg-zinc-900 border border-zinc-800 px-3 py-1.5 rounded">
                <span className="text-zinc-500">PARSED: </span>
                <span className="text-emerald-400 font-bold">{stats.parsed}</span>
              </div>
              <div className="bg-zinc-900 border border-zinc-800 px-3 py-1.5 rounded">
                <span className="text-zinc-500">DUPLICATES: </span>
                <span className="text-amber-400 font-bold">{stats.duplicate}</span>
              </div>
            </div>
          )}

          {lastSyncedAt && (
            <span className="text-[11px] font-mono text-zinc-500">
              Last Synced: <span className="text-zinc-300">{lastSyncedAt}</span>
            </span>
          )}
        </div>
      </div>

      <div className="flex border-b border-zinc-800 gap-4 font-mono text-xs overflow-x-auto">
        <button
          onClick={() => setActiveTab('INGEST')}
          className={`pb-3 font-bold cursor-pointer transition-colors ${
            activeTab === 'INGEST' ? 'text-emerald-400 border-b-2 border-emerald-500' : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          ⚡ Tab 1: Email Sync & Tunnel Ingest ({stagingPayloads.length})
        </button>
        <button
          onClick={() => setActiveTab('VAULT')}
          className={`pb-3 font-bold cursor-pointer transition-colors ${
            activeTab === 'VAULT' ? 'text-indigo-400 border-b-2 border-indigo-500' : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          💾 Tab 2: Database Vault ({dbPayloads.length})
        </button>
      </div>

      {notification && (
        <div className="bg-emerald-950/80 border border-emerald-800 text-emerald-300 text-xs font-mono p-3 rounded-lg flex items-center justify-between">
          <span>ℹ️ {notification}</span>
          <button onClick={() => setNotification(null)} className="text-emerald-500 hover:text-emerald-200 font-bold px-1">✕</button>
        </div>
      )}

      {activeTab === 'INGEST' && (
        <div className="space-y-4">
          <IngestToolbar
            mode="INGEST"
            datePreset={datePreset}
            onDatePresetChange={setDatePreset}
            startDate={startDate}
            endDate={endDate}
            onStartDateChange={setStartDate}
            onEndDateChange={setEndDate}
            onTriggerSync={handleTriggerSync}
            syncing={syncing}
            onCommitSelected={handleCommitSelected}
            committing={committing}
            stagingSelectedCount={stagingSelectedIds.length}
            totalCount={stagingPayloads.length}

          />

          <PayloadTable
            payloads={stagingPayloads}
            selectedIds={stagingSelectedIds}
            taxonomyTree={taxonomyTree}
            onSelectPayload={(item) => setSelectedPayload(item)}
            onToggleSelectAll={handleToggleSelectAll}
            onToggleSelectOne={handleToggleSelectOne}
            onBatchSaveTaxonomy={handleBatchSaveTaxonomy}
          />
        </div>
      )}

      {activeTab === 'VAULT' && (
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
  onRunAudit={handleRunAudit}
  isAuditing={isAuditing}
  auditStats={auditStats}
  onStageSelected={handleStageForMatching}
  stagingForMatching={stagingForMatching}
  dbSelectedCount={dbSelectedIds.length}
  totalCount={dbPayloads.length}
  showStagedOnly={showStagedOnly}
  onToggleStagedOnly={setShowStagedOnly} 
/>

          {loadingDb ? (
            <div className="py-12 text-center font-mono text-xs text-zinc-500">
              Fetching records from MySQL database...
            </div>
          ) : (
            <PayloadTable
              payloads={dbPayloads}
              selectedIds={dbSelectedIds}
              taxonomyTree={taxonomyTree}
              onSelectPayload={(item) => setSelectedPayload(item)}
              onToggleSelectAll={handleToggleSelectAll}
              onToggleSelectOne={handleToggleSelectOne}
              onBatchSaveTaxonomy={handleBatchSaveTaxonomy}
            />
          )}
        </div>
      )}

      <PayloadInspectorModal payload={selectedPayload} onClose={() => setSelectedPayload(null)} />
    </div>
  );
};