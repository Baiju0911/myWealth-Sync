import React from 'react';
import type { HierarchyAssetNode } from '../helper/subledgerGrouping';
import { inrFormatter } from '../../../utils/classificationHelpers';
import { ChevronRight, Store, Landmark, Wallet } from 'lucide-react';

export interface VendorSubCluster {
  vendorKey: string;
  vendorName: string;
  assets: HierarchyAssetNode[];
  totalValuation: number;
}

interface VendorSummaryCardProps {
  cluster: VendorSubCluster;
  isCashDomain: boolean;
  metricLabel: string;
  onClick: () => void;
}

export const VendorSummaryCard: React.FC<VendorSummaryCardProps> = ({
  cluster,
  isCashDomain,
  metricLabel,
  onClick,
}) => {
  const renderIcon = () => {
    if (isCashDomain) return <Wallet className="w-4 h-4 text-emerald-400" />;
    const vName = cluster.vendorName.toLowerCase();
    if (vName.includes('bank') || vName.includes('sbi') || vName.includes('sib')) {
      return <Landmark className="w-4 h-4 text-sky-400" />;
    }
    return <Store className="w-4 h-4 text-teal-400" />;
  };

  return (
    <div
      onClick={onClick}
      className="bg-slate-900/80 border border-slate-800 hover:border-teal-500/50 hover:bg-slate-900 rounded-xl p-4 transition-all cursor-pointer flex flex-col justify-between group shadow-sm hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="p-2 rounded-lg bg-slate-950 border border-slate-800 shrink-0">
            {renderIcon()}
          </div>
          <div className="min-w-0">
            <h3 className="text-xs font-bold text-white truncate group-hover:text-teal-300 transition-colors">
              {cluster.vendorName}
            </h3>
            <span className="text-[10px] text-slate-500 font-mono">
              {cluster.assets.length} {cluster.assets.length === 1 ? 'Item' : 'Items'}
            </span>
          </div>
        </div>

        <ChevronRight className="w-4 h-4 text-slate-600 group-hover:text-teal-400 transition-colors shrink-0" />
      </div>

      <div className="mt-4 pt-3 border-t border-slate-800/60 flex items-center justify-between font-mono">
        <div>
          <span className="text-[9px] text-slate-500 block uppercase tracking-wider">
            {metricLabel}
          </span>
          <span className="text-sm font-bold text-emerald-400 tabular-nums">
            {inrFormatter.format(cluster.totalValuation)}
          </span>
        </div>

        <span className="text-[10px] text-slate-400 group-hover:text-teal-300 font-bold flex items-center gap-1 transition-colors">
          <span>View Items</span>
          <ChevronRight className="w-3 h-3" />
        </span>
      </div>
    </div>
  );
};