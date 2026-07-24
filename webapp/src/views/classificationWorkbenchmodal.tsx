import React, { useState, useEffect, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { 
  getSuspenseClusters, 
  applyReclassification, 
  type Cluster 
} from '../api';

export interface TaxonomyOption {
  category: string;
  subcategories: string[];
}

export interface ExtendedCluster extends Cluster {
  items?: Array<{
    id: string;
    narration: string;
    amount: number;
  }>;
}

export const TAXONOMY_TREE: TaxonomyOption[] = [
  {
    category: 'Expense',
    subcategories: [
      'Food & Dining',
      'Groceries',
      'Utilities & Bills',
      'Shopping',
      'Fuels',                  
      'Transportation',
      'Entertainment',
      'Healthcare',
      'Loans & EMI',            
      'Housing & Rent',         
      'Repair & Maintenance',
      'Suspense Account',
      'Temple',
      'Donations',
      'Borrowed',
      'Festivals',
      
    ],
  },
  {
    category: 'Income',
    subcategories: [
      'Salary',
      'Investments',
      'Rental Income',          
      'Refunds & Cashbacks',
      'Other Income',
    ],
  },
  {
    category: 'Transfer',
    subcategories: [
      'Inter-Account Transfer',
      'Credit Card Payment',
      'Investment Deposit',
      'Temporary Loans',        
      'Permanent Loans',    
      'Wife',    
    ],
  },
];

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  targetSubcategory?: string;
}

export const ClassificationWorkbenchModal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  targetSubcategory = 'Suspense Account',
}) => {
  const [clusters, setClusters] = useState<ExtendedCluster[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Selected transaction IDs (starts completely EMPTY for safety!)
  const [selectedTxnIds, setSelectedTxnIds] = useState<string[]>([]);
  const [activePreviewCluster, setActivePreviewCluster] = useState<Cluster | null>(null);
  
  const [selectedCategory, setSelectedCategory] = useState<string>('Expense');
  const [selectedSubcategory, setSelectedSubcategory] = useState<string>('Housing & Rent');
  const [saveRule, setSaveRule] = useState<boolean>(true);

  const inrFormatter = useMemo(
    () =>
      new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        maximumFractionDigits: 0,
      }),
    []
  );

  useEffect(() => {
    if (isOpen) {
      fetchClusters(targetSubcategory);
    }
  }, [isOpen, targetSubcategory]);

  const fetchClusters = async (subcategoryName: string = targetSubcategory || 'Suspense Account') => {
    setLoading(true);
    // Reset selection safely on load
    setSelectedTxnIds([]);
    setActivePreviewCluster(null);

    try {
      const data = await getSuspenseClusters(subcategoryName);
      if (data.status === 'success') {
        const list = data.clusters || [];
        setClusters(list);
        if (list.length > 0) {
          setActivePreviewCluster(list[0]);
        }
      }
    } catch (err) {
      console.error('Failed to load clusters:', err);
    } finally {
      setLoading(false);
    }
  };

  const filteredClusters = useMemo(() => {
    if (!searchQuery.trim()) return clusters;
    const query = searchQuery.toLowerCase();
    return clusters.filter(
      (c) =>
        c.pattern.toLowerCase().includes(query) ||
        c.sample_descriptions.some((d) => d.toLowerCase().includes(query))
    );
  }, [clusters, searchQuery]);

  // Extract transaction IDs present in the current search view
  const visibleTxnIds = useMemo(() => {
    return filteredClusters.flatMap((c) => c.transaction_ids || []);
  }, [filteredClusters]);

  // Calculate selected metrics safely based strictly on checked lines
  const selectedSummary = useMemo(() => {
    let totalTxns = 0;
    let totalAmount = 0;

    clusters.forEach((cluster) => {
      if (cluster.items && cluster.items.length > 0) {
        cluster.items.forEach((item: { id: string; amount: number }) => {
          if (selectedTxnIds.includes(item.id)) {
            totalTxns += 1;
            totalAmount += item.amount;
          }
        });
      } else {
        const selectedInCluster = (cluster.transaction_ids || []).filter((id) =>
          selectedTxnIds.includes(id)
        );
        if (selectedInCluster.length > 0) {
          totalTxns += selectedInCluster.length;
          const ratio = selectedInCluster.length / (cluster.count || 1);
          totalAmount += cluster.total_amount * ratio;
        }
      }
    });

    return { totalTxns, totalAmount, allTxnIds: selectedTxnIds };
  }, [clusters, selectedTxnIds]);

  // Single line-item toggle
  const toggleIndividualTxn = (txnId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedTxnIds((prev) =>
      prev.includes(txnId) ? prev.filter((id) => id !== txnId) : [...prev, txnId]
    );
  };

  // Whole cluster toggle
  const toggleClusterTxns = (clusterTxnIds: string[], e: React.MouseEvent) => {
    e.stopPropagation();
    const allInClusterSelected = clusterTxnIds.every((id) => selectedTxnIds.includes(id));

    if (allInClusterSelected) {
      setSelectedTxnIds((prev) => prev.filter((id) => !clusterTxnIds.includes(id)));
    } else {
      setSelectedTxnIds((prev) => Array.from(new Set([...prev, ...clusterTxnIds])));
    }
  };

  // Select/Deselect all visible items in search view
  const toggleSelectAllVisible = () => {
    const allVisibleSelected = visibleTxnIds.length > 0 && visibleTxnIds.every((id) => selectedTxnIds.includes(id));

    if (allVisibleSelected) {
      // Remove visible IDs from selection
      setSelectedTxnIds((prev) => prev.filter((id) => !visibleTxnIds.includes(id)));
    } else {
      // Add all visible IDs to selection
      setSelectedTxnIds((prev) => Array.from(new Set([...prev, ...visibleTxnIds])));
    }
  };

  const clearAllSelections = () => {
    setSelectedTxnIds([]);
  };

  const availableSubcategories = useMemo(() => {
    const found = TAXONOMY_TREE.find((item) => item.category === selectedCategory);
    return found ? found.subcategories : [];
  }, [selectedCategory]);

  const handleApplyClassification = async () => {
    if (selectedSummary.allTxnIds.length === 0) return;

    setSubmitting(true);
    try {
      // Pass the active pattern if reclassifying cluster items
      const patternToSave = activePreviewCluster?.pattern !== 'UNCLASSIFIED_OTHER' 
        ? activePreviewCluster?.pattern 
        : undefined;

      const data = await applyReclassification({
        transaction_ids: selectedSummary.allTxnIds,
        target_category: selectedCategory,
        target_subcategory: selectedSubcategory,
        pattern: patternToSave,
        save_rule: saveRule,
      });

      if (data.status === 'success') {
        await fetchClusters(targetSubcategory);
        onSuccess();
      }
    } catch (err) {
      console.error('Failed to apply reclassification:', err);
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return createPortal(
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        width: '100vw',
        height: '100vh',
        backgroundColor: 'rgba(0, 0, 0, 0.85)',
        backdropFilter: 'blur(8px)',
        zIndex: 999999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
        boxSizing: 'border-box',
        fontFamily: 'monospace',
      }}
    >
      <div
        style={{
          backgroundColor: '#09090b',
          border: '1px solid #27272a',
          borderRadius: '16px',
          width: '100%',
          maxWidth: '1100px',
          height: '80vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.75)',
          overflow: 'hidden',
          color: '#f4f4f5',
        }}
      >
        {/* Header Bar */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '16px 24px',
            borderBottom: '1px solid #27272a',
            backgroundColor: '#18181b',
          }}
        >
          <div>
            <h2 style={{ margin: 0, fontSize: '14px', fontWeight: 'bold', textTransform: 'uppercase', color: '#f4f4f5', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#f59e0b' }} />
              Classification Workbench — {targetSubcategory || 'Suspense Account'}
            </h2>
            <p style={{ margin: '4px 0 0 0', fontSize: '11px', color: '#71717a' }}>
              Reviewing merchant clusters under <strong style={{ color: '#e4e4e7' }}>{targetSubcategory || 'Suspense Account'}</strong>. Check individual line items to assign target taxonomy nodes.
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: '#71717a',
              fontSize: '18px',
              cursor: 'pointer',
              padding: '4px 8px',
              borderRadius: '6px',
            }}
          >
            ✕
          </button>
        </div>

        {/* Split-Pane Workspace Body */}
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          
          {/* LEFT PANEL: Merchant Clusters */}
          <div style={{ width: '58%', borderRight: '1px solid #27272a', display: 'flex', flexDirection: 'column', backgroundColor: '#09090b' }}>
            
            {/* Search & Select Bar */}
            <div style={{ padding: '12px', borderBottom: '1px solid #27272a', display: 'flex', alignItems: 'center', gap: '12px', backgroundColor: '#121215' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#a1a1aa', cursor: 'pointer', fontWeight: 'bold' }}>
                <input
                  type="checkbox"
                  checked={visibleTxnIds.length > 0 && visibleTxnIds.every((id) => selectedTxnIds.includes(id))}
                  onChange={toggleSelectAllVisible}
                  style={{ width: '16px', height: '16px', accentColor: '#f59e0b', cursor: 'pointer' }}
                />
                Visible Lines
              </label>

              {selectedTxnIds.length > 0 && (
                <button
                  onClick={clearAllSelections}
                  style={{
                    backgroundColor: '#27272a',
                    color: '#f4f4f5',
                    border: 'none',
                    borderRadius: '4px',
                    padding: '2px 8px',
                    fontSize: '10px',
                    cursor: 'pointer',
                  }}
                >
                  Uncheck All ({selectedTxnIds.length})
                </button>
              )}

              <input
                type="text"
                placeholder="Search vendor patterns, raw narrations..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  flex: 1,
                  backgroundColor: '#18181b',
                  border: '1px solid #27272a',
                  borderRadius: '8px',
                  padding: '6px 12px',
                  fontSize: '12px',
                  color: '#f4f4f5',
                  outline: 'none',
                }}
              />
            </div>

            {/* Scrollable Cluster List */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {loading ? (
                <div style={{ textAlign: 'center', padding: '60px 0', color: '#71717a', fontSize: '12px' }}>
                  Parsing merchant anchors & building clusters...
                </div>
              ) : filteredClusters.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '60px 0', color: '#71717a', fontSize: '12px' }}>
                  No matching patterns found.
                </div>
              ) : (
                filteredClusters.map((cluster) => {
                  const clusterTxnIds: string[] = cluster.transaction_ids || [];
                  const selectedInClusterCount = clusterTxnIds.filter((id) => selectedTxnIds.includes(id)).length;
                  const isClusterFullySelected = clusterTxnIds.length > 0 && selectedInClusterCount === clusterTxnIds.length;
                  const isClusterPartiallySelected = selectedInClusterCount > 0 && !isClusterFullySelected;
                  const isActive = activePreviewCluster?.pattern === cluster.pattern;

                  return (
                    <div
                      key={cluster.pattern}
                      onClick={() => setActivePreviewCluster(cluster)}
                      style={{
                        padding: '12px',
                        borderRadius: '10px',
                        border: `1px solid ${isActive ? '#f59e0b' : selectedInClusterCount > 0 ? '#3f3f46' : '#27272a'}`,
                        backgroundColor: isActive ? '#18181b' : '#0f0f12',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      {/* Master Cluster Row */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <input
                            type="checkbox"
                            checked={isClusterFullySelected}
                            ref={(el) => { if (el) el.indeterminate = isClusterPartiallySelected; }}
                            onClick={(e) => toggleClusterTxns(clusterTxnIds, e)}
                            onChange={() => {}}
                            style={{ width: '16px', height: '16px', accentColor: '#f59e0b', cursor: 'pointer' }}
                          />
                          <span style={{ fontWeight: 'bold', fontSize: '12px', color: '#f4f4f5' }}>
                            #{cluster.pattern}
                          </span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ padding: '2px 6px', fontSize: '10px', backgroundColor: '#27272a', color: '#d4d4d8', borderRadius: '4px' }}>
                            {selectedInClusterCount} / {cluster.count} selected
                          </span>
                          <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#fb7185' }}>
                            {inrFormatter.format(cluster.total_amount)}
                          </span>
                        </div>
                      </div>

                      {/* Line Items Array */}
                      <div style={{ paddingLeft: '8px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        {cluster.items && cluster.items.length > 0 ? (
                          cluster.items.map((item: { id: string; narration: string; amount: number }) => {
                            const isItemChecked = selectedTxnIds.includes(item.id);

                            return (
                              <label
                                key={item.id}
                                onClick={(e) => e.stopPropagation()}
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '8px',
                                  padding: '4px 6px',
                                  borderRadius: '6px',
                                  backgroundColor: isItemChecked ? '#27272a' : 'transparent',
                                  cursor: 'pointer',
                                  fontSize: '11px',
                                  color: isItemChecked ? '#f4f4f5' : '#71717a',
                                }}
                              >
                                <input
                                  type="checkbox"
                                  checked={isItemChecked}
                                  onClick={(e) => toggleIndividualTxn(item.id, e)}
                                  onChange={() => {}}
                                  style={{ width: '14px', height: '14px', accentColor: '#f59e0b', cursor: 'pointer' }}
                                />
                                <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontFamily: 'monospace' }}>
                                  • {item.narration}
                                </span>
                                <span style={{ fontSize: '10px', fontWeight: 'bold', color: '#a1a1aa' }}>
                                  ₹{item.amount.toLocaleString('en-IN')}
                                </span>
                              </label>
                            );
                          })
                        ) : (
                          cluster.sample_descriptions.map((desc: string, idx: number) => (
                            <div key={idx} style={{ fontSize: '10px', color: '#71717a', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontFamily: 'monospace' }}>
                              • {desc}
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* RIGHT PANEL: Category Mapper & Execution */}
          <div style={{ width: '42%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '24px', backgroundColor: '#0f0f12' }}>
            {selectedSummary.allTxnIds.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                
                {/* Summary Card */}
                <div style={{ backgroundColor: '#18181b', border: '1px solid #27272a', padding: '16px', borderRadius: '12px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <span style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', fontWeight: 'bold' }}>
                    Target Selection Summary
                  </span>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '13px', fontWeight: 'bold', color: '#f59e0b' }}>
                      {selectedSummary.totalTxns} Line Item{selectedSummary.totalTxns > 1 ? 's' : ''} Selected
                    </span>
                    <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#f4f4f5' }}>
                      {inrFormatter.format(selectedSummary.totalAmount)}
                    </span>
                  </div>
                </div>

                {/* Category Dropdowns */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <h3 style={{ margin: 0, fontSize: '11px', fontWeight: 'bold', textTransform: 'uppercase', color: '#a1a1aa', borderBottom: '1px solid #27272a', paddingBottom: '8px' }}>
                    Assign Taxonomy Nodes
                  </h3>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <div>
                      <label style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
                        Primary Category
                      </label>
                      <select
                        value={selectedCategory}
                        onChange={(e) => {
                          setSelectedCategory(e.target.value);
                          const found = TAXONOMY_TREE.find((t) => t.category === e.target.value);
                          if (found && found.subcategories.length > 0) {
                            setSelectedSubcategory(found.subcategories[0]);
                          }
                        }}
                        style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', color: '#f4f4f5', outline: 'none' }}
                      >
                        {TAXONOMY_TREE.map((t) => (
                          <option key={t.category} value={t.category}>
                            {t.category}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label style={{ fontSize: '10px', textTransform: 'uppercase', color: '#71717a', display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
                        Subcategory
                      </label>
                      <select
                        value={selectedSubcategory}
                        onChange={(e) => setSelectedSubcategory(e.target.value)}
                        style={{ width: '100%', backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', color: '#f4f4f5', outline: 'none' }}
                      >
                        {availableSubcategories.map((sub) => (
                          <option key={sub} value={sub}>
                            {sub}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                </div>

                {/* Rule Learning Toggle */}
                <div style={{ backgroundColor: '#09090b', border: '1px solid #27272a', padding: '12px', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
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
            ) : (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#71717a', fontSize: '12px', textAlign: 'center' }}>
                Check individual transaction lines or cluster headers on the left to begin reclassifying.
              </div>
            )}

            {/* Footer Action Buttons */}
            <div style={{ borderTop: '1px solid #27272a', paddingTop: '16px', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
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
                {submitting ? 'Applying...' : `Reclassify ${selectedSummary.totalTxns} Selected Line${selectedSummary.totalTxns > 1 ? 's' : ''}`}
              </button>
            </div>

          </div>

        </div>
      </div>
    </div>,
    document.body
  );
};