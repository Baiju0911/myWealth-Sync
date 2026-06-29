import type { ColumnConfig } from './columns';

interface TableEngineProps {
  columns: ColumnConfig[];
  data: any[];
  isDuplicateRow?: (row: any) => boolean;
}

export function TableEngine({ columns, data, isDuplicateRow }: TableEngineProps) {
  return (
    <div className="w-full overflow-x-auto rounded-lg border border-zinc-800/80 bg-zinc-900/40 backdrop-blur-sm">
      <table className="w-full text-left text-xs text-zinc-300 table-fixed border-collapse" style={{ minWidth: "1100px" }}>
        
        {/* 📋 SCHEMATIC HEADER */}
        <thead className="sticky top-0 bg-zinc-900 z-10 shadow-md">
          <tr className="border-b border-zinc-800 text-zinc-500 font-mono text-[10px] uppercase tracking-wider bg-zinc-900">
            {columns.map((col) => (
              <th 
                key={col.key} 
                style={{ width: col.width, textAlign: col.align }} 
                className={`py-3 px-2 font-semibold ${col.headerClass || ''}`}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>

        {/* 🧬 CONTEXT VIRTUALIZED BODY */}
        <tbody className="divide-y divide-zinc-800/40 font-sans">
          {data.map((row, rowIndex) => {
            const isDuplicate = isDuplicateRow ? isDuplicateRow(row) : (row.status === "DUPLICATE");
            const isEnriched = row.status === "ENRI";

            return (
              <tr 
                key={row.id || rowIndex} 
                className={`transition-colors border-b border-zinc-800/30 ${
                  isDuplicate 
                    ? 'bg-zinc-950/20 text-zinc-500 hover:bg-zinc-950/30 border-l-2 border-zinc-700' 
                    : isEnriched
                    ? 'bg-amber-950/10 text-zinc-200 hover:bg-amber-950/20 border-l-2 border-amber-500/80' // Distinct container highlighting
                    : 'hover:bg-zinc-950/40 text-zinc-300'
                }`}
                style={{ 
                  opacity: isDuplicate ? 0.65 : 1,
                  contentVisibility: 'auto', 
                  containIntrinsicSize: 'auto 45px'
                }}
              >
                {columns.map((col) => {
                  const rawValue = row[col.key];
                  
                  const cellColorClass = isDuplicate 
                    ? 'text-zinc-600 line-through decoration-zinc-800/60' 
                    : (col.textColor || col.fallbackColor || 'text-zinc-300');

                  return (
                    <td 
                      key={col.key}
                      style={{ textAlign: col.align }} 
                      className={`py-3 px-2 font-mono align-top text-[13px] ${cellColorClass}`}
                    >
                      {/* 🎯 CUSTOM KEY CONDITIONAL RENDERING MATRIX */}
                      {col.isCurrency ? (
                        rawValue !== null && rawValue !== undefined && rawValue !== '-' && rawValue !== '' ? (
                          `${Number(String(rawValue).replace(/,/g, '')).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
                        ) : (
                          <span className="text-zinc-800 opacity-40 font-normal">-</span>
                        )
                      ) : col.key === 'post_date' ? (
                        <span className="text-zinc-400">{rawValue}</span>
                      ) : col.key === 'value_date' ? (
                        <span className="text-orange-400/80">{rawValue || '-'}</span>
                      ) : col.key === 'narration_description' ? (
                        <div className="leading-relaxed text-[12px]">
                          <div className="flex flex-wrap items-center gap-1.5 mb-1">
                            {row.tran_type && (
                              <span className="px-1 py-0.5 bg-zinc-800 text-zinc-400 border border-zinc-700/50 font-mono text-[9px] rounded uppercase font-bold tracking-wider shadow-inner">
                                {row.tran_type}
                              </span>
                            )}
                            {/* 💎 INLINE AMBER CHIP FOR ENRICHED LABELS */}
                            {isEnriched}
                          </div>
                          <span className={isDuplicate ? 'text-zinc-600 line-through decoration-zinc-800/60' : 'text-zinc-200'}>
                            {rawValue}
                          </span>
                        </div>
                      ) : col.key === 'tran_type' ? (
                        rawValue ? (
                          <span className="px-1 py-0.5 bg-zinc-800 border border-zinc-700 text-indigo-300 text-[8px] font-bold rounded uppercase">
                            {rawValue}
                          </span>
                        ) : '-'
                      ) : col.key === 'chq_ref' ? (
                        rawValue && rawValue !== '-' ? (
                          <span className="px-1 py-0.5 bg-sky-950/40 text-sky-400 border border-sky-900/30 text-[9px] rounded font-bold tracking-wider">
                            {rawValue}
                          </span>
                        ) : '-'
                      ) : col.key === 'status' ? (
                        isDuplicate ? (
                          <span className="text-zinc-600 uppercase font-bold">STALE</span>
                        ) : isEnriched ? (
                          <span className="text-amber-400 font-bold uppercase drop-shadow-[0_0_6px_rgba(245,158,11,0.2)]">ENRI</span>
                        ) : (
                          <span className="text-emerald-400 font-bold uppercase drop-shadow-[0_0_6px_rgba(52,211,153,0.2)]">NEW</span>
                        )
                      ) : (
                        rawValue || <span className="text-zinc-800 opacity-40">-</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}