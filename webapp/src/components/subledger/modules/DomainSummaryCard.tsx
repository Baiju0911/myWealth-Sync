import React from 'react';
import type { AssetCategoryGroup } from '../helper/subledgerGrouping';
import { inrFormatter } from '../../../utils/classificationHelpers';
import {
  ChevronRight,
  Wallet,
  Building2,
  Coins,
  ShieldCheck,
  Landmark,
  PiggyBank,
  Layers,
} from 'lucide-react';

interface DomainSummaryCardProps {
  group: AssetCategoryGroup;
  metricLabel: string;
  onClick: () => void;
}

export const DomainSummaryCard: React.FC<DomainSummaryCardProps> = ({
  group,
  metricLabel,
  onClick,
}) => {
  const isCash = group.isCashDomain;
  const metricTitle = isCash ? 'FLOAT BALANCE' : metricLabel;

  const renderIcon = () => {
    if (isCash) return <Wallet className="w-4 h-4 text-emerald-400" />;
    const title = group.groupTitle.toLowerCase();
    if (title.includes('real estate') || title.includes('land')) {
      return <Building2 className="w-4 h-4 text-blue-400" />;
    }
    if (title.includes('gold') || title.includes('metal')) {
      return <Coins className="w-4 h-4 text-amber-400" />;
    }
    if (title.includes('insurance')) {
      return <ShieldCheck className="w-4 h-4 text-cyan-400" />;
    }
    if (title.includes('deposit')) {
      return <Landmark className="w-4 h-4 text-teal-400" />;
    }
    if (title.includes('pension') || title.includes('retirement')) {
      return <PiggyBank className="w-4 h-4 text-violet-400" />;
    }
    return <Layers className="w-4 h-4 text-slate-400" />;
  };

  return (
    <div
      onClick={onClick}
      className="bg-slate-900/70 border border-slate-800 hover:border-slate-700 hover:bg-slate-900/90 rounded-xl p-4 transition-all cursor-pointer flex flex-col justify-between group shadow-sm hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="p-2 rounded-lg bg-slate-950 border border-slate-800 shrink-0">
            {renderIcon()}
          </div>
          <div className="min-w-0">
            <h3 className="text-xs font-bold text-white truncate group-hover:text-emerald-400 transition-colors">
              {group.groupTitle}
            </h3>
            <span className="text-[10px] text-slate-500 font-mono">
              {group.totalNodeCount} {group.totalNodeCount === 1 ? 'Folio' : 'Folios'}
            </span>
          </div>
        </div>

        <ChevronRight className="w-4 h-4 text-slate-600 group-hover:text-emerald-400 transition-colors shrink-0" />
      </div>

      <div className="mt-4 pt-3 border-t border-slate-800/60 flex items-center justify-between font-mono">
        <div>
          <span className="text-[9px] text-slate-500 block uppercase tracking-wider">
            {metricTitle}
          </span>
          <span className="text-sm font-bold text-emerald-400 tabular-nums">
            {inrFormatter.format(group.totalValuation)}
          </span>
        </div>

        <span className="text-[10px] text-slate-400 group-hover:text-slate-200 font-bold flex items-center gap-1 transition-colors">
          <span>Open</span>
          <ChevronRight className="w-3 h-3" />
        </span>
      </div>
    </div>
  );
};