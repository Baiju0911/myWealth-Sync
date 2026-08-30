import React from 'react';
import { type IngestStats } from '../../api/emailIngestApi';

interface Props {
  stats: IngestStats;
}

export const IngestStatsCards: React.FC<Props> = ({ stats }) => {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <div className="p-4 bg-slate-900/80 border border-slate-800 rounded-xl shadow-sm">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total Ingested</p>
        <p className="text-3xl font-bold text-slate-100 mt-1">{stats.total || 0}</p>
      </div>
      <div className="p-4 bg-slate-900/80 border border-slate-800 rounded-xl shadow-sm">
        <p className="text-xs font-semibold text-emerald-400 uppercase tracking-wider">Parsed Successfully</p>
        <p className="text-3xl font-bold text-emerald-400 mt-1">{stats.parsed || 0}</p>
      </div>
      <div className="p-4 bg-slate-900/80 border border-slate-800 rounded-xl shadow-sm">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Duplicates Skipped</p>
        <p className="text-3xl font-bold text-slate-300 mt-1">{stats.duplicate || 0}</p>
      </div>
      <div className="p-4 bg-slate-900/80 border border-slate-800 rounded-xl shadow-sm">
        <p className="text-xs font-semibold text-rose-400 uppercase tracking-wider">Flagged / Failed</p>
        <p className="text-3xl font-bold text-rose-400 mt-1">{stats.failed || 0}</p>
      </div>
    </div>
  );
};