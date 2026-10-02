import React from 'react';

interface MetricProps {
  label: string;
  leftVal: string | number;
  rightVal: string | number;
  leftColor: string;
  rightColor: string;
  accentColor: string;
}

const TickerItem: React.FC<MetricProps> = ({ label, leftVal, rightVal, leftColor, rightColor, accentColor }) => (
  <div className="relative py-2 px-3 pl-3.5 bg-zinc-900/90 border border-zinc-800 rounded-lg min-w-32.5">
    <div className="absolute left-0 top-0 h-full w-1 rounded-l" style={{ backgroundColor: accentColor }} />
    <div className="text-zinc-400 text-[9px] font-bold font-mono uppercase tracking-wider">{label}</div>
    <div className="text-[11px] font-mono mt-0.5">
      <span className={leftColor}>{leftVal}</span> · <span className={rightColor}>{rightVal}</span>
    </div>
  </div>
);

export const PipelineMetricsHeader: React.FC<{ matrixStats: any; totalNodes: number; isAudited: boolean }> = ({
  matrixStats,
  totalNodes,
  isAudited,
}) => {
  return (
    <div className={`p-4 rounded-xl border flex flex-col md:flex-row justify-between items-start md:items-center gap-4 transition-all ${
      isAudited ? "border-emerald-500/30 bg-emerald-950/10" : "border-rose-500/30 bg-rose-950/10"
    }`}>
      <div>
        <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-400">Pipeline Balance Status</div>
        <h2 className="text-sm md:text-base font-bold tracking-tight mt-0.5 whitespace-nowrap">
          Staged For Bulk High Clearance: <span className="text-emerald-400 font-mono">{totalNodes} Nodes Passed</span>
        </h2>
      </div>

      <div className="flex flex-row gap-2 flex-wrap items-center">
        <TickerItem 
          label="T1 System Rules" 
          leftVal={`M:${matrixStats.t1_system?.real || 0}`} 
          rightVal={`S:${matrixStats.t1_system?.suspense || 0}`} 
          leftColor="text-emerald-400" 
          rightColor="text-amber-400" 
          accentColor="#3b82f6" 
        />
        <TickerItem 
          label="T2 Transfer Tunnels" 
          leftVal={`I:${matrixStats.t2_internal?.real || 0}`} 
          rightVal={`N:${matrixStats.t2_internal?.suspense || 0}`} 
          leftColor="text-emerald-400" 
          rightColor="text-zinc-400" 
          accentColor="#a855f7" 
        />
        <TickerItem 
          label="T3 Ledger Mappings" 
          leftVal={`M:${matrixStats.t3_layout?.real || 0}`} 
          rightVal={`S:${matrixStats.t3_layout?.suspense || 0}`} 
          leftColor="text-emerald-400" 
          rightColor="text-amber-400" 
          accentColor="#06b6d4" 
        />
        <TickerItem 
          label="T4 Master Rulebook" 
          leftVal={`A:${matrixStats.t4_rulebook?.real || 0}`} 
          rightVal={`F:${matrixStats.t4_rulebook?.suspense || 0}`} 
          leftColor="text-yellow-400" 
          rightColor="text-cyan-400" 
          accentColor="#eab308" 
        />
        <TickerItem 
          label="T5 Local AI Memory" 
          leftVal={`V:${matrixStats.t5_ai?.real || totalNodes}`} 
          rightVal={`S:${matrixStats.t5_ai?.suspense || 0}`} 
          leftColor="text-emerald-400" 
          rightColor="text-purple-400" 
          accentColor="#10b981" 
        />
      </div>
    </div>
  );
};