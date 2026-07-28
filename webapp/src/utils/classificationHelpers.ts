// utils/classificationHelpers.ts

import type { ExtendedCluster, RemarksJSON } from '../api';

/**
 * Parses raw JSON remarks safely with string fallback.
 */
export const parseRemarks = (remarks: unknown): RemarksJSON => {
  if (!remarks) return {};
  if (typeof remarks === 'object' && remarks !== null) {
    return remarks as RemarksJSON;
  }
  if (typeof remarks === 'string') {
    try {
      return JSON.parse(remarks);
    } catch {
      return { display_text: remarks };
    }
  }
  return {};
};

/**
 * Standard Indian Rupee (INR) currency formatter.
 */
export const inrFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
});

/**
 * Calculates batch summary totals for checked/selected transactions.
 */
export const calculateSelectedMetrics = (
  clusters: ExtendedCluster[],
  selectedTxnIds: string[]
) => {
  let totalTxns = 0;
  let totalAmount = 0;

  clusters.forEach((cluster) => {
    if (cluster.items && cluster.items.length > 0) {
      cluster.items.forEach((item) => {
        if (selectedTxnIds.includes(item.id)) {
          totalTxns += 1;
          totalAmount += item.amount || 0;
        }
      });
    } else {
      const selectedInCluster = (cluster.transaction_ids || []).filter((id) =>
        selectedTxnIds.includes(id)
      );
      if (selectedInCluster.length > 0) {
        totalTxns += selectedInCluster.length;
        const ratio = selectedInCluster.length / (cluster.count || 1);
        totalAmount += (cluster.total_amount || 0) * ratio;
      }
    }
  });

  return { totalTxns, totalAmount, allTxnIds: selectedTxnIds };
};

/**
 * High-speed field matcher for individual transaction items.
 */
const matchItemFields = (item: any, searchStr: string): boolean => {
  // Fast raw string checks first before parsing JSON remarks
  if (item.narration && item.narration.toLowerCase().includes(searchStr))
    return true;
  if (item.debit && String(item.debit).includes(searchStr)) return true;
  if (item.credit && String(item.credit).includes(searchStr)) return true;
  if (item.amount && String(item.amount).includes(searchStr)) return true;
  if (item.transaction_date && item.transaction_date.includes(searchStr))
    return true;

  // Inspect structured remarks fields (payee, display text, UPI reference)
  const remarks = parseRemarks(item.remarks);
  if (remarks.payee && remarks.payee.toLowerCase().includes(searchStr))
    return true;
  if (
    remarks.display_text &&
    remarks.display_text.toLowerCase().includes(searchStr)
  )
    return true;
  if (remarks.upi_ref && remarks.upi_ref.toLowerCase().includes(searchStr))
    return true;

  return false;
};

/**
 * Two-tiered smart search filter for workbench clusters and individual item rows.
 */
export const filterClustersByQuery = (
  clusters: ExtendedCluster[],
  searchQuery: string
): ExtendedCluster[] => {
  if (!searchQuery || !searchQuery.trim()) return clusters;

  const rawQuery = searchQuery.trim().toLowerCase();

  return clusters
    .map((cluster) => {
      const c = cluster as any;

      // -------------------------------------------------------------
      // Scenario 1: Hashtag Search (e.g., "#Hardware" or "#Hardware 500")
      // -------------------------------------------------------------
      if (rawQuery.startsWith('#')) {
        const tagContent = rawQuery.slice(1).trim();
        if (!tagContent) return cluster;

        const spaceIndex = tagContent.indexOf(' ');
        let patternQuery = tagContent;
        let textQuery = '';

        if (spaceIndex !== -1) {
          patternQuery = tagContent.slice(0, spaceIndex).trim();
          textQuery = tagContent.slice(spaceIndex + 1).trim();
        }

        const matchesTag =
          (c.pattern && c.pattern.toLowerCase().includes(patternQuery)) ||
          (c.resolved_category &&
            c.resolved_category.toLowerCase().includes(patternQuery)) ||
          (c.category && c.category.toLowerCase().includes(patternQuery)) ||
          (c.resolved_subcategory &&
            c.resolved_subcategory.toLowerCase().includes(patternQuery)) ||
          (c.subcategory && c.subcategory.toLowerCase().includes(patternQuery));

        if (!matchesTag) return null;

        if (textQuery && cluster.items) {
          const matchingItems = cluster.items.filter((item) =>
            matchItemFields(item, textQuery)
          );
          if (matchingItems.length === 0) return null;
          return { ...cluster, items: matchingItems };
        }

        return cluster;
      }

      // -------------------------------------------------------------
      // Scenario 2: Direct Text Search across Tags, Items, & Sample Descriptions
      // -------------------------------------------------------------
      const matchesPatternTag =
        (c.pattern && c.pattern.toLowerCase().includes(rawQuery)) ||
        (c.resolved_category &&
          c.resolved_category.toLowerCase().includes(rawQuery)) ||
        (c.category && c.category.toLowerCase().includes(rawQuery));

      if (matchesPatternTag) return cluster;

      if (cluster.items && cluster.items.length > 0) {
        const matchingItems = cluster.items.filter((item) =>
          matchItemFields(item, rawQuery)
        );
        if (matchingItems.length > 0) {
          return { ...cluster, items: matchingItems };
        }
      }

      const matchesSampleDesc = cluster.sample_descriptions?.some((desc) =>
        desc.toLowerCase().includes(rawQuery)
      );
      if (matchesSampleDesc) return cluster;

      return null;
    })
    .filter((c): c is ExtendedCluster => c !== null);
};
