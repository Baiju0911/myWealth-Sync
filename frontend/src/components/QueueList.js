import React from 'react';
import { StyleSheet, Text, View, ScrollView } from 'react-native';

export default function QueueList({ queueItems }) {
  return (
    <View style={styles.queueContainer}>
      <Text style={styles.queueSectionHeader}>📋 Items Currently in Queue</Text>
      {queueItems.length === 0 ? (
        <View style={styles.emptyQueueBox}>
          <Text style={styles.emptyQueueText}>
            No transactions waiting in storage memory.
          </Text>
        </View>
      ) : (
        <ScrollView
          style={styles.queueScrollContainer}
          showsVerticalScrollIndicator={false}
        >
          {queueItems.map((item) => (
            <View key={item.id} style={styles.queueItemCard}>
              <View style={styles.queueCardLeft}>
                <Text style={styles.queueItemDescription} numberOfLines={1}>
                  {item.description.replace('Scan Intent: ', '')}
                </Text>
                <Text style={styles.queueItemMeta}>
                  {new Date(item.timestamp).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}{' '}
                  • {item.scanned_by}
                </Text>
              </View>
              <View style={styles.queueCardRight}>
                <Text style={styles.queueItemAmount}>
                  ₹{item.amount.toFixed(2)}
                </Text>
              </View>
            </View>
          ))}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  queueContainer: { flex: 1, paddingHorizontal: 16, marginBottom: 4 },
  queueSectionHeader: {
    color: '#AEAEB2',
    fontSize: 13,
    fontWeight: 'bold',
    marginBottom: 10,
  },
  queueScrollContainer: { flex: 1 },
  emptyQueueBox: {
    backgroundColor: '#1C1C24',
    borderRadius: 12,
    padding: 32,
    alignItems: 'center',
    justifyContent: 'center',
    borderStyle: 'dashed',
    borderWidth: 1,
    borderColor: '#3A3A44',
  },
  emptyQueueText: { color: '#636366', fontSize: 13 },
  queueItemCard: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#1C1C24',
    padding: 14,
    borderRadius: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#2C2C32',
  },
  queueCardLeft: { flex: 1, paddingRight: 12 },
  queueCardRight: { justifyContent: 'center' },
  queueItemDescription: { color: '#FFFFFF', fontSize: 14, fontWeight: '600' },
  queueItemMeta: { color: '#636366', fontSize: 11, marginTop: 4 },
  queueItemAmount: { color: '#30D158', fontSize: 15, fontWeight: 'bold' },
});
