// webapp/src/components/Stage3/Workbench/clusterlistHelpers/WorkbenchSearchBar.tsx
import React, { useEffect, useRef } from 'react';
import { Search, Sparkles, Building2, HelpCircle, ArrowUpDown, X } from 'lucide-react';
import type { StatusFilterType, DirectionFilterType, SortOrderType } from './searchAndFilterHelpers';

interface Props {
  selectedCount: number;
  isAllVisibleSelected: boolean;
  onToggleSelectAll: () => void;
  onClearAll: () => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  statusFilter: StatusFilterType;
  onStatusFilterChange: (f: StatusFilterType) => void;
  directionFilter: DirectionFilterType;
  onDirectionFilterChange: (d: DirectionFilterType) => void;
  sortOrder: SortOrderType;
  onSortOrderChange: (s: SortOrderType) => void;
  availableYears: string[];
  narrationMode: 'smart' | 'raw';
  onToggleNarrationMode: (m: 'smart' | 'raw') => void;
  onExpandAll: () => void;
  onCollapseAll: () => void;
}

export const WorkbenchSearchBar: React.FC<Props> = ({
  selectedCount,
  isAllVisibleSelected,
  onToggleSelectAll,
  onClearAll,
  searchQuery,
  onSearchChange,
  statusFilter,
  onStatusFilterChange,
  directionFilter,
  onDirectionFilterChange,
  sortOrder,
  onSortOrderChange,
  availableYears = [],
  narrationMode,
  onToggleNarrationMode,
  onExpandAll,
  onCollapseAll,
}) => {
  const inputRef = useRef<HTMLInputElement>(null);

  // ⚡ Global Keyboard Shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const targetTag = (e.target as HTMLElement)?.tagName?.toLowerCase();
      const isInput = targetTag === 'input' || targetTag === 'textarea';

      // Press "/" to focus search
      if (e.key === '/' && !isInput) {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
        return;
      }

      // Press "Escape" to clear search or blur
      if (e.key === 'Escape' && isInput) {
        if (searchQuery) {
          onSearchChange('');
        } else {
          inputRef.current?.blur();
        }
        return;
      }

      // Alt + A: Select visible
      if (e.altKey && (e.key === 'a' || e.key === 'A')) {
        e.preventDefault();
        onToggleSelectAll();
        return;
      }

      // Alt + C: Clear selections
      if (e.altKey && (e.key === 'c' || e.key === 'C')) {
        e.preventDefault();
        onClearAll();
        return;
      }

      // Alt + S: Toggle Smart / Raw mode
      if (e.altKey && (e.key === 's' || e.key === 'S')) {
        e.preventDefault();
        onToggleNarrationMode(narrationMode === 'smart' ? 'raw' : 'smart');
        return;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [searchQuery, narrationMode, onSearchChange, onToggleSelectAll, onClearAll, onToggleNarrationMode]);

  // Preset Chips applicator
  const applyPreset = (queryValue: string, direction?: DirectionFilterType, status?: StatusFilterType) => {
    onSearchChange(queryValue);
    if (direction) onDirectionFilterChange(direction);
    if (status) onStatusFilterChange(status);
  };

  return (
    <div className="p-3 border-b border-zinc-800 flex flex-col gap-2 bg-zinc-900/60 shrink-0 font-mono text-xs select-none">
      {/* Row 1: Select Checkbox, Search Input with Shortcuts, Narration Toggle, Controls */}
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-1.5 text-[11px] text-zinc-400 font-bold cursor-pointer shrink-0">
          <input
            type="checkbox"
            checked={isAllVisibleSelected}
            onChange={onToggleSelectAll}
            className="w-3.5 h-3.5 accent-amber-500 cursor-pointer rounded"
            title="Shortcut: Alt+A"
          />
          <span>Visible</span>
        </label>

        {selectedCount > 0 && (
          <button
            type="button"
            onClick={onClearAll}
            className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 px-2 py-0.5 rounded text-[10px] font-bold transition-colors cursor-pointer shrink-0"
            title="Shortcut: Alt+C"
          >
            Clear ({selectedCount})
          </button>
        )}

        <div className="relative flex-1">
          <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input
            ref={inputRef}
            type="text"
            placeholder="Search vendor, >50000, 2026, Q3, from:SIB to:NRO... (Press '/')"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-800 rounded-lg pl-8 pr-12 py-1.5 text-xs text-zinc-200 outline-none focus:border-amber-500/60 transition-colors font-sans"
          />
          <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
            {searchQuery && (
              <button
                type="button"
                onClick={() => onSearchChange('')}
                className="text-zinc-500 hover:text-zinc-300 p-0.5"
                title="Clear (Esc)"
              >
                <X className="w-3 h-3" />
              </button>
            )}
            <span
              className="text-zinc-500 hover:text-amber-400 cursor-help"
              title="Quick Search Tips:&#10;• Amounts: >100000, <5000, 50000..200000&#10;• FY Quarters: Q1, Q2, Q3, Q4&#10;• Routing: from:sib to:nre, bank:bob&#10;• Year: 2024, 2025, 2026&#10;• Shortcuts: '/' focus, Esc clear, Alt+A select all, Alt+S toggle raw/smart"
            >
              <HelpCircle className="w-3.5 h-3.5" />
            </span>
          </div>
        </div>

        {/* Global Smart / Raw Flipper */}
        <div className="flex bg-zinc-900 rounded-lg border border-zinc-800 p-0.5 shrink-0" title="Shortcut: Alt+S">
          <button
            type="button"
            onClick={() => onToggleNarrationMode('smart')}
            className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-bold transition-all cursor-pointer ${
              narrationMode === 'smart'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <Sparkles className="w-3 h-3" />
            Smart
          </button>
          <button
            type="button"
            onClick={() => onToggleNarrationMode('raw')}
            className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-bold transition-all cursor-pointer ${
              narrationMode === 'raw'
                ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <Building2 className="w-3 h-3" />
            Raw
          </button>
        </div>

        {/* Sort Selector */}
        <div className="flex items-center gap-1 bg-zinc-950 border border-zinc-800 rounded-lg px-2 py-0.5 shrink-0">
          <ArrowUpDown className="w-3 h-3 text-zinc-500 shrink-0" />
          <select
            value={sortOrder}
            onChange={(e) => onSortOrderChange(e.target.value as SortOrderType)}
            className="bg-transparent text-[10px] text-zinc-300 outline-none cursor-pointer font-bold"
          >
            <option value="amount_desc" className="bg-zinc-900">Highest ₹</option>
            <option value="count_desc" className="bg-zinc-900">Most Txns</option>
            <option value="name_asc" className="bg-zinc-900">A-Z Name</option>
          </select>
        </div>

        <div className="flex gap-1 shrink-0">
          <button
            type="button"
            onClick={onExpandAll}
            className="bg-zinc-950 border border-zinc-800 hover:bg-zinc-800 text-zinc-400 px-2 py-1 rounded text-[10px] font-bold cursor-pointer"
          >
            Expand
          </button>
          <button
            type="button"
            onClick={onCollapseAll}
            className="bg-zinc-950 border border-zinc-800 hover:bg-zinc-800 text-zinc-400 px-2 py-1 rounded text-[10px] font-bold cursor-pointer"
          >
            Collapse
          </button>
        </div>
      </div>

      {/* Row 2: Status & Direction Filters */}
      <div className="flex items-center justify-between flex-wrap gap-2 text-[10px]">
        {/* Status Filters */}
        <div className="flex items-center gap-1.5">
          <span className="text-zinc-500 uppercase font-bold text-[9px] mr-1">Status:</span>
          {(['all', 'unmapped', 'mapped', 'contra'] as StatusFilterType[]).map((pill) => (
            <button
              key={pill}
              type="button"
              onClick={() => onStatusFilterChange(pill)}
              className={`px-2 py-0.5 rounded text-[10px] font-bold capitalize transition-all cursor-pointer border ${
                statusFilter === pill
                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/50 shadow-xs'
                  : 'bg-zinc-950 text-zinc-500 border-zinc-800 hover:text-zinc-300'
              }`}
            >
              {pill === 'contra' ? 'Self-Transfers' : pill}
            </button>
          ))}
        </div>

        {/* Direction Filters */}
        <div className="flex items-center gap-1.5">
          <span className="text-zinc-500 uppercase font-bold text-[9px] mr-1">Vector:</span>
          <button
            type="button"
            onClick={() => onDirectionFilterChange('all')}
            className={`px-2 py-0.5 rounded font-bold border transition-all cursor-pointer ${
              directionFilter === 'all'
                ? 'bg-zinc-700 text-zinc-100 border-zinc-600'
                : 'bg-zinc-950 text-zinc-500 border-zinc-800 hover:text-zinc-300'
            }`}
          >
            All
          </button>
          <button
            type="button"
            onClick={() => onDirectionFilterChange('outflow')}
            className={`px-2 py-0.5 rounded font-bold border transition-all cursor-pointer ${
              directionFilter === 'outflow'
                ? 'bg-rose-950/80 text-rose-300 border-rose-700 shadow-xs'
                : 'bg-zinc-950 text-zinc-500 border-zinc-800 hover:text-rose-400'
            }`}
          >
            🔻 Debits (Out)
          </button>
          <button
            type="button"
            onClick={() => onDirectionFilterChange('inflow')}
            className={`px-2 py-0.5 rounded font-bold border transition-all cursor-pointer ${
              directionFilter === 'inflow'
                ? 'bg-emerald-950/80 text-emerald-300 border-emerald-700 shadow-xs'
                : 'bg-zinc-950 text-zinc-500 border-zinc-800 hover:text-emerald-400'
            }`}
          >
            🟢 Credits (In)
          </button>
        </div>
      </div>

      {/* Row 3: Presets & Dynamic Years */}
{/* Row 3: Presets & Compact Selectors */}
      <div className="flex items-center justify-between gap-2 pt-0.5 text-[10px]">
        {/* Left: Quick Value / Status Presets */}
        <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar">
          <span className="text-zinc-500 uppercase font-bold text-[9px] mr-0.5 shrink-0">Presets:</span>
          
          <button
            type="button"
            onClick={() => applyPreset('>100000', 'outflow')}
            className={`px-2 py-0.5 rounded text-[10px] font-bold transition-all cursor-pointer border shrink-0 ${
              searchQuery.includes('>100000') && directionFilter === 'outflow'
                ? 'bg-rose-950/80 text-rose-300 border-rose-700'
                : 'bg-zinc-950 text-zinc-400 border-zinc-800 hover:text-zinc-200'
            }`}
          >
            &gt; ₹1L Out
          </button>

          <button
            type="button"
            onClick={() => applyPreset('>500000')}
            className={`px-2 py-0.5 rounded text-[10px] font-bold transition-all cursor-pointer border shrink-0 ${
              searchQuery.includes('>500000')
                ? 'bg-amber-500/20 text-amber-300 border-amber-500/50'
                : 'bg-zinc-950 text-zinc-400 border-zinc-800 hover:text-zinc-200'
            }`}
          >
            &gt; ₹5L Large
          </button>

          <button
            type="button"
            onClick={() => applyPreset('', 'outflow', 'unmapped')}
            className={`px-2 py-0.5 rounded text-[10px] font-bold transition-all cursor-pointer border shrink-0 ${
              statusFilter === 'unmapped' && directionFilter === 'outflow'
                ? 'bg-amber-500/20 text-amber-300 border-amber-500/50'
                : 'bg-zinc-950 text-amber-400/80 border-zinc-800 hover:text-amber-300'
            }`}
          >
            Unmapped Debits
          </button>
        </div>

        {/* Right: Clean Year & Quarter Dropdown Selects */}
        <div className="flex items-center gap-1.5 shrink-0">
          {/* Dynamic FY Select */}
          <div className="flex items-center gap-1 bg-zinc-950 border border-zinc-800 hover:border-zinc-700 rounded-md px-2 py-0.5 transition-colors">
            <span className="text-zinc-500 text-[9px] font-bold uppercase tracking-wider">FY</span>
            <select
              value={availableYears.find((y) => searchQuery.includes(y)) || ''}
              onChange={(e) => {
                const val = e.target.value;
                const cleaned = searchQuery.replace(/\b20\d{2}\b/g, '').trim();
                onSearchChange(val ? `${cleaned} ${val}`.trim() : cleaned);
              }}
              className="bg-transparent text-[10px] text-zinc-300 outline-none cursor-pointer font-bold font-mono"
            >
              <option value="" className="bg-zinc-900 text-zinc-400">All Years</option>
              {(availableYears.length > 0 ? availableYears : ['2026', '2025', '2024', '2023', '2022', '2021']).map((yr) => (
                <option key={yr} value={yr} className="bg-zinc-900 text-zinc-200">
                  FY {yr}
                </option>
              ))}
            </select>
          </div>

          {/* Quarter Select (Aware of Selected FY) */}
          {(() => {
            const selectedYr = availableYears.find((y) => searchQuery.includes(y));
            const nextYr = selectedYr ? String(parseInt(selectedYr, 10) + 1).slice(-2) : '';

            return (
              <div className="flex items-center gap-1 bg-zinc-950 border border-zinc-800 hover:border-zinc-700 rounded-md px-2 py-0.5 transition-colors">
                <span className="text-zinc-500 text-[9px] font-bold uppercase tracking-wider">QTR</span>
                <select
                  value={['Q1', 'Q2', 'Q3', 'Q4'].find((q) => new RegExp(`\\b${q}\\b`, 'i').test(searchQuery)) || ''}
                  onChange={(e) => {
                    const val = e.target.value;
                    const cleaned = searchQuery.replace(/\bQ[1-4]\b/gi, '').trim();
                    onSearchChange(val ? `${cleaned} ${val}`.trim() : cleaned);
                  }}
                  className="bg-transparent text-[10px] text-zinc-300 outline-none cursor-pointer font-bold font-mono"
                >
                  <option value="" className="bg-zinc-900 text-zinc-400">All Qtrs</option>
                  <option value="Q1" className="bg-zinc-900 text-zinc-200">
                    Q1 (Apr–Jun{selectedYr ? ` '${selectedYr.slice(-2)}` : ''})
                  </option>
                  <option value="Q2" className="bg-zinc-900 text-zinc-200">
                    Q2 (Jul–Sep{selectedYr ? ` '${selectedYr.slice(-2)}` : ''})
                  </option>
                  <option value="Q3" className="bg-zinc-900 text-zinc-200">
                    Q3 (Oct–Dec{selectedYr ? ` '${selectedYr.slice(-2)}` : ''})
                  </option>
                  <option value="Q4" className="bg-zinc-900 text-zinc-200">
                    Q4 (Jan–Mar{nextYr ? ` '${nextYr}` : ''})
                  </option>
                </select>
              </div>
            );
          })()}

          {/* Quarter Select
          <div className="flex items-center gap-1 bg-zinc-950 border border-zinc-800 hover:border-zinc-700 rounded-md px-2 py-0.5 transition-colors">
            <span className="text-zinc-500 text-[9px] font-bold uppercase tracking-wider">QTR</span>
            <select
              value={['Q1', 'Q2', 'Q3', 'Q4'].find((q) => new RegExp(`\\b${q}\\b`, 'i').test(searchQuery)) || ''}
              onChange={(e) => {
                const val = e.target.value;
                const cleaned = searchQuery.replace(/\bQ[1-4]\b/gi, '').trim();
                onSearchChange(val ? `${cleaned} ${val}`.trim() : cleaned);
              }}
              className="bg-transparent text-[10px] text-zinc-300 outline-none cursor-pointer font-bold font-mono"
            >
              <option value="" className="bg-zinc-900 text-zinc-400">All Qtrs</option>
              <option value="Q1" className="bg-zinc-900 text-zinc-200">Q1 (Apr–Jun)</option>
              <option value="Q2" className="bg-zinc-900 text-zinc-200">Q2 (Jul–Sep)</option>
              <option value="Q3" className="bg-zinc-900 text-zinc-200">Q3 (Oct–Dec)</option>
              <option value="Q4" className="bg-zinc-900 text-zinc-200">Q4 (Jan–Mar)</option>
            </select>
          </div> */}
        </div>


      </div>
    </div>
  );
};