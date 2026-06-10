import React from 'react';
import {
  StyleSheet,
  View,
  TouchableOpacity,
  Text,
  StatusBar,
  ActivityIndicator,
  Platform,
} from 'react-native';

// 🎯 INTERNAL DECOUPLED IMPORTS
import Header from './src/components/Header';
import SyncConsole from './src/components/SyncConsole';
import QueueList from './src/components/QueueList';
import ScannerOverlay from './src/components/ScannerOverlay';
import TransactionModal from './src/components/TransactionModal';
import PaymentGatewayModal from './src/components/PaymentGatewayModal';

// 🎯 CUSTOM SEPARATED HOOKS & UTILITIES LAYER
import { useBackendSync } from './src/hooks/useBackendSync';
import { useFinanceScanner } from './src/hooks/useFinanceScanner';
import { PaymentRouterService } from './src/services/paymentRouter'; // 🎯 NEW IMPORT

export default function App() {
  // 1. Initialize Sync Core Engine
  const syncEngine = useBackendSync((txt) => setStatusText(txt));
  const {
    availableAccounts,
    queueCount,
    queueItems,
    isSyncing,
    refreshQueueData,
    synchronizeQueueWithBackend,
  } = syncEngine;

  // 2. Initialize Scanner Component Engine
  const scannerEngine = useFinanceScanner(availableAccounts, refreshQueueData);
  const {
    permission,
    isCameraActive,
    setIsCameraActive,
    isCameraReady,
    setIsCameraReady,
    scanned,
    setScanned,
    statusText,
    setStatusText,
    isModalVisible,
    setIsModalVisible,
    isGatewayModalVisible,
    setIsGatewayModalVisible,
    pendingQRData,
    merchantName,
    paymentAmount,
    setPaymentAmount,
    handleOpenScanner,
    handleBarCodeScanned,
    commitToLocalCache,
    saveOfflineTransaction,
  } = scannerEngine;

  // 3. 🎯 CLEAN REFLECTION PIPELINE: Direct pass through mapping straight to decoupled service wrapper
  const executeNativePaymentHandoff = (chosenScheme) => {
    PaymentRouterService.executeHandoff({
      chosenScheme,
      pendingQRData,
      paymentAmount,
      availableAccounts,
      setIsGatewayModalVisible,
      setScanned,
      setStatusText,
      saveOfflineTransaction,
      refreshQueueData,
    });
  };

  if (!permission) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#0A84FF" />
        <Text style={styles.loaderMessage}>Waking platform modules...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" />

      <View style={styles.contentFlex}>
        <Header />
        <SyncConsole
          queueCount={queueCount}
          isSyncing={isSyncing}
          onSync={synchronizeQueueWithBackend}
        />
        <QueueList queueItems={queueItems} />

        <View style={styles.actionButtonContainer}>
          <TouchableOpacity
            style={styles.floatingScanButton}
            onPress={handleOpenScanner}
          >
            <Text style={styles.floatingScanButtonIcon}>📷</Text>
            <Text style={styles.floatingScanButtonText}>Scan Any QR</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.footer}>
          <Text style={styles.statusDisplay}>System Status: {statusText}</Text>
        </View>
      </View>

      {isCameraActive && (
        <ScannerOverlay
          isCameraReady={isCameraReady}
          onCameraReady={() => setIsCameraReady(true)}
          scanned={scanned}
          onScan={handleBarCodeScanned}
          onClose={() => setIsCameraActive(false)}
        />
      )}

      <TransactionModal
        visible={isModalVisible}
        merchantName={merchantName}
        value={paymentAmount}
        onChangeValue={setPaymentAmount}
        onDrop={() => {
          setIsModalVisible(false);
          setScanned(false);
        }}
        onConfirm={commitToLocalCache}
      />

      <PaymentGatewayModal
        visible={isGatewayModalVisible}
        merchantName={merchantName}
        amount={paymentAmount}
        onSelect={executeNativePaymentHandoff}
        onClose={() => {
          setIsGatewayModalVisible(false);
          setScanned(false);
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#121214' },
  contentFlex: { flex: 1 },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#121214',
  },
  loaderMessage: { color: '#AEAEB2', marginTop: 12 },
  actionButtonContainer: {
    alignItems: 'center',
    paddingVertical: 12,
    backgroundColor: '#121214',
  },
  floatingScanButton: {
    backgroundColor: '#30D158',
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 14,
    paddingHorizontal: 32,
    borderRadius: 30,
    elevation: 6,
  },
  floatingScanButtonIcon: { fontSize: 18, marginRight: 8 },
  floatingScanButtonText: {
    color: '#000000',
    fontWeight: 'bold',
    fontSize: 16,
  },
  footer: { padding: 12, backgroundColor: '#1A1A1E', alignItems: 'center' },
  statusDisplay: {
    color: '#8E8E93',
    fontSize: 11,
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
  },
});
