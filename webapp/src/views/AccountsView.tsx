// src/views/AccountsView.tsx
import { type BankEntity, type AccountEntity } from '../types/ledger';
import { useAccountsCrud } from '../hooks/useAccountsCrud';

export default function AccountsView() {
  const {
    banks,
    accounts,
    accountName,
    setAccountName,
    accountType,
    setAccountType,
    ifscCode,
    setIfscCode,
    branchName,
    setBranchName,
    address,
    setAddress,
    selectedBankId,
    setSelectedBankId,
    
    // 🎯 NEW RELATION HOOKS: Wire these fields to track account_number values inside your useAccountsCrud hook!
    accountNumber,      // Make sure these are declared inside useAccountsCrud hook parameters
    setAccountNumber,   
    editAccountNumber,  
    setEditAccountNumber,

    editingId,
    setEditingId,
    editName,
    setEditName,
    editType,
    setEditType,
    editIfsc,
    setEditIfsc,
    editBranch,
    setEditBranch,
    editAddress,
    setEditAddress,
    loading,
    fetchLoading,
    message,
    handleAccountSubmit,
    handleUpdateAccount,
    handleDeleteAccount,
    startEditing
  } = useAccountsCrud(); 

  return (
    <div className="space-y-8 animate-fade-in">
      <div>
        <h2 className="text-2xl font-bold tracking-tight text-white">Financial Ledger Accounts</h2>
        <p className="text-sm text-zinc-400">Map precise corporate banking branch networks directly to core nodes.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Side Input Configuration Form */}
        <div className="lg:col-span-4 p-6 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl">
          <h3 className="text-base font-semibold text-white mb-6">Open Ledger Account Node</h3>
          <form onSubmit={handleAccountSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Parent Bank Entity</label>
              <select
                value={selectedBankId}
                onChange={(e) => setSelectedBankId(e.target.value)}
                className="w-full px-4 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-emerald-500 transition-colors"
                disabled={loading}
              >
                <option value="">-- Link Master Institution --</option>
                {banks.map((b: BankEntity) => (
                  <option key={b.id} value={b.id}>[{b.code}] {b.display_name}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Account Display Name</label>
              <input
                type="text"
                placeholder="e.g., Primary Savings AC"
                value={accountName}
                onChange={(e) => setAccountName(e.target.value)}
                className="w-full px-4 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-200 placeholder-zinc-700 focus:outline-none focus:border-emerald-500 transition-colors"
                disabled={loading}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1.5">Account Type</label>
                <select
                  value={accountType}
                  onChange={(e) => setAccountType(e.target.value)}
                  className="w-full px-4 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-emerald-500 transition-colors"
                  disabled={loading}
                >
                  <option value="ASSET">Asset</option>
                  <option value="LIABILITY">Liability</option>
                  <option value="EXPENSE">Expense</option>
                  <option value="INCOME">Income</option>
                </select>
              </div>
              
              {/* 🎯 ADDED TO FORM: 4-Digit Account Number Suffix field */}
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1.5">Account Suffix</label>
                <input
                  type="text"
                  maxLength={4}
                  placeholder="Last 4 Digits"
                  value={accountNumber}
                  onChange={(e) => setAccountNumber(e.target.value.replace(/\D/g, ''))}
                  className="w-full px-4 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-200 placeholder-zinc-700 focus:outline-none focus:border-emerald-500 transition-colors"
                  disabled={loading}
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">IFSC Code</label>
              <input
                type="text"
                maxLength={11}
                placeholder="SBIN0001234"
                value={ifscCode}
                onChange={(e) => setIfscCode(e.target.value)}
                className="w-full px-4 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-200 placeholder-zinc-700 focus:outline-none focus:border-emerald-500 transition-colors uppercase"
                disabled={loading}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Branch Name</label>
              <input
                type="text"
                placeholder="e.g., MG Road Branch"
                value={branchName}
                onChange={(e) => setBranchName(e.target.value)}
                className="w-full px-4 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-200 placeholder-zinc-700 focus:outline-none focus:border-emerald-500 transition-colors"
                disabled={loading}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Branch Address</label>
              <input
                type="text"
                placeholder="e.g., Ernakulam, Kerala"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                className="w-full px-4 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-200 placeholder-zinc-700 focus:outline-none focus:border-emerald-500 transition-colors"
                disabled={loading}
              />
            </div>

            {message.text && (
              <div className={`p-3.5 rounded-lg text-xs font-semibold ${message.type === 'success' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20'}`}>
                {message.text}
              </div>
            )}

            <button type="submit" disabled={loading} className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-sm rounded-lg shadow-lg transition-all">
              Link Account Node
            </button>
          </form>
        </div>

        {/* Right Side: Data Grid Panel Wrapper */}
        <div className="lg:col-span-8 p-6 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl min-h-[480px]">
          <h3 className="text-base font-semibold text-white mb-6 pb-3 border-b border-zinc-800">Active Ledger Accounts Matrix</h3>
          {fetchLoading ? (
            <p className="text-sm text-zinc-500 font-mono italic">Querying ledger indexes...</p>
          ) : accounts.length === 0 ? (
            <div className="p-12 text-center text-sm text-zinc-500 border border-dashed border-zinc-800 rounded-lg">No structural accounts linked yet.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-zinc-300 table-fixed">
                <thead>
                  <tr className="border-b border-zinc-800 text-zinc-500 font-mono text-xs">
                    <th className="pb-3 font-medium w-1/3">Ledger Node / Identity</th>
                    <th className="pb-3 font-medium w-1/6">Type</th>
                    <th className="pb-3 font-medium w-1/4">Routing / IFSC</th>
                    <th className="pb-3 font-medium w-1/4">Branch Details</th>
                    <th className="pb-3 font-medium text-right w-1/6">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/40 text-xs">
                  {accounts.map((acc: AccountEntity) => {
                    const linkedBank = banks.find((b: BankEntity) => b.id === acc.bank_id);
                    return (
                      <tr key={acc.id} className={`transition-colors group ${editingId === acc.id ? 'bg-zinc-950/60' : 'hover:bg-zinc-950/20'}`}>
                        
                        {/* NAME DISPLAY & SECURE SUFFIX MASK */}
                        <td className="py-4 pr-2">
                          {editingId === acc.id ? (
                            <div className="space-y-1">
                              <input type="text" value={editName} onChange={(e) => setEditName(e.target.value)} className="px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-xs text-white w-full focus:outline-none focus:border-emerald-500" placeholder="Display Name" />
                              {/* 🎯 ADDED TO INLINE EDITING: Sub-input to update account suffix number manually */}
                              <input type="text" maxLength={4} value={editAccountNumber} onChange={(e) => setEditAccountNumber(e.target.value.replace(/\D/g, ''))} className="px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-[11px] text-white w-full focus:outline-none focus:border-emerald-500" placeholder="Suffix (Last 4 digits)" />
                            </div>
                          ) : (
                            <div>
                              <div className="font-semibold text-zinc-200 truncate">
                                {/* 🎯 DISPLAY TWIST: Interpolates security masked 4-digit token inside structural list layout */}
                                {acc.name} {acc.account_number ? `(•••• ${acc.account_number})` : ''}
                              </div>
                              <div className="text-[10px] font-mono text-zinc-500 mt-0.5">
                                Bank: <span className="text-emerald-400 font-bold">{linkedBank ? linkedBank.display_name : 'Default Node'}</span>
                              </div>
                            </div>
                          )}
                        </td>

                        {/* ACCOUNT TYPE */}
                        <td className="py-4 pr-2">
                          {editingId === acc.id ? (
                            <select value={editType} onChange={(e) => setEditType(e.target.value)} className="px-1.5 py-1 bg-zinc-900 border border-zinc-700 rounded font-mono text-xs text-white w-full focus:outline-none focus:border-emerald-500">
                              <option value="ASSET">ASSET</option>
                              <option value="LIABILITY">LIABILITY</option>
                              <option value="EXPENSE">EXPENSE</option>
                              <option value="INCOME">INCOME</option>
                            </select>
                          ) : (
                            <span className={`px-2 py-0.5 border rounded text-[10px] font-bold font-mono tracking-wide ${acc.account_type === 'ASSET' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-amber-500/10 text-amber-400 border-amber-500/20'}`}>
                              {acc.account_type}
                            </span>
                          )}
                        </td>

                        {/* IFSC ROUTING CODE */}
                        <td className="py-4 pr-2 'hover:bg-zinc-950/20' font-mono text-zinc-300 uppercase truncate">
                          {editingId === acc.id ? (
                            <input type="text" maxLength={11} value={editIfsc} onChange={(e) => setEditIfsc(e.target.value)} className="px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-xs text-white uppercase w-full focus:outline-none focus:border-emerald-500" />
                          ) : (
                            acc.ifsc_code || '---'
                          )}
                        </td>

                        {/* BRANCH METRICS DETAILS */}
                        <td className="py-4 pr-2 text-zinc-400 truncate">
                          {editingId === acc.id ? (
                            <div className="space-y-1">
                              <input type="text" value={editBranch} onChange={(e) => setEditBranch(e.target.value)} className="px-2 py-0.5 bg-zinc-900 border border-zinc-700 rounded text-[11px] text-white w-full focus:outline-none" placeholder="Branch Name" />
                              <input type="text" value={editAddress} onChange={(e) => setEditAddress(e.target.value)} className="px-2 py-0.5 bg-zinc-900 border border-zinc-700 rounded text-[11px] text-white w-full focus:outline-none" placeholder="Address Location" />
                            </div>
                          ) : (
                            <div>
                              <div className="font-medium text-zinc-300 truncate">{acc.branch_name || 'Generic'}</div>
                              <div className="text-[11px] text-zinc-500 truncate max-w-[120px]">{acc.address}</div>
                            </div>
                          )}
                        </td>

                        {/* ACTION CALL MUTATIONS CONTROL HOOKS BUTTONS */}
                        <td className="py-4 text-right whitespace-nowrap">
                          {editingId === acc.id ? (
                            <div className="flex justify-end gap-1.5">
                              <button onClick={() => handleUpdateAccount(acc.id, acc.bank_id)} className="px-2 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs rounded transition-all">Save</button>
                              <button onClick={() => setEditingId(null)} className="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 font-medium text-xs rounded transition-all">Exit</button>
                            </div>
                          ) : (
                            <div className="flex justify-end gap-3 opacity-30 group-hover:opacity-100 transition-opacity">
                              <button onClick={() => startEditing(acc)} className="text-xs text-zinc-400 hover:text-sky-400 font-semibold">Edit</button>
                              <button onClick={() => handleDeleteAccount(acc.id, acc.name)} className="text-xs text-zinc-500 hover:text-red-400 font-medium">Purge</button>
                            </div>
                          )}
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