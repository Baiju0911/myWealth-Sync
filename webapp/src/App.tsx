import { useState } from 'react';
import Sidebar from './components/navigation/Sidebar';
import DashboardShell from './components/dashboard/DashboardShell';

export type AppView = 'summary' | 'banks' | 'accounts' | 'upload' | 'credentials' | 'schemas'| 'ingestDynamic'| 'ingestDynamicBulk';

export default function App() {
  const [currentView, setCurrentView] = useState<AppView>('summary');

  return (
    // Explicit horizontal row grid that spans the absolute monitor framework
    <div 
      className="flex flex-row w-screen h-screen bg-zinc-950 text-zinc-100 antialiased overflow-hidden selection:bg-emerald-500/30 select-none"
      style={{ display: 'flex', flexDirection: 'row', width: '100vw', height: '100vh', overflow: 'hidden' }}
    >
      
      {/* 🧭 Left Hand Column Lane: Collapsible Sidebar Menu Panel */}
      <Sidebar currentView={currentView} setCurrentView={setCurrentView} />

      {/* 💻 Right Hand Column Viewport: THE MAIN BODY CANVAS PANEL */}
      <main 
        className="flex-1 min-w-0 h-full overflow-y-auto bg-zinc-950 pl-4 py-2 pr-2" // 🟢 Added pl-4 to push it right, overflow-y-auto for the scrollbar
        style={{ 
          flex: 1, 
          minWidth: 0, 
          height: '100%', 
          display: 'flex', 
          flexDirection: 'column', 
          overflowY: 'auto', // 🚀 Unlocks the clean native vertical workspace scrollbar tracks
          paddingLeft: '24px' // 🚀 Enforces an explicit 24px structural air gap pushing it rightward
        }}
      >
        <DashboardShell currentView={currentView} />
      </main>
      
    </div>
  );
}