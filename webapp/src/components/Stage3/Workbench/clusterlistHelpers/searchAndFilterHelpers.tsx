// webapp/src/components/Stage3/Workbench/clusterlistHelpers/searchAndFilterHelpers.tsx
import React from 'react';

export type StatusFilterType = 'all' | 'unmapped' | 'mapped' | 'contra';
export type DirectionFilterType = 'all' | 'outflow' | 'inflow';
export type SortOrderType = 'amount_desc' | 'count_desc' | 'date_desc' | 'name_asc';

export interface ParsedFilterCriteria {
  tokens: string[];
  minAmount?: number;
  maxAmount?: number;
  targetYear?: string;
  quarter?: 'Q1' | 'Q2' | 'Q3' | 'Q4';
  fromBank?: string;
  toBank?: string;
}

/**
 * 🧠 Intelligent Client-Side Query Parser
 * Handles: >50000, <1000, 500..2000, 2026, Q1..Q4, from:SIB to:NRO, etc.
 */
export function parseAdvancedSearchQuery(query: string): ParsedFilterCriteria {
  const raw = (query || '').trim();
  if (!raw) return { tokens: [] };

  const criteria: ParsedFilterCriteria = { tokens: [] };
  const words = raw.split(/\s+/).filter(Boolean);

  words.forEach((word) => {
    const cleanWord = word.replace(/,/g, '');
    const lower = cleanWord.toLowerCase();

    // 1. Amount range: e.g. 5000..20000
    if (/^\d+(\.\d+)?\.\.\d+(\.\d+)?$/.test(cleanWord)) {
      const [minStr, maxStr] = cleanWord.split('..');
      criteria.minAmount = parseFloat(minStr);
      criteria.maxAmount = parseFloat(maxStr);
      return;
    }

    // 2. Amount comparative: >50000, >=50000, <1000, <=1000
    const amtGte = cleanWord.match(/^(?:>=|>)([0-9]+(?:\.[0-9]+)?)$/);
    if (amtGte) {
      criteria.minAmount = parseFloat(amtGte[1]);
      return;
    }
    const amtLte = cleanWord.match(/^(?:<=|<)([0-9]+(?:\.[0-9]+)?)$/);
    if (amtLte) {
      criteria.maxAmount = parseFloat(amtLte[1]);
      return;
    }

    // 3. Bank routing tokens
    if (lower.startsWith('from:')) {
      criteria.fromBank = lower.replace('from:', '');
      return;
    }
    if (lower.startsWith('to:')) {
      criteria.toBank = lower.replace('to:', '');
      return;
    }
    if (lower.startsWith('bank:')) {
      criteria.fromBank = lower.replace('bank:', '');
      return;
    }

    // 4. Fiscal Quarter tokens (Indian Financial Year: Q1 = Apr-Jun, Q2 = Jul-Sep, Q3 = Oct-Dec, Q4 = Jan-Mar)
    if (/^q[1-4]$/i.test(cleanWord)) {
      criteria.quarter = cleanWord.toUpperCase() as 'Q1' | 'Q2' | 'Q3' | 'Q4';
      return;
    }

    // 5. Year token
    if (lower.startsWith('year:')) {
      criteria.targetYear = lower.replace('year:', '');
      return;
    }
    if (/^(202[0-9])$/.test(cleanWord)) {
      criteria.targetYear = cleanWord;
      return;
    }

    // Free text tokens (ignore standalone math characters)
    if (!['>', '<', '>=', '<=', '=', '..'].includes(cleanWord)) {
      criteria.tokens.push(lower);
    }
  });

  return criteria;
}

/**
 * Checks if a transaction date falls into an Indian Financial Year quarter
 * Q1: Apr-Jun (04-06)
 * Q2: Jul-Sep (07-09)
 * Q3: Oct-Dec (10-12)
 * Q4: Jan-Mar (01-03)
 */
// function matchesQuarter(dateStr: string, quarter: 'Q1' | 'Q2' | 'Q3' | 'Q4'): boolean {
//   if (!dateStr) return false;
//   const match = dateStr.match(/-(\d{2})-/);
//   if (!match) return false;
//   const month = parseInt(match[1], 10);

//   switch (quarter) {
//     case 'Q1': return month >= 4 && month <= 6;
//     case 'Q2': return month >= 7 && month <= 9;
//     case 'Q3': return month >= 10 && month <= 12;
//     case 'Q4': return month >= 1 && month <= 3;
//     default: return true;
//   }
// }

/**
 * ⚡ Evaluates whether a line item strictly matches all criteria
 */
export function evaluateItemMatch(
  item: any,
  criteria: ParsedFilterCriteria,
  statusFilter: StatusFilterType = 'all',
  directionFilter: DirectionFilterType = 'all'
): boolean {
  if (!item) return false;

  // 1. Direction Filter
  const dir = (item.direction || item.vector_type || item.entry_type || '').toUpperCase();
  const isOut =
    ['OUTFLOW', 'DEBIT', 'DR'].includes(dir) ||
    (item.debit != null && Number(item.debit) > 0) ||
    (item.amount ?? 0) < 0;

  if (directionFilter === 'outflow' && !isOut) return false;
  if (directionFilter === 'inflow' && isOut) return false;

  // 2. Status Filter
  const isMapped = Boolean(item.is_mapped || item.subledger_mapping || item.mapping_id || item.asset_id);
  if (statusFilter === 'unmapped' && isMapped) return false;
  if (statusFilter === 'mapped' && !isMapped) return false;
  if (statusFilter === 'contra') {
    const isContra = Boolean(item.contra_meta?.is_self_transfer);
    if (!isContra) return false;
  }

  // 3. Amount Filter Range
  const rawAmt = Math.abs(Number(item.amount ?? item.debit ?? item.credit ?? 0));
  if (criteria.minAmount != null && rawAmt < criteria.minAmount) return false;
  if (criteria.maxAmount != null && rawAmt > criteria.maxAmount) return false;

  // 4. Year & Quarter Filter
  if (item.transaction_date) {
    const dStr = String(item.transaction_date);
    if (criteria.targetYear && !criteria.quarter && !dStr.startsWith(criteria.targetYear)) {
      return false;
    }
    if (criteria.quarter && !matchesFiscalQuarter(dStr, criteria.targetYear, criteria.quarter)) {
      return false;
    }
  }

  // 5. From-Bank & To-Bank Routing
  const contra = item.contra_meta;
  if (criteria.fromBank) {
    const fromStr = (contra?.from_account_name || item.bank_name || item.remarks?.bank_name || '').toLowerCase();
    if (!fromStr.includes(criteria.fromBank)) return false;
  }
  if (criteria.toBank) {
    const toStr = (contra?.to_account_name || '').toLowerCase();
    if (!toStr.includes(criteria.toBank)) return false;
  }

  // 6. Free-text tokens matching
  if (criteria.tokens.length > 0) {
    const fullSearchHaystack = [
      item.narration,
      item.raw_narration,
      item.universal_narration,
      item.display_payee,
      item.display_text,
      item.remarks?.payee,
      item.remarks?.upi_ref,
      item.remarks?.bank_name,
      item.bank_name,
      item.asset_code,
      item.subledger_mapping?.asset_code,
      String(rawAmt),
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();

    const matchesAllTokens = criteria.tokens.every((token) => fullSearchHaystack.includes(token));
    if (!matchesAllTokens) return false;
  }

  return true;
}

/**
 * 🎨 Renders highlighted keywords with amber marks
 */
export function renderSearchHighlightedText(text: any, searchTokens: string[] = []): React.ReactNode {
  const str = String(text ?? '');
  if (!str || !Array.isArray(searchTokens) || searchTokens.length === 0) {
    return str;
  }

  const validTokens = searchTokens
    .map((t) => (typeof t === 'string' ? t.trim() : ''))
    .filter((t) => t.length > 0)
    .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));

  if (validTokens.length === 0) return str;

  try {
    const regex = new RegExp(`(${validTokens.join('|')})`, 'gi');
    const parts = str.split(regex);

    return (
      <>
        {parts.map((part, i) =>
          regex.test(part) ? (
            <mark key={i} className="bg-amber-500/30 text-amber-200 rounded px-0.5 font-bold">
              {part}
            </mark>
          ) : (
            part
          )
        )}
      </>
    );
  } catch {
    return str;
  }
}

/**
 * 📋 Clipboard Copy Utility
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
    const textArea = document.createElement('textarea');
    textArea.value = text;
    document.body.appendChild(textArea);
    textArea.select();
    document.execCommand('copy');
    document.body.removeChild(textArea);
    return true;
  } catch {
    return false;
  }
}

/**
 * 📅 Evaluates Indian FY Quarter matches
 * FY 2024:
 * - Q1: 01-Apr-2024 to 30-Jun-2024 (04-06)
 * - Q2: 01-Jul-2024 to 30-Sep-2024 (07-09)
 * - Q3: 01-Oct-2024 to 31-Dec-2024 (10-12)
 * - Q4: 01-Jan-2025 to 31-Mar-2025 (01-03)
 */
export function matchesFiscalQuarter(
  dateStr: string,
  targetYear?: string,
  quarter?: 'Q1' | 'Q2' | 'Q3' | 'Q4'
): boolean {
  if (!dateStr || !quarter) return true;

  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return false;

  const month = d.getMonth() + 1; // 1 - 12
  const calYear = d.getFullYear();

  // If a specific FY is selected
  if (targetYear) {
    const fyStartYear = parseInt(targetYear, 10);
    switch (quarter) {
      case 'Q1':
        return calYear === fyStartYear && month >= 4 && month <= 6;
      case 'Q2':
        return calYear === fyStartYear && month >= 7 && month <= 9;
      case 'Q3':
        return calYear === fyStartYear && month >= 10 && month <= 12;
      case 'Q4':
        return calYear === fyStartYear + 1 && month >= 1 && month <= 3;
    }
  }

  // If only a quarter is picked without an explicit FY
  switch (quarter) {
    case 'Q1': return month >= 4 && month <= 6;
    case 'Q2': return month >= 7 && month <= 9;
    case 'Q3': return month >= 10 && month <= 12;
    case 'Q4': return month >= 1 && month <= 3;
    default: return true;
  }
}

/**
 * 📊 Converts selected transaction rows into a clipboard-ready TSV format (paste directly into Excel/Sheets)
 */
export function generateTSVFromItems(items: any[]): string {
  const headers = ['Date', 'Payee / Narration', 'Direction', 'Amount', 'Bank', 'Ref', 'Mapped Folio'];
  const rows = items.map((it) => {
    const isOut =
      ['OUTFLOW', 'DEBIT', 'DR'].includes((it.direction || it.vector_type || '').toUpperCase()) ||
      (it.debit != null && Number(it.debit) > 0) ||
      (it.amount ?? 0) < 0;
    const amountVal = Math.abs(Number(it.amount ?? it.debit ?? it.credit ?? 0));
    const folio = it.asset_code || it.subledger_mapping?.asset_code || 'UNMAPPED';
    const narration = (it.universal_narration || it.raw_narration || it.narration || '').replace(/[\t\n\r]/g, ' ');
    const bank = it.bank_name || it.remarks?.bank_name || '';
    const ref = it.remarks?.upi_ref || it.remarks?.reference || '';

    return [
      it.transaction_date || '',
      narration,
      isOut ? 'DEBIT' : 'CREDIT',
      amountVal,
      bank,
      ref,
      folio,
    ].join('\t');
  });

  return [headers.join('\t'), ...rows].join('\n');
}