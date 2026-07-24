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

export const ledgerMasterApi = {
  /**
   * 📥 GET: Pull down the full collection of master data nodes
   */
  getMasterCategories: async () => {
    const targetUrl = '/config/categories/';
    console.log(
      `🔌 [AXIOS OUTBOUND] Hitting path: ${api.defaults.baseURL || ''}${targetUrl}`
    );
    const res = await api.get(targetUrl);
    return res.data;
  },

  /**
   * 🚀 POST: Commit a new configuration block or transfer route mapping
   */
  createMasterCategory: async (payload: any) => {
    // 🎯 FIXED: Realigned route pattern to point to Django's config/categories/
    const res = await api.post('/config/categories/', payload);
    return res.data;
  },

  /**
   * 🗑️ DELETE: Permanently remove a database entry mapping by row primary key
   */
  deleteMasterCategory: async (id: string | number) => {
    // 🎯 FIXED: Realigned route pattern to point to Django's config/categories/<id>/
    await api.delete(`/config/categories/${id}/`);
    return true;
  },
};

/* ==========================================================================
   Staging WIP Evaluation Queue Matrix Interfaces & API
   ========================================================================== */

export interface WorkspaceAnalysis {
  category_id: number | null;
  category_item: string;
  subcategory: string;
  dashboard_cat: string;
  group: string;
  rule_code: string;
  rule_title: string;
}

export type ConfidenceLevel = 'HIGH' | 'MEDIUM' | 'LOW' | 'ZERO';

export interface PipelineStopTelemetry {
  category: string | null;
  subcategory: string | null;
  score: number;
  dashboard?: string | null;
  rule_id?: number | null;
}

export interface WorkspaceNode {
  wip_id: string;
  hash: string;
  date: string;
  narration: string;
  debit: number;
  credit: number;
  confidence: ConfidenceLevel;
  errors: string[];
  routing_status: string;
  analysis: WorkspaceAnalysis;

  pipeline_trace: {
    stop1_known_default: PipelineStopTelemetry;
    stop2_self_transfer: PipelineStopTelemetry;
    stop3_balance_sheet: PipelineStopTelemetry;
    stop4_accounting_rule: PipelineStopTelemetry;
  };
}

export interface SweepMetrics {
  scanned: number;
  initialized: number;
  skipped: number;
}

export interface EvaluationSummary {
  staged_for_bulk_high: number;
  uncategorized_vault_zero: number;
}

export interface EvaluatorPayloadResponse {
  account_id: string;
  sweep_metrics: SweepMetrics;
  evaluation_summary: EvaluationSummary;
  workspace_queue: WorkspaceNode[];
}

export interface SplitAllocationPayload {
  categoryId: string;
  subcat: string;
  amount: number;
}

export const stagingQueueApi = {
  /**
   * 📥 POST: Triggers the 3-Tier processing pipeline & populates the sandbox view rows
   */
  evaluateWorkspace: async (
    accountId: string
  ): Promise<EvaluatorPayloadResponse> => {
    const res = await api.post<EvaluatorPayloadResponse>(
      '/staging/auto-categorize/',
      {
        account_id: accountId,
      }
    );
    return res.data;
  },

  /**
   * ⚡ POST: Clears high-confidence transaction lines directly into the accounting ledger
   */
  bulkCommitLedger: async (
    accountId: string,
    wipIds: string[]
  ): Promise<void> => {
    await api.post('/accounting/bulk-commit-ledger/', {
      account_id: accountId,
      wip_ids: wipIds,
    });
  },

  /**
   * 🔀 POST: Commits a balanced split line allocation array to separate destination headers
   */
  commitSplitAllocation: async (
    parentWipId: string,
    splits: SplitAllocationPayload[]
  ): Promise<void> => {
    await api.post('/accounting/wip-split-allocation/', {
      parent_wip_id: parentWipId,
      splits: splits,
    });
  },
};

//DashBoards

export interface AccountNode {
  id: string | number;
  name: string;
  account_number: string;
}

export const getAccounts = async (): Promise<AccountNode[]> => {
  const response = await api.get<AccountNode[]>('/accounts/');
  return response.data;
};

export interface DashboardParams {
  bank_account_id?: string | number;
  taxonomy_account_id?: string | number;
  from_date?: string;
  to_date?: string;
}

export interface DateBounds {
  min_date: string;
  max_date: string;
  applied_from_date: string;
  applied_to_date: string;
}

export interface KPISummary {
  net_liquidity: number;
  total_income: number;
  total_expense: number;
  suspense_count: number;
  suspense_amount: number;
}

export interface SymmetryProof {
  bank_account_id: number;
  taxonomy_account_id: number;
  bank_net: number;
  taxonomy_net: number;
  variance: number;
  is_balanced: boolean;
}

export interface CategoryRow {
  category: string | null;
  subcategory: string | null;
  transaction_count: number;
  total_debit: string;
  total_credit: string;
  net_balance: string;
}

export interface DashboardSummaryResponse {
  date_bounds: DateBounds;
  kpis: KPISummary;
  symmetry_proof: SymmetryProof;
  category_breakdown: CategoryRow[];
}

// Centrally managed call using your application's client instance
export const getDashboardSummary = async (
  params: DashboardParams
): Promise<DashboardSummaryResponse> => {
  const response = await api.get<DashboardSummaryResponse>(
    '/dashboard/summary/',
    { params }
  );
  return response.data;
};

//Classifications

// Classifications

export interface ClusterItem {
  id: string;
  narration: string;
  amount: number;
}

export interface ApplyReclassificationParams {
  transaction_ids: string[];
  target_category: string;
  target_subcategory: string;
  pattern?: string | null; // 👈 Allow null here
  save_rule: boolean;
}

export interface Cluster {
  pattern: string;
  count: number;
  total_amount: number;
  sample_descriptions: string[];
  transaction_ids: string[];
  items?: ClusterItem[];
}

export interface SuspenseWorkbenchResponse {
  status: string;
  total_clusters: number;
  clusters: Cluster[];
}

export interface ReclassifyPayload {
  transaction_ids: string[];
  target_category: string;
  target_subcategory: string;
  pattern?: string;
  save_rule?: boolean;
}

/**
 * Fetches auto-clustered merchant patterns for Suspense Account transactions.
 */
export const getSuspenseClusters1 =
  async (): Promise<SuspenseWorkbenchResponse> => {
    const response = await api.get<SuspenseWorkbenchResponse>(
      '/get_suspense_workbench_data/'
    );
    return response.data;
  };

// src/api.ts (or wherever getSuspenseClusters is declared)
// export const getSuspenseClusters = async (
//   subcategory?: string
// ): Promise<any> => {
//   const url = subcategory
//     ? `/api/get_suspense_workbench_data/?subcategory=${encodeURIComponent(subcategory)}`
//     : '/api/get_suspense_workbench_data/';
//   const response = await fetch(url);
//   return response.json();
// };
// export const getSuspenseClusters = async (
//   subcategory?: string
// ): Promise<any> => {
//   // 🟢 Use encodeURIComponent to safely handle spaces and special chars like '&'
//   const subParam = subcategory
//     ? encodeURIComponent(subcategory)
//     : 'Suspense%20Account';

//   // Note the trailing slash before '?' to avoid Django 301 redirects!
//   const url = `/get_suspense_workbench_data/?subcategory=${subParam}`;

//   const response = await fetch(url);

//   if (!response.ok) {
//     throw new Error(`Server returned status ${response.status}`);
//   }

//   return response.json();
// };

export const getSuspenseClusters = async (
  subcategory?: string
): Promise<SuspenseWorkbenchResponse> => {
  const response = await api.get<SuspenseWorkbenchResponse>(
    '/get_suspense_workbench_data/',
    {
      params: {
        subcategory: subcategory || 'Suspense Account',
      },
    }
  );
  return response.data;
};

/**
 * Applies bulk reclassification and updates/learns classification rules.
 */
export const applyReclassification = async (payload: ReclassifyPayload) => {
  const response = await api.post(
    '/apply_reclassification_and_learn/',
    payload
  );
  return response.data;
};
