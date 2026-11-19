import React, { useState, useEffect, useMemo } from 'react';
import { createPortal } from 'react-dom';
import {
  X,
  Sparkles,
  Check,
  ArrowRight,
  Building2,
  Tag,
  Plus,
  Layers,
  Search,
  Sliders,
  Zap,
} from 'lucide-react';
import { narrationTaggingApi } from '../../../api/narrationTaggingApi';

interface TagRuleBuilderModalProps {
  isOpen: boolean;
  onClose: () => void;
  headerScope: string;
  parentGroupTag: string;
  subgroupTag?: string | null;
  onSubgroupTagChange?: (newSub: string | null) => void;
  selectedTransactions: any[];
  activeVendorName?: string;
  onSuccess: (matchedCount: number) => void;
}

export const TagRuleBuilderModal: React.FC<TagRuleBuilderModalProps> = ({
  isOpen,
  onClose,
  headerScope,
  parentGroupTag,
  subgroupTag,
  onSubgroupTagChange,
  selectedTransactions = [],
  activeVendorName,
  onSuccess,
}) => {
  const [activeSubgroup, setActiveSubgroup] = useState<string>(subgroupTag || '');
  const [isAddingNewSubgroup, setIsAddingNewSubgroup] = useState<boolean>(false);
  const [inlineNewSubgroup, setInlineNewSubgroup] = useState<string>('');

  // Multi-Token state
  const [selectedAnchors, setSelectedAnchors] = useState<string[]>([]);
  const [customTokenInput, setCustomTokenInput] = useState<string>('');
  const [userAddedTokens, setUserAddedTokens] = useState<string[]>([]);

  // Backend-hydrated context fallback when line item lacks destination_account_id
  const [backendContext, setBackendContext] = useState<{
    source_account?: string;
    source_account_id?: number | null;
    destination_account?: string;
    destination_account_id?: number | null;
    detected_rail?: string;
    tokens?: string[];
  } | null>(null);

  const [accountScope, setAccountScope] = useState<'PAIR' | 'SOURCE_ONLY' | 'ANY'>('PAIR');
  const [lockDirection, setLockDirection] = useState<boolean>(true);
  const [lockRail, setLockRail] = useState<boolean>(true);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Hydrate missing account IDs from backend synthesize-context when modal opens
  useEffect(() => {
    if (!isOpen || !selectedTransactions || selectedTransactions.length === 0) {
      setBackendContext(null);
      return;
    }

    const first = selectedTransactions[0];
    const hostId = first.account_id ?? first.source_account_id ?? first.account?.id ?? null;
    const rawDestId =
      first.destination_account_id ??
      first.target_account_id ??
      first.contra_meta?.to_account_id ??
      first.suggested_contra_account_id ??
      null;

    // Fetch backend context if destination is missing or collides with host account ID
    if (!rawDestId || (hostId && Number(rawDestId) === Number(hostId))) {
      const txnIds = selectedTransactions
        .map((t) => t.row_identifier || t.id)
        .filter(Boolean);
      narrationTaggingApi
        .synthesizeRuleContext({
          transaction_ids: txnIds,
          vendor_name: activeVendorName || first.vendor_name || '',
        })
        .then((res) => {
          setBackendContext(res);
        })
        .catch(() => {
          setBackendContext(null);
        });
    } else {
      setBackendContext(null);
    }
  }, [isOpen, selectedTransactions, activeVendorName]);

  // Telemetry Engine
  const telemetry = useMemo(() => {
    if (!selectedTransactions || selectedTransactions.length === 0) {
      return {
        count: 0,
        amount: 0,
        date: '',
        displayNarration: '',
        rawNarrations: [] as string[],
        sourceAccount: '',
        sourceAccountId: null as number | null,
        sourceMasked: '',
        destAccount: '',
        destAccountId: null as number | null,
        destMasked: '',
        detectedRail: 'ANY',
        direction: 'OUTFLOW' as 'OUTFLOW' | 'INFLOW',
        isInternalContra: false,
        referenceNo: '',
      };
    }

    const first = selectedTransactions[0];
    const contraMeta = first.contra_meta || {};
    const rawNarrations = selectedTransactions
      .map((t) => t.raw_narration || t.narration || t.description || '')
      .filter(Boolean);

    const totalAmt = selectedTransactions.reduce((acc, t) => {
      const amt = Number(t.debit || t.credit || t.amount || 0);
      return acc + Math.abs(amt);
    }, 0);

    // 1. Host account of the selected statement line(s)
    const hostAccId: number | null =
      first.account_id ??
      backendContext?.source_account_id ??
      first.source_account_id ??
      first.account?.id ??
      null;

    const srcAccountId: number | null = hostAccId ? Number(hostAccId) : null;

    // 2. Resolve the OTHER account in the contra pair (never equal to srcAccountId)
    const contraFromId = contraMeta.from_account_id ? Number(contraMeta.from_account_id) : null;
    const contraToId = contraMeta.to_account_id ? Number(contraMeta.to_account_id) : null;
    const rawDestId =
      first.destination_account_id ??
      first.target_account_id ??
      backendContext?.destination_account_id ??
      first.suggested_contra_account_id ??
      first.suggested_contra_account?.id ??
      null;

    let counterpartyAccId: number | null = rawDestId ? Number(rawDestId) : null;
    if (!counterpartyAccId || (srcAccountId && counterpartyAccId === srcAccountId)) {
      if (contraFromId && srcAccountId !== contraFromId) {
        counterpartyAccId = contraFromId;
      } else if (contraToId && srcAccountId !== contraToId) {
        counterpartyAccId = contraToId;
      } else {
        counterpartyAccId = null;
      }
    }

    const destAccountId: number | null = counterpartyAccId;

    // 3. Resolve Source & Destination display names symmetrically
    const isHostReceiver = Boolean(
      contraToId && srcAccountId && contraToId === srcAccountId
    );

    const srcName =
      first.bank_name ||
      first.account_name ||
      first.account?.name ||
      (isHostReceiver ? contraMeta.to_account_name : contraMeta.from_account_name) ||
      backendContext?.source_account ||
      first.source_account_name ||
      first.source_account ||
      'Origin Account';

    const srcNumber =
      first.bank_last4 ||
      first.source_account_number ||
      first.account_number ||
      first.account?.account_number ||
      (isHostReceiver ? contraMeta.to_account_number : contraMeta.from_account_number) ||
      '';
    const srcMasked = srcNumber
      ? `••${String(srcNumber).slice(-4)}`
      : first.source_account_display || '';

    const destName =
      (isHostReceiver ? contraMeta.from_account_name : contraMeta.to_account_name) ||
      backendContext?.destination_account ||
      first.target_account_name ||
      first.destination_account_name ||
      first.suggested_contra_account?.name ||
      first.destination_account ||
      first.contra_account_name ||
      '';

    const destNumber =
      (isHostReceiver ? contraMeta.from_account_number : contraMeta.to_account_number) ||
      first.target_account_number ||
      first.destination_account_number ||
      first.suggested_contra_account?.account_number ||
      first.target_account_no ||
      '';
    const destMasked = destNumber
      ? `••${String(destNumber).slice(-4)}`
      : first.target_account_display || '';

    let rail = first.detected_rail || first.rail || backendContext?.detected_rail || '';
    if (!rail || rail === 'ANY' || rail === 'BANK_TRANSFER') {
      const combined = (rawNarrations.join(' ') + ' ' + (first.narration || '')).toUpperCase();
      if (combined.includes('UPI/') || combined.includes('@') || combined.includes('UPI')) rail = 'UPI';
      else if (combined.includes('NEFT')) rail = 'NEFT';
      else if (combined.includes('IMPS')) rail = 'IMPS';
      else if (combined.includes('RTGS')) rail = 'RTGS';
      else if (combined.includes('ATM')) rail = 'ATM';
      else rail = 'ANY';
    }

    const hasOutflows = selectedTransactions.some(
      (t) =>
        ['OUTFLOW', 'DEBIT', 'DR'].includes(String(t.direction || t.vector_type || '').toUpperCase()) ||
        Number(t.debit) > 0 ||
        Number(t.amount) < 0
    );
    const direction = hasOutflows ? 'OUTFLOW' : 'INFLOW';

    let refNum = first.reference_no || first.ref_no || '';
    if (!refNum && rawNarrations[0]) {
      const refMatch = rawNarrations[0].match(/(\d{10,14})/);
      if (refMatch) refNum = refMatch[1];
    }

    const hasValidPair = Boolean(
      srcAccountId &&
        (destAccountId || (destName && destName !== srcName)) &&
        (!destAccountId || srcAccountId !== destAccountId)
    );

    return {
      count: selectedTransactions.length,
      amount: totalAmt,
      date: first.date || first.transaction_date || '',
      displayNarration: first.narration || first.clean_narration || '',
      rawNarrations,
      sourceAccount: srcName,
      sourceAccountId: srcAccountId,
      sourceMasked: srcMasked,
      destAccount: destName,
      destAccountId: destAccountId,
      destMasked: destMasked,
      detectedRail: rail,
      direction,
      isInternalContra: Boolean(
        hasValidPair || contraMeta.is_self_transfer || first.suggested_contra_account_id
      ),
      referenceNo: refNum,
    };
  }, [selectedTransactions, backendContext]);

  const canStrictPair = Boolean(
    telemetry.sourceAccountId &&
      (telemetry.destAccountId ||
        (telemetry.destAccount && telemetry.destAccount !== telemetry.sourceAccount)) &&
      (!telemetry.destAccountId || telemetry.sourceAccountId !== telemetry.destAccountId)
  );

  useEffect(() => {
    if (isOpen) {
      setActiveSubgroup(subgroupTag || '');
      setUserAddedTokens([]);
      setSelectedAnchors([]);
    }
  }, [isOpen, subgroupTag]);

  // Calibrate default scope whenever telemetry updates
  useEffect(() => {
    if (!isOpen) return;
    if (canStrictPair) {
      setAccountScope('PAIR');
    } else if (telemetry.sourceAccountId) {
      setAccountScope('SOURCE_ONLY');
    } else {
      setAccountScope('ANY');
    }
  }, [isOpen, canStrictPair, telemetry.sourceAccountId]);

  // Extract candidate tokens across inspected transactions
  const autoExtractedTokens = useMemo(() => {
    if (!selectedTransactions || selectedTransactions.length === 0) return [];

    const tokenFrequency = new Map<string, number>();

    const extractTokens = (raw: string, vendor?: string) => {
      const set = new Set<string>();

      if (vendor) {
        const cleanV = vendor.replace(/\(OUT\)|\(IN\)|#\w+/g, '').trim();
        if (cleanV) set.add(cleanV.toUpperCase());
      }

      if (raw.includes('/')) {
        const parts = raw.split('/').map((p) => p.trim()).filter(Boolean);
        if (parts.length >= 4 && parts[3].length > 2 && isNaN(Number(parts[3]))) {
          set.add(parts[3].toUpperCase());
        }
        if (parts.length >= 2 && parts[1].length <= 6 && /^[A-Z]+$/i.test(parts[1])) {
          set.add(parts[1].toUpperCase());
        }
      }

      const vpaMatch = raw.match(/([A-Za-z0-9._-]+@[A-Za-z0-9]+)/);
      if (vpaMatch) {
        set.add(vpaMatch[1].toUpperCase());
        set.add(vpaMatch[1].split('@')[0].toUpperCase());
      } else {
        const dotMatch = raw.match(/([A-Z]{3,}(?:\.[A-Z]{1,})+)/i);
        if (dotMatch) {
          set.add(dotMatch[1].toUpperCase());
        }
      }

      if (vendor) {
        vendor.split(/\s+/).forEach((w) => {
          if (w.length > 3 && !['OUTFLOW', 'INFLOW', 'CONTRA'].includes(w.toUpperCase())) {
            set.add(w.toUpperCase());
          }
        });
      }

      return Array.from(set).filter(
        (t) => !['#CONTRA', 'CONTRA', 'BALANCE', 'NOTRF', 'TRANSFER', 'PAYMENT'].includes(t)
      );
    };

    selectedTransactions.forEach((txn) => {
      const raw = txn.raw_narration || txn.narration || '';
      const v = txn.vendor_name || txn.vendor || txn.payee || activeVendorName;
      const tokens = extractTokens(raw, v);
      tokens.forEach((tk) => {
        tokenFrequency.set(tk, (tokenFrequency.get(tk) || 0) + 1);
      });
    });

    if (backendContext?.tokens) {
      backendContext.tokens.forEach((tk) => {
        const up = String(tk).trim().toUpperCase();
        if (up && !tokenFrequency.has(up)) {
          tokenFrequency.set(up, 1);
        }
      });
    }

    return Array.from(tokenFrequency.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([token]) => token);
  }, [selectedTransactions, activeVendorName, backendContext]);

  // Combine auto-extracted tokens with custom tokens added by user
  const allCandidateTokens = useMemo(() => {
    return Array.from(new Set([...userAddedTokens, ...autoExtractedTokens]));
  }, [userAddedTokens, autoExtractedTokens]);

  // Initialize selection with the first primary token
  useEffect(() => {
    if (autoExtractedTokens.length > 0 && selectedAnchors.length === 0) {
      setSelectedAnchors([autoExtractedTokens[0]]);
    }
  }, [autoExtractedTokens, selectedAnchors.length]);

  if (!isOpen) return null;

  const handleToggleToken = (token: string) => {
    setSelectedAnchors((prev) =>
      prev.includes(token) ? prev.filter((t) => t !== token) : [...prev, token]
    );
  };

  const handleAddCustomToken = () => {
    const clean = customTokenInput.trim().toUpperCase();
    if (!clean) return;

    if (!userAddedTokens.includes(clean)) {
      setUserAddedTokens((prev) => [clean, ...prev]);
    }
    if (!selectedAnchors.includes(clean)) {
      setSelectedAnchors((prev) => [...prev, clean]);
    }
    setCustomTokenInput('');
  };

  const handleCreateSubgroupInline = async () => {
    if (!inlineNewSubgroup.trim()) return;
    const cleanSub = inlineNewSubgroup.trim().toUpperCase();

    try {
      await narrationTaggingApi.createGroup({
        header_scope: headerScope,
        group_tag: parentGroupTag,
        subgroup_tag: cleanSub,
      });
      setActiveSubgroup(cleanSub);
      if (onSubgroupTagChange) onSubgroupTagChange(cleanSub);
      setIsAddingNewSubgroup(false);
      setInlineNewSubgroup('');
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to create subgroup in hierarchy');
    }
  };

  const handleSaveAndApply = async () => {
    if (selectedAnchors.length === 0) return;
    setIsSubmitting(true);
    try {
      const primaryAnchor = selectedAnchors[0];
      const isStrictPair = accountScope === 'PAIR' && canStrictPair;

      const resolvedSourceId =
        accountScope === 'PAIR' || accountScope === 'SOURCE_ONLY'
          ? telemetry.sourceAccountId
          : null;

      const resolvedDestId =
        isStrictPair &&
        telemetry.destAccountId &&
        telemetry.destAccountId !== resolvedSourceId
          ? telemetry.destAccountId
          : null;

      const resolvedRail =
        lockRail && telemetry.detectedRail && telemetry.detectedRail !== 'ANY'
          ? telemetry.detectedRail.trim().toUpperCase()
          : '';

      const createdRule = await narrationTaggingApi.createTagRule({
        keyword_pattern: primaryAnchor,
        match_tokens: selectedAnchors,
        match_type: 'CONTAINS',
        allowed_vector: (lockDirection ? telemetry.direction : 'ANY') as 'ANY' | 'OUTFLOW' | 'INFLOW',
        allowed_rail: resolvedRail,
        header_scope: headerScope,
        parent_group_tag: parentGroupTag,
        subgroup_tag: activeSubgroup || '',
        require_internal_contra: isStrictPair,
        source_account_id: resolvedSourceId,
        destination_account_id: resolvedDestId,
        ...(isStrictPair && telemetry.destAccount && telemetry.destAccount !== telemetry.sourceAccount
          ? { destination_account: telemetry.destAccount }
          : {}),
        priority: isStrictPair ? 100 : 50,
        is_active: true,
      });

      const applyRes = await narrationTaggingApi.applyRuleToStream(createdRule.id);
      onSuccess(applyRes.matched_rows);
      onClose();
    } catch (err: any) {
      const detail =
        err?.response?.data?.destination_account_id?.[0] ||
        err?.response?.data?.detail ||
        err.message ||
        'Error saving tag rule';
      alert(detail);
    } finally {
      setIsSubmitting(false);
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-10000 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md font-mono text-zinc-100 animate-in fade-in duration-150">
      <div className="bg-zinc-950 border border-zinc-800 rounded-2xl w-full max-w-2xl flex flex-col shadow-2xl overflow-hidden border-t-2 border-t-emerald-500">
        {/* Header Bar */}
        <div className="flex justify-between items-center px-6 py-4 border-b border-zinc-800/80 bg-zinc-900/50">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold uppercase tracking-wider text-zinc-200">
                  Synthesize Stream Tag Rule
                </span>
                <span className="text-zinc-600">/</span>
                <span className="text-xs font-bold text-emerald-400">{parentGroupTag}</span>
                {activeSubgroup && (
                  <>
                    <span className="text-zinc-600">➔</span>
                    <span className="text-xs font-bold text-cyan-300">{activeSubgroup}</span>
                  </>
                )}
              </div>
              <p className="text-[11px] text-zinc-400 font-sans mt-0.5">
                Auto-tags future stream transactions under header scope:{' '}
                <span className="text-zinc-200 font-semibold">{headerScope}</span>
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-zinc-400 hover:text-zinc-100 p-1.5 rounded-lg hover:bg-zinc-800 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 flex flex-col gap-4 max-h-[78vh] overflow-y-auto">
          {/* SECTION 1: Selected Transaction Inspector HUD */}
          <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-4 flex flex-col gap-3 shadow-inner">
            <div className="flex justify-between items-center text-[10px] uppercase font-bold tracking-wider text-zinc-400">
              <span className="flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-emerald-400" />
                <span>Selected Line Telemetry ({telemetry.count} Selected)</span>
              </span>
              <div className="flex items-center gap-2">
                {telemetry.amount > 0 && (
                  <span
                    className={`px-2 py-0.5 rounded font-mono font-bold text-xs ${
                      telemetry.direction === 'OUTFLOW'
                        ? 'bg-rose-950/80 text-rose-300 border border-rose-800/60'
                        : 'bg-emerald-950/80 text-emerald-300 border border-emerald-800/60'
                    }`}
                  >
                    {telemetry.direction === 'OUTFLOW' ? '-' : '+'}₹
                    {telemetry.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </span>
                )}
                <span className="text-zinc-500 font-normal">{telemetry.date}</span>
              </div>
            </div>

            {/* Account Route Flow Visualization */}
            <div className="flex items-center justify-between bg-zinc-950/90 border border-zinc-800/90 rounded-xl p-3">
              <div className="flex items-center gap-2.5">
                <Building2 className="w-4 h-4 text-cyan-400 shrink-0" />
                <div>
                  <span className="text-[9px] text-zinc-500 uppercase font-bold block">
                    Source Account
                  </span>
                  <span className="text-xs font-bold text-zinc-200 font-mono">
                    {telemetry.sourceAccount}{' '}
                    <span className="text-zinc-500 font-normal">{telemetry.sourceMasked}</span>
                  </span>
                </div>
              </div>

              <div className="flex flex-col items-center px-4">
                <span
                  className={`text-[9px] font-bold px-2 py-0.5 rounded uppercase border flex items-center gap-1 ${
                    telemetry.direction === 'OUTFLOW'
                      ? 'bg-rose-950/60 text-rose-300 border-rose-800/80'
                      : 'bg-emerald-950/60 text-emerald-300 border-emerald-800/80'
                  }`}
                >
                  <span>{telemetry.direction}</span>
                  {telemetry.detectedRail !== 'ANY' && (
                    <span className="text-zinc-400 font-normal">({telemetry.detectedRail})</span>
                  )}
                </span>
                <ArrowRight className="w-4 h-4 text-zinc-500 mt-1" />
              </div>

              <div className="flex items-center gap-2.5 text-right">
                <div>
                  <span className="text-[9px] text-zinc-500 uppercase font-bold block">
                    Destination Account
                  </span>
                  <span className="text-xs font-bold text-zinc-200 font-mono">
                    {telemetry.destAccount ? (
                      <>
                        {telemetry.destAccount}{' '}
                        <span className="text-zinc-500 font-normal">{telemetry.destMasked}</span>
                      </>
                    ) : (
                      <span className="text-zinc-500 font-normal italic">External / Unpaired</span>
                    )}
                  </span>
                </div>
                <Building2
                  className={`w-4 h-4 shrink-0 ${
                    telemetry.destAccount ? 'text-emerald-400' : 'text-zinc-600'
                  }`}
                />
              </div>
            </div>

            {/* Clean Parsed Summary */}
            {telemetry.displayNarration && (
              <div className="text-[11px] font-sans text-zinc-300 bg-zinc-900/40 px-3 py-1.5 rounded-lg border border-zinc-800/60">
                <span className="text-zinc-500 font-bold mr-1.5">Parsed:</span>
                {telemetry.displayNarration}
              </div>
            )}

            {/* Raw Monospace Bank Telemetry Strip */}
            <div className="text-[10px] font-mono text-zinc-400 bg-zinc-950 p-2.5 rounded-lg border border-zinc-800/70 break-all leading-relaxed select-all">
              <span className="text-zinc-600 block text-[9px] uppercase font-bold mb-0.5">
                Raw Bank Narration Payload:
              </span>
              {telemetry.rawNarrations[0] || 'No raw narration payload loaded.'}
            </div>
          </div>

          {/* SECTION 2: Route Scope & Subgroup Bucket Configurator */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {/* Account Specificity Option */}
            <div className="bg-zinc-900/40 border border-zinc-800/90 rounded-xl p-3.5 space-y-2">
              <label className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-1.5">
                <Sliders className="w-3.5 h-3.5 text-cyan-400" /> Account Route Scope
              </label>
              <div className="flex flex-col gap-1.5">
                {(['PAIR', 'SOURCE_ONLY', 'ANY'] as const).map((mode) => {
                  const isDisabled = mode === 'PAIR' && !canStrictPair;
                  return (
                    <button
                      key={mode}
                      type="button"
                      disabled={isDisabled}
                      onClick={() => setAccountScope(mode)}
                      className={`px-2.5 py-1.5 rounded-lg text-xs font-medium border text-left transition-all flex items-center justify-between ${
                        isDisabled
                          ? 'bg-zinc-950/30 border-zinc-900 text-zinc-600 cursor-not-allowed opacity-60'
                          : accountScope === mode
                          ? 'bg-cyan-950/80 border-cyan-500 text-cyan-200 shadow-xs cursor-pointer'
                          : 'bg-zinc-950/60 border-zinc-800 text-zinc-400 hover:text-zinc-200 cursor-pointer'
                      }`}
                    >
                      <span>
                        {mode === 'PAIR'
                          ? 'Strict Pair (Source ➔ Destination)'
                          : mode === 'SOURCE_ONLY'
                          ? 'Host Account Only (Origin Bank)'
                          : 'Any Account (Global)'}
                      </span>
                      {accountScope === mode && !isDisabled && (
                        <Check className="w-3.5 h-3.5 text-cyan-400" />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Target Subgroup Selection */}
            <div className="bg-zinc-900/40 border border-zinc-800/90 rounded-xl p-3.5 space-y-2">
              <div className="flex justify-between items-center">
                <label className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-1.5">
                  <Tag className="w-3.5 h-3.5 text-amber-400" /> Subgroup Bucket
                </label>
                {!isAddingNewSubgroup ? (
                  <button
                    type="button"
                    onClick={() => setIsAddingNewSubgroup(true)}
                    className="text-[10px] text-emerald-400 hover:underline flex items-center gap-0.5 cursor-pointer font-sans"
                  >
                    <Plus className="w-3 h-3" /> New Subgroup
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => setIsAddingNewSubgroup(false)}
                    className="text-[10px] text-zinc-500 hover:text-zinc-300 cursor-pointer font-sans"
                  >
                    Cancel
                  </button>
                )}
              </div>

              {isAddingNewSubgroup ? (
                <div className="flex items-center gap-1.5 pt-1">
                  <input
                    type="text"
                    value={inlineNewSubgroup}
                    onChange={(e) => setInlineNewSubgroup(e.target.value)}
                    placeholder="e.g. SIB NRO 60 TO 81"
                    className="flex-1 bg-zinc-950 border border-cyan-600 rounded-lg px-2.5 py-1.5 text-xs text-cyan-300 font-bold outline-none"
                  />
                  <button
                    type="button"
                    onClick={handleCreateSubgroupInline}
                    disabled={!inlineNewSubgroup.trim()}
                    className="px-2.5 py-1.5 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white rounded-lg text-xs font-bold cursor-pointer transition-colors"
                  >
                    Create
                  </button>
                </div>
              ) : (
                <div className="p-2.5 bg-zinc-950/80 border border-zinc-800/80 rounded-lg flex items-center justify-between">
                  <span className="text-xs font-mono font-bold text-cyan-300">
                    {activeSubgroup || '-- None (Root Tag Only) --'}
                  </span>
                  {activeSubgroup && (
                    <button
                      type="button"
                      onClick={() => {
                        setActiveSubgroup('');
                        if (onSubgroupTagChange) onSubgroupTagChange(null);
                      }}
                      className="text-[10px] text-zinc-500 hover:text-rose-400 cursor-pointer underline font-sans"
                    >
                      Clear
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* SECTION 3: Multi-Select Matching Anchor Tokens (Checkboxes) */}
          <div className="bg-zinc-900/40 border border-zinc-800/90 rounded-xl p-4 space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
                <span>Select Matching Anchor Tokens ({selectedAnchors.length} Checked)</span>
              </span>
              <span className="text-[10px] text-zinc-500 font-sans">
                Rule matches if any checked token is found
              </span>
            </div>

            {/* Token Checkbox Chips */}
            <div className="flex flex-wrap gap-2 max-h-36 overflow-y-auto p-0.5">
              {allCandidateTokens.length === 0 ? (
                <div className="text-zinc-500 text-xs italic py-1">
                  No tokens extracted. Type a custom pattern below:
                </div>
              ) : (
                allCandidateTokens.map((token) => {
                  const isChecked = selectedAnchors.includes(token);
                  return (
                    <label
                      key={token}
                      onClick={(e) => {
                        e.preventDefault();
                        handleToggleToken(token);
                      }}
                      className={`px-3 py-1.5 rounded-xl text-xs font-bold font-mono border transition-all cursor-pointer flex items-center gap-2 select-none ${
                        isChecked
                          ? 'bg-emerald-950/80 border-emerald-500 text-emerald-300 shadow-sm ring-1 ring-emerald-500/30'
                          : 'bg-zinc-900/70 border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => {}}
                        className="w-3.5 h-3.5 accent-emerald-500 rounded border-zinc-700 bg-zinc-950 pointer-events-none"
                      />
                      <span>{token}</span>
                    </label>
                  );
                })
              )}
            </div>

            {/* Add Custom Token / Regex Pattern */}
            <div className="flex items-center gap-2 pt-1">
              <div className="relative flex-1">
                <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={customTokenInput}
                  onChange={(e) => setCustomTokenInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleAddCustomToken();
                    }
                  }}
                  placeholder="Type new alias or token (e.g. PRAVEEN, SIBL) and press Enter..."
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-lg pl-8 pr-3 py-2 text-xs text-emerald-300 font-mono font-bold outline-none focus:border-emerald-500 shadow-inner"
                />
              </div>
              <button
                type="button"
                onClick={handleAddCustomToken}
                disabled={!customTokenInput.trim()}
                className="px-3 py-2 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-zinc-200 border border-zinc-700 rounded-lg text-xs font-bold cursor-pointer transition-colors flex items-center gap-1"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add Token</span>
              </button>
            </div>
          </div>

          {/* SECTION 4: Live Rule Execution Summary Statement */}
          <div className="bg-emerald-950/20 border border-emerald-500/30 rounded-xl p-3.5 flex items-start gap-3">
            <Zap className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            <div className="text-xs leading-relaxed text-zinc-300">
              <span className="text-[10px] font-bold uppercase text-emerald-400 tracking-wider block mb-0.5">
                Auto-Tag Synthesis Impact (JSON Rule)
              </span>
              Future & existing{' '}
              <strong className="text-amber-300">{lockDirection ? telemetry.direction : 'ANY'}</strong>{' '}
              transactions{' '}
              {lockRail && telemetry.detectedRail !== 'ANY' && (
                <>via <strong className="text-blue-400">{telemetry.detectedRail}</strong> </>
              )}
              {accountScope === 'PAIR' && canStrictPair ? (
                <>
                  from <strong className="text-cyan-300">{telemetry.sourceAccount}</strong> to{' '}
                  <strong className="text-cyan-300">{telemetry.destAccount}</strong>{' '}
                </>
              ) : accountScope === 'SOURCE_ONLY' && telemetry.sourceAccount ? (
                <>
                  from <strong className="text-cyan-300">{telemetry.sourceAccount}</strong>{' '}
                </>
              ) : null}
              matching <span className="text-zinc-400">any token in</span>{' '}
              <strong className="text-emerald-300 font-mono">
                {selectedAnchors.length > 0
                  ? `[${selectedAnchors.map((t) => `"${t}"`).join(', ')}]`
                  : '[]'}
              </strong>{' '}
              will be auto-tagged under{' '}
              <strong className="text-emerald-400 font-bold">{parentGroupTag}</strong>
              {activeSubgroup ? (
                <>
                  {' '}
                  ➔ <strong className="text-cyan-300 font-bold">{activeSubgroup}</strong>
                </>
              ) : null}
              .
            </div>
          </div>
        </div>

        {/* Footer Bar */}
        <div className="border-t border-zinc-800/80 px-6 py-4 bg-zinc-900/50 flex justify-between items-center">
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={lockDirection}
                onChange={(e) => setLockDirection(e.target.checked)}
                className="w-4 h-4 rounded border-zinc-700 text-emerald-500 bg-zinc-900 cursor-pointer"
              />
              <span>Lock to {telemetry.direction}</span>
            </label>
            {telemetry.detectedRail !== 'ANY' && (
              <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={lockRail}
                  onChange={(e) => setLockRail(e.target.checked)}
                  className="w-4 h-4 rounded border-zinc-700 text-blue-500 bg-zinc-900 cursor-pointer"
                />
                <span>Lock to {telemetry.detectedRail}</span>
              </label>
            )}
          </div>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs text-zinc-400 hover:text-white font-bold transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSaveAndApply}
              disabled={selectedAnchors.length === 0 || isSubmitting || telemetry.count === 0}
              className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded-xl text-xs font-bold flex items-center gap-2 shadow-lg transition-all cursor-pointer"
            >
              <Check className="w-4 h-4" />
              <span>{isSubmitting ? 'Tagging Stream...' : 'Create Rule & Re-tag Stream'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
};