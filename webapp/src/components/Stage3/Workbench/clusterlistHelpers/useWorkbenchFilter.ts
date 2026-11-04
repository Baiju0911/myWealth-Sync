// webapp/src/components/Stage3/Workbench/clusterlistHelpers/useWorkbenchFilter.ts
import { useState, useMemo, useEffect } from 'react';
import type { ExtendedCluster } from '../../../../api/api';
import {
  parseAdvancedSearchQuery,
  evaluateItemMatch,
  type StatusFilterType,
  type DirectionFilterType,
  type SortOrderType,
} from './searchAndFilterHelpers';

export const useWorkbenchFilter = (
  clusters: ExtendedCluster[],
  clusterItemsMap: Record<string, any[]>,
  searchQuery: string
) => {
  const [statusFilter, setStatusFilter] = useState<StatusFilterType>('all');
  const [directionFilter, setDirectionFilter] =
    useState<DirectionFilterType>('all');
  const [sortOrder, setSortOrder] = useState<SortOrderType>('amount_desc');
  const [expandedClusterKeys, setExpandedClusterKeys] = useState<
    Record<string, boolean>
  >({});

  const criteria = useMemo(
    () => parseAdvancedSearchQuery(searchQuery),
    [searchQuery]
  );

  // In-Memory Cluster Filtering & Sorting (Zero Backend Calls)
  const filteredClusters = useMemo(() => {
    const result = clusters.filter((c, idx) => {
      const clusterKey = c.pattern
        ? `cluster-${c.pattern}-${idx}`
        : `cluster-idx-${idx}`;
      const items = clusterItemsMap[clusterKey] || c.items || [];
      const hasLoadedItems = items.length > 0;

      // 1. Precise match when transactions are loaded in client state
      if (hasLoadedItems) {
        return items.some((it) =>
          evaluateItemMatch(it, criteria, statusFilter, directionFilter)
        );
      }

      // 2. Strict evaluation for unexpanded/collapsed clusters
      if (directionFilter === 'outflow' && ((c as any).total_outflow ?? 0) <= 0)
        return false;
      if (directionFilter === 'inflow' && ((c as any).total_inflow ?? 0) <= 0)
        return false;

      if (statusFilter === 'contra') {
        const isContra = Boolean(
          (c as any).is_contra_group || c.pattern === '#SELF_TRANSFER'
        );
        if (!isContra) return false;
      }

      const clusterTotal = Math.abs(
        Number(
          directionFilter === 'outflow'
            ? ((c as any).total_outflow ?? c.total_amount ?? 0)
            : directionFilter === 'inflow'
              ? ((c as any).total_inflow ?? 0)
              : (c.total_amount ?? 0)
        )
      );

      if (criteria.minAmount != null && clusterTotal < criteria.minAmount) {
        return false;
      }

      if (criteria.minAmount != null && c.sample_descriptions?.length) {
        const hasSampleMeetingMin = c.sample_descriptions.some((desc) => {
          const numbers = desc.match(/[0-9,]+(?:\.[0-9]+)?/g);
          if (!numbers) return false;
          return numbers.some((numStr) => {
            const val = parseFloat(numStr.replace(/,/g, ''));
            return !isNaN(val) && val >= criteria.minAmount!;
          });
        });

        const allSamplesBelowMin = c.sample_descriptions.every((desc) => {
          const numbers = desc.match(/[0-9,]+(?:\.[0-9]+)?/g);
          if (!numbers) return true;
          return numbers.every((numStr) => {
            const val = parseFloat(numStr.replace(/,/g, ''));
            return isNaN(val) || val < criteria.minAmount!;
          });
        });

        if (!hasSampleMeetingMin && c.count === 1) return false;
        if (allSamplesBelowMin && !hasSampleMeetingMin) return false;
      }

      if (
        criteria.maxAmount != null &&
        criteria.minAmount == null &&
        c.count === 1 &&
        clusterTotal > criteria.maxAmount
      ) {
        return false;
      }

      if (criteria.tokens.length > 0) {
        const clusterHaystack = [
          c.pattern,
          (c as any).display_name,
          ...(c.sample_descriptions || []),
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();

        const matchesTokens = criteria.tokens.every((token) =>
          clusterHaystack.includes(token)
        );
        if (!matchesTokens) return false;
      }

      if (criteria.targetYear) {
        const maxDate = String(
          (c as any).max_date || (c as any).end_date || ''
        );
        if (
          maxDate &&
          !maxDate.includes(criteria.targetYear) &&
          maxDate < criteria.targetYear
        ) {
          return false;
        }

        const samplesContainYear = (c.sample_descriptions || []).some((s) =>
          s.includes(criteria.targetYear!)
        );
        if (!samplesContainYear && (c.count ?? 0) <= 5) return false;
      }

      if (criteria.fromBank || criteria.toBank) {
        const routingText = (c.sample_descriptions || [])
          .join(' ')
          .toLowerCase();
        if (criteria.fromBank && !routingText.includes(criteria.fromBank))
          return false;
        if (criteria.toBank && !routingText.includes(criteria.toBank))
          return false;
      }

      return true;
    });

    // ⚡ Sort Clusters
    return result.sort((a, b) => {
      const aAmt = Math.abs(
        Number(a.total_amount ?? (a as any).total_outflow ?? 0)
      );
      const bAmt = Math.abs(
        Number(b.total_amount ?? (b as any).total_outflow ?? 0)
      );
      const aCount = a.count || a.transaction_ids?.length || 0;
      const bCount = b.count || b.transaction_ids?.length || 0;

      if (sortOrder === 'amount_desc') return bAmt - aAmt;
      if (sortOrder === 'count_desc') return bCount - aCount;
      if (sortOrder === 'name_asc')
        return (a.pattern || '').localeCompare(b.pattern || '');
      return 0;
    });
  }, [
    clusters,
    clusterItemsMap,
    criteria,
    statusFilter,
    directionFilter,
    sortOrder,
  ]);

  // Auto-expand clusters when query is entered
  useEffect(() => {
    if (searchQuery.trim().length >= 2) {
      const autoOpen: Record<string, boolean> = {};
      filteredClusters.forEach((c, idx) => {
        const key = c.pattern
          ? `cluster-${c.pattern}-${idx}`
          : `cluster-idx-${idx}`;
        autoOpen[key] = true;
      });
      setExpandedClusterKeys(autoOpen);
    }
  }, [searchQuery, filteredClusters]);

  // 📅 Dynamically collect unique years present across clusters & loaded items
  const availableYears = useMemo(() => {
    const yearsSet = new Set<string>();

    // 1. Collect from loaded line items
    Object.values(clusterItemsMap).forEach((items) => {
      items.forEach((it) => {
        if (it.transaction_date) {
          const match = String(it.transaction_date).match(/\b(20\d{2})\b/);
          if (match) yearsSet.add(match[1]);
        }
      });
    });

    // 2. Collect from cluster metadata and sample descriptions
    clusters.forEach((c) => {
      const dates = [
        (c as any).max_date,
        (c as any).min_date,
        (c as any).end_date,
        (c as any).start_date,
        ...(c.sample_descriptions || []),
      ];

      dates.forEach((d) => {
        if (!d) return;
        const matches = String(d).match(/\b(20\d{2})\b/g);
        if (matches) {
          matches.forEach((y) => yearsSet.add(y));
        }
      });
    });

    // Sort descending (e.g. ['2026', '2025', '2024'])
    return Array.from(yearsSet).sort((a, b) => b.localeCompare(a));
  }, [clusters, clusterItemsMap]);

  const expandAll = () => {
    const map: Record<string, boolean> = {};
    filteredClusters.forEach((c, idx) => {
      const key = c.pattern
        ? `cluster-${c.pattern}-${idx}`
        : `cluster-idx-${idx}`;
      map[key] = true;
    });
    setExpandedClusterKeys(map);
  };

  const collapseAll = () => setExpandedClusterKeys({});

  return {
    statusFilter,
    setStatusFilter,
    directionFilter,
    setDirectionFilter,
    sortOrder,
    setSortOrder,
    filteredClusters,
    expandedClusterKeys,
    setExpandedClusterKeys,
    expandAll,
    collapseAll,
    searchTokens: criteria.tokens,
    availableYears,
  };
};
