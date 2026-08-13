// utils/classificationHelpers.ts

import type { ExtendedCluster, RemarksJSON } from '../api/api';

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
 * Normalizes strings for space and punctuation-insensitive matching.
 * Strips all spaces, underscores, hyphens, slashes, and special characters.
 * e.g., 'PRAVEE N P' -> 'PRAVEENP'
 *       'B_AIJU'     -> 'BAIJU'
 */
export const normalizeStr = (str: string): string => {
  if (!str) return '';
  return String(str)
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '');
};

/**
 * High-speed normalized field matcher for individual transaction items.
 * Matches even when names contain random bank spaces or mangled tokens.
 */
const matchItemFields = (
  item: any,
  rawSearchStr: string,
  normSearchStr: string
): boolean => {
  const rawLower = rawSearchStr.toLowerCase();

  // 1. Raw exact substring checks (Fast pass for numbers, dates, exact words)
  if (item.narration && item.narration.toLowerCase().includes(rawLower))
    return true;
  if (item.debit && String(item.debit).includes(rawLower)) return true;
  if (item.credit && String(item.credit).includes(rawLower)) return true;
  if (item.amount && String(item.amount).includes(rawLower)) return true;
  if (item.transaction_date && item.transaction_date.includes(rawLower))
    return true;

  const remarks = parseRemarks(item.remarks);
  if (remarks.payee && remarks.payee.toLowerCase().includes(rawLower))
    return true;
  if (
    remarks.display_text &&
    remarks.display_text.toLowerCase().includes(rawLower)
  )
    return true;
  if (remarks.upi_ref && remarks.upi_ref.toLowerCase().includes(rawLower))
    return true;

  // 2. Normalized fallback pass (Handles mangled names like "PRAVEE N P" vs "praveen")
  if (normSearchStr.length >= 2) {
    if (item.narration && normalizeStr(item.narration).includes(normSearchStr))
      return true;
    if (remarks.payee && normalizeStr(remarks.payee).includes(normSearchStr))
      return true;
    if (
      remarks.display_text &&
      normalizeStr(remarks.display_text).includes(normSearchStr)
    )
      return true;
  }

  return false;
};

/**
 * Two-tiered smart normalized search filter for workbench clusters and individual item rows.
 */
export const filterClustersByQuery = (
  clusters: ExtendedCluster[],
  searchQuery: string
): ExtendedCluster[] => {
  if (!searchQuery || !searchQuery.trim()) return clusters;

  const rawQuery = searchQuery.trim().toLowerCase();
  const normQuery = normalizeStr(searchQuery);

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

        const normPatternQuery = normalizeStr(patternQuery);

        const matchesTag =
          (c.pattern && normalizeStr(c.pattern).includes(normPatternQuery)) ||
          (c.resolved_category &&
            normalizeStr(c.resolved_category).includes(normPatternQuery)) ||
          (c.category && normalizeStr(c.category).includes(normPatternQuery)) ||
          (c.resolved_subcategory &&
            normalizeStr(c.resolved_subcategory).includes(normPatternQuery)) ||
          (c.subcategory &&
            normalizeStr(c.subcategory).includes(normPatternQuery));

        if (!matchesTag) return null;

        if (textQuery && cluster.items) {
          const normTextQuery = normalizeStr(textQuery);
          const matchingItems = cluster.items.filter((item) =>
            matchItemFields(item, textQuery, normTextQuery)
          );
          if (matchingItems.length === 0) return null;
          return { ...cluster, items: matchingItems };
        }

        return cluster;
      }

      // -------------------------------------------------------------
      // Scenario 2: Smart Normalized Text Search across Tags, Items, & Samples
      // -------------------------------------------------------------

      // Check cluster tag / category matching (Normalized comparison)
      const matchesPatternTag =
        (c.pattern && normalizeStr(c.pattern).includes(normQuery)) ||
        (c.resolved_category &&
          normalizeStr(c.resolved_category).includes(normQuery)) ||
        (c.category && normalizeStr(c.category).includes(normQuery));

      if (matchesPatternTag) return cluster;

      // Check line item fields (Narration, Amounts, Remarks, Payee)
      if (cluster.items && cluster.items.length > 0) {
        const matchingItems = cluster.items.filter((item) =>
          matchItemFields(item, rawQuery, normQuery)
        );
        if (matchingItems.length > 0) {
          return { ...cluster, items: matchingItems };
        }
      }

      // Check sample descriptions fallback
      const matchesSampleDesc = cluster.sample_descriptions?.some((desc) =>
        normalizeStr(desc).includes(normQuery)
      );
      if (matchesSampleDesc) return cluster;

      return null;
    })
    .filter((c): c is ExtendedCluster => c !== null);
};

// export const extractCleanPayee = (rawNarration: string): string => {
//   if (!rawNarration) return '';

//   // Handle standard UPI format: UPI/GATEWAY/RRN/PAYEE_NAME/...
//   const parts = rawNarration.split('/');
//   if (parts.length >= 4 && parts[0].toUpperCase() === 'UPI') {
//     let candidate = parts[3].trim();
//     // Remove "NO REMARKS" or "NO REM" if attached
//     candidate = candidate.replace(/NO REMARKS?/i, '').trim();
//     return candidate;
//   }

//   return rawNarration;
// };
// 💡 Utility function to extract clean payee name from raw UPI strings
export const extractCleanPayee = (rawNarration: string): string => {
  if (!rawNarration) return '';

  // Parse standard UPI format: UPI/GATEWAY/RRN/PAYEE_NAME/...
  const parts = rawNarration.split('/');
  if (parts.length >= 4 && parts[0].trim().toUpperCase() === 'UPI') {
    let candidate = parts[3].trim();
    // Strip trailing or attached "NO REMARKS" noise
    candidate = candidate.replace(/NO REMARKS?/i, '').trim();
    if (candidate) return candidate;
  }

  return rawNarration;
};

export const extractUpiRemark = (rawNarration: string): string | null => {
  if (!rawNarration) return null;

  const parts = rawNarration.split('/');
  // Standard UPI format: UPI / GATEWAY / RRN / PAYEE / REMARK / ...
  if (parts.length >= 5 && parts[0].trim().toUpperCase() === 'UPI') {
    const rawRemark = parts[4].trim().toUpperCase();

    // Ignore system noise/empty remarks
    const noiseWords = [
      'NO REMARK',
      'NO REMARKS',
      'NA',
      'NONE',
      'UPI',
      'CIG',
      'PAYMENT',
    ];
    if (rawRemark && !noiseWords.includes(rawRemark) && rawRemark.length > 1) {
      return rawRemark;
    }
  }

  return null;
};
