// utils/classificationHelpers.ts

import type { ExtendedCluster, RemarksJSON } from '../api/api';

/**
 * Standard Indian Rupee (INR) currency formatter.
 */
export const inrFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
});

export const formatShortDate = (dateStr?: string | null): string => {
  if (!dateStr) return '';
  const clean = String(dateStr).trim();

  const monthNames = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ];

  // 1. Match DD-MM-YYYY or DD/MM/YYYY
  const ddmmyyyyMatch = clean.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$/);
  if (ddmmyyyyMatch) {
    const day = ddmmyyyyMatch[1].padStart(2, '0');
    const monthIdx = parseInt(ddmmyyyyMatch[2], 10) - 1;
    const year = ddmmyyyyMatch[3];
    if (monthIdx >= 0 && monthIdx < 12) {
      return `${day} ${monthNames[monthIdx]} ${year}`;
    }
  }

  // 2. Match YYYY-MM-DD
  const yyyymmddMatch = clean.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/);
  if (yyyymmddMatch) {
    const year = yyyymmddMatch[1];
    const monthIdx = parseInt(yyyymmddMatch[2], 10) - 1;
    const day = yyyymmddMatch[3].padStart(2, '0');
    if (monthIdx >= 0 && monthIdx < 12) {
      return `${day} ${monthNames[monthIdx]} ${year}`;
    }
  }

  // 3. Fallback standard Date parsing
  const d = new Date(clean);
  if (!isNaN(d.getTime())) {
    const day = String(d.getDate()).padStart(2, '0');
    const month = monthNames[d.getMonth()];
    const year = d.getFullYear();
    return `${day} ${month} ${year}`;
  }

  return clean;
};

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
 * Resolves narrative text safely from strings or complex remarks objects.
 * Guarantees a clean, human-readable string without returning "[object Object]".
 */
export const resolveCandidateNarration = (
  remarks: unknown,
  fallbackNarration?: string
): string => {
  if (typeof remarks === 'object' && remarks !== null) {
    const obj = remarks as Record<string, any>;
    const candidate =
      obj.display_text ||
      obj.narration ||
      obj.payee ||
      obj.target_account_name ||
      obj.account_name;
    if (typeof candidate === 'string' && candidate.trim()) {
      return candidate.trim();
    }
    try {
      return JSON.stringify(remarks);
    } catch {
      return fallbackNarration || 'No narration details';
    }
  }

  if (typeof remarks === 'string' && remarks.trim()) {
    try {
      const parsed = JSON.parse(remarks);
      if (typeof parsed === 'object' && parsed !== null) {
        return (
          parsed.display_text ||
          parsed.narration ||
          parsed.payee ||
          parsed.target_account_name ||
          remarks
        );
      }
    } catch {
      return remarks.trim();
    }
    return remarks.trim();
  }

  return fallbackNarration || 'No narration details';
};

/**
 * Normalizes any date representation (DD-MM-YYYY, DD/MM/YYYY, ISO, timestamps)
 * to standard HTML5 input & backend format (YYYY-MM-DD).
 */
export const toIsoDateString = (
  dateVal?: string | number | Date | null
): string => {
  if (!dateVal) return new Date().toISOString().split('T')[0];

  if (dateVal instanceof Date) {
    return isNaN(dateVal.getTime())
      ? new Date().toISOString().split('T')[0]
      : dateVal.toISOString().split('T')[0];
  }

  const cleaned = String(dateVal).trim();

  // Matches DD-MM-YYYY or DD/MM/YYYY
  if (/^\d{2}[-/]\d{2}[-/]\d{4}$/.test(cleaned)) {
    const parts = cleaned.split(/[-/]/);
    return `${parts[2]}-${parts[1]}-${parts[0]}`;
  }

  // Matches YYYY-MM-DD
  if (/^\d{4}-\d{2}-\d{2}$/.test(cleaned)) {
    return cleaned;
  }

  // ISO timestamps with T or time component
  if (cleaned.includes('T')) {
    return cleaned.split('T')[0];
  }

  return cleaned;
};

/**
 * Cleans vendor names and search keywords by removing corporate suffixes and noise words.
 * e.g., "Kalyan Jewels" -> "KALYAN", "Bhima Jewellers and Diamonds" -> "BHIMA"
 */
export const cleanVendorKeyword = (rawKeyword?: string | null): string => {
  if (!rawKeyword) return '';

  return String(rawKeyword)
    .replace(/[\[\]]/g, ' ')
    .replace(
      /\b(Jewels|Jewellers|Jewellery|Diamonds?|India|Limited|Limit|Pvt|Ltd|Stores?|Gold|Coins?|Bank|Enterprises?)\b/gi,
      ' '
    )
    .replace(/\s+/g, ' ')
    .trim();
};

/**
 * Extracts the primary vendor search token from a subledger asset node.
 * Checks vendor name, bracket tokens [e.g. [BHIMA]], and cleaned asset name.
 */
export const extractVendorTokenFromNode = (node: any): string => {
  if (!node) return '';

  const explicitVendor =
    node.vendor_name ||
    node.vendor_detail?.name ||
    (typeof node.vendor === 'string' ? node.vendor : '');

  if (explicitVendor) {
    const cleaned = cleanVendorKeyword(explicitVendor);
    if (cleaned.length >= 2) return cleaned;
  }

  if (node.name) {
    const bracketMatch = String(node.name).match(/\[(.*?)\]/);
    if (bracketMatch && bracketMatch[1].trim().length > 2) {
      return cleanVendorKeyword(bracketMatch[1].trim());
    }

    const cleanedName = String(node.name)
      .replace(/^(FD#?|AST-|SBI FD|Asset|GOLD|Coins)\s*/i, '')
      .trim();

    const cleaned = cleanVendorKeyword(cleanedName);
    if (cleaned.length >= 2) return cleaned;
  }

  return '';
};

/**
 * Normalizes strings for space and punctuation-insensitive matching.
 * Strips all spaces, underscores, hyphens, slashes, and special characters.
 * e.g., 'PRAVEE N P' -> 'PRAVEENP'
 */
export const normalizeStr = (str: string): string => {
  if (!str) return '';
  return String(str)
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '');
};

/**
 * Splits text into highlighted matched chunks and plain chunks for safe <mark> rendering.
 */
export const highlightKeywords = (
  text: string,
  searchKeywords?: string
): Array<{ text: string; isMatch: boolean }> => {
  if (!text) return [];
  if (!searchKeywords || !searchKeywords.trim()) {
    return [{ text, isMatch: false }];
  }

  const tokens = searchKeywords
    .split(',')
    .map((k) => cleanVendorKeyword(k))
    .filter((k) => k.length >= 2);

  if (tokens.length === 0) {
    return [{ text, isMatch: false }];
  }

  const escapedTokens = tokens.map((t) =>
    t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  );
  const regex = new RegExp(`(${escapedTokens.join('|')})`, 'gi');
  const parts = text.split(regex);

  return parts.map((part) => ({
    text: part,
    isMatch: regex.test(part),
  }));
};

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
 * High-speed normalized field matcher for individual transaction items.
 */
const matchItemFields = (
  item: any,
  rawSearchStr: string,
  normSearchStr: string
): boolean => {
  const rawLower = rawSearchStr.toLowerCase();

  // 1. Raw exact substring checks
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

  // 2. Normalized fallback pass
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

      // Scenario 1: Hashtag Search
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

      // Scenario 2: Smart Normalized Text Search
      const matchesPatternTag =
        (c.pattern && normalizeStr(c.pattern).includes(normQuery)) ||
        (c.resolved_category &&
          normalizeStr(c.resolved_category).includes(normQuery)) ||
        (c.category && normalizeStr(c.category).includes(normQuery));

      if (matchesPatternTag) return cluster;

      if (cluster.items && cluster.items.length > 0) {
        const matchingItems = cluster.items.filter((item) =>
          matchItemFields(item, rawQuery, normQuery)
        );
        if (matchingItems.length > 0) {
          return { ...cluster, items: matchingItems };
        }
      }

      const matchesSampleDesc = cluster.sample_descriptions?.some((desc) =>
        normalizeStr(desc).includes(normQuery)
      );
      if (matchesSampleDesc) return cluster;

      return null;
    })
    .filter((c): c is ExtendedCluster => c !== null);
};

/**
 * Utility function to extract clean payee name from raw UPI strings.
 */
export const extractCleanPayee = (rawNarration: string): string => {
  if (!rawNarration) return '';

  const parts = rawNarration.split('/');
  if (parts.length >= 4 && parts[0].trim().toUpperCase() === 'UPI') {
    let candidate = parts[3].trim();
    candidate = candidate.replace(/NO REMARKS?/i, '').trim();
    if (candidate) return candidate;
  }

  return rawNarration;
};

/**
 * Extracts optional remark notes from standard UPI narration structures.
 */
export const extractUpiRemark = (rawNarration: string): string | null => {
  if (!rawNarration) return null;

  const parts = rawNarration.split('/');
  if (parts.length >= 5 && parts[0].trim().toUpperCase() === 'UPI') {
    const rawRemark = parts[4].trim().toUpperCase();

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
