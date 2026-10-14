// webapp/src/components/subledger/SubledgerBreakdownDrawer.tsx
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { X, Building2, RefreshCw, Plus, Edit2, Search } from 'lucide-react';
import {
  subledgerApi,
  type SubcategoryBreakdownResponse,
  type AssetSubLedgerNode,
} from '../../api/subledger';
import { CandidateMatcherModal } from './CandidateMatcherModal';
import { HistoryDrawerModal } from './HistoryDrawerModal';
import { AssetFormModal } from './AssetFormModal';

export interface SubledgerBreakdownDrawerProps {
  isOpen: boolean;
  subcategory: string | null;
  accountId?: number | string | null;
  workbenchItems?: any[];
  onClose: () => void;
}

export const SubledgerBreakdownDrawer: React.FC<SubledgerBreakdownDrawerProps> = ({
  isOpen,
  subcategory,
  accountId,
  workbenchItems = [],
  onClose,
}) => {
  const [breakdownData, setBreakdownData] = useState<SubcategoryBreakdownResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');

  const [expandedVendors, setExpandedVendors] = useState<Record<string, boolean>>({});

  const [selectedAssetForScan, setSelectedAssetForScan] = useState<AssetSubLedgerNode | null>(null);
  const [selectedVendorForScan, setSelectedVendorForScan] = useState<string>('');
  const [isMatcherOpen, setIsMatcherOpen] = useState<boolean>(false);

  const [historyAsset, setHistoryAsset] = useState<AssetSubLedgerNode | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState<boolean>(false);

  const [isAssetModalOpen, setIsAssetModalOpen] = useState<boolean>(false);
  const [assetToEdit, setAssetToEdit] = useState<AssetSubLedgerNode | null>(null);

  const [loadingAssetId, setLoadingAssetId] = useState<string | null>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (isMatcherOpen || isHistoryOpen || isAssetModalOpen) return;
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isMatcherOpen, isHistoryOpen, isAssetModalOpen, onClose]);

  const fetchBreakdown = useCallback(async () => {
    if (!subcategory) return;
    setLoading(true);
    try {
      const data = await subledgerApi.getSubcategoryBreakdown(subcategory);
      setBreakdownData(data);
    } catch (err) {
      console.error('Failed to load subcategory breakdown:', err);
    } finally {
      setLoading(false);
    }
  }, [subcategory]);

  useEffect(() => {
    if (isOpen && subcategory) {
      fetchBreakdown();
    }
  }, [isOpen, subcategory, fetchBreakdown]);

  const toggleVendor = (vendorKey: string) => {
    setExpandedVendors((prev) => ({
      ...prev,
      [vendorKey]: !prev[vendorKey],
    }));
  };

  const handleCreateAsset = () => {
    setAssetToEdit(null);
    setIsAssetModalOpen(true);
  };

  const handleEditAsset = async (assetId: string) => {
    setLoadingAssetId(assetId);
    try {
      const fullAsset = await subledgerApi.getAssetById(assetId);
      setAssetToEdit(fullAsset);
      setIsAssetModalOpen(true);
    } catch (err) {
      console.error('Failed to load asset details for editing:', err);
    } finally {
      setLoadingAssetId(null);
    }
  };

  const handleLaunchMatcherForAsset = async (assetId: string, vendorName: string) => {
    setLoadingAssetId(assetId);
    try {
      const fullAsset = await subledgerApi.getAssetById(assetId);
      setSelectedAssetForScan(fullAsset);
      setSelectedVendorForScan(vendorName);
      setIsMatcherOpen(true);
    } catch (err) {
      console.error('Failed to load asset details for scanner:', err);
    } finally {
      setLoadingAssetId(null);
    }
  };

  const handleLaunchGlobalSubcategoryScan = () => {
    setSelectedAssetForScan(null);
    setSelectedVendorForScan('');
    setIsMatcherOpen(true);
  };

  const handleOpenHistoryForAsset = async (assetId: string) => {
    setLoadingAssetId(assetId);
    try {
      const fullAsset = await subledgerApi.getAssetById(assetId);
      setHistoryAsset(fullAsset);
      setIsHistoryOpen(true);
    } catch (err) {
      console.error('Failed to load asset details for history:', err);
    } finally {
      setLoadingAssetId(null);
    }
  };

  const groupedAssets = useMemo(() => {
    if (!breakdownData?.assets) return {};

    const q = searchQuery.trim().toLowerCase();
    const filteredAssets = q
      ? breakdownData.assets.filter((a: any) => {
          const nameMatch = (a.name || '').toLowerCase().includes(q);
          const codeMatch = (a.asset_code || '').toLowerCase().includes(q);
          const vendorMatch = (a.vendor_name || a.vendor_detail?.name || a.vendor || '').toLowerCase().includes(q);
          return nameMatch || codeMatch || vendorMatch;
        })
      : breakdownData.assets;

    const groups: Record<
      string,
      {
        vendorName: string;
        assets: typeof breakdownData.assets;
        totalValuation: number;
        totalMapped: number;
      }
    > = {};

    filteredAssets.forEach((asset: any) => {
      const vendorName =
        asset.vendor_name ||
        asset.vendor_detail?.name ||
        (typeof asset.vendor === 'string' && asset.vendor.length > 0 ? asset.vendor : null) ||
        'Independent / Uncategorized';

      const vendorKey =
        asset.vendor_id ||
        asset.vendor_detail?.id ||
        asset.vendor ||
        'uncategorized';

      if (!groups[vendorKey]) {
        groups[vendorKey] = {
          vendorName,
          assets: [],
          totalValuation: 0,
          totalMapped: 0,
        };
      }

      groups[vendorKey].assets.push(asset);
      groups[vendorKey].totalValuation += Number(asset.current_valuation || 0);
      groups[vendorKey].totalMapped += Number(asset.mapped_transaction_total || 0);
    });

    return groups;
  }, [breakdownData, searchQuery]);

  if (!isOpen || !subcategory) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-10000 overflow-hidden bg-black/85 backdrop-blur-sm flex items-center justify-center p-4 font-sans"
      onClick={onClose}
    >
      <div
        className="w-full max-w-6xl h-[90vh] max-h-[96vh] bg-slate-950 border border-slate-800 rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between shrink-0 gap-4">
          <div className="flex items-center space-x-3 shrink-0">
            <div className="p-2 bg-emerald-950/80 border border-emerald-800/60 rounded-xl text-emerald-400">
              <Building2 className="w-5 h-5" />
            </div>
            <div className="flex items-center space-x-2.5">
              <h1 className="text-sm font-mono uppercase tracking-wider font-bold text-white">
                {subcategory}
              </h1>
              <span className="text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800/80 px-2.5 py-0.5 rounded-full font-mono">
                Subledger Operations Hub
              </span>
            </div>
          </div>

          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search assets by folio name, code, or vendor..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-emerald-500/60 font-mono transition-colors"
            />
          </div>

          <div className="flex items-center space-x-2 shrink-0">
            <button
              type="button"
              onClick={handleLaunchGlobalSubcategoryScan}
              className="px-3 py-1.5 bg-cyan-950 hover:bg-cyan-900 text-cyan-300 border border-cyan-800/80 font-mono text-xs font-bold rounded-lg transition-colors cursor-pointer flex items-center space-x-1.5 shadow-sm"
              title="Open scanner across all vendors in this subcategory"
            >
              <Search className="w-3.5 h-3.5" />
              <span>Scan Outflows (All)</span>
            </button>

            <button
              type="button"
              onClick={handleCreateAsset}
              className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs font-bold rounded-lg transition-colors cursor-pointer flex items-center space-x-1.5 shadow-sm"
              title="Register new subledger asset instance"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>New Asset</span>
            </button>

            <button
              type="button"
              onClick={fetchBreakdown}
              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors cursor-pointer"
              title="Refresh Breakdown"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>

            <button
              type="button"
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {breakdownData && (
          <div className="grid grid-cols-4 gap-4 px-6 py-3 bg-slate-900/50 border-b border-slate-800/80 text-xs font-mono shrink-0">
            <div>
              <span className="text-[10px] text-slate-500 uppercase block tracking-wider">Taxonomy Balance</span>
              <span className="font-bold text-slate-200 text-sm">
                ₹{Number(breakdownData.total_taxonomy_balance).toLocaleString('en-IN')}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 uppercase block tracking-wider">Mapped Total</span>
              <span className="font-bold text-emerald-400 text-sm">
                ₹{Number(breakdownData.total_subledger_mapped).toLocaleString('en-IN')}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 uppercase block tracking-wider">Unmapped Variance</span>
              <span className="font-bold text-amber-400 text-sm">
                ₹{Number(breakdownData.unmapped_variance).toLocaleString('en-IN')}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 uppercase block tracking-wider">Asset Instances</span>
              <span className="font-bold text-slate-200 text-sm">
                {breakdownData.asset_count} Registered
              </span>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-5 bg-slate-950 space-y-3 font-mono">
          {loading ? (
            <div className="py-20 text-center text-xs text-slate-400 font-mono flex flex-col items-center gap-2">
              <div className="w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
              <span>Fetching subledger breakdown for {subcategory}...</span>
            </div>
          ) : Object.keys(groupedAssets).length === 0 ? (
            <div className="p-12 border border-dashed border-slate-800 rounded-xl text-center text-slate-500 text-xs font-mono space-y-3">
              <p>{searchQuery ? `No asset folios found matching "${searchQuery}".` : `No asset instances mapped under ${subcategory} yet.`}</p>
              {!searchQuery && (
                <button
                  type="button"
                  onClick={handleCreateAsset}
                  className="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-emerald-400 border border-emerald-500/30 rounded-lg text-xs font-bold font-mono transition-colors cursor-pointer inline-flex items-center gap-1.5"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Register First Asset</span>
                </button>
              )}
            </div>
          ) : (
            Object.entries(groupedAssets).map(([vendorKey, group]) => {
              const isExpanded = expandedVendors[vendorKey] !== false;

              return (
                <div
                  key={vendorKey}
                  className="rounded-xl border border-slate-800/80 bg-slate-900/90 overflow-hidden shadow-lg space-y-0"
                >
                  <div
                    onClick={() => toggleVendor(vendorKey)}
                    className="flex items-center justify-between bg-slate-800/80 px-4 py-3 cursor-pointer hover:bg-slate-800 transition-colors select-none border-b border-slate-800/60"
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-emerald-400">
                        {isExpanded ? '▼' : '▶'}
                      </span>
                      <h3 className="text-sm font-bold text-white flex items-center gap-2">
                        🏬 {group.vendorName}
                        <span className="text-[10px] font-normal text-slate-400 bg-slate-950 px-2 py-0.5 rounded-full border border-slate-700">
                          {group.assets.length} {group.assets.length === 1 ? 'Asset' : 'Assets'}
                        </span>
                      </h3>
                    </div>

                    <div className="flex items-center gap-6 text-xs">
                      <div className="text-right">
                        <span className="text-slate-400 block text-[9px]">TOTAL VALUATION</span>
                        <span className="text-emerald-400 font-bold">
                          ₹{group.totalValuation.toLocaleString('en-IN')}
                        </span>
                      </div>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="border-t border-slate-800/60 bg-slate-950/40">
                      <table className="w-full text-left font-mono text-xs">
                        <thead className="bg-slate-900/40 text-slate-400 uppercase text-[10px] border-b border-slate-800">
                          <tr>
                            <th className="p-2.5">Code</th>
                            <th className="p-2.5">Asset Name</th>
                            <th className="p-2.5 text-right">Valuation</th>
                            <th className="p-2.5 text-right">Mapped Total</th>
                            <th className="p-2.5 text-center">Mapped Count</th>
                            <th className="p-2.5 text-center">Actions</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60 text-slate-300">
                          {group.assets.map((asset: any) => {
                            const assetKey = asset.asset_id || asset.id;
                            return (
                              <tr key={assetKey} className="hover:bg-slate-900/50 transition-colors">
                                <td className="p-2.5 font-bold text-emerald-400">{asset.asset_code}</td>
                                <td className="p-2.5 text-slate-200 font-semibold">{asset.name}</td>
                                <td className="p-2.5 text-right">
                                  ₹{Number(asset.current_valuation || 0).toLocaleString('en-IN')}
                                </td>
                                <td className="p-2.5 text-right text-emerald-400 font-bold">
                                  ₹{Number(asset.mapped_transaction_total || 0).toLocaleString('en-IN')}
                                </td>
                                <td className="p-2.5 text-center text-slate-400">
                                  {asset.mapped_count || 0} entries
                                </td>
                                <td className="p-2.5 text-center">
                                  <div className="flex items-center justify-center space-x-1.5">
                                    <button
                                      type="button"
                                      onClick={() => handleLaunchMatcherForAsset(assetKey, group.vendorName)}
                                      disabled={loadingAssetId === assetKey}
                                      className="px-2 py-1 bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-800/80 text-emerald-400 text-[10px] font-bold rounded transition-all cursor-pointer disabled:opacity-50"
                                      title={`Scan staging lines & bind transactions for ${asset.name}`}
                                    >
                                      {loadingAssetId === assetKey ? 'Loading...' : '🔍 Scan Outflows'}
                                    </button>

                                    <button
                                      type="button"
                                      onClick={() => handleOpenHistoryForAsset(assetKey)}
                                      disabled={loadingAssetId === assetKey}
                                      className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] font-bold rounded transition-all cursor-pointer disabled:opacity-50"
                                      title="View bound transaction history"
                                    >
                                      📜 History
                                    </button>

                                    <button
                                      type="button"
                                      onClick={() => handleEditAsset(assetKey)}
                                      disabled={loadingAssetId === assetKey}
                                      className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-[10px] font-bold rounded transition-all cursor-pointer disabled:opacity-50 flex items-center gap-1"
                                      title="Edit asset details"
                                    >
                                      <Edit2 className="w-3 h-3" />
                                      <span>Edit</span>
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {isMatcherOpen && (
          <CandidateMatcherModal
            isOpen={isMatcherOpen}
            onClose={() => {
              setIsMatcherOpen(false);
              setSelectedAssetForScan(null);
              setSelectedVendorForScan('');
            }}
            asset={selectedAssetForScan}
            accountId={accountId}
            taxonomyContext={{
              category: 'Asset',
              subcategory: subcategory,
              // Prioritize the vendor name token (e.g. "BHIMA") to guarantee keyword highlighting
              defaultKeyword: selectedVendorForScan || (selectedAssetForScan as any)?.vendor_name || '',
              stagedItems: workbenchItems,
              selectedRowIds: workbenchItems.map((r: any) => r.row_identifier || String(r.id)),
            }}
            onSuccess={() => {
              fetchBreakdown();
              setIsMatcherOpen(false);
              setSelectedAssetForScan(null);
              setSelectedVendorForScan('');
            }}
          />
        )}

        {historyAsset && (
          <HistoryDrawerModal
            isOpen={isHistoryOpen}
            onClose={() => {
              setIsHistoryOpen(false);
              setHistoryAsset(null);
            }}
            asset={historyAsset}
          />
        )}

        <AssetFormModal
          isOpen={isAssetModalOpen}
          onClose={() => {
            setIsAssetModalOpen(false);
            setAssetToEdit(null);
          }}
          defaultSubcategory={subcategory}
          assetToEdit={assetToEdit}
          onSuccess={() => {
            fetchBreakdown();
            setIsAssetModalOpen(false);
            setAssetToEdit(null);
          }}
        />
      </div>
    </div>,
    document.body
  );
};

export default SubledgerBreakdownDrawer;