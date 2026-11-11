import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import {
  X,
  Plus,
  Trash2,
  Edit2,
  Check,
  FolderTree,
  AlertCircle,
  FolderPlus,
} from 'lucide-react';
import {
  narrationTaggingApi,
  type GroupHierarchyItem,
} from '../../../api/narrationTaggingApi';

interface ManageGroupsModalProps {
  isOpen: boolean;
  onClose: () => void;
  headerScope: string;
  onHierarchyUpdated: () => void;
}

export const ManageGroupsModal: React.FC<ManageGroupsModalProps> = ({
  isOpen,
  onClose,
  headerScope,
  onHierarchyUpdated,
}) => {
  const [hierarchies, setHierarchies] = useState<GroupHierarchyItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // New Group input
  const [newGroupTag, setNewGroupTag] = useState('');
  const [newSubgroupTag, setNewSubgroupTag] = useState('');

  // Inline editing state
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editGroupTag, setEditGroupTag] = useState('');
  const [editSubgroupTag, setEditSubgroupTag] = useState('');

  useEffect(() => {
    if (isOpen) {
      loadHierarchy();
      setError(null);
      setEditingId(null);
    }
  }, [isOpen, headerScope]);

  const loadHierarchy = async () => {
    setLoading(true);
    try {
      const data = await narrationTaggingApi.getHierarchies(headerScope);
      setHierarchies(data);
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ||
          err.message ||
          'Failed to fetch group hierarchy'
      );
    } finally {
      setLoading(false);
    }
  };

  const formatTag = (tag: string) => {
    const trimmed = tag.trim();
    if (!trimmed) return '';
    return trimmed.startsWith('#')
      ? trimmed.toUpperCase()
      : `#${trimmed.toUpperCase()}`;
  };

  const handleCreateGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newGroupTag.trim()) return;

    const formattedTag = formatTag(newGroupTag);
    const formattedSub = newSubgroupTag.trim()
      ? newSubgroupTag.trim().toUpperCase()
      : null;

    const duplicate = hierarchies.some(
      (h) =>
        h.group_tag.toUpperCase() === formattedTag &&
        (h.subgroup_tag || '').toUpperCase() === (formattedSub || '')
    );

    if (duplicate) {
      setError(
        `Group '${formattedTag}' ${
          formattedSub ? `with subgroup '${formattedSub}'` : ''
        } already exists under '${headerScope}'.`
      );
      return;
    }

    try {
      await narrationTaggingApi.createGroup({
        header_scope: headerScope,
        group_tag: formattedTag,
        subgroup_tag: formattedSub,
      });

      setNewGroupTag('');
      setNewSubgroupTag('');
      setError(null);
      await loadHierarchy();
      onHierarchyUpdated();
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Creation failed');
    }
  };

  const startEdit = (item: GroupHierarchyItem) => {
    setEditingId(item.id);
    setEditGroupTag(item.group_tag);
    setEditSubgroupTag(item.subgroup_tag || '');
    setError(null);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditGroupTag('');
    setEditSubgroupTag('');
  };

  const handleSaveEdit = async (id: number) => {
    if (!editGroupTag.trim()) return;

    const formattedGroup = formatTag(editGroupTag);
    const formattedSub = editSubgroupTag.trim()
      ? editSubgroupTag.trim().toUpperCase()
      : null;

    try {
      await narrationTaggingApi.updateHierarchy(id, {
        group_tag: formattedGroup,
        subgroup_tag: formattedSub,
      });

      setEditingId(null);
      setError(null);
      await loadHierarchy();
      onHierarchyUpdated();
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Update failed');
    }
  };

  const handleDeleteItem = async (id: number) => {
    try {
      await narrationTaggingApi.deleteHierarchy(id);
      await loadHierarchy();
      onHierarchyUpdated();
    } catch (err: any) {
      setError(
        err?.response?.data?.detail || err.message || 'Failed to delete item'
      );
    }
  };

  if (!isOpen) return null;

  // Extract distinct parent groups for selector/autocomplete
  const distinctGroups = Array.from(
    new Set(hierarchies.map((h) => h.group_tag))
  );

  return createPortal(
    <div className="fixed inset-0 z-10000 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm font-mono text-zinc-100">
      <div className="bg-zinc-950 border border-zinc-800 rounded-xl w-full max-w-2xl flex flex-col shadow-2xl overflow-hidden">
        
        {/* Header */}
        <div className="flex justify-between items-center px-5 py-3 border-b border-zinc-800 bg-zinc-900/90">
          <div className="flex items-center gap-2">
            <FolderTree className="w-4 h-4 text-emerald-400" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-100">
              Manage Groups & Hierarchy — <span className="text-emerald-400">{headerScope}</span>
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-zinc-400 hover:text-zinc-100 p-1 rounded hover:bg-zinc-800 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Notice */}
        <div className="px-5 py-2 bg-zinc-900/40 border-b border-zinc-800/80 text-[11px] text-zinc-400">
          Changes here only organize visual clusters within <strong className="text-zinc-200">{headerScope}</strong>. Core ledger entries remain untouched.
        </div>

        {error && (
          <div className="mx-5 mt-3 p-2.5 bg-rose-950/60 border border-rose-800 text-rose-300 rounded text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="p-5 flex-1 overflow-y-auto space-y-5 max-h-[70vh]">
          
          {/* Add Group Section */}
          <form
            onSubmit={handleCreateGroup}
            className="space-y-3 bg-zinc-900/40 border border-zinc-800/80 p-3.5 rounded-lg"
          >
            <div className="text-[11px] font-bold uppercase tracking-wider text-zinc-300 flex items-center gap-1.5">
              <FolderPlus className="w-3.5 h-3.5 text-emerald-400" /> Add New Group or Subgroup
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <div className="flex flex-col gap-1">
                <input
                  type="text"
                  placeholder="#GROUP_TAG (e.g. #INTERABANK)"
                  value={newGroupTag}
                  onChange={(e) => setNewGroupTag(e.target.value)}
                  className="bg-zinc-900 border border-zinc-700/80 rounded px-3 py-1.5 text-xs text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:border-emerald-500"
                />
                {distinctGroups.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    <span className="text-[10px] text-zinc-500">Quick pick:</span>
                    {distinctGroups.map((g) => (
                      <button
                        key={g}
                        type="button"
                        onClick={() => setNewGroupTag(g)}
                        className="text-[10px] px-1.5 py-0.2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded cursor-pointer"
                      >
                        {g}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div>
                <input
                  type="text"
                  placeholder="Subgroup Tag (e.g. 60to81, Optional)"
                  value={newSubgroupTag}
                  onChange={(e) => setNewSubgroupTag(e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-700/80 rounded px-3 py-1.5 text-xs text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:border-emerald-500"
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={!newGroupTag.trim()}
              className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded text-xs font-semibold cursor-pointer transition-colors flex items-center gap-1.5"
            >
              <Plus className="w-3.5 h-3.5" /> Save Group Node
            </button>
          </form>

          {/* Active Hierarchy Table */}
          <div className="space-y-2">
            <div className="flex justify-between items-center text-[11px] font-bold uppercase tracking-wider text-zinc-400">
              <span>Active Groups & Subgroups under {headerScope}</span>
              <span className="text-[10px] text-zinc-500">{hierarchies.length} nodes</span>
            </div>
            <div className="border border-zinc-800 rounded-lg overflow-hidden bg-zinc-900/30">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="bg-zinc-900/80 border-b border-zinc-800 text-zinc-400">
                    <th className="py-2.5 px-3">Parent Group Tag</th>
                    <th className="py-2.5 px-3">Subgroup Label</th>
                    <th className="py-2.5 px-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60 font-mono">
                  {hierarchies.length === 0 ? (
                    <tr>
                      <td colSpan={3} className="py-6 text-center text-zinc-500">
                        {loading
                          ? 'Loading hierarchy...'
                          : 'No custom groups configured for this header.'}
                      </td>
                    </tr>
                  ) : (
                    hierarchies.map((item) => {
                      const isEditing = editingId === item.id;

                      if (isEditing) {
                        return (
                          <tr key={item.id} className="bg-zinc-900/90">
                            <td className="py-2 px-3">
                              <input
                                type="text"
                                value={editGroupTag}
                                onChange={(e) => setEditGroupTag(e.target.value)}
                                className="w-full bg-zinc-950 border border-emerald-500 rounded px-2 py-1 text-xs text-emerald-300 font-bold outline-none"
                              />
                            </td>
                            <td className="py-2 px-3">
                              <input
                                type="text"
                                value={editSubgroupTag}
                                onChange={(e) => setEditSubgroupTag(e.target.value)}
                                placeholder="Subgroup (or empty for none)"
                                className="w-full bg-zinc-950 border border-cyan-500 rounded px-2 py-1 text-xs text-cyan-300 outline-none"
                              />
                            </td>
                            <td className="py-2 px-3 text-right space-x-1 whitespace-nowrap">
                              <button
                                type="button"
                                onClick={() => handleSaveEdit(item.id)}
                                className="p-1.5 bg-emerald-700/80 hover:bg-emerald-600 text-white rounded cursor-pointer transition-colors"
                                title="Save changes"
                              >
                                <Check className="w-3.5 h-3.5" />
                              </button>
                              <button
                                type="button"
                                onClick={cancelEdit}
                                className="p-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-400 rounded cursor-pointer transition-colors"
                                title="Cancel"
                              >
                                <X className="w-3.5 h-3.5" />
                              </button>
                            </td>
                          </tr>
                        );
                      }

                      return (
                        <tr key={item.id} className="hover:bg-zinc-800/30">
                          <td className="py-2.5 px-3 font-semibold text-emerald-400">
                            {item.group_tag}
                          </td>
                          <td className="py-2.5 px-3">
                            {item.subgroup_tag ? (
                              <span className="px-2 py-0.5 rounded bg-zinc-800/80 border border-zinc-700/60 text-cyan-300 text-[11px]">
                                {item.subgroup_tag}
                              </span>
                            ) : (
                              <span className="text-zinc-600 italic">None (Root Tag)</span>
                            )}
                          </td>
                          <td className="py-2.5 px-3 text-right space-x-1 whitespace-nowrap">
                            <button
                              type="button"
                              onClick={() => startEdit(item)}
                              className="p-1 text-zinc-500 hover:text-zinc-200 transition-colors cursor-pointer"
                              title="Edit tag / subgroup"
                            >
                              <Edit2 className="w-3.5 h-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => handleDeleteItem(item.id)}
                              className="p-1 text-zinc-500 hover:text-rose-400 transition-colors cursor-pointer"
                              title="Delete group node"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

        </div>

      </div>
    </div>,
    document.body
  );
};