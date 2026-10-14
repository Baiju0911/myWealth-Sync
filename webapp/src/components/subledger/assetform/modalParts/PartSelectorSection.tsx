import React, { useState, useMemo } from 'react';
import type { Vendor } from '../../../../api/subledger';

interface PartySelectorSectionProps {
  currentMode: string;
  vendors: Vendor[];
  selectedVendorId: string;
  onSelectVendor: (vendorId: string) => void;
  onQuickCreateVendor: (name: string) => Promise<void>;
  masterAssets: any[];
  parentAssetId: string;
  onSelectParentAsset: (parentId: string) => void;
}

export const PartySelectorSection: React.FC<PartySelectorSectionProps> = ({
  currentMode,
  vendors,
  selectedVendorId,
  onSelectVendor,
  onQuickCreateVendor,
  masterAssets,
  parentAssetId,
  onSelectParentAsset,
}) => {
  const [vendorSearch, setVendorSearch] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [isCreatingVendor, setIsCreatingVendor] = useState(false);
  const [newVendorName, setNewVendorName] = useState('');

  const filteredVendors = useMemo(() => {
    const term = vendorSearch.trim().toLowerCase();
    if (!term) return vendors;
    return vendors.filter((v) => v.name.toLowerCase().includes(term));
  }, [vendors, vendorSearch]);

  const handleSaveParty = async () => {
    if (!newVendorName.trim()) return;
    await onQuickCreateVendor(newVendorName.trim());
    setNewVendorName('');
    setIsCreatingVendor(false);
  };

  return (
    <div className="rounded-lg bg-slate-950 p-3 border border-slate-800 space-y-2.5 font-mono">
      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="block text-xs font-semibold text-sky-400">
            {currentMode === 'INCOME' ? 'Payer / Source' : 'Merchant / Builder / Counterparty'}
          </label>
          <div className="flex items-center gap-2">
            {!isCreatingVendor && vendors.length > 5 && (
              <button
                type="button"
                onClick={() => {
                  setIsSearching(!isSearching);
                  if (isSearching) setVendorSearch('');
                }}
                className="text-[11px] text-slate-400 hover:text-slate-200 cursor-pointer"
              >
                {isSearching ? '✕ Close Filter' : '🔍 Filter'}
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                setIsCreatingVendor(!isCreatingVendor);
                setIsSearching(false);
              }}
              className="text-xs text-emerald-400 hover:underline cursor-pointer"
            >
              {isCreatingVendor ? 'Cancel' : '+ New Party'}
            </button>
          </div>
        </div>

        {isCreatingVendor ? (
          <div className="flex gap-2 pt-1">
            <input
              type="text"
              placeholder="e.g. City Plaza Builder, Bhima Jewellers, Bank"
              value={newVendorName}
              onChange={(e) => setNewVendorName(e.target.value)}
              className="w-full rounded border border-slate-700 bg-slate-900 p-1.5 text-xs text-white focus:border-emerald-500 focus:outline-none"
            />
            <button
              type="button"
              onClick={handleSaveParty}
              className="rounded bg-emerald-600 px-3 py-1 text-xs font-semibold text-white hover:bg-emerald-500 cursor-pointer whitespace-nowrap"
            >
              Save
            </button>
          </div>
        ) : (
          <div className="space-y-1.5">
            {isSearching && (
              <input
                type="text"
                autoFocus
                placeholder="Type to filter parties..."
                value={vendorSearch}
                onChange={(e) => setVendorSearch(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-200 focus:border-emerald-500 focus:outline-none"
              />
            )}
            <select
              value={selectedVendorId}
              onChange={(e) => onSelectVendor(e.target.value)}
              className="w-full rounded border border-slate-700 bg-slate-900 p-1.5 text-xs text-white focus:border-emerald-500 focus:outline-none cursor-pointer"
            >
              <option value="">-- Independent / Direct (No External Counterparty) --</option>
              {filteredVendors.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {masterAssets.length > 0 && (
        <div className="pt-2 border-t border-slate-800/80">
          <label className="block text-[11px] text-slate-400 mb-1">
            Master Parent Asset <span className="text-slate-500">(Optional Sub-Unit Parent)</span>
          </label>
          <select
            value={parentAssetId}
            onChange={(e) => onSelectParentAsset(e.target.value)}
            className="w-full rounded border border-slate-800 bg-slate-900 p-1.5 text-xs text-slate-300 focus:border-emerald-500 focus:outline-none cursor-pointer"
          >
            <option value="">-- Standalone Master Asset (No Parent) --</option>
            {masterAssets.map((ast) => (
              <option key={ast.id} value={ast.id}>
                [{ast.asset_code}] {ast.name} ({ast.linked_gl_account || ast.category_display || ast.category})
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
};