// src/hooks/useBanksCrud.ts
import { useState, useEffect } from 'react';
import { bankApi } from '../api';
import { type BankEntity } from '../types/ledger';

export function useBanksCrud() {
  const [banks, setBanks] = useState<BankEntity[]>([]);
  const [displayName, setDisplayName] = useState('');
  const [code, setCode] = useState('');

  // Inline Editing States
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editCode, setEditCode] = useState('');

  const [loading, setLoading] = useState(false);
  const [fetchLoading, setFetchLoading] = useState(true);
  const [message, setMessage] = useState({ type: '', text: '' });

  const fetchBalancesMatrix = async () => {
    setFetchLoading(true);
    try {
      const data = await bankApi.getBanks();
      const normalizedData = (
        Array.isArray(data) ? data : data.results || []
      ).map((b: any) => ({
        ...b,
        account_count: b.account_count ?? 0,
        credential_count: b.credential_count ?? 0,
      }));
      setBanks(normalizedData);
    } catch (err) {
      console.error(err);
      setMessage({
        type: 'error',
        text: 'Failed to synchronize with backend database.',
      });
    } finally {
      setFetchLoading(false);
    }
  };

  useEffect(() => {
    fetchBalancesMatrix();
  }, []);

  const handleBankSubmit = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (!displayName.trim() || !code.trim()) {
      setMessage({ type: 'error', text: 'All layout fields are mandatory.' });
      return;
    }
    setLoading(true);
    setMessage({ type: '', text: '' });

    try {
      const data = await bankApi.createBank({
        code: code.trim().toUpperCase(),
        display_name: displayName.trim(),
      });
      setMessage({
        type: 'success',
        text: `Successfully anchored ${data.display_name}!`,
      });
      setDisplayName('');
      setCode('');
      setBanks((prev) => [
        { ...data, account_count: 0, credential_count: 0 },
        ...prev,
      ]);
    } catch {
      setMessage({
        type: 'error',
        text: 'Validation error: Unique constraints broken.',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateBank = async (id: string) => {
    if (!editName.trim() || !editCode.trim()) return;
    setLoading(true);
    try {
      const data = await bankApi.updateBank(id, {
        code: editCode.trim().toUpperCase(),
        display_name: editName.trim(),
      });
      setBanks((prev) =>
        prev.map((b) => (b.id === id ? { ...b, ...data } : b))
      );
      setEditingId(null);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteBank = async (id: string, name: string) => {
    if (!window.confirm(`Are you sure you want to completely purge "${name}"?`))
      return;
    setLoading(true);
    try {
      await bankApi.deleteBank(id);
      setBanks((prev) => prev.filter((b) => b.id !== id));
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const startEditing = (bank: BankEntity) => {
    setEditingId(bank.id);
    setEditName(bank.display_name);
    setEditCode(bank.code);
  };

  const cancelEditing = () => {
    setEditingId(null);
  };

  return {
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
  };
}
