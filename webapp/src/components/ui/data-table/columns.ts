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
