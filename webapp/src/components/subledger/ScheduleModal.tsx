import React, { useState, useEffect } from 'react';
import { subledgerApi } from '../../api/subledger';
import type {
  ScheduleType,
  RecurrencePatternType,
  AssetSubLedgerNode,
  AssetComplianceSchedule,
} from '../../api/subledger';

interface ScheduleModalProps {
  isOpen: boolean;
  onClose: () => void;
  asset: AssetSubLedgerNode;
  scheduleToEdit?: AssetComplianceSchedule | null;
  onSuccess: () => void;
}

export const ScheduleModal: React.FC<ScheduleModalProps> = ({
  isOpen,
  onClose,
  asset,
  scheduleToEdit,
  onSuccess,
}) => {
  const [title, setTitle] = useState('');
  const [operationalAccountId, setOperationalAccountId] = useState<string>('');
  const [scheduleType, setScheduleType] = useState<ScheduleType>('LAND_TAX_DUE');
  const [recurrencePattern, setRecurrencePattern] =
    useState<RecurrencePatternType>('ANNUALLY');
  const [dueDate, setDueDate] = useState('2026-09-30');
  const [expectedAmount, setExpectedAmount] = useState<number | string>('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      if (scheduleToEdit) {
        setTitle(scheduleToEdit.title);
        setOperationalAccountId(scheduleToEdit.operational_account || '');
        setScheduleType(scheduleToEdit.schedule_type);
        setRecurrencePattern(scheduleToEdit.recurrence_pattern);
        setDueDate(scheduleToEdit.due_date);
        setExpectedAmount(scheduleToEdit.expected_amount);
      } else {
        setOperationalAccountId(asset.operational_accounts?.[0]?.id || '');
        setTitle('');
        setExpectedAmount('');
      }
      setError(null);
    }
  }, [isOpen, scheduleToEdit, asset]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);

    try {
      const payload = {
        asset: asset.id,
        operational_account: operationalAccountId || null,
        title,
        schedule_type: scheduleType,
        recurrence_pattern: recurrencePattern,
        due_date: dueDate,
        expected_amount: Number(expectedAmount),
        advance_notice_days: 15,
      };

      if (scheduleToEdit) {
        await subledgerApi.updateSchedule(scheduleToEdit.id, payload);
      } else {
        await subledgerApi.createSchedule(payload);
      }

      onSuccess();
      onClose();
    } catch (err) {
      console.error('Failed to save schedule:', err);
      setError('Could not save schedule. Please check inputs and try again.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-xl border border-slate-800 bg-slate-900 p-6 shadow-2xl text-slate-100">
        <div className="flex justify-between items-center border-b border-slate-800 pb-3">
          <h3 className="text-sm font-bold text-white">
            {scheduleToEdit ? '✏️ Edit Reminder' : '⏰ Add Compliance Due / Reminder'}
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <div>
            <label className="block text-xs font-semibold text-slate-300">
              Target Operational Account / Utility
            </label>
            <select
              value={operationalAccountId}
              onChange={(e) => setOperationalAccountId(e.target.value)}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
            >
              <option value="">-- Unlinked / General Asset Due --</option>
              {asset.operational_accounts.map((op) => (
                <option key={op.id} value={op.id}>
                  {op.provider_name} ({op.consumer_identifier})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-400">
              Schedule Title
            </label>
            <input
              type="text"
              required
              placeholder="e.g. Bi-Monthly KSEB Bill or Revenue Land Tax"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs font-medium text-slate-400">
                Due Date
              </label>
              <input
                type="date"
                required
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400">
                Expected Amount (₹)
              </label>
              <input
                type="number"
                step="0.01"
                required
                placeholder="1850.00"
                value={expectedAmount}
                onChange={(e) => setExpectedAmount(e.target.value)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs font-medium text-slate-400">
                Type
              </label>
              <select
                value={scheduleType}
                onChange={(e) => setScheduleType(e.target.value as ScheduleType)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
              >
                <option value="LAND_TAX_DUE">Land Tax Due</option>
                <option value="PROPERTY_TAX_DUE">Property Tax Due</option>
                <option value="UTILITY_BILL">Utility Bill</option>
                <option value="PREMIUM_DUE">Insurance Premium</option>
                <option value="FD_MATURITY">FD Maturity</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400">
                Recurrence
              </label>
              <select
                value={recurrencePattern}
                onChange={(e) => setRecurrencePattern(e.target.value as RecurrencePatternType)}
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
              >
                <option value="ANNUALLY">Annually</option>
                <option value="BIMONTHLY">Bi-Monthly</option>
                <option value="QUARTERLY">Quarterly</option>
                <option value="MONTHLY">Monthly</option>
                <option value="HALF_YEARLY">Half-Yearly</option>
                <option value="ONE_OFF">One Off</option>
              </select>
            </div>
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
              {saving ? 'Saving...' : scheduleToEdit ? 'Update Reminder' : 'Add Reminder'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};