import React from 'react';
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';

export default function SyncConsole({ queueCount, isSyncing, onSync }) {
  return (
    <View style={styles.syncConsoleCard}>
      <View style={styles.syncMetaInfo}>
        <Text style={styles.syncTitle}>Local Ledger Cache</Text>
        <Text style={styles.syncCounter}>
          {queueCount === 0
            ? '✨ Queue Clear'
            : `📦 ${queueCount} Scan(s) Pending`}
        </Text>
      </View>
      <TouchableOpacity
        style={[
          styles.syncButton,
          queueCount === 0 && styles.disabledSyncButton,
        ]}
        onPress={onSync}
        disabled={queueCount === 0 || isSyncing}
      >
        {isSyncing ? (
          <ActivityIndicator color="#FFFFFF" size="small" />
        ) : (
          <Text style={styles.syncButtonText}>🔄 Sync Now</Text>
        )}
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  syncConsoleCard: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#1C1C24',
    margin: 16,
    padding: 16,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#2C2C35',
  },
  syncMetaInfo: { flex: 1 },
  syncTitle: { color: '#AEAEB2', fontSize: 12, fontWeight: '600' },
  syncCounter: {
    color: '#30D158',
    fontSize: 16,
    fontWeight: 'bold',
    marginTop: 4,
  },
  syncButton: {
    backgroundColor: '#0A84FF',
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 10,
  },
  disabledSyncButton: { backgroundColor: '#2C2C35', opacity: 0.5 },
  syncButtonText: { color: '#FFFFFF', fontWeight: 'bold', fontSize: 14 },
});
