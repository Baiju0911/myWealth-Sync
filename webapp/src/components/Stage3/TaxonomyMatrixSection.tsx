import React, { useState, useMemo } from 'react';
import { Download, Search, SlidersHorizontal } from 'lucide-react';
import { TableEngine } from '../ui/data-table/TableEngine';
import { CATEGORY_BREAKDOWN_COLUMNS } from '../ui/data-table/columns';

interface TaxonomyMatrixSectionProps {
  categoryBreakdown: any[];
  selectedAccountId: string;
  subledgerCapableSet: Set<string>;
  onRowClick: (row: any) => void;
  onOpenSubledgerDrawer: (subcategory: string) => void;
  onExportCsv: (data: any[], filenamePrefix: string) => void;
}

export const TaxonomyMatrixSection: React.FC<TaxonomyMatrixSectionProps> = ({
  categoryBreakdown,
  selectedAccountId,
  subledgerCapableSet,
  onRowClick,
  onOpenSubledgerDrawer,
  onExportCsv,
}) => {
  const [filterClass, setFilterClass] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const classes = ['ALL', 'Expense', 'Income', 'Asset', 'Transfer', 'Liability'];

  const filteredData = useMemo(() => {
    return categoryBreakdown.filter((item) => {
      const matchClass = filterClass === 'ALL' || item.category === filterClass;
      const matchSearch = !searchQuery || 
        item.subcategory?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.category?.toLowerCase().includes(searchQuery.toLowerCase());
      return matchClass && matchSearch;
    });
  }, [categoryBreakdown, filterClass, searchQuery]);

  return (
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4 shadow-md space-y-3 font-mono">
      {/* Header Toolbar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-zinc-800/80 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="w-4 h-4 text-cyan-400" />
            <h2 className="text-xs uppercase tracking-wider text-zinc-100 font-bold">
              Taxonomy Breakdown Matrix
            </h2>
          </div>
          <p className="text-[11px] text-zinc-400 font-sans mt-0.5">
            Double-entry chart of accounts with dynamic subledger inspection. Click any row to open Workbench.
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => onExportCsv(filteredData, `Taxonomy_Breakdown_Node_${selectedAccountId}`)}
            className="flex items-center gap-1.5 bg-zinc-950 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer shadow-xs"
            title="Export filtered matrix to CSV"
          >
            <Download className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
            <span>Export CSV</span>
          </button>

          <span className="text-xs bg-zinc-950 border border-zinc-800 px-2.5 py-1 rounded-lg text-zinc-400">
            {filteredData.length} of {categoryBreakdown.length} heads
          </span>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 pt-1">
        {/* Class Filter Pills */}
        <div className="flex items-center gap-1 bg-zinc-950 p-1 rounded-lg border border-zinc-800/80 text-[11px]">
          {classes.map((cls) => (
            <button
              key={cls}
              onClick={() => setFilterClass(cls)}
              className={`px-2.5 py-0.5 rounded font-bold transition-colors cursor-pointer ${
                filterClass === cls
                  ? 'bg-zinc-800 text-cyan-400 border border-zinc-700 shadow-xs'
                  : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              {cls}
            </button>
          ))}
        </div>

        {/* Search input */}
        <div className="relative w-full sm:w-64">
          <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search account head..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-800 pl-8 pr-3 py-1 rounded-lg text-xs text-zinc-200 outline-none focus:border-cyan-500/50 transition-colors font-sans"
          />
        </div>
      </div>

      {/* Structured Table Container */}
      <div className="rounded-lg border border-zinc-800/80 overflow-hidden bg-zinc-950/40">
        <TableEngine
          columns={CATEGORY_BREAKDOWN_COLUMNS}
          data={filteredData}
          showFooter={true}
          onRowClick={onRowClick}
          meta={{
            subledgerCapableSet,
            onOpenSubledgerDrawer,
          }}
        />
      </div>
    </div>
  );
};