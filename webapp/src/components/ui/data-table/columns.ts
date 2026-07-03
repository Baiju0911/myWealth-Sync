export interface ColumnConfig {
  key: string;
  label: string;
  width: string;
  align: 'left' | 'center' | 'right';
  textColor?: string;
  fallbackColor?: string;
  isCurrency?: boolean;
  headerClass?: string;
  //HEXA?: string; // 🎯 Added to clean up header styles dynamically
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
    key: 'narration_description', // 🎯 Fixed: Matches 'line.narration_description' from your markup
    label: 'Narration Description',
    width: '35%',
    align: 'left',
  },
  {
    key: 'tran_type', // 🎯 Fixed: Matches 'line.tran_type' from your markup
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
    align: 'left', // Keep text layout standard, custom pills handle their internal alignment
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
  // {
  //   key: 'id',
  //   label: 'id',
  //   width: '9%',
  //   align: 'right',
  //   isCurrency: false,
  //   textColor: 'text-cyan-400/90',
  //   headerClass: 'text-cyan-400',
  // },

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

// Add this to src/components/ui/data-table/columns.ts

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
