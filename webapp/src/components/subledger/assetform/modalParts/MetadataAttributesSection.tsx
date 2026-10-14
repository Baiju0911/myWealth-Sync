import React from 'react';

export interface MetadataRow {
  key: string;
  value: string;
}

interface MetadataAttributesSectionProps {
  entries: MetadataRow[];
  onChange: (index: number, field: 'key' | 'value', value: string) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
}

export const MetadataAttributesSection: React.FC<MetadataAttributesSectionProps> = ({
  entries,
  onChange,
  onAdd,
  onRemove,
}) => {
  return (
    <div className="rounded-lg bg-slate-950 p-3 border border-slate-800 font-mono">
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs font-bold text-slate-400 uppercase">
          Dynamic Metadata Attributes ({entries.length})
        </span>
        <button
          type="button"
          onClick={onAdd}
          className="text-xs text-emerald-400 hover:underline cursor-pointer"
        >
          + Add Custom Field
        </button>
      </div>

      <div className="space-y-2">
        {entries.map((row, idx) => (
          <div key={idx} className="flex gap-2 items-center">
            <input
              type="text"
              placeholder="Field Key (e.g. sro_name, survey_no)"
              value={row.key}
              onChange={(e) => onChange(idx, 'key', e.target.value)}
              className="w-1/2 rounded border border-slate-800 bg-slate-900 p-1.5 text-xs text-white"
            />
            <input
              type="text"
              placeholder="Value"
              value={row.value}
              onChange={(e) => onChange(idx, 'value', e.target.value)}
              className="w-1/2 rounded border border-slate-800 bg-slate-900 p-1.5 text-xs text-white"
            />
            <button
              type="button"
              onClick={() => onRemove(idx)}
              className="text-slate-500 hover:text-rose-400 text-xs px-1 cursor-pointer"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};