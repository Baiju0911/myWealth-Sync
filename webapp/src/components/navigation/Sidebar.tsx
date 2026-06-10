import { useState } from 'react';
import type { AppView } from '../../App'; 

interface SidebarProps {
  currentView: AppView;
  setCurrentView: (view: AppView) => void;
}

export default function Sidebar({ currentView, setCurrentView }: SidebarProps) {
  const [isCollapsed, setIsCollapsed] = useState<boolean>(false);

  const menuItems: { id: AppView; label: string; icon: string }[] = [
    { id: 'summary', label: 'Financial Summary', icon: '📊' },
    { id: 'banks', label: 'Institutions Matrix', icon: '🏛️' }, 
    { id: 'ingestDynamicBulk', label: 'Universal Statement Ingestion [NEW]', icon: '📂' },
    { id: 'upload', label: 'Statement Ingestion [Legacy]', icon: '📂' },
    { id: 'ingestDynamic', label: 'Statement Ingestion Dynamic [Testing]', icon: '📂' },
    { id: 'schemas', label: 'Mapping Schemas', icon: '📋' }, 
  ];

  return (
    <aside 
      className={`bg-zinc-900 border-r border-zinc-800 flex flex-col h-screen text-zinc-100 shrink-0 transition-all duration-300 relative select-none ${
        isCollapsed ? 'w-16' : 'w-64'
      }`}
      style={{ display: 'flex', flexDirection: 'column' }} // 👈 Inline safety override against global CSS contamination
    >
      
      {/* 🛠️ CONTROLLER BUTTON */}
      <button
        onClick={() => setIsCollapsed(!isCollapsed)}
        className="absolute -right-3 top-6 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 w-6 h-6 rounded-full flex items-center justify-center text-xs shadow-md z-50 transition-colors cursor-pointer"
        title={isCollapsed ? "Expand Sidebar Workspace" : "Collapse Sidebar Workspace"}
      >
        {isCollapsed ? '→' : '←'}
      </button>

      {/* Platform Branding Header */}
      <div 
        className={`border-b border-zinc-800 flex items-center gap-3 overflow-hidden ${isCollapsed ? 'justify-center p-4' : 'p-6'}`}
        style={{ display: 'flex', alignItems: 'center' }}
      >
        <span className="text-xl shrink-0">💰</span>
        {!isCollapsed && (
          <div className="animate-fade-in text-left">
            <h1 className="font-bold text-sm tracking-tight text-white whitespace-nowrap m-0 leading-none" style={{ fontSize: '14px', margin: 0 }}>myWealth-Sync</h1>
            <p className="text-[10px] text-zinc-500 font-mono m-0 mt-0.5" style={{ margin: 0 }}>v1.0 (MySQL)</p>
          </div>
        )}
      </div>

      {/* Dynamic Navigation Tabs Ribbons */}
      <nav 
        className="flex-1 p-2.5 space-y-1.5 overflow-y-auto w-full flex flex-col" 
        style={{ display: 'flex', flexDirection: 'column', gap: '6px' }} // 👈 Guarantees elements stack vertically down the lane
      >
        {menuItems.map((item) => {
          const isActive = 
            currentView === item.id || 
            (item.id === 'banks' && (currentView === 'accounts' || currentView === 'credentials'));

          return (
            <button
              key={item.id}
              onClick={() => setCurrentView(item.id)}
              title={isCollapsed ? item.label : undefined}
              className={`w-full flex items-center rounded-lg text-xs font-medium transition-all duration-200 cursor-pointer ${
                isCollapsed ? 'justify-center p-3 gap-0' : 'px-4 py-2.5 gap-3 justify-start text-left'
              } ${
                isActive
                  ? 'bg-emerald-600 text-white shadow-md shadow-emerald-900/20'
                  : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
              }`}
              style={{ display: 'flex', alignItems: 'center', textAlign: 'left' }}
            >
              <span className="text-base shrink-0" style={{ display: 'inline-block' }}>{item.icon}</span>
              {!isCollapsed && (
                <span className="truncate animate-fade-in text-[13px] font-sans" style={{ display: 'inline-block' }}>
                  {item.label}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* User Context Profile Footer */}
      <div 
        className={`p-3 border-t border-zinc-800 bg-zinc-950/40 flex items-center gap-3 overflow-hidden ${isCollapsed ? 'justify-center' : ''}`}
        style={{ display: 'flex', alignItems: 'center' }}
      >
        <div className="w-7 h-7 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400 font-bold text-xs shrink-0">
          AT
        </div>
        {!isCollapsed && (
          <div className="truncate animate-fade-in text-left">
            <p className="text-xs font-semibold text-zinc-300 truncate m-0" style={{ margin: 0 }}>Alpha Tester</p>
            <p className="text-[9px] text-zinc-500 font-mono truncate m-0" style={{ margin: 0 }}>testowner@wealth.com</p>
          </div>
        )}
      </div>
      
    </aside>
  );
}