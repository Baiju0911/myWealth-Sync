import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Zap, CheckCircle, RefreshCw, Sparkles, X, Trash2 } from 'lucide-react';
import { 
  getSweepPreview, 
  executeBulkSweep, 
  removePatternFromRule, bulkRemovePatternsFromRules,
  type SweepMatchGroup 
} from '../api/api';

interface BulkSweephubModalProps {
  isOpen: boolean;
  onClose: () => void;
  accountId?: string;
  onSweepComplete?: () => void;
}

export const BulkSweepHubModal: React.FC<BulkSweephubModalProps> = ({
  isOpen,
  onClose,
  accountId = '99',
  onSweepComplete,
}) => {
  const [loading, setLoading] = useState<boolean>(false);
  const [executing, setExecuting] = useState<boolean>(false);
  const [purgingBulk, setPurgingBulk] = useState<boolean>(false);
  const [deletingPattern, setDeletingPattern] = useState<string | null>(null);
  const [matches, setMatches] = useState<SweepMatchGroup[]>([]);
  const [selectedPatterns, setSelectedPatterns] = useState<string[]>([]);

  const fetchPreviewData = async () => {
    try {
      const ruleMatches = await getSweepPreview(accountId);
      const safeMatches = ruleMatches || [];
      setMatches(safeMatches);
      setSelectedPatterns(safeMatches.map((m) => m.pattern));
    } catch (err) {
      console.error('Failed to fetch sweep preview:', err);
      setMatches([]);
    }
  };

  useEffect(() => {
    let isMounted = true;

    if (isOpen) {
      setLoading(true);
      fetchPreviewData().finally(() => {
        if (isMounted) setLoading(false);
      });
    }

    return () => {
      isMounted = false;
    };
  }, [isOpen, accountId]);

  const handleTogglePattern = (pattern: string) => {
    setSelectedPatterns((prev) =>
      prev.includes(pattern) ? prev.filter((p) => p !== pattern) : [...prev, pattern]
    );
  };

  const handleDeletePattern = async (e: React.MouseEvent, ruleCode: string, patternTag: string) => {
    e.stopPropagation();

    const token = patternTag.replace(/^#/, '').trim();

    if (!window.confirm(`Are you sure you want to remove pattern '#${token}' from rule ${ruleCode}?`)) {
      return;
    }

    setDeletingPattern(patternTag);

    try {
      const success = await removePatternFromRule(ruleCode, token);
      if (success) {
        await fetchPreviewData();
      } else {
        alert(`Failed to delete pattern '#${token}' from rule.`);
      }
    } catch (err) {
      console.error('Error removing pattern:', err);
    } finally {
      setDeletingPattern(null);
    }
  };

  // 🚀 NEW: Bulk Purge Handler for Checked Cards
  // const handleBulkPurgeSelected = async () => {
  //   if (selectedPatterns.length === 0) return;

  //   const count = selectedPatterns.length;
  //   if (!window.confirm(`Are you sure you want to PURGE ${count} selected noise patterns from their rules?`)) {
  //     return;
  //   }

  //   setPurgingBulk(true);

  //   try {
  //     // 1. Find matching items from state
  //     const itemsToPurge = matches.filter((m) => selectedPatterns.includes(m.pattern));

  //     // 2. Execute sequentially to avoid MySQL row lock contention / race conditions
  //     for (const item of itemsToPurge) {
  //       const token = item.pattern.replace(/^#/, '').trim();
  //       try {
  //         await removePatternFromRule(item.rule_code, token);
  //       } catch (singleErr) {
  //         console.error(`Failed to purge pattern '${token}' from rule ${item.rule_code}:`, singleErr);
  //       }
  //     }

  //     // 3. Re-fetch fresh preview state after ALL requests have completed sequentially
  //     await fetchPreviewData();
  //   } catch (err) {
  //     console.error('Error executing bulk pattern purge:', err);
  //   } finally {
  //     setPurgingBulk(false);
  //   }
  // };

  const handleBulkPurgeSelected = async () => {
  if (selectedPatterns.length === 0) return;

  const count = selectedPatterns.length;
  if (!window.confirm(`Are you sure you want to PURGE ${count} selected noise patterns from their rules?`)) {
    return;
  }

  setPurgingBulk(true);

  try {
    // Construct single payload for all checked items
    const itemsToPurge = matches
      .filter((m) => selectedPatterns.includes(m.pattern))
      .map((m) => ({
        rule_code: m.rule_code,
        pattern: m.pattern.replace(/^#/, '').trim(),
      }));

    // 🚀 One API call to purge all items atomically
    const success = await bulkRemovePatternsFromRules(itemsToPurge);

    if (success) {
      // Re-fetch fresh sweep preview instantly
      await fetchPreviewData();
    } else {
      alert('Bulk pattern purge failed. Check backend logs.');
    }
  } catch (err) {
    console.error('Error executing bulk pattern purge:', err);
  } finally {
    setPurgingBulk(false);
  }
};


  const handleExecuteBulkSweep = async () => {
    if (selectedPatterns.length === 0) return;
    setExecuting(true);

    try {
      const success = await executeBulkSweep(selectedPatterns, accountId);
      if (success) {
        onSweepComplete?.();
        onClose();
      } else {
        alert('Bulk sweep failed. Check Django server console logs.');
      }
    } catch (err) {
      console.error('Bulk sweep execution error:', err);
    } finally {
      setExecuting(false);
    }
  };

  if (!isOpen) return null;

  const totalMatchedQueue = matches.reduce((acc, curr) => acc + curr.matched_rows, 0);

  const totalSelectedRows = matches
    .filter((m) => selectedPatterns.includes(m.pattern))
    .reduce((acc, curr) => acc + curr.matched_rows, 0);

  const totalSelectedAmount = matches
    .filter((m) => selectedPatterns.includes(m.pattern))
    .reduce((acc, curr) => acc + curr.total_amount, 0);

  return createPortal(
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 99999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1rem',
        backgroundColor: 'rgba(9, 9, 11, 0.85)',
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
        fontFamily: 'monospace, sans-serif',
        color: '#f4f4f5',
      }}
    >
      <div
        style={{
          backgroundColor: '#09090b',
          border: '1px solid #27272a',
          borderRadius: '1rem',
          width: '100%',
          maxWidth: '52rem',
          maxHeight: '85vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '1.25rem',
            borderBottom: '1px solid #27272a',
            backgroundColor: '#18181b',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div
              style={{
                padding: '0.5rem',
                backgroundColor: 'rgba(245, 158, 11, 0.1)',
                border: '1px solid rgba(245, 158, 11, 0.3)',
                borderRadius: '0.75rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Zap style={{ width: '1.25rem', height: '1.25rem', color: '#f59e0b' }} />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <h2 style={{ fontSize: '0.875rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#f4f4f5', margin: 0 }}>
                  Node 99 Smart Rule Clearance Hub
                </h2>

                {totalMatchedQueue > 0 && (
                  <span
                    style={{
                      backgroundColor: '#27272a',
                      color: '#f59e0b',
                      fontSize: '0.625rem',
                      padding: '0.125rem 0.5rem',
                      borderRadius: '9999px',
                      fontWeight: 800,
                      border: '1px solid rgba(245, 158, 11, 0.3)',
                    }}
                  >
                    {totalMatchedQueue} Rule Matches
                  </span>
                )}
              </div>
              <p style={{ fontSize: '0.75rem', color: '#a1a1aa', margin: '0.25rem 0 0 0' }}>
                Bulk clearance for unclassified transactions matching your learned rules.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#a1a1aa',
              cursor: 'pointer',
              padding: '0.5rem',
              borderRadius: '0.5rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <X style={{ width: '1.25rem', height: '1.25rem' }} />
          </button>
        </div>

        {/* Content Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {loading ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '4rem 0', color: '#71717a', gap: '0.75rem' }}>
              <RefreshCw style={{ width: '1.5rem', height: '1.5rem', color: '#f59e0b', animation: 'spin 1s linear infinite' }} />
              <p style={{ fontSize: '0.75rem' }}>Scanning Node 99 against active learned rulebook...</p>
            </div>
          ) : matches.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '4rem 0', color: '#71717a' }}>
              <CheckCircle style={{ width: '2rem', height: '2rem', color: '#34d399', margin: '0 auto 0.5rem auto' }} />
              <p style={{ fontSize: '0.875rem', fontWeight: 700, color: '#e4e4e7', margin: 0 }}>No Matched Rules Pending</p>
              <p style={{ fontSize: '0.75rem', margin: '0.25rem 0 0 0' }}>All entries in Node 99 either require manual classification or match zero active rules.</p>
            </div>
          ) : (
            matches.map((group) => {
              const isChecked = selectedPatterns.includes(group.pattern);
              const isDeletingThis = deletingPattern === group.pattern;

              return (
                <div
                  key={group.pattern}
                  onClick={() => handleTogglePattern(group.pattern)}
                  style={{
                    padding: '1rem',
                    borderRadius: '0.75rem',
                    border: isChecked ? '1px solid rgba(245, 158, 11, 0.5)' : '1px solid #27272a',
                    backgroundColor: isChecked ? '#18181b' : '#09090b',
                    opacity: isDeletingThis || purgingBulk ? 0.4 : isChecked ? 1 : 0.6,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => {}}
                      style={{ width: '1.125rem', height: '1.125rem', accentColor: '#f59e0b', cursor: 'pointer' }}
                    />
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <span style={{ fontWeight: 800, fontSize: '0.875rem', color: '#f4f4f5' }}>
                          #{group.pattern}
                        </span>
                        <span
                          style={{
                            fontSize: '0.625rem',
                            backgroundColor: '#27272a',
                            color: '#a1a1aa',
                            padding: '0.125rem 0.375rem',
                            borderRadius: '0.375rem',
                            fontWeight: 700,
                          }}
                        >
                          {group.rule_code}
                        </span>

                        {/* 🗑️ Single Delete Pattern Button */}
                        <button
                          type="button"
                          title={`Purge #${group.pattern} from Rule ${group.rule_code}`}
                          onClick={(e) => handleDeletePattern(e, group.rule_code, group.pattern)}
                          disabled={isDeletingThis || purgingBulk}
                          style={{
                            backgroundColor: 'rgba(239, 68, 68, 0.1)',
                            border: '1px solid rgba(239, 68, 68, 0.3)',
                            color: '#ef4444',
                            borderRadius: '0.375rem',
                            padding: '0.2rem 0.4rem',
                            cursor: 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.25rem',
                            fontSize: '0.625rem',
                            fontWeight: 700,
                            marginLeft: '0.25rem',
                            transition: 'all 0.15s ease',
                          }}
                        >
                          <Trash2 style={{ width: '0.75rem', height: '0.75rem' }} />
                          <span>{isDeletingThis ? 'Deleting...' : 'Purge'}</span>
                        </button>
                      </div>

                      <p style={{ fontSize: '0.75rem', color: '#a1a1aa', margin: '0.25rem 0 0 0' }}>
                        Auto-routes to:{' '}
                        <strong style={{ color: '#34d399', fontWeight: 700 }}>
                          {group.suggested_category} → {group.suggested_subcategory}
                        </strong>
                      </p>
                    </div>
                  </div>

                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: 800, color: '#f59e0b' }}>
                      {group.matched_rows} {group.matched_rows === 1 ? 'Row' : 'Rows'}
                    </div>
                    <div style={{ fontSize: '0.875rem', fontWeight: 700, color: '#e4e4e7', marginTop: '0.125rem' }}>
                      ₹{group.total_amount.toLocaleString('en-IN')}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '1rem 1.25rem',
            borderTop: '1px solid #27272a',
            backgroundColor: '#18181b',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <span style={{ fontSize: '0.75rem', color: '#a1a1aa', display: 'block' }}>Selected Active Queue:</span>
            <span style={{ fontSize: '0.875rem', fontWeight: 800, color: '#f59e0b' }}>
              {selectedPatterns.length} Patterns ({totalSelectedRows} Rows | ₹{totalSelectedAmount.toLocaleString('en-IN')})
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            {/* 🔴 Purge Selected Button */}
            <button
              type="button"
              onClick={handleBulkPurgeSelected}
              disabled={purgingBulk || executing || selectedPatterns.length === 0}
              style={{
                padding: '0.625rem 1rem',
                backgroundColor: 'rgba(239, 68, 68, 0.15)',
                border: '1px solid rgba(239, 68, 68, 0.4)',
                color: '#ef4444',
                fontSize: '0.75rem',
                fontWeight: 800,
                borderRadius: '0.75rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.375rem',
                cursor: purgingBulk || executing || selectedPatterns.length === 0 ? 'not-allowed' : 'pointer',
                opacity: selectedPatterns.length === 0 ? 0.5 : 1,
              }}
            >
              <Trash2 style={{ width: '0.875rem', height: '0.875rem' }} />
              <span>{purgingBulk ? 'Purging...' : `Purge Selected (${selectedPatterns.length})`}</span>
            </button>

            {/* ⚡ Execute Bulk Sweep Button */}
            <button
              type="button"
              onClick={handleExecuteBulkSweep}
              disabled={executing || purgingBulk || totalSelectedRows === 0}
              style={{
                padding: '0.625rem 1.25rem',
                backgroundColor: executing || totalSelectedRows === 0 ? '#71717a' : '#f59e0b',
                color: '#09090b',
                fontSize: '0.75rem',
                fontWeight: 800,
                borderRadius: '0.75rem',
                border: 'none',
                boxShadow: '0 10px 15px -3px rgba(245, 158, 11, 0.3)',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                cursor: executing || totalSelectedRows === 0 ? 'not-allowed' : 'pointer',
              }}
            >
              <Sparkles style={{ width: '1rem', height: '1rem' }} />
              <span>{executing ? 'Sweeping...' : `Execute Bulk Sweep (${totalSelectedRows} Rows)`}</span>
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
};

export default BulkSweepHubModal;