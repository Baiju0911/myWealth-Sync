import React, { useState, useEffect } from 'react';
import {
  subledgerApi,
  type AssetSubLedgerNode,
  type AssetCategoryType,
  type OwnershipType,
  type AssetStatusType,
  type SubledgerTaxonomyGroup,
} from '../../api/subledger';

interface AssetFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  assetToEdit?: AssetSubLedgerNode | null;
  onSuccess: () => void;
}

export const AssetFormModal: React.FC<AssetFormModalProps> = ({
  isOpen,
  onClose,
  assetToEdit,
  onSuccess,
}) => {
  const [assetCode, setAssetCode] = useState('AST-RE-002');
  const [name, setName] = useState('');
  const [category, setCategory] = useState<AssetCategoryType>('REAL_ESTATE');
  
  // 📅 Acquisition Date State
  const [acquisitionDate, setAcquisitionDate] = useState<string>(
    new Date().toISOString().split('T')[0]
  );
  
  const [acquisitionCost, setAcquisitionCost] = useState<number | string>('');
  const [currentValuation, setCurrentValuation] = useState<number | string>('');
  const [ownershipType, setOwnershipType] = useState<OwnershipType>('INDIVIDUAL');
  const [status, setStatus] = useState<AssetStatusType>('ACTIVE');

  // Holds either the UUID primary key or subcategory string
  const [linkedGlAccount, setLinkedGlAccount] = useState<string>('');

  // Taxonomy State
  const [taxonomyTree, setTaxonomyTree] = useState<SubledgerTaxonomyGroup[]>([]);
  const [, setLoadingTaxonomy] = useState<boolean>(false);

  // Dynamic Metadata key-value builder
  const [metadataEntries, setMetadataEntries] = useState<{ key: string; value: string }[]>([
    { key: 'sro_name', value: '' },
    { key: 'survey_no', value: '' },
  ]);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch Taxonomy Nodes on Open
  useEffect(() => {
    if (isOpen) {
      setLoadingTaxonomy(true);
      subledgerApi
        .getTaxonomyNodesForSubledger()
        .then((tree) => {
          setTaxonomyTree(tree);
          if (tree.length > 0 && tree[0].subcategories.length > 0 && !linkedGlAccount) {
            const firstItem: any = tree[0].subcategories[0];
            const defaultValue = typeof firstItem === 'string' ? firstItem : firstItem.id;
            setLinkedGlAccount(defaultValue);
          }
        })
        .catch((err) => console.error('Failed to load taxonomy tree:', err))
        .finally(() => setLoadingTaxonomy(false));
    }
  }, [isOpen]);

  // Populate form fields if editing an existing asset
  useEffect(() => {
    if (assetToEdit) {
      setAssetCode(assetToEdit.asset_code);
      setName(assetToEdit.name);
      setCategory(assetToEdit.category);
      setAcquisitionDate(
        assetToEdit.acquisition_date 
          ? assetToEdit.acquisition_date.split('T')[0] 
          : new Date().toISOString().split('T')[0]
      );
      setAcquisitionCost(assetToEdit.acquisition_cost);
      setCurrentValuation(assetToEdit.current_valuation);
      setOwnershipType(assetToEdit.ownership_type);
      setStatus(assetToEdit.status);
      setLinkedGlAccount(String(assetToEdit.linked_gl_account || ''));

      if (assetToEdit.metadata_payload) {
        setMetadataEntries(
          Object.entries(assetToEdit.metadata_payload).map(([k, v]) => ({
            key: k,
            value: String(v),
          }))
        );
      }
    } else {
      setName('');
      setAcquisitionDate(new Date().toISOString().split('T')[0]);
      setAcquisitionCost('');
      setCurrentValuation('');
      setMetadataEntries([
        { key: 'sro_name', value: '' },
        { key: 'survey_no', value: '' },
      ]);
    }
  }, [assetToEdit, isOpen]);

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
    setSaving(true);
    setError(null);

    const metadataPayload: Record<string, any> = {};
    metadataEntries.forEach((row) => {
      if (row.key.trim()) {
        metadataPayload[row.key.trim()] = row.value.trim();
      }
    });

    const payload = {
      asset_code: assetCode,
      name,
      category,
      acquisition_date: acquisitionDate,
      acquisition_cost: Number(acquisitionCost) || 0,
      current_valuation: Number(currentValuation) || 0,
      ownership_type: ownershipType,
      ownership_share_pct: '100.00',
      status,
      linked_gl_account: linkedGlAccount,
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
        setError('Failed to save asset. Please check network connection and try again.');
      }
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-xl border border-slate-800 bg-slate-900 p-6 shadow-2xl text-slate-100">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h2 className="text-lg font-bold text-white">
            {assetToEdit ? '✏️ Edit Asset Sub-Ledger' : '➕ Add New Asset Sub-Ledger'}
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <div className="grid grid-cols-12 gap-3">
            <div className="col-span-4">
              <label className="block text-xs text-slate-400">Asset Code</label>
              <input
                type="text"
                required
                value={assetCode}
                onChange={(e) => setAssetCode(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs font-mono text-white focus:border-emerald-500 focus:outline-none"
              />
            </div>
            <div className="col-span-8">
              <label className="block text-xs text-slate-400">Asset Name</label>
              <input
                type="text"
                required
                placeholder="e.g. Kakkanad Flat or HDFC FD #4092"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
              />
            </div>

            <div className="col-span-6">
              <label className="block text-xs text-slate-400">Category</label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value as AssetCategoryType)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
              >
                <option value="REAL_ESTATE">Real Estate & Land</option>
                <option value="FIXED_DEPOSIT">Fixed Deposit</option>
                <option value="MARKET_INVESTMENT">Market / Mutual Fund</option>
                <option value="VEHICLE">Vehicle</option>
                <option value="PENSION_RETIREMENT">Pension / NPS</option>
              </select>
            </div>

            {/* TAXONOMY DROPDOWN BOUND WITH DYNAMIC PK / STRING RESOLUTION */}
            <div className="col-span-6">
              <label className="block text-xs font-semibold text-amber-400">
                General Ledger Taxonomy Account
              </label>
              <select
                value={linkedGlAccount}
                onChange={(e) => setLinkedGlAccount(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
                required
              >
                <option value="">-- Select GL Account --</option>
                {taxonomyTree.map((catGroup) => (
                  <optgroup key={catGroup.category} label={catGroup.category}>
                    {catGroup.subcategories.map((item: any) => {
                      const optionValue = typeof item === 'object' ? item.id : item;
                      const optionLabel = typeof item === 'object' ? item.subcategory : item;

                      return (
                        <option key={optionValue} value={optionValue}>
                          {catGroup.category} - {optionLabel}
                        </option>
                      );
                    })}
                  </optgroup>
                ))}
              </select>
            </div>

            {/* 📅 ACQUISITION DATE, COST & VALUATION IN 3 COLUMNS */}
            <div className="col-span-4">
              <label className="block text-xs text-slate-400">Acquisition Date</label>
              <input
                type="date"
                required
                value={acquisitionDate}
                onChange={(e) => setAcquisitionDate(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
              />
            </div>

            <div className="col-span-4">
              <label className="block text-xs text-slate-400">Acquisition Cost (₹)</label>
              <input
                type="number"
                required
                value={acquisitionCost}
                onChange={(e) => setAcquisitionCost(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
              />
            </div>

            <div className="col-span-4">
              <label className="block text-xs text-slate-400">Current Valuation (₹)</label>
              <input
                type="number"
                required
                value={currentValuation}
                onChange={(e) => setCurrentValuation(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
              />
            </div>
          </div>

          {/* Dynamic Metadata Section */}
          <div className="rounded-lg bg-slate-950 p-3 border border-slate-800">
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs font-bold text-slate-400 uppercase">
                Dynamic Metadata Attributes (JSON)
              </span>
              <button
                type="button"
                onClick={addMetadataRow}
                className="text-xs text-emerald-400 hover:underline"
              >
                + Add Key/Value
              </button>
            </div>

            <div className="space-y-2">
              {metadataEntries.map((row, idx) => (
                <div key={idx} className="flex gap-2 items-center">
                  <input
                    type="text"
                    placeholder="Key (e.g. survey_no)"
                    value={row.key}
                    onChange={(e) => handleMetadataChange(idx, 'key', e.target.value)}
                    className="w-1/2 rounded border border-slate-800 bg-slate-900 p-1.5 text-xs text-white"
                  />
                  <input
                    type="text"
                    placeholder="Value (e.g. 342/12-A)"
                    value={row.value}
                    onChange={(e) => handleMetadataChange(idx, 'value', e.target.value)}
                    className="w-1/2 rounded border border-slate-800 bg-slate-900 p-1.5 text-xs text-white"
                  />
                  <button
                    type="button"
                    onClick={() => removeMetadataRow(idx)}
                    className="text-slate-500 hover:text-rose-400 text-xs px-1"
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
              className="rounded bg-slate-800 px-4 py-2 text-xs text-slate-300 hover:bg-slate-700"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
            >
              {saving ? 'Saving...' : assetToEdit ? 'Update Asset' : 'Create Asset'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};