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

// export interface ClusterItem {
//   id: string;
//   narration: string;
//   amount: number;
// }

export interface RemarksJSON {
  directional_prefix?: 'By' | 'To' | null;
  target_account_name?: string | null;
  display_text?: string | null;
  payee?: string | null;
  upi_ref?: string | null;
  user_note?: string | null;
  rule_code?: string | null;
  source?: string | null;
}

export interface ClusterItem {
  id: string;
  row_identifier?: string;
  transaction_date?: string;
  narration: string;
  amount: number;
  direction?: 'OUTFLOW' | 'INFLOW';
  flag_color?: 'rose' | 'green';
  debit?: number;
  credit?: number;
  remarks?: RemarksJSON | string | null;
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

  transaction_ids?: string[];
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
  patterns?: string[];
  pattern?: string;
  save_rule?: boolean;
  entry_type?: 'Debit' | 'Credit';
}

/**
 * Fetches auto-clustered merchant patterns for Suspense Account transactions.
 */
// export const getSuspenseClusters1 =
//   async (): Promise<SuspenseWorkbenchResponse> => {
//     const response = await api.get<SuspenseWorkbenchResponse>(
//       '/get_suspense_workbench_data/'
//     );
//     return response.data;
//   };

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

// export const getSuspenseClusters = async (
//   subcategory?: string
// ): Promise<SuspenseWorkbenchResponse> => {
//   const response = await api.get<SuspenseWorkbenchResponse>(
//     '/get_suspense_workbench_data/',
//     {
//       params: {
//         subcategory: subcategory || 'Suspense Account',
//       },
//     }
//   );
//   return response.data;
// };

export const getSuspenseClusters = async (
  subcategoryName: string = 'Suspense Account',
  accountId?: number
): Promise<SuspenseWorkbenchResponse> => {
  const response = await api.get<SuspenseWorkbenchResponse>(
    '/get_suspense_workbench_data/',
    {
      params: {
        subcategory: subcategoryName,
        ...(accountId && { account_id: accountId }),
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

export interface TaxonomyOption {
  category: string;
  subcategories: string[];
}

export interface TaxonomyResponse {
  status: string;
  taxonomy: TaxonomyOption[];
}

export interface ExtendedCluster {
  pattern: string;
  count: number;
  total_amount: number;
  total_outflow?: number;
  total_inflow?: number;
  transaction_ids?: string[];
  items?: ClusterItem[];
  sample_descriptions: string[];
}

export const getTaxonomyTree = async (): Promise<TaxonomyOption[]> => {
  // Use your `api` client so it routes through the proper base URL/proxy!
  const response = await api.get<TaxonomyResponse>('/get_taxonomy_tree/');

  if (response.data && response.data.status === 'success') {
    return response.data.taxonomy;
  }
  return [];
};

export interface AddTaxonomyPayload {
  category: string;
  subcategory: string;
}

export const addTaxonomyNode = async (
  payload: AddTaxonomyPayload
): Promise<boolean> => {
  try {
    const response = await api.post('/add_taxonomy_node/', payload);
    return response.data?.status === 'success';
  } catch (err) {
    console.error('Failed to add new taxonomy node:', err);
    return false;
  }
};

export interface UpdateUserNotePayload {
  entry_id: string;
  user_note: string;
}

export interface UpdateUserNoteResponse {
  status: string;
  entry_id: string;
  remarks: any;
}

export const updateEntryUserNote = async (
  payload: UpdateUserNotePayload
): Promise<UpdateUserNoteResponse | null> => {
  try {
    const response = await api.post('/classification/entry-note/', payload);
    return response.data;
  } catch (err) {
    console.error('Failed to update entry user note:', err);
    return null;
  }
};

export interface SuggestedRule {
  rule_code: string;
  suggested_category: string;
  suggested_subcategory: string;
  matched_pattern: string;
}

export const getSuggestedRule = async (
  pattern: string,
  entryType: 'Debit' | 'Credit' = 'Debit'
): Promise<SuggestedRule | null> => {
  if (!pattern || pattern.trim().length < 3) return null;

  try {
    const response = await fetch('/classification/suggest_rule_for_cluster/', {
      // 👈 Added /api/classification
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pattern: pattern.trim(),
        entry_type: entryType,
      }),
    });

    if (!response.ok) return null;
    const data = await response.json();

    if (data?.has_suggestion) {
      return {
        rule_code: data.rule_code,
        suggested_category: data.suggested_category,
        suggested_subcategory: data.suggested_subcategory,
        matched_pattern: data.matched_pattern,
      };
    }
  } catch (err) {
    console.error('Failed to fetch rule suggestion:', err);
  }
  return null;
};

//// Sweep Call
// ==========================================
// SWEEP HUB & RULE SUGGESTION ENDPOINTS
// ==========================================

export interface SweepMatchGroup {
  pattern: string;
  matched_rows: number;
  total_amount: number;
  suggested_category: string;
  suggested_subcategory: string;
  rule_code: string;
}

export const getSweepPreview = async (
  accountId?: string
): Promise<SweepMatchGroup[]> => {
  try {
    const url =
      accountId && accountId !== '99'
        ? `/classification/staging/sweep-preview/?account_id=${accountId}`
        : `/classification/staging/sweep-preview/`;

    const response = await api.get(url);
    return response.data?.status === 'success'
      ? response.data.rule_matches || []
      : [];
  } catch (err) {
    console.error('Failed to fetch sweep preview from backend:', err);
    return [];
  }
};

export const executeBulkSweep = async (
  patterns: string[],
  accountId?: string
): Promise<boolean> => {
  try {
    const response = await api.post(
      '/classification/staging/execute-bulk-sweep/',
      {
        patterns,
        account_id: accountId,
      }
    );
    return response.data?.status === 'success';
  } catch (err) {
    console.error('Failed to execute bulk sweep:', err);
    return false;
  }
};

// export const removePatternFromRule = async (
//   ruleCode: string,
//   pattern: string
// ): Promise<boolean> => {
//   console.log(`[API] 🚀 Initiating pattern purge:`, { ruleCode, pattern });

//   try {
//     const response = await fetch(
//       '/classification/staging/remove_pattern_from_rule/',
//       {
//         method: 'POST',
//         headers: {
//           'Content-Type': 'application/json',
//         },
//         body: JSON.stringify({
//           rule_code: ruleCode,
//           pattern: pattern,
//         }),
//       }
//     );

//     console.log(
//       `[API] 📡 Response status:`,
//       response.status,
//       response.statusText
//     );

//     if (!response.ok) {
//       console.error(
//         `[API] ❌ Request failed with HTTP status ${response.status}`
//       );
//       return false;
//     }

//     const data = await response.json();
//     console.log(`[API] 📦 Response data:`, data);

//     const isSuccess = data.status === 'success';
//     if (isSuccess) {
//       console.log(
//         `[API] ✅ Pattern '${pattern}' successfully purged from rule ${ruleCode}`
//       );
//     } else {
//       console.warn(
//         `[API] ⚠️ Server returned non-success status:`,
//         data.message
//       );
//     }

//     return isSuccess;
//   } catch (error) {
//     console.error('Failed to purge pattern from rule:', error);
//     return false;
//   }
// };

export const bulkRemovePatternsFromRules = async (
  items: { rule_code: string; pattern: string }[]
): Promise<boolean> => {
  console.log(
    `[API] 🚀 Initiating bulk pattern purge for ${items.length} items:`,
    items
  );

  try {
    const response = await api.post(
      '/classification/staging/bulk_remove_patterns_from_rules/',
      { items }
    );

    console.log(`[API] 📡 Bulk purge response status:`, response.status);
    console.log(`[API] 📦 Bulk purge response data:`, response.data);

    const isSuccess =
      response.data?.status === 'success' || response.data?.success === true;

    if (isSuccess) {
      console.log(`[API] ✅ Bulk pattern purge completed successfully.`);
    } else {
      console.warn(
        `[API] ⚠️ Bulk purge returned non-success status:`,
        response.data?.message
      );
    }

    return isSuccess;
  } catch (error) {
    console.error('[API] ❌ Failed bulk pattern purge:', error);
    return false;
  }
};

export const removePatternFromRule = async (
  ruleCode: string,
  pattern: string
): Promise<boolean> => {
  console.log(`[API] 🚀 Initiating pattern purge:`, { ruleCode, pattern });

  try {
    const response = await api.post(
      '/classification/staging/remove_pattern_from_rule/',
      {
        rule_code: ruleCode,
        pattern: pattern,
      }
    );

    console.log(
      `[API] 📡 Response status:`,
      response.status,
      response.statusText
    );
    console.log(`[API] 📦 Response data:`, response.data);

    const isSuccess = response.data?.status === 'success';

    if (isSuccess) {
      console.log(
        `[API] ✅ Pattern '${pattern}' successfully purged from rule ${ruleCode}`
      );
    } else {
      console.warn(
        `[API] ⚠️ Server returned non-success status:`,
        response.data?.message
      );
    }

    return isSuccess;
  } catch (error) {
    console.error('[API] ❌ Failed to purge pattern from rule:', error);
    return false;
  }
};
