import React from 'react';
import type { TaxonomyOption, ExtendedCluster, Cluster } from '../../api';
import { inrFormatter, parseRemarks } from '../../utils/classificationHelpers';

export interface SuggestedRule {
  rule_code: string;
  suggested_category: string;
  suggested_subcategory: string;
  matched_pattern: string;
}

interface Props {
  targetSubcategoryContext?: string;
  selectedSummary: { totalTxns: number; totalAmount: number; allTxnIds: string[] };
  activePreviewCluster: ExtendedCluster | Cluster | null;
  taxonomyTree: TaxonomyOption[];
  availableSubcategories: string[];
  selectedCategory: string;
  setSelectedCategory: (cat: string) => void;
  selectedSubcategory: string;
  setSelectedSubcategory: (sub: string) => void;
  isCreatingNew: boolean;
  setIsCreatingNew: (val: boolean) => void;
  newCatInput: string;
  setNewCatInput: (v: string) => void;
  newSubInput: string;
  setNewSubInput: (v: string) => void;
  savingNewTaxonomy: boolean;
  handleCreateTaxonomy: () => void;
  saveRule: boolean;
  setSaveRule: (val: boolean) => void;
  submitting: boolean;
  handleApplyClassification: () => void;
  onClose: () => void;
  selectedTxnIds?: string[];
  toggleClusterTxns?: (clusterTxnIds: string[], e: React.MouseEvent) => void;
  // 🟢 Props for Smart Existing Rule Suggestion
  suggestedRule?: SuggestedRule | null;
}

export const TaxonomyMapperPanel: React.FC<Props> = ({
  // targetSubcategoryContext,
  selectedSummary,
  activePreviewCluster,
  taxonomyTree,
  availableSubcategories,
  selectedCategory,
  setSelectedCategory,
  selectedSubcategory,
  setSelectedSubcategory,
  isCreatingNew,
  setIsCreatingNew,
  newCatInput,
  setNewCatInput,
  newSubInput,
  setNewSubInput,
  savingNewTaxonomy,
  handleCreateTaxonomy,
  saveRule,
  setSaveRule,
  submitting,
  handleApplyClassification,
  onClose,
  selectedTxnIds = [],
  toggleClusterTxns,
  suggestedRule = null,
}) => {
  const sampleItem = activePreviewCluster?.items?.[0];
  const remarksData = parseRemarks(sampleItem?.remarks);

  // Check direction vector of active preview sample item
  const isCreditInflow = (sampleItem?.credit || 0) > 0;
  const clusterTxns = activePreviewCluster?.transaction_ids || [];
  const allClusterSelected = clusterTxns.length > 0 && clusterTxns.every((id) => selectedTxnIds.includes(id));

  return (
    <div style={{ width: '42%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '24px', backgroundColor: '#0f0f12', overflowY: 'auto' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        
        {/* Active Audit Context Preview */}
        {activePreviewCluster && (
          <div style={{ backgroundColor: '#18181b', border: '1px solid #27272a', padding: '12px', borderRadius: '10px', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#f59e0b', fontWeight: 'bold' }}>
                Inspect Context: #{activePreviewCluster.pattern || 'UNCLASSIFIED'}
              </span>
              <span style={{ 
                fontSize: '9px', 
                fontWeight: 'bold', 
                padding: '2px 6px', 
                borderRadius: '4px',
                backgroundColor: isCreditInflow ? 'rgba(52, 211, 153, 0.15)' : 'rgba(244, 63, 94, 0.15)',
                color: isCreditInflow ? '#34d399' : '#f43f5e',
                border: isCreditInflow ? '1px solid rgba(52, 211, 153, 0.3)' : '1px solid rgba(244, 63, 94, 0.3)'
              }}>
                {isCreditInflow ? 'INFLOW (CREDIT)' : 'OUTFLOW (DEBIT)'}
              </span>
            </div>
            <p style={{ margin: 0, color: '#e4e4e7', lineHeight: '1.4' }}>
              {remarksData.display_text || sampleItem?.narration || activePreviewCluster.sample_descriptions?.[0] || 'No description'}
            </p>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '2px' }}>
              {remarksData.payee && (
                <span style={{ backgroundColor: '#1e1b4b', color: '#818cf8', padding: '2px 6px', borderRadius: '4px', fontSize: '10px' }}>
                  💳 Payee: {remarksData.payee}
                </span>
              )}
              {remarksData.upi_ref && (
                <span style={{ backgroundColor: '#27272a', color: '#a1a1aa', padding: '2px 6px', borderRadius: '4px', fontSize: '10px', fontFamily: 'monospace' }}>
                  Ref: {remarksData.upi_ref}
                </span>
              )}
            </div>
          </div>
        )}

        {/* 💡 SMART EXISTING RULE SUGGESTION BANNER */}
        {suggestedRule && (
          <div style={{ backgroundColor: '#1e1b4b', border: '1px solid #6366f1', padding: '12px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#818cf8', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '4px' }}>
                💡 Existing Rule Detected
              </span>
              <span style={{ fontSize: '9px', color: '#c7d2fe', backgroundColor: '#312e81', padding: '2px 6px', borderRadius: '4px', fontFamily: 'monospace' }}>
                {suggestedRule.rule_code}
              </span>
            </div>
            <p style={{ margin: 0, fontSize: '11px', color: '#a5b4fc', lineHeight: '1.4' }}>
              Pattern <code style={{ color: '#ffffff', backgroundColor: '#312e81', padding: '1px 4px', borderRadius: '3px' }}>"{suggestedRule.matched_pattern}"</code> previously mapped to:
              <br />
              <strong style={{ color: '#ffffff', fontSize: '12px' }}>
                {suggestedRule.suggested_category} → {suggestedRule.suggested_subcategory}
              </strong>
            </p>
            <button
              type="button"
              onClick={() => {
                setSelectedCategory(suggestedRule.suggested_category);
                setSelectedSubcategory(suggestedRule.suggested_subcategory);
              }}
              style={{
                width: '100%',
                padding: '7px 12px',
                borderRadius: '6px',
                fontSize: '11px',
                fontWeight: 'bold',
                backgroundColor: '#6366f1',
                color: '#ffffff',
                border: 'none',
                cursor: 'pointer',
                transition: 'background 0.2s ease',
              }}
            >
              ⚡ Apply {suggestedRule.suggested_subcategory}
            </button>
          </div>
        )}

        {/* ⚡ PATTERN MATCH SWEEP PROMPT */}
        {activePreviewCluster && clusterTxns.length > 0 && toggleClusterTxns && (
          <div style={{ backgroundColor: '#18181b', border: '1px solid #3f3f46', padding: '12px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#38bdf8', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '4px' }}>
                ⚡ Pattern Sweep Available
              </span>
              <span style={{ fontSize: '10px', color: '#f59e0b', backgroundColor: 'rgba(245, 158, 11, 0.15)', padding: '2px 6px', borderRadius: '4px', fontWeight: 'bold' }}>
                {clusterTxns.length} Rows
              </span>
            </div>

            {/* 🏷️ TARGET TAXONOMY CONTEXT BADGE */}
            <div style={{ backgroundColor: '#09090b', padding: '6px 10px', borderRadius: '6px', border: '1px solid #27272a', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '10px', color: '#71717a', textTransform: 'uppercase' }}>Target Destination:</span>
              <span style={{ fontSize: '11px', fontWeight: 'bold', color: '#f4f4f5' }}>
                <span style={{ color: selectedCategory === 'Income' ? '#34d399' : '#f87171' }}>{selectedCategory}</span> 
                <span style={{ color: '#71717a', margin: '0 4px' }}>→</span> 
                <span style={{ color: '#f59e0b' }}>{selectedSubcategory}</span>
              </span>
            </div>

            <p style={{ margin: 0, fontSize: '11px', color: '#a1a1aa' }}>
              Identified <strong style={{ color: '#f4f4f5' }}>{clusterTxns.length}</strong> matching transaction{clusterTxns.length !== 1 ? 's' : ''} for pattern <code style={{ color: '#38bdf8' }}>"{activePreviewCluster.pattern}"</code>.
            </p>

            <button
              type="button"
              onClick={(e) => toggleClusterTxns(clusterTxns, e)}
              style={{
                width: '100%',
                padding: '6px 12px',
                borderRadius: '6px',
                fontSize: '11px',
                fontWeight: 'bold',
                backgroundColor: allClusterSelected ? '#27272a' : '#38bdf8',
                color: allClusterSelected ? '#f4f4f5' : '#09090b',
                border: allClusterSelected ? '1px solid #3f3f46' : 'none',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
              }}
            >
              {allClusterSelected
                ? `✓ All ${clusterTxns.length} Rows Selected for [${selectedSubcategory}]`
                : `Select All ${clusterTxns.length} Rows for [${selectedSubcategory}]`}
            </button>
          </div>
        )}

        {/* Selection Summary */}
        <div style={{ backgroundColor: '#18181b', border: '1px solid #27272a', padding: '12px 14px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', fontWeight: 'bold' }}>
            Batch Target Summary
          </span>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '13px', fontWeight: 'bold', color: selectedSummary.totalTxns > 0 ? '#f59e0b' : '#71717a' }}>
              {selectedSummary.totalTxns} Item{selectedSummary.totalTxns !== 1 ? 's' : ''} Selected
            </span>
            <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f4f4f5' }}>
              {inrFormatter.format(selectedSummary?.totalAmount || 0)}
            </span>
          </div>
        </div>

        {/* Category Dropdowns / Creator */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #27272a', paddingBottom: '6px' }}>
            <h3 style={{ margin: 0, fontSize: '11px', fontWeight: 'bold', textTransform: 'uppercase', color: '#a1a1aa' }}>
              Assign Taxonomy Nodes
            </h3>
            <button
              onClick={() => setIsCreatingNew(!isCreatingNew)}
              style={{ background: 'none', border: 'none', color: '#f59e0b', fontSize: '11px', cursor: 'pointer', fontWeight: 'bold' }}
            >
              {isCreatingNew ? '← Back to Select' : '+ Create New Node'}
            </button>
          </div>

          {!isCreatingNew ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div>
                <label style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
                  Primary Category
                </label>
                <select
                  value={selectedCategory}
                  onChange={(e) => {
                    const newCat = e.target.value;
                    setSelectedCategory(newCat);
                    const found = taxonomyTree.find((t) => t.category === newCat);
                    if (found && found.subcategories && found.subcategories.length > 0) {
                      setSelectedSubcategory(found.subcategories[0]);
                    }
                  }}
                  style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', color: '#f4f4f5', outline: 'none' }}
                >
                  {taxonomyTree.map((t, catIdx) => (
                    <option key={`cat-${t.category}-${catIdx}`} value={t.category}>
                      {t.category === 'Income' ? '🟢 Income (Inflows)' : t.category === 'Expense' ? '🔴 Expense (Outflows)' : t.category}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
                  Subcategory
                </label>
                <select
                  value={selectedSubcategory || ''}
                  onChange={(e) => setSelectedSubcategory(e.target.value)}
                  style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', color: '#f4f4f5', outline: 'none' }}
                >
                  {(availableSubcategories || []).map((sub, subIdx) => (
                    <option key={`sub-${sub}-${subIdx}`} value={sub}>
                      {sub}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          ) : (
            <div style={{ backgroundColor: '#18181b', border: '1px dashed #f59e0b', padding: '12px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <span style={{ fontSize: '11px', color: '#f59e0b', fontWeight: 'bold' }}>
                New Taxonomy Entry
              </span>
              <div>
                <label style={{ fontSize: '10px', color: '#a1a1aa', display: 'block', marginBottom: '2px' }}>
                  Category Name
                </label>
                <input
                  type="text"
                  placeholder="e.g. Income or Expense"
                  value={newCatInput}
                  onChange={(e) => setNewCatInput(e.target.value)}
                  style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', fontSize: '12px', color: '#f4f4f5' }}
                />
              </div>

              <div>
                <label style={{ fontSize: '10px', color: '#a1a1aa', display: 'block', marginBottom: '2px' }}>
                  Subcategory Name
                </label>
                <input
                  type="text"
                  placeholder="e.g. Dividend Income"
                  value={newSubInput}
                  onChange={(e) => setNewSubInput(e.target.value)}
                  style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', fontSize: '12px', color: '#f4f4f5' }}
                />
              </div>

              <button
                onClick={handleCreateTaxonomy}
                disabled={savingNewTaxonomy || !newCatInput.trim() || !newSubInput.trim()}
                style={{
                  marginTop: '4px',
                  padding: '8px 12px',
                  borderRadius: '6px',
                  fontSize: '11px',
                  fontWeight: 'bold',
                  backgroundColor: '#f59e0b',
                  color: '#09090b',
                  border: 'none',
                  cursor: savingNewTaxonomy ? 'wait' : 'pointer',
                }}
              >
                {savingNewTaxonomy ? 'Saving...' : 'Add & Select Node'}
              </button>
            </div>
          )}
        </div>

        {/* Rule Toggle */}
        <div style={{ backgroundColor: '#09090b', border: '1px solid #27272a', padding: '10px 12px', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f4f4f5', display: 'block' }}>
              Save to Classification Rules
            </span>
            <span style={{ fontSize: '10px', color: '#71717a', display: 'block' }}>
              Auto-classify future imports matching active vendor pattern
            </span>
          </div>
          <input
            type="checkbox"
            checked={saveRule}
            onChange={(e) => setSaveRule(e.target.checked)}
            style={{ width: '16px', height: '16px', accentColor: '#f59e0b', cursor: 'pointer' }}
          />
        </div>

      </div>

      {/* Footer Buttons */}
      <div style={{ borderTop: '1px solid #27272a', paddingTop: '14px', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
        <button
          onClick={onClose}
          style={{ padding: '8px 16px', borderRadius: '8px', fontSize: '12px', color: '#a1a1aa', background: 'none', border: 'none', cursor: 'pointer' }}
        >
          Cancel
        </button>
        <button
          disabled={submitting || selectedSummary.allTxnIds.length === 0}
          onClick={handleApplyClassification}
          style={{
            padding: '10px 20px',
            borderRadius: '8px',
            fontSize: '12px',
            fontWeight: 'bold',
            backgroundColor: '#f59e0b',
            color: '#09090b',
            border: 'none',
            cursor: submitting || selectedSummary.allTxnIds.length === 0 ? 'not-allowed' : 'pointer',
            opacity: submitting || selectedSummary.allTxnIds.length === 0 ? 0.5 : 1,
          }}
        >
          {submitting ? 'Applying...' : `Reclassify ${selectedSummary.totalTxns} Selected Line${selectedSummary.totalTxns !== 1 ? 's' : ''}`}
        </button>
      </div>
    </div>
  );
};




// import React from 'react';
// import type { TaxonomyOption, ExtendedCluster, Cluster } from '../../api';
// import { inrFormatter, parseRemarks } from '../../utils/classificationHelpers';

// interface Props {
//   targetSubcategoryContext?: string;
//   selectedSummary: { totalTxns: number; totalAmount: number; allTxnIds: string[] };
//   activePreviewCluster: ExtendedCluster | Cluster | null;
//   taxonomyTree: TaxonomyOption[];
//   availableSubcategories: string[];
//   selectedCategory: string;
//   setSelectedCategory: (cat: string) => void;
//   selectedSubcategory: string;
//   setSelectedSubcategory: (sub: string) => void;
//   isCreatingNew: boolean;
//   setIsCreatingNew: (val: boolean) => void;
//   newCatInput: string;
//   setNewCatInput: (v: string) => void;
//   newSubInput: string;
//   setNewSubInput: (v: string) => void;
//   savingNewTaxonomy: boolean;
//   handleCreateTaxonomy: () => void;
//   saveRule: boolean;
//   setSaveRule: (val: boolean) => void;
//   submitting: boolean;
//   handleApplyClassification: () => void;
//   onClose: () => void;
// }

// export const TaxonomyMapperPanel: React.FC<Props> = ({
//   targetSubcategoryContext,
//   selectedSummary,
//   activePreviewCluster,
//   taxonomyTree,
//   availableSubcategories,
//   selectedCategory,
//   setSelectedCategory,
//   selectedSubcategory,
//   setSelectedSubcategory,
//   isCreatingNew,
//   setIsCreatingNew,
//   newCatInput,
//   setNewCatInput,
//   newSubInput,
//   setNewSubInput,
//   savingNewTaxonomy,
//   handleCreateTaxonomy,
//   saveRule,
//   setSaveRule,
//   submitting,
//   handleApplyClassification,
//   onClose,
// }) => {
//   const sampleItem = activePreviewCluster?.items?.[0];
//   const remarksData = parseRemarks(sampleItem?.remarks);

//   // Check direction of current active sample item
//   const isCreditInflow = (sampleItem?.credit || 0) > 0;

//   return (
//     <div style={{ width: '42%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '24px', backgroundColor: '#0f0f12' }}>
//       <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        
//         {/* Active Audit Context Preview */}
//         {activePreviewCluster && (
//           <div style={{ backgroundColor: '#18181b', border: '1px solid #27272a', padding: '12px', borderRadius: '10px', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
//             <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
//               <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#f59e0b', fontWeight: 'bold' }}>
//                 Inspect Cluster Context: #{activePreviewCluster.pattern || 'UNCLASSIFIED'}
//               </span>
//               <span style={{ 
//                 fontSize: '9px', 
//                 fontWeight: 'bold', 
//                 padding: '2px 6px', 
//                 borderRadius: '4px',
//                 backgroundColor: isCreditInflow ? 'rgba(52, 211, 153, 0.15)' : 'rgba(244, 63, 94, 0.15)',
//                 color: isCreditInflow ? '#34d399' : '#f43f5e',
//                 border: isCreditInflow ? '1px solid rgba(52, 211, 153, 0.3)' : '1px solid rgba(244, 63, 94, 0.3)'
//               }}>
//                 {isCreditInflow ? 'INFLOW (CREDIT)' : 'OUTFLOW (DEBIT)'}
//               </span>
//             </div>
//             <p style={{ margin: 0, color: '#e4e4e7', lineHeight: '1.4' }}>
//               {remarksData.display_text || sampleItem?.narration || activePreviewCluster.sample_descriptions?.[0] || 'No description'}
//             </p>
//             <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '2px' }}>
//               {remarksData.payee && (
//                 <span style={{ backgroundColor: '#1e1b4b', color: '#818cf8', padding: '2px 6px', borderRadius: '4px', fontSize: '10px' }}>
//                   💳 Payee: {remarksData.payee}
//                 </span>
//               )}
//               {remarksData.upi_ref && (
//                 <span style={{ backgroundColor: '#27272a', color: '#a1a1aa', padding: '2px 6px', borderRadius: '4px', fontSize: '10px', fontFamily: 'monospace' }}>
//                   Ref: {remarksData.upi_ref}
//                 </span>
//               )}
//             </div>
//           </div>
//         )}

//         {/* Selection Summary */}
//         <div style={{ backgroundColor: '#18181b', border: '1px solid #27272a', padding: '14px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
//           <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', fontWeight: 'bold' }}>
//             Batch Target Summary
//           </span>
//           <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
//             <span style={{ fontSize: '13px', fontWeight: 'bold', color: selectedSummary.totalTxns > 0 ? '#f59e0b' : '#71717a' }}>
//               {selectedSummary.totalTxns} Item{selectedSummary.totalTxns !== 1 ? 's' : ''} Selected
//             </span>
//             <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f4f4f5' }}>
//               {inrFormatter.format(selectedSummary?.totalAmount || 0)}
//             </span>
//           </div>
//         </div>

//         {/* Category Dropdowns / On-The-Go Creator */}
//         <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
//           <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #27272a', paddingBottom: '8px' }}>
//             <h3 style={{ margin: 0, fontSize: '11px', fontWeight: 'bold', textTransform: 'uppercase', color: '#a1a1aa' }}>
//               Assign Taxonomy Nodes
//             </h3>
//             <button
//               onClick={() => setIsCreatingNew(!isCreatingNew)}
//               style={{ background: 'none', border: 'none', color: '#f59e0b', fontSize: '11px', cursor: 'pointer', fontWeight: 'bold' }}
//             >
//               {isCreatingNew ? '← Back to Select' : '+ Create New Node'}
//             </button>
//           </div>

//           {!isCreatingNew ? (
//             <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
//               <div>
//                 <label style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
//                   Primary Category
//                 </label>
//                 <select
//                   value={selectedCategory}
//                   onChange={(e) => {
//                     const newCat = e.target.value;
//                     setSelectedCategory(newCat);
//                     const found = taxonomyTree.find((t) => t.category === newCat);
//                     if (found && found.subcategories && found.subcategories.length > 0) {
//                       setSelectedSubcategory(found.subcategories[0]);
//                     }
//                   }}
//                   style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', color: '#f4f4f5', outline: 'none' }}
//                 >
//                   {taxonomyTree.map((t, catIdx) => (
//                     <option key={`cat-${t.category}-${catIdx}`} value={t.category}>
//                       {t.category === 'Income' ? '🟢 Income (Inflows)' : t.category === 'Expense' ? '🔴 Expense (Outflows)' : t.category}
//                     </option>
//                   ))}
//                 </select>
//               </div>

//               <div>
//                 <label style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
//                   Subcategory
//                 </label>
//                 <select
//                   value={selectedSubcategory || ''}
//                   onChange={(e) => setSelectedSubcategory(e.target.value)}
//                   style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', color: '#f4f4f5', outline: 'none' }}
//                 >
//                   {(availableSubcategories || []).map((sub, subIdx) => (
//                     <option key={`sub-${sub}-${subIdx}`} value={sub}>
//                       {sub}
//                     </option>
//                   ))}
//                 </select>
//               </div>
//             </div>
//           ) : (
//             <div style={{ backgroundColor: '#18181b', border: '1px dashed #f59e0b', padding: '12px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
//               <span style={{ fontSize: '11px', color: '#f59e0b', fontWeight: 'bold' }}>
//                 New Taxonomy Entry
//               </span>
//               <div>
//                 <label style={{ fontSize: '10px', color: '#a1a1aa', display: 'block', marginBottom: '2px' }}>
//                   Category Name
//                 </label>
//                 <input
//                   type="text"
//                   placeholder="e.g. Income or Expense"
//                   value={newCatInput}
//                   onChange={(e) => setNewCatInput(e.target.value)}
//                   style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', fontSize: '12px', color: '#f4f4f5' }}
//                 />
//               </div>

//               <div>
//                 <label style={{ fontSize: '10px', color: '#a1a1aa', display: 'block', marginBottom: '2px' }}>
//                   Subcategory Name
//                 </label>
//                 <input
//                   type="text"
//                   placeholder="e.g. Dividend Income"
//                   value={newSubInput}
//                   onChange={(e) => setNewSubInput(e.target.value)}
//                   style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', fontSize: '12px', color: '#f4f4f5' }}
//                 />
//               </div>

//               <button
//                 onClick={handleCreateTaxonomy}
//                 disabled={savingNewTaxonomy || !newCatInput.trim() || !newSubInput.trim()}
//                 style={{
//                   marginTop: '4px',
//                   padding: '8px 12px',
//                   borderRadius: '6px',
//                   fontSize: '11px',
//                   fontWeight: 'bold',
//                   backgroundColor: '#f59e0b',
//                   color: '#09090b',
//                   border: 'none',
//                   cursor: savingNewTaxonomy ? 'wait' : 'pointer',
//                 }}
//               >
//                 {savingNewTaxonomy ? 'Saving...' : 'Add & Select Node'}
//               </button>
//             </div>
//           )}
//         </div>

//         {/* Rule Toggle */}
//         <div style={{ backgroundColor: '#09090b', border: '1px solid #27272a', padding: '12px', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
//           <div>
//             <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f4f4f5', display: 'block' }}>
//               Save to Classification Rules
//             </span>
//             <span style={{ fontSize: '10px', color: '#71717a', display: 'block' }}>
//               Auto-classify future imports matching active vendor pattern
//             </span>
//           </div>
//           <input
//             type="checkbox"
//             checked={saveRule}
//             onChange={(e) => setSaveRule(e.target.checked)}
//             style={{ width: '16px', height: '16px', accentColor: '#f59e0b', cursor: 'pointer' }}
//           />
//         </div>

//       </div>

//       {/* Footer Buttons */}
//       <div style={{ borderTop: '1px solid #27272a', paddingTop: '16px', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
//         <button
//           onClick={onClose}
//           style={{ padding: '8px 16px', borderRadius: '8px', fontSize: '12px', color: '#a1a1aa', background: 'none', border: 'none', cursor: 'pointer' }}
//         >
//           Cancel
//         </button>
//         <button
//           disabled={submitting || selectedSummary.allTxnIds.length === 0}
//           onClick={handleApplyClassification}
//           style={{
//             padding: '10px 20px',
//             borderRadius: '8px',
//             fontSize: '12px',
//             fontWeight: 'bold',
//             backgroundColor: '#f59e0b',
//             color: '#09090b',
//             border: 'none',
//             cursor: submitting || selectedSummary.allTxnIds.length === 0 ? 'not-allowed' : 'pointer',
//             opacity: submitting || selectedSummary.allTxnIds.length === 0 ? 0.5 : 1,
//           }}
//         >
//           {submitting ? 'Applying...' : `Reclassify ${selectedSummary.totalTxns} Selected Line${selectedSummary.totalTxns !== 1 ? 's' : ''}`}
//         </button>
//       </div>
//     </div>
//   );
// };




// // import React from 'react';
// // import type { TaxonomyOption, ExtendedCluster, Cluster } from '../../api';
// // import { inrFormatter, parseRemarks } from '../../utils/classificationHelpers';

// // interface Props {
// //   selectedSummary: { totalTxns: number; totalAmount: number; allTxnIds: string[] };
// //   activePreviewCluster: ExtendedCluster | Cluster | null;
// //   taxonomyTree: TaxonomyOption[];
// //   availableSubcategories: string[];
// //   selectedCategory: string;
// //   setSelectedCategory: (cat: string) => void;
// //   selectedSubcategory: string;
// //   setSelectedSubcategory: (sub: string) => void;
// //   isCreatingNew: boolean;
// //   setIsCreatingNew: (val: boolean) => void;
// //   newCatInput: string;
// //   setNewCatInput: (v: string) => void;
// //   newSubInput: string;
// //   setNewSubInput: (v: string) => void;
// //   savingNewTaxonomy: boolean;
// //   handleCreateTaxonomy: () => void;
// //   saveRule: boolean;
// //   setSaveRule: (val: boolean) => void;
// //   submitting: boolean;
// //   handleApplyClassification: () => void;
// //   onClose: () => void;
// // }

// // export const TaxonomyMapperPanel: React.FC<Props> = ({
// //   selectedSummary,
// //   activePreviewCluster,
// //   taxonomyTree,
// //   availableSubcategories,
// //   selectedCategory,
// //   setSelectedCategory,
// //   selectedSubcategory,
// //   setSelectedSubcategory,
// //   isCreatingNew,
// //   setIsCreatingNew,
// //   newCatInput,
// //   setNewCatInput,
// //   newSubInput,
// //   setNewSubInput,
// //   savingNewTaxonomy,
// //   handleCreateTaxonomy,
// //   saveRule,
// //   setSaveRule,
// //   submitting,
// //   handleApplyClassification,
// //   onClose,
// // }) => {
// //   // Extract remarks from the first item of the active cluster
// //   const sampleItem = activePreviewCluster?.items?.[0];
// //   const remarksData = parseRemarks(sampleItem?.remarks);

// //   return (
// //     <div style={{ width: '42%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '24px', backgroundColor: '#0f0f12' }}>
// //       <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        
// //         {/* Active Audit Context Preview */}
// //         {activePreviewCluster && (
// //           <div style={{ backgroundColor: '#18181b', border: '1px solid #27272a', padding: '12px', borderRadius: '10px', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
// //             <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#f59e0b', fontWeight: 'bold' }}>
// //               Inspect Cluster Context: #{activePreviewCluster.pattern || 'UNCLASSIFIED'}
// //             </span>
// //             <p style={{ margin: 0, color: '#e4e4e7', lineHeight: '1.4' }}>
// //               {remarksData.display_text || sampleItem?.narration || activePreviewCluster.sample_descriptions?.[0] || 'No description'}
// //             </p>
// //             <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '2px' }}>
// //               {remarksData.payee && (
// //                 <span style={{ backgroundColor: '#1e1b4b', color: '#818cf8', padding: '2px 6px', borderRadius: '4px', fontSize: '10px' }}>
// //                   💳 Payee: {remarksData.payee}
// //                 </span>
// //               )}
// //               {remarksData.upi_ref && (
// //                 <span style={{ backgroundColor: '#27272a', color: '#a1a1aa', padding: '2px 6px', borderRadius: '4px', fontSize: '10px', fontFamily: 'monospace' }}>
// //                   Ref: {remarksData.upi_ref}
// //                 </span>
// //               )}
// //             </div>
// //           </div>
// //         )}

// //         {/* Selection Summary */}
// //         <div style={{ backgroundColor: '#18181b', border: '1px solid #27272a', padding: '14px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
// //           <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', fontWeight: 'bold' }}>
// //             Batch Target Summary
// //           </span>
// //           <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
// //             <span style={{ fontSize: '13px', fontWeight: 'bold', color: selectedSummary.totalTxns > 0 ? '#f59e0b' : '#71717a' }}>
// //               {selectedSummary.totalTxns} Item{selectedSummary.totalTxns !== 1 ? 's' : ''} Selected
// //             </span>
// //             <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f4f4f5' }}>
// //               {inrFormatter.format(selectedSummary?.totalAmount || 0)}
// //             </span>
// //           </div>
// //         </div>

// //         {/* Category Dropdowns / On-The-Go Creator */}
// //         <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
// //           <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #27272a', paddingBottom: '8px' }}>
// //             <h3 style={{ margin: 0, fontSize: '11px', fontWeight: 'bold', textTransform: 'uppercase', color: '#a1a1aa' }}>
// //               Assign Taxonomy Nodes
// //             </h3>
// //             <button
// //               onClick={() => setIsCreatingNew(!isCreatingNew)}
// //               style={{ background: 'none', border: 'none', color: '#f59e0b', fontSize: '11px', cursor: 'pointer', fontWeight: 'bold' }}
// //             >
// //               {isCreatingNew ? '← Back to Select' : '+ Create New Node'}
// //             </button>
// //           </div>

// //           {!isCreatingNew ? (
// //             <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
// //               <div>
// //                 <label style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
// //                   Primary Category
// //                 </label>
// //                 <select
// //                   value={selectedCategory}
// //                   onChange={(e) => {
// //                     const newCat = e.target.value;
// //                     setSelectedCategory(newCat);
// //                     const found = taxonomyTree.find((t) => t.category === newCat);
// //                     if (found && found.subcategories && found.subcategories.length > 0) {
// //                       setSelectedSubcategory(found.subcategories[0]);
// //                     }
// //                   }}
// //                   style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', color: '#f4f4f5', outline: 'none' }}
// //                 >
// //                   {taxonomyTree.map((t, catIdx) => (
// //                     <option key={`cat-${t.category}-${catIdx}`} value={t.category}>
// //                       {t.category}
// //                     </option>
// //                   ))}
// //                 </select>
// //               </div>

// //               <div>
// //                 <label style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
// //                   Subcategory
// //                 </label>
// //                 <select
// //                   value={selectedSubcategory || ''}
// //                   onChange={(e) => setSelectedSubcategory(e.target.value)}
// //                   style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', color: '#f4f4f5', outline: 'none' }}
// //                 >
// //                   {(availableSubcategories || []).map((sub, subIdx) => (
// //                     <option key={`sub-${sub}-${subIdx}`} value={sub}>
// //                       {sub}
// //                     </option>
// //                   ))}
// //                 </select>
// //               </div>
// //             </div>
// //           ) : (
// //             <div style={{ backgroundColor: '#18181b', border: '1px dashed #f59e0b', padding: '12px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
// //               <span style={{ fontSize: '11px', color: '#f59e0b', fontWeight: 'bold' }}>
// //                 New Taxonomy Entry
// //               </span>
// //               <div>
// //                 <label style={{ fontSize: '10px', color: '#a1a1aa', display: 'block', marginBottom: '2px' }}>
// //                   Category Name
// //                 </label>
// //                 <input
// //                   type="text"
// //                   placeholder="e.g. Expense"
// //                   value={newCatInput}
// //                   onChange={(e) => setNewCatInput(e.target.value)}
// //                   style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', fontSize: '12px', color: '#f4f4f5' }}
// //                 />
// //               </div>

// //               <div>
// //                 <label style={{ fontSize: '10px', color: '#a1a1aa', display: 'block', marginBottom: '2px' }}>
// //                   Subcategory Name
// //                 </label>
// //                 <input
// //                   type="text"
// //                   placeholder="e.g. Panchami Devi Temple"
// //                   value={newSubInput}
// //                   onChange={(e) => setNewSubInput(e.target.value)}
// //                   style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', fontSize: '12px', color: '#f4f4f5' }}
// //                 />
// //               </div>

// //               <button
// //                 onClick={handleCreateTaxonomy}
// //                 disabled={savingNewTaxonomy || !newCatInput.trim() || !newSubInput.trim()}
// //                 style={{
// //                   marginTop: '4px',
// //                   padding: '8px 12px',
// //                   borderRadius: '6px',
// //                   fontSize: '11px',
// //                   fontWeight: 'bold',
// //                   backgroundColor: '#f59e0b',
// //                   color: '#09090b',
// //                   border: 'none',
// //                   cursor: savingNewTaxonomy ? 'wait' : 'pointer',
// //                 }}
// //               >
// //                 {savingNewTaxonomy ? 'Saving...' : 'Add & Select Node'}
// //               </button>
// //             </div>
// //           )}
// //         </div>

// //         {/* Rule Toggle */}
// //         <div style={{ backgroundColor: '#09090b', border: '1px solid #27272a', padding: '12px', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
// //           <div>
// //             <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f4f4f5', display: 'block' }}>
// //               Save to Classification Rules
// //             </span>
// //             <span style={{ fontSize: '10px', color: '#71717a', display: 'block' }}>
// //               Auto-classify future imports matching active vendor pattern
// //             </span>
// //           </div>
// //           <input
// //             type="checkbox"
// //             checked={saveRule}
// //             onChange={(e) => setSaveRule(e.target.checked)}
// //             style={{ width: '16px', height: '16px', accentColor: '#f59e0b', cursor: 'pointer' }}
// //           />
// //         </div>

// //       </div>

// //       {/* Footer Buttons */}
// //       <div style={{ borderTop: '1px solid #27272a', paddingTop: '16px', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
// //         <button
// //           onClick={onClose}
// //           style={{ padding: '8px 16px', borderRadius: '8px', fontSize: '12px', color: '#a1a1aa', background: 'none', border: 'none', cursor: 'pointer' }}
// //         >
// //           Cancel
// //         </button>
// //         <button
// //           disabled={submitting || selectedSummary.allTxnIds.length === 0}
// //           onClick={handleApplyClassification}
// //           style={{
// //             padding: '10px 20px',
// //             borderRadius: '8px',
// //             fontSize: '12px',
// //             fontWeight: 'bold',
// //             backgroundColor: '#f59e0b',
// //             color: '#09090b',
// //             border: 'none',
// //             cursor: submitting || selectedSummary.allTxnIds.length === 0 ? 'not-allowed' : 'pointer',
// //             opacity: submitting || selectedSummary.allTxnIds.length === 0 ? 0.5 : 1,
// //           }}
// //         >
// //           {submitting ? 'Applying...' : `Reclassify ${selectedSummary.totalTxns} Selected Line${selectedSummary.totalTxns !== 1 ? 's' : ''}`}
// //         </button>
// //       </div>
// //     </div>
// //   );
// // };