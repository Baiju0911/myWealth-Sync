import * as SQLite from 'expo-sqlite';
import { Platform } from 'react-native';

let globalDbInstance = null;

export const getDatabaseConnection = () => {
  if (globalDbInstance) return globalDbInstance;

  console.log(
    '⏳ Instantly mounting SQLite via Synchronous Thread Connection...'
  );
  const instance = SQLite.openDatabaseSync('mywealth_sync.db');

  instance.execSync(`
    CREATE TABLE IF NOT EXISTS offline_transactions (
      id TEXT PRIMARY KEY NOT NULL,
      description TEXT NOT NULL,
      merchant_vpa TEXT,
      upi_rrn TEXT,
      amount REAL NOT NULL,
      timestamp TEXT NOT NULL,
      scanned_by TEXT NOT NULL
    );
  `);

  globalDbInstance = instance;
  return instance;
};
