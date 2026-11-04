// webapp/src/components/Stage3/Workbench/clusterlistHelpers/ClusterAccordionItem.tsx
import React, { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { ExtendedCluster } from '../../../../api/api';
import { inrFormatter } from '../../../../utils/classificationHelpers';
import { ClusterCardItem } from './ClusterCardItem';
import {
  evaluateItemMatch,
  parseAdvancedSearchQuery,
  type StatusFilterType,
  type DirectionFilterType,
} from './searchAndFilterHelpers';

interface Props {
  cluster: ExtendedCluster;
  clusterKey: string;
  isExpanded: boolean;
  isFetchingItems: boolean;
  isActive: boolean;
  selectedTxnIds: string[];
  activeItems: any[];
  globalNarrationMode: 'smart' | 'raw';
  searchTokens?: string[];
  searchQuery?: string;
  statusFilter?: StatusFilterType;
  directionFilter?: DirectionFilterType;
  unmappingItemIds: Record<string, boolean>;
  onToggleExpand: (cluster: ExtendedCluster, clusterKey: string, e: React.MouseEvent) => void;
  onSelectCluster: (cluster: ExtendedCluster) => void;
  onToggleClusterTxns: (txnIds: string[], e: React.MouseEvent) => void;
  onToggleIndividualTxn: (id: string, e: React.MouseEvent) => void;
  onUnmap: (e: React.MouseEvent, item: any, clusterKey: string) => void;
  onOpenRemarksModal: (item: any) => void;
}

export const ClusterAccordionItem: React.FC<Props> = ({
  cluster,
  clusterKey,
  isExpanded,
  isFetchingItems,
  isActive,
  selectedTxnIds,
  activeItems,
  globalNarrationMode,
  searchTokens = [],
  searchQuery,
  statusFilter = 'all',
  directionFilter = 'all',
  unmappingItemIds,
  onToggleExpand,
  onSelectCluster,
  onToggleClusterTxns,
  onToggleIndividualTxn,
  onUnmap,
  onOpenRemarksModal,
}) => {
  const [expandedVendorKeys, setExpandedVendorKeys] = useState<Record<string, boolean>>({});

  const clusterTxnIds: string[] = cluster.transaction_ids || [];
  const selectedCount = clusterTxnIds.filter((id) => selectedTxnIds.includes(id)).length;
  const isFullySelected = clusterTxnIds.length > 0 && selectedCount === clusterTxnIds.length;
  const isPartiallySelected = selectedCount > 0 && !isFullySelected;

  const clusterOutflow = (cluster as ExtendedCluster).total_outflow ?? cluster.total_amount ?? 0;
  const clusterInflow = (cluster as ExtendedCluster).total_inflow ?? 0;
  const displayTag = (cluster.pattern || 'GENERAL_SUSPENSE').replace(/^#+/, '');

  // 🎯 Filter items strictly matching amount, tokens, direction & status
  const vendorGroups = React.useMemo(() => {
    const criteria = parseAdvancedSearchQuery(searchQuery || '');

    const matchingItems = (activeItems || []).filter((it) =>
      evaluateItemMatch(it, criteria, statusFilter, directionFilter)
    );

    const map: Record<string, { vendorName: string; items: any[]; txnIds: string[]; totalAmount: number }> = {};

    matchingItems.forEach((it) => {
      const payee = it.display_payee || it.remarks?.payee || 'Transactions';
      const dir = (it.direction || it.vector_type || it.entry_type || '').toUpperCase();
      const isOut =
        ['OUTFLOW', 'DEBIT', 'DR'].includes(dir) ||
        (it.debit != null && Number(it.debit) > 0) ||
        (it.amount ?? 0) < 0;
      const tag = isOut ? 'OUT' : 'IN';
      const groupKey = `${payee}__${tag}`;

      if (!map[groupKey]) {
        map[groupKey] = { vendorName: `${payee} (${tag})`, items: [], txnIds: [], totalAmount: 0 };
      }
      map[groupKey].items.push(it);
      if (it.id) map[groupKey].txnIds.push(it.id);
      map[groupKey].totalAmount += it.amount || it.debit || it.credit || 0;
    });

    return Object.values(map).sort((a, b) => b.items.length - a.items.length);
  }, [activeItems, searchQuery, statusFilter, directionFilter]);

  return (
    <div
      onClick={() => onSelectCluster(cluster)}
      className={`p-2.5 rounded-xl border transition-all cursor-pointer font-mono text-xs ${
        isActive
          ? 'border-amber-500/80 bg-zinc-900/90 shadow-md ring-1 ring-amber-500/20'
          : selectedCount > 0
          ? 'border-zinc-700 bg-zinc-900/40'
          : 'border-zinc-800/80 bg-zinc-950/60 hover:bg-zinc-900/40'
      }`}
    >
      {/* Cluster Header */}
      <div className="flex justify-between items-center gap-2">
        <div className="flex items-center gap-2 min-w-0 flex-1 mr-3">
          <input
            type="checkbox"
            checked={isFullySelected}
            ref={(el) => {
              if (el) el.indeterminate = isPartiallySelected;
            }}
            onClick={(e) => {
              onSelectCluster(cluster);
              onToggleClusterTxns(clusterTxnIds, e);
            }}
            onChange={() => {}}
            className="w-3.5 h-3.5 accent-amber-500 cursor-pointer rounded shrink-0"
          />

          <button
            type="button"
            onClick={(e) => onToggleExpand(cluster, clusterKey, e)}
            className="text-zinc-500 hover:text-zinc-200 p-0.5 cursor-pointer shrink-0"
          >
            {isFetchingItems ? (
              <div className="w-3 h-3 border border-amber-500 border-t-transparent rounded-full animate-spin" />
            ) : isExpanded ? (
              <ChevronDown className="w-3.5 h-3.5" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5" />
            )}
          </button>

          <span className="font-bold text-xs text-zinc-100 truncate" title={`#${displayTag}`}>
            #{displayTag}
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className="px-1.5 py-0.5 text-[10px] bg-zinc-800 text-zinc-300 rounded font-bold tabular-nums">
            {selectedCount} / {cluster.count || clusterTxnIds.length || 0}
          </span>

          {clusterOutflow > 0 && (
            <span className="text-[10px] font-bold text-rose-400 bg-rose-950/40 border border-rose-800/40 px-1.5 py-0.5 rounded tabular-nums">
              🔻 {inrFormatter.format(clusterOutflow)}
            </span>
          )}

          {clusterInflow > 0 && (
            <span className="text-[10px] font-bold text-emerald-400 bg-emerald-950/40 border border-emerald-800/40 px-1.5 py-0.5 rounded tabular-nums">
              🟢 {inrFormatter.format(clusterInflow)}
            </span>
          )}
        </div>
      </div>

      {/* Sub-Vendor Accordion Body */}
      {isExpanded && (
        <div className="pl-6 pt-2 flex flex-col gap-1.5">
          {isFetchingItems ? (
            <div className="text-[11px] text-zinc-500 py-2 flex items-center gap-2">
              <div className="w-3 h-3 border border-amber-500 border-t-transparent rounded-full animate-spin" />
              <span>Fetching granular transactions...</span>
            </div>
          ) : activeItems.length > 0 && vendorGroups.length === 0 ? (
            <div className="p-3 bg-zinc-900/50 border border-zinc-800/80 rounded-lg text-center font-mono">
              <p className="text-[11px] text-zinc-400 font-semibold">
                No transactions in #{displayTag} match: <span className="text-amber-300 font-bold font-sans">"{searchQuery}"</span>
              </p>
              <p className="text-[10px] text-zinc-600 mt-1">
                Cluster contains {activeItems.length} transactions, but none meet the combined amount/date criteria.
              </p>
            </div>
          ) : vendorGroups.length > 0 ? (
            vendorGroups.map((vGroup, vIdx) => {
              const vendorKey = `${clusterKey}-v-${vGroup.vendorName}-${vIdx}`;
              const isVendorOpen = expandedVendorKeys[vendorKey] !== false;
              const vSelectedCount = vGroup.txnIds.filter((id) => selectedTxnIds.includes(id)).length;
              const isVFully = vGroup.txnIds.length > 0 && vSelectedCount === vGroup.txnIds.length;
              const isVPart = vSelectedCount > 0 && !isVFully;
              const isOut = vGroup.vendorName.endsWith('(OUT)');

              return (
                <div key={vendorKey} className="bg-zinc-900/70 border border-zinc-800 rounded-lg p-2 flex flex-col gap-1.5">
                  <div className="flex justify-between items-center gap-2">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <input
                        type="checkbox"
                        checked={isVFully}
                        ref={(el) => {
                          if (el) el.indeterminate = isVPart;
                        }}
                        onClick={(e) => {
                          onSelectCluster(cluster);
                          onToggleClusterTxns(vGroup.txnIds, e);
                        }}
                        onChange={() => {}}
                        className="w-3.5 h-3.5 accent-amber-500 cursor-pointer rounded shrink-0"
                      />

                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setExpandedVendorKeys((p) => ({ ...p, [vendorKey]: !isVendorOpen }));
                        }}
                        className="text-zinc-500 hover:text-zinc-300 p-0.5 cursor-pointer shrink-0"
                      >
                        {isVendorOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                      </button>

                      <span className="text-[11px] font-bold text-zinc-200 truncate" title={vGroup.vendorName}>
                        {vGroup.vendorName}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-[9px] text-zinc-400 bg-zinc-800 px-1.5 py-0.5 rounded font-bold">
                        {vGroup.items.length} {vGroup.items.length === 1 ? 'item' : 'items'}
                      </span>
                      <span className={`text-[10px] font-bold tabular-nums ${isOut ? 'text-rose-400' : 'text-emerald-400'}`}>
                        {isOut ? '-' : '+'}₹{Math.abs(vGroup.totalAmount).toLocaleString('en-IN')}
                      </span>
                    </div>
                  </div>

                  {/* Transaction Cards */}
                  {isVendorOpen && (
                    <div className="pl-4 pt-1 flex flex-col gap-1.5">
                      {vGroup.items.map((item) => (
                        <ClusterCardItem
                          key={item.id ? `item-${item.id}` : `temp-${Math.random()}`}
                          item={item}
                          clusterKey={clusterKey}
                          isSelected={selectedTxnIds.includes(item.id)}
                          isUnmapping={Boolean(unmappingItemIds[String(item.id)])}
                          globalNarrationMode={globalNarrationMode}
                          searchTokens={searchTokens}
                          onToggleSelect={(id, e) => {
                            onSelectCluster(cluster);
                            onToggleIndividualTxn(id, e);
                          }}
                          onUnmap={onUnmap}
                          onOpenRemarksModal={(it) => {
                            onSelectCluster(cluster);
                            onOpenRemarksModal(it);
                          }}
                        />
                      ))}
                    </div>
                  )}
                </div>
              );
            })
          ) : (
            (cluster.sample_descriptions || []).map((desc, dIdx) => (
              <div key={`d-${dIdx}`} className="text-[10px] text-zinc-500 truncate">• {desc}</div>
            ))
          )}
        </div>
      )}
    </div>
  );
};