// src/views/BanksView.tsx
import { useBanksCrud } from '../hooks/useBanksCrud';
import type { BankEntity } from '../types/ledger';

export default function BanksView() {
  const {
    banks,
    displayName,
    setDisplayName,
    code,
    setCode,
    editingId,
    editName,
    setEditName,
    editCode,
    setEditCode,
    loading,
    fetchLoading,
    message,
    fetchBalancesMatrix,
    handleBankSubmit,
    handleUpdateBank,
    handleDeleteBank,
    startEditing,
    cancelEditing,
  } = useBanksCrud();

  return (
    <div className="space-y-8 animate-fade-in">
      <div>
        <h2 className="text-2xl font-bold tracking-tight text-white">Master Institutional Registries</h2>
        <p className="text-sm text-zinc-400">Anchor central corporate configurations for ledger nodes.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Form (CREATE) */}
        <div className="lg:col-span-4 p-6 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl">
          <h3 className="text-base font-semibold text-white mb-6">Add Master Bank Entity</h3>
          <form onSubmit={handleBankSubmit} className="space-y-5">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-2">Bank Display Name</label>
              <input
                type="text"
                placeholder="e.g., State Bank of India"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="w-full px-4 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-emerald-500 transition-colors"
                disabled={loading}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-2">Unique System Code</label>
              <input
                type="text"
                placeholder="e.g., SBI"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="w-full px-4 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-emerald-500 transition-colors"
                disabled={loading}
              />
            </div>

            {message.text && (
              <div className={`p-3.5 rounded-lg text-xs font-semibold ${message.type === 'success' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20'}`}>
                {message.text}
              </div>
            )}

            <button type="submit" disabled={loading} className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-sm rounded-lg transition-all shadow-md">
              Register Anchor Node
            </button>
          </form>
        </div>

        {/* Right Data Grid (READ, UPDATE, DELETE) */}
        <div className="lg:col-span-8 p-6 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl min-h-[400px]">
          <div className="flex justify-between items-center mb-6 pb-3 border-b border-zinc-800">
            <h3 className="text-base font-semibold text-white">Active Configurations ({banks.length})</h3>
            <button onClick={fetchBalancesMatrix} className="px-3 py-1.5 text-xs bg-zinc-950 hover:bg-zinc-800 border border-zinc-800 text-zinc-400 rounded-md transition-all">
              🔄 Sync Matrix
            </button>
          </div>

          {fetchLoading ? (
            <p className="text-sm text-zinc-500 font-mono italic">Scanning relational database lines...</p>
          ) : banks.length === 0 ? (
            <div className="p-12 text-center text-sm text-zinc-500 border border-dashed border-zinc-800 rounded-lg">No tracking structures declared.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-zinc-300 table-fixed">
                <thead>
                  <tr className="border-b border-zinc-800 text-zinc-500 font-mono text-xs">
                    <th className="pb-3 font-medium w-1/4">Code</th>
                    <th className="pb-3 font-medium w-5/12">Institution Identity</th>
                    <th className="pb-3 font-medium text-center w-1/6">Linked Items</th>
                    <th className="pb-3 font-medium text-right w-1/6">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/40">
                  {/* 🎯 FIXED: Strongly typed runtime mapping context loop */}
                  {banks.map((bank: BankEntity) => (
                    <tr key={bank.id} className={`transition-colors group ${editingId === bank.id ? 'bg-zinc-950/60' : 'hover:bg-zinc-950/20'}`}>
                      
                      {/* CODE PANEL */}
                      <td className="py-4 pr-2">
                        {editingId === bank.id ? (
                          <input
                            type="text"
                            value={editCode}
                            onChange={(e) => setEditCode(e.target.value)}
                            className="px-2 py-1.5 bg-zinc-900 border border-zinc-700 rounded font-mono text-xs text-white uppercase w-full focus:outline-none focus:border-emerald-500"
                          />
                        ) : (
                          <span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-400 rounded text-xs font-bold font-mono border border-emerald-500/10">
                            {bank.code}
                          </span>
                        )}
                      </td>

                      {/* DISPLAY NAME PANEL */}
                      <td className="py-4 pr-2 font-medium text-zinc-200 truncate">
                        {editingId === bank.id ? (
                          <input
                            type="text"
                            value={editName}
                            onChange={(e) => setEditName(e.target.value)}
                            className="px-2 py-1.5 bg-zinc-900 border border-zinc-700 rounded text-xs text-white w-full focus:outline-none focus:border-emerald-500"
                          />
                        ) : (
                          bank.display_name
                        )}
                      </td>

                      {/* CONNECTIONS METRICS COUNTERS */}
                      <td className="py-4 text-center">
                        <div className="flex items-center justify-center gap-1.5 font-mono text-[11px]">
                          <span className="px-1.5 py-0.5 bg-zinc-950/80 border border-zinc-800 rounded text-zinc-400">
                            💳 {bank.account_count}
                          </span>
                          <span className="px-1.5 py-0.5 bg-zinc-950/80 border border-zinc-800 rounded text-zinc-400">
                            🔑 {bank.credential_count}
                          </span>
                        </div>
                      </td>

                      {/* ACTIONS COLUMNS */}
                      <td className="py-4 text-right whitespace-nowrap">
                        {editingId === bank.id ? (
                          <div className="flex justify-end gap-2">
                            <button onClick={() => handleUpdateBank(bank.id)} className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs rounded shadow transition-all">
                              Save
                            </button>
                            <button onClick={cancelEditing} className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 font-medium text-xs rounded transition-all">
                              Exit
                            </button>
                          </div>
                        ) : (
                          <div className="flex justify-end gap-3 opacity-30 group-hover:opacity-100 transition-opacity">
                            <button onClick={() => startEditing(bank)} className="text-xs text-zinc-400 hover:text-sky-400 font-semibold transition-colors">
                              Edit
                            </button>
                            <button onClick={() => handleDeleteBank(bank.id, bank.display_name)} className="text-xs text-zinc-500 hover:text-red-400 font-medium transition-colors">
                              Purge
                            </button>
                          </div>
                        )}
                      </td>

                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}