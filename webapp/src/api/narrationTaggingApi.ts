// webapp/src/api/narrationTaggingApi.ts
import api from './client';

export interface GroupHierarchyItem {
  id: number;
  header_scope: string;
  group_tag: string;
  subgroup_tag?: string | null;
  display_order: number;
}

export interface CreateGroupPayload {
  header_scope: string;
  group_tag: string;
  subgroup_tag?: string | null;
}

export interface MoveSubgroupPayload {
  header_scope: string;
  subgroup_tag: string;
  target_group_tag: string;
}

export interface TagRuleItem {
  id: number;
  keyword_pattern: string;
  match_tokens?: string[];
  match_type: 'CONTAINS' | 'EXACT' | 'REGEX' | 'LAST4';
  allowed_vector: 'ANY' | 'INFLOW' | 'OUTFLOW';
  header_scope: string;
  parent_group_tag: string;
  subgroup_tag?: string | null;
  require_internal_contra: boolean;
  source_account_id?: number | null;
  priority: number;
  is_active: boolean;
}

export interface CreateTagRulePayload {
  keyword_pattern: string;
  match_tokens?: string[];
  match_type?: 'CONTAINS' | 'EXACT' | 'REGEX' | 'LAST4';
  allowed_vector?: 'ANY' | 'INFLOW' | 'OUTFLOW';
  header_scope: string;
  parent_group_tag: string;
  subgroup_tag?: string | null;
  require_internal_contra?: boolean;
  source_account_id?: number | null;
  priority?: number;
  is_active?: boolean;
}
export const narrationTaggingApi = {
  /**
   * 🏷️ GET: Fetch group hierarchies scoped to an active header (e.g. "Suspense Account")
   */
  getHierarchies: async (
    headerScope: string
  ): Promise<GroupHierarchyItem[]> => {
    const res = await api.get<GroupHierarchyItem[]>('/workbench-groups/', {
      params: { header_scope: headerScope },
    });
    return res.data;
  },

  /**
   * ➕ POST: Create a group tag under an active header
   */
  createGroup: async (
    payload: CreateGroupPayload
  ): Promise<GroupHierarchyItem> => {
    const res = await api.post<GroupHierarchyItem>(
      '/workbench-groups/',
      payload
    );
    return res.data;
  },

  /**
   * 🗑️ DELETE: Remove a group hierarchy record
   */
  deleteHierarchy: async (id: number): Promise<boolean> => {
    await api.delete(`/workbench-groups/${id}/`);
    return true;
  },

  /**
   * 🔀 POST: Move a subgroup to another group within the header
   */
  moveSubgroup: async (
    payload: MoveSubgroupPayload
  ): Promise<{ status: string; updated_rows: number }> => {
    const res = await api.post<{ status: string; updated_rows: number }>(
      '/workbench-groups/move-subgroup/',
      payload
    );
    return res.data;
  },

  /**
   * 📜 GET: Fetch all pattern routing tag rules
   */
  getTagRules: async (headerScope?: string): Promise<TagRuleItem[]> => {
    const params = headerScope ? { header_scope: headerScope } : {};
    const res = await api.get<TagRuleItem[]>('/master-tag-rules/', { params });
    return res.data;
  },

  /**
   * ⚡ POST: Save a new pattern auto-routing tag rule
   */
  createTagRule: async (
    payload: Partial<TagRuleItem>
  ): Promise<TagRuleItem> => {
    const res = await api.post<TagRuleItem>('/master-tag-rules/', payload);
    return res.data;
  },

  applyRuleToStream: async (
    ruleId: number
  ): Promise<{ status: string; matched_rows: number; applied_tag: string }> => {
    const res = await api.post('/master-tag-rules/apply-rule/', {
      rule_id: ruleId,
    });
    return res.data;
  },

  getCandidatePatterns: async (payload: {
    transaction_ids: (string | number)[];
    cluster_pattern?: string;
  }): Promise<{
    candidate_patterns: string[];
    clean_entity?: string;
    detected_channel?: string;
    source_account?: string;
    destination_account?: string;
    is_internal_contra?: boolean;
    raw_narration?: string;
  }> => {
    const res = await api.post(
      '/classification/staging/get_candidate_patterns/',
      payload
    );
    return res.data;
  },

  synthesizeRuleContext: async (payload: {
    transaction_ids: (string | number)[];
    cluster_pattern?: string;
    vendor_name?: string;
  }): Promise<{
    status: string;
    raw_narration: string;
    tokens: string[];
    detected_rail: string;
    source_account: string;
    source_account_id: number | null;
    destination_account: string;
    is_contra: boolean;
  }> => {
    const res = await api.post(
      '/master-tag-rules/synthesize-context/',
      payload
    );
    return res.data;
  },

  updateHierarchy: async (
    id: number,
    payload: {
      header_scope?: string;
      group_tag?: string;
      subgroup_tag?: string | null;
      display_order?: number;
    }
  ): Promise<GroupHierarchyItem> => {
    const res = await api.patch(`/workbench-groups/${id}/`, payload);
    return res.data;
  },
};
