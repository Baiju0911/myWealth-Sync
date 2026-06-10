// src/views/CredentialsView.tsx
import { useCredentialsCrud } from '../hooks/useCredentialsCrud';
import type { AccountEntity, CredentialEntity } from '../types/ledger';

export default function CredentialsView() {
  const {
    banks, 
    accounts, 
    credentials,
    selectedAccountId,    
    setSelectedAccountId, 
    passwordKey,
    setPasswordKey,
    loading,
    fetchLoading,
    message,
    handleCredSubmit,
    handleDeleteCred
  } = useCredentialsCrud(); 

  // 🎯 UNIFIED CONTROLLER EDIT ROUTER:
  // Pre-fills the main form on the left with the selected row's data.
  // This automatically uses your main smart upsert engine when you click Save!
  const loadProfileIntoForm = (cred: CredentialEntity) => {
    setSelectedAccountId(cred.account_id);
    setPasswordKey(''); // Clear out to let them type the fresh passphrase variant
    
    // Smooth scroll back to form view on mobile devices if needed
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className="space-y-8 animate-fade-in">
      <div>
        <h2 className="text-2xl font-bold tracking-tight text-white">Secure Statement Password Vault</h2>
        <p className="text-sm text-zinc-400">Lock down statement verification and decryption passphrases for individual ledger nodes.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        
        {/* Left Side: Create/Update Master Input Form */}
        <div className="lg:col-span-4 p-6 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl sticky top-6">
          <h3 className="text-base font-semibold text-white mb-6">Store Profile Vault Key</h3>
          <form onSubmit={handleCredSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Target Account Ledger Node</label>
              <select
                value={selectedAccountId}
                onChange={(e) => setSelectedAccountId(e.target.value)}
                className="w-full px-4 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-emerald-500 transition-colors"
                disabled={loading}
              >
                <option value="">-- Choose Account Profile --</option>
                {accounts.map((acc: AccountEntity) => {
                  const parentBank = banks.find(b => b.id === acc.bank_id);
                  return (
                    <option key={acc.id} value={acc.id}>
                      {acc.name} {acc.account_number ? `(•••• ${acc.account_number})` : ''} [{parentBank ? parentBank.code : 'GENERIC'}]
                    </option>
                  );
                })}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Decryption Passphrase</label>
              <input
                type="password"
                placeholder="••••••••••••"
                value={passwordKey}
                onChange={(e) => setPasswordKey(e.target.value)}
                className="w-full px-4 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-200 placeholder-zinc-700 focus:outline-none focus:border-emerald-500 transition-colors"
                disabled={loading}
              />
              <p className="text-[10px] text-zinc-500 mt-1.5 leading-relaxed">
                💡 Entering a new passphrase will automatically append it to the **very top** of this account's decryption vault loop.
              </p>
            </div>

            {message.text && (
              <div className={`p-3.5 rounded-lg text-xs font-semibold ${message.type === 'success' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20'}`}>
                {message.text}
              </div>
            )}

            <button type="submit" disabled={loading} className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:bg-zinc-800 text-white font-medium text-sm rounded-lg shadow-lg transition-all mt-2">
              {loading ? 'Securing Core Keys...' : 'Secure Configuration Key'}
            </button>
          </form>
        </div>

        {/* Right Side: Read, Track, and Purge Layout Table */}
        <div className="lg:col-span-8 p-6 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl min-h-[440px]">
          <h3 className="text-base font-semibold text-white mb-6 pb-3 border-b border-zinc-800">Active Mapped Credentials Enclaves</h3>

          {fetchLoading ? (
            <p className="text-sm text-zinc-500 font-mono italic">Scanning relational database lines...</p>
          ) : credentials.length === 0 ? (
            <div className="p-12 text-center text-sm text-zinc-500 border border-dashed border-zinc-800 rounded-lg">No verification credentials mapped to this system workspace profile yet.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-zinc-300 table-fixed">
                <thead>
                  <tr className="border-b border-zinc-800 text-zinc-500 font-mono text-xs">
                    <th className="pb-3 font-medium w-7/12">Linked Ledger Account Target</th>
                    <th className="pb-3 font-medium w-3/12">Decryption Pass</th>
                    <th className="pb-3 font-medium text-right w-2/12">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/30">
                  {credentials.map((cred: CredentialEntity) => {
                    const linkedAccount = accounts.find(a => a.id === cred.account_id);
                    const linkedBank = linkedAccount ? banks.find(b => b.id === linkedAccount.bank_id) : null;
                    
                    return (
                      <tr key={cred.id} className="transition-colors group hover:bg-zinc-950/20">
                        
                        {/* DETAILS / ACC NUMBER COLUMN */}
                        <td className="py-4 pr-2">
                          <div>
                            <div className="font-semibold text-zinc-200 truncate">
                              {linkedAccount ? linkedAccount.name : 'Unknown Account Profile'} 
                              {linkedAccount?.account_number ? ` (•••• ${linkedAccount.account_number})` : ''}
                            </div>
                            <div className="text-[10px] font-mono text-zinc-500 mt-0.5">
                              Institution: <span className="text-emerald-400 font-bold">{linkedBank ? linkedBank.display_name : 'Default'}</span>
                              {linkedAccount?.ifsc_code && ` • IFSC: ${linkedAccount.ifsc_code}`}
                            </div>
                          </div>
                        </td>

                        {/* STATUS BADGE COLUMN */}
                        <td className="py-4 pr-2">
                          <span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded font-mono text-[10px] font-bold tracking-wider">
                            AES_256 SECURE
                          </span>
                        </td>

                        {/* ACTIONS COLUMN */}
                        <td className="py-4 text-right whitespace-nowrap">
                          <div className="flex justify-end gap-4 opacity-40 group-hover:opacity-100 transition-opacity">
                            <button 
                              onClick={() => loadProfileIntoForm(cred)} 
                              className="text-xs text-zinc-400 hover:text-emerald-400 font-semibold transition-colors"
                            >
                              Edit
                            </button>
                            <button 
                              onClick={() => handleDeleteCred(cred.id, linkedAccount ? `${linkedAccount.name} (${linkedAccount.account_number || '####'})` : 'this profile')} 
                              className="text-xs text-zinc-500 hover:text-red-400 font-medium transition-colors"
                            >
                              Purge
                            </button>
                          </div>
                        </td>

                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}