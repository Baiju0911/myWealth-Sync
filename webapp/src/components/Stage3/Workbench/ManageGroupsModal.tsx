import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X, Plus, Trash2, ArrowRightLeft, FolderTree, AlertCircle } from 'lucide-react';
import { narrationTaggingApi, type GroupHierarchyItem } from '../../../api/narrationTaggingApi';

interface ManageGroupsModalProps {
  isOpen: boolean;
  onClose: () => void;
  headerScope: string; // e.g. "Suspense Account"
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

  // Move Subgroup state
  const [selectedSubgroup, setSelectedSubgroup] = useState<string>('');
  const [targetParentGroup, setTargetParentGroup] = useState<string>('');

  useEffect(() => {
    if (isOpen) {
      loadHierarchy();
      setError(null);
    }
  }, [isOpen, headerScope]);

  const loadHierarchy = async () => {
    setLoading(true);
    try {
      const data = await narrationTaggingApi.getHierarchies(headerScope);
      setHierarchies(data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Failed to fetch group hierarchy');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newGroupTag.trim()) return;

    const formattedTag = newGroupTag.trim().startsWith('#') 
      ? newGroupTag.trim().toUpperCase() 
      : `#${newGroupTag.trim().toUpperCase()}`;

    // Frontend Duplicate Check within active header
    const duplicate = hierarchies.some(
      (h) => h.group_tag.toUpperCase() === formattedTag && (!newSubgroupTag.trim() || h.subgroup_tag === newSubgroupTag.trim())
    );

    if (duplicate) {
      setError(`Group '${formattedTag}' already exists under '${headerScope}'.`);
      return;
    }

    try {
      await narrationTaggingApi.createGroup({
        header_scope: headerScope,
        group_tag: formattedTag,
        subgroup_tag: newSubgroupTag.trim() || null,
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

  const handleDeleteItem = async (id: number) => {
    try {
      await narrationTaggingApi.deleteHierarchy(id);
      await loadHierarchy();
      onHierarchyUpdated();
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Failed to delete item');
    }
  };

  const handleMoveSubgroup = async () => {
    if (!selectedSubgroup || !targetParentGroup) return;

    try {
      await narrationTaggingApi.moveSubgroup({
        header_scope: headerScope,
        subgroup_tag: selectedSubgroup,
        target_group_tag: targetParentGroup,
      });

      setSelectedSubgroup('');
      setTargetParentGroup('');
      setError(null);
      await loadHierarchy();
      onHierarchyUpdated();
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Move failed');
    }
  };

  if (!isOpen) return null;

  // Extract distinct primary parent groups for dropdown
  const uniqueGroups = Array.from(new Set(hierarchies.map((h) => h.group_tag)));
  const uniqueSubgroups = Array.from(
    new Set(hierarchies.map((h) => h.subgroup_tag).filter(Boolean))
  ) as string[];

  return createPortal(
    <div className="fixed inset-0 z-10000 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm font-mono">
      <div className="bg-zinc-950 border border-zinc-800 rounded-xl w-full max-w-2xl flex flex-col shadow-2xl overflow-hidden text-zinc-100">
        
        {/* Header */}
        <div className="flex justify-between items-center px-5 py-3 border-b border-zinc-800 bg-zinc-900/90">
          <div className="flex items-center gap-2">
            <FolderTree className="w-4 h-4 text-emerald-400" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-100">
              Manage Groups & Hierarchy — <span className="text-emerald-400">{headerScope}</span>
            </h3>
          </div>
          <button
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

        <div className="p-5 flex-1 overflow-y-auto space-y-6">
          
          {/* Add Group Section */}
          <form onSubmit={handleCreateGroup} className="space-y-3 bg-zinc-900/40 border border-zinc-800/80 p-3.5 rounded-lg">
            <div className="text-[11px] font-bold uppercase tracking-wider text-zinc-300 flex items-center gap-1.5">
              <Plus className="w-3.5 h-3.5 text-emerald-400" /> Add New Group Tag
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <input
                type="text"
                placeholder="#GROUP_TAG (e.g. #CONTRA)"
                value={newGroupTag}
                onChange={(e) => setNewGroupTag(e.target.value)}
                className="bg-zinc-900 border border-zinc-700/80 rounded px-3 py-1.5 text-xs text-zinc-100 focus:outline-none focus:border-emerald-500"
              />
              <input
                type="text"
                placeholder="Subgroup Tag (Optional)"
                value={newSubgroupTag}
                onChange={(e) => setNewSubgroupTag(e.target.value)}
                className="bg-zinc-900 border border-zinc-700/80 rounded px-3 py-1.5 text-xs text-zinc-100 focus:outline-none focus:border-emerald-500"
              />
            </div>
            <button
              type="submit"
              className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-semibold cursor-pointer transition-colors"
            >
              Save Group
            </button>
          </form>

          {/* Move Subgroup Section */}
          {uniqueSubgroups.length > 0 && uniqueGroups.length > 1 && (
            <div className="space-y-3 bg-zinc-900/40 border border-zinc-800/80 p-3.5 rounded-lg">
              <div className="text-[11px] font-bold uppercase tracking-wider text-zinc-300 flex items-center gap-1.5">
                <ArrowRightLeft className="w-3.5 h-3.5 text-blue-400" /> Move Subgroup Under Another Group
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                <select
                  value={selectedSubgroup}
                  onChange={(e) => setSelectedSubgroup(e.target.value)}
                  className="bg-zinc-900 border border-zinc-700/80 rounded px-3 py-1.5 text-xs text-zinc-100 focus:outline-none focus:border-blue-500"
                >
                  <option value="">-- Select Subgroup --</option>
                  {uniqueSubgroups.map((sub) => (
                    <option key={sub} value={sub}>{sub}</option>
                  ))}
                </select>
                <select
                  value={targetParentGroup}
                  onChange={(e) => setTargetParentGroup(e.target.value)}
                  className="bg-zinc-900 border border-zinc-700/80 rounded px-3 py-1.5 text-xs text-zinc-100 focus:outline-none focus:border-blue-500"
                >
                  <option value="">-- Select Target Group --</option>
                  {uniqueGroups.map((g) => (
                    <option key={g} value={g}>{g}</option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                onClick={handleMoveSubgroup}
                disabled={!selectedSubgroup || !targetParentGroup}
                className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded text-xs font-semibold cursor-pointer transition-colors"
              >
                Move Subgroup
              </button>
            </div>
          )}

          {/* Existing Groups Table */}
          <div className="space-y-2">
            <div className="text-[11px] font-bold uppercase tracking-wider text-zinc-400">
              Active Groups under {headerScope}
            </div>
            <div className="border border-zinc-800 rounded-lg overflow-hidden bg-zinc-900/30">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="bg-zinc-900/80 border-b border-zinc-800 text-zinc-400">
                    <th className="py-2 px-3">Parent Group</th>
                    <th className="py-2 px-3">Subgroup</th>
                    <th className="py-2 px-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {hierarchies.length === 0 ? (
                    <tr>
                      <td colSpan={3} className="py-4 text-center text-zinc-500">
                        {loading ? 'Loading...' : 'No custom groups configured for this header.'}
                      </td>
                    </tr>
                  ) : (
                    hierarchies.map((item) => (
                      <tr key={item.id} className="hover:bg-zinc-800/30">
                        <td className="py-2 px-3 font-semibold text-emerald-400">{item.group_tag}</td>
                        <td className="py-2 px-3 text-zinc-300">{item.subgroup_tag || '—'}</td>
                        <td className="py-2 px-3 text-right">
                          <button
                            onClick={() => handleDeleteItem(item.id)}
                            className="p-1 text-zinc-500 hover:text-rose-400 transition-colors cursor-pointer"
                            title="Delete"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))
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