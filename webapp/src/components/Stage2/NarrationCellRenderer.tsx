import React, { useState } from 'react';

interface NarrationCellProps {
  row: any;
}

const isBoilerplateRemark = (text: string | null | undefined): boolean => {
  if (!text) return true;
  const clean = text.trim();
  // Filter out bank noise, or abnormally long concatenated strings that aren't real remarks
  if (clean.length > 30 || clean.includes('/') || clean.includes('|')) return true;
  return /^(?:NO(?:\s*REM.*)?|UPI|NA|NONE|NULL|-)$/i.test(clean);
};

function extractFromRaw(text: string) {
  if (!text) return { payee: "Direct Payment", remark: null, rail: "BANK" };
  const clean = text.replace(/^(?:Info\s*[:-]+\s*)+/i, '').trim();
  const normalized = clean.replace(/\|+/g, '/');
  const segments = normalized.split('/').map(s => s.trim()).filter(Boolean);

  let rail = "BANK";
  if (/UPI/i.test(clean)) rail = "UPI";
  else if (/IMPS|MOB/i.test(clean)) rail = "IMPS";
  else if (/NEFT/i.test(clean)) rail = "NEFT";

  if (segments.length >= 2) {
    const candidates = [];
    for (let i = 1; i < segments.length; i++) {
      const seg = segments[i];
      if (/^(?:RRN|REF|UTR)?\s*[:.-]?\s*\d{6,18}$/i.test(seg)) continue;
      if (/^[A-Z]{3,5}$/.test(seg) && candidates.length === 0) continue;
      candidates.push(seg);
    }

    const rawPayee = candidates[0] || segments[1] || clean;
    let rawRemark = candidates.length > 1 ? candidates.slice(1).join(" ") : null;

    if (isBoilerplateRemark(rawRemark)) {
      rawRemark = null;
    }

    return { payee: rawPayee, remark: rawRemark, rail };
  }

  return { payee: clean, remark: null, rail };
}

export const NarrationCellRenderer: React.FC<NarrationCellProps> = ({ row }) => {
  const [showFull, setShowFull] = useState(false);
  const parsed = row.parsed_narration || {};
  const rawNarration = row.narration_normalized || parsed.raw_statement_narration || row.narration || "";

  const fallback = extractFromRaw(rawNarration);

  const cleanPayee = row.display_payee || parsed.suggested_payee || row.payee || fallback.payee;
  let cleanRemark = row.display_remark || parsed.suggested_remark || row.remark || fallback.remark;

  if (isBoilerplateRemark(cleanRemark)) {
    cleanRemark = null;
  }

  const rail = parsed.detected_rail || fallback.rail;

  return (
    <div className="py-0.5 space-y-0.5 font-sans max-w-sm">
      {/* LINE 1: Merchant Title + Compact Remark Tag + Mini Rail Pill */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="font-semibold text-zinc-100 text-xs tracking-tight hover:text-emerald-400 transition-colors cursor-default">
          {cleanPayee}
        </span>

        {cleanRemark && (
          <span 
            title={cleanRemark}
            className="px-1.5 py-0.2 text-[8px] font-mono rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800/50 uppercase tracking-tight max-w-30 truncate"
          >
            {cleanRemark}
          </span>
        )}

        <span className="px-1 py-0.2 text-[8px] font-mono rounded bg-zinc-800/80 text-zinc-400 uppercase">
          {rail}
        </span>
      </div>

      {/* LINE 2: Tight Muted Raw Memo */}
      <div 
        onClick={() => setShowFull(!showFull)}
        title="Click to toggle full text"
        className={`text-[10px] font-mono text-zinc-500 hover:text-zinc-300 cursor-pointer transition-colors leading-tight ${
          showFull ? "break-all whitespace-normal" : "truncate"
        }`}
      >
        {rawNarration}
      </div>
    </div>
  );
};