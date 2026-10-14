import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  subledgerApi,
  type AssetSubLedgerNode,
  type OwnershipType,
  type AssetStatusType,
  type SubledgerTaxonomyGroup,
  type Vendor,
  type AssetCategoryType,
  type AssetSubLedgerPayload,
} from '../../api/subledger';
import {
  CATEGORY_DYNAMIC_SCHEMAS,
  type FieldDefinition,
} from '../ui/categorySchemaRegistry';

import { PartySelectorSection } from './assetform/modalParts/PartSelectorSection';
import { MetadataAttributesSection, type MetadataRow } from './assetform/modalParts/MetadataAttributesSection';
import { FinancialInputsSection } from './assetform/modalParts/FinancialInputsSection';

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
  // --- Core State ---
  const [assetCode, setAssetCode] = useState('AST-001');
  const [name, setName] = useState('');
  const [parentAssetId, setParentAssetId] = useState<string>('');
  const [allAssets, setAllAssets] = useState<AssetSubLedgerNode[]>([]);

  // --- Financials & Status ---
  const [acquisitionDate, setAcquisitionDate] = useState<string>(new Date().toISOString().split('T')[0]);
  const [acquisitionCost, setAcquisitionCost] = useState<number | string>('');
  const [currentValuation, setCurrentValuation] = useState<number | string>('');
  const [acquisitionFundingSource, setAcquisitionFundingSource] = useState<string>('BANK_STAGING');
  const [ownershipType] = useState<OwnershipType>('INDIVIDUAL');
  const [status, setStatus] = useState<AssetStatusType>('ACTIVE');
  const [isMatured, setIsMatured] = useState<boolean>(false);

  // --- Taxonomy & Schema ---
  const [linkedGlAccount, setLinkedGlAccount] = useState<string>('');
  const [selectedCategoryCode, setSelectedCategoryCode] = useState<string>('');
  const [taxonomyTree, setTaxonomyTree] = useState<SubledgerTaxonomyGroup[]>([]);
  const [metadataEntries, setMetadataEntries] = useState<MetadataRow[]>([]);
  const [categoryChoices, setCategoryChoices] = useState<{ code: string; label: string }[]>([]);

  // --- Vendors & Category Creation ---
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [selectedVendorId, setSelectedVendorId] = useState<string>('');
  const [isCreatingCategory, setIsCreatingCategory] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState('');

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasHydratedRef = useRef(false);

  const currentMode = useMemo(() => {
    if (assetToEdit) {
      const editNode = assetToEdit as Record<string, any>;
      const typeStr = String(
        assetToEdit.asset_category_detail?.default_taxonomy_category ||
          editNode.category_type ||
          editNode.category_detail?.category_type ||
          ''
      ).toUpperCase();

      if (typeStr.includes('INCOME') || assetToEdit.asset_code?.startsWith('INC-')) return 'INCOME';
      if (typeStr.includes('EXPENSE') || assetToEdit.asset_code?.startsWith('EXP-')) return 'EXPENSE';
      if (typeStr.includes('ASSET') || assetToEdit.asset_code?.startsWith('AST-')) return 'ASSET';
    }
    return activeTab || 'ASSET';
  }, [assetToEdit, activeTab]);

  const masterAssetsOnly = useMemo(() => {
    return allAssets.filter((ast: any) => {
      if (assetToEdit && String(ast.id) === String(assetToEdit.id)) return false;
      const catType = String(ast.category_type || ast.category_detail?.category_type || 'ASSET').toUpperCase();
      const isIncOrExp = catType === 'INCOME' || catType === 'EXPENSE' || String(ast.asset_code || '').startsWith('INC-') || String(ast.asset_code || '').startsWith('EXP-');
      const parentId = ast.parent_asset_id || ast.parent_asset?.id || ast.parent_asset;
      return catType === 'ASSET' && !isIncOrExp && !parentId;
    });
  }, [allAssets, assetToEdit]);

  const filteredTaxonomySubcategories = useMemo(() => {
    const targetGroup = String(currentMode).trim().toLowerCase();
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
          category_code: typeof sub === 'object' ? sub.category_code || sub.code || sub.asset_category_code || null : null,
          group: group.category,
        }))
      );
  }, [taxonomyTree, currentMode]);

  const loadMergedCategorySchema = useCallback(async (catCode: string) => {
    const localSchema = CATEGORY_DYNAMIC_SCHEMAS[catCode] || [];
    const keySet = new Set<string>();
    const rows: MetadataRow[] = [];

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
      console.error('Failed to fetch category schema keys:', err);
    }

    setMetadataEntries(rows.length > 0 ? rows : [{ key: '', value: '' }]);
  }, []);

  const handleGlTaxonomyChange = useCallback(async (newGlSubcategory: string) => {
    setLinkedGlAccount(newGlSubcategory);
    if (!newGlSubcategory) return;

    const matchedItem = filteredTaxonomySubcategories.find((item) => item.subcategory === newGlSubcategory);
    const code = matchedItem?.category_code || newGlSubcategory.toUpperCase().replace(/^(INCOME|EXPENSE|ASSET)\s*-\s*/, '').replace(/[^A-Z0-9]/g, '_').replace(/_+/g, '_');
    setSelectedCategoryCode(code);
    await loadMergedCategorySchema(code);
  }, [filteredTaxonomySubcategories, loadMergedCategorySchema]);

  const generateDynamicCode = useCallback((prefix: string, vendorNameStr?: string) => {
    const codePrefix = prefix === 'INCOME' ? 'INC' : prefix === 'EXPENSE' ? 'EXP' : 'AST';
    const cleanVendor = vendorNameStr ? vendorNameStr.replace(/[^a-zA-Z0-9]/g, '').slice(0, 4).toUpperCase() : 'GEN';
    return `${codePrefix}-${cleanVendor || 'GEN'}-${Math.floor(1000 + Math.random() * 9000)}`;
  }, []);

  useEffect(() => {
    if (!isOpen) {
      hasHydratedRef.current = false;
      return;
    }
    if (hasHydratedRef.current) return;
    hasHydratedRef.current = true;

    Promise.all([
      subledgerApi.getVendors().catch(() => []),
      subledgerApi.getAssets().catch(() => []),
      subledgerApi.getTaxonomyNodesForSubledger().catch(() => []),
      subledgerApi.getCategoryChoices().catch(() => []),
    ]).then(async ([vList, aList, treeRes, choicesRes]) => {
      setVendors(vList);
      setAllAssets(aList);
      setTaxonomyTree(treeRes);
      setCategoryChoices(choicesRes);

      if (assetToEdit) {
        setAssetCode(assetToEdit.asset_code);
        setName(assetToEdit.name);
        setAcquisitionDate(assetToEdit.acquisition_date ? assetToEdit.acquisition_date.split('T')[0] : new Date().toISOString().split('T')[0]);
        setAcquisitionCost(assetToEdit.acquisition_cost);
        setCurrentValuation(assetToEdit.current_valuation);
        setAcquisitionFundingSource((assetToEdit as any).acquisition_funding_source || 'BANK_STAGING');
        setStatus((assetToEdit.status as AssetStatusType) || 'ACTIVE');
        setIsMatured(assetToEdit.status === 'MATURED' || assetToEdit.status === 'LIQUIDATED');
        setLinkedGlAccount(String(assetToEdit.linked_gl_account || ''));
        setSelectedCategoryCode(assetToEdit.category || '');
        setSelectedVendorId(assetToEdit.vendor ? String(assetToEdit.vendor) : '');
        setParentAssetId((assetToEdit as any).parent_asset ? String((assetToEdit as any).parent_asset) : '');

        if (assetToEdit.metadata_payload && Object.keys(assetToEdit.metadata_payload).length > 0) {
          setMetadataEntries(Object.entries(assetToEdit.metadata_payload).map(([k, v]) => ({ key: k, value: String(v ?? '') })));
        } else {
          await loadMergedCategorySchema(assetToEdit.category || 'REAL_ESTATE');
        }
      } else {
        setName('');
        setAcquisitionDate(new Date().toISOString().split('T')[0]);
        setAcquisitionCost('');
        setCurrentValuation('');
        setAcquisitionFundingSource('BANK_STAGING');
        setStatus('ACTIVE');
        setIsMatured(false);
        setSelectedVendorId('');
        setParentAssetId('');
        setSelectedCategoryCode('');
        setAssetCode(generateDynamicCode(currentMode));

        const initialGl = defaultSubcategory || '';
        if (initialGl) handleGlTaxonomyChange(initialGl);
      }
    });
  }, [isOpen, assetToEdit, defaultSubcategory, currentMode, generateDynamicCode, handleGlTaxonomyChange, loadMergedCategorySchema]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);

    const metadataPayload: Record<string, any> = {};
    metadataEntries.forEach((row) => {
      if (row.key.trim() && row.value.trim() !== '') metadataPayload[row.key.trim()] = row.value.trim();
    });

    const matchedChoice = categoryChoices.find(
      (c) => c.code === selectedCategoryCode || c.label.toLowerCase().includes(linkedGlAccount.toLowerCase())
    );

    const resolvedCategory = (matchedChoice?.code || (currentMode === 'INCOME' ? 'RENTAL_STREAM' : currentMode === 'EXPENSE' ? 'VENDOR_MERCHANT' : 'REAL_ESTATE')) as AssetCategoryType;

    const payload: AssetSubLedgerPayload & { acquisition_funding_source?: string } = {
      asset_code: assetCode.trim(),
      name: name.trim(),
      category: resolvedCategory,
      vendor: selectedVendorId.trim() || null,
      parent_asset: parentAssetId.trim() || null,
      acquisition_date: acquisitionDate,
      acquisition_cost: Number(acquisitionCost) || 0,
      current_valuation: isMatured ? 0 : Number(currentValuation) || 0,
      acquisition_funding_source: acquisitionFundingSource,
      ownership_type: ownershipType,
      ownership_share_pct: '100.00',
      status: isMatured ? 'MATURED' : status,
      linked_gl_account: linkedGlAccount.trim() || null,
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
      setError(`Save Failed: ${JSON.stringify(err.response?.data || err.message)}`);
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm font-sans" onClick={onClose}>
      <div className="w-full max-w-2xl rounded-xl border border-slate-800 bg-slate-900 p-6 shadow-2xl text-slate-100 max-h-[92vh] overflow-y-auto font-mono" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3 font-sans">
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            {assetToEdit ? '✏️ Edit Sub-Ledger Node' : '➕ Register Asset Folio'}
            <span className="text-xs font-mono px-2 py-0.5 rounded border bg-emerald-950/80 text-emerald-300 border-emerald-800">
              {currentMode} MODE
            </span>
          </h2>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-white cursor-pointer p-1">✕</button>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <div className="grid grid-cols-12 gap-3">
            <div className="col-span-4">
              <label className="block text-xs text-slate-400">Entity Code</label>
              <input type="text" required value={assetCode} onChange={(e) => setAssetCode(e.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white" />
            </div>

            <div className="col-span-8">
              <label className="block text-xs text-slate-400">Folio / Asset Name</label>
              <input type="text" required placeholder="e.g. Flat 101, Swasthi, or 22CT Gold Chain" value={name} onChange={(e) => setName(e.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white" />
            </div>

            {/* Linked GL Category Dropdown */}
            <div className="col-span-12">
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-semibold text-amber-400">Linked GL Taxonomy Head ({currentMode})</label>
                <button type="button" onClick={() => setIsCreatingCategory(!isCreatingCategory)} className="text-[11px] text-emerald-400 hover:underline cursor-pointer">
                  {isCreatingCategory ? 'Cancel' : '+ New Category'}
                </button>
              </div>

              {isCreatingCategory ? (
                <div className="flex gap-1.5">
                  <input type="text" placeholder="e.g. Commercial Real Estate" value={newCategoryName} onChange={(e) => setNewCategoryName(e.target.value)} className="w-full rounded border border-slate-700 bg-slate-800 p-1.5 text-xs text-white" />
                  <button type="button" onClick={async () => {
                    await subledgerApi.createTaxonomyNode({ category: currentMode === 'INCOME' ? 'Income' : currentMode === 'EXPENSE' ? 'Expense' : 'Asset', subcategory: newCategoryName.trim(), display_order: 99, is_active: true });
                    const tree = await subledgerApi.getTaxonomyNodesForSubledger();
                    setTaxonomyTree(tree);
                    handleGlTaxonomyChange(newCategoryName.trim());
                    setIsCreatingCategory(false);
                  }} className="rounded bg-emerald-600 px-3 py-1 text-xs font-bold text-white hover:bg-emerald-500 cursor-pointer">Save</button>
                </div>
              ) : (
                <select value={linkedGlAccount} onChange={(e) => handleGlTaxonomyChange(e.target.value)} className="w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white cursor-pointer" required>
                  <option value="">-- Select GL Head ({filteredTaxonomySubcategories.length} available) --</option>
                  {filteredTaxonomySubcategories.map((item) => (
                    <option key={item.id || item.subcategory} value={item.subcategory}>
                      {item.group} ➔ {item.subcategory}
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Financial Inputs Section */}
            <FinancialInputsSection
              currentMode={currentMode}
              acquisitionDate={acquisitionDate}
              setAcquisitionDate={setAcquisitionDate}
              acquisitionCost={acquisitionCost}
              setAcquisitionCost={setAcquisitionCost}
              currentValuation={currentValuation}
              setCurrentValuation={setCurrentValuation}
              acquisitionFundingSource={acquisitionFundingSource}
              setAcquisitionFundingSource={setAcquisitionFundingSource}
              isMatured={isMatured}
            />
          </div>

          {/* Party Selector Section */}
          <PartySelectorSection
            currentMode={currentMode}
            vendors={vendors}
            selectedVendorId={selectedVendorId}
            onSelectVendor={(vId) => {
              setSelectedVendorId(vId);
              const vObj = vendors.find((v) => String(v.id) === String(vId));
              if (!assetToEdit) setAssetCode(generateDynamicCode(currentMode, vObj?.name));
            }}
            onQuickCreateVendor={async (partyName) => {
              const cleanCode = partyName.replace(/[^a-zA-Z0-9]/g, '').toUpperCase().slice(0, 10);
              const created = await subledgerApi.createVendor({ name: partyName, code: `VND-${cleanCode}-${Math.floor(100 + Math.random() * 900)}`, default_keywords: [partyName] });
              setVendors((prev) => [...prev, created]);
              setSelectedVendorId(created.id);
            }}
            masterAssets={masterAssetsOnly}
            parentAssetId={parentAssetId}
            onSelectParentAsset={setParentAssetId}
          />

          {/* Dynamic Metadata Attributes Section */}
          <MetadataAttributesSection
            entries={metadataEntries}
            onChange={(idx, field, val) => {
              setMetadataEntries((prev) => {
                const updated = [...prev];
                updated[idx][field] = val;
                return updated;
              });
            }}
            onAdd={() => setMetadataEntries((prev) => [...prev, { key: '', value: '' }])}
            onRemove={(idx) => setMetadataEntries((prev) => prev.filter((_, i) => i !== idx))}
          />

          {error && <p className="text-xs text-rose-400 bg-rose-500/10 p-2 rounded border border-rose-500/20">{error}</p>}

          <div className="flex justify-end gap-2 border-t border-slate-800 pt-3">
            <button type="button" onClick={onClose} className="rounded bg-slate-800 px-4 py-2 text-xs text-slate-300 hover:bg-slate-700 cursor-pointer">Cancel</button>
            <button type="submit" disabled={saving} className="rounded bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 cursor-pointer">
              {saving ? 'Saving...' : assetToEdit ? 'Update Folio' : 'Register Folio'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};