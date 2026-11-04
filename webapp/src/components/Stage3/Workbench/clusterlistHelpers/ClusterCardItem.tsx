// webapp/src/components/Stage3/Workbench/ClusterCardItem.tsx
import React, { useState } from 'react';
import { Building2, ArrowRight, Copy, Check } from 'lucide-react';
import {
  parseRemarks,
  extractUpiRemark,
  formatShortDate,
} from '../../../../utils/classificationHelpers';
import {
  renderSearchHighlightedText,
  copyToClipboard,
} from './searchAndFilterHelpers';

export interface ClusterCardItemProps {
  item: any;
  clusterKey: string;
  isSelected: boolean;
  isUnmapping: boolean;
  globalNarrationMode: 'smart' | 'raw';
  searchTokens?: string[];
  onToggleSelect: (id: string, e: React.MouseEvent) => void;
  onUnmap: (e: React.MouseEvent, item: any, clusterKey: string) => void;
  onOpenRemarksModal: (item: any) => void;
}

const isDebitOutflow = (item: any): boolean => {
  const dir = (item.direction || item.vector_type || item.entry_type || '').toUpperCase();
  if (['OUTFLOW', 'DEBIT', 'DR'].includes(dir)) return true;
  if (['INFLOW', 'CREDIT', 'CR'].includes(dir)) return false;
  if (item.debit != null && Number(item.debit) > 0) return true;
  if (item.credit != null && Number(item.credit) > 0) return false;
  const narration = (item.narration || '').toUpperCase();
  if (narration.startsWith('DEP TFR NEFT') || narration.includes('CREDIT') || narration.includes('INFLOW')) return false;
  return (item.amount ?? 0) < 0;
};

export const ClusterCardItem: React.FC<ClusterCardItemProps> = ({
  item,
  clusterKey,
  isSelected,
  isUnmapping,
  globalNarrationMode,
  searchTokens = [],
  onToggleSelect,
  onUnmap,
  onOpenRemarksModal,
}) => {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const isOutflow = isDebitOutflow(item);
  const remarksObj = parseRemarks(item.remarks);
  const userRemark = extractUpiRemark(item.narration);

  const contraMeta = item.contra_meta;
  const isSelfTransfer = Boolean(contraMeta?.is_self_transfer);

  const bankName = item.bank_name || remarksObj.bank_name || 'Bank';
  const bankLast4 = item.bank_last4 || remarksObj.bank_last4 || '';
  const displayAccountId = item.account_id && item.account_id !== 99 ? item.account_id : null;

  const isMapped = Boolean(item.is_mapped || item.subledger_mapping || item.mapping_id || item.asset_id);
  const assetCode = item.asset_code || item.subledger_mapping?.asset_code || 'FLT';

  const rawVal = item.amount ?? item.debit ?? item.credit ?? 0;
  const num = Math.abs(Number(rawVal) || 0);

  const rawStatement =
    item.raw_narration ||
    item.narration ||
    item.remarks?.raw_narration ||
    remarksObj.raw_narration ||
    remarksObj.narration ||
    '';

  const smartTitle =
    item.universal_narration ||
    item.remarks?.universal_narration ||
    remarksObj.universal_narration ||
    item.display_text ||
    remarksObj.display_text ||
    item.display_payee ||
    remarksObj.payee ||
    'Unlabeled Line';

  const activeText = globalNarrationMode === 'smart' ? smartTitle : rawStatement;

  const handleCopy = async (text: string, key: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const ok = await copyToClipboard(text);
    if (ok) {
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 1500);
    }
  };

  return (
    <div
      onClick={(e) => e.stopPropagation()}
      className={`p-2.5 rounded-lg flex flex-col gap-1.5 border-l-2 text-[10px] w-full transition-colors ${
        isSelected ? 'bg-zinc-800/90' : 'bg-zinc-950/80 hover:bg-zinc-900/60'
      } ${isOutflow ? 'border-rose-500' : 'border-emerald-500'}`}
    >
      {/* 🟢 TOP ROW */}
      <div className="w-full flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0 flex-1 flex-wrap">
          <input
            type="checkbox"
            checked={isSelected}
            onClick={(e) => onToggleSelect(item.id, e)}
            onChange={() => {}}
            className="w-3.5 h-3.5 accent-amber-500 cursor-pointer rounded shrink-0"
          />

          {item.transaction_date && (
            <span className="text-[10px] font-mono text-zinc-400 font-semibold shrink-0">
              {formatShortDate(item.transaction_date)}
            </span>
          )}

          {/* Contra Routing or Bank Badge */}
          {isSelfTransfer ? (
            <div className="inline-flex items-center gap-1.5 rounded bg-sky-950/80 border border-sky-700/60 px-1.5 py-0.5 text-[9px] font-mono text-sky-300 font-bold shrink-0">
              <span className="text-zinc-100">
                {contraMeta.from_account_name} <span className="text-sky-400 font-normal">••{contraMeta.from_account_last4}</span>
              </span>
              <ArrowRight className="w-2.5 h-2.5 text-sky-400 shrink-0" />
              <span className="text-zinc-100">
                {contraMeta.to_account_name} <span className="text-sky-400 font-normal">••{contraMeta.to_account_last4}</span>
              </span>
              <span
                className={`text-[8px] font-bold px-1 rounded uppercase ${
                  isOutflow ? 'bg-rose-950/80 text-rose-300' : 'bg-emerald-950/80 text-emerald-300'
                }`}
              >
                {isOutflow ? 'SENT' : 'RECVD'}
              </span>
            </div>
          ) : (
            <>
              {bankName ? (
                <span className="inline-flex items-center gap-1 rounded bg-sky-950/80 border border-sky-700/60 px-1.5 py-0.5 text-[9px] font-mono text-sky-300 font-bold shrink-0">
                  <Building2 className="w-2.5 h-2.5 shrink-0" />
                  <span>{bankName}</span>
                  {bankLast4 && <span className="text-sky-400/80 font-normal">••{bankLast4}</span>}
                </span>
              ) : displayAccountId ? (
                <span className="inline-flex items-center rounded bg-zinc-800 border border-zinc-700 px-1.5 py-0.5 text-[9px] font-mono text-zinc-300 shrink-0">
                  Acc #{displayAccountId}
                </span>
              ) : null}

              <span
                className={`text-[8px] font-bold px-1.5 py-0.5 rounded uppercase border shrink-0 ${
                  isOutflow
                    ? 'bg-rose-950/60 text-rose-300 border-rose-800/40'
                    : 'bg-emerald-950/60 text-emerald-300 border-emerald-800/40'
                }`}
              >
                {isOutflow ? 'OUT' : 'IN'}
              </span>
            </>
          )}

          {/* Subledger Mapping Badge */}
          {isMapped && (
            <span className="inline-flex items-center gap-1.5 rounded bg-emerald-950/90 border border-emerald-500/50 px-1.5 py-0.5 text-[9px] font-mono text-emerald-300 font-bold shrink-0">
              <span>Mapped: {assetCode}</span>
              <button
                type="button"
                disabled={isUnmapping}
                onClick={(e) => onUnmap(e, item, clusterKey)}
                className="text-zinc-400 hover:text-rose-400 underline decoration-dotted transition-colors text-[9px] cursor-pointer disabled:opacity-40"
              >
                {isUnmapping ? '...' : '(Unmap)'}
              </button>
            </span>
          )}
        </div>

        {/* Amount */}
        <span
          className={`font-mono text-xs font-bold tabular-nums shrink-0 ml-auto select-text ${
            isOutflow ? 'text-rose-400' : 'text-emerald-400'
          }`}
        >
          {isOutflow ? '-' : '+'}₹{num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
      </div>

      {/* 🟢 NARRATION ROW with Highlight & Copy */}
      <div className="pl-5 font-mono text-[10px] leading-relaxed wrap-break-word flex items-start justify-between gap-2 select-text group">
        <span
          className={`block select-text ${
            globalNarrationMode === 'raw' ? 'text-zinc-400 font-normal' : 'text-amber-300/90 font-semibold'
          }`}
        >
          {globalNarrationMode === 'raw' ? '🏦 ' : ''}
          {renderSearchHighlightedText(activeText, searchTokens)}
        </span>

        <button
          type="button"
          onClick={(e) => handleCopy(rawStatement || activeText, 'narration', e)}
          className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 text-zinc-500 hover:text-zinc-200 cursor-pointer shrink-0"
          title="Copy statement line"
        >
          {copiedKey === 'narration' ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
        </button>
      </div>

      {/* 🟢 FOOTER ROW: UPI Ref + User Remarks + Inspection */}
      <div className="flex items-center gap-2 pl-5 pt-0.5 text-[9px]">
        {remarksObj.upi_ref && (
          <span
            onClick={(e) => handleCopy(String(remarksObj.upi_ref), 'ref', e)}
            className="bg-zinc-900 hover:bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded border border-zinc-800 font-mono select-text cursor-pointer flex items-center gap-1 transition-colors"
            title="Click to copy reference"
          >
            <span>Ref: {renderSearchHighlightedText(String(remarksObj.upi_ref), searchTokens)}</span>
            {copiedKey === 'ref' ? <Check className="w-2.5 h-2.5 text-emerald-400" /> : <Copy className="w-2.5 h-2.5 opacity-50" />}
          </span>
        )}

        {userRemark && (
          <span className="bg-emerald-950 text-emerald-300 border border-emerald-800 px-1.5 py-0.5 rounded font-bold uppercase text-[8px] select-text">
            🏷️ {renderSearchHighlightedText(userRemark, searchTokens)}
          </span>
        )}

        <button
          type="button"
          onClick={() => onOpenRemarksModal({ ...item, narration: rawStatement })}
          className="bg-zinc-800 hover:bg-zinc-700 text-amber-400 border border-zinc-700 px-2 py-0.5 rounded text-[8px] font-bold cursor-pointer transition-colors"
        >
          🔍 Remarks
        </button>
      </div>
    </div>
  );
};




// function smartTitleFallback(item: any, fallback: string): string {
//   return (
//     item.universal_narration ||
//     item.display_text ||
//     item.remarks?.universal_narration ||
//     fallback
//   );
// }






// import React, { useState } from 'react';
// import { Building2, ArrowRight } from 'lucide-react';
// import { parseRemarks, extractUpiRemark } from '../../../utils/classificationHelpers';

// interface Props {
//   item: any;
//   clusterIdx: number;
//   vIdx: number;
//   itemIdx: number;
//   isSelected: boolean;
//   globalNarrationMode: 'smart' | 'raw';
//   onToggleSelect: (id: string, e: React.MouseEvent) => void;
//   onOpenRemarksModal: (item: any) => void;
// }

// export const ClusterCardItem: React.FC<Props> = ({
//   item,
//   clusterIdx,
//   vIdx,
//   itemIdx,
//   isSelected,
//   globalNarrationMode,
//   onToggleSelect,
//   onOpenRemarksModal,
// }) => {
//   const [localFlipped, setLocalFlipped] = useState(false);

//   const activeMode = localFlipped
//     ? globalNarrationMode === 'smart' ? 'raw' : 'smart'
//     : globalNarrationMode;

//   const isOutflow = (() => {
//     const dirStr = (item.direction || item.vector_type || item.entry_type || '').toUpperCase();
//     if (dirStr === 'OUTFLOW' || dirStr === 'DEBIT' || dirStr === 'DR') return true;
//     if (dirStr === 'INFLOW' || dirStr === 'CREDIT' || dirStr === 'CR') return false;
//     if (item.debit != null && Number(item.debit) > 0) return true;
//     if (item.credit != null && Number(item.credit) > 0) return false;
//     return (item.amount ?? 0) < 0;
//   })();

//   const flagColor = isOutflow ? '#fb7185' : '#34d399';
//   const itemKey = item.id ? `card-${item.id}` : `card-idx-${clusterIdx}-${vIdx}-${itemIdx}`;
//   const remarksObj = parseRemarks(item.remarks);
//   const userRemark = extractUpiRemark(item.narration);

//   // Self-Transfer Contra Detection
//   const contraMeta = item.contra_meta;
//   const isSelfTransfer = Boolean(contraMeta?.is_self_transfer);

//   // Fallback single bank pill format (e.g., SIB NRO-60 ••0060)
//   const bankDisplayName = item.bank_name || remarksObj.bank_name || 'Bank';
//   const bankLast4 = item.bank_last4 || remarksObj.bank_last4 || '';
//   const bankBadgeText = bankLast4 ? `${bankDisplayName} ••${bankLast4}` : bankDisplayName;

//   // Date formatting (e.g., 05 Jan 2026 or raw string)
//   const formattedDate = (() => {
//     if (!item.transaction_date) return null;
//     try {
//       const d = new Date(item.transaction_date);
//       if (isNaN(d.getTime())) return String(item.transaction_date);
//       return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
//     } catch {
//       return String(item.transaction_date);
//     }
//   })();

//   const smartTitle =
//     item.universal_narration ||
//     item.display_text ||
//     item.remarks?.universal_narration ||
//     item.narration ||
//     'Unlabeled Line';

//   const rawStatement =
//     item.raw_narration ||
//     item.remarks?.raw_narration ||
//     item.remarks?.narration ||
//     item.narration ||
//     '';

//   const activeText = activeMode === 'smart' ? smartTitle : rawStatement;

//   return (
//     <div
//       key={itemKey}
//       onClick={(e) => e.stopPropagation()}
//       style={{
//         display: 'flex',
//         flexDirection: 'column',
//         gap: '4px',
//         padding: '6px 8px',
//         borderRadius: '4px',
//         backgroundColor: isSelected ? '#27272a' : '#09090b',
//         borderLeft: `3px solid ${flagColor}`,
//         fontSize: '10px',
//       }}
//     >
//       {/* 🟢 TOP METADATA BADGE ROW: Checkbox + Date + (Self-Transfer Badge OR Bank Badge) + Amount */}
//       <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
//         <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
//           <input
//             type="checkbox"
//             checked={isSelected}
//             onClick={(e) => onToggleSelect(item.id, e)}
//             onChange={() => {}}
//             style={{ width: '13px', height: '13px', accentColor: '#f59e0b', cursor: 'pointer' }}
//           />

//           {formattedDate && (
//             <span style={{ fontSize: '10px', color: '#a1a1aa', fontFamily: 'monospace' }}>
//               {formattedDate}
//             </span>
//           )}

//           {/* 🎯 Self-Transfer Two-Way Flow Badge */}
//           {isSelfTransfer ? (
//             <div
//               style={{
//                 display: 'inline-flex',
//                 alignItems: 'center',
//                 gap: '5px',
//                 backgroundColor: '#082f49cc',
//                 color: '#7dd3fc',
//                 border: '1px solid #0284c788',
//                 borderRadius: '4px',
//                 padding: '1px 6px',
//                 fontSize: '9px',
//                 fontFamily: 'monospace',
//                 fontWeight: 600,
//               }}
//             >
//               {/* Source Account */}
//               <span style={{ color: '#f1f5f9' }}>
//                 {contraMeta.from_account_name}{' '}
//                 <span style={{ color: '#38bdf8' }}>••{contraMeta.from_account_last4}</span>
//               </span>

//               {/* Direction Arrow */}
//               <ArrowRight style={{ width: '10px', height: '10px', color: '#38bdf8' }} />

//               {/* Destination Account */}
//               <span style={{ color: '#f1f5f9' }}>
//                 {contraMeta.to_account_name}{' '}
//                 <span style={{ color: '#38bdf8' }}>••{contraMeta.to_account_last4}</span>
//               </span>

//               {/* Status Indicator */}
//               <span
//                 style={{
//                   fontSize: '8px',
//                   fontWeight: 'bold',
//                   padding: '1px 4px',
//                   borderRadius: '3px',
//                   backgroundColor: isOutflow ? '#88133766' : '#064e3b66',
//                   color: flagColor,
//                   border: `1px solid ${isOutflow ? '#f43f5e55' : '#10b98155'}`,
//                   marginLeft: '2px',
//                 }}
//               >
//                 {isOutflow ? 'SENT' : 'RECVD'}
//               </span>
//             </div>
//           ) : (
//             /* 🏦 Standard Bank Badge + In/Out Tag for One-Way / Merchant Traffic */
//             <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
//               <span
//                 style={{
//                   display: 'inline-flex',
//                   alignItems: 'center',
//                   gap: '4px',
//                   backgroundColor: '#0c4a6e33',
//                   color: '#38bdf8',
//                   border: '1px solid #0284c744',
//                   borderRadius: '4px',
//                   padding: '1px 6px',
//                   fontSize: '9px',
//                   fontWeight: 'bold',
//                   fontFamily: 'monospace',
//                 }}
//               >
//                 <Building2 style={{ width: '10px', height: '10px' }} />
//                 {bankBadgeText}
//               </span>

//               <span
//                 style={{
//                   fontSize: '8px',
//                   fontWeight: 'bold',
//                   padding: '1px 4px',
//                   borderRadius: '3px',
//                   backgroundColor: isOutflow ? '#88133744' : '#064e3b44',
//                   color: flagColor,
//                   border: `1px solid ${isOutflow ? '#f43f5e44' : '#10b98144'}`,
//                 }}
//               >
//                 {isOutflow ? 'OUT' : 'IN'}
//               </span>
//             </div>
//           )}
//         </div>

//         {/* Transaction Amount */}
//         <span style={{ fontSize: '11px', fontWeight: 'bold', color: flagColor, fontFamily: 'monospace' }}>
//           {isOutflow
//             ? `-₹${Math.abs(item.amount || item.debit || 0).toLocaleString('en-IN')}`
//             : `+₹${Math.abs(item.amount || item.credit || 0).toLocaleString('en-IN')}`}
//         </span>
//       </div>

//       {/* 🟢 NARRATION ROW */}
//       <div style={{ paddingLeft: '21px' }}>
//         <span
//           onClick={() => setLocalFlipped(!localFlipped)}
//           style={{
//             display: 'block',
//             whiteSpace: 'nowrap',
//             overflow: 'hidden',
//             textOverflow: 'ellipsis',
//             fontFamily: activeMode === 'raw' ? 'monospace' : 'inherit',
//             color: activeMode === 'raw' ? '#38bdf8' : '#e4e4e7',
//             fontWeight: activeMode === 'raw' ? '400' : '500',
//             cursor: 'pointer',
//           }}
//           title="Click to flip between Smart Narrative and Raw Bank Statement"
//         >
//           {activeMode === 'raw' ? `🏦 ${activeText}` : activeText}
//         </span>
//       </div>

//       {/* 🟢 FOOTER ROW: Reference, User Remark, Remarks Modal Trigger */}
//       <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginLeft: '21px', fontSize: '9px' }}>
//         {remarksObj.upi_ref && (
//           <span style={{ backgroundColor: '#18181b', color: '#a1a1aa', padding: '1px 4px', borderRadius: '3px', border: '1px solid #27272a', fontFamily: 'monospace' }}>
//             Ref: {remarksObj.upi_ref}
//           </span>
//         )}

//         {userRemark && (
//           <span
//             style={{
//               backgroundColor: '#064e3b',
//               color: '#34d399',
//               padding: '1px 6px',
//               borderRadius: '3px',
//               border: '1px solid #047857',
//               fontWeight: 'bold',
//               fontSize: '8px',
//               textTransform: 'uppercase',
//             }}
//           >
//             🏷️ {userRemark}
//           </span>
//         )}

//         <button
//           type="button"
//           onClick={(e) => {
//             e.stopPropagation();
//             onOpenRemarksModal(item);
//           }}
//           style={{
//             backgroundColor: '#27272a',
//             color: '#f59e0b',
//             border: '1px solid #3f3f46',
//             borderRadius: '3px',
//             padding: '1px 5px',
//             fontSize: '8px',
//             cursor: 'pointer',
//             fontWeight: 'bold',
//             display: 'flex',
//             alignItems: 'center',
//             gap: '3px',
//           }}
//         >
//           <span>🔍</span> Remarks
//         </button>
//       </div>
//     </div>
//   );
// };