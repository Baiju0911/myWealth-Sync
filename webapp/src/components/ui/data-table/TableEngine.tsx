// src/components/ui/data-table/TableEngine.tsx
import type { ColumnConfig } from './columns';

interface TableEngineProps {
  columns: ColumnConfig[];
  data: any[];
  isDuplicateRow?: (row: any) => boolean;
  showFooter?: boolean;
  onRowClick?: (row: any) => void;
  meta?: any;
}

export function TableEngine({
  columns,
  data,
  isDuplicateRow,
  showFooter = false,
  onRowClick,
  meta,
}: TableEngineProps) {
  return (
    <div className="w-full overflow-x-auto rounded-lg border border-zinc-800/80 bg-zinc-900/40 backdrop-blur-sm">
      <table
        className="w-full text-left text-xs text-zinc-300 table-fixed border-collapse"
        style={{ minWidth: '1100px' }}
      >
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

        {/* 🧬 DATA BODY */}
        <tbody className="divide-y divide-zinc-800/40 font-sans">
          {data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="py-8 text-center text-zinc-500 font-mono text-xs"
              >
                No records found.
              </td>
            </tr>
          ) : (
            data.map((row, rowIndex) => {
              const isDuplicate = isDuplicateRow
                ? isDuplicateRow(row)
                : row.status === 'DUPLICATE';
              const isEnriched = row.status === 'ENRI';

              return (
                <tr
                  key={row.id || rowIndex}
                  onClick={() => onRowClick && onRowClick(row)}
                  className={`transition-colors border-b border-zinc-800/30 ${
                    onRowClick ? 'cursor-pointer hover:bg-zinc-800/60' : ''
                  } ${
                    isDuplicate
                      ? 'bg-zinc-950/20 text-zinc-500 hover:bg-zinc-950/30 border-l-2 border-zinc-700'
                      : isEnriched
                      ? 'bg-amber-950/10 text-zinc-200 hover:bg-amber-950/20 border-l-2 border-amber-500/80'
                      : 'hover:bg-zinc-950/40 text-zinc-300'
                  }`}
                  style={{
                    opacity: isDuplicate ? 0.65 : 1,
                    contentVisibility: 'auto',
                    containIntrinsicSize: 'auto 45px',
                  }}
                >
                  {columns.map((col) => {
                    const rawValue = row[col.key];

                    const cellColorClass = isDuplicate
                      ? 'text-zinc-600 line-through decoration-zinc-800/60'
                      : col.textColor || col.fallbackColor || 'text-zinc-300';

                    return (
                      <td
                        key={col.key}
                        style={{ textAlign: col.align }}
                        className={`py-3 px-2 font-mono align-middle text-[13px] ${cellColorClass}`}
                      >
                        {/* 🎯 PRIORITY 1: Executed Custom Cell Renderer */}
                        {col.renderCell ? (
                          col.renderCell(row, meta)
                        ) : col.isCurrency ? (
                          rawValue !== null &&
                          rawValue !== undefined &&
                          rawValue !== '-' &&
                          rawValue !== '' ? (
                            `₹${Number(
                              String(rawValue).replace(/,/g, '')
                            ).toLocaleString('en-IN', {
                              minimumFractionDigits: 2,
                            })}`
                          ) : (
                            <span className="text-zinc-800 opacity-40 font-normal">
                              -
                            </span>
                          )
                        ) : col.key === 'post_date' ? (
                          <span className="text-zinc-400">{rawValue}</span>
                        ) : col.key === 'value_date' ? (
                          <span className="text-orange-400/80">
                            {rawValue || '-'}
                          </span>
                        ) : col.key === 'narration_description' ? (
                          <div className="leading-relaxed text-[12px]">
                            <div className="flex flex-wrap items-center gap-1.5 mb-1">
                              {row.tran_type && (
                                <span className="px-1 py-0.5 bg-zinc-800 text-zinc-400 border border-zinc-700/50 font-mono text-[9px] rounded uppercase font-bold tracking-wider shadow-inner">
                                  {row.tran_type}
                                </span>
                              )}
                            </div>
                            <span
                              className={
                                isDuplicate
                                  ? 'text-zinc-600 line-through decoration-zinc-800/60'
                                  : 'text-zinc-200'
                              }
                            >
                              {rawValue}
                            </span>
                          </div>
                        ) : col.key === 'tran_type' ? (
                          rawValue ? (
                            <span className="px-1 py-0.5 bg-zinc-800 border border-zinc-700 text-indigo-300 text-[8px] font-bold rounded uppercase">
                              {rawValue}
                            </span>
                          ) : (
                            '-'
                          )
                        ) : col.key === 'chq_ref' ? (
                          rawValue && rawValue !== '-' ? (
                            <span className="px-1 py-0.5 bg-sky-950/40 text-sky-400 border border-sky-900/30 text-[9px] rounded font-bold tracking-wider">
                              {rawValue}
                            </span>
                          ) : (
                            '-'
                          )
                        ) : col.key === 'status' ? (
                          isDuplicate ? (
                            <span className="text-zinc-600 uppercase font-bold">
                              STALE
                            </span>
                          ) : isEnriched ? (
                            <span className="text-amber-400 font-bold uppercase drop-shadow-[0_0_6px_rgba(245,158,11,0.2)]">
                              ENRI
                            </span>
                          ) : (
                            <span className="text-emerald-400 font-bold uppercase drop-shadow-[0_0_6px_rgba(52,211,153,0.2)]">
                              NEW
                            </span>
                          )
                        ) : (
                          rawValue || (
                            <span className="text-zinc-800 opacity-40">-</span>
                          )
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })
          )}
        </tbody>

        {/* 🟢 FOOTER (OPTIONAL) */}
        {showFooter && data.length > 0 && (
          <tfoot className="border-t-2 border-zinc-700 bg-zinc-950/90 font-mono text-xs font-bold text-zinc-100">
            <tr>
              {columns.map((col, index) => {
                if (index === 0) {
                  return (
                    <td
                      key={col.key}
                      style={{ width: col.width, textAlign: col.align }}
                      className="py-3.5 px-2"
                    >
                      <span className="px-2 py-0.5 bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 rounded text-[10px] font-bold uppercase tracking-wider">
                        GRAND TOTALS
                      </span>
                    </td>
                  );
                }

                if (col.renderFooter) {
                  const footerVal = col.renderFooter(data);
                  const numVal = parseFloat(
                    String(footerVal).replace(/,/g, '')
                  );

                  return (
                    <td
                      key={col.key}
                      style={{ width: col.width, textAlign: col.align }}
                      className={`py-3.5 px-2 text-[13px] font-bold tabular-nums ${
                        isNaN(numVal)
                          ? 'text-zinc-100'
                          : numVal < 0
                          ? 'text-amber-400'
                          : 'text-emerald-400'
                      }`}
                    >
                      {footerVal}
                    </td>
                  );
                }

                if (
                  col.isCurrency ||
                  col.key === 'transaction_count' ||
                  col.key === 'txn_count'
                ) {
                  const total = data.reduce((acc, row) => {
                    const val = row[col.key];
                    const num =
                      typeof val === 'number'
                        ? val
                        : parseFloat(String(val || '0').replace(/,/g, ''));
                    return acc + (isNaN(num) ? 0 : num);
                  }, 0);

                  const textColor =
                    col.textColor ||
                    (col.isCurrency ? 'text-zinc-100' : 'text-zinc-400');

                  return (
                    <td
                      key={col.key}
                      style={{ width: col.width, textAlign: col.align }}
                      className={`py-3.5 px-2 text-[13px] font-bold tabular-nums ${textColor}`}
                    >
                      {col.isCurrency
                        ? `₹${total.toLocaleString('en-IN', {
                            minimumFractionDigits: 2,
                          })}`
                        : total.toLocaleString('en-IN')}
                    </td>
                  );
                }

                return (
                  <td
                    key={col.key}
                    style={{ width: col.width }}
                    className="py-3.5 px-2"
                  ></td>
                );
              })}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}