import React, { useState, useMemo } from 'react';
import type { AssetCategoryGroup, HierarchyAssetNode } from '../helper/subledgerGrouping';
import { AssetNodeCard } from './AssetNodeCard';
import { inrFormatter } from '../../../utils/classificationHelpers';

interface AssetGroupContainerProps {
  group: AssetCategoryGroup;
  isExpanded: boolean;
  metricLabel: string;
  onToggleExpand: (groupKey: string) => void;
  onOpenMatcher: any;
  onOpenHistory: any;
  onEditAsset: any;
  onDeleteAsset: any;
  onCreateUtility: any;
  onEditUtility: any;
  onCreateSchedule: any;
  onEditSchedule: any;
}

interface VendorSubCluster {
  vendorKey: string;
  vendorName: string;
  assets: HierarchyAssetNode[];
  totalValuation: number;
}

export const AssetGroupContainer: React.FC<AssetGroupContainerProps> = ({
  group,
  isExpanded,
  metricLabel,
  onToggleExpand,
  onOpenMatcher,
  onOpenHistory,
  onEditAsset,
  onDeleteAsset,
  onCreateUtility,
  onEditUtility,
  onCreateSchedule,
  onEditSchedule,
}) => {
  // Track open/close state for nested vendors inside this GL Head
  const [expandedVendors, setExpandedVendors] = useState<Record<string, boolean>>({});

  // Group this GL head's assets by their Vendor / Merchant / Counterparty
  const vendorSubClusters = useMemo(() => {
    const map: Record<string, VendorSubCluster> = {};

    group.rootAssets.forEach((asset) => {
      const vName =
        asset.vendor_name ||
        (asset as any).vendor_detail?.name ||
        (typeof (asset as any).vendor === 'string' && (asset as any).vendor.trim().length > 0
          ? (asset as any).vendor
          : null) ||
        'Direct / Independent';

      const vKey = vName.toLowerCase().replace(/[^a-z0-9]/g, '_');

      if (!map[vKey]) {
        map[vKey] = {
          vendorKey: vKey,
          vendorName: vName,
          assets: [],
          totalValuation: 0,
        };
      }

      map[vKey].assets.push(asset);
      map[vKey].totalValuation += Number(asset.current_valuation || 0);
    });

    return Object.values(map).sort((a, b) => {
      if (a.vendorName === 'Direct / Independent') return 1;
      if (b.vendorName === 'Direct / Independent') return -1;
      return b.totalValuation - a.totalValuation;
    });
  }, [group.rootAssets]);

  const toggleVendorCluster = (vendorKey: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedVendors((prev) => ({
      ...prev,
      [vendorKey]: !prev[vendorKey],
    }));
  };

  return (
    <div className="rounded-xl border border-slate-800/90 bg-slate-900/60 overflow-hidden shadow-xl font-mono">
      {/* 🏛️️ LEVEL 1: Master GL Head Accordion Header */}
      <div
        onClick={() => onToggleExpand(group.groupKey)}
        className="flex items-center justify-between bg-slate-800/90 px-4 py-3 cursor-pointer hover:bg-slate-800 transition-colors select-none border-b border-slate-800/60"
      >
        <div className="flex items-center gap-3">
          <span className="text-[10px] text-emerald-400 font-bold">
            {isExpanded ? '▼' : '▶'}
          </span>
          <h3 className="text-xs font-bold text-white flex items-center gap-2">
            🏛️ {group.groupTitle}
            <span className="text-[10px] text-slate-400 bg-slate-950 px-2 py-0.5 rounded-full border border-slate-700/80">
              {group.totalNodeCount} {group.totalNodeCount === 1 ? 'Folio' : 'Folios'}
            </span>
          </h3>
        </div>

        <div className="flex items-center gap-6 text-xs">
          <div className="text-right">
            <span className="text-slate-500 block text-[9px] uppercase tracking-wider">
              TOTAL {metricLabel}
            </span>
            <span className="text-emerald-400 font-bold text-xs">
              {inrFormatter.format(group.totalValuation)}
            </span>
          </div>
        </div>
      </div>

      {/* 🏬 LEVEL 2: Nested Vendor / Counterparty Sections */}
      {isExpanded && (
        <div className="p-3.5 space-y-3 bg-slate-950/60">
          {vendorSubClusters.map((cluster) => {
            // Default to expanded, or use explicit toggled state
            const isVendorOpen = expandedVendors[cluster.vendorKey] !== false;

            return (
              <div
                key={cluster.vendorKey}
                className="rounded-lg border border-slate-800/80 bg-slate-900/40 overflow-hidden"
              >
                {/* Vendor Sub-Accordion Header */}
                <div
                  onClick={(e) => toggleVendorCluster(cluster.vendorKey, e)}
                  className="flex items-center justify-between px-3.5 py-2.5 bg-slate-900/90 hover:bg-slate-800/70 cursor-pointer transition-colors border-b border-slate-800/60 select-none"
                >
                  <div className="flex items-center gap-2.5">
                    <span className="text-[9px] text-teal-400">
                      {isVendorOpen ? '▼' : '▶'}
                    </span>
                    <span className="text-xs font-bold text-slate-200 flex items-center gap-2">
                      🏬 {cluster.vendorName}
                      <span className="text-[9px] text-teal-400 bg-teal-950/80 px-2 py-0.5 rounded-full border border-teal-500/30">
                        {cluster.assets.length} {cluster.assets.length === 1 ? 'Item' : 'Items'}
                      </span>
                    </span>
                  </div>

                  <div className="text-right">
                    <span className="text-xs font-bold text-slate-300">
                      {inrFormatter.format(cluster.totalValuation)}
                    </span>
                  </div>
                </div>

                {/* Folio Cards inside this Vendor */}
                {isVendorOpen && (
                  <div className="p-3 space-y-3 bg-slate-950/40">
                    {cluster.assets.map((asset) => (
                      <AssetNodeCard
                        key={asset.id}
                        asset={asset}
                        metricLabel={metricLabel}
                        onOpenMatcher={onOpenMatcher}
                        onOpenHistory={onOpenHistory}
                        onEditAsset={onEditAsset}
                        onDeleteAsset={onDeleteAsset}
                        onCreateUtility={onCreateUtility}
                        onEditUtility={onEditUtility}
                        onCreateSchedule={onCreateSchedule}
                        onEditSchedule={onEditSchedule}
                      />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};