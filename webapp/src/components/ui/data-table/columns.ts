// src/components/ui/data-table/columns.ts
import React from 'react';

export interface ColumnConfig {
  key: string;
  label: string;
  width: string;
  align: 'left' | 'center' | 'right';
  textColor?: string;
  fallbackColor?: string;
  isCurrency?: boolean;
  headerClass?: string;
  renderFooter?: (data: any[]) => string | number;
  // 🎯 Custom cell renderer callback for actions and badges
  renderCell?: (row: any, meta?: any) => React.ReactNode;
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

  // Financial columns with strict right-alignment and fallback parameters
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

// Column configuration for Tab 1: Known Headers
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

// 🔄 TAB 2 COLUMNS: SELF TRANSFER SYSTEM NODES
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

// export const CATEGORY_BREAKDOWN_COLUMNS: ColumnConfig[] = [
//   {
//     key: 'category',
//     label: 'Primary Class',
//     width: '15%',
//     align: 'left',
//     textColor: 'text-zinc-200 font-bold',
//   },
//   {
//     key: 'subcategory',
//     label: 'Subcategory',
//     width: '22%',
//     align: 'left',
//     textColor: 'text-zinc-300',
//   },
//   {
//     key: 'transaction_count',
//     label: 'Txn Count',
//     width: '8%',
//     align: 'center',
//     textColor: 'text-zinc-400 font-mono text-xs',
//   },
//   {
//     key: 'total_debit',
//     label: 'Debit (DR)',
//     width: '13%',
//     align: 'right',
//     isCurrency: true,
//     textColor: 'text-amber-400 font-mono text-xs',
//   },
//   {
//     key: 'total_credit',
//     label: 'Credit (CR)',
//     width: '13%',
//     align: 'right',
//     isCurrency: true,
//     textColor: 'text-emerald-400 font-mono text-xs',
//   },
//   {
//     key: 'net_balance',
//     label: 'Net Balance',
//     width: '17%',
//     align: 'right',
//     isCurrency: true,
//     textColor: 'text-zinc-100 font-bold font-mono text-xs',
//     renderFooter: (data: any[]) => {
//       const net = data.reduce((acc, row) => {
//         const dr = parseFloat(String(row.total_debit || '0').replace(/,/g, ''));
//         const cr = parseFloat(
//           String(row.total_credit || '0').replace(/,/g, '')
//         );
//         return acc + (dr - cr);
//       }, 0);

//       return net.toLocaleString('en-IN', { minimumFractionDigits: 2 });
//     },
//   },
//   // 🎯 Dynamic Action Button Column for Subledger-Capable Rows
//   {
//     key: 'actions',
//     label: 'Actions',
//     width: '12%',
//     align: 'center',
//     renderCell: (row: any, meta?: any) => {
//       const subcategory = row.subcategory;
//       const isSubledgerCapable = meta?.subledgerCapableSet?.has(subcategory);

//       if (!isSubledgerCapable) return null;

//       return React.createElement(
//         'button',
//         {
//           type: 'button',
//           onClick: (e: React.MouseEvent) => {
//             e.stopPropagation();
//             console.log(
//               '📦 [Subledger Hub Button Clicked for]:',
//               subcategory,
//               'Row Data:',
//               row
//             );
//             if (meta?.onOpenSubledgerDrawer) {
//               meta.onOpenSubledgerDrawer(subcategory);
//             }
//           },
//           className:
//             'px-2 py-0.5 bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-800/80 text-cyan-300 font-mono text-[10px] font-bold rounded-md flex items-center justify-center space-x-1 transition-all cursor-pointer shadow-sm mx-auto',
//           title: `Open Subledger Hub for ${subcategory}`,
//         },
//         '📦 Subledger Hub'
//       );
//     },
//   },
// ];

// Ledger Dashboard

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
  // 🎯 Flexible Action Button Column for Subledger-Capable Rows
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

      // 1. Case-insensitive & trimmed matching against backend subledgerCapableSet
      const isSetCapable = Array.from(capableSet).some(
        (item) =>
          String(item).trim().toLowerCase() === subcategory.toLowerCase()
      );

      // 2. Fallback: Automatically render for any row in the "Asset" primary class
      const isAssetRow = primaryCategory === 'asset';

      const isSubledgerCapable = isSetCapable || isAssetRow;

      if (!isSubledgerCapable || !subcategory) return null;

      return React.createElement(
        'button',
        {
          type: 'button',
          onClick: (e: React.MouseEvent) => {
            e.stopPropagation();
            console.log(
              '📦 [Subledger Hub Button Clicked for]:',
              subcategory,
              'Row Data:',
              row
            );
            if (meta?.onOpenSubledgerDrawer) {
              meta.onOpenSubledgerDrawer(subcategory);
            }
          },
          className:
            'px-2 py-0.5 bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-800/80 text-cyan-300 font-mono text-[10px] font-bold rounded-md flex items-center justify-center space-x-1 transition-all cursor-pointer shadow-sm mx-auto',
          title: `Open Subledger Hub for ${subcategory}`,
        },
        '📦 Asset Hub'
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

// export interface ColumnConfig {
//   key: string;
//   label: string;
//   width: string;
//   align: 'left' | 'center' | 'right';
//   textColor?: string;
//   fallbackColor?: string;
//   isCurrency?: boolean;
//   headerClass?: string;
//   //HEXA?: string; // 🎯 Added to clean up header styles dynamically
//   renderFooter?: (data: any[]) => string | number;
// }

// export const LEDGER_COLUMNS: ColumnConfig[] = [
//   { key: 'post_date', label: 'Txn Date', width: '9%', align: 'left' },
//   {
//     key: 'value_date',
//     label: 'Val Date',
//     width: '9%',
//     align: 'left',
//     textColor: 'text-orange-400/80',
//     headerClass: 'text-orange-400',
//   },
//   {
//     key: 'narration_description', // 🎯 Fixed: Matches 'line.narration_description' from your markup
//     label: 'Narration Description',
//     width: '35%',
//     align: 'left',
//   },
//   {
//     key: 'tran_type', // 🎯 Fixed: Matches 'line.tran_type' from your markup
//     label: 'Type',
//     width: '6%',
//     align: 'center',
//     textColor: 'text-indigo-300',
//     headerClass: 'text-indigo-400',
//   },
//   {
//     key: 'chq_ref',
//     label: 'Chq/Ref',
//     width: '9%',
//     align: 'left', // Keep text layout standard, custom pills handle their internal alignment
//     textColor: 'text-sky-400',
//     headerClass: 'text-sky-400',
//   },

//   // Financial columns with strict right-alignment and fallback parameters
//   {
//     key: 'debit',
//     label: 'Debit (-)',
//     width: '9%',
//     align: 'right',
//     isCurrency: true,
//     fallbackColor: 'text-red-400',
//     headerClass: 'text-red-400',
//   },
//   {
//     key: 'credit',
//     label: 'Credit (+)',
//     width: '9%',
//     align: 'right',
//     isCurrency: true,
//     fallbackColor: 'text-emerald-400',
//     headerClass: 'text-emerald-400',
//   },
//   {
//     key: 'balance',
//     label: 'Balance',
//     width: '9%',
//     align: 'right',
//     isCurrency: true,
//     textColor: 'text-cyan-400/90',
//     headerClass: 'text-cyan-400',
//   },
//   // {
//   //   key: 'id',
//   //   label: 'id',
//   //   width: '9%',
//   //   align: 'right',
//   //   isCurrency: false,
//   //   textColor: 'text-cyan-400/90',
//   //   headerClass: 'text-cyan-400',
//   // },

//   { key: 'status', label: 'Status', width: '5%', align: 'center' },
// ];

// // Column configuration for Tab 1: Known Headers
// export const ACCOUNTING_HEADER_COLUMNS: ColumnConfig[] = [
//   {
//     key: 'sno',
//     label: 'SNo',
//     width: '8%',
//     align: 'left',
//     textColor: 'text-zinc-500',
//   },
//   { key: 'category_type', label: 'Type Tag', width: '12%', align: 'center' },
//   {
//     key: 'act_category',
//     label: 'Core Category',
//     width: '15%',
//     align: 'left',
//     textColor: 'text-zinc-400',
//   },
//   {
//     key: 'act_subcategory',
//     label: 'Sub-Category',
//     width: '20%',
//     align: 'left',
//     textColor: 'text-zinc-300',
//   },
//   {
//     key: 'narration_description',
//     label: 'Item Label / Rules Match',
//     width: '33%',
//     align: 'left',
//     textColor: 'text-zinc-100',
//   },
//   { key: 'actions', label: 'CRUD Actions', width: '12%', align: 'center' },
// ];

// // 🔄 TAB 2 COLUMNS: SELF TRANSFER SYSTEM NODES
// export const SELF_TRANSFER_COLUMNS: ColumnConfig[] = [
//   {
//     key: 'sno',
//     label: 'SNo',
//     width: '8%',
//     align: 'left',
//     textColor: 'text-zinc-500',
//   },
//   {
//     key: 'source_account_name',
//     label: 'Debit Origin (From)',
//     width: '30%',
//     align: 'left',
//     textColor: 'text-red-400/90',
//   },
//   {
//     key: 'destination_account_name',
//     label: 'Credit Target (To)',
//     width: '30%',
//     align: 'left',
//     textColor: 'text-emerald-400/90',
//   },
//   {
//     key: 'narration_description',
//     label: 'Routing Instruction',
//     width: '20%',
//     align: 'left',
//   },
//   { key: 'actions', label: 'CRUD Actions', width: '12%', align: 'center' },
// ];

// // Add this to src/components/ui/data-table/columns.ts

// export const BALANCE_SHEET_COLUMNS: ColumnConfig[] = [
//   {
//     key: 'sno',
//     label: 'SNo',
//     width: '8%',
//     align: 'left',
//     textColor: 'text-zinc-500',
//   },
//   {
//     key: 'act_category',
//     label: 'Core Group',
//     width: '15%',
//     align: 'left',
//     textColor: 'text-cyan-400',
//   },
//   {
//     key: 'act_subcategory',
//     label: 'Line Item Header',
//     width: '25%',
//     align: 'left',
//     textColor: 'text-zinc-200',
//   },
//   {
//     key: 'narration_description',
//     label: 'Target Label',
//     width: '25%',
//     align: 'left',
//     textColor: 'text-zinc-100',
//   },
//   {
//     key: 'dashboard_cat',
//     label: 'Dashboard Placement',
//     width: '15%',
//     align: 'center',
//   },
//   { key: 'actions', label: 'CRUD Actions', width: '12%', align: 'center' },
// ];

// export const BULK_APPROVAL_COLUMNS: ColumnConfig[] = [
//   {
//     key: 'date',
//     label: 'Txn Date',
//     width: '10%',
//     align: 'left',
//     textColor: 'text-zinc-400',
//   },
//   {
//     key: 'narration',
//     label: 'Statement Description Reference',
//     width: '35%',
//     align: 'left',
//     textColor: 'text-zinc-100',
//   },
//   {
//     key: 'debit',
//     label: 'Debit (DR)',
//     width: '10%',
//     align: 'right',
//     textColor: 'text-amber-500',
//   },
//   {
//     key: 'credit',
//     label: 'Credit (CR)',
//     width: '10%',
//     align: 'right',
//     textColor: 'text-emerald-500',
//   },
//   {
//     key: 'category_item',
//     label: 'Assigned Header Mapping',
//     width: '20%',
//     align: 'left',
//     textColor: 'text-cyan-400',
//   },
//   {
//     key: 'T1_item',
//     label: 'T1',
//     width: '20%',
//     align: 'left',
//     textColor: 'text-cyan-400',
//   },
//   {
//     key: 'T2_item',
//     label: 'T2',
//     width: '20%',
//     align: 'left',
//     textColor: 'text-cyan-400',
//   },
//   {
//     key: 'T3_item',
//     label: 'T3',
//     width: '20%',
//     align: 'left',
//     textColor: 'text-cyan-400',
//   },
//   {
//     key: 'T4_item',
//     label: 'T4',
//     width: '20%',
//     align: 'left',
//     textColor: 'text-cyan-400',
//   },
//   {
//     key: 'rule_code',
//     label: 'Rule Linked',
//     width: '10%',
//     align: 'center',
//     textColor: 'text-zinc-400',
//   },
//   { key: 'actions', label: 'Clearance', width: '5%', align: 'center' },
// ];

// export const UNCATEGORIZED_VAULT_COLUMNS: ColumnConfig[] = [
//   {
//     key: 'date',
//     label: 'Txn Date',
//     width: '10%',
//     align: 'left',
//     textColor: 'text-zinc-400',
//   },
//   {
//     key: 'narration',
//     label: 'Statement Description Reference',
//     width: '40%',
//     align: 'left',
//     textColor: 'text-zinc-100',
//   },
//   {
//     key: 'debit',
//     label: 'Debit (DR)',
//     width: '10%',
//     align: 'right',
//     textColor: 'text-amber-500',
//   },
//   {
//     key: 'credit',
//     label: 'Credit (CR)',
//     width: '10%',
//     align: 'right',
//     textColor: 'text-emerald-500',
//   },
//   {
//     key: 'errors',
//     label: 'Failed Validation Gate Footprint',
//     width: '20%',
//     align: 'left',
//     textColor: 'text-red-400 font-mono text-[11px]',
//   },
//   { key: 'actions', label: 'Manual Allocation', width: '10%', align: 'center' },
// ];

// export const CATEGORY_BREAKDOWN_COLUMNS: ColumnConfig[] = [
//   {
//     key: 'category',
//     label: 'Primary Class',
//     width: '15%',
//     align: 'left',
//     textColor: 'text-zinc-200 font-bold',
//   },
//   {
//     key: 'subcategory',
//     label: 'Subcategory',
//     width: '25%',
//     align: 'left',
//     textColor: 'text-zinc-300',
//   },
//   {
//     key: 'transaction_count',
//     label: 'Txn Count',
//     width: '10%',
//     align: 'center',
//     textColor: 'text-zinc-400 font-mono text-xs',
//   },
//   {
//     key: 'total_debit',
//     label: 'Debit (DR)',
//     width: '15%',
//     align: 'right',
//     isCurrency: true,
//     textColor: 'text-amber-400 font-mono text-xs',
//   },
//   {
//     key: 'total_credit',
//     label: 'Credit (CR)',
//     width: '15%',
//     align: 'right',
//     isCurrency: true,
//     textColor: 'text-emerald-400 font-mono text-xs',
//   },
//   {
//     key: 'net_balance',
//     label: 'Net Balance',
//     width: '20%',
//     align: 'right',
//     isCurrency: true,
//     textColor: 'text-zinc-100 font-bold font-mono text-xs',
//     // 🟢 Return pure string formatted currency (no JSX tags in .ts file!)
//     renderFooter: (data: any[]) => {
//       const net = data.reduce((acc, row) => {
//         const dr = parseFloat(String(row.total_debit || '0').replace(/,/g, ''));
//         const cr = parseFloat(
//           String(row.total_credit || '0').replace(/,/g, '')
//         );
//         return acc + (dr - cr);
//       }, 0);

//       return net.toLocaleString('en-IN', { minimumFractionDigits: 2 });
//     },
//   },
// ];

// //Ledger Dashboard
// export const KPI_SUMMARY_COLUMNS: ColumnConfig[] = [
//   {
//     key: 'kpi_name',
//     label: 'KPI Metric / Ledger Flow',
//     width: '25%',
//     align: 'left',
//     textColor: 'text-zinc-100 font-bold',
//   },
//   {
//     key: 'description',
//     label: 'Description / Accounting Context',
//     width: '30%',
//     align: 'left',
//     textColor: 'text-zinc-400 font-mono text-xs',
//   },
//   {
//     key: 'count',
//     label: 'Volume',
//     width: '10%',
//     align: 'center',
//     textColor: 'text-cyan-400 font-mono text-xs font-bold',
//   },
//   {
//     key: 'debit',
//     label: 'Debit (DR)',
//     width: '12.5%',
//     align: 'right',
//     isCurrency: true,
//     textColor: 'text-rose-400 font-mono text-xs',
//   },
//   {
//     key: 'credit',
//     label: 'Credit (CR)',
//     width: '12.5%',
//     align: 'right',
//     isCurrency: true,
//     textColor: 'text-emerald-400 font-mono text-xs',
//   },
//   {
//     key: 'net_flow',
//     label: 'Net Balance Impact',
//     width: '10%',
//     align: 'right',
//     isCurrency: true,
//     textColor: 'text-amber-400 font-bold font-mono text-xs',
//   },
// ];
