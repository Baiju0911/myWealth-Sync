// src/components/navigation/Sidebar.tsx
import type { AppView } from '../../App'; // 🔌 Import the unified View Type from your root

interface SidebarProps {
  currentView: AppView;
  setCurrentView: (view: AppView) => void;
}

export default function Sidebar({ currentView, setCurrentView }: SidebarProps) {
  // 🗺️ CLEANED UP: Only keeping top-level, unique layout modules here
  const menuItems: { id: AppView; label: string; icon: string }[] = [
    { id: 'summary', label: 'Financial Summary', icon: '📊' },
    { id: 'banks', label: 'Institutions Matrix', icon: '🏛️' }, // 🏛️ Master entry wrapper for banks, accounts, & keys
    { id: 'upload', label: 'Statement Ingestion', icon: '📂' },
  ];

  return (
    <aside className="w-64 bg-zinc-900 border-r border-zinc-800 flex flex-col h-screen text-zinc-100 shrink-0">
      
      {/* Platform Branding Header */}
      <div className="p-6 border-b border-zinc-800 flex items-center gap-3">
        <span className="text-2xl">💰</span>
        <div>
          <h1 className="font-bold text-lg tracking-tight text-white">myWealth-Sync</h1>
          <p className="text-xs text-zinc-500 font-mono">v1.0 (MySQL Live)</p>
        </div>
      </div>

      {/* Dynamic Navigation Ribbons/Tabs */}
      <nav className="flex-1 p-4 space-y-2 overflow-y-auto">
        {menuItems.map((item) => {
          // 🎯 FIXED HIGHLIGHT LOGIC: Keep the "Institutions Matrix" active if sub-tabs are chosen
          const isActive = 
            currentView === item.id || 
            (item.id === 'banks' && (currentView === 'accounts' || currentView === 'credentials'));

          return (
            <button
              key={item.id}
              onClick={() => setCurrentView(item.id)}
              className={`w-full flex items-center gap-4 px-4 py-3 rounded-lg text-sm font-medium transition-all duration-200 ${
                isActive
                  ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-900/30'
                  : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
              }`}
            >
              <span className="text-lg">{item.icon}</span>
              {item.label}
            </button>
          );
        })}
      </nav>

      {/* User Context Footer (Hardcoded tracking data matches our seed user profile token) */}
      <div className="p-4 border-t border-zinc-800 bg-zinc-950/50 flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400 font-bold text-xs shrink-0">
          AT
        </div>
        <div className="truncate">
          <p className="text-xs font-semibold text-zinc-200 truncate">Alpha Tester</p>
          <p className="text-[10px] text-zinc-500 font-mono truncate">testowner@wealth.com</p>
        </div>
      </div>
      
    </aside>
  );
}