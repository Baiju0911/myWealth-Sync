// src/api/subledger.ts
import api from './client'; // Points directly to your pre-configured Axios instance

/* ==========================================================================
   Sub-Ledger & Asset Management Interfaces & APIs
   ========================================================================== */

export type AssetCategoryType =
  | 'REAL_ESTATE'
  | 'FIXED_DEPOSIT'
  | 'RECURRING_DEPOSIT'
  | 'MARKET_INVESTMENT'
  | 'PENSION_RETIREMENT'
  | 'INSURANCE_PLAN'
  | 'VEHICLE'
  | 'PRECIOUS_METALS'
  | 'PERSONAL_RECEIVABLE';

export type OwnershipType = 'INDIVIDUAL' | 'JOINT' | 'FAMILY' | 'BUSINESS';

export type AssetStatusType =
  | 'ACTIVE'
  | 'MATURED'
  | 'LIQUIDATED'
  | 'SOLD'
  | 'WRITTEN_OFF';

export type ServiceProviderType =
  | 'PROPERTY_TAX'
  | 'LAND_REVENUE_TAX'
  | 'ELECTRICITY'
  | 'WATER'
  | 'BUILDING_MAINTENANCE'
  | 'INSURANCE'
  | 'GAS';

export type ScheduleType =
  | 'PROPERTY_TAX_DUE'
  | 'LAND_TAX_DUE'
  | 'UTILITY_BILL'
  | 'SIP_DUE'
  | 'PREMIUM_DUE'
  | 'FD_MATURITY';

export type RecurrencePatternType =
  | 'ONE_OFF'
  | 'MONTHLY'
  | 'BIMONTHLY'
  | 'QUARTERLY'
  | 'HALF_YEARLY'
  | 'ANNUALLY';

export interface AssetOperationalAccount {
  id: string;
  service_type_display?: string;
  service_type: ServiceProviderType;
  provider_name: string;
  consumer_identifier: string;
  meter_number?: string | null;
  matching_keyword?: string | null;
  is_active: boolean;
  asset: string;
}

export interface AssetComplianceSchedule {
  id: string;
  schedule_type_display?: string;
  recurrence_pattern_display?: string;
  title: string;
  schedule_type: ScheduleType;
  recurrence_pattern: RecurrencePatternType;
  due_date: string;
  expected_amount: string | number;
  advance_notice_days: number;
  is_paid: boolean;
  paid_at?: string | null;
  linked_row_identifier?: string | null;
  asset: string;
  operational_account?: string | null;
}

export interface AssetSubLedgerPayload {
  asset_code: string;
  name: string;
  category: AssetCategoryType;
  acquisition_date: string;
  acquisition_cost: number | string;
  current_valuation: number | string;
  ownership_type: OwnershipType;
  ownership_share_pct: number | string;
  status: AssetStatusType;
  linked_gl_account: number | string;
  metadata_payload?: Record<string, any>;
}

export interface AssetSubLedgerNode extends AssetSubLedgerPayload {
  id: string;
  category_display?: string;
  status_display?: string;
  ownership_type_display?: string;
  valuation_updated_at?: string;
  created_at?: string;
  operational_accounts: AssetOperationalAccount[];
  compliance_schedules: AssetComplianceSchedule[];
}

export interface CandidateMatchQuery {
  document_date: string;
  target_amount?: number | string | null;
  account_id?: number | string | null;
  keywords?: string[];
  day_window?: number;
}

export interface CandidateMatchResult {
  journal_id: string;
  row_identifier: string;
  account_id: number | string;
  transaction_date: string;
  date_offset_days: number;
  debit: number;
  credit: number;
  remarks: string | Record<string, any>;
  probability_score: number;
  is_mapped?: boolean;
  is_mapped_to_this_asset?: boolean;
  mapping_info?: {
    mapping_id: string;
    asset_id: string | number;
    asset_code?: string;
    asset_name?: string;
  } | null;
}

export interface CandidateMatchResponse {
  query: CandidateMatchQuery;
  candidate_count: number;
  candidates: CandidateMatchResult[];
}

export interface BindTransactionPayload {
  asset_id: string;
  schedule_id?: string | null;
  operational_account_id?: string | null;
  row_identifier?: string | null;
  is_cash_entry?: boolean;
  transaction_date: string;
  amount: number | string;
  transaction_purpose: string;
  user_note?: string;
}

export interface BindTransactionResponse {
  status: string;
  mapping_id: string;
  message: string;
}

export interface OperationalAccountPayload {
  asset: string;
  service_type: ServiceProviderType;
  provider_name: string;
  consumer_identifier: string;
  meter_number?: string;
  matching_keyword?: string;
  is_active?: boolean;
}

export interface SchedulePayload {
  asset: string;
  operational_account?: string | null;
  title: string;
  schedule_type: ScheduleType;
  recurrence_pattern?: RecurrencePatternType;
  due_date: string;
  expected_amount: number | string;
  advance_notice_days?: number;
}
export interface SubledgerTaxonomyItem {
  id: string; // UUID string from Django
  subcategory: string;
}

export interface SubledgerTaxonomyGroup {
  category: string;
  subcategories: SubledgerTaxonomyItem[];
}

export interface UnmapTransactionRequest {
  mapping_id?: string;
  row_identifier?: string;
  asset_id?: string | number;
}

// Define candidate match query payload
export interface CandidateMatchPayload {
  asset_id?: string | number;
  document_date: string;
  target_amount?: number | null;
  day_window?: number;
  keywords?: string[];
}

export const subledgerApi = {
  /**
   * 📥 GET: List all sub-ledger master assets with nested operational accounts & schedules
   */
  getAssets: async (): Promise<AssetSubLedgerNode[]> => {
    const res = await api.get<AssetSubLedgerNode[]>('/subledgers/assets/');
    return res.data;
  },

  /**
   * 📥 GET: Single Asset detailed view
   */
  getTaxonomyNodesForSubledger: async (): Promise<SubledgerTaxonomyGroup[]> => {
    const response = await api.get('/get_taxonomy_tree/');
    if (response.data && response.data.status === 'success') {
      return response.data.taxonomy;
    }
    return [];
  },

  getAssetById: async (id: string): Promise<AssetSubLedgerNode> => {
    const res = await api.get<AssetSubLedgerNode>(`/subledgers/assets/${id}/`);
    return res.data;
  },

  updateAsset: async (
    id: string,
    payload: Partial<AssetSubLedgerPayload>
  ): Promise<AssetSubLedgerNode> => {
    const res = await api.put<AssetSubLedgerNode>(
      `/subledgers/assets/${id}/`,
      payload
    );
    return res.data;
  },

  updateOperationalAccount: async (
    id: string,
    payload: Partial<OperationalAccountPayload>
  ): Promise<AssetOperationalAccount> => {
    const res = await api.put<AssetOperationalAccount>(
      `/subledgers/operational-accounts/${id}/`,
      payload
    );
    return res.data;
  },

  updateSchedule: async (
    id: string,
    payload: Partial<SchedulePayload>
  ): Promise<AssetComplianceSchedule> => {
    const res = await api.put<AssetComplianceSchedule>(
      `/subledgers/schedules/${id}/`,
      payload
    );
    return res.data;
  },

  /**
   * 🗑️ DELETE: Delete an Asset Sub-Ledger record
   */
  deleteAsset: async (id: string): Promise<boolean> => {
    await api.delete(`/subledgers/assets/${id}/`);
    return true;
  },

  /**
   * 🗑️ DELETE: Remove an operational account
   */
  deleteOperationalAccount: async (id: string): Promise<boolean> => {
    await api.delete(`/subledgers/operational-accounts/${id}/`);
    return true;
  },

  /**
   * 🗑️ DELETE: Remove a compliance schedule
   */
  deleteSchedule: async (id: string): Promise<boolean> => {
    await api.delete(`/subledgers/schedules/${id}/`);
    return true;
  },

  /**
   * 🚀 POST: Create a new Asset Sub-Ledger record
   */
  createAsset: async (
    payload: AssetSubLedgerPayload
  ): Promise<AssetSubLedgerNode> => {
    const res = await api.post<AssetSubLedgerNode>(
      '/subledgers/assets/',
      payload
    );
    return res.data;
  },

  /**
   * 🎯 POST: Run the ±5 to ±10 day candidate matching algorithm against staging lines
   */
  findCandidates: async (
    query: CandidateMatchQuery
  ): Promise<CandidateMatchResponse> => {
    const res = await api.post<CandidateMatchResponse>(
      '/subledgers/assets/find-candidates/',
      query
    );
    return res.data;
  },

  unmapTransaction: async (payload: UnmapTransactionRequest) => {
    const response = await api.post(
      '/subledgers/assets/unmap-transaction/',
      payload
    );
    return response.data;
  },
  /**
   * ⚡ POST: Atomically bind a bank row identifier to an asset schedule
   */
  bindTransaction: async (
    payload: BindTransactionPayload
  ): Promise<BindTransactionResponse> => {
    const res = await api.post<BindTransactionResponse>(
      '/subledgers/assets/bind-transaction/',
      payload
    );
    return res.data;
  },

  /**
   * ➕ POST: Register a consumer ID/meter/account under an asset
   */
  createOperationalAccount: async (
    payload: OperationalAccountPayload
  ): Promise<AssetOperationalAccount> => {
    const res = await api.post<AssetOperationalAccount>(
      '/subledgers/operational-accounts/',
      payload
    );
    return res.data;
  },

  /**
   * ⏰ POST: Schedule a compliance or tax reminder under an asset
   */
  createSchedule: async (
    payload: SchedulePayload
  ): Promise<AssetComplianceSchedule> => {
    const res = await api.post<AssetComplianceSchedule>(
      '/subledgers/schedules/',
      payload
    );
    return res.data;
  },

  /**
   * 📋 GET: Fetch pending unpaid compliance schedules
   */
  getPendingDues: async (): Promise<AssetComplianceSchedule[]> => {
    const res = await api.get<AssetComplianceSchedule[]>(
      '/subledgers/schedules/pending-dues/'
    );
    return res.data;
  },
};
