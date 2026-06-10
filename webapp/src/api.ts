// src/api.ts
import api from './api/client'; // 🔌 Point directly to your pre-configured Axios instance

export interface BankPayload {
  code: string;
  display_name: string;
}

// 🎯 FIXED: Reoriented the vault payload directly around the Account mapping key
export interface CredentialPayload {
  account_id: string;
  statement_password: string;
}

export interface AccountPayload {
  name: string;
  account_type: string;

  // 🎯 THE FIX: Add the 4-digit token field directly to your known payload signature
  account_number: string;

  ifsc_code: string;
  branch_name: string;
  address: string;
  bank_id: string;
}

export const credentialApi = {
  getCredentials: async () => {
    const res = await api.get('/bank-credentials/');
    return res.data;
  },
  createCredential: async (payload: CredentialPayload) => {
    const res = await api.post('/bank-credentials/', payload);
    return res.data;
  },
  updateCredential: async (id: string, payload: Partial<CredentialPayload>) => {
    // Note: If credentials still use UUIDs, this string replace is perfect!
    const cleanId = id.replace(/-/g, '');
    const res = await api.put(`/bank-credentials/${cleanId}/`, payload);
    return res.data;
  },
  deleteCredential: async (id: string) => {
    const cleanId = id.replace(/-/g, '');
    await api.delete(`/bank-credentials/${cleanId}/`);
    return true;
  },
};

export const bankApi = {
  /**
   * 📥 GET: Pull down all master bank entries from MySQL via Axios
   */
  getBanks: async () => {
    const response = await api.get('/banks/');
    return response.data;
  },

  /**
   * 🚀 POST: Commit a new master institution node to the database
   */
  createBank: async (payload: BankPayload) => {
    const response = await api.post('/banks/', payload);
    return response.data;
  },

  /**
   * ✏️ PUT: Modify an existing institutional registry entry
   */
  updateBank: async (id: string, payload: BankPayload) => {
    // 🎯 FIX: Int primary key pass-through (removed regex string methods)
    const res = await api.put(`/banks/${id}/`, payload);
    return res.data;
  },
  deleteBank: async (id: string) => {
    // 🎯 FIX: Int primary key pass-through (removed regex string methods)
    await api.delete(`/banks/${id}/`);
    return true;
  },
};

export const accountApi = {
  getAccounts: async () => {
    const res = await api.get('/accounts/');
    return res.data;
  },
  createAccount: async (payload: AccountPayload) => {
    const res = await api.post('/accounts/', payload);
    return res.data;
  },
  updateAccount: async (id: string, payload: Partial<AccountPayload>) => {
    // 🎯 FIX: Target route pass-through matching standard integer ID routing
    const res = await api.put(`/accounts/${id}/`, payload);
    return res.data;
  },
  deleteAccount: async (id: string) => {
    // 🎯 FIX: Target route pass-through matching standard integer ID routing
    await api.delete(`/accounts/${id}/`);
    return true;
  },
};
