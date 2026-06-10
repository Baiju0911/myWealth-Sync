// src/views/MasterInstitutionsContainer.tsx
import { useState } from 'react';
import BanksView from './BanksView.tsx';
import AccountsView from './AccountsView';
import CredentialsView from './CredentialsView';

type SubTab = 'hub' | 'ledgers' | 'vault';

export default function MasterInstitutionsContainer() {
  const [activeTab, setActiveTab] = useState<SubTab>('hub');

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header Profile Context */}
      <div>
        <h2 className="text-2xl font-bold tracking-tight text-white">Institutions Matrix</h2>
        <p className="text-sm text-zinc-400">Manage master registries, link ledger branch nodes, and configure credential vaults.</p>
      </div>

      {/* 🧭 High-End Custom Sub-Tab Strip */}
      <div className="flex border-b border-zinc-800 space-x-1 p-1 bg-zinc-900/40 rounded-xl max-w-md">
        <button
          onClick={() => setActiveTab('hub')}
          className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all ${
            activeTab === 'hub' ? 'bg-zinc-800 text-emerald-400 shadow-md' : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          🏛️ Master Hub
        </button>
        <button
          onClick={() => setActiveTab('ledgers')}
          className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all ${
            activeTab === 'ledgers' ? 'bg-zinc-800 text-emerald-400 shadow-md' : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          💳 Linked Ledger ACs
        </button>
        <button
          onClick={() => setActiveTab('vault')}
          className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all ${
            activeTab === 'vault' ? 'bg-zinc-800 text-emerald-400 shadow-md' : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          🔐 Pass Vault
        </button>
      </div>

      {/* 🔮 Dynamic Viewport Swapper Engine */}
      <div className="pt-2">
        {activeTab === 'hub' && <BanksView />}
        {activeTab === 'ledgers' && <AccountsView />}
        {activeTab === 'vault' && <CredentialsView />}
      </div>
    </div>
  );
}