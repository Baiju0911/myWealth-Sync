// webapp/src/hooks/useMultiYearSync.ts
import { useState, useRef, useEffect, useCallback } from 'react';
import { emailIngestApi, type DatePresetType } from '../api/emailIngestApi';

const SYNC_SESSION_KEY = 'mywealth_active_sync_session';

export function useMultiYearSync(
  selectedAccount: string,
  datePreset: DatePresetType,
  startDate: string,
  endDate: string,
  onSyncCycleComplete: () => Promise<void>,
  onNotification: (notif: {
    type: 'success' | 'error' | 'info';
    message: string;
  }) => void
) {
  const [syncing, setSyncing] = useState(false);
  const [progress, setProgress] = useState({
    activeYear: null as number | null,
    totalYears: 0,
    completedYears: 0,
    itemsDiscovered: 0,
    elapsedSeconds: 0,
  });

  const isSyncingRef = useRef(false);
  const timerRef = useRef<number | null>(null);
  const hasMountedRef = useRef(false);

  const startTimer = () => {
    timerRef.current = window.setInterval(() => {
      setProgress((prev) => ({
        ...prev,
        elapsedSeconds: prev.elapsedSeconds + 1,
      }));
    }, 1000);
  };

  const stopTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    setProgress((prev) => ({ ...prev, activeYear: null }));
    isSyncingRef.current = false;
    setSyncing(false);
  };

  const runMultiYearSync = useCallback(
    async (fromYear: number, startYear: number, account: string) => {
      if (isSyncingRef.current) return;
      isSyncingRef.current = true;
      setSyncing(true);

      const totalYears = fromYear - startYear + 1;
      setProgress({
        activeYear: fromYear,
        totalYears,
        completedYears: 0,
        itemsDiscovered: 0,
        elapsedSeconds: 0,
      });
      startTimer();

      try {
        for (let year = fromYear; year >= startYear; year--) {
          setProgress((prev) => ({ ...prev, activeYear: year }));
          localStorage.setItem(
            SYNC_SESSION_KEY,
            JSON.stringify({
              currentYear: year,
              startYear,
              selectedAccount: account,
              status: 'IN_PROGRESS',
              timestamp: Date.now(),
            })
          );

          const res = await emailIngestApi.triggerSync({
            date_preset: 'CUSTOM',
            start_date: `${year}-01-01`,
            end_date: `${year}-12-31`,
            account,
          });
          const added = res?.total_fetched || res?.count || 0;
          setProgress((prev) => ({
            ...prev,
            completedYears: prev.completedYears + 1,
            itemsDiscovered: prev.itemsDiscovered + added,
          }));
          await onSyncCycleComplete();
        }

        localStorage.removeItem(SYNC_SESSION_KEY);
        onNotification({
          type: 'success',
          message: 'Completed full multi-year sync! All alerts buffered.',
        });
      } catch (err) {
        console.error('Multi-year sync error:', err);
        onNotification({
          type: 'error',
          message: 'Sync interrupted. Review console output.',
        });
      } finally {
        stopTimer();
      }
    },
    [onSyncCycleComplete, onNotification]
  );

  const triggerSync = async () => {
    if (isSyncingRef.current) return;

    if (datePreset === 'ALL' || (datePreset as string) === 'ALL_TIME') {
      await runMultiYearSync(new Date().getFullYear(), 2020, selectedAccount);
    } else {
      isSyncingRef.current = true;
      setSyncing(true);
      try {
        const res = await emailIngestApi.triggerSync({
          date_preset: datePreset,
          start_date: startDate,
          end_date: endDate,
          account: selectedAccount,
        });
        onNotification({
          type: 'success',
          message: `Buffered ${res?.total_fetched || 0} transactions.`,
        });
        await onSyncCycleComplete();
      } catch (err) {
        onNotification({ type: 'error', message: 'Sync failed.' });
      } finally {
        setSyncing(false);
        isSyncingRef.current = false;
      }
    }
  };

  // Restore session
  useEffect(() => {
    if (hasMountedRef.current) return;
    hasMountedRef.current = true;
    try {
      const raw = localStorage.getItem(SYNC_SESSION_KEY);
      const session = raw ? JSON.parse(raw) : null;
      if (session && session.status === 'IN_PROGRESS') {
        runMultiYearSync(
          session.currentYear,
          session.startYear,
          session.selectedAccount
        );
      }
    } catch {
      localStorage.removeItem(SYNC_SESSION_KEY);
    }
  }, [runMultiYearSync]);

  return { syncing, syncProgress: progress, triggerSync };
}
