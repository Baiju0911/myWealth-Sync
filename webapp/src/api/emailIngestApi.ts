import api from './client';
import { accountApi, getTaxonomyTree, type TaxonomyOption } from './api';

export interface EmailPayload {
  id: string;
  source: string;
  bank_name?: string;
  account_last4?: string;
  merchant?: string;
  subject?: string;
  sender?: string;
  email_from: string;
  amount?: number | null;
  balance?: number | null;
  upi_ref?: string | null;
  txn_type?: 'DEBIT' | 'CREDIT';
  status:
    | 'PARSED'
    | 'DUPLICATE'
    | 'FAILED'
    | 'UNPARSED'
    | 'DECRYPTED'
    | 'COMPLETED'
    | 'STAGED'; // 👈 Added STAGED to union
  email_date?: string;
  created_at: string;
  body?: string;
  decrypted_body?: string;
  is_synthetic_gap?: boolean;
  is_staged_for_matching?: boolean; // 👈 Added staging flag
  staged_at?: string; // 👈 Added staging timestamp
  raw_item?: any;
  taxonomy_payload?: {
    account_match?: Record<string, any>;
    taxonomy?: {
      category_id?: string;
      category_name?: string;
      subcategory_id?: string;
      subcategory_name?: string;
    };
    normalized_txn?: Record<string, any>;
    audit_trail?: Record<string, any>;
  };
  is_completed?: boolean;
  completed_at?: string;
}

export type { TaxonomyOption };

export interface IngestStats {
  total: number;
  parsed: number;
  duplicate: number;
  failed: number;
}

export interface GetPayloadsParams {
  search?: string;
  status?: string;
  page?: number;
  date_preset?:
    | 'ALL'
    | 'THIS_WEEK'
    | 'THIS_MONTH'
    | 'LAST_MONTH'
    | 'LAST_6_MONTHS'
    | 'CUSTOM';
  start_date?: string;
  end_date?: string;
  account?: string;
  staged_only?: boolean;
}

const STAGING_URL = '/ingest/email/staging';
const VAULT_URL = '/ingest/email/payloads';
const TUNNEL_URL = '/ingest/email/tunnel';
const BALDISC_URL = '/ingest/email/balance-check';

export interface AccountOption {
  label: string;
  value: string; // Account last 4 digits
  id: string;
}

export const DEFAULT_ACCOUNT_OPTIONS: AccountOption[] = [
  { id: '3', label: 'SIB NRO-60 (A/c X0060)', value: '0060' },
];

export const formatAccountOptions = (rawAccounts: any[]): AccountOption[] => {
  if (!Array.isArray(rawAccounts)) return DEFAULT_ACCOUNT_OPTIONS;

  return rawAccounts
    .filter(
      (acc) =>
        acc.account_type !== 'SYSTEM_CORE' &&
        acc.account_number &&
        String(acc.account_number).trim() !== ''
    )
    .map((acc) => {
      const accNum = String(acc.account_number);
      const last4 = accNum.length > 4 ? accNum.slice(-4) : accNum;

      return {
        id: String(acc.id),
        label: `${acc.name} (A/c X${last4})`,
        value: last4,
      };
    });
};

export const fetchAccountOptions = async (): Promise<AccountOption[]> => {
  try {
    const rawData = await accountApi.getAccounts();
    const rawAccounts = Array.isArray(rawData)
      ? rawData
      : rawData?.results || [];
    return formatAccountOptions(rawAccounts);
  } catch (error) {
    console.error('Failed to fetch account options:', error);
    return DEFAULT_ACCOUNT_OPTIONS;
  }
};

export const DATE_PRESET_OPTIONS = [
  { label: 'This Week', value: 'THIS_WEEK' },
  { label: 'This Month', value: 'THIS_MONTH' },
  { label: 'Last Month', value: 'LAST_MONTH' },
  { label: 'Last 6 Months', value: 'LAST_6_MONTHS' },
  { label: 'All Time', value: 'ALL' },
  { label: 'Custom Date Range', value: 'CUSTOM' },
] as const;

export interface BalanceAuditResponse {
  account: string;
  total_records: number;
  discrepancies_found: number;
  results: EmailPayload[];
}

export interface TaxonomyItem {
  id: string;
  category: string;
  subcategory: string;
  display_order: number;
  is_active: number;
}

export const fetchTaxonomyOptions = async (): Promise<TaxonomyOption[]> => {
  try {
    return await getTaxonomyTree();
  } catch (err) {
    console.error('Failed to load taxonomy tree:', err);
    return [];
  }
};

export const emailIngestApi = {
  getPendingStagingPayloads: async () => {
    const response = await api.get(`${STAGING_URL}/pending/`);
    return response.data;
  },

  getTunnelStatus: async () => {
    const response = await api.get(`${TUNNEL_URL}/status/`);
    return response.data;
  },

  // TAB 1: STAGING & STREAM ACTIONS
  receiveEmail: async (payload: any, confirm = false) => {
    const response = await api.post(
      `${STAGING_URL}/ingest/?confirm=${confirm}`,
      payload
    );
    return response.data;
  },

  triggerSync: async (params: GetPayloadsParams = {}) => {
    const response = await api.post(`${STAGING_URL}/sync/`, params);
    return response.data;
  },

  commitSelectedPayloads: async (items: any[]) => {
    const response = await api.post(`${STAGING_URL}/commit-selected/`, {
      items,
    });
    return response.data;
  },

  // TAB 2: VAULT & DATABASE ACTIONS
  getPayloads: async (params: GetPayloadsParams = {}) => {
    const response = await api.get(`${VAULT_URL}/`, { params });
    return response.data;
  },

  getStats: async (params: GetPayloadsParams = {}): Promise<IngestStats> => {
    const response = await api.get<IngestStats>(`${VAULT_URL}/stats/`, {
      params,
    });
    return response.data;
  },

  forwardForProcessing: async (ids: string[]) => {
    const response = await api.post(`${VAULT_URL}/forward-processing/`, {
      ids,
    });
    return response.data;
  },

  reparsePayload: async (payloadId: string) => {
    const response = await api.post(`${VAULT_URL}/${payloadId}/reparse/`);
    return response.data;
  },

  // TAXONOMY CLASSIFICATION UPDATE
  updatePayloadTaxonomy: async (
    payloadId: string,
    categoryId?: string,
    categoryName?: string,
    subcategoryId?: string,
    subcategoryName?: string
  ) => {
    const response = await api.patch(`${VAULT_URL}/${payloadId}/taxonomy/`, {
      category_id: categoryId,
      category_name: categoryName,
      subcategory_id: subcategoryId,
      subcategory_name: subcategoryName,
    });
    return response.data;
  },

  batchUpdateTaxonomy: async (
    updates: Array<{
      payloadId: string;
      categoryName: string;
      subcategoryName: string;
    }>
  ) => {
    const response = await api.post(`${VAULT_URL}/batch-taxonomy/`, {
      updates,
    });
    return response.data;
  },

  // STAGE FOR RECONCILIATION MATCHING
  stageForMatching: async (payloadIds: string[]) => {
    const response = await api.post(`${VAULT_URL}/stage-for-matching/`, {
      payload_ids: payloadIds,
    });
    return response.data;
  },

  // BALANCE DISCREPANCIES AUDIT
  runBalanceAudit: async (account = '0060'): Promise<BalanceAuditResponse> => {
    const response = await api.get<BalanceAuditResponse>(
      `${BALDISC_URL}/audit/`,
      {
        params: { account },
      }
    );
    return response.data;
  },
};
