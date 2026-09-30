// src/api/statementInboxApi.ts
import api from './client';
import {
  type StagingPreviewLine,
  type TemplateMetadata,
} from '../types/ledger';
import { type LiveStreamPayloadItem } from '../components/ui/data-table/columns';

export interface InboxItem {
  id: string;
  filename: string;
  account_hint: string | null;
  bank_name: string | null;
  period_start: string | null;
  period_end: string | null;
  status: string;
  received_date: string | null;
  file_path: string;
}

export interface LiveStreamCommitResponse {
  status: string;
  enriched_count: number;
  waiting_count: number;
  duration_ms?: number;
}

export interface LiveStreamPayloadsResponse {
  total_count: number;
  results: LiveStreamPayloadItem[];
}

export interface IngestBulkResponse {
  status: string;
  preview_dataset?: StagingPreviewLine[];
  data?: {
    preview_dataset?: StagingPreviewLine[];
    decrypted?: boolean;
  };
  export_filename?: string;
  strategy_processed?: string;
  engine_strategy_executed?: string;
  confidence_score?: number;
  decrypted?: boolean;
  count?: number;
  opening_balance?: number;
  closing_balance?: number;
  total_debit?: number;
  total_credit?: number;
  debit_line_count?: number;
  credit_line_count?: number;
  empty_memo_line_count?: number;
  system_noise_records_cleared?: number;
  duplicate_count?: number;
  raw_csv_stream?: string;
  generated_raw_csv_stream?: string;
  message?: string;
}

export interface InboxPreviewResponse {
  status: string;
  preview_dataset?: StagingPreviewLine[];
  account_id?: number | string;
  account_hint?: string;
  bank_name?: string;
  strategy_processed?: string;
  count?: number;
  opening_balance?: number;
  closing_balance?: number;
  total_debit?: number;
  total_credit?: number;
  message?: string;
  error?: string;
}

export const statementInboxApi = {
  // 📥 Attachment Inbox Endpoints
  getPendingInboxItems: async (): Promise<InboxItem[]> => {
    const res = await api.get('/tracker/inbox/pending/');
    return Array.isArray(res.data) ? res.data : [];
  },

  previewInboxItem: async (itemId: string): Promise<InboxPreviewResponse> => {
    const res = await api.post(`/tracker/inbox/${itemId}/preview/`);
    return res.data;
  },

  commitInboxItem: async (
    itemId: string,
    previewDataset: StagingPreviewLine[],
    metaSummary: Record<string, any>
  ): Promise<any> => {
    const res = await api.post(`/tracker/inbox/${itemId}/commit/`, {
      preview_dataset: previewDataset,
      meta_summary: metaSummary,
    });
    return res.data;
  },

  // ⚡ Live Notifications Stream Endpoints
  getLiveStreamPayloads: async (): Promise<LiveStreamPayloadsResponse> => {
    const res = await api.get('/tracker/inbox/live-payloads/');
    if (Array.isArray(res.data)) {
      return { total_count: res.data.length, results: res.data };
    }
    return {
      total_count: res.data?.total_count ?? (res.data?.results?.length || 0),
      results: res.data?.results ?? [],
    };
  },

  commitLiveStreamEnrichment: async (): Promise<LiveStreamCommitResponse> => {
    const res = await api.post(
      '/tracker/inbox/live-payloads/commit-enrichment/'
    );
    return res.data;
  },

  // 📁 Manual Upload & Ingest Bulk Pipelines
  getAvailableTemplates: async (): Promise<TemplateMetadata[]> => {
    const res = await api.get('/statements/available/');
    return Array.isArray(res.data) ? res.data : [];
  },

  ingestBulkStatement: async (
    formData: FormData
  ): Promise<IngestBulkResponse> => {
    const res = await api.post('/statement/ingestbulk/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  commitStagingLedger: async (payload: {
    account_id: string;
    preview_dataset: StagingPreviewLine[];
    file_name: string;
    strategy_used: string;
    meta_summary: Record<string, any>;
  }): Promise<any> => {
    const res = await api.post('/statement/commit-staging/', payload);
    return res.data;
  },
};

export interface StatementSideAudit {
  id: string;
  statement_date: string;
  amount: number;
  raw_narration: string;
  bank_account: string;
  bank_name: string;
}

export interface LiveStreamSideAudit {
  payload_id: string;
  source: string;
  merchant: string;
  upi_rrn: string;
  stream_amount: number;
  received_at: string | null;
  enriched_at: string | null;
  collision_hash: string | null;
}

export interface EnrichedPairAuditItem {
  statement_side: StatementSideAudit;
  live_stream_side: LiveStreamSideAudit;
}

export interface EnrichedAuditResponse {
  total_count: number;
  results: EnrichedPairAuditItem[];
}

export const fetchEnrichedReconciliationAudit = async (
  limit = 100
): Promise<EnrichedAuditResponse> => {
  const res = await api.get(
    '/tracker/inbox/live-payloads/reconciliation-audit/',
    { params: { limit } }
  );
  return res.data;
};

export interface EnrichedAuditRecord {
  statement_id: string;
  statement_date: string;
  statement_amount: number | string;
  raw_narration: string;
  account_last4: string;
  bank_name: string;
  payload_id?: string | null;
  stream_source: string;
  resolved_merchant: string;
  live_upi_rrn?: string | null;
  enriched_at?: string | null;
  completed_at?: string | null;
  match_tier?: string;
  classification?: {
    target_account: string;
    rule_code: string;
    status: string;
    user_note?: string;
  } | null;
  has_warning?: boolean;
  discrepancy_details?: {
    alert_amount?: number | null;
    statement_amount?: number;
    variance?: number;
    warning_type?: string;
  } | null;
}
export interface EnrichedAuditListResponse {
  total_count: number;
  results: EnrichedAuditRecord[];
}

export const fetchLiveStreamAudit = async (
  limit = 200
): Promise<EnrichedAuditListResponse> => {
  const res = await api.get('/inbox/live-payloads/audit/', {
    params: { limit },
  });
  return res.data;
};
