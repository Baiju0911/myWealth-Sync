// src/hooks/useCredentialsCrud.ts
import { useState, useEffect } from 'react';
import { credentialApi, bankApi, accountApi } from '../api';
import type {
  BankEntity,
  AccountEntity,
  CredentialEntity,
} from '../types/ledger';

export function useCredentialsCrud() {
  const [banks, setBanks] = useState<BankEntity[]>([]);
  const [accounts, setAccounts] = useState<AccountEntity[]>([]);
  const [credentials, setCredentials] = useState<CredentialEntity[]>([]);

  // 💾 State Context: Now pointing directly to specific Accounts
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [passwordKey, setPasswordKey] = useState('');

  // ✏️ Inline Editing States
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editPassword, setEditPassword] = useState('');

  const [loading, setLoading] = useState(false);
  const [fetchLoading, setFetchLoading] = useState(true);
  const [message, setMessage] = useState({ type: '', text: '' });

  const loadInitialData = async () => {
    setFetchLoading(true);
    try {
      // 🔄 Simultaneously pipeline your structural database tables
      const [banksData, accountsData, credsData] = await Promise.all([
        bankApi.getBanks(),
        accountApi.getAccounts(),
        credentialApi.getCredentials(),
      ]);

      setBanks(Array.isArray(banksData) ? banksData : banksData.results || []);
      setAccounts(
        Array.isArray(accountsData) ? accountsData : accountsData.results || []
      );
      setCredentials(
        Array.isArray(credsData) ? credsData : credsData.results || []
      );
    } catch (err) {
      console.error('Relational initialization data fetch crash:', err);
    } finally {
      setFetchLoading(false);
    }
  };

  useEffect(() => {
    loadInitialData();
  }, []);

  const handleCredSubmit = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (!selectedAccountId || !passwordKey.trim()) {
      setMessage({
        type: 'error',
        text: 'Target Account Ledger Node and Decryption Passphrase are mandatory.',
      });
      return;
    }
    setLoading(true);
    setMessage({ type: '', text: '' });

    try {
      // 🚀 REST API Mapping: Anchoring password metadata to unique account foreign key values
      const data = await credentialApi.createCredential({
        account_id: selectedAccountId,
        statement_password: passwordKey.trim(),
      });

      setMessage({
        type: 'success',
        text: 'Decryption passphrase secured inside vault!',
      });

      setPasswordKey('');
      setSelectedAccountId('');

      // 🎯 THE FIX: Intelligently replace or append based on unique row identity keys
      setCredentials((prev) => {
        const exists = prev.some((c) => c.id === data.id);
        if (exists) {
          // Update the card state inline and move it to the front
          const remaining = prev.filter((c) => c.id !== data.id);
          return [data, ...remaining];
        }
        // If it is a net-new asset, safely append to top shelf
        return [data, ...prev];
      });
    } catch {
      setMessage({
        type: 'error',
        text: 'Validation failure: One credential record constraint per account broken.',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateCred = async (id: string) => {
    if (!editPassword.trim()) return;
    setLoading(true);
    try {
      const currentCred = credentials.find((c) => c.id === id);
      if (!currentCred) return;

      const data = await credentialApi.updateCredential(id, {
        account_id: currentCred.account_id, // Retain underlying account mapping context
        statement_password: editPassword.trim(),
      });

      // 🎯 SECURED: Unified structure mutation merge rule mapping pass
      setCredentials((prev) =>
        prev.map((c) => (c.id === id ? { ...c, ...data } : c))
      );
      setEditingId(null);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteCred = async (id: string, label: string) => {
    if (
      !window.confirm(
        `Are you sure you want to permanently purge vault keys for "${label}"?`
      )
    )
      return;
    setLoading(true);
    try {
      await credentialApi.deleteCredential(id);
      setCredentials((prev) => prev.filter((c) => c.id !== id));
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const startEditing = (cred: CredentialEntity) => {
    setEditingId(cred.id);
    setEditPassword(cred.statement_password);
  };

  const cancelEditing = () => {
    setEditingId(null);
  };

  return {
    banks,
    accounts,
    credentials,
    selectedAccountId,
    setSelectedAccountId,
    passwordKey,
    setPasswordKey,
    editingId,
    setEditingId,
    editPassword,
    setEditPassword,
    loading,
    fetchLoading,
    message,
    handleCredSubmit,
    handleUpdateCred,
    handleDeleteCred,
    startEditing,
    cancelEditing,
  };
}
