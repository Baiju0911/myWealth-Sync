import React, { useState } from 'react';
import { subledgerApi, type SubledgerTaxonomyGroup } from '../../../../api/subledger';

interface TaxonomyOption {
  id: string;
  subcategory: string;
  group: string;
}

interface TaxonomySelectSectionProps {
  currentMode: string;
  linkedGlAccount: string;
  options: TaxonomyOption[];
  onSelectSubcategory: (sub: string) => void;
  onRefreshTaxonomy: (tree: SubledgerTaxonomyGroup[]) => void;
}

export const TaxonomySelectSection: React.FC<TaxonomySelectSectionProps> = ({
  currentMode,
  linkedGlAccount,
  options,
  onSelectSubcategory,
  onRefreshTaxonomy,
}) => {
  const [isCreatingCategory, setIsCreatingCategory] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState('');
  const [savingCategory, setSavingCategory] = useState(false);

  const handleCreateCategory = async () => {
    if (!newCategoryName.trim()) return;
    setSavingCategory(true);
    try {
      await subledgerApi.createTaxonomyNode({
        category:
          currentMode === 'INCOME' ? 'Income' : currentMode === 'EXPENSE' ? 'Expense' : 'Asset',
        subcategory: newCategoryName.trim(),
        display_order: 99,
        is_active: true,
      });
      const tree = await subledgerApi.getTaxonomyNodesForSubledger();
      onRefreshTaxonomy(tree);
      onSelectSubcategory(newCategoryName.trim());
      setIsCreatingCategory(false);
      setNewCategoryName('');
    } catch (err) {
      console.error('Failed to create category:', err);
    } finally {
      setSavingCategory(false);
    }
  };

  return (
    <div className="col-span-12">
      <div className="flex items-center justify-between mb-1">
        <label className="block text-xs font-semibold text-amber-400">
          Linked GL Taxonomy Head ({currentMode})
        </label>
        <button
          type="button"
          onClick={() => setIsCreatingCategory(!isCreatingCategory)}
          className="text-[11px] text-emerald-400 hover:underline cursor-pointer"
        >
          {isCreatingCategory ? 'Cancel' : '+ New Category'}
        </button>
      </div>

      {isCreatingCategory ? (
        <div className="flex gap-1.5">
          <input
            type="text"
            placeholder="e.g. Commercial Real Estate"
            value={newCategoryName}
            onChange={(e) => setNewCategoryName(e.target.value)}
            className="w-full rounded border border-slate-700 bg-slate-800 p-1.5 text-xs text-white focus:border-emerald-500 focus:outline-none"
          />
          <button
            type="button"
            disabled={savingCategory}
            onClick={handleCreateCategory}
            className="rounded bg-emerald-600 px-3 py-1 text-xs font-bold text-white hover:bg-emerald-500 cursor-pointer disabled:opacity-50"
          >
            {savingCategory ? 'Saving...' : 'Save'}
          </button>
        </div>
      ) : (
        <select
          value={linkedGlAccount}
          onChange={(e) => onSelectSubcategory(e.target.value)}
          className="w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white cursor-pointer focus:border-emerald-500 focus:outline-none"
          required
        >
          <option value="">
            -- Select GL Head ({options.length} available) --
          </option>
          {options.map((item) => (
            <option key={item.id || item.subcategory} value={item.subcategory}>
              {item.group} ➔ {item.subcategory}
            </option>
          ))}
        </select>
      )}
    </div>
  );
};