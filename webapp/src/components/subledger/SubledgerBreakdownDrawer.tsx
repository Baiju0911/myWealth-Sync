// webapp/src/components/subledger/SubledgerBreakdownDrawer.tsx
import React, { useEffect, useState, useCallback, useMemo } from 'react';
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
  onClose: () => void;
}

export const SubledgerBreakdownDrawer: React.FC<SubledgerBreakdownDrawerProps> = ({
  isOpen,
  subcategory,
  onClose,
}) => {
  const [breakdownData, setBreakdownData] = useState<SubcategoryBreakdownResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  // Vendor Accordion Collapsed State
  const [expandedVendors, setExpandedVendors] = useState<Record<string, boolean>>({});

  // Candidate Matcher Modal State
  const [selectedAssetForScan, setSelectedAssetForScan] = useState<AssetSubLedgerNode | null>(null);
  const [isMatcherOpen, setIsMatcherOpen] = useState<boolean>(false);

  // History Drawer State
  const [historyAsset, setHistoryAsset] = useState<AssetSubLedgerNode | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState<boolean>(false);

  // Master Asset Form Modal State
  const [isAssetModalOpen, setIsAssetModalOpen] = useState<boolean>(false);
  const [assetToEdit, setAssetToEdit] = useState<AssetSubLedgerNode | null>(null);

  const [loadingAssetId, setLoadingAssetId] = useState<string | null>(null);

  // ESC Key listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (isMatcherOpen || isHistoryOpen || isAssetModalOpen) return;
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isMatcherOpen, isHistoryOpen, isAssetModalOpen, onClose]);

  // Fetch breakdown summary & asset array from backend
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

  // Helper to fetch full asset node payload and launch Edit Form Modal
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

  // Helper to fetch full asset node payload and launch matcher modal
  const handleLaunchMatcherForAsset = async (assetId: string) => {
    setLoadingAssetId(assetId);
    try {
      const fullAsset = await subledgerApi.getAssetById(assetId);
      setSelectedAssetForScan(fullAsset);
      setIsMatcherOpen(true);
    } catch (err) {
      console.error('Failed to load asset details for scanner:', err);
    } finally {
      setLoadingAssetId(null);
    }
  };

  // 🎯 Launch matcher for the entire subcategory without a pre-selected single asset
  const handleLaunchCategoryScan = () => {
    setSelectedAssetForScan(null);
    setIsMatcherOpen(true);
  };

  // Helper to fetch full asset node payload and launch history modal
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

  // Group breakdown assets by Vendor / Counterparty
  const groupedAssets = useMemo(() => {
    if (!breakdownData?.assets) return {};

    const groups: Record<
      string,
      {
        vendorName: string;
        assets: typeof breakdownData.assets;
        totalValuation: number;
        totalMapped: number;
      }
    > = {};

    breakdownData.assets.forEach((asset: any) => {
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
  }, [breakdownData]);

  if (!isOpen || !subcategory) return null;

  return (
    <div
      className="fixed inset-0 z-50 overflow-hidden bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 font-sans"
      onClick={onClose}
    >
      <div
        className="w-full max-w-5xl h-[165vh] max-h-160 bg-slate-950 border border-slate-800 rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header Bar */}
        <div className="px-5 py-3.5 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between shrink-0">
          <div className="flex items-center space-x-3">
            <div className="p-1.5 bg-emerald-950/80 border border-emerald-800/60 rounded-xl text-emerald-400">
              <Building2 className="w-4 h-4" />
            </div>
            <div className="flex items-center space-x-2">
              <h1 className="text-xs font-mono uppercase tracking-wider font-bold text-white">
                {subcategory}
              </h1>
              <span className="text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800/80 px-2 py-0.5 rounded-full font-mono">
                Subledger Operations Hub
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            {/* 🎯 Category-Wide Scan Button */}
            <button
              type="button"
              onClick={handleLaunchCategoryScan}
              className="px-2.5 py-1 bg-cyan-950/80 hover:bg-cyan-900 text-cyan-300 border border-cyan-800/80 font-mono text-xs font-bold rounded-lg transition-colors cursor-pointer flex items-center space-x-1"
              title={`Scan staging lines for all nodes in ${subcategory}`}
            >
              <Search className="w-3.5 h-3.5" />
              <span>Category Scan</span>
            </button>

            <button
              type="button"
              onClick={handleCreateAsset}
              className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs font-bold rounded-lg transition-colors cursor-pointer flex items-center space-x-1"
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
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            </button>

            <button
              type="button"
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Financial KPI Summary Bar */}
        {breakdownData && (
          <div className="grid grid-cols-4 gap-2 px-5 py-2.5 bg-slate-900/50 border-b border-slate-800/80 text-xs font-mono shrink-0">
            <div>
              <span className="text-[10px] text-slate-500 uppercase block">Taxonomy Balance</span>
              <span className="font-bold text-slate-200">
                ₹{Number(breakdownData.total_taxonomy_balance).toLocaleString('en-IN')}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 uppercase block">Mapped Total</span>
              <span className="font-bold text-emerald-400">
                ₹{Number(breakdownData.total_subledger_mapped).toLocaleString('en-IN')}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 uppercase block">Unmapped Variance</span>
              <span className="font-bold text-amber-400">
                ₹{Number(breakdownData.unmapped_variance).toLocaleString('en-IN')}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-slate-500 uppercase block">Asset Instances</span>
              <span className="font-bold text-slate-200">{breakdownData.asset_count} Registered</span>
            </div>
          </div>
        )}

        {/* Content Body: Collapsible Vendor Groups */}
        <div className="flex-1 overflow-y-auto p-4 bg-slate-950 space-y-3 font-mono">
          {loading ? (
            <div className="py-12 text-center text-xs text-slate-400 font-mono">
              Fetching subledger breakdown for {subcategory}...
            </div>
          ) : !breakdownData?.assets || breakdownData.assets.length === 0 ? (
            <div className="p-8 border border-dashed border-slate-800 rounded-xl text-center text-slate-500 text-xs font-mono space-y-3">
              <p>No asset instances mapped under {subcategory} yet.</p>
              <button
                type="button"
                onClick={handleCreateAsset}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-emerald-400 border border-emerald-500/30 rounded-lg text-xs font-bold font-mono transition-colors cursor-pointer inline-flex items-center gap-1.5"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Register First Asset</span>
              </button>
            </div>
          ) : (
            Object.entries(groupedAssets).map(([vendorKey, group]) => {
              const isExpanded = expandedVendors[vendorKey] !== false;

              return (
                <div
                  key={vendorKey}
                  className="rounded-xl border border-slate-800/80 bg-slate-900/90 overflow-hidden shadow-lg space-y-0"
                >
                  {/* Collapsible Vendor Header */}
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

                  {/* Expandable Table Rows */}
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
                            const isClosedOrMatured =
                              asset.status === 'MATURED' ||
                              asset.status === 'CLOSED' ||
                              asset.status === 'LIQUIDATED';

                            const assetId = asset.asset_id || asset.id;

                            return (
                              <tr key={assetId} className="hover:bg-slate-900/50 transition-colors">
                                <td className="p-2.5 font-bold text-emerald-400">{asset.asset_code}</td>
                                <td className="p-2.5 text-slate-200 font-semibold flex items-center gap-2">
                                  <span>{asset.name}</span>
                                  {isClosedOrMatured && (
                                    <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[9px] font-bold text-amber-300 border border-amber-500/40">
                                      🏁 MATURED
                                    </span>
                                  )}
                                </td>
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
                                      onClick={() => handleLaunchMatcherForAsset(assetId)}
                                      disabled={isClosedOrMatured || loadingAssetId === assetId}
                                      className={`px-2 py-1 text-[10px] font-bold rounded transition-all flex items-center gap-1 ${
                                        isClosedOrMatured
                                          ? 'bg-slate-900 border border-slate-800 text-slate-600 cursor-not-allowed opacity-60'
                                          : 'bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-800/80 text-emerald-400 cursor-pointer'
                                      }`}
                                      title={
                                        isClosedOrMatured
                                          ? 'Transaction mapping is locked for matured/closed nodes'
                                          : 'Scan staging lines & bind transactions'
                                      }
                                    >
                                      {loadingAssetId === assetId ? 'Loading...' : '🔍 Scan Outflows'}
                                    </button>

                                    <button
                                      type="button"
                                      onClick={() => handleOpenHistoryForAsset(assetId)}
                                      disabled={loadingAssetId === assetId}
                                      className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] font-bold rounded transition-all cursor-pointer disabled:opacity-50"
                                      title="View bound transaction history"
                                    >
                                      📜 History
                                    </button>

                                    <button
                                      type="button"
                                      onClick={() => handleEditAsset(assetId)}
                                      disabled={loadingAssetId === assetId}
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

        {/* 🎯 Candidate Matcher Modal (Handles both single-asset and category-wide scans) */}
        {isMatcherOpen && (
          <CandidateMatcherModal
            isOpen={isMatcherOpen}
            onClose={() => {
              setIsMatcherOpen(false);
              setSelectedAssetForScan(null);
            }}
            asset={selectedAssetForScan}
            taxonomyContext={{
              category: 'EXPENSE',
              subcategory: subcategory,
              defaultKeyword: subcategory,
            }}
            onSuccess={() => {
              fetchBreakdown();
              setIsMatcherOpen(false);
              setSelectedAssetForScan(null);
            }}
          />
        )}

        {/* History Drawer Modal */}
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

        {/* Master Asset Creation/Edit Form Modal */}
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
    </div>
  );
};

export default SubledgerBreakdownDrawer;


// // webapp/src/components/subledger/SubledgerBreakdownDrawer.tsx
// import React, { useEffect, useState, useCallback, useMemo } from 'react';
// import { X, Building2, RefreshCw, Plus, Edit2 } from 'lucide-react';
// import {
//   subledgerApi,
//   type SubcategoryBreakdownResponse,
//   type AssetSubLedgerNode,
// } from '../../api/subledger';
// import { CandidateMatcherModal } from './CandidateMatcherModal';
// import { HistoryDrawerModal } from './HistoryDrawerModal';
// import { AssetFormModal } from './AssetFormModal';

// export interface SubledgerBreakdownDrawerProps {
//   isOpen: boolean;
//   subcategory: string | null;
//   onClose: () => void;
// }

// export const SubledgerBreakdownDrawer: React.FC<SubledgerBreakdownDrawerProps> = ({
//   isOpen,
//   subcategory,
//   onClose,
// }) => {
//   const [breakdownData, setBreakdownData] = useState<SubcategoryBreakdownResponse | null>(null);
//   const [loading, setLoading] = useState<boolean>(false);

//   // Vendor Accordion Collapsed State
//   const [expandedVendors, setExpandedVendors] = useState<Record<string, boolean>>({});

//   // Candidate Matcher Modal State
//   const [selectedAssetForScan, setSelectedAssetForScan] = useState<AssetSubLedgerNode | null>(null);
//   const [isMatcherOpen, setIsMatcherOpen] = useState<boolean>(false);

//   // History Drawer State
//   const [historyAsset, setHistoryAsset] = useState<AssetSubLedgerNode | null>(null);
//   const [isHistoryOpen, setIsHistoryOpen] = useState<boolean>(false);

//   // Master Asset Form Modal State
//   const [isAssetModalOpen, setIsAssetModalOpen] = useState<boolean>(false);
//   const [assetToEdit, setAssetToEdit] = useState<AssetSubLedgerNode | null>(null);

//   const [loadingAssetId, setLoadingAssetId] = useState<string | null>(null);

//   // ESC Key listener
//   useEffect(() => {
//     const handleKeyDown = (e: KeyboardEvent) => {
//       if (isMatcherOpen || isHistoryOpen || isAssetModalOpen) return;
//       if (e.key === 'Escape') onClose();
//     };
//     if (isOpen) window.addEventListener('keydown', handleKeyDown);
//     return () => window.removeEventListener('keydown', handleKeyDown);
//   }, [isOpen, isMatcherOpen, isHistoryOpen, isAssetModalOpen, onClose]);

//   // Fetch breakdown summary & asset array from backend
//   const fetchBreakdown = useCallback(async () => {
//     if (!subcategory) return;
//     setLoading(true);
//     try {
//       const data = await subledgerApi.getSubcategoryBreakdown(subcategory);
//       setBreakdownData(data);
//     } catch (err) {
//       console.error('Failed to load subcategory breakdown:', err);
//     } finally {
//       setLoading(false);
//     }
//   }, [subcategory]);

//   useEffect(() => {
//     if (isOpen && subcategory) {
//       fetchBreakdown();
//     }
//   }, [isOpen, subcategory, fetchBreakdown]);

//   const toggleVendor = (vendorKey: string) => {
//     setExpandedVendors((prev) => ({
//       ...prev,
//       [vendorKey]: !prev[vendorKey],
//     }));
//   };

//   const handleCreateAsset = () => {
//     setAssetToEdit(null);
//     setIsAssetModalOpen(true);
//   };

//   // ✏️ Helper to fetch full asset node payload and launch Edit Form Modal
//   const handleEditAsset = async (assetId: string) => {
//     setLoadingAssetId(assetId);
//     try {
//       const fullAsset = await subledgerApi.getAssetById(assetId);
//       setAssetToEdit(fullAsset);
//       setIsAssetModalOpen(true);
//     } catch (err) {
//       console.error('Failed to load asset details for editing:', err);
//     } finally {
//       setLoadingAssetId(null);
//     }
//   };

//   // Helper to fetch full asset node payload and launch matcher modal
//   const handleLaunchMatcherForAsset = async (assetId: string) => {
//     setLoadingAssetId(assetId);
//     try {
//       const fullAsset = await subledgerApi.getAssetById(assetId);
//       setSelectedAssetForScan(fullAsset);
//       setIsMatcherOpen(true);
//     } catch (err) {
//       console.error('Failed to load asset details for scanner:', err);
//     } finally {
//       setLoadingAssetId(null);
//     }
//   };

//   // Helper to fetch full asset node payload and launch history modal
//   const handleOpenHistoryForAsset = async (assetId: string) => {
//     setLoadingAssetId(assetId);
//     try {
//       const fullAsset = await subledgerApi.getAssetById(assetId);
//       setHistoryAsset(fullAsset);
//       setIsHistoryOpen(true);
//     } catch (err) {
//       console.error('Failed to load asset details for history:', err);
//     } finally {
//       setLoadingAssetId(null);
//     }
//   };

//   // Group breakdown assets by Vendor / Counterparty
//   const groupedAssets = useMemo(() => {
//     if (!breakdownData?.assets) return {};

//     const groups: Record<
//       string,
//       {
//         vendorName: string;
//         assets: typeof breakdownData.assets;
//         totalValuation: number;
//         totalMapped: number;
//       }
//     > = {};

//     breakdownData.assets.forEach((asset: any) => {
//       const vendorName =
//         asset.vendor_name ||
//         asset.vendor_detail?.name ||
//         (typeof asset.vendor === 'string' && asset.vendor.length > 0 ? asset.vendor : null) ||
//         'Independent / Uncategorized';

//       const vendorKey =
//         asset.vendor_id ||
//         asset.vendor_detail?.id ||
//         asset.vendor ||
//         'uncategorized';

//       if (!groups[vendorKey]) {
//         groups[vendorKey] = {
//           vendorName,
//           assets: [],
//           totalValuation: 0,
//           totalMapped: 0,
//         };
//       }

//       groups[vendorKey].assets.push(asset);
//       groups[vendorKey].totalValuation += Number(asset.current_valuation || 0);
//       groups[vendorKey].totalMapped += Number(asset.mapped_transaction_total || 0);
//     });

//     return groups;
//   }, [breakdownData]);

//   if (!isOpen || !subcategory) return null;

//   return (
//     <div
//       className="fixed inset-0 z-50 overflow-hidden bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 font-sans"
//       onClick={onClose}
//     >
//       <div
//         className="w-full max-w-4xl h-[78vh] max-h-95 bg-slate-950 border border-slate-800 rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200"
//         onClick={(e) => e.stopPropagation()}
//       >
//         {/* Header Bar */}
//         <div className="px-5 py-3.5 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between shrink-0">
//           <div className="flex items-center space-x-3">
//             <div className="p-1.5 bg-emerald-950/80 border border-emerald-800/60 rounded-xl text-emerald-400">
//               <Building2 className="w-4 h-4" />
//             </div>
//             <div className="flex items-center space-x-2">
//               <h1 className="text-xs font-mono uppercase tracking-wider font-bold text-white">
//                 {subcategory}
//               </h1>
//               <span className="text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800/80 px-2 py-0.5 rounded-full font-mono">
//                 Subledger Operations Hub
//               </span>
//             </div>
//           </div>

//           <div className="flex items-center space-x-2">
//             <button
//               type="button"
//               onClick={handleCreateAsset}
//               className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs font-bold rounded-lg transition-colors cursor-pointer flex items-center space-x-1"
//               title="Register new subledger asset instance"
//             >
//               <Plus className="w-3.5 h-3.5" />
//               <span>New Asset</span>
//             </button>

//             <button
//               type="button"
//               onClick={fetchBreakdown}
//               className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors cursor-pointer"
//               title="Refresh Breakdown"
//             >
//               <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
//             </button>

//             <button
//               type="button"
//               onClick={onClose}
//               className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors cursor-pointer"
//             >
//               <X className="w-4 h-4" />
//             </button>
//           </div>
//         </div>

//         {/* Financial KPI Summary Bar */}
//         {breakdownData && (
//           <div className="grid grid-cols-4 gap-2 px-5 py-2.5 bg-slate-900/50 border-b border-slate-800/80 text-xs font-mono shrink-0">
//             <div>
//               <span className="text-[10px] text-slate-500 uppercase block">Taxonomy Balance</span>
//               <span className="font-bold text-slate-200">
//                 ₹{Number(breakdownData.total_taxonomy_balance).toLocaleString('en-IN')}
//               </span>
//             </div>
//             <div>
//               <span className="text-[10px] text-slate-500 uppercase block">Mapped Total</span>
//               <span className="font-bold text-emerald-400">
//                 ₹{Number(breakdownData.total_subledger_mapped).toLocaleString('en-IN')}
//               </span>
//             </div>
//             <div>
//               <span className="text-[10px] text-slate-500 uppercase block">Unmapped Variance</span>
//               <span className="font-bold text-amber-400">
//                 ₹{Number(breakdownData.unmapped_variance).toLocaleString('en-IN')}
//               </span>
//             </div>
//             <div>
//               <span className="text-[10px] text-slate-500 uppercase block">Asset Instances</span>
//               <span className="font-bold text-slate-200">{breakdownData.asset_count} Registered</span>
//             </div>
//           </div>
//         )}

//         {/* Content Body: Collapsible Vendor Groups */}
//         <div className="flex-1 overflow-y-auto p-4 bg-slate-950 space-y-3 font-mono">
//           {loading ? (
//             <div className="py-12 text-center text-xs text-slate-400 font-mono">
//               Fetching subledger breakdown for {subcategory}...
//             </div>
//           ) : !breakdownData?.assets || breakdownData.assets.length === 0 ? (
//             <div className="p-8 border border-dashed border-slate-800 rounded-xl text-center text-slate-500 text-xs font-mono space-y-3">
//               <p>No asset instances mapped under {subcategory} yet.</p>
//               <button
//                 type="button"
//                 onClick={handleCreateAsset}
//                 className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-emerald-400 border border-emerald-500/30 rounded-lg text-xs font-bold font-mono transition-colors cursor-pointer inline-flex items-center gap-1.5"
//               >
//                 <Plus className="w-3.5 h-3.5" />
//                 <span>Register First Asset</span>
//               </button>
//             </div>
//           ) : (
//             Object.entries(groupedAssets).map(([vendorKey, group]) => {
//               const isExpanded = expandedVendors[vendorKey] !== false;

//               return (
//                 <div
//                   key={vendorKey}
//                   className="rounded-xl border border-slate-800/80 bg-slate-900/90 overflow-hidden shadow-lg space-y-0"
//                 >
//                   {/* Collapsible Vendor Header */}
//                   <div
//                     onClick={() => toggleVendor(vendorKey)}
//                     className="flex items-center justify-between bg-slate-800/80 px-4 py-3 cursor-pointer hover:bg-slate-800 transition-colors select-none border-b border-slate-800/60"
//                   >
//                     <div className="flex items-center gap-3">
//                       <span className="text-xs text-emerald-400">
//                         {isExpanded ? '▼' : '▶'}
//                       </span>
//                       <h3 className="text-sm font-bold text-white flex items-center gap-2">
//                         🏬 {group.vendorName}
//                         <span className="text-[10px] font-normal text-slate-400 bg-slate-950 px-2 py-0.5 rounded-full border border-slate-700">
//                           {group.assets.length} {group.assets.length === 1 ? 'Asset' : 'Assets'}
//                         </span>
//                       </h3>
//                     </div>

//                     <div className="flex items-center gap-6 text-xs">
//                       <div className="text-right">
//                         <span className="text-slate-400 block text-[9px]">TOTAL VALUATION</span>
//                         <span className="text-emerald-400 font-bold">
//                           ₹{group.totalValuation.toLocaleString('en-IN')}
//                         </span>
//                       </div>
//                     </div>
//                   </div>

//                   {/* Expandable Table Rows */}
//                   {isExpanded && (
//                     <div className="border-t border-slate-800/60 bg-slate-950/40">
//                       <table className="w-full text-left font-mono text-xs">
//                         <thead className="bg-slate-900/40 text-slate-400 uppercase text-[10px] border-b border-slate-800">
//                           <tr>
//                             <th className="p-2.5">Code</th>
//                             <th className="p-2.5">Asset Name</th>
//                             <th className="p-2.5 text-right">Valuation</th>
//                             <th className="p-2.5 text-right">Mapped Total</th>
//                             <th className="p-2.5 text-center">Mapped Count</th>
//                             <th className="p-2.5 text-center">Actions</th>
//                           </tr>
//                         </thead>
//                        <tbody className="divide-y divide-slate-800/60 text-slate-300">
//   {group.assets.map((asset: any) => {
//     // 🎯 Lifecycle Status Lock Check
//     const isClosedOrMatured =
//       asset.status === 'MATURED' ||
//       asset.status === 'CLOSED' ||
//       asset.status === 'LIQUIDATED';

//     const assetId = asset.asset_id || asset.id;

//     return (
//       <tr key={assetId} className="hover:bg-slate-900/50 transition-colors">
//         <td className="p-2.5 font-bold text-emerald-400">{asset.asset_code}</td>
//         <td className="p-2.5 text-slate-200 font-semibold flex items-center gap-2">
//           <span>{asset.name}</span>
//           {isClosedOrMatured && (
//             <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[9px] font-bold text-amber-300 border border-amber-500/40">
//               🏁 MATURED
//             </span>
//           )}
//         </td>
//         <td className="p-2.5 text-right">
//           ₹{Number(asset.current_valuation || 0).toLocaleString('en-IN')}
//         </td>
//         <td className="p-2.5 text-right text-emerald-400 font-bold">
//           ₹{Number(asset.mapped_transaction_total || 0).toLocaleString('en-IN')}
//         </td>
//         <td className="p-2.5 text-center text-slate-400">
//           {asset.mapped_count || 0} entries
//         </td>
//         <td className="p-2.5 text-center">
//           <div className="flex items-center justify-center space-x-1.5">
//             {/* 🎯 Scan Outflows Button (Locked if Matured) */}
//             <button
//               type="button"
//               onClick={() => handleLaunchMatcherForAsset(assetId)}
//               disabled={isClosedOrMatured || loadingAssetId === assetId}
//               className={`px-2 py-1 text-[10px] font-bold rounded transition-all flex items-center gap-1 ${
//                 isClosedOrMatured
//                   ? 'bg-slate-900 border border-slate-800 text-slate-600 cursor-not-allowed opacity-60'
//                   : 'bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-800/80 text-emerald-400 cursor-pointer'
//               }`}
//               title={
//                 isClosedOrMatured
//                   ? 'Transaction mapping is locked for matured/closed nodes'
//                   : 'Scan staging lines & bind transactions'
//               }
//             >
//               {loadingAssetId === assetId ? 'Loading...' : '🔍 Scan Outflows'}
//             </button>

//             {/* History Button (Always Enabled) */}
//             <button
//               type="button"
//               onClick={() => handleOpenHistoryForAsset(assetId)}
//               disabled={loadingAssetId === assetId}
//               className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] font-bold rounded transition-all cursor-pointer disabled:opacity-50"
//               title="View bound transaction history"
//             >
//               📜 History
//             </button>

//             {/* Edit Asset Action */}
//             <button
//               type="button"
//               onClick={() => handleEditAsset(assetId)}
//               disabled={loadingAssetId === assetId}
//               className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-[10px] font-bold rounded transition-all cursor-pointer disabled:opacity-50 flex items-center gap-1"
//               title="Edit asset details"
//             >
//               <Edit2 className="w-3 h-3" />
//               <span>Edit</span>
//             </button>
//           </div>
//         </td>
//       </tr>
//     );
//   })}
// </tbody>
//                       </table>
//                     </div>
//                   )}
//                 </div>
//               );
//             })
//           )}
//         </div>

//         {/* Candidate Matcher Modal */}
//         {selectedAssetForScan && (
//           <CandidateMatcherModal
//             isOpen={isMatcherOpen}
//             onClose={() => {
//               setIsMatcherOpen(false);
//               setSelectedAssetForScan(null);
//             }}
//             asset={selectedAssetForScan}
//             onSuccess={() => {
//               fetchBreakdown();
//               setIsMatcherOpen(false);
//               setSelectedAssetForScan(null);
//             }}
//           />
//         )}

//         {/* History Drawer Modal */}
//         {historyAsset && (
//           <HistoryDrawerModal
//             isOpen={isHistoryOpen}
//             onClose={() => {
//               setIsHistoryOpen(false);
//               setHistoryAsset(null);
//             }}
//             asset={historyAsset}
//           />
//         )}

//         {/* Master Asset Creation/Edit Form Modal */}
//         <AssetFormModal
//           isOpen={isAssetModalOpen}
//           onClose={() => {
//             setIsAssetModalOpen(false);
//             setAssetToEdit(null);
//           }}
//           defaultSubcategory={subcategory}
//           assetToEdit={assetToEdit}
//           onSuccess={() => {
//             fetchBreakdown();
//             setIsAssetModalOpen(false);
//             setAssetToEdit(null);
//           }}
//         />
//       </div>
//     </div>
//   );
// };

// export default SubledgerBreakdownDrawer;




// // webapp/src/components/subledger/SubledgerBreakdownDrawer.tsx
// import React, { useEffect, useState, useCallback } from 'react';
// import { X, Building2, RefreshCw, Plus } from 'lucide-react';
// import {
//   subledgerApi,
//   type SubcategoryBreakdownResponse,
//   type AssetSubLedgerNode,
// } from '../../api/subledger';
// import { CandidateMatcherModal } from './CandidateMatcherModal';
// import { HistoryDrawerModal } from './HistoryDrawerModal';
// import { AssetFormModal } from './AssetFormModal';

// interface SubledgerBreakdownDrawerProps {
//   isOpen: boolean;
//   subcategory: string | null;
//   onClose: () => void;
// }

// export const SubledgerBreakdownDrawer: React.FC<SubledgerBreakdownDrawerProps> = ({
//   isOpen,
//   subcategory,
//   onClose,
// }) => {
//   const [breakdownData, setBreakdownData] = useState<SubcategoryBreakdownResponse | null>(null);
//   const [loading, setLoading] = useState<boolean>(false);

//   // Candidate Matcher Modal State
//   const [selectedAssetForScan, setSelectedAssetForScan] = useState<AssetSubLedgerNode | null>(null);
//   const [isMatcherOpen, setIsMatcherOpen] = useState<boolean>(false);

//   // History Drawer State
//   const [historyAsset, setHistoryAsset] = useState<AssetSubLedgerNode | null>(null);
//   const [isHistoryOpen, setIsHistoryOpen] = useState<boolean>(false);

//   // Master Asset Form Modal State
//   const [isAssetModalOpen, setIsAssetModalOpen] = useState<boolean>(false);
//   const [assetToEdit, setAssetToEdit] = useState<AssetSubLedgerNode | null>(null);

//   const [loadingAssetId, setLoadingAssetId] = useState<string | null>(null);

//   // ESC key listener
//   useEffect(() => {
//     const handleKeyDown = (e: KeyboardEvent) => {
//       // If a child modal is active, let the child handle ESC
//       if (isMatcherOpen || isHistoryOpen || isAssetModalOpen) return;

//       if (e.key === 'Escape') onClose();
//     };
//     if (isOpen) window.addEventListener('keydown', handleKeyDown);
//     return () => window.removeEventListener('keydown', handleKeyDown);
//   }, [isOpen, isMatcherOpen, isHistoryOpen, isAssetModalOpen, onClose]);

//   // Fetch breakdown summary data
//   const fetchBreakdown = useCallback(async () => {
//     if (!subcategory) return;
//     setLoading(true);
//     try {
//       const data = await subledgerApi.getSubcategoryBreakdown(subcategory);
//       setBreakdownData(data);
//     } catch (err) {
//       console.error('Failed to load subcategory breakdown:', err);
//     } finally {
//       setLoading(false);
//     }
//   }, [subcategory]);

//   useEffect(() => {
//     if (isOpen && subcategory) {
//       fetchBreakdown();
//     }
//   }, [isOpen, subcategory, fetchBreakdown]);

//   const handleCreateAsset = () => {
//     setAssetToEdit(null);
//     setIsAssetModalOpen(true);
//   };

//   // Helper to fetch full asset node payload and launch matcher
//   const handleLaunchMatcherForAsset = async (assetId: string) => {
//     setLoadingAssetId(assetId);
//     try {
//       const fullAsset = await subledgerApi.getAssetById(assetId);
//       setSelectedAssetForScan(fullAsset);
//       setIsMatcherOpen(true);
//     } catch (err) {
//       console.error('Failed to load asset details for scanner:', err);
//     } finally {
//       setLoadingAssetId(null);
//     }
//   };

//   // Helper to fetch full asset node payload and launch history
//   const handleOpenHistoryForAsset = async (assetId: string) => {
//     setLoadingAssetId(assetId);
//     try {
//       const fullAsset = await subledgerApi.getAssetById(assetId);
//       setHistoryAsset(fullAsset);
//       setIsHistoryOpen(true);
//     } catch (err) {
//       console.error('Failed to load asset details for history:', err);
//     } finally {
//       setLoadingAssetId(null);
//     }
//   };

//   if (!isOpen || !subcategory) return null;

//   return (
//     <div 
//       className="fixed inset-0 z-50 overflow-hidden bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
//       onClick={onClose}
//     >
//       <div 
//         className="w-full max-w-4xl h-[72vh] max-h-[720px] bg-slate-950 border border-slate-800 rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200"
//         onClick={(e) => e.stopPropagation()}
//       >
//         {/* Header Bar */}
//         <div className="px-5 py-3.5 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between shrink-0 font-sans">
//           <div className="flex items-center space-x-3">
//             <div className="p-1.5 bg-emerald-950/80 border border-emerald-800/60 rounded-xl text-emerald-400">
//               <Building2 className="w-4 h-4" />
//             </div>
//             <div className="flex items-center space-x-2">
//               <h1 className="text-xs font-mono uppercase tracking-wider font-bold text-white">
//                 {subcategory}
//               </h1>
//               <span className="text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800/80 px-2 py-0.5 rounded-full font-mono">
//                 Subledger Operations Hub
//               </span>
//             </div>
//           </div>

//           <div className="flex items-center space-x-2">
//             {/* ➕ New Asset Trigger Button */}
//             <button
//               type="button"
//               onClick={handleCreateAsset}
//               className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs font-bold rounded-lg transition-colors cursor-pointer flex items-center space-x-1"
//               title="Register new subledger asset instance"
//             >
//               <Plus className="w-3.5 h-3.5" />
//               <span>New Asset</span>
//             </button>

//             <button
//               type="button"
//               onClick={fetchBreakdown}
//               className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors cursor-pointer"
//               title="Refresh Breakdown"
//             >
//               <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
//             </button>

//             <button
//               type="button"
//               onClick={onClose}
//               className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors cursor-pointer"
//             >
//               <X className="w-4 h-4" />
//             </button>
//           </div>
//         </div>

//         {/* Financial KPI Summary Bar */}
//         {breakdownData && (
//           <div className="grid grid-cols-4 gap-2 px-5 py-2.5 bg-slate-900/50 border-b border-slate-800/80 text-xs font-mono shrink-0">
//             <div>
//               <span className="text-[10px] text-slate-500 uppercase block">Taxonomy Balance</span>
//               <span className="font-bold text-slate-200">
//                 ₹{Number(breakdownData.total_taxonomy_balance).toLocaleString('en-IN')}
//               </span>
//             </div>
//             <div>
//               <span className="text-[10px] text-slate-500 uppercase block">Mapped Total</span>
//               <span className="font-bold text-emerald-400">
//                 ₹{Number(breakdownData.total_subledger_mapped).toLocaleString('en-IN')}
//               </span>
//             </div>
//             <div>
//               <span className="text-[10px] text-slate-500 uppercase block">Unmapped Variance</span>
//               <span className="font-bold text-amber-400">
//                 ₹{Number(breakdownData.unmapped_variance).toLocaleString('en-IN')}
//               </span>
//             </div>
//             <div>
//               <span className="text-[10px] text-slate-500 uppercase block">Asset Instances</span>
//               <span className="font-bold text-slate-200">{breakdownData.asset_count} Registered</span>
//             </div>
//           </div>
//         )}

//         {/* Content Body: Streamlined Asset Table */}
//         <div className="flex-1 overflow-y-auto p-4 bg-slate-950 space-y-3">
//           {loading ? (
//             <div className="py-12 text-center text-xs text-slate-400 font-mono">
//               Fetching subledger breakdown for {subcategory}...
//             </div>
//           ) : !breakdownData?.assets || breakdownData.assets.length === 0 ? (
//             <div className="p-8 border border-dashed border-slate-800 rounded-xl text-center text-slate-500 text-xs font-mono space-y-3">
//               <p>No asset instances mapped under {subcategory} yet.</p>
//               <button
//                 type="button"
//                 onClick={handleCreateAsset}
//                 className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-emerald-400 border border-emerald-500/30 rounded-lg text-xs font-bold font-mono transition-colors cursor-pointer inline-flex items-center gap-1.5"
//               >
//                 <Plus className="w-3.5 h-3.5" />
//                 <span>Register First Asset</span>
//               </button>
//             </div>
//           ) : (
//             <div className="border border-slate-800 rounded-xl overflow-hidden">
//               <table className="w-full text-left font-mono text-xs">
//                 <thead className="bg-slate-900/80 text-slate-400 uppercase text-[10px] border-b border-slate-800">
//                   <tr>
//                     <th className="p-2.5">Code</th>
//                     <th className="p-2.5">Asset Name</th>
//                     <th className="p-2.5 text-right">Valuation</th>
//                     <th className="p-2.5 text-right">Mapped Total</th>
//                     <th className="p-2.5 text-center">Mapped Count</th>
//                     <th className="p-2.5 text-center">Actions</th>
//                   </tr>
//                 </thead>
//                 <tbody className="divide-y divide-slate-800/60 bg-slate-950 text-slate-300">
//                   {breakdownData.assets.map((asset) => (
//                     <tr key={asset.asset_id} className="hover:bg-slate-900/50">
//                       <td className="p-2.5 font-bold text-emerald-400">{asset.asset_code}</td>
//                       <td className="p-2.5 text-slate-200 font-semibold">{asset.name}</td>
//                       <td className="p-2.5 text-right font-mono">
//                         ₹{Number(asset.current_valuation).toLocaleString('en-IN')}
//                       </td>
//                       <td className="p-2.5 text-right font-mono text-emerald-400 font-bold">
//                         ₹{Number(asset.mapped_transaction_total).toLocaleString('en-IN')}
//                       </td>
//                       <td className="p-2.5 text-center font-mono text-slate-400">
//                         {asset.mapped_count} entries
//                       </td>
//                       <td className="p-2.5 text-center">
//                         <div className="flex items-center justify-center space-x-1.5">
//                           <button
//                             type="button"
//                             onClick={() => handleLaunchMatcherForAsset(asset.asset_id)}
//                             disabled={loadingAssetId === asset.asset_id}
//                             className="px-2 py-1 bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-800/80 text-emerald-400 font-mono text-[10px] font-bold rounded transition-all cursor-pointer disabled:opacity-50"
//                             title="Scan staging lines & bind transactions"
//                           >
//                             {loadingAssetId === asset.asset_id ? 'Loading...' : '🔍 Scan Outflows'}
//                           </button>

//                           <button
//                             type="button"
//                             onClick={() => handleOpenHistoryForAsset(asset.asset_id)}
//                             disabled={loadingAssetId === asset.asset_id}
//                             className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 font-mono text-[10px] font-bold rounded transition-all cursor-pointer disabled:opacity-50"
//                             title="View bound transaction history"
//                           >
//                             📜 History
//                           </button>
//                         </div>
//                       </td>
//                     </tr>
//                   ))}
//                 </tbody>
//               </table>
//             </div>
//           )}
//         </div>
//       </div>

//       {/* Candidate Matcher Modal */}
//       {selectedAssetForScan && (
//         <CandidateMatcherModal
//           isOpen={isMatcherOpen}
//           onClose={() => {
//             setIsMatcherOpen(false);
//             setSelectedAssetForScan(null);
//           }}
//           asset={selectedAssetForScan}
//           onSuccess={() => {
//             fetchBreakdown();
//             setIsMatcherOpen(false);
//             setSelectedAssetForScan(null);
//           }}
//         />
//       )}

//       {/* History Drawer Modal */}
//       {historyAsset && (
//         <HistoryDrawerModal
//           isOpen={isHistoryOpen}
//           onClose={() => {
//             setIsHistoryOpen(false);
//             setHistoryAsset(null);
//           }}
//           asset={historyAsset}
//         />
//       )}

//       {/* Master Asset Creation/Edit Form Modal */}
//         {/* Master Asset Creation/Edit Form Modal */}
//         <AssetFormModal
//         isOpen={isAssetModalOpen}
//         onClose={() => {
//             setIsAssetModalOpen(false);
//             setAssetToEdit(null);
//         }}
//         defaultSubcategory={subcategory} // 🎯 Pre-selects active subcategory automatically
//         assetToEdit={assetToEdit}
//         onSuccess={() => {
//             fetchBreakdown();
//             setIsAssetModalOpen(false);
//             setAssetToEdit(null);
//         }}
//         />
//     </div>
//   );
// };

// export default SubledgerBreakdownDrawer;



// // webapp/src/components/subledger/SubledgerBreakdownDrawer.tsx
// import React, { useEffect, useState, useCallback } from 'react';
// import { 
//   X, 
//   Building2, 
//   Plus, 
//   AlertCircle, 
//   ExternalLink, 
//   RefreshCw 
// } from 'lucide-react';

// // 🎯 Route all requests strictly through central API layer
// import { 
//   subledgerApi, 
//   type SubcategoryBreakdownResponse 
// } from '../../api/subledger';

// interface SubledgerBreakdownDrawerProps {
//   isOpen: boolean;
//   subcategory: string | null;
//   onClose: () => void;
//   onOpenAssetModal?: (assetId?: string) => void;
// }

// export const SubledgerBreakdownDrawer: React.FC<SubledgerBreakdownDrawerProps> = ({
//   isOpen,
//   subcategory,
//   onClose,
//   onOpenAssetModal
// }) => {
//   const [data, setData] = useState<SubcategoryBreakdownResponse | null>(null);
//   const [loading, setLoading] = useState<boolean>(false);
//   const [error, setError] = useState<string | null>(null);

//   const fetchBreakdown = useCallback(async () => {
//     if (!subcategory) return;
//     setLoading(true);
//     setError(null);
//     try {
//       // 🚀 Clean API call through subledgerApi service
//       const breakdownData = await subledgerApi.getSubcategoryBreakdown(subcategory);
//       setData(breakdownData);
//     } catch (err: any) {
//       console.error('Failed to fetch subcategory breakdown:', err);
//       setError('Unable to load asset breakdown for this subcategory.');
//     } finally {
//       setLoading(false);
//     }
//   }, [subcategory]);

//   useEffect(() => {
//     if (isOpen && subcategory) {
//       fetchBreakdown();
//     }
//   }, [isOpen, subcategory, fetchBreakdown]);

//   if (!isOpen || !subcategory) return null;

//   const formatINR = (val: number) => 
//     new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(val || 0);

//   return (
//     <div className="fixed inset-0 z-50 overflow-hidden bg-black/60 backdrop-blur-xs flex justify-end transition-opacity duration-300">
//       <div className="w-full max-w-2xl bg-zinc-950 border-l border-zinc-800 h-full flex flex-col shadow-2xl">
        
//         {/* Header */}
//         <div className="p-4 border-b border-zinc-800 flex items-center justify-between bg-zinc-900/50">
//           <div className="flex items-center space-x-3">
//             <div className="p-2 bg-cyan-950/80 border border-cyan-800/60 rounded-lg text-cyan-400">
//               <Building2 className="w-5 h-5" />
//             </div>
//             <div>
//               <h2 className="text-sm font-mono uppercase tracking-wider font-bold text-zinc-100 flex items-center gap-2">
//                 <span>{subcategory}</span>
//                 <span className="text-[10px] bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded-full normal-case font-normal">
//                   Sub-Ledger Hub
//                 </span>
//               </h2>
//               <p className="text-[11px] text-zinc-400 font-mono">
//                 Asset instances and double-entry reconciliation matrix
//               </p>
//             </div>
//           </div>

//           <div className="flex items-center space-x-2">
//             <button
//               type="button"
//               onClick={fetchBreakdown}
//               className="p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg transition-colors cursor-pointer"
//               title="Refresh"
//             >
//               <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-cyan-400' : ''}`} />
//             </button>
//             <button
//               type="button"
//               onClick={onClose}
//               className="p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg transition-colors cursor-pointer"
//             >
//               <X className="w-5 h-5" />
//             </button>
//           </div>
//         </div>

//         {/* Content Body */}
//         <div className="flex-1 overflow-y-auto p-4 space-y-4 font-mono text-xs">
//           {loading && (
//             <div className="flex flex-col items-center justify-center py-16 text-zinc-500 gap-2">
//               <div className="animate-spin rounded-full h-7 w-7 border-b-2 border-cyan-400" />
//               <p className="text-[11px] tracking-wider">LOADING SUB-LEDGER BALANCES...</p>
//             </div>
//           )}

//           {error && (
//             <div className="p-3 bg-rose-950/40 border border-rose-800 rounded-xl text-rose-300 flex items-center space-x-2">
//               <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
//               <span>{error}</span>
//             </div>
//           )}

//           {!loading && data && (
//             <>
//               {/* Reconciliation Cards */}
//               <div className="grid grid-cols-3 gap-3">
//                 <div className="bg-zinc-900/80 border border-zinc-800 p-3 rounded-xl space-y-1">
//                   <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">GL Balance</span>
//                   <p className="text-sm font-bold text-zinc-100">{formatINR(data.total_taxonomy_balance)}</p>
//                 </div>

//                 <div className="bg-zinc-900/80 border border-zinc-800 p-3 rounded-xl space-y-1">
//                   <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Subledger Mapped</span>
//                   <p className="text-sm font-bold text-emerald-400">{formatINR(data.total_subledger_mapped)}</p>
//                 </div>

//                 <div className="bg-zinc-900/80 border border-zinc-800 p-3 rounded-xl space-y-1">
//                   <span className="text-[10px] text-zinc-400 uppercase tracking-wider block">Unmapped Variance</span>
//                   <p className={`text-sm font-bold ${data.unmapped_variance > 0 ? 'text-amber-400' : 'text-zinc-400'}`}>
//                     {formatINR(data.unmapped_variance)}
//                   </p>
//                 </div>
//               </div>

//               {/* Action Bar */}
//               <div className="flex items-center justify-between pt-2">
//                 <span className="text-zinc-400 font-bold uppercase text-[10px] tracking-wider">
//                   Registered Assets ({data.asset_count})
//                 </span>
                
//                 {onOpenAssetModal && (
//                   <button
//                     type="button"
//                     onClick={() => onOpenAssetModal()}
//                     className="flex items-center space-x-1 px-2.5 py-1 bg-cyan-500 hover:bg-cyan-400 text-zinc-950 font-bold rounded-lg transition-colors text-[11px] cursor-pointer"
//                   >
//                     <Plus className="w-3.5 h-3.5" />
//                     <span>New Asset Instance</span>
//                   </button>
//                 )}
//               </div>

//               {/* Asset Instance Cards */}
//               {data.assets.length === 0 ? (
//                 <div className="p-8 border border-dashed border-zinc-800 rounded-xl text-center space-y-3">
//                   <Building2 className="w-8 h-8 text-zinc-600 mx-auto" />
//                   <p className="text-zinc-400">No assets registered under {subcategory} yet.</p>
//                   {onOpenAssetModal && (
//                     <button
//                       type="button"
//                       onClick={() => onOpenAssetModal()}
//                       className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-cyan-400 rounded-lg font-bold text-xs"
//                     >
//                       Register First Asset
//                     </button>
//                   )}
//                 </div>
//               ) : (
//                 <div className="space-y-3">
//                   {data.assets.map((asset) => (
//                     <div
//                       key={asset.asset_id}
//                       className="bg-zinc-900/60 border border-zinc-800/80 hover:border-zinc-700 p-4 rounded-xl space-y-3 transition-all"
//                     >
//                       <div className="flex items-start justify-between">
//                         <div>
//                           <div className="flex items-center space-x-2">
//                             <span className="font-bold text-zinc-100 text-sm">{asset.name}</span>
//                             <span className="px-1.5 py-0.5 bg-zinc-800 text-zinc-400 rounded-md text-[10px] uppercase">
//                               {asset.asset_code}
//                             </span>
//                           </div>
//                           <span className="text-[10px] text-zinc-400">Status: {asset.status}</span>
//                         </div>

//                         {onOpenAssetModal && (
//                           <button
//                             type="button"
//                             onClick={() => onOpenAssetModal(asset.asset_id)}
//                             className="p-1 text-zinc-400 hover:text-cyan-400 hover:bg-zinc-800 rounded transition-colors"
//                             title="Edit Asset Details"
//                           >
//                             <ExternalLink className="w-3.5 h-3.5" />
//                           </button>
//                         )}
//                       </div>

//                       <div className="grid grid-cols-3 gap-2 bg-zinc-950 p-2.5 rounded-lg border border-zinc-900 text-[11px]">
//                         <div>
//                           <span className="text-zinc-400 text-[9px] block uppercase">Acquisition Cost</span>
//                           <span className="text-zinc-200">{formatINR(asset.acquisition_cost)}</span>
//                         </div>
//                         <div>
//                           <span className="text-zinc-400 text-[9px] block uppercase">Valuation</span>
//                           <span className="text-zinc-200">{formatINR(asset.current_valuation)}</span>
//                         </div>
//                         <div>
//                           <span className="text-zinc-400 text-[9px] block uppercase">Mapped Lines</span>
//                           <span className="text-emerald-400 font-bold">{asset.mapped_count} ({formatINR(asset.mapped_transaction_total)})</span>
//                         </div>
//                       </div>
//                     </div>
//                   ))}
//                 </div>
//               )}
//             </>
//           )}
//         </div>
//       </div>
//     </div>
//   );
// };

// export default SubledgerBreakdownDrawer;