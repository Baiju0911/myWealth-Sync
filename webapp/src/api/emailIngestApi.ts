import api from './client';
import { accountApi, getTaxonomyTree, type TaxonomyOption } from './api';

export interface EmailPayload {
  id: string;
  source: string;
  bank_name?: string;
  account_last4?: string;
  merchant?: string;
  amount?: number | null;
  balance?: number | null;
  txn_type?: 'DEBIT' | 'CREDIT' | 'NOISE' | string;
  upi_ref?: string;
  status:
    | 'PARSED'
    | 'PREVIEW_ONLY'
    | 'DUPLICATE'
    | 'STAGED'
    | 'COMPLETED'
    | string;
  is_duplicate?: boolean;
  created_at?: string;
  email_date?: string;
  decrypted_body?: string;
  body?: string;
  subject?: string;
  email_from?: string;
  headers_json?: any;
  taxonomy_payload?: any;
  raw_item?: any;
  parsed_transaction?: any;
  raw_payload?: any;
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
  date_preset?: DatePresetType;
  start_date?: string;
  end_date?: string;
  account?: string;
  staged_only?: boolean;
}

// =========================================================================
// PDF Bank Statement Staging Types
// =========================================================================
export interface StagedStatementItem {
  stage_id: string;
  message_id: string;
  attachment_id?: string;
  attachment_hash?: string;
  filename: string;
  file_path: string;
  file_size: number;
  doc_type: string;
  status: string;
  sender: string;
  subject: string;
  received_date: string;
  account_hint: string;
  bank_name: string;
  period_start: string | null;
  period_end: string | null;
  selected: boolean;
  created_at: string;
}

export interface StagedStatementsResponse {
  status: string;
  count: number;
  results: StagedStatementItem[];
}

export interface HarvestStatementsResponse {
  status: string;
  message: string;
  staged_count: number;
  items: StagedStatementItem[];
}

export interface CommitStatementsPayload {
  selected_ids: string[];
  overrides?: Record<
    string,
    { account_hint?: string; bank_name?: string; doc_type?: string }
  >;
}

export interface CommitStatementsResponse {
  status: string;
  message: string;
  committed_items: any[];
}

const STAGING_URL = '/ingest/email/staging';
const VAULT_URL = '/ingest/email/payloads';
const TUNNEL_URL = '/ingest/email/tunnel';
const BALDISC_URL = '/ingest/email/balance-check';
const DOCUMENTS_INBOX_URL = '/ingest/email/documents/inbox';

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

export type DatePresetType =
  | 'ALL'
  | 'ALL_TIME'
  | 'THIS_WEEK'
  | 'THIS_MONTH'
  | 'LAST_MONTH'
  | 'LAST_6_MONTHS'
  | 'CUSTOM';

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

  // =========================================================================
  // TAB 1: STAGING & STREAM ACTIONS
  // =========================================================================
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
    const sanitizedItems = items.map((item) => {
      const raw = item.raw_payload || item.raw_item?.raw_payload || {};
      const parsed =
        item.parsed_transaction || item.raw_item?.parsed_transaction || {};

      return {
        payload_hash:
          item.id || item.payload_hash || item.raw_item?.payload_hash,
        source: item.source || raw.source || 'GMAIL_API',
        raw_payload: {
          email_date: item.email_date || raw.email_date || item.created_at,
          email_from: item.email_from || raw.email_from,
          subject: item.subject || raw.subject,
          decrypted_body: item.body || raw.decrypted_body || '',
        },
        parsed_transaction: parsed,
      };
    });

    const response = await api.post(`${STAGING_URL}/commit-selected/`, {
      items: sanitizedItems,
    });
    return response.data;
  },

  discardStagingPayloads: async (
    ids: string[]
  ): Promise<{ status: string; removed_count: number }> => {
    const response = await api.post(`${STAGING_URL}/discard/`, { ids });
    return response.data;
  },

  // =========================================================================
  // TAB 2: VAULT & DATABASE ACTIONS
  // =========================================================================
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

  stageForMatching: async (payloadIds: string[], syntheticGaps: any[] = []) => {
    const response = await api.post(`${VAULT_URL}/stage-for-matching/`, {
      payload_ids: payloadIds,
      synthetic_gaps: syntheticGaps,
    });
    return response.data;
  },

  unstageFromMatching: async (payloadIds: string[]) => {
    const response = await api.post(`${VAULT_URL}/unstage-from-matching/`, {
      payload_ids: payloadIds,
    });
    return response.data;
  },

  runBalanceAudit: async (account = '0060'): Promise<BalanceAuditResponse> => {
    const response = await api.get<BalanceAuditResponse>(
      `${BALDISC_URL}/audit/`,
      {
        params: { account },
      }
    );
    return response.data;
  },

  // =========================================================================
  // TAB 3: PDF BANK STATEMENTS STAGING & INBOX PIPELINE
  // =========================================================================
  getStagedStatements: async (): Promise<StagedStatementsResponse> => {
    const response = await api.get<StagedStatementsResponse>(
      `${DOCUMENTS_INBOX_URL}/staged/`
    );
    return response.data;
  },

  harvestBankStatements: async (
    maxResults = 25
  ): Promise<HarvestStatementsResponse> => {
    const response = await api.post<HarvestStatementsResponse>(
      `${DOCUMENTS_INBOX_URL}/harvest/`,
      { max_results: maxResults }
    );
    return response.data;
  },

  commitSelectedStatements: async (
    payload: CommitStatementsPayload
  ): Promise<CommitStatementsResponse> => {
    const response = await api.post<CommitStatementsResponse>(
      `${DOCUMENTS_INBOX_URL}/commit/`,
      payload
    );
    return response.data;
  },
  previewStagedPdf: async (
    filePath: string,
    password?: string
  ): Promise<Blob> => {
    const response = await api.post(
      `${DOCUMENTS_INBOX_URL}/preview-staged/`,
      { file_path: filePath, password },
      { responseType: 'blob' }
    );
    return response.data;
  },
};
