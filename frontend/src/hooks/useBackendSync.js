import { useState, useEffect } from 'react';
import { Alert, Platform } from 'react-native';
import axios from 'axios';
import { getDatabaseConnection } from '../config/db';

const API_BASE_URL = 'http://192.168.31.114:8000/api';

export function useBackendSync(setStatusText) {
  const [availableAccounts, setAvailableAccounts] = useState([]);
  const [queueCount, setQueueCount] = useState(0);
  const [queueItems, setQueueItems] = useState([]);
  const [isSyncing, setIsSyncing] = useState(false);

  const refreshQueueData = () => {
    try {
      const localDb = getDatabaseConnection();
      const allRows = localDb.getAllSync(
        'SELECT COUNT(*) as total FROM offline_transactions;'
      );
      const items = localDb.getAllSync(
        'SELECT * FROM offline_transactions ORDER BY timestamp DESC;'
      );
      setQueueCount(allRows[0]?.total || 0);
      setQueueItems(items || []);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    refreshQueueData();
    (async () => {
      try {
        const res = await axios.get(`${API_BASE_URL}/accounts/`, {
          timeout: 1000,
        });
        setAvailableAccounts(res.data);
      } catch (err) {
        setAvailableAccounts([
          { id: 1, name: 'Default Cash' },
          { id: 2, name: 'Default Expense' },
        ]);
      }
    })();
  }, []);

  const synchronizeQueueWithBackend = async () => {
    if (queueCount === 0 || isSyncing) return;
    setIsSyncing(true);
    setStatusText('Syncing batch logs to Django...');

    try {
      const localDb = getDatabaseConnection();
      const cachedRecords = localDb.getAllSync(
        'SELECT * FROM offline_transactions;'
      );

      const bulkPayloadArray = cachedRecords.map((row) => ({
        description: row.description,
        merchant_vpa: row.merchant_vpa,
        upi_rrn: row.upi_rrn,
        timestamp: row.timestamp,
        scanned_by: row.scanned_by,
        status: 'INTENT',
        lines: [
          {
            account_id: availableAccounts[0]?.id || 1,
            debit_amount: row.amount,
            credit_amount: 0.0,
          },
          {
            account_id: availableAccounts[1]?.id || 2,
            debit_amount: 0.0,
            credit_amount: row.amount,
          },
        ],
      }));

      await axios.post(`${API_BASE_URL}/transactions/sync/`, bulkPayloadArray);
      localDb.runSync('DELETE FROM offline_transactions;');

      setStatusText('Sync sequence complete.');
      Alert.alert(
        'Sync Success',
        `Successfully uploaded ${cachedRecords.length} records!`
      );
      refreshQueueData();
    } catch (err) {
      setStatusText('Sync failed. Backend offline.');
      Alert.alert(
        'Sync Offline',
        "Transactions are safely preserved inside your phone's memory cache."
      );
    } finally {
      setIsSyncing(false);
    }
  };

  return {
    availableAccounts,
    queueCount,
    queueItems,
    isSyncing,
    refreshQueueData,
    synchronizeQueueWithBackend,
  };
}
