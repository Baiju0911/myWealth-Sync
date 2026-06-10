// src/App.tsx
import { useState } from 'react';
import Sidebar from './components/navigation/Sidebar';
import DashboardShell from './components/dashboard/DashboardShell';

// 🔌 FIXED: Integrated 'upload' into the master app routing type matrix
export type AppView = 'summary' | 'banks' | 'accounts' | 'upload' | 'credentials' | 'schemas';

export default function App() {
  // Application view router state tracking index initialized to 'summary'
  const [currentView, setCurrentView] = useState<AppView>('summary');

  return (
    <div className="flex w-screen h-screen bg-zinc-950 text-zinc-100 antialiased overflow-hidden selection:bg-emerald-500/30 select-none">
      
      {/* 🧭 Left Hand Menu Navigation Strip */}
      <Sidebar currentView={currentView} setCurrentView={setCurrentView} />

      {/* 💻 Right Hand Live Data Panel Viewport Shell */}
      <main className="flex-1 h-full overflow-y-auto">
        <DashboardShell currentView={currentView} />
      </main>
      
    </div>
  );
}