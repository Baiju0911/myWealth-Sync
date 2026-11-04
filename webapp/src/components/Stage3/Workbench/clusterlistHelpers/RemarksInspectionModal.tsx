// webapp/src/components/Stage3/Workbench/clusterlistHelpers/RemarksInspectionModal.tsx
import React, { useState } from 'react';
import { X } from 'lucide-react';
import { DualNarrationViewer } from '../DualNarrationViewer';
import { updateEntryUserNote } from '../../../../api/api';
import { parseRemarks } from '../../../../utils/classificationHelpers';

interface Props {
  item: { id: string; narration?: string; remarks?: any } | null;
  onClose: () => void;
}

export const RemarksInspectionModal: React.FC<Props> = ({ item, onClose }) => {
  if (!item) return null;

  const initialNote = parseRemarks(item.remarks).user_note || '';
  const [userNote, setUserNote] = useState(initialNote);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const data = await updateEntryUserNote({ entry_id: item.id, user_note: userNote });
      if (data?.status === 'success') {
        item.remarks = data.remarks;
        onClose();
      }
    } catch (err) {
      console.error('Save note error:', err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 bg-black/80 z-9999 flex items-center justify-center p-4 backdrop-blur-xs font-mono"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-zinc-900 border border-zinc-700 rounded-xl p-5 max-w-lg w-full text-zinc-100 shadow-2xl space-y-3"
      >
        <div className="flex justify-between items-center border-b border-zinc-800 pb-2">
          <h3 className="text-xs font-bold text-amber-400 uppercase tracking-wider">Line Item Audit & Remarks</h3>
          <button type="button" onClick={onClose} className="text-zinc-400 hover:text-zinc-100 p-1 rounded">
            <X className="w-4 h-4" />
          </button>
        </div>

        <DualNarrationViewer item={item} />

        <div className="space-y-1">
          <label className="text-[10px] text-amber-400 uppercase font-bold block">User Comment / Note</label>
          <input
            type="text"
            placeholder="e.g., Personal payment for tea at Technopark..."
            value={userNote}
            onChange={(e) => setUserNote(e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-700 px-3 py-2 rounded-lg text-xs text-zinc-100 outline-none focus:border-amber-400 font-sans"
          />
        </div>

        <div className="flex gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs rounded-lg font-bold cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="flex-1 py-2 bg-amber-500 hover:bg-amber-400 text-zinc-950 text-xs rounded-lg font-bold cursor-pointer disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Comment'}
          </button>
        </div>
      </div>
    </div>
  );
};