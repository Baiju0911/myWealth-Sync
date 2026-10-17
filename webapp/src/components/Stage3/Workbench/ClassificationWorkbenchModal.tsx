// webapp/src/components/Stage3/Workbench/ClassificationWorkbenchModal.tsx
import React from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { useWorkbenchModalState } from './useWorkbenchModalState';
import { ClusterListPanel } from './ClusterListPanel';
import { TaxonomyMapperPanel, clearSubledgerBreakdownCache } from './TaxonomyMapperPanel';
import { PatternSelectionModal } from './PatternSelectionModal';
import { AssetFormModal } from '../../subledger/AssetFormModal';
import type { TaxonomyMatchContext } from '../../subledger/CandidateMatcherModal';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  targetSubcategory?: string;
  accountId?: number;
  subledgerCapableSet?: Set<string>;
  onOpenSubledgerDrawer?: (subcategory: string, matchContext?: TaxonomyMatchContext) => void;
  onOpenOperationsHub?: (subcategory: string) => void;
}

const DEFAULT_SUBLEDGER_CAPABLE_HEADS = new Set<string>([
  'Suspense Account',
  'Gold & Precious Metals',
  'ShareMarket & Mutual Funds',
  'Real Estate',
  'Insurance Assets',
  'Fixed Deposits',
  'Loans & Advances',
  'Sundry Debtors',
  'Sundry Creditors',
]);

export const ClassificationWorkbenchModal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  targetSubcategory = 'Suspense Account',
  accountId,
  subledgerCapableSet = DEFAULT_SUBLEDGER_CAPABLE_HEADS,
  onOpenSubledgerDrawer,
}) => {
  const { state, actions } = useWorkbenchModalState({
    isOpen,
    targetSubcategory,
    accountId,
    onSuccess,
  });

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-9999 flex items-center justify-center p-2 sm:p-4 bg-black/90 backdrop-blur-md font-mono">
      <div className="bg-zinc-950 border border-zinc-800 rounded-2xl w-[96vw] max-w-[1720px] h-[93vh] flex flex-col shadow-2xl overflow-hidden text-zinc-100">
        
        {/* Header Bar */}
        <div className="flex justify-between items-center px-6 py-3.5 border-b border-zinc-800 bg-zinc-900/90 shrink-0">
          <div>
            <h2 className="text-xs sm:text-sm font-bold uppercase tracking-wider text-zinc-100 flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${state.vectorType === 'Debit' ? 'bg-rose-500' : 'bg-emerald-500'}`} />
              <span>Classification Workbench — {targetSubcategory || 'Suspense Account'}</span>
              <span className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase ${
                state.vectorType === 'Debit'
                  ? 'bg-rose-950/80 text-rose-300 border border-rose-800/60'
                  : 'bg-emerald-950/80 text-emerald-300 border border-emerald-800/60'
              }`}>
                {state.vectorType === 'Debit' ? 'Outflow (DR)' : 'Inflow (CR)'}
              </span>
            </h2>
            <p className="text-[11px] text-zinc-500 font-sans mt-0.5">
              Reviewing merchant clusters under <span className="text-zinc-200 font-semibold">{targetSubcategory || 'Suspense Account'}</span>
            </p>
          </div>

          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-zinc-100 p-1.5 rounded-lg hover:bg-zinc-800 transition-colors cursor-pointer"
            title="Close Workbench (Esc)"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Workspace Split Body */}
        <div className="flex-1 flex overflow-hidden">
          <ClusterListPanel
            loading={state.loading}
            filteredClusters={state.clusters}
            selectedTxnIds={state.selectedTxnIds}
            visibleTxnIds={state.visibleTxnIds}
            activePreviewCluster={state.activePreviewCluster}
            searchQuery={state.searchQuery}
            setSearchQuery={actions.setSearchQuery}
            setActivePreviewCluster={actions.handleSelectCluster}
            toggleIndividualTxn={actions.toggleIndividualTxn}
            toggleClusterTxns={actions.toggleClusterTxns}
            toggleSelectAllVisible={actions.toggleSelectAllVisible}
            clearAllSelections={actions.clearAllSelections}
          />

          <TaxonomyMapperPanel
            targetSubcategoryContext={targetSubcategory}
            selectedSummary={state.selectedSummary}
            activePreviewCluster={state.activePreviewCluster}
            taxonomyTree={state.taxonomyTree}
            availableSubcategories={state.availableSubcategories}
            selectedCategory={state.selectedCategory}
            setSelectedCategory={actions.setSelectedCategory}
            selectedSubcategory={state.selectedSubcategory}
            setSelectedSubcategory={actions.setSelectedSubcategory}
            isCreatingNew={state.isCreatingNew}
            setIsCreatingNew={actions.setIsCreatingNew}
            newCatInput={state.newCatInput}
            setNewCatInput={actions.setNewCatInput}
            newSubInput={state.newSubInput}
            setNewSubInput={actions.setNewSubInput}
            savingNewTaxonomy={state.savingNewTaxonomy}
            handleCreateTaxonomy={actions.handleCreateTaxonomy}
            saveRule={state.saveRule}
            setSaveRule={actions.setSaveRule}
            upiStrategy={state.upiStrategy}
            setUpiStrategy={actions.setUpiStrategy}
            vectorType={state.vectorType}
            submitting={state.submitting}
            handleApplyClassification={actions.handleOpenPatternSelectionFlow}
            onClose={onClose}
            suggestedRule={state.suggestedRule}
            subledgerCapableSet={subledgerCapableSet}
            onOpenSubledgerDrawer={onOpenSubledgerDrawer}
            onOpenNewFolioModal={(sub) => {
              actions.setPendingTargetSubcategory(sub);
              actions.setIsFolioModalOpen(true);
            }}
          />
        </div>
      </div>

      <PatternSelectionModal
        isOpen={state.isPatternModalOpen}
        selectedTxnIds={state.selectedSummary.allTxnIds}
        targetCategory={state.selectedCategory}
        targetSubcategory={state.selectedSubcategory}
        activeVendorName={state.activeVendorName}
        upiStrategy={state.upiStrategy}
        onClose={() => actions.setIsPatternModalOpen(false)}
        onConfirm={actions.handleFinalReclassificationSubmit}
        isSubmitting={state.submitting}
      />

      <AssetFormModal
        isOpen={state.isFolioModalOpen}
        onClose={() => actions.setIsFolioModalOpen(false)}
        defaultSubcategory={state.pendingTargetSubcategory || state.selectedSubcategory}
        activeTab="ASSET"
        onSuccess={() => {
          clearSubledgerBreakdownCache(state.pendingTargetSubcategory || state.selectedSubcategory);
          actions.loadClusters(targetSubcategory, accountId, state.searchQuery);
        }}
      />
    </div>,
    document.body
  );
};

export default ClassificationWorkbenchModal;