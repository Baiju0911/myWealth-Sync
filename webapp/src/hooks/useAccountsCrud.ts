// src/hooks/useAccountsCrud.ts
import { useState, useEffect } from 'react';
import { type BankEntity, type AccountEntity } from '../types/ledger';
import { accountApi, bankApi } from '../api';

export function useAccountsCrud() {
  const [banks, setBanks] = useState<BankEntity[]>([]);
  const [accounts, setAccounts] = useState<AccountEntity[]>([]);

  const [accountName, setAccountName] = useState('');
  const [accountType, setAccountType] = useState('ASSET');

  // 🎯 NEW: Creation Form State tracking your 4-digit token
  const [accountNumber, setAccountNumber] = useState('');

  const [ifscCode, setIfscCode] = useState('');
  const [branchName, setBranchName] = useState('');
  const [address, setAddress] = useState('');
  const [selectedBankId, setSelectedBankId] = useState('');

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editType, setEditType] = useState('ASSET');

  // 🎯 NEW: Inline Editing Form State tracking your 4-digit token updates
  const [editAccountNumber, setEditAccountNumber] = useState('');

  const [editIfsc, setEditIfsc] = useState('');
  const [editBranch, setEditBranch] = useState('');
  const [editAddress, setEditAddress] = useState('');

  const [loading, setLoading] = useState(false);
  const [fetchLoading, setFetchLoading] = useState(true);
  const [message, setMessage] = useState({ type: '', text: '' });

  const loadDataMatrix = async () => {
    setFetchLoading(true);
    try {
      const [banksData, accountsData] = await Promise.all([
        bankApi.getBanks(),
        accountApi.getAccounts(),
      ]);
      setBanks(Array.isArray(banksData) ? banksData : banksData.results || []);
      setAccounts(
        Array.isArray(accountsData) ? accountsData : accountsData.results || []
      );
    } catch (err) {
      console.error(err);
      setMessage({
        type: 'error',
        text: 'Pipeline breakdown tracking configurations.',
      });
    } finally {
      setFetchLoading(false);
    }
  };

  useEffect(() => {
    loadDataMatrix();
  }, []);

  const handleAccountSubmit = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (!accountName.trim() || !selectedBankId) {
      setMessage({
        type: 'error',
        text: 'Account Name and Parent Bank are required.',
      });
      return;
    }
    setLoading(true);
    setMessage({ type: '', text: '' });

    try {
      // 🚀 PAYLOAD UPDATE: Passes account_number to the backend create layer
      const data = await accountApi.createAccount({
        name: accountName.trim(),
        account_type: accountType,
        account_number: accountNumber.trim(),
        ifsc_code: ifscCode.trim().toUpperCase(),
        branch_name: branchName.trim(),
        address: address.trim(),
        bank_id: selectedBankId,
      });

      setMessage({
        type: 'success',
        text: `Successfully mapped: ${data.name}`,
      });

      setAccountName('');
      setAccountNumber(''); // Clear input string field upon success
      setIfscCode('');
      setBranchName('');
      setAddress('');
      setAccounts((prev) => [data, ...prev]);
    } catch {
      setMessage({ type: 'error', text: 'Validation failure.' });
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateAccount = async (id: string, bankId: string) => {
    if (!editName.trim()) return;
    setLoading(true);
    try {
      // 🚀 PAYLOAD UPDATE: Passes editAccountNumber to the backend update layer
      const data = await accountApi.updateAccount(id, {
        name: editName.trim(),
        account_type: editType,
        account_number: editAccountNumber.trim(),
        ifsc_code: editIfsc.trim().toUpperCase(),
        branch_name: editBranch.trim(),
        address: editAddress.trim(),
        bank_id: bankId,
      });

      setAccounts((prev) =>
        prev.map((a) => (a.id === id ? { ...a, ...data } : a))
      );
      setEditingId(null);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteAccount = async (id: string, name: string) => {
    if (!window.confirm(`Confirm permanent removal of account node "${name}"?`))
      return;
    setLoading(true);
    try {
      await accountApi.deleteAccount(id);
      setAccounts((prev) => prev.filter((a) => a.id !== id));
    } catch {
      setMessage({ type: 'error', text: 'Deletion transaction aborted.' });
    } finally {
      setLoading(false);
    }
  };

  const startEditing = (acc: AccountEntity) => {
    setEditingId(acc.id);
    setEditName(acc.name);
    setEditType(acc.account_type);

    // 🎯 NEW: Populates inline edit input element field value on start trigger
    setEditAccountNumber(acc.account_number || '');

    setEditIfsc(acc.ifsc_code);
    setEditBranch(acc.branch_name);
    setEditAddress(acc.address);
  };

  return {
    banks,
    accounts,
    accountName,
    setAccountName,
    accountType,
    setAccountType,

    // 🎯 NEW HOOK ENTRIES EXPOSED FOR FRONTEND VIEW BINDING
    accountNumber,
    setAccountNumber,
    editAccountNumber,
    setEditAccountNumber,

    ifscCode,
    setIfscCode,
    branchName,
    setBranchName,
    address,
    setAddress,
    selectedBankId,
    setSelectedBankId,
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
    startEditing,
  };
}
