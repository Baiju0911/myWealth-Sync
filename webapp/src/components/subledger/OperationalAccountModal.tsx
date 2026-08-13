import React, { useState, useEffect } from 'react';
import { subledgerApi } from '../../api/subledger';
import type {
  ServiceProviderType,
  AssetSubLedgerNode,
  AssetOperationalAccount,
} from '../../api/subledger';

interface OperationalAccountModalProps {
  isOpen: boolean;
  onClose: () => void;
  asset: AssetSubLedgerNode;
  utilityToEdit?: AssetOperationalAccount | null;
  onSuccess: () => void;
}

export const OperationalAccountModal: React.FC<OperationalAccountModalProps> = ({
  isOpen,
  onClose,
  asset,
  utilityToEdit,
  onSuccess,
}) => {
  const [serviceType, setServiceType] = useState<ServiceProviderType>('PROPERTY_TAX');
  const [providerName, setProviderName] = useState('');
  const [consumerIdentifier, setConsumerIdentifier] = useState('');
  const [matchingKeyword, setMatchingKeyword] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      if (utilityToEdit) {
        setServiceType(utilityToEdit.service_type);
        setProviderName(utilityToEdit.provider_name);
        setConsumerIdentifier(utilityToEdit.consumer_identifier);
        setMatchingKeyword(utilityToEdit.matching_keyword || '');
      } else {
        setServiceType('PROPERTY_TAX');
        setProviderName('');
        setConsumerIdentifier('');
        setMatchingKeyword('');
      }
      setError(null);
    }
  }, [isOpen, utilityToEdit]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);

    try {
      const payload = {
        asset: asset.id,
        service_type: serviceType,
        provider_name: providerName,
        consumer_identifier: consumerIdentifier,
        matching_keyword: matchingKeyword || providerName,
        is_active: true,
      };

      if (utilityToEdit) {
        await subledgerApi.updateOperationalAccount(utilityToEdit.id, payload);
      } else {
        await subledgerApi.createOperationalAccount(payload);
      }

      onSuccess();
      onClose();
    } catch (err) {
      console.error('Failed to save operational account:', err);
      setError('Could not save operational account. Check fields and retry.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-xl border border-slate-800 bg-slate-900 p-6 shadow-2xl text-slate-100">
        <div className="flex justify-between items-center border-b border-slate-800 pb-3">
          <h3 className="text-sm font-bold text-white">
            {utilityToEdit ? '✏️ Edit Operational Utility' : '➕ Register Operational Utility'}
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white">✕</button>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <div>
            <label className="block text-xs text-slate-400">Service Type</label>
            <select
              value={serviceType}
              onChange={(e) => setServiceType(e.target.value as ServiceProviderType)}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:outline-none"
            >
              <option value="PROPERTY_TAX">Property / Local Body Tax</option>
              <option value="LAND_REVENUE_TAX">Land Revenue Tax</option>
              <option value="ELECTRICITY">Electricity (KSEB / Board)</option>
              <option value="WATER">Water Supply (KWA / Board)</option>
              <option value="BUILDING_MAINTENANCE">HOA / Maintenance</option>
              <option value="INSURANCE">Insurance Plan</option>
            </select>
          </div>

          <div>
            <label className="block text-xs text-slate-400">Provider Name</label>
            <input
              type="text"
              required
              placeholder="e.g. KSEB or Trivandrum Corp"
              value={providerName}
              onChange={(e) => setProviderName(e.target.value)}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400">Consumer ID / Meter #</label>
            <input
              type="text"
              required
              placeholder="e.g. Consumer #1233434"
              value={consumerIdentifier}
              onChange={(e) => setConsumerIdentifier(e.target.value)}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400">
              Matching Keyword Anchor <span className="text-[10px] text-slate-500">(Bank Narration Match)</span>
            </label>
            <input
              type="text"
              required
              placeholder="e.g. KSEB, ULLOOR, REVENUE"
              value={matchingKeyword}
              onChange={(e) => setMatchingKeyword(e.target.value)}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:outline-none"
            />
          </div>

          {error && <p className="text-xs text-rose-400">{error}</p>}

          <div className="flex justify-end gap-2 pt-3 border-t border-slate-800 mt-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-700"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
            >
              {saving ? 'Saving...' : utilityToEdit ? 'Update Utility' : 'Add Utility'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};