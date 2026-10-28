import React, { useState } from 'react';
import { Building2, ArrowRight } from 'lucide-react';
import { parseRemarks, extractUpiRemark } from '../../../utils/classificationHelpers';

interface Props {
  item: any;
  clusterIdx: number;
  vIdx: number;
  itemIdx: number;
  isSelected: boolean;
  globalNarrationMode: 'smart' | 'raw';
  onToggleSelect: (id: string, e: React.MouseEvent) => void;
  onOpenRemarksModal: (item: any) => void;
}

export const ClusterCardItem: React.FC<Props> = ({
  item,
  clusterIdx,
  vIdx,
  itemIdx,
  isSelected,
  globalNarrationMode,
  onToggleSelect,
  onOpenRemarksModal,
}) => {
  const [localFlipped, setLocalFlipped] = useState(false);

  const activeMode = localFlipped
    ? globalNarrationMode === 'smart' ? 'raw' : 'smart'
    : globalNarrationMode;

  const isOutflow = (() => {
    const dirStr = (item.direction || item.vector_type || item.entry_type || '').toUpperCase();
    if (dirStr === 'OUTFLOW' || dirStr === 'DEBIT' || dirStr === 'DR') return true;
    if (dirStr === 'INFLOW' || dirStr === 'CREDIT' || dirStr === 'CR') return false;
    if (item.debit != null && Number(item.debit) > 0) return true;
    if (item.credit != null && Number(item.credit) > 0) return false;
    return (item.amount ?? 0) < 0;
  })();

  const flagColor = isOutflow ? '#fb7185' : '#34d399';
  const itemKey = item.id ? `card-${item.id}` : `card-idx-${clusterIdx}-${vIdx}-${itemIdx}`;
  const remarksObj = parseRemarks(item.remarks);
  const userRemark = extractUpiRemark(item.narration);

  // Self-Transfer Contra Detection
  const contraMeta = item.contra_meta;
  const isSelfTransfer = Boolean(contraMeta?.is_self_transfer);

  // Fallback single bank pill format (e.g., SIB NRO-60 ••0060)
  const bankDisplayName = item.bank_name || remarksObj.bank_name || 'Bank';
  const bankLast4 = item.bank_last4 || remarksObj.bank_last4 || '';
  const bankBadgeText = bankLast4 ? `${bankDisplayName} ••${bankLast4}` : bankDisplayName;

  // Date formatting (e.g., 05 Jan 2026 or raw string)
  const formattedDate = (() => {
    if (!item.transaction_date) return null;
    try {
      const d = new Date(item.transaction_date);
      if (isNaN(d.getTime())) return String(item.transaction_date);
      return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
    } catch {
      return String(item.transaction_date);
    }
  })();

  const smartTitle =
    item.universal_narration ||
    item.display_text ||
    item.remarks?.universal_narration ||
    item.narration ||
    'Unlabeled Line';

  const rawStatement =
    item.raw_narration ||
    item.remarks?.raw_narration ||
    item.remarks?.narration ||
    item.narration ||
    '';

  const activeText = activeMode === 'smart' ? smartTitle : rawStatement;

  return (
    <div
      key={itemKey}
      onClick={(e) => e.stopPropagation()}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '4px',
        padding: '6px 8px',
        borderRadius: '4px',
        backgroundColor: isSelected ? '#27272a' : '#09090b',
        borderLeft: `3px solid ${flagColor}`,
        fontSize: '10px',
      }}
    >
      {/* 🟢 TOP METADATA BADGE ROW: Checkbox + Date + (Self-Transfer Badge OR Bank Badge) + Amount */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <input
            type="checkbox"
            checked={isSelected}
            onClick={(e) => onToggleSelect(item.id, e)}
            onChange={() => {}}
            style={{ width: '13px', height: '13px', accentColor: '#f59e0b', cursor: 'pointer' }}
          />

          {formattedDate && (
            <span style={{ fontSize: '10px', color: '#a1a1aa', fontFamily: 'monospace' }}>
              {formattedDate}
            </span>
          )}

          {/* 🎯 Self-Transfer Two-Way Flow Badge */}
          {isSelfTransfer ? (
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                backgroundColor: '#082f49cc',
                color: '#7dd3fc',
                border: '1px solid #0284c788',
                borderRadius: '4px',
                padding: '1px 6px',
                fontSize: '9px',
                fontFamily: 'monospace',
                fontWeight: 600,
              }}
            >
              {/* Source Account */}
              <span style={{ color: '#f1f5f9' }}>
                {contraMeta.from_account_name}{' '}
                <span style={{ color: '#38bdf8' }}>••{contraMeta.from_account_last4}</span>
              </span>

              {/* Direction Arrow */}
              <ArrowRight style={{ width: '10px', height: '10px', color: '#38bdf8' }} />

              {/* Destination Account */}
              <span style={{ color: '#f1f5f9' }}>
                {contraMeta.to_account_name}{' '}
                <span style={{ color: '#38bdf8' }}>••{contraMeta.to_account_last4}</span>
              </span>

              {/* Status Indicator */}
              <span
                style={{
                  fontSize: '8px',
                  fontWeight: 'bold',
                  padding: '1px 4px',
                  borderRadius: '3px',
                  backgroundColor: isOutflow ? '#88133766' : '#064e3b66',
                  color: flagColor,
                  border: `1px solid ${isOutflow ? '#f43f5e55' : '#10b98155'}`,
                  marginLeft: '2px',
                }}
              >
                {isOutflow ? 'SENT' : 'RECVD'}
              </span>
            </div>
          ) : (
            /* 🏦 Standard Bank Badge + In/Out Tag for One-Way / Merchant Traffic */
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  backgroundColor: '#0c4a6e33',
                  color: '#38bdf8',
                  border: '1px solid #0284c744',
                  borderRadius: '4px',
                  padding: '1px 6px',
                  fontSize: '9px',
                  fontWeight: 'bold',
                  fontFamily: 'monospace',
                }}
              >
                <Building2 style={{ width: '10px', height: '10px' }} />
                {bankBadgeText}
              </span>

              <span
                style={{
                  fontSize: '8px',
                  fontWeight: 'bold',
                  padding: '1px 4px',
                  borderRadius: '3px',
                  backgroundColor: isOutflow ? '#88133744' : '#064e3b44',
                  color: flagColor,
                  border: `1px solid ${isOutflow ? '#f43f5e44' : '#10b98144'}`,
                }}
              >
                {isOutflow ? 'OUT' : 'IN'}
              </span>
            </div>
          )}
        </div>

        {/* Transaction Amount */}
        <span style={{ fontSize: '11px', fontWeight: 'bold', color: flagColor, fontFamily: 'monospace' }}>
          {isOutflow
            ? `-₹${Math.abs(item.amount || item.debit || 0).toLocaleString('en-IN')}`
            : `+₹${Math.abs(item.amount || item.credit || 0).toLocaleString('en-IN')}`}
        </span>
      </div>

      {/* 🟢 NARRATION ROW */}
      <div style={{ paddingLeft: '21px' }}>
        <span
          onClick={() => setLocalFlipped(!localFlipped)}
          style={{
            display: 'block',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            fontFamily: activeMode === 'raw' ? 'monospace' : 'inherit',
            color: activeMode === 'raw' ? '#38bdf8' : '#e4e4e7',
            fontWeight: activeMode === 'raw' ? '400' : '500',
            cursor: 'pointer',
          }}
          title="Click to flip between Smart Narrative and Raw Bank Statement"
        >
          {activeMode === 'raw' ? `🏦 ${activeText}` : activeText}
        </span>
      </div>

      {/* 🟢 FOOTER ROW: Reference, User Remark, Remarks Modal Trigger */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginLeft: '21px', fontSize: '9px' }}>
        {remarksObj.upi_ref && (
          <span style={{ backgroundColor: '#18181b', color: '#a1a1aa', padding: '1px 4px', borderRadius: '3px', border: '1px solid #27272a', fontFamily: 'monospace' }}>
            Ref: {remarksObj.upi_ref}
          </span>
        )}

        {userRemark && (
          <span
            style={{
              backgroundColor: '#064e3b',
              color: '#34d399',
              padding: '1px 6px',
              borderRadius: '3px',
              border: '1px solid #047857',
              fontWeight: 'bold',
              fontSize: '8px',
              textTransform: 'uppercase',
            }}
          >
            🏷️ {userRemark}
          </span>
        )}

        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onOpenRemarksModal(item);
          }}
          style={{
            backgroundColor: '#27272a',
            color: '#f59e0b',
            border: '1px solid #3f3f46',
            borderRadius: '3px',
            padding: '1px 5px',
            fontSize: '8px',
            cursor: 'pointer',
            fontWeight: 'bold',
            display: 'flex',
            alignItems: 'center',
            gap: '3px',
          }}
        >
          <span>🔍</span> Remarks
        </button>
      </div>
    </div>
  );
};