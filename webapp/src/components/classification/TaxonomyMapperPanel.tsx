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
{/* Primary Category Select */}
              <div>
                <label style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
                  Primary Category
                </label>
                <select
                  value={selectedCategory || ''}
                  onChange={(e) => {
                    const newCat = e.target.value;
                    setSelectedCategory(newCat);
                    const found = taxonomyTree.find((t) => String(t?.category) === newCat);
                    if (found && Array.isArray(found.subcategories) && found.subcategories.length > 0) {
                      setSelectedSubcategory(String(found.subcategories[0] || ''));
                    }
                  }}
                  style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', color: getCategoryColor(selectedCategory), fontWeight: 'bold', outline: 'none' }}
                >
                  {(taxonomyTree || []).map((t, catIdx) => {
                    const catName = String(t?.category || '');
                    if (!catName) return null;
                    const label = catName === 'Income' ? 'Income (Inflows)' : catName === 'Expense' ? 'Expense (Outflows)' : catName;
                    return (
                      <option key={`cat-${catName}-${catIdx}`} value={catName} style={{ color: '#f4f4f5', backgroundColor: '#18181b' }}>
                        {label}
                      </option>
                    );
                  })}
                </select>
              </div>

{/* Subcategory Select */}
              <div>
                <label style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
                  Subcategory
                </label>
                <select
                  value={typeof selectedSubcategory === 'string' ? selectedSubcategory : ''}
                  onChange={(e) => setSelectedSubcategory(e.target.value)}
                  style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', color: '#f4f4f5', outline: 'none' }}
                >
                  {(availableSubcategories || []).map((sub: any, subIdx: number) => {
                    // Extract plain string if `sub` is an object (e.g. { subcategory: 'Rent Income' })
                    const displayLabel = typeof sub === 'object' && sub !== null 
                      ? (sub.subcategory || sub.name || sub.title || String(sub)) 
                      : String(sub || '');

                    if (!displayLabel) return null;

                    return (
                      <option 
                        key={`sub-opt-${subIdx}-${displayLabel}`} 
                        value={displayLabel} 
                        style={{ color: '#f4f4f5', backgroundColor: '#18181b' }}
                      >
                        {displayLabel}
                      </option>
                    );
                  })}
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
