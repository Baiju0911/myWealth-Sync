import type { AppView } from '../../App.tsx';
// 🟢 Keep both legacy and dynamic components imported from your views index
import { MasterInstitutionsContainer, StatementIngestView, StatementIngestionNode,UniversalStatementIngestView } from '../../views'; 
import StatementMapper from '../mappers/StatementMapper.tsx'; 

interface ShellProps {
  currentView: AppView;
  setViewAction?: (view: AppView) => void; 
}

export default function DashboardShell({ currentView, setViewAction }: ShellProps) {
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

      case 'banks':
      case 'accounts':
      case 'credentials':
        return <MasterInstitutionsContainer />;

      case 'upload':
        // 💾 Standard manual upload view preserved here
        return <StatementIngestView />;

      case 'ingestDynamic':
        // ⚡ Smart automated template router view running independently
        return (
          <StatementIngestionNode 
            onRedirectToMapper={() => {
              if (setViewAction) {
                setViewAction('schemas');
              } else {
                console.warn("DashboardShell warning: setViewAction function callback dependency missing.");
              }
            }} 
          />
        );

      case 'ingestDynamicBulk':
        // ⚡ Smart automated template router view running independently
        return (
          <UniversalStatementIngestView />
        );

      case 'schemas':
        return <StatementMapper />; 

      default:
        return <MasterInstitutionsContainer />;
    }
  };

  return (
    <div className="w-full h-auto bg-zinc-950 pt-2 pb-16">
      <div className="w-full px-1"> 
        {renderViewContent()}
      </div>
    </div>
  );
}