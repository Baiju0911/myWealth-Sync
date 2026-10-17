import React from 'react';

interface IdentifiersSectionProps {
  assetCode: string;
  setAssetCode: (val: string) => void;
  name: string;
  setName: (val: string) => void;
}

export const IdentifiersSection: React.FC<IdentifiersSectionProps> = ({
  assetCode,
  setAssetCode,
  name,
  setName,
}) => {
  return (
    <>
      <div className="col-span-4">
        <label className="block text-xs text-slate-400">Entity Code</label>
        <input
          type="text"
          required
          value={assetCode}
          onChange={(e) => setAssetCode(e.target.value)}
          className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
        />
      </div>

      <div className="col-span-8">
        <label className="block text-xs text-slate-400">Folio / Asset Name</label>
        <input
          type="text"
          required
          placeholder="e.g. Flat 101, Swasthi, or 22CT Gold Chain"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white focus:border-emerald-500 focus:outline-none"
        />
      </div>
    </>
  );
};