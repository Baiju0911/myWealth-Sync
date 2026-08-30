import { useState, useEffect, useCallback, useRef } from 'react';
import { emailIngestApi, type EmailPayload } from '../api/emailIngestApi';

interface TunnelInfo {
  status: 'ONLINE' | 'OFFLINE';
  tunnel_url: string | null;
  ingest_endpoint: string | null;
  protocol: string | null;
  edge_location: string | null;
}

export const useLiveIngestStream = (
  activeTab: string,
  isLivePollingEnabled: boolean,
  syncing: boolean,
  committing: boolean
) => {
  const [tunnel, setTunnel] = useState<TunnelInfo>({
    status: 'OFFLINE',
    tunnel_url: null,
    ingest_endpoint: null,
    protocol: null,
    edge_location: null,
  });

  const [stagingPayloads, setStagingPayloads] = useState<EmailPayload[]>([]);
  const [isLiveFetching, setIsLiveFetching] = useState<boolean>(false);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const isSyncingRef = useRef<boolean>(false);

  const updateLastSyncedTimestamp = () => {
    setLastSyncedAt(
      new Date().toLocaleTimeString('en-IN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    );
  };

  const fetchTunnelStatus = useCallback(async () => {
    try {
      const data = await emailIngestApi.getTunnelStatus();
      setTunnel(data);
    } catch (err) {
      setTunnel((prev) => ({ ...prev, status: 'OFFLINE' }));
    }
  }, []);

  const fetchLiveStagingStream = useCallback(async () => {
    if (isSyncingRef.current || syncing || committing) return;

    setIsLiveFetching(true);
    try {
      const res = await emailIngestApi.getPendingStagingPayloads();
      if (
        res?.previews &&
        Array.isArray(res.previews) &&
        res.previews.length > 0
      ) {
        const liveItems: EmailPayload[] = res.previews.map(
          (item: any, index: number) => {
            const parsed = item.parsed_transaction || {};
            const raw = item.raw_payload || {};
            const headers = raw.headers_json || {};
            const summary = headers.parsed_summary || {};
            const isDup = parsed.is_duplicate || item.is_duplicate;

            const uniqueId =
              item.payload_hash ||
              parsed.txn_fingerprint ||
              `live-${raw.email_date || Date.now()}-${index}`;

            return {
              id: uniqueId,
              source: raw.source || 'IOS_SMS',
              bank_name:
                parsed.bank_name || summary.bank || 'SOUTH INDIAN BANK',
              account_last4: parsed.account_last4 || summary.account || null,
              merchant:
                parsed.merchant && parsed.merchant !== 'UNKNOWN VENDOR'
                  ? parsed.merchant
                  : raw.subject || 'UPI Transfer',
              amount: parsed.amount ? parseFloat(parsed.amount) : null,
              balance: parsed.balance || summary.balance || null,
              upi_ref: parsed.upi_ref || summary.upi_ref || null,
              txn_type: parsed.txn_type || 'DEBIT',
              status: isDup
                ? 'DUPLICATE'
                : parsed.is_parsed
                  ? 'PARSED'
                  : 'UNPARSED',
              subject: raw.subject || raw.decrypted_body || 'Incoming SMS',
              email_from: raw.email_from || raw.sender || 'UNKNOWN_SENDER',
              email_date: raw.email_date || new Date().toISOString(),
              created_at: raw.email_date || new Date().toISOString(),
              body: raw.decrypted_body || raw.body,
              raw_item: item,
            } as any;
          }
        );

        setStagingPayloads(liveItems);
      } else {
        setStagingPayloads([]);
      }
      updateLastSyncedTimestamp();
    } catch (err) {
      console.error('Staging stream polling error:', err);
    } finally {
      setIsLiveFetching(false);
    }
  }, [syncing, committing]);

  useEffect(() => {
    if (activeTab === 'INGEST' && isLivePollingEnabled) {
      fetchTunnelStatus();
      fetchLiveStagingStream();

      const tunnelInterval = setInterval(fetchTunnelStatus, 10000);
      const streamInterval = setInterval(fetchLiveStagingStream, 5000);

      return () => {
        clearInterval(tunnelInterval);
        clearInterval(streamInterval);
      };
    }
  }, [
    activeTab,
    isLivePollingEnabled,
    fetchTunnelStatus,
    fetchLiveStagingStream,
  ]);

  return {
    tunnel,
    stagingPayloads,
    setStagingPayloads,
    isLiveFetching,
    lastSyncedAt,
    updateLastSyncedTimestamp,
    isSyncingRef,
  };
};
