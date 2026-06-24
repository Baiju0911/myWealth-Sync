interface VerificationDeckProps {
  responseMeta: {
    fileType: string;
    debitLineCount: number;
    creditLineCount: number;
    emptyMemoLineCount: number;
  };
  previewLines: any[];
  opening: number | null;
  totalDebit: number | null;
  totalCredit: number | null;
  statementClosing: number | null;
  calculatedClosingValue: number | null;
  isDoubleTrustOk: boolean;
  isBalanceVerified: boolean;
  isFileFullyStale: boolean;
  isRowCountVerified: boolean;
}

export function VerificationDeck({
  responseMeta,
  previewLines,
  opening,
  totalDebit,
  totalCredit,
  statementClosing,
  calculatedClosingValue,
  isDoubleTrustOk,
  isBalanceVerified,
  isFileFullyStale,
  isRowCountVerified
}: VerificationDeckProps) {
  return (
    <div className="w-full bg-zinc-950 border border-zinc-800 rounded-xl p-6 shadow-2xl space-y-6 font-mono text-zinc-300 block clear-both" style={{ width: '100%', minWidth: '100%', display: 'block' }}>
      
      {/* 📋 SECTION HEADER */}
      <div className="w-full flex flex-row items-center justify-between border-b border-zinc-800 pb-3 gap-4" style={{ display: 'flex', flexDirection: 'row', justifyContent: 'space-between' }}>
        <div className="flex items-center gap-2 min-w-0" style={{ display: 'flex', alignItems: 'center' }}>
          <span className="text-emerald-400 text-base shrink-0">⚖️</span>
          <h3 className="text-sm tracking-wider uppercase truncate" style={{ fontWeight: 900, color: '#f3f4f6' }}>
            Automated Engine Verification Summary Deck
          </h3>
        </div>
        <div className="text-[10px] uppercase tracking-widest shrink-0 bg-zinc-900 px-2 py-0.5 border border-zinc-800 rounded hidden sm:inline-block" style={{ fontWeight: 700, color: '#9ca3af' }}>
          File Mode: {responseMeta.fileType}
        </div>
      </div>

      {/* 📡 GRID LAYER 1: TELEMETRY MATRIX STRIPS */}
      <div className="w-full block" style={{ display: 'block', width: '100%' }}>
        <div className="text-[10px] uppercase tracking-wider mb-3" style={{ fontWeight: 900, color: '#f3f4f6' }}>
          Telemetry Stream Metrics
        </div>
        
        {/* 🎯 Fixed: Kept standard layout, removed broken styles */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, minmax(0, 1fr))', gap: '12px', width: '100%' }}>
          
          {/* ACTIVE DEBITS CARD */}
          <div className="bg-zinc-900/40 border border-zinc-800 rounded-lg p-3 col-span-2 sm:col-span-1" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', minWidth: '0' }}>
            <div className="text-[10px] uppercase tracking-wider truncate" style={{ fontWeight: 900, color: '#9ca3af' }}>
              <span style={{ display: 'inline-block', width: '6px', height: '6px', backgroundColor: '#f87171', borderRadius: '50%', marginRight: '6px' }}></span> Debits
            </div>
            <div className="text-lg font-bold text-red-400 mt-2 font-mono tabular-nums">
              {responseMeta.debitLineCount} <span style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#6b7280', fontSize: '10px' }}>Rows</span>
            </div>
          </div>

          {/* ACTIVE CREDITS CARD */}
          <div className="bg-zinc-900/40 border border-zinc-800 rounded-lg p-3 col-span-2 sm:col-span-1" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', minWidth: '0' }}>
            <div className="text-[10px] uppercase tracking-wider truncate" style={{ fontWeight: 900, color: '#9ca3af' }}>
              <span style={{ display: 'inline-block', width: '6px', height: '6px', backgroundColor: '#34d399', borderRadius: '50%', marginRight: '6px' }}></span> Credits
            </div>
            <div className="text-lg font-bold text-emerald-400 mt-2 font-mono tabular-nums">
              {responseMeta.creditLineCount} <span style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#6b7280', fontSize: '10px' }}>Rows</span>
            </div>
          </div>

          {/* LIVE FRESH/NEW LEDGER COUNTER */}
          <div className="bg-cyan-950/20 border border-cyan-800/30 rounded-lg p-3 col-span-2 sm:col-span-1" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', minWidth: '0' }}>
            <div className="text-[10px] uppercase tracking-wider truncate" style={{ fontWeight: 900, color: '#22d3ee' }}>
              ✨ New Records
            </div>
            <div className="text-lg font-bold text-cyan-400 mt-2 font-mono tabular-nums">
              {previewLines.filter(tx => tx.status === 'NEW').length} <span style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#0891b2', fontSize: '10px' }}>Rows</span>
            </div>
          </div>

          {/* LIVE DUPLICATE COUNTER */}
          <div className="bg-amber-950/20 border border-amber-800/30 rounded-lg p-3 col-span-2 sm:col-span-1" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', minWidth: '0' }}>
            <div className="text-[10px] uppercase tracking-wider truncate" style={{ fontWeight: 900, color: '#fbbf24' }}>
              ⏳ Stale / Dup
            </div>
            <div className="text-lg font-bold text-amber-400 mt-2 font-mono tabular-nums">
              {previewLines.filter(tx => tx.status === 'DUPLICATE' || tx.status === 'STALE').length} <span style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#d97706', fontSize: '10px' }}>Rows</span>
            </div>
          </div>

          {/* ADMINISTRATIVE NOTES CARD */}
          <div className="bg-zinc-900/40 border border-zinc-800 rounded-lg p-3 col-span-2 sm:col-span-1" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', minWidth: '0' }}>
            <div className="text-[10px] uppercase tracking-wider truncate" style={{ fontWeight: 900, color: '#9ca3af' }}>
              <span>📝</span> Admin Notes
            </div>
            <div className="text-lg font-bold text-amber-500 mt-2 font-mono tabular-nums">
              {responseMeta.emptyMemoLineCount} <span style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#6b7280', fontSize: '10px' }}>Row</span>
            </div>
          </div>

          {/* GLOBAL SUM TOTAL CARD */}
          <div className="bg-zinc-900/80 border border-zinc-700/60 rounded-lg p-3 shadow-inner col-span-4 sm:col-span-1" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', minWidth: '0' }}>
            <div className="text-[10px] uppercase tracking-wider truncate" style={{ fontWeight: 900, color: '#e4e4e7' }}>
              📦 Global Total
            </div>
            <div className="text-lg font-mono tabular-nums" style={{ fontWeight: 900, color: '#f3f4f6' }}>
              {previewLines.length} <span style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#a1a1aa', fontSize: '10px' }}>Total</span>
            </div>
          </div>

        </div>
      </div>

      {/* 💰 GRID LAYER 2: LEDGER ACCUMULATOR MATH COMPILER */}
      <div className="w-full block space-y-2.5">
        <div className="text-[10px] uppercase tracking-wider" style={{ fontWeight: 900, color: '#f3f4f6' }}>
          Financial Liquidity Ledger Blocks
        </div>
        
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))', gap: '12px', width: '100%' }}>
          
          {/* OPENING BASE */}
          <div className="bg-zinc-900/20 border border-zinc-800 rounded-lg p-3.5 min-w-0">
            <div className="text-[12px] uppercase tracking-wider truncate" style={{ fontWeight: 900, color: '#f3f4f6' }}>Opening Balance</div>
            {/* 🎯 Fixed camelCase syntax on styles below */}
            <div style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#6b7280', fontSize: '11px', letterSpacing: '0.05em', marginTop: '4px' }}>Baseline Anchor</div>
            <div className="text-sm font-bold text-zinc-200 mt-1 font-mono tabular-nums truncate">
              ₹{opening?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
          </div>

          {/* TOTAL DEBITS */}
          <div className="bg-zinc-900/20 border border-zinc-800 rounded-lg p-3.5 min-w-0">
            <div className="text-[12px] text-red-400 uppercase tracking-wider truncate" style={{ fontWeight: 900 }}>Total Debits (-)</div>
            <div style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#ef4444', opacity: 0.5, fontSize: '11px', letterSpacing: '0.05em', marginTop: '4px' }}>Cash Vol Outflow</div>
            <div className="text-sm font-bold text-red-400 mt-1 font-mono tabular-nums truncate">
              ₹{totalDebit?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
          </div>

          {/* TOTAL CREDITS */}
          <div className="bg-zinc-900/20 border border-zinc-800 rounded-lg p-3.5 min-w-0">
            <div className="text-[12px] text-emerald-400 uppercase tracking-wider truncate" style={{ fontWeight: 900 }}>Total Credits (+)</div>
            <div style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#10b981', opacity: 0.5, fontSize: '11px', letterSpacing: '0.05em', marginTop: '4px' }}>Cash Vol Inflow</div>
            <div className="text-sm font-bold text-emerald-400 mt-1 font-mono tabular-nums truncate">
              ₹{totalCredit?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
          </div>

          {/* STATEMENT CLOSING */}
          <div className="bg-zinc-900/20 border border-zinc-800 rounded-lg p-3.5 min-w-0">
            <div className="text-[12px] uppercase tracking-wider truncate" style={{ fontWeight: 900, color: '#f3f4f6' }}>Statement Closing</div>
            <div style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#6b7280', fontSize: '11px', letterSpacing: '0.05em', marginTop: '4px' }}>Document Target</div>
            <div className="text-sm font-bold text-zinc-200 mt-1 font-mono tabular-nums truncate">
              ₹{statementClosing?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
          </div>

          {/* COMPUTED RUN */}
          <div className="bg-zinc-900/20 border border-zinc-800 rounded-lg p-3.5 min-w-0">
            <div className="text-[10px] text-cyan-400 uppercase tracking-wider truncate" style={{ fontWeight: 900 }}>Computed Run</div>
            <div style={{ fontFamily: 'sans-serif', fontWeight: 500, color: '#06b6d4', opacity: 0.5, fontSize: '9px', letterSpacing: '0.05em', marginTop: '4px' }}>Calculated Result</div>
            <div className="text-sm font-bold text-cyan-400 mt-1 font-mono tabular-nums truncate">
              ₹{calculatedClosingValue?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
          </div>
        </div>
      </div>

      {/* 🚥 SAFETY SECURITY AUDIT CHECK PANEL */}
      <div className="w-full p-4 rounded-lg border flex flex-col sm:flex-row items-center justify-between gap-4 text-[10px] font-bold tracking-wider"
           style={{ 
             backgroundColor: isDoubleTrustOk ? 'rgba(16, 185, 129, 0.05)' : 'rgba(239, 68, 68, 0.05)',
             borderColor: isDoubleTrustOk ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)',
             color: isDoubleTrustOk ? '#34d399' : '#f87171',
             display: 'flex'
           }}>
        <div className="flex items-center gap-2 uppercase shrink-0" style={{ color: '#f3f4f6' }}>
          <span className="text-xs">🛡️</span> Security Pipeline Verification Status:
        </div>
        <div className="flex flex-row flex-wrap gap-2 justify-end w-full sm:w-auto" style={{ display: 'flex' }}>
          <span className="px-2.5 py-1 rounded border uppercase font-mono font-bold tracking-wide shadow-sm"
                style={{ backgroundColor: isBalanceVerified ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)', borderColor: isBalanceVerified ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)' }}>
            {isBalanceVerified ? "🟢 Balance: MATCHED" : isFileFullyStale ? "⏳ RE-PARSE" : "🔴 Balance: DRIFTED"}
          </span>
          <span className="px-2.5 py-1 rounded border uppercase font-mono font-bold tracking-wide shadow-sm"
                style={{ backgroundColor: isRowCountVerified ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)', borderColor: isRowCountVerified ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)' }}>
            {isRowCountVerified ? `🟢 Parsing: ${previewLines.length} Rows Whole` : "🔴 SIZE MISMATCH"}
          </span>
        </div>
      </div>

    </div>
  );
}