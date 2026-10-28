// webapp/src/components/Stage3/Workbench/ClusterListPanel.tsx
import React, { useState, useCallback } from 'react';
import type { ExtendedCluster, Cluster } from '../../../api/api';
import { updateEntryUserNote, getClusterLineItems } from '../../../api/api';
import { inrFormatter, parseRemarks, extractCleanPayee } from '../../../utils/classificationHelpers';
import { ClusterCardItem } from './ClusterCardItem';
import { DualNarrationViewer } from './DualNarrationViewer';

interface VendorGroup {
  vendorName: string;
  items: any[];
  txnIds: string[];
  totalAmount: number;
}

interface Props {
  loading: boolean;
  filteredClusters: ExtendedCluster[];
  selectedTxnIds: string[];
  visibleTxnIds: string[];
  activePreviewCluster: ExtendedCluster | Cluster | null;
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  setActivePreviewCluster: (cluster: ExtendedCluster) => void;
  toggleIndividualTxn: (txnId: string, e: React.MouseEvent) => void;
  toggleClusterTxns: (clusterTxnIds: string[], e: React.MouseEvent) => void;
  toggleSelectAllVisible: () => void;
  clearAllSelections: () => void;
}

export const ClusterListPanel: React.FC<Props> = ({
  loading,
  filteredClusters,
  selectedTxnIds,
  visibleTxnIds,
  activePreviewCluster,
  searchQuery,
  setSearchQuery,
  setActivePreviewCluster,
  toggleIndividualTxn,
  toggleClusterTxns,
  toggleSelectAllVisible,
  clearAllSelections,
}) => {
  const [remarksModalItem, setRemarksModalItem] = useState<any | null>(null);
  const [userNoteInput, setUserNoteInput] = useState<string>('');
  const [savingNote, setSavingNote] = useState<boolean>(false);
  const [globalNarrationMode, setGlobalNarrationMode] = useState<'smart' | 'raw'>('smart');

  // Accordion expansion states
  const [expandedClusterKeys, setExpandedClusterKeys] = useState<Record<string, boolean>>({});
  const [expandedVendorKeys, setExpandedVendorKeys] = useState<Record<string, boolean>>({});

  // 🟢 LAZY-LOAD CACHE: Stores items fetched on demand per cluster
  const [clusterItemsCache, setClusterItemsCache] = useState<Record<string, any[]>>({});
  const [loadingClusterKeys, setLoadingClusterKeys] = useState<Record<string, boolean>>({});

  const isClusterExpanded = useCallback(
    (key: string) => !!expandedClusterKeys[key],
    [expandedClusterKeys]
  );

  const isVendorExpanded = useCallback(
    (key: string) => expandedVendorKeys[key] !== false,
    [expandedVendorKeys]
  );

  const handleLoadClusterItems = async (clusterKey: string, cluster: ExtendedCluster, e: React.MouseEvent) => {
  e.stopPropagation();
  if (clusterItemsCache[clusterKey] || loadingClusterKeys[clusterKey]) return;

  const txnIds = cluster.transaction_ids || [];
  if (txnIds.length === 0) return;

  setLoadingClusterKeys((prev) => ({ ...prev, [clusterKey]: true }));
  try {
    const response = await getClusterLineItems(txnIds);
    const fetchedItems = Array.isArray(response) ? response : [];
    setClusterItemsCache((prev) => ({ ...prev, [clusterKey]: fetchedItems }));
  } catch (err) {
    console.error('Failed to load cluster items:', err);
  } finally {
    setLoadingClusterKeys((prev) => ({ ...prev, [clusterKey]: false }));
  }
};

  // 🟢 Global Expand: opens headers without flooding the network
  const handleGlobalExpand = () => {
    const openMap: Record<string, boolean> = {};
    filteredClusters.forEach((c, idx) => {
      const key = c.pattern ? `cluster-${c.pattern}-${idx}` : `cluster-idx-${idx}`;
      openMap[key] = true;
    });
    setExpandedClusterKeys(openMap);
  };

  // 🟢 Global Collapse: collapses all clusters instantly
  const handleGlobalCollapse = () => {
    setExpandedClusterKeys({});
  };

  // Lazy fetch items on accordion expansion
  const toggleExpandCluster = async (clusterKey: string, cluster: ExtendedCluster, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    const willExpand = !isClusterExpanded(clusterKey);

    setExpandedClusterKeys((prev) => ({ ...prev, [clusterKey]: willExpand }));

    // If opening and items are not cached yet, fetch from backend:
    if (willExpand && !clusterItemsCache[clusterKey] && (!cluster.items || cluster.items.length === 0)) {
      const txnIds = cluster.transaction_ids || [];
      if (txnIds.length === 0) return;

      setLoadingClusterKeys((prev) => ({ ...prev, [clusterKey]: true }));
      try {
        const response = await getClusterLineItems(txnIds);
        const fetchedItems = Array.isArray(response) ? response : [];
        setClusterItemsCache((prev) => ({ ...prev, [clusterKey]: fetchedItems }));
      } catch (err) {
        console.error('Failed to lazy load cluster items:', err);
      } finally {
        setLoadingClusterKeys((prev) => ({ ...prev, [clusterKey]: false }));
      }
    }
  };

  const toggleExpandVendor = (key: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedVendorKeys((prev) => ({ ...prev, [key]: !isVendorExpanded(key) }));
  };

  const handleOpenInspectionModal = (item: any) => {
    setRemarksModalItem(item);
    const parsed = parseRemarks(item.remarks);
    setUserNoteInput(parsed.user_note || '');
  };

  const handleSaveUserNote = async () => {
    if (!remarksModalItem) return;
    setSavingNote(true);

    try {
      const data = await updateEntryUserNote({
        entry_id: remarksModalItem.id,
        user_note: userNoteInput,
      });

      if (data && data.status === 'success') {
        remarksModalItem.remarks = data.remarks;
        setRemarksModalItem(null);
      } else {
        alert('Failed to save user note.');
      }
    } catch (err) {
      console.error('Save note error:', err);
    } finally {
      setSavingNote(false);
    }
  };

  const groupItemsByVendor = (items: any[] = []): VendorGroup[] => {
    const groupsMap: Record<string, VendorGroup> = {};

    items.forEach((item) => {
      const remarksObj = parseRemarks(item.remarks);
      const name = item.display_payee || extractCleanPayee(item.narration) || remarksObj.payee || 'Unlabeled Vendor';

      const dirStr = (item.direction || item.vector_type || item.entry_type || '').toUpperCase();
      const isOut = dirStr === 'OUTFLOW' || dirStr === 'DEBIT' || dirStr === 'DR'
        ? true
        : dirStr === 'INFLOW' || dirStr === 'CREDIT' || dirStr === 'CR'
        ? false
        : item.debit != null && Number(item.debit) > 0
        ? true
        : item.credit != null && Number(item.credit) > 0
        ? false
        : (item.amount ?? 0) < 0;

      const directionTag = isOut ? 'OUT' : 'IN';
      const groupKey = `${name}__${directionTag}`;

      if (!groupsMap[groupKey]) {
        groupsMap[groupKey] = {
          vendorName: `${name} (${directionTag})`,
          items: [],
          txnIds: [],
          totalAmount: 0,
        };
      }

      groupsMap[groupKey].items.push(item);
      if (item.id) groupsMap[groupKey].txnIds.push(item.id);
      groupsMap[groupKey].totalAmount += item.amount || item.debit || item.credit || 0;
    });

    return Object.values(groupsMap).sort((a, b) => {
      if (b.items.length !== a.items.length) return b.items.length - a.items.length;
      return Math.abs(b.totalAmount) - Math.abs(a.totalAmount);
    });
  };

  return (
    <div style={{ width: '58%', borderRight: '1px solid #27272a', display: 'flex', flexDirection: 'column', backgroundColor: '#09090b' }}>
      
      {/* Top Controls Toolbar */}
      <div style={{ padding: '12px', borderBottom: '1px solid #27272a', display: 'flex', alignItems: 'center', gap: '8px', backgroundColor: '#121215' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: '#a1a1aa', cursor: 'pointer', fontWeight: 'bold' }}>
          <input
            type="checkbox"
            checked={visibleTxnIds.length > 0 && visibleTxnIds.every((id) => selectedTxnIds.includes(id))}
            onChange={toggleSelectAllVisible}
            style={{ width: '15px', height: '15px', accentColor: '#f59e0b', cursor: 'pointer' }}
          />
          Visible
        </label>

        {selectedTxnIds.length > 0 && (
          <button
            type="button"
            onClick={clearAllSelections}
            style={{ backgroundColor: '#27272a', color: '#f4f4f5', border: 'none', borderRadius: '4px', padding: '3px 8px', fontSize: '10px', cursor: 'pointer' }}
          >
            Clear ({selectedTxnIds.length})
          </button>
        )}

        <input
          type="text"
          placeholder="Search vendor patterns, narrations..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{ flex: 1, backgroundColor: '#18181b', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', fontSize: '11px', color: '#f4f4f5', outline: 'none' }}
        />

        {/* Global Narration View Switcher */}
        <div style={{ display: 'flex', backgroundColor: '#18181b', borderRadius: '6px', border: '1px solid #27272a', padding: '2px' }}>
          <button
            type="button"
            onClick={() => setGlobalNarrationMode('smart')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: '4px',
              fontSize: '10px',
              fontWeight: 'bold',
              border: 'none',
              cursor: 'pointer',
              backgroundColor: globalNarrationMode === 'smart' ? '#f59e0b22' : 'transparent',
              color: globalNarrationMode === 'smart' ? '#fbbf24' : '#71717a',
            }}
          >
            ✨ Smart
          </button>
          <button
            type="button"
            onClick={() => setGlobalNarrationMode('raw')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: '4px',
              fontSize: '10px',
              fontWeight: 'bold',
              border: 'none',
              cursor: 'pointer',
              backgroundColor: globalNarrationMode === 'raw' ? '#0284c722' : 'transparent',
              color: globalNarrationMode === 'raw' ? '#38bdf8' : '#71717a',
            }}
          >
            🏦 Raw Bank
          </button>
        </div>

        {/* 🟢 Functional Expand / Collapse Actions */}
        <div style={{ display: 'flex', gap: '4px' }}>
          <button
            type="button"
            onClick={handleGlobalExpand}
            title="Expand all clusters"
            style={{ backgroundColor: '#18181b', border: '1px solid #27272a', color: '#a1a1aa', padding: '3px 6px', borderRadius: '4px', fontSize: '10px', cursor: 'pointer' }}
          >
            ▼ Expand
          </button>
          <button
            type="button"
            onClick={handleGlobalCollapse}
            title="Collapse all clusters"
            style={{ backgroundColor: '#18181b', border: '1px solid #27272a', color: '#a1a1aa', padding: '3px 6px', borderRadius: '4px', fontSize: '10px', cursor: 'pointer' }}
          >
            ▶ Collapse
          </button>
        </div>
      </div>

      {/* Cluster List Container */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px 0', color: '#71717a', fontSize: '12px' }}>
            Building clusters...
          </div>
        ) : filteredClusters.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px 0', color: '#71717a', fontSize: '12px' }}>
            No matching patterns found.
          </div>
        ) : (
          filteredClusters.map((cluster, clusterIdx) => {
            const clusterTxnIds: string[] = cluster.transaction_ids || [];
            const selectedInClusterCount = clusterTxnIds.filter((id) => selectedTxnIds.includes(id)).length;
            const isClusterFullySelected = clusterTxnIds.length > 0 && selectedInClusterCount === clusterTxnIds.length;
            const isClusterPartiallySelected = selectedInClusterCount > 0 && !isClusterFullySelected;
            const isActive = activePreviewCluster?.pattern === cluster.pattern;
            const clusterKey = cluster.pattern ? `cluster-${cluster.pattern}-${clusterIdx}` : `cluster-idx-${clusterIdx}`;

            const expanded = isClusterExpanded(clusterKey);
            const isFetchingItems = !!loadingClusterKeys[clusterKey];

            // 🟢 PREFER CACHED ITEMS, THEN CLUSTER.ITEMS
            const itemsPool = clusterItemsCache[clusterKey] || cluster.items || [];
            const vendorGroups = groupItemsByVendor(itemsPool);

            const clusterOutflow = cluster.total_outflow ?? cluster.total_amount ?? 0;
            const clusterInflow = cluster.total_inflow ?? 0;
            const displayTag = (cluster.pattern || 'GENERAL_SUSPENSE').replace(/^#+/, '');

            return (
              <div
                key={clusterKey}
                onClick={() => setActivePreviewCluster(cluster)}
                style={{
                  padding: '10px 12px',
                  borderRadius: '8px',
                  border: `1px solid ${isActive ? '#f59e0b' : selectedInClusterCount > 0 ? '#3f3f46' : '#27272a'}`,
                  backgroundColor: isActive ? '#18181b' : '#0f0f12',
                  cursor: 'pointer',
                }}
              >
                {/* Cluster Tag Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <input
                      type="checkbox"
                      checked={isClusterFullySelected}
                      ref={(el) => { if (el) el.indeterminate = isClusterPartiallySelected; }}
                      onClick={(e) => {
                        setActivePreviewCluster(cluster);
                        toggleClusterTxns(clusterTxnIds, e);
                      }}
                      onChange={() => {}}
                      style={{ width: '15px', height: '15px', accentColor: '#f59e0b', cursor: 'pointer' }}
                    />
                    <button
                      type="button"
                      onClick={(e) => toggleExpandCluster(clusterKey, cluster, e)}
                      style={{ background: 'none', border: 'none', color: '#71717a', fontSize: '10px', cursor: 'pointer', padding: '2px 4px' }}
                    >
                      {expanded ? '▼' : '▶'}
                    </button>
                    <span style={{ fontWeight: 'bold', fontSize: '12px', color: '#f4f4f5', fontFamily: 'monospace' }}>
                      #{displayTag}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ padding: '2px 6px', fontSize: '10px', backgroundColor: '#27272a', color: '#d4d4d8', borderRadius: '4px' }}>
                      {selectedInClusterCount} / {cluster.count || clusterTxnIds.length || 0}
                    </span>
                    {clusterOutflow > 0 && (
                      <span style={{ fontSize: '11px', fontWeight: 'bold', color: '#fb7185', backgroundColor: '#88133722', padding: '2px 6px', borderRadius: '4px', border: '1px solid #f43f5e33' }}>
                        🔻 {inrFormatter.format(clusterOutflow)}
                      </span>
                    )}
                    {clusterInflow > 0 && (
                      <span style={{ fontSize: '11px', fontWeight: 'bold', color: '#34d399', backgroundColor: '#064e3b22', padding: '2px 6px', borderRadius: '4px', border: '1px solid #10b98133' }}>
                        🟢 {inrFormatter.format(clusterInflow)}
                      </span>
                    )}
                  </div>
                </div>

                {/* Sub-group Accordion Body */}
                {expanded && (
                  <div style={{ paddingLeft: '20px', paddingTop: '8px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {isFetchingItems ? (
                      <div style={{ fontSize: '11px', color: '#a1a1aa', padding: '6px 0', fontStyle: 'italic' }}>
                        Loading line items...
                      </div>
                    ) : itemsPool.length === 0 ? (
                      <div style={{ padding: '6px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '10px', color: '#71717a' }}>
                          {cluster.count || clusterTxnIds.length} transactions available.
                        </span>
                        {/* <button
                          type="button"
                          onClick={(e) => toggleExpandCluster(clusterKey, cluster, e)}
                          style={{
                            backgroundColor: '#27272a',
                            border: '1px solid #3f3f46',
                            color: '#f59e0b',
                            borderRadius: '4px',
                            padding: '2px 8px',
                            fontSize: '10px',
                            cursor: 'pointer',
                            fontWeight: 'bold',
                          }}
                        >
                          Load Items
                        </button> */}
                        <button
  type="button"
  onClick={(e) => handleLoadClusterItems(clusterKey, cluster, e)}
  style={{
    backgroundColor: '#27272a',
    border: '1px solid #3f3f46',
    color: '#f59e0b',
    borderRadius: '4px',
    padding: '2px 8px',
    fontSize: '10px',
    cursor: 'pointer',
    fontWeight: 'bold',
  }}
>
  Load Items
</button>
                      </div>
                    ) : vendorGroups.length > 0 ? (
                      vendorGroups.map((vGroup, vIdx) => {
                        const vendorKey = `${clusterKey}-vendor-${vGroup.vendorName}-${vIdx}`;
                        const selectedInVendorCount = vGroup.txnIds.filter((id) => selectedTxnIds.includes(id)).length;
                        const isVendorFullySelected = vGroup.txnIds.length > 0 && selectedInVendorCount === vGroup.txnIds.length;
                        const isVendorPartiallySelected = selectedInVendorCount > 0 && !isVendorFullySelected;
                        const isVendorOpen = isVendorExpanded(vendorKey);
                        const isGroupOutflow = vGroup.vendorName.endsWith('(OUT)');

                        return (
                          <div
                            key={vendorKey}
                            style={{ backgroundColor: '#141417', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', display: 'flex', flexDirection: 'column', gap: '4px' }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <input
                                  type="checkbox"
                                  checked={isVendorFullySelected}
                                  ref={(el) => { if (el) el.indeterminate = isVendorPartiallySelected; }}
                                  onClick={(e) => {
                                    setActivePreviewCluster(cluster);
                                    toggleClusterTxns(vGroup.txnIds, e);
                                  }}
                                  onChange={() => {}}
                                  style={{ width: '14px', height: '14px', accentColor: '#f59e0b', cursor: 'pointer' }}
                                />
                                <button
                                  type="button"
                                  onClick={(e) => toggleExpandVendor(vendorKey, e)}
                                  style={{ background: 'none', border: 'none', color: '#71717a', fontSize: '9px', cursor: 'pointer', padding: '1px 3px' }}
                                >
                                  {isVendorOpen ? '▼' : '▶'}
                                </button>
                                <span style={{ fontSize: '11px', fontWeight: 'bold', color: '#f4f4f5' }}>
                                  {vGroup.vendorName}
                                </span>
                              </div>

                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span style={{ fontSize: '10px', color: '#a1a1aa', backgroundColor: '#27272a', padding: '1px 6px', borderRadius: '4px', fontWeight: 'bold' }}>
                                  {vGroup.items.length} {vGroup.items.length === 1 ? 'item' : 'items'}
                                </span>
                                <span style={{ fontSize: '11px', fontWeight: 'bold', color: isGroupOutflow ? '#fb7185' : '#34d399', fontFamily: 'monospace' }}>
                                  {isGroupOutflow ? '-' : '+'}₹{Math.abs(vGroup.totalAmount).toLocaleString('en-IN')}
                                </span>
                              </div>
                            </div>

                            {/* Line Items Container using ClusterCardItem */}
                            {isVendorOpen && (
                              <div style={{ paddingLeft: '22px', paddingTop: '4px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                {vGroup.items.map((item, itemIdx) => (
                                  <ClusterCardItem
                                    key={item.id ? `card-${item.id}` : `card-idx-${clusterIdx}-${vIdx}-${itemIdx}`}
                                    item={item}
                                    clusterIdx={clusterIdx}
                                    vIdx={vIdx}
                                    itemIdx={itemIdx}
                                    isSelected={selectedTxnIds.includes(item.id)}
                                    globalNarrationMode={globalNarrationMode}
                                    onToggleSelect={(id, e) => {
                                      setActivePreviewCluster(cluster);
                                      toggleIndividualTxn(id, e);
                                    }}
                                    onOpenRemarksModal={(clickedItem) => {
                                      setActivePreviewCluster(cluster);
                                      handleOpenInspectionModal(clickedItem);
                                    }}
                                  />
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })
                    ) : (
                      (cluster.sample_descriptions || []).map((desc: string, descIdx: number) => (
                        <div
                          key={`desc-${clusterIdx}-${descIdx}`}
                          style={{ fontSize: '10px', color: '#71717a', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontFamily: 'monospace' }}
                        >
                          • {desc}
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Modal with DualNarrationViewer */}
      {remarksModalItem && (
        <div
          onClick={() => setRemarksModalItem(null)}
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.8)',
            backdropFilter: 'blur(4px)',
            zIndex: 9999999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '16px',
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              backgroundColor: '#18181b',
              border: '1px solid #3f3f46',
              borderRadius: '12px',
              padding: '20px',
              maxWidth: '540px',
              width: '100%',
              color: '#f4f4f5',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <h3 style={{ margin: 0, fontSize: '13px', fontWeight: 'bold', color: '#f59e0b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Line Item Audit & Dual Narration
              </h3>
              <button
                type="button"
                onClick={() => setRemarksModalItem(null)}
                style={{ background: 'none', border: 'none', color: '#a1a1aa', cursor: 'pointer', fontSize: '16px' }}
              >
                ✕
              </button>
            </div>

            <DualNarrationViewer item={remarksModalItem} />

            <div style={{ marginBottom: '16px' }}>
              <label style={{ fontSize: '10px', color: '#f59e0b', textTransform: 'uppercase', fontWeight: 'bold', display: 'block', marginBottom: '4px' }}>
                User Comment / Note
              </label>
              <input
                type="text"
                placeholder="e.g., Personal payment for tea at Technopark..."
                value={userNoteInput}
                onChange={(e) => setUserNoteInput(e.target.value)}
                style={{
                  width: '100%',
                  backgroundColor: '#09090b',
                  border: '1px solid #3f3f46',
                  borderRadius: '6px',
                  padding: '8px 12px',
                  fontSize: '12px',
                  color: '#f4f4f5',
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                type="button"
                onClick={() => setRemarksModalItem(null)}
                style={{ flex: 1, padding: '8px', backgroundColor: '#27272a', border: 'none', borderRadius: '6px', color: '#a1a1aa', fontSize: '12px', cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveUserNote}
                disabled={savingNote}
                style={{ flex: 1, padding: '8px', backgroundColor: '#f59e0b', border: 'none', borderRadius: '6px', color: '#09090b', fontSize: '12px', fontWeight: 'bold', cursor: savingNote ? 'wait' : 'pointer' }}
              >
                {savingNote ? 'Saving...' : 'Save Comment'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};


// import React, { useState, useCallback, useEffect } from 'react';
// import type { ExtendedCluster, Cluster } from '../../../api/api';
// import { updateEntryUserNote, getClusterLineItems } from '../../../api/api';
// import { subledgerApi, type UnmapTransactionRequest } from '../../../api/subledger';
// import {
//   inrFormatter,
//   parseRemarks,
//   extractCleanPayee,
//   extractUpiRemark,
//   formatShortDate,
// } from '../../../utils/classificationHelpers';
// import { Search, ChevronDown, ChevronRight, X, AlertCircle } from 'lucide-react';

// interface VendorGroup {
//   vendorName: string;
//   items: any[];
//   txnIds: string[];
//   totalAmount: number;
// }

// interface Props {
//   loading: boolean;
//   filteredClusters: ExtendedCluster[];
//   selectedTxnIds: string[];
//   visibleTxnIds: string[];
//   activePreviewCluster: ExtendedCluster | Cluster | null;
//   searchQuery: string;
//   setSearchQuery: (q: string) => void;
//   setActivePreviewCluster: (cluster: ExtendedCluster) => void;
//   toggleIndividualTxn: (txnId: string, e: React.MouseEvent) => void;
//   toggleClusterTxns: (clusterTxnIds: string[], e: React.MouseEvent) => void;
//   toggleSelectAllVisible: () => void;
//   clearAllSelections: () => void;
//   // 🚀 New Props to synchronize mapping updates in-place without modal reload
//   lastAppliedMapping?: {
//     txnIds: string[];
//     asset_id?: string | number;
//     asset_code?: string;
//     asset_name?: string;
//   } | null;
//   onUnmapSuccess?: (unmappedId: string) => void;
// }

// export const ClusterListPanel: React.FC<Props> = ({
//   loading,
//   filteredClusters,
//   selectedTxnIds,
//   visibleTxnIds,
//   activePreviewCluster,
//   searchQuery,
//   setSearchQuery,
//   setActivePreviewCluster,
//   toggleIndividualTxn,
//   toggleClusterTxns,
//   toggleSelectAllVisible,
//   clearAllSelections,
//   lastAppliedMapping,
//   onUnmapSuccess,
// }) => {
//   const [remarksModalItem, setRemarksModalItem] = useState<{ id: string; narration?: string; remarks?: any } | null>(null);
//   const [userNoteInput, setUserNoteInput] = useState<string>('');
//   const [savingNote, setSavingNote] = useState<boolean>(false);

//   // Map to store dynamically fetched items per cluster
//   const [clusterItemsMap, setClusterItemsMap] = useState<Record<string, any[]>>({});
//   const [loadingClusterKeys, setLoadingClusterKeys] = useState<Record<string, boolean>>({});
//   const [unmappingItemIds, setUnmappingItemIds] = useState<Record<string, boolean>>({});

//   const [expandedClusterKeys, setExpandedClusterKeys] = useState<Record<string, boolean>>({});
//   const [expandedVendorKeys, setExpandedVendorKeys] = useState<Record<string, boolean>>({});

//   // 🔄 Instantly reflect newly mapped items across all active clusters in state
//   useEffect(() => {
//     if (!lastAppliedMapping || !lastAppliedMapping.txnIds?.length) return;

//     const { txnIds, asset_id, asset_code, asset_name } = lastAppliedMapping;

//     setClusterItemsMap((prev) => {
//       const updated = { ...prev };
//       let changed = false;

//       Object.keys(updated).forEach((key) => {
//         const list = updated[key];
//         if (Array.isArray(list) && list.some((it) => txnIds.includes(it.id))) {
//           changed = true;
//           updated[key] = list.map((it) => {
//             if (txnIds.includes(it.id)) {
//               return {
//                 ...it,
//                 is_mapped: true,
//                 asset_id: asset_id ? String(asset_id) : it.asset_id,
//                 asset_code: asset_code || it.asset_code || 'FLT',
//                 asset_name: asset_name || it.asset_name || 'Petty Cash Float',
//               };
//             }
//             return it;
//           });
//         }
//       });

//       return changed ? updated : prev;
//     });
//   }, [lastAppliedMapping]);

//   const isClusterExpanded = useCallback(
//     (clusterKey: string) => expandedClusterKeys[clusterKey] === true,
//     [expandedClusterKeys]
//   );

//   const isVendorExpanded = useCallback(
//     (vendorKey: string) => expandedVendorKeys[vendorKey] !== false,
//     [expandedVendorKeys]
//   );

//   const toggleExpandCluster = async (cluster: ExtendedCluster, clusterKey: string, e: React.MouseEvent) => {
//     e.stopPropagation();
//     const willBeOpen = !isClusterExpanded(clusterKey);

//     setExpandedClusterKeys((prev) => ({
//       ...prev,
//       [clusterKey]: willBeOpen,
//     }));

//     if (willBeOpen && !clusterItemsMap[clusterKey] && cluster.transaction_ids?.length) {
//       setLoadingClusterKeys((prev) => ({ ...prev, [clusterKey]: true }));
//       try {
//         const fetched = await getClusterLineItems(cluster.transaction_ids);
//         setClusterItemsMap((prev) => ({
//           ...prev,
//           [clusterKey]: Array.isArray(fetched) ? fetched : [],
//         }));
//       } catch (err) {
//         console.error('Failed to lazy load cluster items:', err);
//       } finally {
//         setLoadingClusterKeys((prev) => ({ ...prev, [clusterKey]: false }));
//       }
//     }
//   };

//   const toggleExpandVendor = (vendorKey: string, e: React.MouseEvent) => {
//     e.stopPropagation();
//     setExpandedVendorKeys((prev) => ({
//       ...prev,
//       [vendorKey]: !isVendorExpanded(vendorKey),
//     }));
//   };

//   const expandAllClusters = () => {
//     const expandedMap: Record<string, boolean> = {};
//     filteredClusters.forEach((c, idx) => {
//       const key = c.pattern ? `cluster-${c.pattern}-${idx}` : `cluster-idx-${idx}`;
//       expandedMap[key] = true;
//     });
//     setExpandedClusterKeys(expandedMap);
//   };

//   const collapseAllClusters = () => setExpandedClusterKeys({});

//   const handleOpenInspectionModal = (item: any) => {
//     setRemarksModalItem(item);
//     const parsed = parseRemarks(item.remarks);
//     setUserNoteInput(parsed.user_note || '');
//   };

//   const handleSaveUserNote = async () => {
//     if (!remarksModalItem) return;
//     setSavingNote(true);

//     try {
//       const data = await updateEntryUserNote({
//         entry_id: remarksModalItem.id,
//         user_note: userNoteInput,
//       });

//       if (data && data.status === 'success') {
//         remarksModalItem.remarks = data.remarks;
//         setRemarksModalItem(null);
//       } else {
//         alert('Failed to save user note.');
//       }
//     } catch (err) {
//       console.error('Save note error:', err);
//     } finally {
//       setSavingNote(false);
//     }
//   };

//   const handleUnmapSubledger = async (e: React.MouseEvent, item: any, clusterKey: string) => {
//     e.stopPropagation();
//     const itemId = String(item.id);
//     if (!item.mapping_id && !item.row_identifier) return;

//     setUnmappingItemIds((prev) => ({ ...prev, [itemId]: true }));

//     try {
//       const payload: UnmapTransactionRequest = item.mapping_id
//         ? { mapping_id: item.mapping_id }
//         : { row_identifier: item.row_identifier, asset_id: item.asset_id };

//       const res = await subledgerApi.unmapTransaction(payload);
//       if (res?.status === 'success') {
//         // Optimistically mutate item in local cluster cache
//         setClusterItemsMap((prev) => {
//           const list = prev[clusterKey];
//           if (!list) return prev;
//           return {
//             ...prev,
//             [clusterKey]: list.map((it) =>
//               String(it.id) === itemId
//                 ? {
//                     ...it,
//                     is_mapped: false,
//                     mapping_id: null,
//                     asset_id: null,
//                     asset_code: null,
//                     asset_name: null,
//                   }
//                 : it
//             ),
//           };
//         });

//         if (onUnmapSuccess) {
//           onUnmapSuccess(itemId);
//         }
//       } else {
//         alert(res?.message || 'Failed to unmap item.');
//       }
//     } catch (err) {
//       console.error('Failed to unmap transaction from subledger:', err);
//       alert('Error unmapping transaction.');
//     } finally {
//       setUnmappingItemIds((prev) => ({ ...prev, [itemId]: false }));
//     }
//   };

//   const groupItemsByVendor = (items: any[] = []): VendorGroup[] => {
//     const groupsMap: Record<string, VendorGroup> = {};

//     items.forEach((item) => {
//       const remarksObj = parseRemarks(item.remarks);
//       const rawPayee = extractCleanPayee(item.narration) || remarksObj.payee;
//       const cleanPayee = rawPayee && rawPayee.trim().length <= 40 ? rawPayee.trim() : '';

//       const dirStr = (item.direction || item.vector_type || item.entry_type || '').toUpperCase();
//       const isOut =
//         dirStr === 'OUTFLOW' || dirStr === 'DEBIT' || dirStr === 'DR'
//           ? true
//           : dirStr === 'INFLOW' || dirStr === 'CREDIT' || dirStr === 'CR'
//           ? false
//           : item.debit != null && Number(item.debit) > 0
//           ? true
//           : item.credit != null && Number(item.credit) > 0
//           ? false
//           : (item.narration || '').toUpperCase().startsWith('DEP TFR NEFT')
//           ? false
//           : (item.amount ?? 0) < 0;

//       const directionTag = isOut ? 'OUT' : 'IN';
//       const displayName = cleanPayee || 'Transactions';
//       const groupKey = `${displayName}__${directionTag}`;

//       if (!groupsMap[groupKey]) {
//         groupsMap[groupKey] = {
//           vendorName: `${displayName} (${directionTag})`,
//           items: [],
//           txnIds: [],
//           totalAmount: 0,
//         };
//       }

//       groupsMap[groupKey].items.push(item);
//       if (item.id) groupsMap[groupKey].txnIds.push(item.id);
//       groupsMap[groupKey].totalAmount += item.amount || item.debit || item.credit || 0;
//     });

//     return Object.values(groupsMap).sort((a, b) => {
//       if (b.items.length !== a.items.length) {
//         return b.items.length - a.items.length;
//       }
//       return Math.abs(b.totalAmount) - Math.abs(a.totalAmount);
//     });
//   };

//   // Helper to render an individual transaction card
//   const renderTransactionCard = (
//     item: any,
//     cluster: ExtendedCluster,
//     clusterIdx: number,
//     vIdx: number,
//     itemIdx: number,
//     clusterKey: string
//   ) => {
//     const isItemChecked = selectedTxnIds.includes(item.id);
//     const isUnmapping = !!unmappingItemIds[String(item.id)];

//     const isOutflow = (() => {
//       const dirStr = (item.direction || item.vector_type || item.entry_type || '').toUpperCase();
//       if (dirStr === 'OUTFLOW' || dirStr === 'DEBIT' || dirStr === 'DR') return true;
//       if (dirStr === 'INFLOW' || dirStr === 'CREDIT' || dirStr === 'CR') return false;
//       if (item.debit != null && Number(item.debit) > 0) return true;
//       if (item.credit != null && Number(item.credit) > 0) return false;
//       const narration = (item.narration || '').toUpperCase();
//       if (narration.startsWith('DEP TFR NEFT') || narration.includes('CREDIT') || narration.includes('INFLOW')) return false;
//       return (item.amount ?? 0) < 0;
//     })();

//     const itemKey = item.id ? `item-${item.id}` : `item-idx-${clusterIdx}-${vIdx}-${itemIdx}`;
//     const remarksObj = parseRemarks(item.remarks);
//     const userRemark = extractUpiRemark(item.narration);

//     const bankName =
//       item.bank_name ||
//       item.remarks?.bank_name ||
//       (remarksObj as Record<string, any>)?.bank_name;

//     const bankLast4 =
//       item.bank_last4 ||
//       item.remarks?.bank_last4 ||
//       (remarksObj as Record<string, any>)?.bank_last4;

//     const displayAccountId =
//       item.account_id && item.account_id !== 99 ? item.account_id : null;

//     const rawVal = item.amount ?? item.debit ?? item.credit ?? 0;
//     const num = Math.abs(Number(rawVal) || 0);

//     return (
//       <div
//         key={itemKey}
//         onClick={(e) => e.stopPropagation()}
//         className={`p-2 rounded-lg flex flex-col gap-1.5 border-l-2 text-[10px] w-full transition-colors ${
//           isItemChecked ? 'bg-zinc-800/90' : 'bg-zinc-950/80 hover:bg-zinc-900/60'
//         } ${isOutflow ? 'border-rose-500' : 'border-emerald-500'}`}
//       >
//         {/* ROW 1: Controls, Date, Bank Badge, Vector Tag, Mapped Status, and Right-Aligned Amount */}
//         <div className="w-full flex items-center justify-between gap-2">
//           <div className="flex items-center gap-1.5 min-w-0 flex-1 flex-wrap">
//             <input
//               type="checkbox"
//               checked={isItemChecked}
//               onClick={(e) => {
//                 setActivePreviewCluster(cluster);
//                 toggleIndividualTxn(item.id, e);
//               }}
//               onChange={() => {}}
//               className="w-3.5 h-3.5 accent-amber-500 cursor-pointer rounded shrink-0"
//             />

//             {/* 📅 Date */}
//             {item.transaction_date && (
//               <span className="text-[10px] font-mono text-zinc-400 font-semibold shrink-0">
//                 {formatShortDate(item.transaction_date)}
//               </span>
//             )}

//             {/* 🏦 Originating Bank Account Badge */}
//             {bankName ? (
//               <span className="inline-flex items-center gap-1 rounded bg-sky-950/80 border border-sky-700/60 px-1.5 py-0.2 text-[9px] font-mono text-sky-300 font-bold shrink-0 shadow-xs">
//                 <span>🏦</span>
//                 <span>{bankName}</span>
//                 {bankLast4 && (
//                   <span className="text-sky-400/80 font-normal">••{bankLast4}</span>
//                 )}
//               </span>
//             ) : displayAccountId ? (
//               <span className="inline-flex items-center rounded bg-zinc-800 border border-zinc-700 px-1.5 py-0.2 text-[9px] font-mono text-zinc-300 shrink-0">
//                 Acc #{displayAccountId}
//               </span>
//             ) : null}

//             {/* Vector Tag */}
//             <span
//               className={`text-[8px] font-bold px-1.5 py-0.2 rounded uppercase border shrink-0 ${
//                 isOutflow
//                   ? 'bg-rose-950/60 text-rose-300 border-rose-800/40'
//                   : 'bg-emerald-950/60 text-emerald-300 border-emerald-800/40'
//               }`}
//             >
//               {isOutflow ? 'OUT' : 'IN'}
//             </span>

//             {/* 🏷️ MAPPED STATUS INDICATOR & QUICK UNMAP BUTTON */}
//             {item.is_mapped && (
//               <span className="inline-flex items-center gap-1 rounded bg-emerald-950/90 border border-emerald-500/50 px-1.5 py-0.2 text-[9px] font-mono text-emerald-300 font-bold shrink-0 shadow-xs">
//                 <span>Mapped: {item.asset_code || 'Float'}</span>
//                 <button
//                   type="button"
//                   disabled={isUnmapping}
//                   onClick={(e) => handleUnmapSubledger(e, item, clusterKey)}
//                   className="text-zinc-400 hover:text-rose-400 underline decoration-dotted transition-colors text-[9px] cursor-pointer disabled:opacity-40"
//                   title="Unmap this transaction from the cash float"
//                 >
//                   {isUnmapping ? '...' : '(Unmap)'}
//                 </button>
//               </span>
//             )}
//           </div>

//           {/* 💰 Transaction Amount (pinned to the right) */}
//           <span
//             className={`font-mono text-xs font-bold tabular-nums shrink-0 ml-auto ${
//               isOutflow ? 'text-rose-400' : 'text-emerald-400'
//             }`}
//           >
//             {isOutflow ? '-' : '+'}₹{num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
//           </span>
//         </div>

//         {/* ROW 2: Wide Narration String */}
//         <div className="pl-5 text-zinc-300 font-mono text-[10px] leading-relaxed wrap-break-words">
//           {item.narration || 'Unlabeled Bank Line'}
//         </div>

//         {/* ROW 3: Secondary Badges & Actions */}
//         <div className="flex items-center gap-2 pl-5 pt-0.5 text-[9px]">
//           {remarksObj.upi_ref && (
//             <span className="bg-zinc-900 text-zinc-400 px-1.5 py-0.5 rounded border border-zinc-800 font-mono">
//               Ref: {remarksObj.upi_ref}
//             </span>
//           )}

//           {userRemark && (
//             <span className="bg-emerald-950 text-emerald-300 border border-emerald-800 px-1.5 py-0.5 rounded font-bold uppercase text-[8px]">
//               🏷️ {userRemark}
//             </span>
//           )}

//           <button
//             type="button"
//             onClick={(e) => {
//               e.stopPropagation();
//               setActivePreviewCluster(cluster);
//               handleOpenInspectionModal(item);
//             }}
//             className="bg-zinc-800 hover:bg-zinc-700 text-amber-400 border border-zinc-700 px-2 py-0.5 rounded text-[8px] font-bold cursor-pointer transition-colors"
//           >
//             🔍 Remarks
//           </button>
//         </div>
//       </div>
//     );
//   };

//   return (
//     <div className="w-[58%] border-r border-zinc-800 flex flex-col bg-zinc-950 font-mono text-xs overflow-hidden">
//       {/* Search & Control Bar */}
//       <div className="p-3 border-b border-zinc-800 flex items-center gap-2.5 bg-zinc-900/60 shrink-0">
//         <label className="flex items-center gap-1.5 text-[11px] text-zinc-400 font-bold cursor-pointer shrink-0">
//           <input
//             type="checkbox"
//             checked={visibleTxnIds.length > 0 && visibleTxnIds.every((id) => selectedTxnIds.includes(id))}
//             onChange={toggleSelectAllVisible}
//             className="w-3.5 h-3.5 accent-amber-500 cursor-pointer rounded"
//           />
//           <span>Visible</span>
//         </label>

//         {selectedTxnIds.length > 0 && (
//           <button
//             type="button"
//             onClick={clearAllSelections}
//             className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 px-2 py-0.5 rounded text-[10px] font-bold transition-colors cursor-pointer shrink-0"
//           >
//             Clear ({selectedTxnIds.length})
//           </button>
//         )}

//         <div className="relative flex-1">
//           <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
//           <input
//             type="text"
//             placeholder="Search vendor patterns, narrations across all database records..."
//             value={searchQuery}
//             onChange={(e) => setSearchQuery(e.target.value)}
//             className="w-full bg-zinc-950 border border-zinc-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-zinc-200 outline-none focus:border-amber-500/60 transition-colors font-sans"
//           />
//         </div>

//         <div className="flex gap-1 shrink-0">
//           <button
//             type="button"
//             onClick={expandAllClusters}
//             className="bg-zinc-950 border border-zinc-800 hover:bg-zinc-800 text-zinc-400 px-2 py-1 rounded text-[10px] font-bold transition-colors cursor-pointer"
//             title="Expand all clusters"
//           >
//             Expand
//           </button>
//           <button
//             type="button"
//             onClick={collapseAllClusters}
//             className="bg-zinc-950 border border-zinc-800 hover:bg-zinc-800 text-zinc-400 px-2 py-1 rounded text-[10px] font-bold transition-colors cursor-pointer"
//             title="Collapse all clusters"
//           >
//             Collapse
//           </button>
//         </div>
//       </div>

//       {/* Cluster List Container */}
//       <div className="flex-1 overflow-y-auto overflow-x-hidden p-3 flex flex-col gap-2">
//         {loading ? (
//           <div className="text-center py-20 text-zinc-500 flex flex-col items-center gap-2">
//             <div className="w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
//             <span className="text-xs">Querying database & assembling vendor patterns...</span>
//           </div>
//         ) : filteredClusters.length === 0 ? (
//           <div className="text-center py-20 text-zinc-600 flex flex-col items-center gap-2">
//             <AlertCircle className="w-6 h-6 text-zinc-600" />
//             <span className="text-xs">No matching transaction patterns found.</span>
//           </div>
//         ) : (
//           filteredClusters.map((cluster, clusterIdx) => {
//             const clusterTxnIds: string[] = cluster.transaction_ids || [];
//             const selectedInClusterCount = clusterTxnIds.filter((id) => selectedTxnIds.includes(id)).length;
//             const isClusterFullySelected = clusterTxnIds.length > 0 && selectedInClusterCount === clusterTxnIds.length;
//             const isClusterPartiallySelected = selectedInClusterCount > 0 && !isClusterFullySelected;
//             const isActive = activePreviewCluster?.pattern === cluster.pattern;
//             const clusterKey = cluster.pattern ? `cluster-${cluster.pattern}-${clusterIdx}` : `cluster-idx-${clusterIdx}`;

//             const expanded = isClusterExpanded(clusterKey);
//             const isFetchingItems = !!loadingClusterKeys[clusterKey];
//             const clusterOutflow = (cluster as ExtendedCluster).total_outflow ?? cluster.total_amount ?? 0;
//             const clusterInflow = (cluster as ExtendedCluster).total_inflow ?? 0;
//             const displayTag = (cluster.pattern || 'GENERAL_SUSPENSE').replace(/^#+/, '');

//             const activeItems = clusterItemsMap[clusterKey] || cluster.items || [];
//             const vendorGroups = groupItemsByVendor(activeItems);

//             return (
//               <div
//                 key={clusterKey}
//                 onClick={() => setActivePreviewCluster(cluster)}
//                 className={`p-2.5 rounded-xl border transition-all cursor-pointer ${
//                   isActive
//                     ? 'border-amber-500/80 bg-zinc-900/90 shadow-md ring-1 ring-amber-500/20'
//                     : selectedInClusterCount > 0
//                     ? 'border-zinc-700 bg-zinc-900/40'
//                     : 'border-zinc-800/80 bg-zinc-950/60 hover:bg-zinc-900/40'
//                 }`}
//               >
//                 {/* Master Cluster Header Row */}
//                 <div className="flex justify-between items-center gap-2">
//                   <div className="flex items-center gap-2 min-w-0 flex-1 mr-3">
//                     <input
//                       type="checkbox"
//                       checked={isClusterFullySelected}
//                       ref={(el) => {
//                         if (el) el.indeterminate = isClusterPartiallySelected;
//                       }}
//                       onClick={(e) => {
//                         setActivePreviewCluster(cluster);
//                         toggleClusterTxns(clusterTxnIds, e);
//                       }}
//                       onChange={() => {}}
//                       className="w-3.5 h-3.5 accent-amber-500 cursor-pointer rounded shrink-0"
//                     />

//                     <button
//                       type="button"
//                       onClick={(e) => toggleExpandCluster(cluster, clusterKey, e)}
//                       className="text-zinc-500 hover:text-zinc-200 p-0.5 cursor-pointer shrink-0"
//                     >
//                       {isFetchingItems ? (
//                         <div className="w-3 h-3 border border-amber-500 border-t-transparent rounded-full animate-spin" />
//                       ) : expanded ? (
//                         <ChevronDown className="w-3.5 h-3.5" />
//                       ) : (
//                         <ChevronRight className="w-3.5 h-3.5" />
//                       )}
//                     </button>

//                     <span className="font-bold text-xs text-zinc-100 truncate" title={`#${displayTag}`}>
//                       #{displayTag}
//                     </span>
//                   </div>

//                   <div className="flex items-center gap-2 shrink-0">
//                     <span className="px-1.5 py-0.5 text-[10px] bg-zinc-800 text-zinc-300 rounded font-bold tabular-nums">
//                       {selectedInClusterCount} / {cluster.count || clusterTxnIds.length || 0}
//                     </span>

//                     {clusterOutflow > 0 && (
//                       <span className="text-[10px] font-bold text-rose-400 bg-rose-950/40 border border-rose-800/40 px-1.5 py-0.5 rounded tabular-nums">
//                         🔻 {inrFormatter.format(clusterOutflow)}
//                       </span>
//                     )}

//                     {clusterInflow > 0 && (
//                       <span className="text-[10px] font-bold text-emerald-400 bg-emerald-950/40 border border-emerald-800/40 px-1.5 py-0.5 rounded tabular-nums">
//                         🟢 {inrFormatter.format(clusterInflow)}
//                       </span>
//                     )}
//                   </div>
//                 </div>

//                 {/* Sub-Vendors Accordion Layer */}
//                 {expanded && (
//                   <div className="pl-6 pt-2 flex flex-col gap-1.5">
//                     {isFetchingItems ? (
//                       <div className="text-[11px] text-zinc-500 py-2 flex items-center gap-2">
//                         <div className="w-3 h-3 border border-amber-500 border-t-transparent rounded-full animate-spin" />
//                         <span>Fetching granular transactions...</span>
//                       </div>
//                     ) : vendorGroups.length > 0 ? (
//                       vendorGroups.map((vGroup, vIdx) => {
//                         const vendorKey = `${clusterKey}-vendor-${vGroup.vendorName}-${vIdx}`;
//                         const selectedInVendorCount = vGroup.txnIds.filter((id) => selectedTxnIds.includes(id)).length;
//                         const isVendorFullySelected =
//                           vGroup.txnIds.length > 0 && selectedInVendorCount === vGroup.txnIds.length;
//                         const isVendorPartiallySelected = selectedInVendorCount > 0 && !isVendorFullySelected;
//                         const isVendorOpen = isVendorExpanded(vendorKey);
//                         const isGroupOutflow = vGroup.vendorName.endsWith('(OUT)');

//                         const isSingleItemGeneric =
//                           vGroup.items.length === 1 && vGroup.vendorName.startsWith('Granular Transactions');

//                         if (isSingleItemGeneric) {
//                           return renderTransactionCard(vGroup.items[0], cluster, clusterIdx, vIdx, 0, clusterKey);
//                         }

//                         return (
//                           <div
//                             key={vendorKey}
//                             className="bg-zinc-900/70 border border-zinc-800 rounded-lg p-2 flex flex-col gap-1.5"
//                           >
//                             <div className="flex justify-between items-center gap-2">
//                               <div className="flex items-center gap-2 min-w-0 flex-1">
//                                 <input
//                                   type="checkbox"
//                                   checked={isVendorFullySelected}
//                                   ref={(el) => {
//                                     if (el) el.indeterminate = isVendorPartiallySelected;
//                                   }}
//                                   onClick={(e) => {
//                                     setActivePreviewCluster(cluster);
//                                     toggleClusterTxns(vGroup.txnIds, e);
//                                   }}
//                                   onChange={() => {}}
//                                   className="w-3.5 h-3.5 accent-amber-500 cursor-pointer rounded shrink-0"
//                                 />

//                                 <button
//                                   type="button"
//                                   onClick={(e) => toggleExpandVendor(vendorKey, e)}
//                                   className="text-zinc-500 hover:text-zinc-300 p-0.5 cursor-pointer shrink-0"
//                                 >
//                                   {isVendorOpen ? (
//                                     <ChevronDown className="w-3 h-3" />
//                                   ) : (
//                                     <ChevronRight className="w-3 h-3" />
//                                   )}
//                                 </button>

//                                 <span className="text-[11px] font-bold text-zinc-200 truncate" title={vGroup.vendorName}>
//                                   {vGroup.vendorName}
//                                 </span>
//                               </div>

//                               <div className="flex items-center gap-2 shrink-0">
//                                 <span className="text-[9px] text-zinc-400 bg-zinc-800 px-1.5 py-0.2 rounded font-bold">
//                                   {vGroup.items.length} {vGroup.items.length === 1 ? 'item' : 'items'}
//                                 </span>
//                                 <span
//                                   className={`text-[10px] font-bold tabular-nums ${
//                                     isGroupOutflow ? 'text-rose-400' : 'text-emerald-400'
//                                   }`}
//                                 >
//                                   {isGroupOutflow ? '-' : '+'}₹{Math.abs(vGroup.totalAmount).toLocaleString('en-IN')}
//                                 </span>
//                               </div>
//                             </div>

//                             {/* Raw Line Items Under Vendor */}
//                             {isVendorOpen && (
//                               <div className="pl-4 pt-1 flex flex-col gap-1.5">
//                                 {vGroup.items.map((item, itemIdx) =>
//                                   renderTransactionCard(item, cluster, clusterIdx, vIdx, itemIdx, clusterKey)
//                                 )}
//                               </div>
//                             )}
//                           </div>
//                         );
//                       })
//                     ) : (
//                       (cluster.sample_descriptions || []).map((desc: string, descIdx: number) => (
//                         <div key={`desc-${clusterIdx}-${descIdx}`} className="text-[10px] text-zinc-500 truncate">
//                           • {desc}
//                         </div>
//                       ))
//                     )}
//                   </div>
//                 )}
//               </div>
//             );
//           })
//         )}
//       </div>

//       {/* Audit Remarks Dialog */}
//       {remarksModalItem && (
//         <div
//           onClick={() => setRemarksModalItem(null)}
//           className="fixed inset-0 bg-black/80 z-9999 flex items-center justify-center p-4 backdrop-blur-xs"
//         >
//           <div
//             onClick={(e) => e.stopPropagation()}
//             className="bg-zinc-900 border border-zinc-700 rounded-xl p-5 max-w-lg w-full text-zinc-100 shadow-2xl space-y-3 font-mono"
//           >
//             <div className="flex justify-between items-center border-b border-zinc-800 pb-2">
//               <h3 className="text-xs font-bold text-amber-400 uppercase tracking-wider">
//                 Line Item Audit & Remarks
//               </h3>
//               <button
//                 type="button"
//                 onClick={() => setRemarksModalItem(null)}
//                 className="text-zinc-400 hover:text-zinc-100 p-1 rounded"
//               >
//                 <X className="w-4 h-4" />
//               </button>
//             </div>

//             <div className="space-y-1">
//               <label className="text-[10px] text-zinc-500 uppercase font-bold block">
//                 Original Statement Narration
//               </label>
//               <div className="bg-zinc-950 border border-zinc-800 p-2.5 rounded-lg text-xs text-cyan-300 wrap-break-word font-mono">
//                 {remarksModalItem.narration}
//               </div>
//             </div>

//             <div className="space-y-1">
//               <label className="text-[10px] text-amber-400 uppercase font-bold block">
//                 User Comment / Note
//               </label>
//               <input
//                 type="text"
//                 placeholder="e.g., Personal payment for tea at Technopark..."
//                 value={userNoteInput}
//                 onChange={(e) => setUserNoteInput(e.target.value)}
//                 className="w-full bg-zinc-950 border border-zinc-700 px-3 py-2 rounded-lg text-xs text-zinc-100 outline-none focus:border-amber-400 font-sans"
//               />
//             </div>

//             <div className="flex gap-2 pt-2">
//               <button
//                 type="button"
//                 onClick={() => setRemarksModalItem(null)}
//                 className="flex-1 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs rounded-lg font-bold transition-colors cursor-pointer"
//               >
//                 Cancel
//               </button>
//               <button
//                 type="button"
//                 onClick={handleSaveUserNote}
//                 disabled={savingNote}
//                 className="flex-1 py-2 bg-amber-500 hover:bg-amber-400 text-zinc-950 text-xs rounded-lg font-bold transition-colors cursor-pointer disabled:opacity-50"
//               >
//                 {savingNote ? 'Saving...' : 'Save Comment'}
//               </button>
//             </div>
//           </div>
//         </div>
//       )}
//     </div>
//   );
// };