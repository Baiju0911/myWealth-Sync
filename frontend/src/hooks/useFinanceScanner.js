import { useState, useEffect } from 'react';
import { Alert, Platform } from 'react-native';
import { useCameraPermissions } from 'expo-camera';
import { getDatabaseConnection } from '../config/db';
import { UPIParserService } from '../services/financeService';

let localScanLock = false;

export function useFinanceScanner(availableAccounts, refreshCallback) {
  const [permission, requestPermission] = useCameraPermissions();
  const [isCameraActive, setIsCameraActive] = useState(false);
  const [isCameraReady, setIsCameraReady] = useState(false);
  const [scanned, setScanned] = useState(false);
  const [statusText, setStatusText] = useState('System Operational.');

  const [isModalVisible, setIsModalVisible] = useState(false);
  const [isGatewayModalVisible, setIsGatewayModalVisible] = useState(false);
  const [pendingQRData, setPendingQRData] = useState('');
  const [merchantName, setMerchantName] = useState('');
  const [paymentAmount, setPaymentAmount] = useState('50.00');

  const handleOpenScanner = async () => {
    if (!permission || !permission.granted) {
      const updatedPermission = await requestPermission();
      if (!updatedPermission.granted) {
        Alert.alert(
          'Permission Required',
          'Please allow camera access to scan QR codes.'
        );
        return;
      }
    }
    setScanned(false);
    setIsCameraReady(false);
    setIsCameraActive(true);
  };

  const handleBarCodeScanned = ({ data }) => {
    if (!isCameraReady || scanned || localScanLock) return;

    if (data && data.startsWith('upi://pay')) {
      localScanLock = true;
      setScanned(true);
      const nameMatch = data.match(/[?&]pn=([^&]*)/);
      const payeeName = nameMatch
        ? decodeURIComponent(nameMatch[1])
        : 'Unknown Merchant';

      setPaymentAmount('0.00');
      setPendingQRData(data);
      setMerchantName(payeeName);
      setIsCameraActive(false);
      setIsModalVisible(true);

      setTimeout(() => {
        localScanLock = false;
      }, 1000);
    } else {
      setStatusText('Invalid UPI payload format.');
    }
  };

  const commitToLocalCache = () => {
    if (!paymentAmount || parseFloat(paymentAmount) <= 0) {
      Alert.alert(
        'Invalid Amount',
        'Please enter a transaction value greater than zero.'
      );
      return;
    }
    setIsModalVisible(false);
    setIsGatewayModalVisible(true);
  };

  const saveOfflineTransaction = (packet) => {
    const localDb = getDatabaseConnection();
    const uniqueUUID = `${Platform.OS}-${Date.now()}-${Math.floor(Math.random() * 1000)}`;

    localDb.runSync(
      `INSERT INTO offline_transactions (id, description, merchant_vpa, upi_rrn, amount, timestamp, scanned_by) 
       VALUES (?, ?, ?, ?, ?, ?, ?);`,
      [
        uniqueUUID,
        packet.description,
        packet.merchant_vpa,
        packet.upi_rrn,
        parseFloat(paymentAmount),
        packet.timestamp,
        packet.scanned_by,
      ]
    );
  };

  return {
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
  };
}
