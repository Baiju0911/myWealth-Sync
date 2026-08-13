import React, { useEffect } from 'react';
import type { TaxonomyOption, ExtendedCluster, Cluster, SuggestedRule } from '../../api/api';
import { inrFormatter } from '../../utils/classificationHelpers';

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
  upiStrategy: 'vendor' | 'auto_consolidate';
  setUpiStrategy: (val: 'vendor' | 'auto_consolidate') => void;
  vectorType: 'Debit' | 'Credit';
  submitting: boolean;
  handleApplyClassification: () => void;
  onClose: () => void;
  suggestedRule?: SuggestedRule | null;
}

export const TaxonomyMapperPanel: React.FC<Props> = ({
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
  upiStrategy,
  setUpiStrategy,
  vectorType,
  submitting,
  handleApplyClassification,
  onClose,
  suggestedRule = null,
}) => {

  // 💡 Auto-switch strategy to 'vendor' when inspecting an explicit entity pattern
  useEffect(() => {
    if (activePreviewCluster?.pattern) {
      const cleanPattern = activePreviewCluster.pattern.replace(/^#+/, '');
      // If inspecting a specific entity (not a bank generic rail like #YESB or #SBIN)
      if (!['YESB', 'SBIN', 'HDFC', 'ICIC', 'PAYTM'].includes(cleanPattern.toUpperCase())) {
        setUpiStrategy('vendor');
      }
    }
  }, [activePreviewCluster, setUpiStrategy]);

  const getCategoryColor = (category: string) => {
    switch (category) {
      case 'Income': return '#34d399';
      case 'Expense': return '#f87171';
      case 'Asset': return '#38bdf8';
      case 'Liability': return '#fb923c';
      case 'Transfer': return '#c084fc';
      default: return '#f4f4f5';
    }
  };
  const isUpiSelection = (cluster: ExtendedCluster | Cluster | null, items: any[] = []): boolean => {
  // If inspecting a cluster pattern starting with UPI or bank handle
  if (cluster?.pattern) {
    const pattern = cluster.pattern.toUpperCase();
    if (pattern.includes('UPI') || pattern.includes('PAYTM') || pattern.includes('YBL')) return true;
  }

  // Fallback: Check raw narration string of selected items
  if (items && items.length > 0) {
    return items.some((item) => {
      const narration = (item.narration || '').toUpperCase();
      return narration.startsWith('UPI/') || narration.includes('/UPI/') || narration.includes('@');
    });
  }

  return false;
};

  return (
    <div style={{ width: '42%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '24px', backgroundColor: '#0f0f12', overflowY: 'auto' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        
        {/* Active Inspection Context Badge */}
        {activePreviewCluster ? (
          <div style={{ backgroundColor: '#18181b', border: '1px solid #27272a', padding: '12px', borderRadius: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span style={{ fontSize: '10px', color: '#71717a', textTransform: 'uppercase', display: 'block', fontWeight: 'bold' }}>
                Inspecting Pattern
              </span>
              <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f59e0b', fontFamily: 'monospace' }}>
                #{(activePreviewCluster.pattern || 'UNCLASSIFIED').replace(/^#+/, '')}
              </span>
            </div>
            <span style={{ fontSize: '10px', color: '#a1a1aa', backgroundColor: '#27272a', padding: '4px 8px', borderRadius: '4px', fontFamily: 'monospace' }}>
              {activePreviewCluster.count || activePreviewCluster.transaction_ids?.length || 0} Total Rows
            </span>
          </div>
        ) : (
          <div style={{ backgroundColor: '#18181b', border: '1px dashed #3f3f46', padding: '14px', borderRadius: '10px', textAlign: 'center', color: '#71717a', fontSize: '11px' }}>
            👈 Select a cluster on the left to inspect patterns.
          </div>
        )}

        {/* 💡 Smart Rule Suggestion Pill */}
        {suggestedRule && (
          <div style={{ backgroundColor: '#1e1b4b', border: '1px solid #6366f1', padding: '12px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#818cf8', fontWeight: 'bold' }}>
                💡 Suggested Rule Mapping
              </span>
              <button
                type="button"
                onClick={() => {
                  const ruleAny = suggestedRule as any;
                  const cat = ruleAny.suggested_category || ruleAny.target_category || 'Expense';
                  const sub = ruleAny.suggested_subcategory || ruleAny.target_subcategory || '';
                  setSelectedCategory(cat);
                  setSelectedSubcategory(sub);
                }}
                style={{ backgroundColor: '#6366f1', color: '#ffffff', border: 'none', padding: '2px 8px', borderRadius: '4px', fontSize: '10px', cursor: 'pointer', fontWeight: 'bold' }}
              >
                Apply Suggestion
              </button>
            </div>
            <span style={{ fontSize: '11px', color: '#c7d2fe' }}>
              {(suggestedRule as any).suggested_category || (suggestedRule as any).target_category} ➔ <strong>{(suggestedRule as any).suggested_subcategory || (suggestedRule as any).target_subcategory}</strong>
            </span>
          </div>
        )}

        {/* Batch Target Summary */}
        <div style={{ backgroundColor: '#18181b', border: '1px solid #27272a', padding: '12px 14px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', fontWeight: 'bold' }}>
            Batch Reclassification Selection
          </span>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '13px', fontWeight: 'bold', color: selectedSummary.totalTxns > 0 ? '#f59e0b' : '#71717a' }}>
              {selectedSummary.totalTxns} Item{selectedSummary.totalTxns !== 1 ? 's' : ''} Selected
            </span>
            <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f4f4f5', fontFamily: 'monospace' }}>
              {inrFormatter.format(selectedSummary?.totalAmount || 0)}
            </span>
          </div>
        </div>

        {/* Assign Taxonomy Dropdowns */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #27272a', paddingBottom: '6px' }}>
            <h3 style={{ margin: 0, fontSize: '11px', fontWeight: 'bold', textTransform: 'uppercase', color: '#a1a1aa' }}>
              Assign Destination Node
            </h3>
            <button
              type="button"
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
                  style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', color: getCategoryColor(selectedCategory), fontWeight: 'bold', outline: 'none' }}
                >
                  {taxonomyTree.map((t, catIdx) => (
                    <option key={`cat-${t.category}-${catIdx}`} value={t.category} style={{ color: '#f4f4f5', backgroundColor: '#18181b' }}>
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
                    <option key={`sub-${sub}-${subIdx}`} value={sub} style={{ color: '#f4f4f5', backgroundColor: '#18181b' }}>
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
              <input
                type="text"
                placeholder="Category (e.g., Expense)"
                value={newCatInput}
                onChange={(e) => setNewCatInput(e.target.value)}
                style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', fontSize: '12px', color: '#f4f4f5' }}
              />
              <input
                type="text"
                placeholder="Subcategory (e.g., Software Subscriptions)"
                value={newSubInput}
                onChange={(e) => setNewSubInput(e.target.value)}
                style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', fontSize: '12px', color: '#f4f4f5' }}
              />
              <button
                type="button"
                onClick={handleCreateTaxonomy}
                disabled={savingNewTaxonomy || !newCatInput.trim() || !newSubInput.trim()}
                style={{ padding: '8px', borderRadius: '6px', fontSize: '11px', fontWeight: 'bold', backgroundColor: '#f59e0b', color: '#09090b', border: 'none', cursor: 'pointer' }}
              >
                {savingNewTaxonomy ? 'Saving...' : 'Add & Select Node'}
              </button>
            </div>
          )}
        </div>

        {/* Save to Learned Rules Toggle & Strategy Options */}
        <div style={{ backgroundColor: '#09090b', border: '1px solid #27272a', padding: '12px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f4f4f5', display: 'block' }}>
                Save to Classification Rules
              </span>
              <span style={{ fontSize: '10px', color: '#71717a', display: 'block' }}>
                Allows Node 99 Rule Sweep Hub to auto-clear future matches
              </span>
            </div>
            <input
              type="checkbox"
              checked={saveRule}
              onChange={(e) => setSaveRule(e.target.checked)}
              style={{ width: '16px', height: '16px', accentColor: '#f59e0b', cursor: 'pointer' }}
            />
          </div>

          {/* 💡 Sub-Option: UPI Strategy Selector (Strictly Gated for Debits AND Active Selection) */}
          {saveRule && vectorType === 'Debit' && selectedSummary.totalTxns > 0 && isUpiSelection(activePreviewCluster, activePreviewCluster?.items) && (
            <div style={{ borderTop: '1px solid #1c1c20', paddingTop: '8px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <span style={{ fontSize: '10px', color: '#a1a1aa', fontWeight: 'bold', textTransform: 'uppercase' }}>
                UPI Rule Matching Strategy
              </span>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', color: '#d4d4d8', cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="upiStrategy"
                  value="auto_consolidate"
                  checked={upiStrategy === 'auto_consolidate'}
                  onChange={() => setUpiStrategy('auto_consolidate')}
                  style={{ accentColor: '#f59e0b' }}
                />
                ⚡ Auto-Consolidate as UPI Merchant (Apply Normalizer)
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', color: '#d4d4d8', cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="upiStrategy"
                  value="vendor"
                  checked={upiStrategy === 'vendor'}
                  onChange={() => setUpiStrategy('vendor')}
                  style={{ accentColor: '#f59e0b' }}
                />
                🏷️ Anchor to Clean Vendor Name Only
              </label>
            </div>
          )}
        </div>

      </div>

      {/* Footer Action Bar */}
      <div style={{ borderTop: '1px solid #27272a', paddingTop: '14px', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
        <button
          type="button"
          onClick={onClose}
          style={{ padding: '8px 16px', borderRadius: '8px', fontSize: '12px', color: '#a1a1aa', background: 'none', border: 'none', cursor: 'pointer' }}
        >
          Cancel
        </button>
        <button
          type="button"
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
// import type { TaxonomyOption, ExtendedCluster, Cluster, SuggestedRule } from '../../api';
// import { inrFormatter } from '../../utils/classificationHelpers';

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
//   suggestedRule?: SuggestedRule | null;
// }

// export const TaxonomyMapperPanel: React.FC<Props> = ({
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
//   suggestedRule = null,
// }) => {
//   const getCategoryColor = (category: string) => {
//     switch (category) {
//       case 'Income': return '#34d399';
//       case 'Expense': return '#f87171';
//       case 'Asset': return '#38bdf8';
//       case 'Liability': return '#fb923c';
//       case 'Transfer': return '#c084fc';
//       default: return '#f4f4f5';
//     }
//   };

//   return (
//     <div style={{ width: '42%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '24px', backgroundColor: '#0f0f12', overflowY: 'auto' }}>
//       <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        
//         {/* Active Inspection Context Badge */}
//         {activePreviewCluster ? (
//           <div style={{ backgroundColor: '#18181b', border: '1px solid #27272a', padding: '12px', borderRadius: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
//             <div>
//               <span style={{ fontSize: '10px', color: '#71717a', textTransform: 'uppercase', display: 'block', fontWeight: 'bold' }}>
//                 Inspecting Pattern
//               </span>
//               <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f59e0b', fontFamily: 'monospace' }}>
//                 #{(activePreviewCluster.pattern || 'UNCLASSIFIED').replace(/^#+/, '')}
//               </span>
//             </div>
//             <span style={{ fontSize: '10px', color: '#a1a1aa', backgroundColor: '#27272a', padding: '4px 8px', borderRadius: '4px', fontFamily: 'monospace' }}>
//               {activePreviewCluster.count || activePreviewCluster.transaction_ids?.length || 0} Total Rows
//             </span>
//           </div>
//         ) : (
//           <div style={{ backgroundColor: '#18181b', border: '1px dashed #3f3f46', padding: '14px', borderRadius: '10px', textAlign: 'center', color: '#71717a', fontSize: '11px' }}>
//             👈 Select a cluster on the left to inspect patterns.
//           </div>
//         )}

// {/* 💡 Smart Rule Suggestion Pill */}
//         {suggestedRule && (
//           <div style={{ backgroundColor: '#1e1b4b', border: '1px solid #6366f1', padding: '12px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
//             <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
//               <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#818cf8', fontWeight: 'bold' }}>
//                 💡 Suggested Rule Mapping
//               </span>
//               <button
//                 type="button"
//                 onClick={() => {
//                   const ruleAny = suggestedRule as any;
//                   const cat = ruleAny.suggested_category || ruleAny.target_category || 'Expense';
//                   const sub = ruleAny.suggested_subcategory || ruleAny.target_subcategory || '';
//                   setSelectedCategory(cat);
//                   setSelectedSubcategory(sub);
//                 }}
//                 style={{ backgroundColor: '#6366f1', color: '#ffffff', border: 'none', padding: '2px 8px', borderRadius: '4px', fontSize: '10px', cursor: 'pointer', fontWeight: 'bold' }}
//               >
//                 Apply Suggestion
//               </button>
//             </div>
//             <span style={{ fontSize: '11px', color: '#c7d2fe' }}>
//               {(suggestedRule as any).suggested_category || (suggestedRule as any).target_category} ➔ <strong>{(suggestedRule as any).suggested_subcategory || (suggestedRule as any).target_subcategory}</strong>
//             </span>
//           </div>
//         )}

//         {/* Batch Target Summary */}
//         <div style={{ backgroundColor: '#18181b', border: '1px solid #27272a', padding: '12px 14px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
//           <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', fontWeight: 'bold' }}>
//             Batch Reclassification Selection
//           </span>
//           <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
//             <span style={{ fontSize: '13px', fontWeight: 'bold', color: selectedSummary.totalTxns > 0 ? '#f59e0b' : '#71717a' }}>
//               {selectedSummary.totalTxns} Item{selectedSummary.totalTxns !== 1 ? 's' : ''} Selected
//             </span>
//             <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f4f4f5', fontFamily: 'monospace' }}>
//               {inrFormatter.format(selectedSummary?.totalAmount || 0)}
//             </span>
//           </div>
//         </div>

//         {/* Assign Taxonomy Dropdowns */}
//         <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
//           <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #27272a', paddingBottom: '6px' }}>
//             <h3 style={{ margin: 0, fontSize: '11px', fontWeight: 'bold', textTransform: 'uppercase', color: '#a1a1aa' }}>
//               Assign Destination Node
//             </h3>
//             <button
//               type="button"
//               onClick={() => setIsCreatingNew(!isCreatingNew)}
//               style={{ background: 'none', border: 'none', color: '#f59e0b', fontSize: '11px', cursor: 'pointer', fontWeight: 'bold' }}
//             >
//               {isCreatingNew ? '← Back to Select' : '+ Create New Node'}
//             </button>
//           </div>

//           {!isCreatingNew ? (
//             <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
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
//                   style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', color: getCategoryColor(selectedCategory), fontWeight: 'bold', outline: 'none' }}
//                 >
//                   {taxonomyTree.map((t, catIdx) => (
//                     <option key={`cat-${t.category}-${catIdx}`} value={t.category} style={{ color: '#f4f4f5', backgroundColor: '#18181b' }}>
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
//                     <option key={`sub-${sub}-${subIdx}`} value={sub} style={{ color: '#f4f4f5', backgroundColor: '#18181b' }}>
//                       {sub}
//                     </option>
//                   ))}
//                 </select>
//               </div>
//             </div>
//           ) : (
//             <div style={{ backgroundColor: '#18181b', border: '1px dashed #f59e0b', padding: '12px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
//               <span style={{ fontSize: '11px', color: '#f59e0b', fontWeight: 'bold' }}>
//                 New Taxonomy Entry
//               </span>
//               <input
//                 type="text"
//                 placeholder="Category (e.g., Expense)"
//                 value={newCatInput}
//                 onChange={(e) => setNewCatInput(e.target.value)}
//                 style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', fontSize: '12px', color: '#f4f4f5' }}
//               />
//               <input
//                 type="text"
//                 placeholder="Subcategory (e.g., Software Subscriptions)"
//                 value={newSubInput}
//                 onChange={(e) => setNewSubInput(e.target.value)}
//                 style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', fontSize: '12px', color: '#f4f4f5' }}
//               />
//               <button
//                 type="button"
//                 onClick={handleCreateTaxonomy}
//                 disabled={savingNewTaxonomy || !newCatInput.trim() || !newSubInput.trim()}
//                 style={{ padding: '8px', borderRadius: '6px', fontSize: '11px', fontWeight: 'bold', backgroundColor: '#f59e0b', color: '#09090b', border: 'none', cursor: 'pointer' }}
//               >
//                 {savingNewTaxonomy ? 'Saving...' : 'Add & Select Node'}
//               </button>
//             </div>
//           )}
//         </div>

//         {/* Save to Learned Rules Toggle */}
//         <div style={{ backgroundColor: '#09090b', border: '1px solid #27272a', padding: '10px 12px', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
//           <div>
//             <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f4f4f5', display: 'block' }}>
//               Save to Classification Rules
//             </span>
//             <span style={{ fontSize: '10px', color: '#71717a', display: 'block' }}>
//               Allows Node 99 Rule Sweep Hub to auto-clear future matches
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

//       {/* Footer Action Bar */}
//       <div style={{ borderTop: '1px solid #27272a', paddingTop: '14px', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
//         <button
//           type="button"
//           onClick={onClose}
//           style={{ padding: '8px 16px', borderRadius: '8px', fontSize: '12px', color: '#a1a1aa', background: 'none', border: 'none', cursor: 'pointer' }}
//         >
//           Cancel
//         </button>
//         <button
//           type="button"
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




// import React from 'react';
// import type { TaxonomyOption, ExtendedCluster, Cluster } from '../../api';
// import { inrFormatter } from '../../utils/classificationHelpers';

// export interface SuggestedRule {
//   rule_code: string;
//   suggested_category: string;
//   suggested_subcategory: string;
//   matched_pattern: string;
//   target_category?: string;
//   target_subcategory?: string;
// }

// // interface Props {
// //   targetSubcategoryContext?: string;
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
// //   selectedTxnIds?: string[];
// //   suggestedRule?: SuggestedRule | null;
// // }


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
//   selectedTxnIds?: string[];
//   toggleClusterTxns?: (clusterTxnIds: string[], e: React.MouseEvent) => void; // 👈 Add back as optional
//   suggestedRule?: SuggestedRule | null;
// }
// export const TaxonomyMapperPanel: React.FC<Props> = ({
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
//   suggestedRule = null,
// }) => {

//   const getCategoryColor = (category: string) => {
//     switch (category) {
//       case 'Income': return '#34d399';
//       case 'Expense': return '#f87171';
//       case 'Asset': return '#38bdf8';
//       case 'Liability': return '#fb923c';
//       case 'Transfer': return '#c084fc';
//       default: return '#f4f4f5';
//     }
//   };

//   return (
//     <div style={{ width: '42%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '24px', backgroundColor: '#0f0f12', overflowY: 'auto' }}>
//       <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        
//         {/* 📊 Active Inspection Context Badge */}
//         {activePreviewCluster ? (
//           <div style={{ backgroundColor: '#18181b', border: '1px solid #27272a', padding: '12px', borderRadius: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
//             <div>
//               <span style={{ fontSize: '10px', color: '#71717a', textTransform: 'uppercase', display: 'block', fontWeight: 'bold' }}>
//                 Inspecting Pattern
//               </span>
//               <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f59e0b', fontFamily: 'monospace' }}>
//                 #{(activePreviewCluster.pattern || 'UNCLASSIFIED').replace(/^#+/, '')}
//               </span>
//             </div>
//             <span style={{ fontSize: '10px', color: '#a1a1aa', backgroundColor: '#27272a', padding: '4px 8px', borderRadius: '4px', fontFamily: 'monospace' }}>
//               {activePreviewCluster.count || activePreviewCluster.transaction_ids?.length || 0} Total Cluster Rows
//             </span>
//           </div>
//         ) : (
//           <div style={{ backgroundColor: '#18181b', border: '1px dashed #3f3f46', padding: '14px', borderRadius: '10px', textAlign: 'center', color: '#71717a', fontSize: '11px' }}>
//             👈 Select a cluster on the left to inspect patterns.
//           </div>
//         )}
//         {/* 💡 Smart Rule Suggestion Pill (If Detected) */}
//         {suggestedRule && (
//           <div style={{ backgroundColor: '#1e1b4b', border: '1px solid #6366f1', padding: '12px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
//             <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
//               <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#818cf8', fontWeight: 'bold' }}>
//                 💡 Suggested Rule Mapping
//               </span>
//               <button
//                 type="button"
//                 onClick={() => {
//                   const cat = suggestedRule.suggested_category || suggestedRule.target_category || 'Expense';
//                   const sub = suggestedRule.suggested_subcategory || suggestedRule.target_subcategory || '';
//                   setSelectedCategory(cat);
//                   setSelectedSubcategory(sub);
//                 }}
//                 style={{ backgroundColor: '#6366f1', color: '#ffffff', border: 'none', padding: '2px 8px', borderRadius: '4px', fontSize: '10px', cursor: 'pointer', fontWeight: 'bold' }}
//               >
//                 Apply Suggestion
//               </button>
//             </div>
//             <span style={{ fontSize: '11px', color: '#c7d2fe' }}>
//               {suggestedRule.suggested_category || suggestedRule.target_category} ➔ <strong>{suggestedRule.suggested_subcategory || suggestedRule.target_subcategory}</strong>
//             </span>
//           </div>
//         )}

//         {/* 🏷️ Batch Target Summary */}
//         <div style={{ backgroundColor: '#18181b', border: '1px solid #27272a', padding: '12px 14px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
//           <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', fontWeight: 'bold' }}>
//             Batch Reclassification Selection
//           </span>
//           <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
//             <span style={{ fontSize: '13px', fontWeight: 'bold', color: selectedSummary.totalTxns > 0 ? '#f59e0b' : '#71717a' }}>
//               {selectedSummary.totalTxns} Item{selectedSummary.totalTxns !== 1 ? 's' : ''} Selected
//             </span>
//             <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f4f4f5', fontFamily: 'monospace' }}>
//               {inrFormatter.format(selectedSummary?.totalAmount || 0)}
//             </span>
//           </div>
//         </div>

//         {/* 🏷️ Assign Taxonomy Dropdowns */}
//         <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
//           <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #27272a', paddingBottom: '6px' }}>
//             <h3 style={{ margin: 0, fontSize: '11px', fontWeight: 'bold', textTransform: 'uppercase', color: '#a1a1aa' }}>
//               Assign Destination Node
//             </h3>
//             <button
//               type="button"
//               onClick={() => setIsCreatingNew(!isCreatingNew)}
//               style={{ background: 'none', border: 'none', color: '#f59e0b', fontSize: '11px', cursor: 'pointer', fontWeight: 'bold' }}
//             >
//               {isCreatingNew ? '← Back to Select' : '+ Create New Node'}
//             </button>
//           </div>

//           {!isCreatingNew ? (
//             <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
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
//                   style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', color: getCategoryColor(selectedCategory), fontWeight: 'bold', outline: 'none' }}
//                 >
//                   {taxonomyTree.map((t, catIdx) => (
//                     <option key={`cat-${t.category}-${catIdx}`} value={t.category} style={{ color: '#f4f4f5', backgroundColor: '#18181b' }}>
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
//                     <option key={`sub-${sub}-${subIdx}`} value={sub} style={{ color: '#f4f4f5', backgroundColor: '#18181b' }}>
//                       {sub}
//                     </option>
//                   ))}
//                 </select>
//               </div>
//             </div>
//           ) : (
//             <div style={{ backgroundColor: '#18181b', border: '1px dashed #f59e0b', padding: '12px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
//               <span style={{ fontSize: '11px', color: '#f59e0b', fontWeight: 'bold' }}>
//                 New Taxonomy Entry
//               </span>
//               <input
//                 type="text"
//                 placeholder="Category (e.g., Expense)"
//                 value={newCatInput}
//                 onChange={(e) => setNewCatInput(e.target.value)}
//                 style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', fontSize: '12px', color: '#f4f4f5' }}
//               />
//               <input
//                 type="text"
//                 placeholder="Subcategory (e.g., Software Subscriptions)"
//                 value={newSubInput}
//                 onChange={(e) => setNewSubInput(e.target.value)}
//                 style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', fontSize: '12px', color: '#f4f4f5' }}
//               />
//               <button
//                 type="button"
//                 onClick={handleCreateTaxonomy}
//                 disabled={savingNewTaxonomy || !newCatInput.trim() || !newSubInput.trim()}
//                 style={{ padding: '8px', borderRadius: '6px', fontSize: '11px', fontWeight: 'bold', backgroundColor: '#f59e0b', color: '#09090b', border: 'none', cursor: 'pointer' }}
//               >
//                 {savingNewTaxonomy ? 'Saving...' : 'Add & Select Node'}
//               </button>
//             </div>
//           )}
//         </div>

//         {/* ⚙️ Save to Learned Rules Toggle */}
//         <div style={{ backgroundColor: '#09090b', border: '1px solid #27272a', padding: '10px 12px', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
//           <div>
//             <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f4f4f5', display: 'block' }}>
//               Save to Classification Rules
//             </span>
//             <span style={{ fontSize: '10px', color: '#71717a', display: 'block' }}>
//               Allows Node 99 Rule Sweep Hub to auto-clear future matches
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

//       {/* 🚀 Footer Action Bar */}
//       <div style={{ borderTop: '1px solid #27272a', paddingTop: '14px', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
//         <button
//           type="button"
//           onClick={onClose}
//           style={{ padding: '8px 16px', borderRadius: '8px', fontSize: '12px', color: '#a1a1aa', background: 'none', border: 'none', cursor: 'pointer' }}
//         >
//           Cancel
//         </button>
//         <button
//           type="button"
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


// import React from 'react';
// import type { TaxonomyOption, ExtendedCluster, Cluster } from '../../api';
// import { inrFormatter, parseRemarks } from '../../utils/classificationHelpers';

// export interface SuggestedRule {
//   rule_code: string;
//   suggested_category: string;
//   suggested_subcategory: string;
//   matched_pattern: string;
// }

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
//   selectedTxnIds?: string[];
//   toggleClusterTxns?: (clusterTxnIds: string[], e: React.MouseEvent) => void;
//   // 🟢 Props for Smart Existing Rule Suggestion
//   suggestedRule?: SuggestedRule | null;
// }

// export const TaxonomyMapperPanel: React.FC<Props> = ({
//   // targetSubcategoryContext,
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
//   selectedTxnIds = [],
//   toggleClusterTxns,
//   suggestedRule = null,
// }) => {
//   const sampleItem = activePreviewCluster?.items?.[0];
//   const remarksData = parseRemarks(sampleItem?.remarks);

//   // Check direction vector of active preview sample item
//   const isCreditInflow = (sampleItem?.credit || 0) > 0;
//   const clusterTxns = activePreviewCluster?.transaction_ids || [];
//   const allClusterSelected = clusterTxns.length > 0 && clusterTxns.every((id) => selectedTxnIds.includes(id));

//   return (
//     <div style={{ width: '42%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '24px', backgroundColor: '#0f0f12', overflowY: 'auto' }}>
//       <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        
//         {/* Active Audit Context Preview */}
//         {activePreviewCluster && (
//           <div style={{ backgroundColor: '#18181b', border: '1px solid #27272a', padding: '12px', borderRadius: '10px', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
//             <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
//               <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#f59e0b', fontWeight: 'bold' }}>
//                 Inspect Context: #{activePreviewCluster.pattern || 'UNCLASSIFIED'}
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

//         {/* 💡 SMART EXISTING RULE SUGGESTION BANNER */}
//         {suggestedRule && (
//           <div style={{ backgroundColor: '#1e1b4b', border: '1px solid #6366f1', padding: '12px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
//             <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
//               <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#818cf8', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '4px' }}>
//                 💡 Existing Rule Detected
//               </span>
//               <span style={{ fontSize: '9px', color: '#c7d2fe', backgroundColor: '#312e81', padding: '2px 6px', borderRadius: '4px', fontFamily: 'monospace' }}>
//                 {suggestedRule.rule_code}
//               </span>
//             </div>
//             <p style={{ margin: 0, fontSize: '11px', color: '#a5b4fc', lineHeight: '1.4' }}>
//               Pattern <code style={{ color: '#ffffff', backgroundColor: '#312e81', padding: '1px 4px', borderRadius: '3px' }}>"{suggestedRule.matched_pattern}"</code> previously mapped to:
//               <br />
//               <strong style={{ color: '#ffffff', fontSize: '12px' }}>
//                 {suggestedRule.suggested_category} → {suggestedRule.suggested_subcategory}
//               </strong>
//             </p>
//             <button
//               type="button"
//               onClick={() => {
//                 setSelectedCategory(suggestedRule.suggested_category);
//                 setSelectedSubcategory(suggestedRule.suggested_subcategory);
//               }}
//               style={{
//                 width: '100%',
//                 padding: '7px 12px',
//                 borderRadius: '6px',
//                 fontSize: '11px',
//                 fontWeight: 'bold',
//                 backgroundColor: '#6366f1',
//                 color: '#ffffff',
//                 border: 'none',
//                 cursor: 'pointer',
//                 transition: 'background 0.2s ease',
//               }}
//             >
//               ⚡ Apply {suggestedRule.suggested_subcategory}
//             </button>
//           </div>
//         )}

//         {/* ⚡ PATTERN MATCH SWEEP PROMPT */}
//         {activePreviewCluster && clusterTxns.length > 0 && toggleClusterTxns && (
//           <div style={{ backgroundColor: '#18181b', border: '1px solid #3f3f46', padding: '12px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
//             <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
//               <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#38bdf8', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '4px' }}>
//                 ⚡ Pattern Sweep Available
//               </span>
//               <span style={{ fontSize: '10px', color: '#f59e0b', backgroundColor: 'rgba(245, 158, 11, 0.15)', padding: '2px 6px', borderRadius: '4px', fontWeight: 'bold' }}>
//                 {clusterTxns.length} Rows
//               </span>
//             </div>

//             {/* 🏷️ TARGET TAXONOMY CONTEXT BADGE */}
//             <div style={{ backgroundColor: '#09090b', padding: '6px 10px', borderRadius: '6px', border: '1px solid #27272a', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
//               <span style={{ fontSize: '10px', color: '#71717a', textTransform: 'uppercase' }}>Target Destination:</span>
//               <span style={{ fontSize: '11px', fontWeight: 'bold', color: '#f4f4f5' }}>
//                 <span style={{ color: selectedCategory === 'Income' ? '#34d399' : '#f87171' }}>{selectedCategory}</span> 
//                 <span style={{ color: '#71717a', margin: '0 4px' }}>→</span> 
//                 <span style={{ color: '#f59e0b' }}>{selectedSubcategory}</span>
//               </span>
//             </div>

//             <p style={{ margin: 0, fontSize: '11px', color: '#a1a1aa' }}>
//               Identified <strong style={{ color: '#f4f4f5' }}>{clusterTxns.length}</strong> matching transaction{clusterTxns.length !== 1 ? 's' : ''} for pattern <code style={{ color: '#38bdf8' }}>"{activePreviewCluster.pattern}"</code>.
//             </p>

//             <button
//               type="button"
//               onClick={(e) => toggleClusterTxns(clusterTxns, e)}
//               style={{
//                 width: '100%',
//                 padding: '6px 12px',
//                 borderRadius: '6px',
//                 fontSize: '11px',
//                 fontWeight: 'bold',
//                 backgroundColor: allClusterSelected ? '#27272a' : '#38bdf8',
//                 color: allClusterSelected ? '#f4f4f5' : '#09090b',
//                 border: allClusterSelected ? '1px solid #3f3f46' : 'none',
//                 cursor: 'pointer',
//                 transition: 'all 0.2s ease',
//               }}
//             >
//               {allClusterSelected
//                 ? `✓ All ${clusterTxns.length} Rows Selected for [${selectedSubcategory}]`
//                 : `Select All ${clusterTxns.length} Rows for [${selectedSubcategory}]`}
//             </button>
//           </div>
//         )}

//         {/* Selection Summary */}
//         <div style={{ backgroundColor: '#18181b', border: '1px solid #27272a', padding: '12px 14px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
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

//         {/* Category Dropdowns / Creator */}
//         <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
//           <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #27272a', paddingBottom: '6px' }}>
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
//             <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
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
//             <div style={{ backgroundColor: '#18181b', border: '1px dashed #f59e0b', padding: '12px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
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
//         <div style={{ backgroundColor: '#09090b', border: '1px solid #27272a', padding: '10px 12px', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
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
//       <div style={{ borderTop: '1px solid #27272a', paddingTop: '14px', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
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
// //   targetSubcategoryContext?: string;
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
// //   targetSubcategoryContext,
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
// //   const sampleItem = activePreviewCluster?.items?.[0];
// //   const remarksData = parseRemarks(sampleItem?.remarks);

// //   // Check direction of current active sample item
// //   const isCreditInflow = (sampleItem?.credit || 0) > 0;

// //   return (
// //     <div style={{ width: '42%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '24px', backgroundColor: '#0f0f12' }}>
// //       <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        
// //         {/* Active Audit Context Preview */}
// //         {activePreviewCluster && (
// //           <div style={{ backgroundColor: '#18181b', border: '1px solid #27272a', padding: '12px', borderRadius: '10px', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
// //             <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
// //               <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#f59e0b', fontWeight: 'bold' }}>
// //                 Inspect Cluster Context: #{activePreviewCluster.pattern || 'UNCLASSIFIED'}
// //               </span>
// //               <span style={{ 
// //                 fontSize: '9px', 
// //                 fontWeight: 'bold', 
// //                 padding: '2px 6px', 
// //                 borderRadius: '4px',
// //                 backgroundColor: isCreditInflow ? 'rgba(52, 211, 153, 0.15)' : 'rgba(244, 63, 94, 0.15)',
// //                 color: isCreditInflow ? '#34d399' : '#f43f5e',
// //                 border: isCreditInflow ? '1px solid rgba(52, 211, 153, 0.3)' : '1px solid rgba(244, 63, 94, 0.3)'
// //               }}>
// //                 {isCreditInflow ? 'INFLOW (CREDIT)' : 'OUTFLOW (DEBIT)'}
// //               </span>
// //             </div>
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
// //                       {t.category === 'Income' ? '🟢 Income (Inflows)' : t.category === 'Expense' ? '🔴 Expense (Outflows)' : t.category}
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
// //                   placeholder="e.g. Income or Expense"
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
// //                   placeholder="e.g. Dividend Income"
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




// // // import React from 'react';
// // // import type { TaxonomyOption, ExtendedCluster, Cluster } from '../../api';
// // // import { inrFormatter, parseRemarks } from '../../utils/classificationHelpers';

// // // interface Props {
// // //   selectedSummary: { totalTxns: number; totalAmount: number; allTxnIds: string[] };
// // //   activePreviewCluster: ExtendedCluster | Cluster | null;
// // //   taxonomyTree: TaxonomyOption[];
// // //   availableSubcategories: string[];
// // //   selectedCategory: string;
// // //   setSelectedCategory: (cat: string) => void;
// // //   selectedSubcategory: string;
// // //   setSelectedSubcategory: (sub: string) => void;
// // //   isCreatingNew: boolean;
// // //   setIsCreatingNew: (val: boolean) => void;
// // //   newCatInput: string;
// // //   setNewCatInput: (v: string) => void;
// // //   newSubInput: string;
// // //   setNewSubInput: (v: string) => void;
// // //   savingNewTaxonomy: boolean;
// // //   handleCreateTaxonomy: () => void;
// // //   saveRule: boolean;
// // //   setSaveRule: (val: boolean) => void;
// // //   submitting: boolean;
// // //   handleApplyClassification: () => void;
// // //   onClose: () => void;
// // // }

// // // export const TaxonomyMapperPanel: React.FC<Props> = ({
// // //   selectedSummary,
// // //   activePreviewCluster,
// // //   taxonomyTree,
// // //   availableSubcategories,
// // //   selectedCategory,
// // //   setSelectedCategory,
// // //   selectedSubcategory,
// // //   setSelectedSubcategory,
// // //   isCreatingNew,
// // //   setIsCreatingNew,
// // //   newCatInput,
// // //   setNewCatInput,
// // //   newSubInput,
// // //   setNewSubInput,
// // //   savingNewTaxonomy,
// // //   handleCreateTaxonomy,
// // //   saveRule,
// // //   setSaveRule,
// // //   submitting,
// // //   handleApplyClassification,
// // //   onClose,
// // // }) => {
// // //   // Extract remarks from the first item of the active cluster
// // //   const sampleItem = activePreviewCluster?.items?.[0];
// // //   const remarksData = parseRemarks(sampleItem?.remarks);

// // //   return (
// // //     <div style={{ width: '42%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '24px', backgroundColor: '#0f0f12' }}>
// // //       <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        
// // //         {/* Active Audit Context Preview */}
// // //         {activePreviewCluster && (
// // //           <div style={{ backgroundColor: '#18181b', border: '1px solid #27272a', padding: '12px', borderRadius: '10px', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
// // //             <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#f59e0b', fontWeight: 'bold' }}>
// // //               Inspect Cluster Context: #{activePreviewCluster.pattern || 'UNCLASSIFIED'}
// // //             </span>
// // //             <p style={{ margin: 0, color: '#e4e4e7', lineHeight: '1.4' }}>
// // //               {remarksData.display_text || sampleItem?.narration || activePreviewCluster.sample_descriptions?.[0] || 'No description'}
// // //             </p>
// // //             <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '2px' }}>
// // //               {remarksData.payee && (
// // //                 <span style={{ backgroundColor: '#1e1b4b', color: '#818cf8', padding: '2px 6px', borderRadius: '4px', fontSize: '10px' }}>
// // //                   💳 Payee: {remarksData.payee}
// // //                 </span>
// // //               )}
// // //               {remarksData.upi_ref && (
// // //                 <span style={{ backgroundColor: '#27272a', color: '#a1a1aa', padding: '2px 6px', borderRadius: '4px', fontSize: '10px', fontFamily: 'monospace' }}>
// // //                   Ref: {remarksData.upi_ref}
// // //                 </span>
// // //               )}
// // //             </div>
// // //           </div>
// // //         )}

// // //         {/* Selection Summary */}
// // //         <div style={{ backgroundColor: '#18181b', border: '1px solid #27272a', padding: '14px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
// // //           <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', fontWeight: 'bold' }}>
// // //             Batch Target Summary
// // //           </span>
// // //           <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
// // //             <span style={{ fontSize: '13px', fontWeight: 'bold', color: selectedSummary.totalTxns > 0 ? '#f59e0b' : '#71717a' }}>
// // //               {selectedSummary.totalTxns} Item{selectedSummary.totalTxns !== 1 ? 's' : ''} Selected
// // //             </span>
// // //             <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f4f4f5' }}>
// // //               {inrFormatter.format(selectedSummary?.totalAmount || 0)}
// // //             </span>
// // //           </div>
// // //         </div>

// // //         {/* Category Dropdowns / On-The-Go Creator */}
// // //         <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
// // //           <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #27272a', paddingBottom: '8px' }}>
// // //             <h3 style={{ margin: 0, fontSize: '11px', fontWeight: 'bold', textTransform: 'uppercase', color: '#a1a1aa' }}>
// // //               Assign Taxonomy Nodes
// // //             </h3>
// // //             <button
// // //               onClick={() => setIsCreatingNew(!isCreatingNew)}
// // //               style={{ background: 'none', border: 'none', color: '#f59e0b', fontSize: '11px', cursor: 'pointer', fontWeight: 'bold' }}
// // //             >
// // //               {isCreatingNew ? '← Back to Select' : '+ Create New Node'}
// // //             </button>
// // //           </div>

// // //           {!isCreatingNew ? (
// // //             <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
// // //               <div>
// // //                 <label style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
// // //                   Primary Category
// // //                 </label>
// // //                 <select
// // //                   value={selectedCategory}
// // //                   onChange={(e) => {
// // //                     const newCat = e.target.value;
// // //                     setSelectedCategory(newCat);
// // //                     const found = taxonomyTree.find((t) => t.category === newCat);
// // //                     if (found && found.subcategories && found.subcategories.length > 0) {
// // //                       setSelectedSubcategory(found.subcategories[0]);
// // //                     }
// // //                   }}
// // //                   style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', color: '#f4f4f5', outline: 'none' }}
// // //                 >
// // //                   {taxonomyTree.map((t, catIdx) => (
// // //                     <option key={`cat-${t.category}-${catIdx}`} value={t.category}>
// // //                       {t.category}
// // //                     </option>
// // //                   ))}
// // //                 </select>
// // //               </div>

// // //               <div>
// // //                 <label style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
// // //                   Subcategory
// // //                 </label>
// // //                 <select
// // //                   value={selectedSubcategory || ''}
// // //                   onChange={(e) => setSelectedSubcategory(e.target.value)}
// // //                   style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', color: '#f4f4f5', outline: 'none' }}
// // //                 >
// // //                   {(availableSubcategories || []).map((sub, subIdx) => (
// // //                     <option key={`sub-${sub}-${subIdx}`} value={sub}>
// // //                       {sub}
// // //                     </option>
// // //                   ))}
// // //                 </select>
// // //               </div>
// // //             </div>
// // //           ) : (
// // //             <div style={{ backgroundColor: '#18181b', border: '1px dashed #f59e0b', padding: '12px', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
// // //               <span style={{ fontSize: '11px', color: '#f59e0b', fontWeight: 'bold' }}>
// // //                 New Taxonomy Entry
// // //               </span>
// // //               <div>
// // //                 <label style={{ fontSize: '10px', color: '#a1a1aa', display: 'block', marginBottom: '2px' }}>
// // //                   Category Name
// // //                 </label>
// // //                 <input
// // //                   type="text"
// // //                   placeholder="e.g. Expense"
// // //                   value={newCatInput}
// // //                   onChange={(e) => setNewCatInput(e.target.value)}
// // //                   style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', fontSize: '12px', color: '#f4f4f5' }}
// // //                 />
// // //               </div>

// // //               <div>
// // //                 <label style={{ fontSize: '10px', color: '#a1a1aa', display: 'block', marginBottom: '2px' }}>
// // //                   Subcategory Name
// // //                 </label>
// // //                 <input
// // //                   type="text"
// // //                   placeholder="e.g. Panchami Devi Temple"
// // //                   value={newSubInput}
// // //                   onChange={(e) => setNewSubInput(e.target.value)}
// // //                   style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', fontSize: '12px', color: '#f4f4f5' }}
// // //                 />
// // //               </div>

// // //               <button
// // //                 onClick={handleCreateTaxonomy}
// // //                 disabled={savingNewTaxonomy || !newCatInput.trim() || !newSubInput.trim()}
// // //                 style={{
// // //                   marginTop: '4px',
// // //                   padding: '8px 12px',
// // //                   borderRadius: '6px',
// // //                   fontSize: '11px',
// // //                   fontWeight: 'bold',
// // //                   backgroundColor: '#f59e0b',
// // //                   color: '#09090b',
// // //                   border: 'none',
// // //                   cursor: savingNewTaxonomy ? 'wait' : 'pointer',
// // //                 }}
// // //               >
// // //                 {savingNewTaxonomy ? 'Saving...' : 'Add & Select Node'}
// // //               </button>
// // //             </div>
// // //           )}
// // //         </div>

// // //         {/* Rule Toggle */}
// // //         <div style={{ backgroundColor: '#09090b', border: '1px solid #27272a', padding: '12px', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
// // //           <div>
// // //             <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f4f4f5', display: 'block' }}>
// // //               Save to Classification Rules
// // //             </span>
// // //             <span style={{ fontSize: '10px', color: '#71717a', display: 'block' }}>
// // //               Auto-classify future imports matching active vendor pattern
// // //             </span>
// // //           </div>
// // //           <input
// // //             type="checkbox"
// // //             checked={saveRule}
// // //             onChange={(e) => setSaveRule(e.target.checked)}
// // //             style={{ width: '16px', height: '16px', accentColor: '#f59e0b', cursor: 'pointer' }}
// // //           />
// // //         </div>

// // //       </div>

// // //       {/* Footer Buttons */}
// // //       <div style={{ borderTop: '1px solid #27272a', paddingTop: '16px', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
// // //         <button
// // //           onClick={onClose}
// // //           style={{ padding: '8px 16px', borderRadius: '8px', fontSize: '12px', color: '#a1a1aa', background: 'none', border: 'none', cursor: 'pointer' }}
// // //         >
// // //           Cancel
// // //         </button>
// // //         <button
// // //           disabled={submitting || selectedSummary.allTxnIds.length === 0}
// // //           onClick={handleApplyClassification}
// // //           style={{
// // //             padding: '10px 20px',
// // //             borderRadius: '8px',
// // //             fontSize: '12px',
// // //             fontWeight: 'bold',
// // //             backgroundColor: '#f59e0b',
// // //             color: '#09090b',
// // //             border: 'none',
// // //             cursor: submitting || selectedSummary.allTxnIds.length === 0 ? 'not-allowed' : 'pointer',
// // //             opacity: submitting || selectedSummary.allTxnIds.length === 0 ? 0.5 : 1,
// // //           }}
// // //         >
// // //           {submitting ? 'Applying...' : `Reclassify ${selectedSummary.totalTxns} Selected Line${selectedSummary.totalTxns !== 1 ? 's' : ''}`}
// // //         </button>
// // //       </div>
// // //     </div>
// // //   );
// // // };