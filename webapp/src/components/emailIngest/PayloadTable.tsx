import React, { useState, useMemo } from 'react';
import { type EmailPayload, type TaxonomyOption } from '../../api/emailIngestApi';

interface Props {
  payloads: EmailPayload[];
  selectedIds: string[];
  taxonomyTree?: TaxonomyOption[];
  onSelectPayload: (payload: EmailPayload) => void;
  onToggleSelectAll: () => void;
  onToggleSelectOne: (id: string) => void;
  onUpdateTaxonomy?: (
    payloadId: string,
    categoryName?: string,
    subcategoryName?: string
  ) => void;
  onBatchSaveTaxonomy?: (
    updates: Array<{ payloadId: string; categoryName: string; subcategoryName: string }>
  ) => Promise<void>;
}

export const PayloadTable: React.FC<Props> = ({
  payloads,
  selectedIds,
  taxonomyTree = [],
  onSelectPayload,
  onToggleSelectAll,
  onToggleSelectOne,
  onUpdateTaxonomy,
  onBatchSaveTaxonomy,
}) => {
  const isAllSelected = payloads.length > 0 && selectedIds.length === payloads.length;

  const [localTaxonomy, setLocalTaxonomy] = useState<
    Record<string, { categoryName: string; subcategoryName: string }>
  >({});
  const [isSaving, setIsSaving] = useState<boolean>(false);

  const uniqueCategoryNames = useMemo(() => {
    if (!Array.isArray(taxonomyTree)) return [];
    const categories = taxonomyTree.map((item: any) =>
      typeof item === 'string' ? item : item?.category || item?.name || ''
    );
    return Array.from(new Set(categories)).filter(Boolean).sort();
  }, [taxonomyTree]);

  const pendingCount = Object.keys(localTaxonomy).length;

  const handleCategoryChange = (rowId: string, newCatName: string) => {
    setLocalTaxonomy((prev) => ({
      ...prev,
      [rowId]: {
        categoryName: newCatName,
        subcategoryName: '',
      },
    }));

    if (onUpdateTaxonomy && !onBatchSaveTaxonomy) {
      onUpdateTaxonomy(rowId, newCatName, '');
    }
  };

  const handleSubcategoryChange = (rowId: string, currentCatName: string, newSubName: string) => {
    setLocalTaxonomy((prev) => ({
      ...prev,
      [rowId]: {
        categoryName: currentCatName,
        subcategoryName: newSubName,
      },
    }));

    if (onUpdateTaxonomy && !onBatchSaveTaxonomy) {
      onUpdateTaxonomy(rowId, currentCatName, newSubName);
    }
  };

  const handleCommitBatch = async () => {
    if (!onBatchSaveTaxonomy || pendingCount === 0) return;

    setIsSaving(true);
    try {
      const updates = Object.entries(localTaxonomy).map(([payloadId, vals]) => ({
        payloadId,
        categoryName: vals.categoryName,
        subcategoryName: vals.subcategoryName,
      }));

      await onBatchSaveTaxonomy(updates);
      setLocalTaxonomy({});
    } catch (err) {
      console.error('Failed to commit taxonomy updates:', err);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-3">
      {pendingCount > 0 && onBatchSaveTaxonomy && (
        <div className="flex items-center justify-between bg-indigo-950/90 border border-indigo-700 px-4 py-2.5 rounded-lg text-xs font-mono shadow-lg">
          <span className="text-indigo-300 font-medium">
            ⚠️ You have <strong className="text-white font-bold">{pendingCount}</strong> unsaved taxonomy classification(s).
          </span>
          <button
            onClick={handleCommitBatch}
            disabled={isSaving}
            className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-800 text-white font-bold rounded transition-colors cursor-pointer flex items-center gap-1.5 shadow-md"
          >
            <span>{isSaving ? '⏳ Saving...' : '💾 Save Taxonomy Batch'}</span>
          </button>
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-900/40">
        <table className="w-full text-left text-xs font-mono">
          <thead className="bg-zinc-900/80 text-zinc-400 uppercase tracking-wider border-b border-zinc-800">
            <tr>
              <th className="p-3 w-10 text-center">
                <input
                  type="checkbox"
                  checked={isAllSelected}
                  onChange={onToggleSelectAll}
                  className="rounded border-zinc-700 bg-zinc-800 text-indigo-600 focus:ring-0 cursor-pointer"
                />
              </th>
              <th className="p-3">Source</th>
              <th className="p-3">Account & Bank</th>
              <th className="p-3">Merchant / Narration</th>
              <th className="p-3 text-right text-rose-400/90 whitespace-nowrap">DEBIT (DR)</th>
              <th className="p-3 text-right text-emerald-400/90 whitespace-nowrap">CREDIT (CR)</th>
              <th className="p-3 text-right">Avail. Balance</th>
              <th className="p-3 font-mono">UPI Ref / RRN</th>
              <th className="p-3 text-indigo-400">Taxonomy Classification</th>
              <th className="p-3 text-center">Ingest Status</th>
              <th className="p-3">Received At</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60 text-zinc-300">
            {payloads.length === 0 ? (
              <tr>
                <td colSpan={11} className="p-6 text-center text-zinc-500">
                  No payload streams available.
                </td>
              </tr>
            ) : (
              payloads.map((payload: any) => {
                const rowId = payload.id || payload.payload_hash;
                const isSelected = selectedIds.includes(rowId);
                const statusStr = (payload.status || 'UNPARSED').toUpperCase();
                const isSyntheticGap = Boolean(payload.is_synthetic_gap);
                const isStaged = Boolean(payload.is_staged_for_matching || statusStr === 'STAGED');

                const rawItem = payload.raw_item || {};
                const parsedTxn = rawItem.parsed_transaction || {};

                let headers = payload.headers_json || rawItem.raw_payload?.headers_json || {};
                if (typeof headers === 'string') {
                  try {
                    headers = JSON.parse(headers);
                  } catch (e) {
                    headers = {};
                  }
                }

                const summary = headers.parsed_summary || {};

                const bankName = payload.bank_name || parsedTxn.bank_name || summary.bank || 'SOUTH INDIAN BANK';
                const accountLast4 = payload.account_last4 || parsedTxn.account_last4 || summary.account;
                const upiRef = payload.upi_ref || parsedTxn.upi_ref || summary.upi_ref || '—';
                const amount = payload.amount !== undefined && payload.amount !== null ? payload.amount : parsedTxn.amount;
                const merchant = payload.merchant || parsedTxn.merchant || payload.subject || '—';

                const isCredit = payload.txn_type === 'CREDIT';

                let dbTaxonomy = payload.taxonomy_payload || {};
                if (typeof dbTaxonomy === 'string') {
                  try {
                    dbTaxonomy = JSON.parse(dbTaxonomy);
                  } catch (e) {
                    dbTaxonomy = {};
                  }
                }

                const pending = localTaxonomy[rowId];
                const currentCatName = pending
                  ? pending.categoryName
                  : dbTaxonomy.taxonomy?.category_name || '';
                const currentSubName = pending
                  ? pending.subcategoryName
                  : dbTaxonomy.taxonomy?.subcategory_name || '';

                const matchedCategoryObj = taxonomyTree.find(
                  (item: any) => (typeof item === 'string' ? item : item?.category) === currentCatName
                );
                const availableSubcategories = matchedCategoryObj?.subcategories || [];

                return (
                  <tr
                    key={rowId}
                    className={`transition-colors border-l-4 ${
                      isSelected
                        ? 'bg-amber-950/60 border-l-amber-400 ring-1 ring-amber-500/50'
                        : isSyntheticGap
                        ? 'bg-amber-950/30 hover:bg-amber-950/50 border-l-amber-500'
                        : isStaged
                        ? 'bg-amber-950/20 hover:bg-amber-950/30 border-l-amber-600'
                        : pending
                        ? 'bg-indigo-950/30 hover:bg-indigo-950/40 border-l-indigo-500'
                        : 'hover:bg-zinc-800/30 border-l-transparent'
                    }`}
                  >
                    <td className="p-3 text-center">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => onToggleSelectOne(rowId)}
                        className="rounded border-zinc-700 bg-zinc-800 text-indigo-600 focus:ring-0 cursor-pointer"
                      />
                    </td>

                    {/* Source */}
                    <td className="p-3 font-bold whitespace-nowrap">
                      {isSyntheticGap ? (
                        <span className="text-amber-400 font-mono text-[11px] bg-amber-950/80 border border-amber-700/60 px-1.5 py-0.5 rounded">
                          ⚠️ AUDIT_GAP
                        </span>
                      ) : (
                        <span className="text-indigo-400">{payload.source || 'IOS_SMS'}</span>
                      )}
                    </td>

                    {/* Account & Bank */}
                    <td className="p-3">
                      <div className="font-semibold text-zinc-200">{bankName}</div>
                      {accountLast4 ? (
                        <div className="text-[10px] text-zinc-400 font-mono">A/c X{accountLast4}</div>
                      ) : (
                        <div className="text-[10px] text-zinc-600 font-mono">A/c —</div>
                      )}
                    </td>

                    {/* Merchant / Narration */}
                    <td className="p-3">
                      {isSyntheticGap ? (
                        <span className="text-amber-300 font-semibold italic">{merchant}</span>
                      ) : (
                        <button
                          onClick={() => onSelectPayload(payload)}
                          className="text-left font-medium text-zinc-200 hover:text-indigo-400 cursor-pointer max-w-xs truncate block border-none bg-transparent p-0 focus:outline-none"
                        >
                          {merchant}
                        </button>
                      )}
                    </td>

                    {/* DEBIT (DR) */}
                    <td className="p-3 text-right font-bold whitespace-nowrap font-mono">
                      {!isCredit && amount !== null && amount !== undefined && amount !== '' ? (
                        <span className={isSyntheticGap ? 'text-amber-400 font-bold' : 'text-zinc-200'}>
                          ₹{Number(amount).toLocaleString('en-IN', {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })}
                        </span>
                      ) : (
                        <span className="text-zinc-700">—</span>
                      )}
                    </td>

                    {/* CREDIT (CR) */}
                    <td className="p-3 text-right font-bold whitespace-nowrap font-mono">
                      {isCredit && amount !== null && amount !== undefined && amount !== '' ? (
                        <span className={isSyntheticGap ? 'text-amber-400 font-bold' : 'text-emerald-400'}>
                          +₹{Number(amount).toLocaleString('en-IN', {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })}
                        </span>
                      ) : (
                        <span className="text-zinc-700">—</span>
                      )}
                    </td>

                    {/* Available Balance */}
                    <td className="p-3 text-right font-semibold text-zinc-200 whitespace-nowrap font-mono">
                      {(() => {
                        let bal = payload.balance;

                        if (bal === null || bal === undefined || bal === '') {
                          bal = parsedTxn.balance || summary.balance;
                        }

                        if (bal !== null && bal !== undefined && bal !== '' && !isNaN(Number(bal))) {
                          return (
                            <span className={isSyntheticGap ? 'text-amber-300 font-bold' : 'text-zinc-200 font-bold'}>
                              ₹{Number(bal).toLocaleString('en-IN', {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}
                            </span>
                          );
                        }

                        return <span className="text-zinc-600">—</span>;
                      })()}
                    </td>

                    {/* UPI Ref / RRN */}
                    <td className="p-3 font-mono text-[11px] whitespace-nowrap">
                      {isSyntheticGap ? (
                        <span className="text-amber-500/80 font-bold">PENDING_STATEMENT</span>
                      ) : (
                        <span className="text-zinc-400">{upiRef}</span>
                      )}
                    </td>

                    {/* Taxonomy Classification Dropdowns */}
                    <td className="p-3">
                      {isSyntheticGap ? (
                        <span className="text-zinc-600 italic text-[11px]">Auto-Assigned on Statement</span>
                      ) : (
                        <div className="flex flex-col gap-1 min-w-42.5">
                          <select
                            value={currentCatName}
                            onChange={(e) => handleCategoryChange(rowId, e.target.value)}
                            className={`bg-zinc-950 border text-[11px] rounded px-2 py-1 focus:outline-none cursor-pointer transition-colors ${
                              pending ? 'border-indigo-500 text-indigo-200 font-bold' : 'border-zinc-800 text-zinc-300'
                            }`}
                          >
                            <option value="">Select Category...</option>
                            {uniqueCategoryNames.map((catName) => (
                              <option key={`cat-${catName}`} value={catName}>
                                {catName}
                              </option>
                            ))}
                          </select>

                          <select
                            value={currentSubName}
                            disabled={!currentCatName || availableSubcategories.length === 0}
                            onChange={(e) => handleSubcategoryChange(rowId, currentCatName, e.target.value)}
                            className={`bg-zinc-950 border text-[11px] rounded px-2 py-1 focus:outline-none cursor-pointer disabled:text-zinc-600 disabled:bg-zinc-900 transition-colors ${
                              pending ? 'border-indigo-500 text-indigo-200 font-bold' : 'border-zinc-800 text-zinc-400'
                            }`}
                          >
                            <option value="">Select Subcategory...</option>
                            {availableSubcategories.map((subItem: any, index: number) => {
                              const subName =
                                typeof subItem === 'string'
                                  ? subItem
                                  : subItem?.subcategory || subItem?.name || subItem?.label || '';
                              const subKey =
                                typeof subItem === 'object' && subItem?.id
                                  ? subItem.id
                                  : `sub-${subName}-${index}`;

                              return (
                                <option key={subKey} value={subName}>
                                  {subName}
                                </option>
                              );
                            })}
                          </select>
                        </div>
                      )}
                    </td>

                    {/* Status Badge */}
                    <td className="p-3 text-center whitespace-nowrap">
                      {isSyntheticGap ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950 text-amber-400 border border-amber-800/80 inline-flex items-center gap-1">
                          <span>⚠️</span> SUSPENSE
                        </span>
                      ) : isStaged ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950 text-amber-400 border border-amber-800/80 inline-flex items-center gap-1">
                          <span>🎯</span> STAGED
                        </span>
                      ) : (
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold inline-flex items-center gap-1 ${
                            statusStr === 'PARSED'
                              ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/60'
                              : statusStr === 'DUPLICATE'
                              ? 'bg-amber-950 text-amber-400 border border-amber-800/60'
                              : statusStr === 'COMPLETED'
                              ? 'bg-indigo-950 text-indigo-400 border border-indigo-800/60'
                              : 'bg-zinc-800 text-zinc-400 border border-zinc-700'
                          }`}
                        >
                          <span>
                            {statusStr === 'DUPLICATE'
                              ? '⚠️'
                              : statusStr === 'PARSED' || statusStr === 'COMPLETED'
                              ? '✅'
                              : '⚙️'}
                          </span>
                          {statusStr}
                        </span>
                      )}
                    </td>

                    {/* Received At */}
                    <td className="p-3 text-zinc-400 whitespace-nowrap">
                      {payload.email_date
                        ? new Date(payload.email_date).toLocaleString('en-IN', {
                            day: '2-digit',
                            month: 'short',
                            year: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit',
                          })
                        : '—'}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};