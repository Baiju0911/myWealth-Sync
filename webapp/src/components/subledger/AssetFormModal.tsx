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

interface AssetFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  assetToEdit?: AssetSubLedgerNode | null;
  defaultSubcategory?: string | null;
  activeTab?: 'ASSET' | 'INCOME' | 'EXPENSE';
  onSuccess: () => void;
}

interface MetadataRow {
  key: string;
  value: string;
}

// 🟢 Acquisition Funding Choices Mapping
const FUNDING_SOURCE_OPTIONS = [
  { value: 'BANK_STAGING', label: '🏦 Bank Line (Reconciled via Staging)' },
  { value: 'DIRECT_CASH', label: '💵 Direct Cash / Manual (Bank Row Missing)' },
  { value: 'HISTORICAL_OPENING', label: '📜 Historical / Opening Balance (Pre-System Asset)' },
  { value: 'GIFTS_INHERITANCE', label: '🎁 Gift / Family Inheritance (Non-Cash Capital)' },
  { value: 'OTHER', label: '📁 Other / Manual Adjustment' },
];

export const AssetFormModal: React.FC<AssetFormModalProps> = ({
  isOpen,
  onClose,
  assetToEdit,
  defaultSubcategory,
  activeTab = 'ASSET',
  onSuccess,
}) => {
  // --- Core Entity State ---
  const [assetCode, setAssetCode] = useState('AST-001');
  const [name, setName] = useState('');
  const [parentAssetId, setParentAssetId] = useState<string>('');
  const [allAssets, setAllAssets] = useState<AssetSubLedgerNode[]>([]);

  // --- Financials, Dates & Status ---
  const [acquisitionDate, setAcquisitionDate] = useState<string>(
    new Date().toISOString().split('T')[0]
  );
  const [acquisitionCost, setAcquisitionCost] = useState<number | string>('');
  const [currentValuation, setCurrentValuation] = useState<number | string>('');
  
  // 🟢 NEW STATE: Acquisition Funding Source
  const [acquisitionFundingSource, setAcquisitionFundingSource] = useState<string>('BANK_STAGING');

  const [ownershipType] = useState<OwnershipType>('INDIVIDUAL');
  const [status, setStatus] = useState<AssetStatusType>('ACTIVE');
  const [isMatured, setIsMatured] = useState<boolean>(false);

  // --- GL Account & Taxonomy State ---
  const [linkedGlAccount, setLinkedGlAccount] = useState<string>('');
  const [selectedCategoryCode, setSelectedCategoryCode] = useState<string>(''); // DB Choice Key
  const [taxonomyTree, setTaxonomyTree] = useState<SubledgerTaxonomyGroup[]>([]);
  const [metadataEntries, setMetadataEntries] = useState<MetadataRow[]>([]);

  const [categoryChoices, setCategoryChoices] = useState<{ code: string; label: string }[]>([]);

  // --- Vendors & Parties ---
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [selectedVendorId, setSelectedVendorId] = useState<string>('');
  const [newVendorName, setNewVendorName] = useState<string>('');
  const [isCreatingVendor, setIsCreatingVendor] = useState(false);

  // --- Quick-Create Taxonomy State ---
  const [isCreatingCategory, setIsCreatingCategory] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState('');

  // --- Submission Flags ---
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Guard against infinite API fetch loops
  const hasHydratedRef = useRef(false);

  // 1. Context Mode Resolution
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

  // 2. Base Parent Candidates (Prevents self-referencing)
  const baseParentCandidates = useMemo(() => {
    return allAssets.filter((ast: Record<string, any>) => {
      if (assetToEdit && String(ast.id) === String(assetToEdit.id)) return false;

      const catType = String(
        ast.category_type || ast.category_detail?.category_type || 'ASSET'
      ).toUpperCase();

      const isIncomeOrExpense =
        catType === 'INCOME' ||
        catType === 'EXPENSE' ||
        String(ast.asset_code || '').startsWith('INC-') ||
        String(ast.asset_code || '').startsWith('EXP-');

      return catType === 'ASSET' && !isIncomeOrExpense;
    });
  }, [allAssets, assetToEdit]);

  // 3. Resolve Master Entities Only (Excludes child sub-nodes)
  const masterAssetsOnly = useMemo(() => {
    return baseParentCandidates.filter((a: any) => {
      const parentId = a.parent_asset_id || a.parent_asset?.id || a.parent_asset;
      return !parentId;
    });
  }, [baseParentCandidates]);

  // 4. Contextual Vendor Filter for Master Assets Dropdown
  const filteredMasterAssets = useMemo(() => {
    if (!selectedVendorId) return masterAssetsOnly;

    const vendorMatched = masterAssetsOnly.filter((a: any) => {
      const vId = a.vendor_id || a.vendor_detail?.id || a.vendor;
      return String(vId) === String(selectedVendorId);
    });

    return vendorMatched.length > 0 ? vendorMatched : masterAssetsOnly;
  }, [masterAssetsOnly, selectedVendorId]);

  // 5. Dynamic Taxonomy Subcategory Filtering
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
          category_code:
            typeof sub === 'object'
              ? sub.category_code || sub.code || sub.asset_category_code || null
              : null,
          group: group.category,
        }))
      );
  }, [taxonomyTree, currentMode]);

  // Schema Loader
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

  // Direct Taxonomy Handler: Captures Subcategory and DB Choice Code together
  const handleGlTaxonomyChange = useCallback(async (newGlSubcategory: string) => {
    setLinkedGlAccount(newGlSubcategory);
    if (!newGlSubcategory) return;

    const matchedItem = filteredTaxonomySubcategories.find(
      (item) => item.subcategory === newGlSubcategory
    );

    if (matchedItem?.category_code) {
      setSelectedCategoryCode(matchedItem.category_code);
      await loadMergedCategorySchema(matchedItem.category_code);
    } else {
      const cleanCode = newGlSubcategory
        .toUpperCase()
        .replace(/^(INCOME|EXPENSE|ASSET)\s*-\s*/, '')
        .replace(/[^A-Z0-9]/g, '_')
        .replace(/_+/g, '_');
      setSelectedCategoryCode(cleanCode);
      await loadMergedCategorySchema(cleanCode);
    }
  }, [filteredTaxonomySubcategories, loadMergedCategorySchema]);

  // Code Generator Helper
  const generateDynamicCode = useCallback((prefix: string, vendorNameStr?: string) => {
    const codePrefix = prefix === 'INCOME' ? 'INC' : prefix === 'EXPENSE' ? 'EXP' : 'AST';
    const cleanVendor = vendorNameStr 
      ? vendorNameStr.replace(/[^a-zA-Z0-9]/g, '').slice(0, 4).toUpperCase()
      : 'GEN';
    const randomSuffix = Math.floor(1000 + Math.random() * 9000);
    return `${codePrefix}-${cleanVendor || 'GEN'}-${randomSuffix}`;
  }, []);

  const handleVendorChange = (vendorId: string) => {
    setSelectedVendorId(vendorId);
    const vObj = vendors.find((v) => String(v.id) === String(vendorId));
    if (!assetToEdit) {
      setAssetCode(generateDynamicCode(currentMode, vObj?.name));
    }
  };

  const handleMaturityToggle = (matured: boolean) => {
    setIsMatured(matured);
    if (matured) {
      setCurrentValuation('0.00');
      setStatus('MATURED');
    } else {
      setStatus('ACTIVE');
    }
  };

  // Keyboard Shortcuts (ESC Close)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Modal Hydration & State Reset (Runs ONCE per open session)
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
        setAcquisitionDate(
          assetToEdit.acquisition_date
            ? assetToEdit.acquisition_date.split('T')[0]
            : new Date().toISOString().split('T')[0]
        );
        setAcquisitionCost(assetToEdit.acquisition_cost);
        setCurrentValuation(assetToEdit.current_valuation);
        
        // 🟢 Hydrate acquisition_funding_source
        setAcquisitionFundingSource(
          (assetToEdit as any).acquisition_funding_source || 'BANK_STAGING'
        );

        setStatus((assetToEdit.status as AssetStatusType) || 'ACTIVE');
        setIsMatured(assetToEdit.status === 'MATURED' || assetToEdit.status === 'LIQUIDATED');
        setLinkedGlAccount(String(assetToEdit.linked_gl_account || ''));
        setSelectedCategoryCode(assetToEdit.category || '');
        setSelectedVendorId(assetToEdit.vendor ? String(assetToEdit.vendor) : '');
        setParentAssetId((assetToEdit as any).parent_asset ? String((assetToEdit as any).parent_asset) : '');

        if (assetToEdit.metadata_payload && Object.keys(assetToEdit.metadata_payload).length > 0) {
          setMetadataEntries(
            Object.entries(assetToEdit.metadata_payload).map(([k, v]) => ({
              key: k,
              value: String(v ?? ''),
            }))
          );
        } else {
          await loadMergedCategorySchema(assetToEdit.category || 'REAL_ESTATE');
        }
      } else {
        setName('');
        setAcquisitionDate(new Date().toISOString().split('T')[0]);
        setAcquisitionCost('');
        setCurrentValuation('');
        setAcquisitionFundingSource('BANK_STAGING'); // Reset choice
        setStatus('ACTIVE');
        setIsMatured(false);
        setSelectedVendorId('');
        setParentAssetId('');
        setSelectedCategoryCode('');

        setAssetCode(generateDynamicCode(currentMode));

        let initialGl = defaultSubcategory || '';
        if (!initialGl && treeRes.length > 0) {
          const firstGroup = treeRes.find((g) =>
            currentMode === 'INCOME'
              ? g.category.toLowerCase().includes('income')
              : currentMode === 'EXPENSE'
              ? g.category.toLowerCase().includes('expense')
              : g.category.toLowerCase().includes('asset')
          );
          if (firstGroup && firstGroup.subcategories.length > 0) {
            const firstSub: any = firstGroup.subcategories[0];
            initialGl = typeof firstSub === 'object' ? firstSub.subcategory : firstSub;
          }
        }

        if (initialGl) {
          setLinkedGlAccount(initialGl);
        }
      }
    });
  }, [isOpen, assetToEdit, defaultSubcategory, currentMode, loadMergedCategorySchema, generateDynamicCode]);

  const handleQuickCreateCategory = async () => {
    if (!newCategoryName.trim()) return;
    try {
      const targetCategoryGroup =
        currentMode === 'INCOME' ? 'Income' : currentMode === 'EXPENSE' ? 'Expense' : 'Asset';

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
      setError(`Party Creation Failed: ${JSON.stringify(err.response?.data || err.message)}`);
    }
  };

  const handleMetadataChange = (index: number, field: 'key' | 'value', val: string) => {
    setMetadataEntries((prev) => {
      const updated = [...prev];
      updated[index][field] = val;
      return updated;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setSaving(true);
    setError(null);

    const metadataPayload: Record<string, any> = {};
    metadataEntries.forEach((row) => {
      const k = row.key.trim();
      const v = row.value.trim();
      if (k && v !== '') metadataPayload[k] = v;
    });

    const matchedChoice = categoryChoices.find(
      (c) =>
        c.code === selectedCategoryCode ||
        c.label.toLowerCase().includes(linkedGlAccount.toLowerCase()) ||
        linkedGlAccount.toLowerCase().includes(c.label.toLowerCase())
    );

    const resolvedCategory = (
      matchedChoice?.code ||
      (currentMode === 'INCOME'
        ? 'RENTAL_STREAM'
        : currentMode === 'EXPENSE'
        ? 'VENDOR_MERCHANT'
        : 'REAL_ESTATE')
    ) as AssetCategoryType;

    const payload: AssetSubLedgerPayload & { acquisition_funding_source?: string } = {
      asset_code: assetCode.trim(),
      name: name.trim(),
      category: resolvedCategory,
      vendor: selectedVendorId.trim() || null,
      parent_asset: parentAssetId.trim() || null,
      acquisition_date: acquisitionDate,
      acquisition_cost: Number(acquisitionCost) || 0,
      current_valuation: isMatured ? 0 : Number(currentValuation) || 0,
      
      // 🟢 Pass acquisition_funding_source to payload
      acquisition_funding_source: acquisitionFundingSource,

      ownership_type: ownershipType,
      ownership_share_pct: '100.00',
      status: isMatured ? 'MATURED' : status,
      linked_gl_account: linkedGlAccount.trim() || null,
      metadata_payload: metadataPayload,
    };

    try {
      let savedNode: AssetSubLedgerNode;
      if (assetToEdit) {
        savedNode = await subledgerApi.updateAsset(assetToEdit.id, payload);
      } else {
        savedNode = await subledgerApi.createAsset(payload);
      }

      if (currentMode === 'ASSET' && isMatured && savedNode?.id) {
        try {
          const freshNodes = await subledgerApi.getAssets();
          const childStreams = freshNodes.filter(
            (node: any) => String((node as any).parent_asset) === String(savedNode.id)
          );

          await Promise.all(
            childStreams.map((stream) =>
              subledgerApi.updateAsset(stream.id, {
                status: 'MATURED',
                current_valuation: 0,
              })
            )
          );
        } catch (cascadeErr) {
          console.error('Failed to cascade closure:', cascadeErr);
        }
      }

      onSuccess();
      onClose();
    } catch (err: any) {
      console.error('❌ BACKEND RESPONSE ERROR:', {
        status: err.response?.status,
        data: err.response?.data,
        message: err.message,
      });

      const details = err.response?.data
        ? typeof err.response.data === 'object'
          ? JSON.stringify(err.response.data)
          : String(err.response.data)
        : 'Failed to save entity.';
      setError(`Save Failed: ${details}`);
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
        className="w-full max-w-2xl rounded-xl border border-slate-800 bg-slate-900 p-6 shadow-2xl text-slate-100 max-h-[90vh] overflow-y-auto font-mono"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-800 pb-3 font-sans">
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            {assetToEdit ? '✏️ Edit Sub-Ledger Node' : '➕ Add New Sub-Ledger Node'}
            <span
              className={`text-xs font-mono px-2 py-0.5 rounded border ${
                currentMode === 'INCOME'
                  ? 'bg-cyan-950/80 text-cyan-300 border-cyan-800'
                  : currentMode === 'EXPENSE'
                  ? 'bg-rose-950/80 text-rose-300 border-rose-800'
                  : 'bg-emerald-950/80 text-emerald-300 border-emerald-800'
              }`}
            >
              {currentMode} MODE
            </span>
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white cursor-pointer p-1 rounded transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Lifecycle Banner */}
        <div className="mt-4 rounded-lg bg-slate-950 p-3 border border-slate-800 font-mono flex items-center justify-between">
          <div>
            <span className="text-xs font-bold text-slate-200 block">
              Lifecycle Status: {isMatured ? '🏁 MATURED / CLOSED' : '⚡ ACTIVE'}
            </span>
            <p className="text-[10px] text-slate-500 mt-0.5">
              {currentMode === 'ASSET'
                ? 'Marking as matured resets valuation to ₹0 and closes linked income streams.'
                : 'Closes this yield stream and marks it fully realized.'}
            </p>
          </div>

          <button
            type="button"
            onClick={() => handleMaturityToggle(!isMatured)}
            className={`px-3 py-1.5 rounded text-xs font-bold cursor-pointer transition-all shrink-0 ${
              isMatured
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 hover:bg-amber-500 hover:text-slate-950'
                : 'bg-slate-800 text-slate-400 hover:bg-rose-950 hover:text-rose-300 border border-slate-700'
            }`}
          >
            {isMatured ? 'Re-open Node' : '🏁 Mark as Matured'}
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
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none font-mono"
              />
            </div>

            <div className="col-span-8">
              <label className="block text-xs text-slate-400 font-mono">
                {currentMode === 'INCOME' ? 'Income Stream Name' : currentMode === 'EXPENSE' ? 'Expense / Cost Name' : 'Asset Name'}
              </label>
              <input
                type="text"
                required
                placeholder={
                  currentMode === 'INCOME'
                    ? 'e.g. Monthly Salary or Flat 302 Rent'
                    : currentMode === 'EXPENSE'
                    ? 'e.g. Electricity Bill or Maintenance'
                    : 'e.g. Kakkanad Flat or HDFC FD #4092'
                }
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none font-mono"
              />
            </div>

            {/* GL Taxonomy Category Dropdown */}
            <div className="col-span-12">
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-semibold text-amber-400 font-mono">
                  Linked GL Taxonomy Category ({currentMode})
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
                    placeholder="e.g. Interest Income or MMC Charges"
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
              <label className="block text-xs text-slate-400 font-mono">Start / Acquisition Date</label>
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
                {currentMode === 'INCOME' ? 'Base Yield (₹)' : currentMode === 'EXPENSE' ? 'Initial Spend (₹)' : 'Acquisition Cost (₹)'}
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
                {currentMode === 'INCOME' ? 'Target Annual Income (₹)' : currentMode === 'EXPENSE' ? 'Annual Budget Cap (₹)' : 'Current Valuation (₹)'}
              </label>
              <input
                type="number"
                required
                disabled={isMatured}
                value={isMatured ? '0.00' : currentValuation}
                onChange={(e) => setCurrentValuation(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none font-mono disabled:opacity-50"
              />
            </div>

            {/* 🟢 NEW FIELD: Acquisition Funding Origin Selector */}
            <div className="col-span-12">
              <label className="block text-xs font-semibold text-emerald-400 font-mono mb-1">
                Acquisition Funding Origin / Bank Row Status
              </label>
              <select
                value={acquisitionFundingSource}
                onChange={(e) => setAcquisitionFundingSource(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-emerald-300 font-bold focus:border-emerald-500 focus:outline-none font-mono cursor-pointer"
              >
                {FUNDING_SOURCE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <p className="text-[10px] text-slate-500 mt-1 font-mono">
                {acquisitionFundingSource === 'BANK_STAGING'
                  ? 'Cost baseline is backed by imported bank staging statements.'
                  : 'Flags this node with `is_bank_row_missing = True` to allow direct cash or opening balance mapping on balance sheets.'}
              </p>
            </div>
          </div>

          {/* Vendors & Relationships Section */}
          <div className="rounded-lg bg-slate-950 p-3 border border-slate-800 font-mono space-y-3">
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-semibold text-sky-400">
                  {currentMode === 'INCOME' ? 'Payer / Client / Source' : 'Vendor / Counterparty'}
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

            {/* Master Entities Only Dropdown */}
            {filteredMasterAssets.length > 0 && (
              <div className="pt-2 border-t border-slate-800/80">
                <label className="block text-[11px] text-slate-400 mb-1">
                  Linked Balance Sheet Asset <span className="text-slate-500">(Optional Master Parent Entity)</span>
                </label>
                <select
                  value={parentAssetId}
                  onChange={(e) => setParentAssetId(e.target.value)}
                  className="w-full rounded border border-slate-800 bg-slate-900 p-1.5 text-xs text-slate-300 focus:border-emerald-500 focus:outline-none font-mono cursor-pointer"
                >
                  <option value="">-- None / Standalone Master Entity --</option>
                  {filteredMasterAssets.map((ast) => (
                    <option key={ast.id} value={ast.id}>
                      [{ast.asset_code}] {ast.name} ({ast.category_display || ast.category})
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* Dynamic Metadata Attributes */}
          <div className="rounded-lg bg-slate-950 p-3 border border-slate-800 font-mono">
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs font-bold text-slate-400 uppercase">Dynamic Metadata Attributes (JSON)</span>
              <button
                type="button"
                onClick={() => setMetadataEntries((prev) => [...prev, { key: '', value: '' }])}
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
                    placeholder="Key"
                    value={row.key}
                    onChange={(e) => handleMetadataChange(idx, 'key', e.target.value)}
                    className="w-1/2 rounded border border-slate-800 bg-slate-900 p-1.5 text-xs text-white font-mono"
                  />
                  <input
                    type="text"
                    placeholder="Value"
                    value={row.value}
                    onChange={(e) => handleMetadataChange(idx, 'value', e.target.value)}
                    className="w-1/2 rounded border border-slate-800 bg-slate-900 p-1.5 text-xs text-white font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => setMetadataEntries((prev) => prev.filter((_, i) => i !== idx))}
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
              onClick={onClose}
              className="rounded bg-slate-800 px-4 py-2 text-xs text-slate-300 hover:bg-slate-700 cursor-pointer font-mono"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 cursor-pointer font-mono"
            >
              {saving ? 'Saving...' : assetToEdit ? 'Update Node' : `Create ${currentMode} Stream`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};