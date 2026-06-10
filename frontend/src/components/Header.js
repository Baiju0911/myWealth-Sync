import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

export default function Header() {
  return (
    <View style={styles.header}>
      <Text style={styles.headerTitle}>myWealth Sync</Text>
      <Text style={styles.headerSubtitle}>Offline Ledger Gateway v2</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    paddingTop: 60,
    paddingBottom: 16,
    paddingHorizontal: 20,
    backgroundColor: '#1A1A1E',
  },
  headerTitle: { color: '#FFFFFF', fontSize: 22, fontWeight: 'bold' },
  headerSubtitle: { color: '#8E8E93', fontSize: 13, marginTop: 2 },
});
