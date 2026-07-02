// webapp/src/components/ui/data-table/VerificationDeck.tsx


interface VerificationDeckProps {
  responseMeta: {
    fileType: string;
    debitLineCount: number;
    creditLineCount: number;
    emptyMemoLineCount: number;
    count: number;
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
  strategyExecuted: string;
  confidenceScore: number | null;
  frontendRenderCount: number;
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
  isRowCountVerified,
  strategyExecuted,
  confidenceScore,
  frontendRenderCount
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

      </div>

      {/* 📡 GRID LAYER 1: TELEMETRY MATRIX STRIPS */}
      <div className="w-full block" style={{ display: 'block', width: '100%' }}>
        <div className="text-[10px] uppercase tracking-wider mb-3" style={{ fontWeight: 900, color: '#f3f4f6' }}>
          Telemetry Stream Metrics
        </div>
        
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


    <br/>
      {/* 🛡️ HIGH-FIDELITY DE-CONGESTED SECURITY COMMAND HUB BLOCK */}
{responseMeta && (
  <div className="w-full bg-zinc-900/90 border border-zinc-800/80 rounded-xl shadow-2xl overflow-hidden mt-6 backdrop-blur-md flex flex-col" style={{ display: 'flex', flexDirection: 'column' }}>
    
    {/* 🎚️ FIXED INLINE HORIZONTAL HUD STRIP (FORCED ROW ROUTING) */}
    <div 
      className="w-full p-4 overflow-x-auto" 
      style={{ 
        display: 'flex', 
        flexDirection: 'row', 
        alignItems: 'center', 
        justifyContent: 'space-between', 
        gap: '24px',
        width: '100%',
        minWidth: '100%'
      }}
    >
      
      {/* HUD BLOCK 0: Core Identifier Block */}
      <div className="shrink-0 min-w-[200px]" style={{ display: 'flex', alignItems: 'center', gap: '12px', borderRight: '1px solid rgba(63, 63, 70, 0.6)', paddingRight: '24px' }}>
        <div className="h-8 w-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 select-none shrink-0">
          🔒
        </div>
        <div className="flex flex-col" style={{ display: 'flex', flexDirection: 'column' }}>
          <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold font-sans">Control Center</span>
          <span className="text-xs font-bold text-zinc-200 font-sans tracking-wide">Verification Matrix</span>
        </div>
      </div>

      {/* HUD BLOCK 1: Balance Liquidity */}
      <div className="shrink-0" style={{ display: 'flex', flexDirection: 'column', gap: '4px', minWidth: '120px' }}>
        <span className="text-[10px] text-zinc-500 font-sans font-medium uppercase tracking-wider">Liquidity Matrix</span>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <span className={`px-2 py-0.5 rounded-md text-[10px] font-bold border tracking-wide shadow-sm flex items-center gap-1.5 ${isBalanceVerified ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'}`}>
            <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse"></span>
            {isBalanceVerified ? 'BALANCE: MATCHED' : 'BALANCE: DRIFT'}
          </span>
        </div>
      </div>

      {/* HUD BLOCK 2: Data Integrity */}
      <div className="shrink-0" style={{ display: 'flex', flexDirection: 'column', gap: '4px', minWidth: '130px' }}>
        <span className="text-[10px] text-zinc-500 font-sans font-medium uppercase tracking-wider">Data Integrity</span>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <span className={`px-2 py-0.5 rounded-md text-[10px] font-bold border tracking-wide shadow-sm ${isRowCountVerified ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-amber-500/10 text-amber-400 border-amber-500/20'}`}>
            {isRowCountVerified ? `🟢 ${frontendRenderCount} ROWS INTACT` : '⚠️ SIZE VARIANCE'}
          </span>
        </div>
      </div>

      {/* HUD BLOCK 3: Engine Routing */}
      <div className="shrink-0" style={{ display: 'flex', flexDirection: 'column', gap: '4px', minWidth: '180px', maxWidth: '240px' }}>
        <span className="text-[10px] text-zinc-500 font-sans font-medium uppercase tracking-wider">Pipeline Routing</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span className="text-blue-400 font-bold tracking-wide text-xs truncate select-all" title={strategyExecuted}>
            {strategyExecuted || 'UNASSIGNED'}
          </span>
          <span className="px-1.5 py-0.5 bg-zinc-800 border border-zinc-700 text-zinc-400 rounded text-[8px] font-bold uppercase tracking-wider shrink-0 select-none">
            {strategyExecuted.includes('CSV') ? 'Flat' : 'Coord'}
          </span>
        </div>
      </div>

      {/* HUD BLOCK 4: Stream Confidence */}
      <div className="shrink-0" style={{ display: 'flex', flexDirection: 'column', gap: '4px', minWidth: '120px' }}>
        <span className="text-[10px] text-zinc-500 font-sans font-medium uppercase tracking-wider">Stream Confidence</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          
          <span className={`px-1 py-0.5 rounded text-[8px] font-bold border shrink-0 uppercase tracking-wide select-none ${strategyExecuted.includes('CSV') ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' : 'bg-amber-500/10 text-amber-400 border-amber-500/20'}`}>
            {strategyExecuted.includes('CSV') ? 'Direct' : 'OCR'}
          </span>
          <span className="text-emerald-400 font-bold text-xs">
            {strategyExecuted.includes('CSV') || confidenceScore === null || confidenceScore === 100
              ? '100.00' 
              : confidenceScore.toFixed(2)}%
          </span>
        </div>
      </div>

      {/* HUD BLOCK 5: Ingest Mode */}
      <div className="shrink-0" style={{ display: 'flex', flexDirection: 'column', gap: '4px', minWidth: '100px'}}>
        <span className="text-[10px] text-zinc-500 font-sans font-medium uppercase tracking-wider">Ingest Mode</span>
        <span className="px-1 py-0.5 rounded text-[8px] font-bold border shrink-0 uppercase tracking-wide select-none">
          {responseMeta.fileType || 'UNKNOWN'}
        </span>
      </div>

    </div>

    
              <br/>
{/* 🎚️ BOTTOM SYSTEM STATUS AUDIT TICKER (PULLED TO THE LEFT) */}
<div 
  className="w-full px-5 py-3 border-t text-[10px] font-bold tracking-wider select-none transition-all duration-300"
  style={{ 
    display: 'flex',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-start', // 🎯 FIX: Pulls everything to the left side
    gap: '24px',                   // 🎯 Spacing between the main header and the indicators group
    backgroundColor: isDoubleTrustOk ? 'rgba(16, 185, 129, 0.03)' : 'rgba(239, 68, 68, 0.03)',
    borderColor: isDoubleTrustOk ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)',
    color: isDoubleTrustOk ? '#34d399' : '#f87171'
  }}
>
  {/* Left Label Header */}
  <div className="flex items-center gap-2 uppercase text-zinc-400 shrink-0" style={{ display: 'flex', alignItems: 'center' }}>
    <span className="text-zinc-500 animate-pulse">⚡</span> SYSTEM SECURITY AUDIT PASS:
  </div>

  {/* Status Pills Group - Pulled left alongside header */}
  <div style={{ display: 'flex', flexDirection: 'row', gap: '16px', alignItems: 'center' }}>
    <span className="text-xs text-zinc-100 font-sans font-bold" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
      <span className={`h-2 w-2 rounded-full ${isBalanceVerified ? 'bg-emerald-500 animate-ping' : 'bg-red-500'}`}></span>
      Liquidity System: <span className={isBalanceVerified ? 'text-emerald-400' : 'text-red-400'}>{isBalanceVerified ? 'SECURE' : 'COMPROMISED'}</span>
    </span>
    
    <span className="text-zinc-700 font-sans font-light select-none">|</span>
    
    <span className="text-xs text-zinc-100 font-sans font-bold" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
      <span className={`h-2 w-2 rounded-full ${isRowCountVerified ? 'bg-emerald-500' : 'bg-amber-500'}`}></span>
      Payload Integrity: <span className={isRowCountVerified ? 'text-emerald-400' : 'text-amber-400'}>{isRowCountVerified ? 'INTACT' : 'VARIANCE_DETECTION'}</span>
    </span>
  </div>
</div>

  </div>
)}

    </div>
  );
}