// src/components/ui/data-table/columns.ts
import React from 'react';

export interface ColumnConfig {
  key: string;
  label: string | React.ReactNode;
  width: string;
  align: 'left' | 'center' | 'right';
  textColor?: string;
  fallbackColor?: string;
  isCurrency?: boolean;
  headerClass?: string;
  renderFooter?: (data: any[]) => string | number;
  renderCell?: (row: any, meta?: any) => React.ReactNode;
}

export interface SmartTermDepositMeta {
  td_account_number?: string;
  td_open_date?: string;
  td_renewal_date?: string;
  td_principal_amount?: string;
  td_tenure?: string;
  td_maturity_date?: string;
  td_total_interest?: string;
  td_tds_deducted?: string;
  [key: string]: any;
}

export interface LiveStreamPayloadItem {
  id: string;
  source: 'IOS_SMS' | 'GMAIL_API' | 'MERGED_STREAM' | 'POWER_AUTOMATE' | string;
  sender: string;
  subject?: string | null;
  raw_body?: string | null;
  amount: string | number | null;
  balance: string | number | null;
  txn_date?: string | null;
  account_last4: string | null;
  account_display_name?: string | null;
  bank_name: string | null;
  upi_ref: string | null;
  status: string;
  created_at: string;
  full_narration: string | null;
  merchant?: string | null;
  smart_meta?: SmartTermDepositMeta | null;
  direction?: 'DEBIT' | 'CREDIT' | string;
  payment_protocol?: string;
  amount_label?: string;
  clean_beneficiary?: string;
}

export const LEDGER_COLUMNS: ColumnConfig[] = [
  { key: 'post_date', label: 'Txn Date', width: '9%', align: 'left' },
  {
    key: 'value_date',
    label: 'Val Date',
    width: '9%',
    align: 'left',
    textColor: 'text-orange-400/80',
    headerClass: 'text-orange-400',
  },
  {
    key: 'narration_description',
    label: 'Narration Description',
    width: '35%',
    align: 'left',
  },
  {
    key: 'tran_type',
    label: 'Type',
    width: '6%',
    align: 'center',
    textColor: 'text-indigo-300',
    headerClass: 'text-indigo-400',
  },
  {
    key: 'chq_ref',
    label: 'Chq/Ref',
    width: '9%',
    align: 'left',
    textColor: 'text-sky-400',
    headerClass: 'text-sky-400',
  },
  {
    key: 'debit',
    label: 'Debit (-)',
    width: '9%',
    align: 'right',
    isCurrency: true,
    fallbackColor: 'text-red-400',
    headerClass: 'text-red-400',
  },
  {
    key: 'credit',
    label: 'Credit (+)',
    width: '9%',
    align: 'right',
    isCurrency: true,
    fallbackColor: 'text-emerald-400',
    headerClass: 'text-emerald-400',
  },
  {
    key: 'balance',
    label: 'Balance',
    width: '9%',
    align: 'right',
    isCurrency: true,
    textColor: 'text-cyan-400/90',
    headerClass: 'text-cyan-400',
  },
  { key: 'status', label: 'Status', width: '5%', align: 'center' },
];

export const ATTACHMENT_INBOX_COLUMNS: ColumnConfig[] = [
  {
    key: 'received_date',
    label: 'Received',
    width: '10%',
    align: 'left',
    renderCell: (row: any) => (
      <span className="font-mono text-[11px] text-zinc-400 whitespace-nowrap">
        {row.received_date ? String(row.received_date).slice(0, 10) : '—'}
      </span>
    ),
  },
  {
    key: 'bank_name',
    label: 'Bank',
    width: '15%',
    align: 'left',
    renderCell: (row: any) => (
      <span className="font-bold text-zinc-200 whitespace-nowrap text-[11px]">
        {row.bank_name || 'Generic Bank'}
      </span>
    ),
  },
  {
    key: 'account_hint',
    label: 'Account',
    width: '10%',
    align: 'left',
    renderCell: (row: any) => (
      <span className="font-bold text-emerald-400 font-mono whitespace-nowrap text-[11px]">
        •••• {row.account_hint || '----'}
      </span>
    ),
  },
  {
    key: 'filename',
    label: 'File Name',
    width: '24%',
    align: 'left',
    renderCell: (row: any) => (
      <span className="text-zinc-300 font-mono text-[11px] truncate max-w-xs block" title={row.filename}>
        {row.filename}
      </span>
    ),
  },
  {
    key: 'period',
    label: 'Statement Period',
    width: '21%',
    align: 'left',
    renderCell: (row: any) => {
      const formatDate = (dateStr: string | null) => {
        if (!dateStr) return null;
        try {
          const d = new Date(dateStr);
          if (isNaN(d.getTime())) return dateStr.slice(0, 10);
          return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
        } catch {
          return dateStr.slice(0, 10);
        }
      };

      const start = formatDate(row.period_start);
      const end = formatDate(row.period_end);

      if (start && end) {
        return (
          <div className="flex items-center gap-1.5 font-mono text-[10px]">
            <span className="text-emerald-400 font-medium">{start}</span>
            <span className="text-zinc-500">→</span>
            <span className="text-emerald-400 font-medium">{end}</span>
          </div>
        );
      }
      return <span className="text-zinc-600 italic text-[10px]">Auto-detect on preview</span>;
    },
  },
  {
    key: 'status',
    label: 'Status',
    width: '10%',
    align: 'center',
    renderCell: (row: any) => (
      <span className="px-1.5 py-0.5 rounded text-[9px] font-bold font-mono bg-zinc-800 text-zinc-400 border border-zinc-700">
        {row.status}
      </span>
    ),
  },
  {
    key: 'actions',
    label: 'Action',
    width: '10%',
    align: 'right',
    renderCell: (row: any, meta: any) => {
      const isActive = meta?.activeItemId === row.id;
      const isLoading = meta?.loading && isActive;

      return (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            meta?.onPreviewItem?.(row.id);
          }}
          disabled={meta?.loading}
          className={`px-2.5 py-1 rounded text-[10px] font-bold transition-all cursor-pointer border font-mono ${
            isActive
              ? 'bg-emerald-500 text-black border-emerald-400 font-extrabold shadow-sm'
              : 'bg-emerald-600/10 hover:bg-emerald-600 text-emerald-400 hover:text-white border-emerald-500/30 hover:border-emerald-500'
          }`}
        >
          {isLoading ? 'Extracting...' : isActive ? '✓ Staged' : 'Preview & Verify'}
        </button>
      );
    },
  },
];

export const LIVE_STREAM_COLUMNS: ColumnConfig[] = [
  {
    key: 'source',
    label: 'SOURCE',
    width: '11%',
    align: 'left',
    renderCell: (row: any) => {
      const isSms = row.source === 'IOS_SMS';
      const isMerged = row.source === 'MERGED_STREAM';
      const badgeStyle = isMerged
        ? 'bg-purple-500/20 text-purple-400 border-purple-500/30'
        : isSms
        ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
        : 'bg-blue-500/20 text-blue-400 border-blue-500/30';
      return (
        <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${badgeStyle}`}>
          {row.source}
        </span>
      );
    },
  },
  {
    key: 'account_and_bank',
    label: 'ACCOUNT & BANK',
    width: '15%',
    align: 'left',
    renderCell: (row: any) => (
      <div className="font-mono text-xs">
        <div className="text-zinc-200 font-bold">{row.bank_name || 'UNKNOWN BANK'}</div>
        <div className="text-zinc-500 text-[11px]">•••• {row.account_last4 || '----'}</div>
      </div>
    ),
  },
  {
    key: 'merchant_narration',
    label: 'MERCHANT / NARRATION',
    width: '24%',
    align: 'left',
    renderCell: (row: any) => (
      <div className="font-mono text-xs max-w-sm truncate" title={row.full_narration || ''}>
        <span className="text-zinc-200">{row.merchant || row.full_narration || 'Direct Payment'}</span>
      </div>
    ),
  },
  {
    key: 'amount',
    label: 'AMOUNT',
    width: '10%',
    align: 'right',
    isCurrency: true,
    renderCell: (row: any) => {
      const amt = parseFloat(String(row.amount || 0));
      return (
        <span className="font-mono font-bold text-xs text-zinc-200">
          ₹{amt.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
        </span>
      );
    },
  },
  {
    key: 'balance',
    label: 'AVAIL. BALANCE',
    width: '10%',
    align: 'right',
    isCurrency: true,
    renderCell: (row: any) => {
      if (!row.balance) return <span className="text-zinc-600 font-mono text-xs">-</span>;
      const bal = parseFloat(String(row.balance));
      return (
        <span className="font-mono text-xs text-emerald-400">
          ₹{bal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
        </span>
      );
    },
  },
  {
    key: 'upi_ref',
    label: 'UPI REF / RRN',
    width: '12%',
    align: 'left',
    renderCell: (row: any) => (
      <span className="font-mono text-xs text-zinc-400 select-all">
        {row.upi_ref || <span className="text-zinc-600">-</span>}
      </span>
    ),
  },
  {
    key: 'status',
    label: 'STATUS',
    width: '8%',
    align: 'center',
    renderCell: (row: any) => {
      const isMatched = row.status === 'MATCHED_2_WAY';
      const isDup = row.status === 'DUPLICATE';
      const badgeStyle = isMatched
        ? 'bg-purple-500/20 text-purple-400 border-purple-500/30'
        : isDup
        ? 'bg-orange-500/20 text-orange-400 border-orange-500/30'
        : 'bg-amber-500/20 text-amber-400 border-amber-500/30';
      return (
        <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${badgeStyle}`}>
          {row.status}
        </span>
      );
    },
  },
  {
    key: 'created_at',
    label: 'TXN / INGEST DATE',
    width: '14%',
    align: 'left',
    renderCell: (row: any) => (
      <div className="font-mono text-[11px] leading-tight flex flex-col">
        <span className={row.txn_date ? 'text-amber-400 font-semibold' : 'text-zinc-400'}>
          {row.txn_date ? `Txn: ${row.txn_date}` : 'Txn: Same Day'}
        </span>
        <span className="text-zinc-600 text-[10px]">
          Ingest: {row.created_at ? new Date(row.created_at).toLocaleDateString('en-GB') : '-'}
        </span>
      </div>
    ),
  },
];


export const STATEMENT_STAGING_COLUMNS: ColumnConfig[] = [
  {
  key: 'select',
  label: '',
  width: '4%',
  align: 'center',
  renderCell: (row: any, meta: any) => {
    const isSelected = meta?.selectedIds?.includes(row.stage_id);
    const isDupe = row.is_duplicate || row.status === 'DUPLICATE';

    return (
      <input
        type="checkbox"
        checked={isSelected}
        // Optional: Disable checkbox if duplicate and not unrecognized
        disabled={isDupe && row.account_hint !== 'UNRECOGNIZED'}
        onChange={(e) => {
          e.stopPropagation();
          meta?.onToggleSelectOne?.(row.stage_id);
        }}
        className="rounded border-zinc-700 bg-zinc-800 text-emerald-500 focus:ring-0 cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
      />
    );
  }
},
  {
    key: 'bank_filename',
    label: 'BANK & FILENAME',
    width: '28%',
    align: 'left',
    renderCell: (row: any, meta: any) => (
      <div className="flex flex-col">
        <div className="flex items-center gap-2">
          <span className="font-bold text-zinc-200 uppercase text-xs">
            {row.bank_name || 'UNKNOWN BANK'}
          </span>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              meta?.onOpenPreview?.(row);
            }}
            className="text-[10px] text-amber-400 hover:text-amber-300 font-mono flex items-center gap-1 cursor-pointer"
          >
            <span>👁️</span> Preview
          </button>
        </div>
        <span className="text-[11px] text-zinc-400 font-mono truncate max-w-sm" title={row.filename}>
          {row.filename}
        </span>
      </div>
    ),
  },
  {
    key: 'account_hint',
    label: 'ACCOUNT HINT',
    width: '16%',
    align: 'left',
    renderCell: (row: any, meta: any) => {
      const selectedAcc = meta?.accountOverrides?.[row.stage_id] || row.account_hint;
      if (row.account_hint && row.account_hint !== 'UNRECOGNIZED') {
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-emerald-950/80 border border-emerald-800 text-emerald-400">
            A/c X{row.account_hint}
          </span>
        );
      }
      return (
        <select
          value={selectedAcc === 'UNRECOGNIZED' ? '' : selectedAcc}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => meta?.onAccountOverrideChange?.(row.stage_id, e.target.value)}
          className="bg-zinc-950 border border-amber-600/80 text-amber-300 text-xs rounded px-2 py-1 focus:outline-none cursor-pointer font-semibold"
        >
          <option value="">Select Account...</option>
          {meta?.accountOptions?.map((opt: any) => (
            <option key={opt.id} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      );
    },
  },
  {
    key: 'period',
    label: 'STATEMENT PERIOD',
    width: '18%',
    align: 'left',
    renderCell: (row: any) => (
      <span className="font-mono text-xs text-zinc-300">
        {row.period_start || '—'} → {row.period_end || '—'}
      </span>
    ),
  },
  {
    key: 'status',
    label: 'INGEST STATUS',
    width: '12%',
    align: 'center',
    renderCell: (row: any) => {
      const isDupe = row.is_duplicate || row.status === 'DUPLICATE' || row.status === 'COMMITTED';
      if (isDupe) {
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-amber-950/80 border border-amber-800/80 text-amber-400 shadow-sm">
            <span>⚠️</span> DUPLICATE
          </span>
        );
      }
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-emerald-950/80 border border-emerald-800/80 text-emerald-400 shadow-sm">
          <span>📥</span> READY
        </span>
      );
    },
  },
  {
    key: 'file_size',
    label: 'SIZE',
    width: '7%',
    align: 'right',
    renderCell: (row: any) => (
      <span className="font-mono text-xs text-zinc-400">
        {row.file_size ? `${Math.round(row.file_size / 1024)} KB` : '—'}
      </span>
    ),
  },
  {
    key: 'received_date',
    label: 'RECEIVED AT',
    width: '11%',
    align: 'left',
    renderCell: (row: any) => (
      <span className="font-mono text-[11px] text-zinc-400">
        {row.received_date || '—'}
      </span>
    ),
  },
  {
    key: 'doc_type',
    label: 'DOC TYPE',
    width: '8%',
    align: 'center',
    renderCell: (row: any) => (
      <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-zinc-900 border border-zinc-800 text-zinc-400 uppercase">
        {row.doc_type || 'STATEMENT'}
      </span>
    ),
  },
];

export const ACCOUNTING_HEADER_COLUMNS: ColumnConfig[] = [
  {
    key: 'sno',
    label: 'SNo',
    width: '8%',
    align: 'left',
    textColor: 'text-zinc-500',
  },
  { key: 'category_type', label: 'Type Tag', width: '12%', align: 'center' },
  {
    key: 'act_category',
    label: 'Core Category',
    width: '15%',
    align: 'left',
    textColor: 'text-zinc-400',
  },
  {
    key: 'act_subcategory',
    label: 'Sub-Category',
    width: '20%',
    align: 'left',
    textColor: 'text-zinc-300',
  },
  {
    key: 'narration_description',
    label: 'Item Label / Rules Match',
    width: '33%',
    align: 'left',
    textColor: 'text-zinc-100',
  },
  { key: 'actions', label: 'CRUD Actions', width: '12%', align: 'center' },
];

export const SELF_TRANSFER_COLUMNS: ColumnConfig[] = [
  {
    key: 'sno',
    label: 'SNo',
    width: '8%',
    align: 'left',
    textColor: 'text-zinc-500',
  },
  {
    key: 'source_account_name',
    label: 'Debit Origin (From)',
    width: '30%',
    align: 'left',
    textColor: 'text-red-400/90',
  },
  {
    key: 'destination_account_name',
    label: 'Credit Target (To)',
    width: '30%',
    align: 'left',
    textColor: 'text-emerald-400/90',
  },
  {
    key: 'narration_description',
    label: 'Routing Instruction',
    width: '20%',
    align: 'left',
  },
  { key: 'actions', label: 'CRUD Actions', width: '12%', align: 'center' },
];

export const BALANCE_SHEET_COLUMNS: ColumnConfig[] = [
  {
    key: 'sno',
    label: 'SNo',
    width: '8%',
    align: 'left',
    textColor: 'text-zinc-500',
  },
  {
    key: 'act_category',
    label: 'Core Group',
    width: '15%',
    align: 'left',
    textColor: 'text-cyan-400',
  },
  {
    key: 'act_subcategory',
    label: 'Line Item Header',
    width: '25%',
    align: 'left',
    textColor: 'text-zinc-200',
  },
  {
    key: 'narration_description',
    label: 'Target Label',
    width: '25%',
    align: 'left',
    textColor: 'text-zinc-100',
  },
  {
    key: 'dashboard_cat',
    label: 'Dashboard Placement',
    width: '15%',
    align: 'center',
  },
  { key: 'actions', label: 'CRUD Actions', width: '12%', align: 'center' },
];

export const BULK_APPROVAL_COLUMNS: ColumnConfig[] = [
  {
    key: 'date',
    label: 'Txn Date',
    width: '10%',
    align: 'left',
    textColor: 'text-zinc-400',
  },
  {
    key: 'narration',
    label: 'Statement Description Reference',
    width: '35%',
    align: 'left',
    textColor: 'text-zinc-100',
  },
  {
    key: 'debit',
    label: 'Debit (DR)',
    width: '10%',
    align: 'right',
    textColor: 'text-amber-500',
  },
  {
    key: 'credit',
    label: 'Credit (CR)',
    width: '10%',
    align: 'right',
    textColor: 'text-emerald-500',
  },
  {
    key: 'category_item',
    label: 'Assigned Header Mapping',
    width: '20%',
    align: 'left',
    textColor: 'text-cyan-400',
  },
  {
    key: 'T1_item',
    label: 'T1',
    width: '20%',
    align: 'left',
    textColor: 'text-cyan-400',
  },
  {
    key: 'T2_item',
    label: 'T2',
    width: '20%',
    align: 'left',
    textColor: 'text-cyan-400',
  },
  {
    key: 'T3_item',
    label: 'T3',
    width: '20%',
    align: 'left',
    textColor: 'text-cyan-400',
  },
  {
    key: 'T4_item',
    label: 'T4',
    width: '20%',
    align: 'left',
    textColor: 'text-cyan-400',
  },
  {
    key: 'rule_code',
    label: 'Rule Linked',
    width: '10%',
    align: 'center',
    textColor: 'text-zinc-400',
  },
  { key: 'actions', label: 'Clearance', width: '5%', align: 'center' },
];

export const UNCATEGORIZED_VAULT_COLUMNS: ColumnConfig[] = [
  {
    key: 'date',
    label: 'Txn Date',
    width: '10%',
    align: 'left',
    textColor: 'text-zinc-400',
  },
  {
    key: 'narration',
    label: 'Statement Description Reference',
    width: '40%',
    align: 'left',
    textColor: 'text-zinc-100',
  },
  {
    key: 'debit',
    label: 'Debit (DR)',
    width: '10%',
    align: 'right',
    textColor: 'text-amber-500',
  },
  {
    key: 'credit',
    label: 'Credit (CR)',
    width: '10%',
    align: 'right',
    textColor: 'text-emerald-500',
  },
  {
    key: 'errors',
    label: 'Failed Validation Gate Footprint',
    width: '20%',
    align: 'left',
    textColor: 'text-red-400 font-mono text-[11px]',
  },
  { key: 'actions', label: 'Manual Allocation', width: '10%', align: 'center' },
];

export const CATEGORY_BREAKDOWN_COLUMNS: ColumnConfig[] = [
  {
    key: 'category',
    label: 'Primary Class',
    width: '15%',
    align: 'left',
    textColor: 'text-zinc-200 font-bold',
  },
  {
    key: 'subcategory',
    label: 'Subcategory',
    width: '22%',
    align: 'left',
    textColor: 'text-zinc-300',
  },
  {
    key: 'transaction_count',
    label: 'Txn Count',
    width: '8%',
    align: 'center',
    textColor: 'text-zinc-400 font-mono text-xs',
  },
  {
    key: 'total_debit',
    label: 'Debit (DR)',
    width: '13%',
    align: 'right',
    isCurrency: true,
    textColor: 'text-amber-400 font-mono text-xs',
  },
  {
    key: 'total_credit',
    label: 'Credit (CR)',
    width: '13%',
    align: 'right',
    isCurrency: true,
    textColor: 'text-emerald-400 font-mono text-xs',
  },
  {
    key: 'net_balance',
    label: 'Net Balance',
    width: '17%',
    align: 'right',
    isCurrency: true,
    textColor: 'text-zinc-100 font-bold font-mono text-xs',
    renderFooter: (data: any[]) => {
      const net = data.reduce((acc, row) => {
        const dr = parseFloat(String(row.total_debit || '0').replace(/,/g, ''));
        const cr = parseFloat(
          String(row.total_credit || '0').replace(/,/g, '')
        );
        return acc + (dr - cr);
      }, 0);

      return net.toLocaleString('en-IN', { minimumFractionDigits: 2 });
    },
  },
  {
    key: 'actions',
    label: 'Actions',
    width: '12%',
    align: 'center',
    renderCell: (row: any, meta?: any) => {
      const subcategory = String(row.subcategory || '').trim();
      const primaryCategory = String(row.category || '')
        .trim()
        .toLowerCase();

      const capableSet: Set<string> = meta?.subledgerCapableSet || new Set();
      const isSubledgerCapable = Array.from(capableSet).some(
        (item) =>
          String(item).trim().toLowerCase() === subcategory.toLowerCase()
      );

      if (!isSubledgerCapable || !subcategory) return null;

      let buttonLabel = '📦 Subledger';
      let colorStyles =
        'bg-teal-950/80 hover:bg-teal-900 border-teal-800/80 text-teal-300';

      if (primaryCategory === 'asset') {
        buttonLabel = '📦 Asset Hub';
        colorStyles =
          'bg-cyan-950/80 hover:bg-cyan-900 border-cyan-800/80 text-cyan-300';
      } else if (primaryCategory === 'expense') {
        buttonLabel = '📊 Subledger';
        colorStyles =
          'bg-rose-950/80 hover:bg-rose-900 border-rose-800/80 text-rose-300';
      } else if (primaryCategory === 'income') {
        buttonLabel = '💰 Subledger';
        colorStyles =
          'bg-emerald-950/80 hover:bg-emerald-900 border-emerald-800/80 text-emerald-300';
      }

      return React.createElement(
        'button',
        {
          type: 'button',
          onClick: (e: React.MouseEvent) => {
            e.stopPropagation();
            if (meta?.onOpenSubledgerDrawer) {
              meta.onOpenSubledgerDrawer(subcategory);
            }
          },
          className: `px-2 py-0.5 border font-mono text-[10px] font-bold rounded-md flex items-center justify-center space-x-1 transition-all cursor-pointer shadow-sm mx-auto ${colorStyles}`,
          title: `Open Subledger Hub for ${subcategory}`,
        },
        buttonLabel
      );
    },
  },
];

export const KPI_SUMMARY_COLUMNS: ColumnConfig[] = [
  {
    key: 'kpi_name',
    label: 'KPI Metric / Ledger Flow',
    width: '25%',
    align: 'left',
    textColor: 'text-zinc-100 font-bold',
  },
  {
    key: 'description',
    label: 'Description / Accounting Context',
    width: '30%',
    align: 'left',
    textColor: 'text-zinc-400 font-mono text-xs',
  },
  {
    key: 'count',
    label: 'Volume',
    width: '10%',
    align: 'center',
    textColor: 'text-cyan-400 font-mono text-xs font-bold',
  },
  {
    key: 'debit',
    label: 'Debit (DR)',
    width: '12.5%',
    align: 'right',
    isCurrency: true,
    textColor: 'text-rose-400 font-mono text-xs',
  },
  {
    key: 'credit',
    label: 'Credit (CR)',
    width: '12.5%',
    align: 'right',
    isCurrency: true,
    textColor: 'text-emerald-400 font-mono text-xs',
  },
  {
    key: 'net_flow',
    label: 'Net Balance Impact',
    width: '10%',
    align: 'right',
    isCurrency: true,
    textColor: 'text-amber-400 font-bold font-mono text-xs',
  },
];

export const EVALUATOR_5TIER_COLUMNS: ColumnConfig[] = [
  {
    key: 'date',
    label: 'TXN DATE',
    width: '8%',
    align: 'left',
    textColor: 'text-zinc-400',
  },
  {
    key: 'narration',
    label: 'STATEMENT DESCRIPTION REFERENCE',
    width: '26%',
    align: 'left',
    textColor: 'text-zinc-100',
  },
  {
    key: 'debit',
    label: 'DEBIT (DR)',
    width: '7%',
    align: 'right',
    textColor: 'text-amber-500',
    isCurrency: true,
  },
  {
    key: 'credit',
    label: 'CREDIT (CR)',
    width: '7%',
    align: 'right',
    textColor: 'text-emerald-500',
    isCurrency: true,
  },
  {
    key: 'category_item',
    label: 'ASSIGNED HEADER',
    width: '10%',
    align: 'left',
    textColor: 'text-cyan-400 font-bold',
  },
  {
    key: 'T1_item',
    label: 'T1 SYSTEM',
    width: '8%',
    align: 'left',
    textColor: 'text-zinc-400',
  },
  {
    key: 'T2_item',
    label: 'T2 TUNNEL',
    width: '8%',
    align: 'left',
    textColor: 'text-zinc-400',
  },
  {
    key: 'T3_item',
    label: 'T3 LAYOUT',
    width: '8%',
    align: 'left',
    textColor: 'text-zinc-400',
  },
  {
    key: 'T4_item',
    label: 'T4 MASTER',
    width: '8%',
    align: 'left',
    textColor: 'text-zinc-400',
  },
  {
    key: 'T5_item',
    label: 'T5 (AI)',
    width: '8%',
    align: 'left',
    textColor: 'text-emerald-400 font-semibold',
  },
  {
    key: 'actions',
    label: 'CLEARANCE',
    width: '4%',
    align: 'center',
  },
];

export const EMAIL_INGEST_COLUMNS: ColumnConfig[] = [
  { key: 'select', label: '', width: '4%', align: 'center' },
  {
    key: 'source',
    label: 'Source',
    width: '12%',
    align: 'left',
    textColor: 'text-indigo-400 font-mono text-[11px]',
  },
  {
    key: 'bank_name',
    label: 'Bank Name',
    width: '15%',
    align: 'left',
    textColor: 'text-zinc-100 font-semibold',
  },
  {
    key: 'merchant',
    label: 'Merchant / Narration',
    width: '32%',
    align: 'left',
    textColor: 'text-zinc-200',
  },
  {
    key: 'amount',
    label: 'Amount',
    width: '12%',
    align: 'right',
    isCurrency: true,
    textColor: 'text-emerald-400 font-mono font-bold',
  },
  { key: 'status', label: 'Status', width: '10%', align: 'center' },
  {
    key: 'email_date',
    label: 'Received At',
    width: '10%',
    align: 'left',
    textColor: 'text-zinc-400 text-[11px]',
  },
  { key: 'actions', label: 'Actions', width: '5%', align: 'center' },
];
