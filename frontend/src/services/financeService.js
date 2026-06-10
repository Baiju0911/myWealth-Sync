// frontend/src/services/financeService.js
import { Platform } from 'react-native';
import * as Device from 'expo-device';

import { apiClient, setAuthToken } from './api';
export const AuthService = {
  /**
   * Submits user credentials to obtain a secure backend authorization token.
   */
  login: async (username, password) => {
    const response = await apiClient.post('login/', { username, password });
    const { token } = response.data;

    // Lock the token straight into our central Axios interceptor engine context
    setAuthToken(token);
    return response.data;
  },

  /**
   * Logs out the user safely by wiping the cached network headers.
   */
  logout: () => {
    setAuthToken(null);
  },
};

export const ConfigService = {
  /**
   * Fetches the dynamic configuration constants directly from Django's single source of truth.
   */
  getSystemConfig: async () => {
    const response = await apiClient.get('config/');
    return response.data;
  },
};

export const LedgerService = {
  /**
   * Fetches the user's isolated account listings.
   */
  getAccounts: async () => {
    const response = await apiClient.get('accounts/');
    return response.data;
  },

  /**
   * Submits a multi-legged compound ledger transaction payload securely.
   */
  createTransaction: async (transactionPayload) => {
    const response = await apiClient.post('transactions/', transactionPayload);
    return response.data;
  },
};

export const UPIParserService = {
  /**
   * Extracts parameters safely from a raw UPI deep-link string without relying on URLSearchParams.
   * Guaranteed safe for both iOS JavaScriptCore and Android V8 engines with explicit ledger assignment scopes.
   */
  parseUPILink: (rawUrl, dbAccounts, finalAmount) => {
    try {
      if (!rawUrl || !rawUrl.includes('?')) return null;

      // 🎯 SAFE REGEX PARSER: Extracts query keys regardless of platform OS environment
      const getParam = (key) => {
        const match = rawUrl.match(new RegExp(`[?&]${key}=([^&]*)`));
        return match ? decodeURIComponent(match[1]) : '';
      };

      const payeeName = getParam('pn') || 'Unknown Merchant';
      const merchantVpa = getParam('pa') || '';
      const txRef = getParam('tr') || '';
      const validatedAmount = parseFloat(finalAmount);

      // 🗂️ FIX: Explicitly extract and declare the database account keys from dbAccounts argument
      const debitAccountID = dbAccounts[0]?.id;
      const creditAccountID = dbAccounts[1]?.id;

      // 📱 CAPTURE DEVICE FINGERPRINT METRICS:
      const deviceName = Device.modelName || 'Unknown Hardware';
      const osLabel = Platform.OS === 'ios' ? 'iOS' : 'Android';
      const deviceFingerprint = `${osLabel} (${deviceName})`;

      return {
        description: `Scan Intent: ${payeeName} (${txRef})`,
        status: 'INTENT',
        upi_rrn: txRef,
        merchant_vpa: merchantVpa,
        timestamp: new Date().toISOString(),

        // Tracks the physical hardware device source structure
        scanned_by: deviceFingerprint,

        lines: [
          {
            account: debitAccountID,
            account_id: debitAccountID,
            debit_amount: validatedAmount,
            credit_amount: 0.0,
          },
          {
            account: creditAccountID,
            account_id: creditAccountID,
            debit_amount: 0.0,
            credit_amount: validatedAmount,
          },
        ],
      };
    } catch (error) {
      console.error('❌ Failed to parse UPI payload structure:', error);
      return null;
    }
  },
};
