import React, { useState, useEffect, useMemo } from 'react';
import {
  subledgerApi,
  type AssetSubLedgerNode,
  type OwnershipType,
  type AssetStatusType,
  type SubledgerTaxonomyGroup,
  type Vendor,
} from '../../api/subledger';
import {
  CATEGORY_DYNAMIC_SCHEMAS,
  type FieldDefinition,
} from '../ui/categorySchemaRegistry';

interface AssetFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  assetToEdit?: AssetSubLedgerNode | null;
  defaultSubcategory?: string | null;
  activeTab?: 'ASSET' | 'INCOME' | 'EXPENSE';
  onSuccess: () => void;
}

export const AssetFormModal: React.FC<AssetFormModalProps> = ({
  isOpen,
  onClose,
  assetToEdit,
  defaultSubcategory,
  activeTab = 'ASSET',
  onSuccess,
}) => {
  const [assetCode, setAssetCode] = useState('AST-001');
  const [name, setName] = useState('');

  // 🎯 Optional Parent Asset Link (Income/Expense tied to an existing Asset)
  const [parentAssetId, setParentAssetId] = useState<string>('');
  const [allAssets, setAllAssets] = useState<AssetSubLedgerNode[]>([]);

  // Dates & Financials
  const [acquisitionDate, setAcquisitionDate] = useState<string>(
    new Date().toISOString().split('T')[0]
  );
  const [acquisitionCost, setAcquisitionCost] = useState<number | string>('');
  const [currentValuation, setCurrentValuation] = useState<number | string>('');
  const [ownershipType] = useState<OwnershipType>('INDIVIDUAL');
  const [status] = useState<AssetStatusType>('ACTIVE');

  // Single Source GL Account from TaxonomyTree
  const [linkedGlAccount, setLinkedGlAccount] = useState<string>('');
  const [taxonomyTree, setTaxonomyTree] = useState<SubledgerTaxonomyGroup[]>([]);

  // Dynamic Metadata
  const [metadataEntries, setMetadataEntries] = useState<{ key: string; value: string }[]>([]);

  // Vendor / Payer / Client State
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [selectedVendorId, setSelectedVendorId] = useState<string>('');
  const [newVendorName, setNewVendorName] = useState<string>('');
  const [isCreatingVendor, setIsCreatingVendor] = useState(false);

  // Quick Create Taxonomy Subcategory
  const [isCreatingCategory, setIsCreatingCategory] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState('');

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 1. ESC Key Listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    if (isOpen) window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // 2. Fetch Vendors and Registered Assets on open
  useEffect(() => {
    if (isOpen) {
      Promise.all([
        subledgerApi.getVendors().catch(() => []),
        subledgerApi.getAssets().catch(() => []),
      ]).then(([vList, aList]) => {
        setVendors(vList);
        setAllAssets(aList);
      });
    }
  }, [isOpen]);

  // 🎯 Filter Linked Asset options strictly to balance sheet ASSETS only
  const availableParentAssets = useMemo(() => {
    return allAssets.filter((ast: any) => {
      if (assetToEdit && String(ast.id) === String(assetToEdit.id)) return false;

      const catType = String(
        ast.category_type ||
        ast.category_detail?.category_type ||
        'ASSET'
      ).toUpperCase();

      const isIncomeOrExpense =
        catType === 'INCOME' ||
        catType === 'EXPENSE' ||
        String(ast.asset_code || '').startsWith('INC-') ||
        String(ast.asset_code || '').startsWith('EXP-');

      return catType === 'ASSET' && !isIncomeOrExpense;
    });
  }, [allAssets, assetToEdit]);

  // Filter Taxonomy Subcategories dynamically matching current active tab
  const filteredTaxonomySubcategories = useMemo(() => {
    const targetGroup = String(activeTab).trim().toLowerCase();

    return taxonomyTree
      .filter((group) => {
        const catName = group.category.toLowerCase();
        if (targetGroup === 'income') return catName.includes('income');
        if (targetGroup === 'expense') return catName.includes('expense');
        return catName.includes('asset');
      })
      .flatMap((group) =>
        group.subcategories.map((sub: any) => ({
          id: typeof sub === 'object' ? sub.id : sub,
          subcategory: typeof sub === 'object' ? sub.subcategory : sub,
          group: group.category,
        }))
      );
  }, [taxonomyTree, activeTab]);

  const loadMergedCategorySchema = async (catCode: string) => {
    const localSchema = CATEGORY_DYNAMIC_SCHEMAS[catCode] || [];
    const keySet = new Set<string>();
    const rows: { key: string; value: string }[] = [];

    localSchema.forEach((field: FieldDefinition) => {
      rows.push({ key: field.key, value: '' });
      keySet.add(field.key);
    });

    try {
      const dbKeys = await subledgerApi.getCategorySchemaKeys(catCode);
      dbKeys.forEach((dbKey: string) => {
        if (!keySet.has(dbKey)) {
          rows.push({ key: dbKey, value: '' });
          keySet.add(dbKey);
        }
      });
    } catch (err) {
      console.error('Failed to fetch historical category keys from DB:', err);
    }

    setMetadataEntries(rows.length > 0 ? rows : [{ key: '', value: '' }]);
  };

  const handleGlTaxonomyChange = async (newGlSubcategory: string) => {
    setLinkedGlAccount(newGlSubcategory);

    if (!newGlSubcategory) return;

    const cleanCode = newGlSubcategory
      .toUpperCase()
      .replace(/^INCOME\s*-\s*/, '')
      .replace(/^EXPENSE\s*-\s*/, '')
      .replace(/^ASSET\s*-\s*/, '')
      .replace(/[^A-Z0-9]/g, '_')
      .replace(/_+/g, '_');

    await loadMergedCategorySchema(cleanCode);
  };

  const handleVendorChange = (vendorId: string) => {
    setSelectedVendorId(vendorId);
    const vObj = vendors.find((v) => String(v.id) === String(vendorId));
    if (vObj && !assetToEdit) {
      const cleanPrefix = vObj.name.replace(/[^a-zA-Z0-9]/g, '').slice(0, 4).toUpperCase();
      const codePrefix = activeTab === 'INCOME' ? 'INC' : activeTab === 'EXPENSE' ? 'EXP' : 'AST';
      setAssetCode(`${codePrefix}-${cleanPrefix}-008`);
    }
  };

  useEffect(() => {
    if (!isOpen) return;

    subledgerApi
      .getTaxonomyNodesForSubledger()
      .then(async (treeRes) => {
        setTaxonomyTree(treeRes);

        if (assetToEdit) {
          setAssetCode(assetToEdit.asset_code);
          setName(assetToEdit.name);
          setAcquisitionDate(
            assetToEdit.acquisition_date
              ? assetToEdit.acquisition_date.split('T')[0]
              : new Date().toISOString().split('T')[0]
          );
          setAcquisitionCost(assetToEdit.acquisition_cost);
          setCurrentValuation(assetToEdit.current_valuation);
          setLinkedGlAccount(String(assetToEdit.linked_gl_account || ''));
          setSelectedVendorId(assetToEdit.vendor ? String(assetToEdit.vendor) : '');
          setParentAssetId((assetToEdit as any).parent_asset ? String((assetToEdit as any).parent_asset) : '');

          if (assetToEdit.metadata_payload && Object.keys(assetToEdit.metadata_payload).length > 0) {
            const rows = Object.entries(assetToEdit.metadata_payload).map(([k, v]) => ({
              key: k,
              value: String(v ?? ''),
            }));
            setMetadataEntries(rows);
          } else {
            await loadMergedCategorySchema(assetToEdit.category || 'REAL_ESTATE');
          }
        } else {
          setName('');
          setAcquisitionDate(new Date().toISOString().split('T')[0]);
          setAcquisitionCost('');
          setCurrentValuation('');
          setSelectedVendorId('');
          setParentAssetId('');

          const codePrefix = activeTab === 'INCOME' ? 'INC' : activeTab === 'EXPENSE' ? 'EXP' : 'AST';
          setAssetCode(`${codePrefix}-${Math.floor(100 + Math.random() * 900)}`);

          let initialGl = defaultSubcategory || '';
          if (!initialGl && treeRes.length > 0) {
            const firstGroup = treeRes.find((g) =>
              activeTab === 'INCOME'
                ? g.category.toLowerCase().includes('income')
                : activeTab === 'EXPENSE'
                ? g.category.toLowerCase().includes('expense')
                : g.category.toLowerCase().includes('asset')
            );
            if (firstGroup && firstGroup.subcategories.length > 0) {
              const firstSub: any = firstGroup.subcategories[0];
              initialGl = typeof firstSub === 'object' ? firstSub.subcategory : firstSub;
            }
          }

          if (initialGl) {
            await handleGlTaxonomyChange(initialGl);
          }
        }
      })
      .catch((err) => console.error('Failed to load taxonomy tree:', err));
  }, [isOpen, assetToEdit, defaultSubcategory, activeTab]);

  const handleQuickCreateCategory = async () => {
    if (!newCategoryName.trim()) return;
    try {
      const targetCategoryGroup =
        activeTab === 'INCOME' ? 'Income' : activeTab === 'EXPENSE' ? 'Expense' : 'Asset';

      await subledgerApi.createTaxonomyNode({
        category: targetCategoryGroup,
        subcategory: newCategoryName.trim(),
        display_order: 99,
        is_active: true,
      });

      const updatedTree = await subledgerApi.getTaxonomyNodesForSubledger();
      setTaxonomyTree(updatedTree);
      await handleGlTaxonomyChange(newCategoryName.trim());
      setNewCategoryName('');
      setIsCreatingCategory(false);
    } catch (err: any) {
      console.error('Failed to create taxonomy node:', err);
      setError(`Subcategory Creation Failed: ${JSON.stringify(err.response?.data || err.message)}`);
    }
  };

  const handleQuickCreateVendor = async () => {
    if (!newVendorName.trim()) return;
    try {
      const cleanCode = newVendorName.replace(/[^a-zA-Z0-9]/g, '').toUpperCase().slice(0, 10);
      const generatedCode = `VND-${cleanCode}-${Math.floor(100 + Math.random() * 900)}`;

      const created = await subledgerApi.createVendor({
        name: newVendorName.trim(),
        code: generatedCode,
        default_keywords: [newVendorName.trim()],
      });

      setVendors((prev) => [...prev, created]);
      setSelectedVendorId(created.id);
      setNewVendorName('');
      setIsCreatingVendor(false);
    } catch (err: any) {
      console.error('Failed to create vendor:', err.response?.data || err);
      setError(`Party Creation Failed: ${JSON.stringify(err.response?.data || err.message)}`);
    }
  };

  const handleMetadataChange = (index: number, field: 'key' | 'value', val: string) => {
    const updated = [...metadataEntries];
    updated[index][field] = val;
    setMetadataEntries(updated);
  };

  const addMetadataRow = () => {
    setMetadataEntries([...metadataEntries, { key: '', value: '' }]);
  };

  const removeMetadataRow = (index: number) => {
    setMetadataEntries(metadataEntries.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setSaving(true);
    setError(null);

    const metadataPayload: Record<string, any> = {};
    metadataEntries.forEach((row) => {
      if (row.key.trim()) {
        metadataPayload[row.key.trim()] = row.value.trim();
      }
    });

    const cleanGlAccount = linkedGlAccount.trim() ? linkedGlAccount.trim() : null;
    const cleanVendorId = selectedVendorId && selectedVendorId.trim() !== '' ? selectedVendorId : null;
    const cleanParentAssetId = parentAssetId && parentAssetId.trim() !== '' ? parentAssetId : null;

    const resolveCategoryCode = () => {
      if (activeTab === 'INCOME') {
        const cleanGl = linkedGlAccount.toUpperCase();
        if (cleanGl.includes('DIVIDEND')) return 'DIVIDEND_FOLIO';
        return 'RENTAL_STREAM';
      }

      if (activeTab === 'EXPENSE') {
        const cleanGl = linkedGlAccount.toUpperCase();
        if (cleanGl.includes('CHARITY')) return 'CHARITY_RECIPIENT';
        return 'VENDOR_MERCHANT';
      }

      if (linkedGlAccount) {
        const cleanGl = linkedGlAccount.toUpperCase();
        if (cleanGl.includes('FIXED')) return 'FIXED_DEPOSIT';
        if (cleanGl.includes('RECURRING')) return 'RECURRING_DEPOSIT';
        if (cleanGl.includes('MUTUAL') || cleanGl.includes('SHARE')) return 'MARKET_INVESTMENT';
        if (cleanGl.includes('VEHICLE')) return 'VEHICLE';
        if (cleanGl.includes('GOLD')) return 'PRECIOUS_METALS';
        if (cleanGl.includes('INSURANCE')) return 'INSURANCE_PLAN';
      }

      return assetToEdit?.category || 'REAL_ESTATE';
    };

    const payload: any = {
      asset_code: assetCode.trim(),
      name: name.trim(),
      category: resolveCategoryCode(),
      vendor: cleanVendorId,
      parent_asset: activeTab !== 'ASSET' ? cleanParentAssetId : null,
      acquisition_date: acquisitionDate,
      acquisition_cost: Number(acquisitionCost) || 0,
      current_valuation: Number(currentValuation) || 0,
      ownership_type: ownershipType,
      ownership_share_pct: '100.00',
      status,
      linked_gl_account: cleanGlAccount,
      metadata_payload: metadataPayload,
    };

    try {
      if (assetToEdit) {
        await subledgerApi.updateAsset(assetToEdit.id, payload);
      } else {
        await subledgerApi.createAsset(payload);
      }
      onSuccess();
      onClose();
    } catch (err: any) {
      console.error('Save failed - details:', err.response?.data || err);
      if (err.response?.data) {
        const details =
          typeof err.response.data === 'object'
            ? JSON.stringify(err.response.data)
            : String(err.response.data);
        setError(`Save Failed: ${details}`);
      } else {
        setError('Failed to save entity. Check network connection and try again.');
      }
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm font-sans"
      onClick={(e) => {
        e.stopPropagation();
        onClose();
      }}
    >
      <div
        className="w-full max-w-2xl rounded-xl border border-slate-800 bg-slate-900 p-6 shadow-2xl text-slate-100 font-sans max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            {assetToEdit ? '✏️ Edit Sub-Ledger Node' : '➕ Add New Sub-Ledger Node'}
            <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-amber-400 border border-slate-700">
              {activeTab} MODE
            </span>
          </h2>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onClose();
            }}
            className="text-slate-400 hover:text-white cursor-pointer p-1 rounded transition-colors"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <div className="grid grid-cols-12 gap-3">
            <div className="col-span-4">
              <label className="block text-xs text-slate-400 font-mono">Entity Code</label>
              <input
                type="text"
                required
                value={assetCode}
                onChange={(e) => setAssetCode(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs font-mono text-white focus:border-emerald-500 focus:outline-none"
              />
            </div>
            <div className="col-span-8">
              <label className="block text-xs text-slate-400 font-mono">
                {activeTab === 'INCOME' ? 'Income Stream Name' : activeTab === 'EXPENSE' ? 'Expense / Cost Name' : 'Asset Name'}
              </label>
              <input
                type="text"
                required
                placeholder={
                  activeTab === 'INCOME'
                    ? 'e.g. Monthly Salary, Flat 302 Rent, or HDFC FD Interest'
                    : activeTab === 'EXPENSE'
                    ? 'e.g. Electricity Bill, Maintenance, or Groceries'
                    : 'e.g. Kakkanad Flat or HDFC FD #4092'
                }
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none font-mono"
              />
            </div>

            {/* GL TAXONOMY CATEGORY DROPDOWN */}
            <div className="col-span-12">
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-semibold text-amber-400 font-mono">
                  Linked GL Taxonomy Category ({activeTab})
                </label>
                <button
                  type="button"
                  onClick={() => setIsCreatingCategory(!isCreatingCategory)}
                  className="text-[11px] text-emerald-400 hover:underline font-mono cursor-pointer"
                >
                  {isCreatingCategory ? 'Cancel' : '+ New Category'}
                </button>
              </div>

              {isCreatingCategory ? (
                <div className="flex gap-1.5">
                  <input
                    type="text"
                    placeholder={`e.g. ${
                      activeTab === 'INCOME'
                        ? 'Interest Income'
                        : activeTab === 'EXPENSE'
                        ? 'MMC Charges'
                        : 'New Asset Type'
                    }`}
                    value={newCategoryName}
                    onChange={(e) => setNewCategoryName(e.target.value)}
                    className="w-full rounded border border-slate-700 bg-slate-800 p-1.5 text-xs text-white font-mono focus:border-emerald-500 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={handleQuickCreateCategory}
                    className="rounded bg-emerald-600 px-3 py-1 text-xs font-bold text-white hover:bg-emerald-500 font-mono cursor-pointer whitespace-nowrap"
                  >
                    Save
                  </button>
                </div>
              ) : (
                <select
                  value={linkedGlAccount}
                  onChange={(e) => handleGlTaxonomyChange(e.target.value)}
                  className="w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none font-mono cursor-pointer"
                  required
                >
                  <option value="">
                    -- Select GL Category ({filteredTaxonomySubcategories.length} available) --
                  </option>
                  {filteredTaxonomySubcategories.map((item) => (
                    <option key={item.id || item.subcategory} value={item.subcategory}>
                      {item.group} - {item.subcategory}
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div className="col-span-4">
              <label className="block text-xs text-slate-400 font-mono">
                {activeTab === 'INCOME'
                  ? 'Start Date'
                  : activeTab === 'EXPENSE'
                  ? 'Start Date'
                  : 'Acquisition Date'}
              </label>
              <input
                type="date"
                required
                value={acquisitionDate}
                onChange={(e) => setAcquisitionDate(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none font-mono"
              />
            </div>

            <div className="col-span-4">
              <label className="block text-xs text-slate-400 font-mono">
                {activeTab === 'INCOME'
                  ? 'Base Yield (₹)'
                  : activeTab === 'EXPENSE'
                  ? 'Initial Spend (₹)'
                  : 'Acquisition Cost (₹)'}
              </label>
              <input
                type="number"
                required
                value={acquisitionCost}
                onChange={(e) => setAcquisitionCost(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none font-mono"
              />
            </div>

            <div className="col-span-4">
              <label className="block text-xs text-slate-400 font-mono">
                {activeTab === 'INCOME'
                  ? 'Target Annual Income (₹)'
                  : activeTab === 'EXPENSE'
                  ? 'Annual Budget Cap (₹)'
                  : 'Current Valuation (₹)'}
              </label>
              <input
                type="number"
                required
                value={currentValuation}
                onChange={(e) => setCurrentValuation(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none font-mono"
              />
            </div>
          </div>

          {/* VENDOR / PAYER / CLIENT SECTION */}
          <div className="rounded-lg bg-slate-950 p-3 border border-slate-800 font-mono space-y-3">
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-semibold text-sky-400">
                  {activeTab === 'INCOME'
                    ? 'Payer / Client / Source'
                    : activeTab === 'EXPENSE'
                    ? 'Vendor / Merchant'
                    : 'Vendor / Counterparty'}
                </label>
                <button
                  type="button"
                  onClick={() => setIsCreatingVendor(!isCreatingVendor)}
                  className="text-xs text-emerald-400 hover:underline cursor-pointer"
                >
                  {isCreatingVendor ? 'Cancel' : '+ New Party'}
                </button>
              </div>

              {isCreatingVendor ? (
                <div className="mt-2 flex gap-2">
                  <input
                    type="text"
                    placeholder="e.g. Employer Name, Tenant, or Bank"
                    value={newVendorName}
                    onChange={(e) => setNewVendorName(e.target.value)}
                    className="w-full rounded border border-slate-700 bg-slate-900 p-1.5 text-xs text-white font-mono focus:border-emerald-500 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={handleQuickCreateVendor}
                    className="rounded bg-emerald-600 px-3 py-1 text-xs font-semibold text-white hover:bg-emerald-500 font-mono cursor-pointer whitespace-nowrap"
                  >
                    Save
                  </button>
                </div>
              ) : (
                <select
                  value={selectedVendorId}
                  onChange={(e) => handleVendorChange(e.target.value)}
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 p-1.5 text-xs text-white focus:border-emerald-500 focus:outline-none font-mono cursor-pointer"
                >
                  <option value="">-- Independent / Direct Source --</option>
                  {vendors.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.name}
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* 🎯 OPTIONAL: Link to a balance sheet asset (Strictly filtered to ASSETS) */}
            {activeTab !== 'ASSET' && (
              <div className="pt-2 border-t border-slate-800/80">
                <label className="block text-[11px] text-slate-400 mb-1">
                  Linked Balance Sheet Asset <span className="text-slate-500">(Optional)</span>
                </label>
                <select
                  value={parentAssetId}
                  onChange={(e) => setParentAssetId(e.target.value)}
                  className="w-full rounded border border-slate-800 bg-slate-900 p-1.5 text-xs text-slate-300 focus:border-emerald-500 focus:outline-none font-mono cursor-pointer"
                >
                  <option value="">-- None / Standalone Income Stream --</option>
                  {availableParentAssets.map((ast) => (
                    <option key={ast.id} value={ast.id}>
                      [{ast.asset_code}] {ast.name} ({ast.category_display || ast.category})
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* DYNAMIC METADATA ATTRIBUTES */}
          <div className="rounded-lg bg-slate-950 p-3 border border-slate-800 font-mono">
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs font-bold text-slate-400 uppercase">
                Dynamic Metadata Attributes (JSON)
              </span>
              <button
                type="button"
                onClick={addMetadataRow}
                className="text-xs text-emerald-400 hover:underline cursor-pointer"
              >
                + Add Key/Value
              </button>
            </div>

            <div className="space-y-2">
              {metadataEntries.map((row, idx) => (
                <div key={idx} className="flex gap-2 items-center">
                  <input
                    type="text"
                    placeholder="Key (e.g. account_no or frequency)"
                    value={row.key}
                    onChange={(e) => handleMetadataChange(idx, 'key', e.target.value)}
                    className="w-1/2 rounded border border-slate-800 bg-slate-900 p-1.5 text-xs text-white font-mono"
                  />
                  <input
                    type="text"
                    placeholder="Value (e.g. 1029384)"
                    value={row.value}
                    onChange={(e) => handleMetadataChange(idx, 'value', e.target.value)}
                    className="w-1/2 rounded border border-slate-800 bg-slate-900 p-1.5 text-xs text-white font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => removeMetadataRow(idx)}
                    className="text-slate-500 hover:text-rose-400 text-xs px-1 cursor-pointer"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          </div>

          {error && (
            <p className="text-xs text-rose-400 font-mono bg-rose-500/10 p-2 rounded border border-rose-500/20">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 border-t border-slate-800 pt-3">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onClose();
              }}
              className="rounded bg-slate-800 px-4 py-2 text-xs text-slate-300 hover:bg-slate-700 cursor-pointer font-mono"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 cursor-pointer font-mono"
            >
              {saving ? 'Saving...' : assetToEdit ? 'Update Node' : `Create ${activeTab} Stream`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};