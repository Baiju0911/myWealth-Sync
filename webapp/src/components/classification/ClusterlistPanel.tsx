import React, { useState, useCallback } from 'react';
import type { ExtendedCluster, Cluster } from '../../api/api';
import { updateEntryUserNote } from '../../api/api';
import { 
  inrFormatter, 
  parseRemarks, 
  extractCleanPayee, 
  extractUpiRemark 
} from '../../utils/classificationHelpers';

// 💡 Type definition for internal vendor sub-grouping
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
  lastAppliedMapping?: {
    txnIds: string[];
    asset_id?: string | number;
    asset_code?: string;
    asset_name?: string;
  } | null;
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
  lastAppliedMapping,
}) => {
  const [remarksModalItem, setRemarksModalItem] = useState<{
    id: string;
    narration?: string;
    remarks?: any;
    subledger_mapping?: any;
  } | null>(null);
  const [userNoteInput, setUserNoteInput] = useState<string>('');
  const [savingNote, setSavingNote] = useState<boolean>(false);

  // Collapsible state for top-level cluster cards (all expanded by default)
  const [expandedClusterKeys, setExpandedClusterKeys] = useState<Record<string, boolean>>({});
  
  // Collapsible state for vendor sub-accordions (collapsed by default to keep view compact)
  const [expandedVendorKeys, setExpandedVendorKeys] = useState<Record<string, boolean>>({});

  const isClusterExpanded = useCallback(
    (clusterKey: string) => expandedClusterKeys[clusterKey] !== false,
    [expandedClusterKeys]
  );

  const isVendorExpanded = useCallback(
    (vendorKey: string) => !!expandedVendorKeys[vendorKey],
    [expandedVendorKeys]
  );

  const toggleExpandCluster = (clusterKey: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedClusterKeys((prev) => ({
      ...prev,
      [clusterKey]: !isClusterExpanded(clusterKey),
    }));
  };

  const toggleExpandVendor = (vendorKey: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedVendorKeys((prev) => ({
      ...prev,
      [vendorKey]: !isVendorExpanded(vendorKey),
    }));
  };

  const expandAllClusters = () => setExpandedClusterKeys({});

  const collapseAllClusters = () => {
    const collapsedMap: Record<string, boolean> = {};
    filteredClusters.forEach((c, idx) => {
      const key = c.pattern ? `cluster-${c.pattern}-${idx}` : `cluster-idx-${idx}`;
      collapsedMap[key] = false;
    });
    setExpandedClusterKeys(collapsedMap);
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

  // Helper to resolve mapping with optimistic overlay
  const resolveItemMapping = (item: any) => {
    if (
      lastAppliedMapping &&
      lastAppliedMapping.txnIds.includes(String(item.id || item.row_identifier))
    ) {
      return {
        asset_id: lastAppliedMapping.asset_id,
        asset_code: lastAppliedMapping.asset_code,
        asset_name: lastAppliedMapping.asset_name,
        is_cash_float: String(lastAppliedMapping.asset_code || '').includes('FLT'),
      };
    }
    return item.subledger_mapping || item.mapping_info || null;
  };

  // 💡 Sub-group raw cluster items by clean vendor name AND direction (IN vs OUT), sorted Max to Min Count
  const groupItemsByVendor = (items: any[] = []): VendorGroup[] => {
    const groupsMap: Record<string, VendorGroup> = {};

    items.forEach((item) => {
      const remarksObj = parseRemarks(item.remarks);
      const name = extractCleanPayee(item.narration) || remarksObj.payee || 'Unlabeled Vendor';

      // Determine item direction explicitly
      const dirStr = (item.direction || item.vector_type || item.entry_type || '').toUpperCase();
      const isOut = dirStr === 'OUTFLOW' || dirStr === 'DEBIT' || dirStr === 'DR'
        ? true
        : dirStr === 'INFLOW' || dirStr === 'CREDIT' || dirStr === 'CR'
        ? false
        : item.debit != null && Number(item.debit) > 0
        ? true
        : item.credit != null && Number(item.credit) > 0
        ? false
        : (item.narration || '').toUpperCase().startsWith('DEP TFR NEFT')
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
      if (b.items.length !== a.items.length) {
        return b.items.length - a.items.length;
      }
      return Math.abs(b.totalAmount) - Math.abs(a.totalAmount);
    });
  };

  return (
    <div style={{ width: '58%', borderRight: '1px solid #27272a', display: 'flex', flexDirection: 'column', backgroundColor: '#09090b' }}>
      
      {/* Search & Select Bar */}
      <div style={{ padding: '12px', borderBottom: '1px solid #27272a', display: 'flex', alignItems: 'center', gap: '10px', backgroundColor: '#121215' }}>
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
            style={{
              backgroundColor: '#27272a',
              color: '#f4f4f5',
              border: 'none',
              borderRadius: '4px',
              padding: '3px 8px',
              fontSize: '10px',
              cursor: 'pointer',
            }}
          >
            Clear ({selectedTxnIds.length})
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
            borderRadius: '6px',
            padding: '6px 10px',
            fontSize: '11px',
            color: '#f4f4f5',
            outline: 'none',
          }}
        />

        <div style={{ display: 'flex', gap: '4px' }}>
          <button
            type="button"
            onClick={expandAllClusters}
            title="Expand all clusters"
            style={{ backgroundColor: '#18181b', border: '1px solid #27272a', color: '#a1a1aa', padding: '3px 6px', borderRadius: '4px', fontSize: '10px', cursor: 'pointer' }}
          >
            ▼ Expand
          </button>
          <button
            type="button"
            onClick={collapseAllClusters}
            title="Collapse all clusters"
            style={{ backgroundColor: '#18181b', border: '1px solid #27272a', color: '#a1a1aa', padding: '3px 6px', borderRadius: '4px', fontSize: '10px', cursor: 'pointer' }}
          >
            ▶ Collapse
          </button>
        </div>
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
          filteredClusters.map((cluster, clusterIdx) => {
            const clusterTxnIds: string[] = cluster.transaction_ids || [];
            const selectedInClusterCount = clusterTxnIds.filter((id) => selectedTxnIds.includes(id)).length;
            const isClusterFullySelected = clusterTxnIds.length > 0 && selectedInClusterCount === clusterTxnIds.length;
            const isClusterPartiallySelected = selectedInClusterCount > 0 && !isClusterFullySelected;
            const isActive = activePreviewCluster?.pattern === cluster.pattern;
            const clusterKey = cluster.pattern ? `cluster-${cluster.pattern}-${clusterIdx}` : `cluster-idx-${clusterIdx}`;

            const expanded = isClusterExpanded(clusterKey);
            const clusterOutflow = cluster.total_outflow ?? cluster.total_amount ?? 0;
            const clusterInflow = cluster.total_inflow ?? 0;
            const displayTag = (cluster.pattern || 'GENERAL_SUSPENSE').replace(/^#+/, '');

            const vendorGroups = groupItemsByVendor(cluster.items || []);

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
                  transition: 'background-color 0.15s ease',
                }}
              >
                {/* Master Cluster Header Row */}
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
                      onClick={(e) => toggleExpandCluster(clusterKey, e)}
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

                {/* Collapsible Vendor Sub-Clusters Layer */}
                {expanded && (
                  <div style={{ paddingLeft: '20px', paddingTop: '8px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {vendorGroups.length > 0 ? (
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
                            style={{
                              backgroundColor: '#141417',
                              border: '1px solid #27272a',
                              borderRadius: '6px',
                              padding: '6px 10px',
                              display: 'flex',
                              flexDirection: 'column',
                              gap: '4px',
                            }}
                          >
                            {/* Vendor Sub-Cluster Header Bar */}
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

                            {/* Collapsible Individual Raw Line Items */}
                            {isVendorOpen && (
                              <div style={{ paddingLeft: '22px', paddingTop: '4px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                {vGroup.items.map((item, itemIdx) => {
                                  const isItemChecked = selectedTxnIds.includes(item.id);

                                  const isOutflow = (() => {
                                    const dirStr = (item.direction || item.vector_type || item.entry_type || '').toUpperCase();
                                    if (dirStr === 'OUTFLOW' || dirStr === 'DEBIT' || dirStr === 'DR') return true;
                                    if (dirStr === 'INFLOW' || dirStr === 'CREDIT' || dirStr === 'CR') return false;

                                    if (item.debit != null && Number(item.debit) > 0) return true;
                                    if (item.credit != null && Number(item.credit) > 0) return false;

                                    const narration = (item.narration || '').toUpperCase();
                                    if (narration.startsWith('DEP TFR NEFT') || narration.includes('CREDIT') || narration.includes('INFLOW')) {
                                      return false;
                                    }

                                    return (item.amount ?? 0) < 0;
                                  })();

                                  const flagColor = isOutflow ? '#fb7185' : '#34d399';
                                  const itemKey = item.id ? `item-${item.id}` : `item-idx-${clusterIdx}-${vIdx}-${itemIdx}`;
                                  const remarksObj = parseRemarks(item.remarks);
                                  const userRemark = extractUpiRemark(item.narration);
                                  const subledgerMap = resolveItemMapping(item);

                                  return (
                                    <div
                                      key={itemKey}
                                      onClick={(e) => e.stopPropagation()}
                                      style={{
                                        display: 'flex',
                                        flexDirection: 'column',
                                        gap: '3px',
                                        padding: '5px 8px',
                                        borderRadius: '4px',
                                        backgroundColor: isItemChecked ? '#27272a' : '#09090b',
                                        borderLeft: `3px solid ${flagColor}`,
                                        fontSize: '10px',
                                      }}
                                    >
                                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                        <input
                                          type="checkbox"
                                          checked={isItemChecked}
                                          onClick={(e) => {
                                            setActivePreviewCluster(cluster);
                                            toggleIndividualTxn(item.id, e);
                                          }}
                                          onChange={() => {}}
                                          style={{ width: '13px', height: '13px', accentColor: '#f59e0b', cursor: 'pointer' }}
                                        />

                                        <span
                                          style={{
                                            fontSize: '8px',
                                            fontWeight: 'bold',
                                            padding: '1px 3px',
                                            borderRadius: '2px',
                                            backgroundColor: isOutflow ? '#88133744' : '#064e3b44',
                                            color: flagColor,
                                            border: `1px solid ${isOutflow ? '#f43f5e44' : '#10b98144'}`,
                                          }}
                                        >
                                          {isOutflow ? 'OUT' : 'IN'}
                                        </span>

                                        <span
                                          style={{
                                            flex: 1,
                                            whiteSpace: 'nowrap',
                                            overflow: 'hidden',
                                            textOverflow: 'ellipsis',
                                            fontFamily: 'monospace',
                                            color: '#d4d4d8',
                                          }}
                                          title={item.narration}
                                        >
                                          {item.narration || 'Unlabeled Bank Line'}
                                        </span>

                                        <span style={{ fontSize: '10px', fontWeight: 'bold', color: flagColor, fontFamily: 'monospace' }}>
                                          {isOutflow 
                                            ? `-₹${Math.abs(item.amount || item.debit || 0).toLocaleString('en-IN')}` 
                                            : `+₹${Math.abs(item.amount || item.credit || 0).toLocaleString('en-IN')}`}
                                        </span>
                                      </div>

                                      {/* Subledger Destination Badge & Metadata Row */}
                                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginLeft: '21px', fontSize: '9px', marginTop: '2px' }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                                          {/* 🎯 Subledger / Cash Float Attribution Badge */}
                                          {subledgerMap ? (
                                            <span
                                              style={{
                                                display: 'inline-flex',
                                                alignItems: 'center',
                                                gap: '3px',
                                                backgroundColor: subledgerMap.is_cash_float ? '#451a03' : '#064e3b',
                                                color: subledgerMap.is_cash_float ? '#fcd34d' : '#6ee7b7',
                                                border: `1px solid ${subledgerMap.is_cash_float ? '#b45309' : '#047857'}`,
                                                padding: '1px 5px',
                                                borderRadius: '3px',
                                                fontWeight: 'bold',
                                                fontFamily: 'monospace',
                                                fontSize: '8.5px',
                                              }}
                                              title={`Mapped to ${subledgerMap.asset_name || 'Subledger Folio'}`}
                                            >
                                              <span>{subledgerMap.is_cash_float ? '💵' : '🏬'}</span>
                                              <span>[{subledgerMap.asset_code || 'FOLIO'}]</span>
                                              <span style={{ maxWidth: '140px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                {subledgerMap.asset_name}
                                              </span>
                                            </span>
                                          ) : (
                                            <span style={{ color: '#52525b', fontSize: '8.5px', fontFamily: 'monospace' }}>
                                              Direct GL
                                            </span>
                                          )}

                                          {remarksObj.upi_ref && (
                                            <span style={{ backgroundColor: '#18181b', color: '#a1a1aa', padding: '1px 4px', borderRadius: '3px', border: '1px solid #27272a', fontFamily: 'monospace' }}>
                                              Ref: {remarksObj.upi_ref}
                                            </span>
                                          )}

                                          {userRemark && (
                                            <span
                                              style={{
                                                backgroundColor: '#064e3b',
                                                color: '#34d399',
                                                padding: '1px 6px',
                                                borderRadius: '3px',
                                                border: '1px solid #047857',
                                                fontWeight: 'bold',
                                                fontSize: '8px',
                                                textTransform: 'uppercase',
                                              }}
                                              title={`Detected user remark: ${userRemark}`}
                                            >
                                              🏷️ {userRemark}
                                            </span>
                                          )}
                                        </div>

                                        <button
                                          type="button"
                                          onClick={(e) => {
                                            e.stopPropagation();
                                            setActivePreviewCluster(cluster);
                                            handleOpenInspectionModal({
                                              ...item,
                                              subledger_mapping: subledgerMap,
                                            });
                                          }}
                                          style={{
                                            backgroundColor: '#27272a',
                                            color: '#f59e0b',
                                            border: '1px solid #3f3f46',
                                            borderRadius: '3px',
                                            padding: '1px 5px',
                                            fontSize: '8.5px',
                                            cursor: 'pointer',
                                            fontWeight: 'bold',
                                          }}
                                        >
                                          🔍 Remarks
                                        </button>
                                      </div>
                                    </div>
                                  );
                                })}
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

      {/* Line Item Audit Remarks Modal */}
      {remarksModalItem && (
        <div
          onClick={() => setRemarksModalItem(null)}
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.75)',
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
              maxWidth: '520px',
              width: '100%',
              color: '#f4f4f5',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <h3 style={{ margin: 0, fontSize: '13px', fontWeight: 'bold', color: '#f59e0b', textTransform: 'uppercase' }}>
                Line Item Audit & Remarks
              </h3>
              <button
                type="button"
                onClick={() => setRemarksModalItem(null)}
                style={{ background: 'none', border: 'none', color: '#a1a1aa', cursor: 'pointer', fontSize: '16px' }}
              >
                ✕
              </button>
            </div>

            {/* Subledger Destination Status In Modal */}
            {remarksModalItem.subledger_mapping && (
              <div style={{ marginBottom: '12px', padding: '8px 10px', borderRadius: '6px', backgroundColor: '#09090b', border: '1px solid #27272a', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '10px', color: '#71717a', textTransform: 'uppercase', fontWeight: 'bold' }}>
                  Subledger Folio Link:
                </span>
                <span style={{
                  fontSize: '10px',
                  fontWeight: 'bold',
                  color: remarksModalItem.subledger_mapping.is_cash_float ? '#fcd34d' : '#6ee7b7',
                  fontFamily: 'monospace',
                }}>
                  {remarksModalItem.subledger_mapping.is_cash_float ? '💵 Cash Float' : '🏬 Folio Asset'}: [{remarksModalItem.subledger_mapping.asset_code}] {remarksModalItem.subledger_mapping.asset_name}
                </span>
              </div>
            )}

            <div style={{ marginBottom: '12px' }}>
              <label style={{ fontSize: '10px', color: '#71717a', textTransform: 'uppercase', fontWeight: 'bold', display: 'block', marginBottom: '2px' }}>
                Original Statement Narration
              </label>
              <div style={{ backgroundColor: '#09090b', border: '1px solid #27272a', padding: '8px 10px', borderRadius: '6px', fontSize: '11px', fontFamily: 'monospace', color: '#38bdf8', wordBreak: 'break-word' }}>
                {remarksModalItem.narration}
              </div>
            </div>

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