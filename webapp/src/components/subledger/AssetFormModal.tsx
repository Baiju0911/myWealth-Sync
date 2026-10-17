import React from 'react';
import type { AssetSubLedgerNode } from '../../api/subledger';
import { subledgerApi } from '../../api/subledger';
import { useAssetFormState } from './assetform/userAssetFormState';
import { generateDynamicCode } from './helper/subledgerCodeGenerator';

import { IdentifiersSection } from './assetform/modalParts/IdentifiersSection';
import { TaxonomySelectSection } from './assetform/modalParts/TaxonomySelectSection'; 
import { FinancialInputsSection } from './assetform/modalParts/FinancialInputsSection';
import { PartySelectorSection } from './assetform/modalParts/PartSelectorSection';
import { MetadataAttributesSection } from './assetform/modalParts/MetadataAttributesSection';

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
  const { state, actions } = useAssetFormState({
    isOpen,
    assetToEdit,
    defaultSubcategory,
    activeTab,
    onSuccess,
    onClose,
  });

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm font-sans"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl rounded-xl border border-slate-800 bg-slate-900 p-6 shadow-2xl text-slate-100 max-h-[92vh] overflow-y-auto font-mono"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3 font-sans">
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            {assetToEdit ? '✏️ Edit Sub-Ledger Node' : '➕ Register Asset Folio'}
            <span className="text-xs font-mono px-2 py-0.5 rounded border bg-emerald-950/80 text-emerald-300 border-emerald-800">
              {state.currentMode} MODE
            </span>
          </h2>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-white cursor-pointer p-1">
            ✕
          </button>
        </div>

        <form onSubmit={actions.handleSubmit} className="mt-4 space-y-4">
          <div className="grid grid-cols-12 gap-3">
            <IdentifiersSection
              assetCode={state.assetCode}
              setAssetCode={actions.setAssetCode}
              name={state.name}
              setName={actions.setName}
            />

            <TaxonomySelectSection
              currentMode={state.currentMode}
              linkedGlAccount={state.linkedGlAccount}
              options={state.filteredTaxonomySubcategories}
              onSelectSubcategory={actions.handleGlTaxonomyChange}
              onRefreshTaxonomy={actions.setTaxonomyTree}
            />

            <FinancialInputsSection
              currentMode={state.currentMode}
              acquisitionDate={state.acquisitionDate}
              setAcquisitionDate={actions.setAcquisitionDate}
              acquisitionCost={state.acquisitionCost}
              setAcquisitionCost={actions.setAcquisitionCost}
              currentValuation={state.currentValuation}
              setCurrentValuation={actions.setCurrentValuation}
              acquisitionFundingSource={state.acquisitionFundingSource}
              setAcquisitionFundingSource={actions.setAcquisitionFundingSource}
              isMatured={state.isMatured}
              isCashDomain={state.isCashFormMode}
            />
          </div>

          <PartySelectorSection
            currentMode={state.currentMode}
            vendors={state.vendors}
            selectedVendorId={state.selectedVendorId}
            onSelectVendor={(vId) => {
              actions.setSelectedVendorId(vId);
              const vObj = state.vendors.find((v) => String(v.id) === String(vId));
              if (!assetToEdit) {
                actions.setAssetCode(
                  generateDynamicCode(state.currentMode, vObj?.name, state.isCashFormMode)
                );
              }
            }}
            onQuickCreateVendor={async (partyName) => {
              const cleanCode = partyName.replace(/[^a-zA-Z0-9]/g, '').toUpperCase().slice(0, 10);
              const created = await subledgerApi.createVendor({
                name: partyName,
                code: `VND-${cleanCode}-${Math.floor(100 + Math.random() * 900)}`,
                default_keywords: [partyName],
              });
              actions.setVendors([...state.vendors, created]);
              actions.setSelectedVendorId(created.id);
            }}
            masterAssets={state.masterAssetsOnly}
            parentAssetId={state.parentAssetId}
            onSelectParentAsset={actions.setParentAssetId}
          />

          <MetadataAttributesSection
            entries={state.metadataEntries}
            onChange={(idx, field, val) => {
              actions.setMetadataEntries((prev) => {
                const updated = [...prev];
                updated[idx][field] = val;
                return updated;
              });
            }}
            onAdd={() => actions.setMetadataEntries((prev) => [...prev, { key: '', value: '' }])}
            onRemove={(idx) => actions.setMetadataEntries((prev) => prev.filter((_, i) => i !== idx))}
          />

          {state.error && (
            <p className="text-xs text-rose-400 bg-rose-500/10 p-2 rounded border border-rose-500/20">
              {state.error}
            </p>
          )}

          <div className="flex justify-end gap-2 border-t border-slate-800 pt-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded bg-slate-800 px-4 py-2 text-xs text-slate-300 hover:bg-slate-700 cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={state.saving}
              className="rounded bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 cursor-pointer"
            >
              {state.saving ? 'Saving...' : assetToEdit ? 'Update Folio' : 'Register Folio'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};