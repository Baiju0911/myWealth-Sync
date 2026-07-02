// src/api.ts
import api from './api/client'; // 🔌 Point directly to your pre-configured Axios instance

/* ==========================================================================
   Existing Interfaces
   ========================================================================== */
export interface BankPayload {
  code: string;
  display_name: string;
}

export interface CredentialPayload {
  account_id: string;
  statement_password: string;
}

export interface AccountPayload {
  name: string;
  account_type: string;
  account_number: string;
  ifsc_code: string;
  branch_name: string;
  address: string;
  bank_id: string;
}

/* ==========================================================================
   New Accounting Interfaces
   ========================================================================== */
export interface AccountingHeaderPayload {
  id?: string | number;
  account_name: string;
  account_code: string; // e.g., "1010", "2100"
  type: 'Asset' | 'Liability' | 'Equity' | 'Revenue' | 'Expense';
  balance?: number;
}

export interface SelfTransferPayload {
  id?: string | number;
  source_account_id: string | number;
  destination_account_id: string | number;
  transfer_type: string;
  is_active: boolean;
}

export interface RuleConstraintPayload {
  id?: string | number;
  rule_name: string;
  is_enabled: boolean;
  strict_mode: boolean;
}

/* ==========================================================================
   Existing Core APIs
   ========================================================================== */
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
  getBanks: async () => {
    const response = await api.get('/banks/');
    return response.data;
  },
  createBank: async (payload: BankPayload) => {
    const response = await api.post('/banks/', payload);
    return response.data;
  },
  updateBank: async (id: string | number, payload: BankPayload) => {
    const res = await api.put(`/banks/${id}/`, payload);
    return res.data;
  },
  deleteBank: async (id: string | number) => {
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
  updateAccount: async (
    id: string | number,
    payload: Partial<AccountPayload>
  ) => {
    const res = await api.put(`/accounts/${id}/`, payload);
    return res.data;
  },
  deleteAccount: async (id: string | number) => {
    await api.delete(`/accounts/${id}/`);
    return true;
  },
};

/* ==========================================================================
   New Accounting System APIs
   ========================================================================== */

// 1️⃣ TAB 1: KNOWN HEADERS CRUD
export const accountingHeaderApi = {
  getHeaders: async () => {
    const res = await api.get('/accounting/headers/');
    return res.data;
  },
  createHeader: async (payload: AccountingHeaderPayload) => {
    const res = await api.post('/accounting/headers/', payload);
    return res.data;
  },
  updateHeader: async (
    id: string | number,
    payload: Partial<AccountingHeaderPayload>
  ) => {
    const res = await api.put(`/accounting/headers/${id}/`, payload);
    return res.data;
  },
  deleteHeader: async (id: string | number) => {
    await api.delete(`/accounting/headers/${id}/`);
    return true;
  },
};

// 2️⃣ TAB 2: SELF TRANSFERS CRUD
export const selfTransferApi = {
  getRoutes: async () => {
    const res = await api.get('/statements/self-transfers/');
    return res.data;
  },
  createRoute: async (payload: SelfTransferPayload) => {
    const res = await api.post('/statements/self-transfers/', payload);
    return res.data;
  },
  updateRoute: async (
    id: string | number,
    payload: Partial<SelfTransferPayload>
  ) => {
    const res = await api.put(`/statements/self-transfers/${id}/`, payload);
    return res.data;
  },
  deleteRoute: async (id: string | number) => {
    await api.delete(`/statements/self-transfers/${id}/`);
    return true;
  },
};

// 3️⃣ TAB 3: BALANCE SHEET MATRIX (Read-only Calculation View)
export const balanceSheetApi = {
  getMatrix: async () => {
    const res = await api.get('/accounting/balance-sheet/matrix/');
    return res.data;
  },
};

// 4️⃣ TAB 4: GOLDEN RULE ENGINE INTERCEPTORS CRUD
export const goldenRuleApi = {
  getRules: async () => {
    const res = await api.get('/accounting/rules/golden-engine/');
    return res.data;
  },
  updateRuleConstraint: async (
    id: string | number,
    payload: Partial<RuleConstraintPayload>
  ) => {
    const res = await api.put(
      `/accounting/rules/golden-engine/${id}/`,
      payload
    );
    return res.data;
  },
};

// src/api.ts

export interface AccountingHeaderPayload {
  id?: string | number;
  account_name: string;
  account_code: string; // e.g., "1010", "2100"
  type: 'Asset' | 'Liability' | 'Equity' | 'Revenue' | 'Expense';
  balance?: number;
}

export interface SelfTransferPayload {
  id?: string | number;
  source_account_id: string | number;
  destination_account_id: string | number;
  transfer_type: string;
  is_active: boolean;
}
