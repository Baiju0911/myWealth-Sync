import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import {
  X,
  Sparkles,
  Check,
  ArrowRightLeft,
  Radio,
  Building2,
  UserCheck,
  Fingerprint,
  Loader2,
  ShieldCheck,
} from 'lucide-react';
import { narrationTaggingApi } from '../../../api/narrationTaggingApi';

interface TagRuleBuilderModalProps {
  isOpen: boolean;
  onClose: () => void;
  headerScope: string;
  parentGroupTag: string;
  subgroupTag?: string | null;
  selectedTxnIds: (string | number)[];
  activeVendorName?: string;
  defaultPattern?: string;
  vectorType: 'Debit' | 'Credit';
  onSuccess: (matchedCount: number) => void;
}

export const TagRuleBuilderModal: React.FC<TagRuleBuilderModalProps> = ({
  isOpen,
  onClose,
  headerScope,
  parentGroupTag,
  subgroupTag,
  selectedTxnIds,
  activeVendorName,
  defaultPattern,
  vectorType,
  onSuccess,
}) => {
  const [loading, setLoading] = useState<boolean>(false);
  const [candidateAnchors, setCandidateAnchors] = useState<string[]>([]);
  const [selectedAnchor, setSelectedAnchor] = useState<string>('');
  const [customAnchor, setCustomAnchor] = useState<string>('');

  // Structured fields from backend synthesis
  const [rawNarration, setRawNarration] = useState<string>('');
  const [sourceAccount, setSourceAccount] = useState<string>('');
  const [sourceAccountId, setSourceAccountId] = useState<number | null>(null);
  const [destAccount, setDestAccount] = useState<string>('');
  const [selectedRail, setSelectedRail] = useState<string>('ANY');

  // 🎯 Account Scope: 'PAIR' (locks source_account_id), 'SOURCE_ONLY', or 'ANY'
  const [accountScope, setAccountScope] = useState<'PAIR' | 'SOURCE_ONLY' | 'ANY'>('PAIR');

  // Rule settings
  const [matchType, setMatchType] = useState<'CONTAINS' | 'EXACT'>('CONTAINS');
  const [requireContra, setRequireContra] = useState<boolean>(true);
  const [allowedVector, setAllowedVector] = useState<'OUTFLOW' | 'INFLOW' | 'ANY'>(
    vectorType === 'Debit' ? 'OUTFLOW' : 'INFLOW'
  );
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen) return;

    setLoading(true);

    narrationTaggingApi
      .synthesizeRuleContext({
        transaction_ids: selectedTxnIds,
        cluster_pattern: defaultPattern,
        vendor_name: activeVendorName,
      })
      .then((data) => {
        setCandidateAnchors(data.tokens || []);
        if (data.tokens && data.tokens.length > 0) {
          setSelectedAnchor(data.tokens[0]);
        }

        setRawNarration(data.raw_narration || defaultPattern || '');
        setSourceAccount(data.source_account || '');
        setDestAccount(data.destination_account || '');
        setSourceAccountId(data.source_account_id || null);

        if (data.detected_rail) {
          setSelectedRail(data.detected_rail);
        }

        if (data.is_contra !== undefined) {
          setRequireContra(data.is_contra);
        }
      })
      .catch((err) => {
        console.error('Failed to synthesize rule context:', err);
      })
      .finally(() => setLoading(false));
  }, [isOpen, selectedTxnIds, activeVendorName, defaultPattern]);

  if (!isOpen) return null;

  const activeAnchorValue = customAnchor.trim()
    ? customAnchor.trim().toUpperCase()
    : selectedAnchor;

  const handleSaveAndApply = async () => {
    if (!activeAnchorValue) return;
    setIsSubmitting(true);
    try {
      let patternToSave = activeAnchorValue;
      if (selectedRail !== 'ANY' && !activeAnchorValue.includes(selectedRail)) {
        patternToSave = `${selectedRail}*${activeAnchorValue}`;
      }

      const createdRule = await narrationTaggingApi.createTagRule({
        keyword_pattern: patternToSave,
        match_type: matchType,
        allowed_vector: allowedVector,
        header_scope: headerScope,
        parent_group_tag: parentGroupTag,
        subgroup_tag: subgroupTag || null,
        require_internal_contra: requireContra,
        source_account_id: accountScope !== 'ANY' ? sourceAccountId : null,
        priority: 100,
        is_active: true,
      });

      const applyRes = await narrationTaggingApi.applyRuleToStream(createdRule.id);
      onSuccess(applyRes.matched_rows);
      onClose();
    } catch (err: any) {
      alert(err?.response?.data?.detail || err.message || 'Error saving rule');
    } finally {
      setIsSubmitting(false);
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-10000 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md font-mono text-zinc-100">
      <div className="bg-zinc-950 border border-zinc-800 rounded-2xl w-full max-w-2xl flex flex-col shadow-2xl overflow-hidden border-t-2 border-t-emerald-500">
        
        {/* Header */}
        <div className="flex justify-between items-center px-6 py-4 border-b border-zinc-800 bg-zinc-900/60">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-emerald-950/80 border border-emerald-800/60 text-emerald-400">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-100 flex items-center gap-2">
                <span>Rule Synthesis Engine</span>
                <span className="text-zinc-500">➔</span>
                <span className="text-emerald-400 font-bold">{parentGroupTag}</span>
              </h3>
              <p className="text-[10px] text-zinc-400 font-sans mt-0.5">
                Automatically tags matching stream entries under <span className="text-zinc-200">{headerScope}</span>
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

        {/* Workspace Body */}
        <div className="p-6 flex flex-col gap-5 max-h-[80vh] overflow-y-auto">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-zinc-400">
              <Loader2 className="w-6 h-6 animate-spin text-emerald-400" />
              <span className="text-xs">Analyzing narration patterns with backend NLP...</span>
            </div>
          ) : (
            <>
              {/* Captured Narration Strip */}
              <div className="bg-zinc-900/50 border border-zinc-800/90 rounded-xl p-3.5 space-y-2 shadow-inner">
                <div className="flex justify-between items-center text-[10px] uppercase font-bold text-zinc-400 tracking-wider">
                  <span className="flex items-center gap-1.5">
                    <Fingerprint className="w-3.5 h-3.5 text-amber-400" />
                    <span>Captured Transaction Narration</span>
                  </span>
                  <span className="text-amber-400 font-mono">{headerScope}</span>
                </div>
                <div className="text-[11px] font-mono text-zinc-200 bg-zinc-950/90 p-2.5 rounded-lg border border-zinc-800/80 wrap-break-word leading-relaxed select-all">
                  {rawNarration || defaultPattern || '#CONTRA'}
                </div>
              </div>

              {/* Account Route Context & Bank Specificity */}
              <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-xl p-3.5 space-y-2.5">
                <div className="flex justify-between items-center">
                  <span className="text-[10px] font-bold text-cyan-400 uppercase tracking-wider flex items-center gap-1.5">
                    <Building2 className="w-3.5 h-3.5 text-cyan-400" /> Account Route & Bank Specificity
                  </span>
                  <div className="flex gap-1">
                    {(['PAIR', 'SOURCE_ONLY', 'ANY'] as const).map((mode) => (
                      <button
                        key={mode}
                        type="button"
                        onClick={() => setAccountScope(mode)}
                        className={`px-2 py-0.5 rounded text-[9px] font-bold border transition-colors cursor-pointer ${
                          accountScope === mode
                            ? 'bg-cyan-950 text-cyan-300 border-cyan-500 shadow-xs'
                            : 'bg-zinc-950 text-zinc-500 border-zinc-800 hover:text-zinc-300'
                        }`}
                      >
                        {mode === 'PAIR' ? 'Specific Bank Pair' : mode === 'SOURCE_ONLY' ? 'Source Bank Only' : 'Any Bank'}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex items-center gap-2 text-xs">
                  <span className="px-2.5 py-1.5 bg-zinc-950 border border-cyan-900/60 rounded-lg text-cyan-300 font-bold font-mono">
                    {sourceAccount || 'Source Bank'}
                  </span>
                  <ArrowRightLeft className="w-3.5 h-3.5 text-zinc-500" />
                  <span className="px-2.5 py-1.5 bg-zinc-950 border border-cyan-900/60 rounded-lg text-cyan-300 font-bold font-mono">
                    {destAccount || 'Destination Bank'}
                  </span>
                </div>
              </div>

              {/* Protocol / Channel Rail Filter */}
              <div className="space-y-2">
                <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-1.5">
                  <Radio className="w-3.5 h-3.5 text-blue-400" /> Protocol / Channel Rail Filter
                </span>
                <div className="grid grid-cols-7 gap-1.5">
                  {['ANY', 'UPI', 'NEFT', 'IMPS', 'RTGS', 'ATM', 'NACH'].map((rail) => (
                    <button
                      key={rail}
                      type="button"
                      onClick={() => setSelectedRail(rail)}
                      className={`py-1.5 rounded-lg text-xs font-bold border transition-all text-center cursor-pointer ${
                        selectedRail === rail
                          ? 'bg-blue-600 border-blue-400 text-white shadow-xs'
                          : 'bg-zinc-900/70 border-zinc-800 text-zinc-400 hover:text-zinc-200'
                      }`}
                    >
                      {rail === selectedRail && rail !== 'ANY' ? `⚡ ${rail}` : rail}
                    </button>
                  ))}
                </div>
              </div>

              {/* Extracted Entity Anchors */}
              <div className="space-y-2.5">
                <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                  <UserCheck className="w-3.5 h-3.5 text-emerald-400" /> Extracted Keyword Anchors (Entity, VPA & Rail)
                </span>

                <div className="flex flex-wrap gap-2">
                  {candidateAnchors.length === 0 ? (
                    <span className="text-zinc-500 text-xs">Type a custom keyword anchor below:</span>
                  ) : (
                    candidateAnchors.map((token) => {
                      const isSelected = activeAnchorValue === token;
                      return (
                        <button
                          key={token}
                          type="button"
                          onClick={() => {
                            setSelectedAnchor(token);
                            setCustomAnchor('');
                          }}
                          className={`px-3 py-1.5 rounded-xl text-xs font-bold border transition-all cursor-pointer ${
                            isSelected
                              ? 'bg-emerald-600 border-emerald-400 text-white shadow-sm scale-102'
                              : 'bg-zinc-900 border-zinc-800 text-zinc-300 hover:border-zinc-700 hover:text-white'
                          }`}
                        >
                          {token}
                        </button>
                      );
                    })
                  )}
                </div>

                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="text"
                    value={customAnchor}
                    onChange={(e) => setCustomAnchor(e.target.value)}
                    placeholder="Or define custom keyword pattern (e.g. BAIJU.S.NAIR or SIBL)..."
                    className="flex-1 bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-xs text-emerald-300 font-bold outline-none focus:border-emerald-500 shadow-inner"
                  />
                  {customAnchor && (
                    <button
                      type="button"
                      onClick={() => setCustomAnchor('')}
                      className="text-xs text-zinc-500 hover:text-zinc-300 px-2 cursor-pointer"
                    >
                      Clear
                    </button>
                  )}
                </div>
              </div>

              {/* Logic Criteria Grid */}
              <div className="grid grid-cols-3 gap-3 pt-1">
                {/* Flow Vector */}
                <div className="bg-zinc-900/40 border border-zinc-800/80 p-3 rounded-xl space-y-2">
                  <label className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider block">
                    Flow Direction
                  </label>
                  <div className="flex flex-col gap-1.5">
                    {(['OUTFLOW', 'INFLOW', 'ANY'] as const).map((v) => (
                      <button
                        key={v}
                        type="button"
                        onClick={() => setAllowedVector(v)}
                        className={`py-1.5 rounded-lg text-[10px] font-bold border text-center transition-all cursor-pointer ${
                          allowedVector === v
                            ? 'bg-zinc-800 text-amber-300 border-amber-500/60 shadow-xs'
                            : 'bg-zinc-950 text-zinc-500 border-zinc-800 hover:text-zinc-300'
                        }`}
                      >
                        {v}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Match Mode */}
                <div className="bg-zinc-900/40 border border-zinc-800/80 p-3 rounded-xl space-y-2">
                  <label className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider block">
                    Match Mode
                  </label>
                  <div className="flex flex-col gap-1.5">
                    {(['CONTAINS', 'EXACT'] as const).map((m) => (
                      <button
                        key={m}
                        type="button"
                        onClick={() => setMatchType(m)}
                        className={`py-1.5 rounded-lg text-[10px] font-bold border text-center transition-all cursor-pointer ${
                          matchType === m
                            ? 'bg-zinc-800 text-emerald-400 border-emerald-500/60 shadow-xs'
                            : 'bg-zinc-950 text-zinc-500 border-zinc-800 hover:text-zinc-300'
                        }`}
                      >
                        {m}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Internal Transfer Scope */}
                <div className="bg-zinc-900/40 border border-zinc-800/80 p-3 rounded-xl flex flex-col justify-between">
                  <label className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider block">
                    Transfer Scope
                  </label>
                  <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer pb-2 select-none">
                    <input
                      type="checkbox"
                      checked={requireContra}
                      onChange={(e) => setRequireContra(e.target.checked)}
                      className="w-4 h-4 rounded border-zinc-700 text-emerald-500 focus:ring-0 bg-zinc-900 cursor-pointer"
                    />
                    <span className="flex items-center gap-1.5 text-[11px] leading-tight">
                      <ShieldCheck className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                      Both Accounts Internal
                    </span>
                  </label>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-zinc-800 px-6 py-4 bg-zinc-900/60 flex justify-between items-center">
          <div className="text-xs text-zinc-400">
            Target Tag: <strong className="text-emerald-400 font-bold">{parentGroupTag}</strong>
            {subgroupTag ? ` ➔ ${subgroupTag}` : ''}
          </div>
          <div className="flex items-center gap-3">
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
              disabled={!activeAnchorValue || isSubmitting || loading}
              className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded-xl text-xs font-bold flex items-center gap-2 shadow-lg transition-all cursor-pointer"
            >
              <Check className="w-4 h-4" />
              <span>{isSubmitting ? 'Tagging Transactions...' : 'Save Rule & Tag Matching Lines'}</span>
            </button>
          </div>
        </div>

      </div>
    </div>,
    document.body
  );
};