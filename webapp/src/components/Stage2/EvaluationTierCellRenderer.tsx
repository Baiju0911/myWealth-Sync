import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';

interface EvaluationTierCellProps {
  row: any;
}

function extractPayee(text: string) {
  if (!text) return "Direct Payment";
  const clean = text.replace(/^(?:Info\s*[:-]+\s*)+/i, '').replace(/\|+/g, '/').trim();
  const segments = clean.split('/').map(s => s.trim()).filter(Boolean);

  if (segments.length >= 2) {
    const candidates = [];
    for (let i = 1; i < segments.length; i++) {
      const seg = segments[i];
      if (/^(?:RRN|REF|UTR)?\s*[:.-]?\s*\d{6,18}$/i.test(seg)) continue;
      if (/^[A-Z]{3,5}$/.test(seg) && candidates.length === 0) continue;
      candidates.push(seg);
    }
    return candidates[0] || segments[1] || clean;
  }
  return clean;
}

export const EvaluationTierCellRenderer: React.FC<EvaluationTierCellProps> = ({ row }) => {
  const [isOpen, setIsOpen] = useState(false);
  const matrix = row.matrix_evaluation || {};

  const t4Hit = matrix.t4?.hit;
  const t5Hit = matrix.t5?.hit;
  const t2Weight = matrix.t2?.weight || 0;

  // Determine top winning gate
  let winnerKey: 't1' | 't2' | 't4' | 't5' = 't1';
  let winnerTag = "T1 FALLBACK";
  let winnerCategory = "Suspense";
  let badgeColor = "border-cyan-900/60 bg-cyan-950/20 text-cyan-400 hover:border-cyan-600";

  if (t4Hit) {
    winnerKey = 't4';
    winnerTag = "T4 RULE";
    winnerCategory = matrix.t4?.subcategory || row.resolved_subcategory || "Rule Match";
    badgeColor = "border-amber-900/80 bg-amber-950/40 text-amber-300 hover:border-amber-600";
  } else if (t5Hit) {
    winnerKey = 't5';
    winnerTag = "T5 AI";
    winnerCategory = matrix.t5?.subcategory || row.resolved_subcategory || "AI Memory";
    badgeColor = "border-emerald-900/80 bg-emerald-950/40 text-emerald-300 hover:border-emerald-600";
  } else if (t2Weight > 0 && matrix.t2?.category && matrix.t2?.category !== "None") {
    winnerKey = 't2';
    winnerTag = "T2 TUNNEL";
    winnerCategory = matrix.t2?.subcategory || "Transfer";
    badgeColor = "border-purple-900/80 bg-purple-950/40 text-purple-300 hover:border-purple-600";
  } else {
    // T1 Fallback
    const sub = matrix.t1?.subcategory || row.resolved_subcategory || "";
    winnerCategory = sub.toLowerCase().includes("suspense") ? "Suspense" : (sub || matrix.t1?.category || "Default");
  }

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsOpen(false);
    };
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  const rawNarration = row.narration_normalized || row.narration || "";
  const displayPayee = row.display_payee || row.payee || extractPayee(rawNarration);
  const amountVal = Number(row.debit || row.credit || row.amount || 0);

  const modalContent = isOpen ? (
    <div 
      className="fixed inset-0 z-[9999] bg-black/80 backdrop-blur-xs flex items-center justify-center p-4"
      onClick={() => setIsOpen(false)}
    >
      <div 
        className="bg-zinc-900 border border-zinc-800 rounded-xl max-w-lg w-full max-h-[85vh] flex flex-col shadow-2xl text-zinc-200 my-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex justify-between items-center border-b border-zinc-800 px-5 py-3.5 shrink-0">
          <div>
            <h3 className="font-bold text-xs uppercase tracking-wider text-zinc-100 flex items-center gap-2">
              <span>Evaluation Tier Matrix</span>
              <span className={`text-[10px] px-2 py-0.5 rounded font-mono font-bold border ${badgeColor}`}>
                ★ {winnerTag} WON
              </span>
            </h3>
            <p className="text-[10px] text-zinc-500 font-sans mt-0.5">Diagnostic inspection of 5 evaluation tiers</p>
          </div>
          <button 
            onClick={() => setIsOpen(false)}
            className="text-zinc-400 hover:text-zinc-100 text-base leading-none p-1 rounded hover:bg-zinc-800 transition-colors cursor-pointer"
          >
            ✕
          </button>
        </div>

        {/* Scrollable Body */}
        <div className="p-4 space-y-3 overflow-y-auto font-mono text-xs">
          {/* Target Txn Card */}
          <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800/80 space-y-1">
            <div className="flex justify-between items-start gap-2">
              <span className="text-zinc-100 font-sans font-semibold text-xs truncate">
                {displayPayee}
              </span>
              <span className="text-emerald-400 font-bold shrink-0">
                ₹{amountVal.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </div>
            <div className="text-zinc-500 text-[10px] break-all leading-tight">
              {rawNarration}
            </div>
          </div>

          {/* T1 - T5 Cards with Explicit Winner Highlighting */}
          <div className="space-y-2 text-[11px]">
            {/* T1 System Rules */}
            <div className={`p-2.5 rounded border transition-all ${
              winnerKey === 't1' 
                ? 'bg-cyan-950/20 border-cyan-500/70 shadow-[0_0_12px_rgba(6,182,212,0.15)] ring-1 ring-cyan-500/30' 
                : 'bg-zinc-950/60 border-zinc-800/60 opacity-60'
            }`}>
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <span className="text-cyan-400 font-bold text-[10px]">T1 SYSTEM RULES</span>
                  {winnerKey === 't1' && (
                    <span className="bg-cyan-900/60 text-cyan-300 text-[8px] font-bold px-1.5 py-0.2 rounded border border-cyan-700 uppercase">
                      Active Winner
                    </span>
                  )}
                </div>
                <span className="text-[10px] text-zinc-400 font-bold">{matrix.t1?.weight || 100}%</span>
              </div>
              <div className="text-zinc-200 mt-1">{matrix.t1?.category || 'None'} → {matrix.t1?.subcategory || 'None'}</div>
            </div>

            {/* T2 Transfer Tunnels */}
            <div className={`p-2.5 rounded border transition-all ${
              winnerKey === 't2' 
                ? 'bg-purple-950/20 border-purple-500/70 shadow-[0_0_12px_rgba(168,85,247,0.15)] ring-1 ring-purple-500/30' 
                : 'bg-zinc-950/60 border-zinc-800/60 opacity-60'
            }`}>
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <span className="text-purple-400 font-bold text-[10px]">T2 TRANSFER TUNNELS</span>
                  {winnerKey === 't2' && (
                    <span className="bg-purple-900/60 text-purple-300 text-[8px] font-bold px-1.5 py-0.2 rounded border border-purple-700 uppercase">
                      Active Winner
                    </span>
                  )}
                </div>
                <span className="text-[10px] text-zinc-400 font-bold">{matrix.t2?.weight || 0}%</span>
              </div>
              <div className="text-zinc-200 mt-1">{matrix.t2?.category || 'None'} → {matrix.t2?.subcategory || 'None'}</div>
            </div>

            {/* T3 Ledger Mappings */}
            <div className="p-2.5 rounded bg-zinc-950/40 border border-zinc-800/60 opacity-60">
              <div className="flex justify-between items-center">
                <span className="text-blue-400 font-bold text-[10px]">T3 LEDGER MAPPINGS</span>
                <span className="text-[10px] text-zinc-400 font-bold">{matrix.t3?.weight || 0}%</span>
              </div>
              <div className="text-zinc-200 mt-1">{matrix.t3?.category || 'None'} → {matrix.t3?.subcategory || 'None'}</div>
            </div>

            {/* T4 Master Rulebook */}
            <div className={`p-2.5 rounded border transition-all ${
              winnerKey === 't4' 
                ? 'bg-amber-950/30 border-amber-500/80 shadow-[0_0_12px_rgba(245,158,11,0.2)] ring-1 ring-amber-500/40' 
                : 'bg-zinc-950/60 border-zinc-800/60 opacity-60'
            }`}>
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <span className={`text-[10px] font-bold ${winnerKey === 't4' ? 'text-amber-300' : 'text-zinc-400'}`}>
                    T4 MASTER RULEBOOK
                  </span>
                  {winnerKey === 't4' && (
                    <span className="bg-amber-900/80 text-amber-200 text-[8px] font-bold px-1.5 py-0.2 rounded border border-amber-600 uppercase">
                      Active Winner
                    </span>
                  )}
                </div>
                <span className={`text-[10px] font-bold ${t4Hit ? 'text-amber-400' : 'text-zinc-500'}`}>
                  {t4Hit ? 'MATCHED' : 'UNMATCHED'}
                </span>
              </div>
              <div className="text-zinc-200 mt-1">{matrix.t4?.category || 'None'} → {matrix.t4?.subcategory || 'None'}</div>
            </div>

            {/* T5 Local AI Memory */}
            <div className={`p-2.5 rounded border transition-all ${
              winnerKey === 't5' 
                ? 'bg-emerald-950/30 border-emerald-500/80 shadow-[0_0_12px_rgba(16,185,129,0.2)] ring-1 ring-emerald-500/40' 
                : 'bg-zinc-950/60 border-zinc-800/60 opacity-60'
            }`}>
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <span className={`text-[10px] font-bold ${winnerKey === 't5' ? 'text-emerald-300' : 'text-zinc-400'}`}>
                    T5 LOCAL AI MEMORY
                  </span>
                  {winnerKey === 't5' && (
                    <span className="bg-emerald-900/80 text-emerald-200 text-[8px] font-bold px-1.5 py-0.2 rounded border border-emerald-600 uppercase">
                      Active Winner
                    </span>
                  )}
                </div>
                <span className={`text-[10px] font-bold ${t5Hit ? 'text-emerald-400' : 'text-zinc-500'}`}>
                  {t5Hit ? (matrix.t5?.source || 'AI_HIT') : 'IDLE'}
                </span>
              </div>
              <div className="text-zinc-200 mt-1">{matrix.t5?.category || 'None'} → {matrix.t5?.subcategory || 'None'}</div>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="px-5 py-2.5 border-t border-zinc-800 flex justify-end shrink-0 bg-zinc-900/90 rounded-b-xl">
          <button 
            onClick={() => setIsOpen(false)}
            className="px-3.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded font-mono text-xs cursor-pointer transition-colors"
          >
            Close Diagnostic
          </button>
        </div>
      </div>
    </div>
  ) : null;

  return (
    <div className="font-mono text-xs whitespace-nowrap">
      <button
        onClick={() => setIsOpen(true)}
        className={`px-2 py-0.5 rounded border inline-flex items-center gap-1.5 transition-all cursor-pointer ${badgeColor}`}
        title="Click to view T1-T5 diagnostic"
      >
        <span className="font-bold uppercase text-[9px] tracking-wide">{winnerTag}</span>
        <span className="opacity-40">›</span>
        <span className="truncate max-w-[120px] text-[10px] font-medium">{winnerCategory}</span>
      </button>

      {modalContent && typeof document !== 'undefined' && createPortal(modalContent, document.body)}
    </div>
  );
};