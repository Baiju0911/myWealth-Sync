import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  emailIngestApi,
  fetchAccountOptions,
  fetchTaxonomyOptions,
  DEFAULT_ACCOUNT_OPTIONS,
  type AccountOption,
  type EmailPayload,
  type IngestStats,
  type GetPayloadsParams,
  type TaxonomyOption,
  type DatePresetType,
} from '../api/emailIngestApi';

import { useLiveIngestStream } from '../hooks/useLiveIngestStream';
import { PayloadTable } from '../components/emailIngest/PayloadTable';
import { PayloadInspectorModal } from '../components/emailIngest/PayloadInspectorModal';
import { IngestToolbar } from '../components/emailIngest/IngestToolbar';

type ActiveTab = 'INGEST' | 'VAULT' | 'PROCESS_STAGING';

const SYNC_SESSION_KEY = 'mywealth_active_sync_session';

interface SyncSession {
  datePreset: string;
  currentYear: number;
  startYear: number;
  selectedAccount: string;
  status: 'IN_PROGRESS' | 'COMPLETED';
  timestamp?: number;
}

const getStoredSyncSession = (): SyncSession | null => {
  try {
    const raw = localStorage.getItem(SYNC_SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

const saveSyncSession = (session: SyncSession) => {
  localStorage.setItem(
    SYNC_SESSION_KEY,
    JSON.stringify({ ...session, timestamp: Date.now() })
  );
};

const clearSyncSession = () => {
  localStorage.removeItem(SYNC_SESSION_KEY);
};

export const EmailIngestView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ActiveTab>('INGEST');
  const [accountOptions, setAccountOptions] = useState<AccountOption[]>(DEFAULT_ACCOUNT_OPTIONS);
  const [selectedAccount, setSelectedAccount] = useState<string>('0060');

  const [isLivePollingEnabled, setIsLivePollingEnabled] = useState<boolean>(true);
  const [syncing, setSyncing] = useState<boolean>(false);
  const [committing, setCommitting] = useState<boolean>(false);
  const [isDiscarding, setIsDiscarding] = useState<boolean>(false);
  const [hideDuplicates, setHideDuplicates] = useState<boolean>(false);

  // Real-Time Progress & Telemetry Metrics
  const [syncProgress, setSyncProgress] = useState<{
    activeYear: number | null;
    totalYears: number;
    completedYears: number;
    itemsDiscovered: number;
    elapsedSeconds: number;
  }>({
    activeYear: null,
    totalYears: 0,
    completedYears: 0,
    itemsDiscovered: 0,
    elapsedSeconds: 0,
  });

  const timerRef = useRef<number | null>(null);
  const hasMountedRef = useRef<boolean>(false);

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

  const [stagingForMatching, setStagingForMatching] = useState<boolean>(false);
  const [unstagingForMatching, setUnstagingForMatching] = useState<boolean>(false);

  const [selectedPayload, setSelectedPayload] = useState<EmailPayload | null>(null);
  const [notification, setNotification] = useState<{ type: 'info' | 'success' | 'error'; message: string } | null>(null);

  const [datePreset, setDatePreset] = useState<DatePresetType>('THIS_WEEK');
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [taxonomyTree, setTaxonomyTree] = useState<TaxonomyOption[]>([]);
  const [showStagedOnly, setShowStagedOnly] = useState<boolean>(false);

  const displayedStagingPayloads = useMemo(() => {
    if (!hideDuplicates) return stagingPayloads;
    return stagingPayloads.filter(
      (p) => p.status !== 'DUPLICATE' && !(p as any).is_duplicate
    );
  }, [stagingPayloads, hideDuplicates]);

  useEffect(() => {
    if (!notification) return;
    const timer = setTimeout(() => {
      setNotification(null);
    }, 4500);
    return () => clearTimeout(timer);
  }, [notification]);

  useEffect(() => {
    const init = async () => {
      const [options, tree] = await Promise.all([
        fetchAccountOptions(),
        fetchTaxonomyOptions(),
      ]);
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
    const params: GetPayloadsParams & { account?: string } = {
      date_preset: datePreset,
      account: selectedAccount,
      staged_only: showStagedOnly,
    };
    if (datePreset === 'CUSTOM' && startDate.length === 10 && endDate.length === 10) {
      params.start_date = startDate;
      params.end_date = endDate;
    }
    return params;
  }, [datePreset, startDate, endDate, selectedAccount, showStagedOnly]);

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
          } catch {
            headers = {};
          }
        }

        let taxonomyPayload = item.taxonomy_payload || {};
        if (typeof taxonomyPayload === 'string') {
          try {
            taxonomyPayload = JSON.parse(taxonomyPayload);
          } catch {
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
          bank_name: item.bank_name || summary.bank || 'UNKNOWN BANK',
        };
      });

      setDbPayloads(enrichedPayloads);
      setStats(statsRes || null);
      setDbSelectedIds([]);
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

  // Fully Hydrating Refresh Logic: Transmits account_id, account_display_name, and metadata
  const refreshStagingTable = useCallback(async () => {
    try {
      const res = await emailIngestApi.getPendingStagingPayloads();
      if (res?.previews && Array.isArray(res.previews)) {
        const liveItems: EmailPayload[] = res.previews.map((item: any, index: number) => {
          const parsed = item.parsed_transaction || {};
          const raw = item.raw_payload || {};
          const headers = raw.headers_json || {};
          const summary = headers.parsed_summary || {};
          const isDup = Boolean(parsed.is_duplicate || item.is_duplicate);

          const uniqueId =
            item.payload_hash ||
            parsed.txn_fingerprint ||
            `live-${raw.email_date || Date.now()}-${index}`;

          const resolvedBank = parsed.bank_name || summary.bank || 'SOUTH INDIAN BANK';
          const resolvedAccountLast4 = parsed.account_last4 || summary.account || null;
          const resolvedAccountName = parsed.account_display_name || summary.account_name || 'Account Not Found';

          return {
            id: uniqueId,
            source: raw.source || (headers.is_merged ? 'MERGED_STREAM' : 'IOS_SMS'),
            bank_name: resolvedBank,
            account_last4: resolvedAccountLast4,
            account_id: parsed.account_id || null,
            account_display_name: resolvedAccountName,
            merchant:
              parsed.merchant && parsed.merchant !== 'UNKNOWN VENDOR'
                ? parsed.merchant
                : raw.subject || 'UPI Transfer',
            amount: parsed.amount ? parseFloat(parsed.amount) : null,
            balance: parsed.balance || summary.balance || null,
            upi_ref: parsed.upi_ref || summary.upi_ref || null,
            txn_type: parsed.txn_type || 'DEBIT',
            payment_rail: parsed.payment_rail || 'UNKNOWN',
            is_self_transfer: Boolean(parsed.is_self_transfer),
            status: isDup
              ? 'DUPLICATE'
              : parsed.is_merged
              ? 'MATCHED_2_WAY'
              : parsed.is_parsed
              ? 'PARSED'
              : 'UNPARSED',
            subject: raw.subject || raw.decrypted_body || 'Incoming SMS',
            email_from: raw.email_from || raw.sender || 'UNKNOWN_SENDER',
            email_date: raw.email_date || new Date().toISOString(),
            created_at: raw.email_date || new Date().toISOString(),
            body: raw.decrypted_body || raw.body,
            raw_item: item,
            parsed_transaction: parsed,
          } as any;
        });

        setStagingPayloads(liveItems);
        updateLastSyncedTimestamp();
      }
    } catch (err) {
      console.error('Failed to refresh staging table:', err);
    }
  }, [setStagingPayloads, updateLastSyncedTimestamp]);

  const runMultiYearSync = async (
    fromYear: number,
    startYear: number,
    account: string
  ) => {
    if (isSyncingRef.current) return;
    isSyncingRef.current = true;
    setSyncing(true);

    const totalYears = fromYear - startYear + 1;
    setSyncProgress({
      activeYear: fromYear,
      totalYears,
      completedYears: 0,
      itemsDiscovered: 0,
      elapsedSeconds: 0,
    });

    timerRef.current = window.setInterval(() => {
      setSyncProgress((prev) => ({ ...prev, elapsedSeconds: prev.elapsedSeconds + 1 }));
    }, 1000);

    try {
      for (let year = fromYear; year >= startYear; year--) {
        setSyncProgress((prev) => ({ ...prev, activeYear: year }));

        saveSyncSession({
          datePreset: 'ALL',
          currentYear: year,
          startYear,
          selectedAccount: account,
          status: 'IN_PROGRESS',
        });

        const res = await emailIngestApi.triggerSync({
          date_preset: 'CUSTOM',
          start_date: `${year}-01-01`,
          end_date: `${year}-12-31`,
          account,
        });

        const addedThisYear = res?.total_fetched || res?.count || 0;
        setSyncProgress((prev) => ({
          ...prev,
          completedYears: prev.completedYears + 1,
          itemsDiscovered: prev.itemsDiscovered + addedThisYear,
        }));

        await refreshStagingTable();
      }

      clearSyncSession();
      setNotification({
        type: 'success',
        message: 'Completed full multi-year sync! All alerts buffered into staging.',
      });
      updateLastSyncedTimestamp();
    } catch (err) {
      console.error('Multi-year sync failed or interrupted:', err);
      setNotification({ type: 'error', message: 'Sync interrupted. Review console output.' });
    } finally {
      if (timerRef.current) clearInterval(timerRef.current);
      setSyncing(false);
      isSyncingRef.current = false;
      setSyncProgress((prev) => ({ ...prev, activeYear: null }));
    }
  };

  const handleTriggerSync = async () => {
    if (isSyncingRef.current) return;

    if (datePreset === 'ALL' || (datePreset as string) === 'ALL_TIME') {
      const currentYear = new Date().getFullYear();
      const startYear = 2020;
      await runMultiYearSync(currentYear, startYear, selectedAccount);
    } else {
      isSyncingRef.current = true;
      setSyncing(true);
      setSyncProgress({
        activeYear: new Date().getFullYear(),
        totalYears: 1,
        completedYears: 0,
        itemsDiscovered: 0,
        elapsedSeconds: 0,
      });

      timerRef.current = window.setInterval(() => {
        setSyncProgress((prev) => ({ ...prev, elapsedSeconds: prev.elapsedSeconds + 1 }));
      }, 1000);

      try {
        const res = await emailIngestApi.triggerSync({
          date_preset: datePreset,
          start_date: startDate,
          end_date: endDate,
          account: selectedAccount,
        });

        const previewCount = res?.total_fetched || res?.count || 0;
        setNotification({
          type: 'success',
          message: `Stream completed: ${previewCount} financial transactions buffered in ${res?.duration_seconds || 0}s.`,
        });
        updateLastSyncedTimestamp();
        await refreshStagingTable();
      } catch (err) {
        console.error('Gmail sync failed:', err);
        setNotification({ type: 'error', message: 'Gmail synchronization encountered an error.' });
      } finally {
        if (timerRef.current) clearInterval(timerRef.current);
        setSyncing(false);
        isSyncingRef.current = false;
        setSyncProgress((prev) => ({ ...prev, activeYear: null }));
      }
    }
  };

  useEffect(() => {
    if (hasMountedRef.current) return;
    hasMountedRef.current = true;

    const activeSession = getStoredSyncSession();
    if (activeSession && activeSession.status === 'IN_PROGRESS') {
      const isStale = Date.now() - (activeSession.timestamp || 0) > 30 * 60 * 1000;
      if (isStale) {
        clearSyncSession();
        return;
      }

      runMultiYearSync(
        activeSession.currentYear,
        activeSession.startYear,
        activeSession.selectedAccount
      );
    }
  }, []);

  const handleCommitSelected = async () => {
    if (stagingSelectedIds.length === 0) return;
    setCommitting(true);
    try {
      const selectedItemsToCommit = stagingPayloads
        .filter((p) => stagingSelectedIds.includes(p.id))
        .map((p: any) => p.raw_item || p);

      const res = await emailIngestApi.commitSelectedPayloads(selectedItemsToCommit);
      setStagingPayloads((prev) => prev.filter((p) => !stagingSelectedIds.includes(p.id)));
      setStagingSelectedIds([]);

      const dupCount = res?.duplicates_detected || 0;
      const committedCount = res?.committed_count || 0;

      setNotification({
        type: 'success',
        message: `Committed ${committedCount} alerts into Vault${dupCount > 0 ? ` (${dupCount} duplicate records reconciled)` : ''}.`,
      });
    } catch (err) {
      console.error('Failed to commit selected payloads:', err);
      setNotification({ type: 'error', message: 'Failed to commit selected items to Vault database.' });
    } finally {
      setCommitting(false);
    }
  };

  // Discard Selected Items from Tab 1 Staging Buffer
  const handleDiscardSelected = async () => {
    if (stagingSelectedIds.length === 0) return;
    
    const count = stagingSelectedIds.length;
    setIsDiscarding(true);
    try {
      await emailIngestApi.discardStagingPayloads(stagingSelectedIds);
      // Optimistically remove from state
      setStagingPayloads((prev) => prev.filter((p) => !stagingSelectedIds.includes(p.id)));
      setStagingSelectedIds([]);
      setNotification({
        type: 'info',
        message: `Removed ${count} item(s) from staging buffer.`,
      });
    } catch (err) {
      console.error('Failed to discard items:', err);
      setNotification({
        type: 'error',
        message: 'Failed to remove selected items from staging.',
      });
    } finally {
      setIsDiscarding(false);
    }
  };

  const handleStageForMatching = async () => {
    if (dbSelectedIds.length === 0) return;
    setStagingForMatching(true);

    try {
      const selectedGapObjects = dbPayloads.filter(
        (item: any) =>
          item.is_synthetic_gap &&
          dbSelectedIds.includes(item.id || (item as any).payload_hash)
      );

      const standardPayloadIds = dbSelectedIds.filter((id) => !id.startsWith('gap_'));

      await emailIngestApi.stageForMatching(standardPayloadIds, selectedGapObjects);

      setNotification({
        type: 'success',
        message: `Staged ${dbSelectedIds.length} item(s) for balance statement reconciliation.`,
      });
      setDbSelectedIds([]);
      fetchVaultData();
    } catch (err) {
      console.error('Failed to stage payloads:', err);
      setNotification({ type: 'error', message: 'Failed to stage selected records.' });
    } finally {
      setStagingForMatching(false);
    }
  };

  const handleUnstageSelected = async () => {
    if (dbSelectedIds.length === 0) return;
    setUnstagingForMatching(true);

    try {
      const res = await emailIngestApi.unstageFromMatching(dbSelectedIds);
      if (res.status === 'success') {
        setNotification({
          type: 'success',
          message: `Successfully unstaged ${res.unstaged_count} record(s).`,
        });
        setDbSelectedIds([]);
        fetchVaultData();
      }
    } catch (err) {
      console.error('Failed to unstage records:', err);
      setNotification({ type: 'error', message: 'Failed to unstage records.' });
    } finally {
      setUnstagingForMatching(false);
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

      setNotification({
        type: 'success',
        message: `Saved ledger classifications for ${updates.length} item(s).`,
      });
    } catch (err) {
      console.error('Failed batch taxonomy update:', err);
      setNotification({ type: 'error', message: 'Failed to persist ledger categorization.' });
    }
  };

  const handleToggleSelectAll = () => {
    if (activeTab === 'INGEST') {
      setStagingSelectedIds(
        stagingSelectedIds.length === displayedStagingPayloads.length
          ? []
          : displayedStagingPayloads.map((p) => p.id)
      );
    } else if (activeTab === 'VAULT') {
      setDbSelectedIds(
        dbSelectedIds.length === dbPayloads.length
          ? []
          : dbPayloads.map((p) => p.id || (p as any).payload_hash)
      );
    }
  };

  const handleToggleSelectOne = (id: string) => {
    if (activeTab === 'INGEST') {
      setStagingSelectedIds((prev) =>
        prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
      );
    } else if (activeTab === 'VAULT') {
      setDbSelectedIds((prev) =>
        prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
      );
    }
  };

  return (
    <div className="p-6 space-y-5 bg-zinc-950 min-h-screen text-zinc-100 font-sans selection:bg-emerald-500/20 selection:text-emerald-300">
      
      {/* Top Navigation & System Health Header */}
      <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center border-b border-zinc-800/80 pb-4 gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="h-2.5 w-2.5 rounded-full bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)]" />
            <h1 className="text-lg font-bold font-mono tracking-tight text-zinc-100">
              Transaction Vault & Stream Ingest
            </h1>
          </div>
          <p className="text-[11px] text-zinc-400 font-mono mt-1 flex items-center gap-2">
            <span>Tunnel Endpoint:</span>
            <span
              className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-[10px] font-semibold ${
                tunnel.status === 'ONLINE'
                  ? 'border-emerald-500/30 bg-emerald-950/30 text-emerald-400'
                  : 'border-rose-500/30 bg-rose-950/30 text-rose-400'
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${tunnel.status === 'ONLINE' ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'}`} />
              {tunnel.status}
            </span>
          </p>
        </div>

        {/* Action Status Pills */}
        <div className="flex items-center gap-2.5 flex-wrap">
          {activeTab === 'INGEST' && (
            <label className="flex items-center gap-2 cursor-pointer text-xs font-mono bg-zinc-900/90 hover:bg-zinc-800/80 border border-zinc-800 px-3 py-1.5 rounded-lg select-none transition-all">
              <input
                type="checkbox"
                checked={isLivePollingEnabled}
                onChange={(e) => setIsLivePollingEnabled(e.target.checked)}
                className="rounded border-zinc-700 bg-zinc-800 text-emerald-500 focus:ring-0 cursor-pointer"
              />
              <span className={isLivePollingEnabled ? 'text-emerald-400 font-semibold' : 'text-zinc-500'}>
                Auto-Poll (4s)
              </span>
              {isLiveFetching && <span className="h-2 w-2 rounded-full bg-emerald-400 animate-ping" />}
            </label>
          )}

          {stats && activeTab === 'VAULT' && (
            <div className="flex items-center gap-2 text-xs font-mono">
              <div className="bg-zinc-900 border border-zinc-800 px-3 py-1.5 rounded-lg">
                <span className="text-zinc-500 text-[10px]">TOTAL: </span>
                <span className="text-zinc-200 font-bold">{stats.total}</span>
              </div>
              <div className="bg-zinc-900 border border-zinc-800 px-3 py-1.5 rounded-lg">
                <span className="text-zinc-500 text-[10px]">PARSED: </span>
                <span className="text-emerald-400 font-bold">{stats.parsed}</span>
              </div>
              <div className="bg-zinc-900 border border-zinc-800 px-3 py-1.5 rounded-lg">
                <span className="text-zinc-500 text-[10px]">DUPLICATES: </span>
                <span className="text-amber-400 font-bold">{stats.duplicate}</span>
              </div>
            </div>
          )}

          {lastSyncedAt && (
            <div className="text-[11px] font-mono text-zinc-500 bg-zinc-900 border border-zinc-800 px-3 py-1.5 rounded-lg">
              Updated: <span className="text-zinc-300 font-medium">{lastSyncedAt}</span>
            </div>
          )}
        </div>
      </div>

      {/* Progress Telemetry */}
      {syncing && (
        <div className="bg-linear-to-r from-zinc-900 via-zinc-900/90 to-zinc-900 border border-emerald-500/30 p-4 rounded-xl shadow-[0_4px_20px_rgba(0,0,0,0.5)] animate-in fade-in slide-in-from-top-3">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
            <div className="flex items-center gap-3">
              <div className="h-8 w-8 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 animate-spin">
                ⏳
              </div>
              <div>
                <h4 className="text-xs font-bold font-mono text-zinc-100 flex items-center gap-2">
                  <span>Synchronizing Google Mail Bank Alerts</span>
                  {syncProgress.activeYear && (
                    <span className="bg-emerald-500/20 text-emerald-400 text-[10px] px-2 py-0.5 rounded-full border border-emerald-500/40">
                      YEAR {syncProgress.activeYear}
                    </span>
                  )}
                </h4>
                <p className="text-[11px] text-zinc-400 font-mono mt-0.5">
                  Streaming chunks directly to local disk buffer with AES deduplication.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-4 text-xs font-mono self-end sm:self-auto">
              <div className="text-right">
                <span className="text-zinc-500 block text-[10px]">DISCOVERED</span>
                <span className="text-emerald-400 font-bold text-sm">
                  {syncProgress.itemsDiscovered} items
                </span>
              </div>
              <div className="h-7 w-px bg-zinc-800" />
              <div className="text-right">
                <span className="text-zinc-500 block text-[10px]">DURATION</span>
                <span className="text-zinc-300 font-semibold">{syncProgress.elapsedSeconds}s</span>
              </div>
            </div>
          </div>

          {syncProgress.totalYears > 1 && (
            <div className="mt-3.5 space-y-1.5">
              <div className="flex justify-between text-[10px] font-mono text-zinc-400">
                <span>Multi-Year Ingestion Progress</span>
                <span>
                  {syncProgress.completedYears} of {syncProgress.totalYears} Years Complete
                </span>
              </div>
              <div className="w-full bg-zinc-800/80 rounded-full h-1.5 overflow-hidden">
                <div
                  className="bg-emerald-500 h-1.5 rounded-full transition-all duration-500"
                  style={{
                    width: `${Math.max(
                      5,
                      (syncProgress.completedYears / syncProgress.totalYears) * 100
                    )}%`,
                  }}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Primary Subsystem Tabs */}
      <div className="flex border-b border-zinc-800/80 gap-6 font-mono text-xs overflow-x-auto">
        <button
          onClick={() => setActiveTab('INGEST')}
          className={`pb-3 font-bold cursor-pointer transition-all border-b-2 flex items-center gap-2 ${
            activeTab === 'INGEST'
              ? 'text-emerald-400 border-emerald-500 drop-shadow-[0_2px_8px_rgba(52,211,153,0.3)]'
              : 'text-zinc-400 border-transparent hover:text-zinc-200'
          }`}
        >
          <span>⚡ Live Staging Buffer</span>
          <span className="bg-zinc-900 border border-zinc-700/80 text-zinc-300 px-2 py-0.5 rounded-full text-[10px]">
            {stagingPayloads.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab('VAULT')}
          className={`pb-3 font-bold cursor-pointer transition-all border-b-2 flex items-center gap-2 ${
            activeTab === 'VAULT'
              ? 'text-indigo-400 border-indigo-500 drop-shadow-[0_2px_8px_rgba(99,102,241,0.3)]'
              : 'text-zinc-400 border-transparent hover:text-zinc-200'
          }`}
        >
          <span>💾 Database Vault</span>
          <span className="bg-zinc-900 border border-zinc-700/80 text-zinc-300 px-2 py-0.5 rounded-full text-[10px]">
            {dbPayloads.length}
          </span>
        </button>
      </div>

      {/* Notifications Banner */}
      {notification && (
        <div
          className={`border text-xs font-mono p-3 rounded-xl flex items-center justify-between shadow-lg backdrop-blur-sm transition-all duration-300 animate-in fade-in slide-in-from-top-2 ${
            notification.type === 'success'
              ? 'bg-emerald-950/80 border-emerald-700/80 text-emerald-200'
              : notification.type === 'error'
              ? 'bg-rose-950/80 border-rose-700/80 text-rose-200'
              : 'bg-zinc-900/90 border-zinc-700 text-zinc-200'
          }`}
        >
          <div className="flex items-center gap-2.5">
            <span>{notification.type === 'success' ? '✅' : notification.type === 'error' ? '⚠️' : 'ℹ️'}</span>
            <span>{notification.message}</span>
          </div>
          <button
            onClick={() => setNotification(null)}
            className="text-zinc-400 hover:text-white font-bold px-2 py-0.5 rounded transition-colors cursor-pointer"
          >
            ✕
          </button>
        </div>
      )}

      {/* Tab 1: Live Staging Buffer View */}
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
            onDiscardSelected={handleDiscardSelected}
            isDiscarding={isDiscarding}
            stagingSelectedCount={stagingSelectedIds.length}
            totalCount={stagingPayloads.length}
            stagingPayloads={stagingPayloads}
            hideDuplicates={hideDuplicates}
            onToggleHideDuplicates={() => setHideDuplicates((prev) => !prev)}
          />

          <PayloadTable
            payloads={displayedStagingPayloads}
            selectedIds={stagingSelectedIds}
            taxonomyTree={taxonomyTree}
            hideTaxonomy={true}
            onSelectPayload={(item) => setSelectedPayload(item)}
            onToggleSelectAll={handleToggleSelectAll}
            onToggleSelectOne={handleToggleSelectOne}
            onBatchSaveTaxonomy={handleBatchSaveTaxonomy}
          />
        </div>
      )}

      {/* Tab 2: Persistent Database Vault View */}
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
            onStageSelected={handleStageForMatching}
            stagingForMatching={stagingForMatching}
            onUnstageSelected={handleUnstageSelected}
            unstagingForMatching={unstagingForMatching}
            dbSelectedCount={dbSelectedIds.length}
            totalCount={dbPayloads.length}
            showStagedOnly={showStagedOnly}
            onToggleStagedOnly={setShowStagedOnly}
          />

          {loadingDb ? (
            <div className="py-20 text-center font-mono text-xs text-zinc-400 bg-zinc-900/40 rounded-xl border border-zinc-800/60 flex flex-col items-center justify-center gap-3">
              <span className="h-5 w-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              <span>Querying committed bank alerts from database...</span>
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

      {/* Record Inspector Drawer Modal */}
      <PayloadInspectorModal payload={selectedPayload} onClose={() => setSelectedPayload(null)} />
    </div>
  );
};