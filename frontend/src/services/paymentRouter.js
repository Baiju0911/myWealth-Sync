import { Linking, Alert, Platform } from 'react-native';
import { UPIParserService } from './financeService';

export const PaymentRouterService = {
  executeHandoff: async ({
    chosenScheme,
    pendingQRData,
    paymentAmount,
    availableAccounts,
    setIsGatewayModalVisible,
    setScanned,
    setStatusText,
    saveOfflineTransaction,
    refreshQueueData,
  }) => {
    setIsGatewayModalVisible(false);

    try {
      let baseParameters = '';

      // 1. Sanitize string inputs into valid URL parameter layouts
      if (pendingQRData.includes('?')) {
        baseParameters = pendingQRData.substring(pendingQRData.indexOf('?'));
      } else {
        const safeVPA = encodeURIComponent(pendingQRData.trim());
        baseParameters = `?pa=${safeVPA}&pn=${encodeURIComponent('Manual Entry')}`;
      }

      // 2. Safely apply payment variable values
      if (baseParameters.includes('am=')) {
        baseParameters = baseParameters.replace(
          /am=[^&]*/,
          `am=${paymentAmount}`
        );
      } else {
        baseParameters = `${baseParameters}&am=${paymentAmount}`;
      }

      if (baseParameters.includes('&aid=')) {
        baseParameters = baseParameters.replace(/&aid=[^&]*/, '');
      }

      // 🔍 DETECT LINK ACCOUNT NATURE: P2P vs P2M Merchant
      const isMerchantLink = baseParameters.includes('mc=');
      let finalUpiUrl = '';

      if (!isMerchantLink) {
        // 🎯 THE UNIVERSAL COMPATIBILITY OVERRIDE FOR P2P LINKS
        // If there is no merchant code, we bypass private schemes (bhim://, tez://) entirely.
        // Firing upi:// opens the global platform tray, enabling clean personal transfers without security blocks.
        console.log(
          '💸 Personal P2P Link Detected. Leveraging global upi:// scheme to bypass app-specific security limits.'
        );
        finalUpiUrl = `upi://pay${baseParameters}`;
      } else {
        // 🏪 MERCHANT LINKS LOGIC: Safe to use explicit targeted pathways
        if (chosenScheme === 'bhim') {
          let isBhimInstalled = false;
          try {
            isBhimInstalled = await Linking.canOpenURL('bhim://');
          } catch (e) {
            console.log('Cannot verify BHIM scheme via core link register.');
          }

          if (isBhimInstalled) {
            console.log(
              '🎯 Verified Merchant + BHIM found. Routing to direct app pipeline.'
            );
            finalUpiUrl = `bhim://pay${baseParameters}`;
          } else {
            if (Platform.OS === 'ios') {
              finalUpiUrl = `tez://upi/pay${baseParameters}`;
            } else {
              finalUpiUrl = `upi://pay${baseParameters}`;
            }
          }
        } else {
          // Direct explicit targeting for Google Pay (tez://) or PhonePe (phonepe://)
          finalUpiUrl = `${chosenScheme}://upi/pay${baseParameters}`;
        }
      }

      console.log(
        `📡 Payment Router Firing Safe Intent Target: ${finalUpiUrl}`
      );

      // 🎯 PLATFORM INTENT EXECUTION LAYER
      if (Platform.OS === 'ios') {
        try {
          console.log(
            '🚀 Executing direct iOS URL handoff flight to bypass Expo Go white-list constraints...'
          );
          await Linking.openURL(finalUpiUrl);
        } catch (err) {
          console.log(
            'Direct handoff failed, dropping back to prompt panel alternative.'
          );
          Alert.alert(
            'Launch Error',
            'Could not redirect straight to your chosen app. Please verify it is installed.'
          );
          setScanned(false);
          return;
        }
      } else {
        // Standard Android runtime execution
        let canOpen = false;
        try {
          canOpen = await Linking.canOpenURL(finalUpiUrl);
        } catch (e) {
          canOpen = false;
        }

        if (canOpen) {
          await Linking.openURL(finalUpiUrl);
        } else {
          await Linking.openURL(`upi://pay${baseParameters}`);
        }
      }

      // 📝 PARSE AND RETAIN LOCAL LEDGER DATA IN SQLITE
      const packet = UPIParserService.parseUPILink(
        pendingQRData.includes('?')
          ? pendingQRData
          : `upi://pay${baseParameters}`,
        availableAccounts,
        paymentAmount
      );
      if (!packet) throw new Error('Parser specification mapping fault');

      saveOfflineTransaction(packet);

      setScanned(false);
      setStatusText('Intent launched successfully.');
      refreshQueueData();
    } catch (err) {
      console.error('Payment Deep Link Router Failure:', err);
      Alert.alert(
        'Handoff Fault',
        'Could not establish connection parameters.'
      );
    }
  },
};
