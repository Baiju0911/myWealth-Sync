// src/components/dashboard/DashboardShell.tsx
import type { AppView } from '../../App.tsx';
import { MasterInstitutionsContainer, StatementIngestView } from '../../views'; 


interface ShellProps {
  currentView: AppView;
}

export default function DashboardShell({ currentView }: ShellProps) {
  // 🧭 The Engine Resolver maps the active token to a dedicated viewport module
  const renderViewContent = () => {
    switch (currentView) {
      case 'summary':
        return (
          <div className="space-y-6 animate-fade-in">
            <div>
              <h2 className="text-2xl font-bold tracking-tight text-white">Financial Summary Overview</h2>
              <p className="text-sm text-zinc-400">High-precision double-entry checking log balances.</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="p-6 bg-zinc-900 border border-zinc-800 rounded-xl">
                <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Base Currency</p>
                <p className="text-2xl font-bold text-zinc-100 mt-2">INR (₹)</p>
              </div>
              <div className="p-6 bg-zinc-900 border border-zinc-800 rounded-xl">
                <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">System Balancing State</p>
                <p className="text-2xl font-bold text-emerald-400 mt-2">Balanced (0.00)</p>
              </div>
            </div>
          </div>
        );

      // 🏛️ Unified Landing Dock for all corporate relational layouts
      case 'banks':
      case 'accounts':
      case 'credentials':
        return <MasterInstitutionsContainer />;

      case 'upload':
        return <StatementIngestView />;

      case 'schemas':
        return (
          <div className="p-12 text-center text-sm text-zinc-500 border border-dashed border-zinc-800 rounded-lg">
            📋 Layout structural mapping schemas layer.
          </div>
        );

      default:
        return <MasterInstitutionsContainer />;
    }
  };

  return (
    <div className="w-full h-full p-8 bg-zinc-950 overflow-y-auto">
      <div className="max-w-7xl mx-auto">
        {renderViewContent()}
      </div>
    </div>
  );
}