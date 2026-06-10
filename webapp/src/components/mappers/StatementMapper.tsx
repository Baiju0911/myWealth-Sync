import { useState, useEffect, useRef } from 'react';
import type { DragEvent, MouseEvent, ChangeEvent } from 'react';
import { accountApi } from '../../api.ts';
import api from '../../api/client'; 
import type { AccountEntity } from '../../types/ledger'; 

interface SpatialToken {
  text: string;
  x_pct: number;
}

interface TemplateMetadata {
  id: number;
  template_name: string;
  is_universal: boolean;
  matching_keyword: string;
  bounds: { [key: string]: number };
}

export default function StatementMapper() {
  const [accounts, setAccounts] = useState<AccountEntity[]>([]); 
  const [file, setFile] = useState<File | null>(null);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [, setIsDragging] = useState<boolean>(false); 
  const [spatialMatrix, setSpatialMatrix] = useState<SpatialToken[][]>([]); 
  const [loading, setLoading] = useState<boolean>(false);

  // 🟢 EDIT MODE POOL STATES
  const [availableTemplates, setAvailableTemplates] = useState<TemplateMetadata[]>([]);
  const [selectedEditId, setSelectedEditId] = useState<string>('NEW');

  // 📐 8 Explicit Sequential Slider Boundaries slicing our 9-Column Universe
  const [dateBounds, setDateBounds] = useState<number>(10);
  const [valueDateBounds, setValueDateBounds] = useState<number>(18);
  const [particularsBounds, setParticularsBounds] = useState<number>(45);
  const [typeBounds, setTypeBounds] = useState<number>(52);
  const [chequeBounds, setChequeBounds] = useState<number>(60);
  const [withdrawalsBounds, setWithdrawalsBounds] = useState<number>(72);
  const [depositsBounds, setDepositsBounds] = useState<number>(84);
  const [balanceBounds, setBalanceBounds] = useState<number>(94); 
  
  const [templateName, setTemplateName] = useState<string>('');
  const [matchingKeyword, setMatchingKeyword] = useState<string>('');

  // 🟢 NEW: State array storing hot-rendered computed rows instantly on boundary changes
  const [computedTransactions, setComputedTransactions] = useState<any[]>([]);

  // 🎯 Mouse Laser Pointer Tracking State
  const [hoverX, setHoverX] = useState<number | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);

  // Initial lookup mounts
  useEffect(() => {
    accountApi.getAccounts()
      .then((res: any) => {
        const extractedAccounts = Array.isArray(res) ? res : res.results || [];
        setAccounts(extractedAccounts);
      })
      .catch((err) => console.error("Failed loading ledger workspace nodes:", err));

    fetchAvailableBlueprints();
  }, []);

  const fetchAvailableBlueprints = () => {
    api.get('/statements/available/')
      .then((res) => setAvailableTemplates(res.data || []))
      .catch((err) => console.error("Failed loading registered templates:", err));
  };

  // 🟢 FIXED HOT-RELOAD TRACKER:
  // Watches slider boundary parameters. The split algorithm fires instantly on change!
  useEffect(() => {
    if (spatialMatrix.length === 0) {
      setComputedTransactions([]);
      return;
    }

    const compiledRows = spatialMatrix.map((row) => {
      const cols: { [key: string]: string[] } = {
        date: [], v_date: [], part: [], type: [], chq: [], wth: [], dep: [], bal: [], ind: []
      };

      row.forEach(token => {
        if (dateBounds > 0 && token.x_pct <= dateBounds) cols.date.push(token.text);
        else if (valueDateBounds > 0 && token.x_pct <= valueDateBounds) cols.v_date.push(token.text);
        else if (particularsBounds > 0 && token.x_pct <= particularsBounds) cols.part.push(token.text);
        else if (typeBounds > 0 && token.x_pct <= typeBounds) cols.type.push(token.text);
        else if (chequeBounds > 0 && token.x_pct <= chequeBounds) cols.chq.push(token.text);
        else if (withdrawalsBounds > 0 && token.x_pct <= withdrawalsBounds) cols.wth.push(token.text);
        else if (depositsBounds > 0 && token.x_pct <= depositsBounds) cols.dep.push(token.text);
        else if (balanceBounds > 0 && token.x_pct <= balanceBounds) cols.bal.push(token.text);
        else cols.ind.push(token.text);
      });

      const fDate = cols.date.join(" ").trim();
      const fVDate = cols.v_date.join(" ").trim();
      const fPart = cols.part.join(" ").trim();

      if (!fDate && !fPart) return null;

      return {
        date: fDate,
        vDate: fVDate,
        particulars: fPart,
        type: cols.type.join(" ").trim(),
        chqRef: cols.chq.join(" ").trim(),
        debit: cols.wth.join(" ").trim(),
        credit: cols.dep.join(" ").trim(),
        balance: cols.bal.join(" ").trim(),
        indicator: cols.ind.join(" ").trim()
      };
    }).filter(Boolean);

    setComputedTransactions(compiledRows);
  }, [spatialMatrix, dateBounds, valueDateBounds, particularsBounds, typeBounds, chequeBounds, withdrawalsBounds, depositsBounds, balanceBounds]);

  // Handle Edit dropdown selections
  const handleEditSelectionChange = (e: ChangeEvent<HTMLSelectElement>) => {
    const targetId = e.target.value;
    setSelectedEditId(targetId);

    if (targetId === 'NEW') {
      setTemplateName('');
      setMatchingKeyword('');
      setDateBounds(10); setValueDateBounds(18); setParticularsBounds(45);
      setTypeBounds(52); setChequeBounds(60); setWithdrawalsBounds(72);
      setDepositsBounds(84); setBalanceBounds(94);
    } else {
      const matchTmpl = availableTemplates.find(t => t.id.toString() === targetId);
      if (matchTmpl) {
        setTemplateName(matchTmpl.template_name);
        setMatchingKeyword(matchTmpl.matching_keyword);
        setDateBounds(matchTmpl.bounds.date_max);
        setValueDateBounds(matchTmpl.bounds.value_date_max);
        setParticularsBounds(matchTmpl.bounds.particulars_max);
        setTypeBounds(matchTmpl.bounds.trantype_max);
        setChequeBounds(matchTmpl.bounds.cheque_max);
        setWithdrawalsBounds(matchTmpl.bounds.withdrawals_max);
        setDepositsBounds(matchTmpl.bounds.deposits_max);
        setBalanceBounds(matchTmpl.bounds.balance_max);
      }
    }
  };

  const handleMouseMove = (e: MouseEvent<HTMLDivElement>) => {
    if (!canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const xPositionPixels = e.clientX - rect.left;
    const calculatedPercentage = (xPositionPixels / rect.width) * 100;
    setHoverX(Math.max(0, Math.min(100, calculatedPercentage)));
  };

  const handleMouseLeaveCanvas = () => setHoverX(null);
  const handleDragOver = (e: DragEvent<HTMLDivElement>) => { e.preventDefault(); if (!loading) setIsDragging(true); };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile && selectedAccountId) {
      setFile(droppedFile);
      triggerExtractionPipeline(droppedFile, selectedAccountId);
    }
  };

  const triggerExtractionPipeline = async (targetFile: File, accountId: string) => {
    setLoading(true);
    const formData = new FormData();
    formData.append('file', targetFile);
    formData.append('account_id', accountId);

    try {
      const response = await api.post('/statements/preview/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      if (response.data && response.data.raw_matrix) {
        setSpatialMatrix(response.data.raw_matrix);
      }
    } catch (err: any) {
      alert(err.response?.data?.error || "Failed to cross-reference statement parameters.");
    } finally {      
      setLoading(false);
    }
  };

  const saveTemplateAndProcess = async () => {
    if (!templateName.trim()) { alert("Please provide a Format Reference Code Identifier."); return; }
    if (!matchingKeyword.trim()) { alert("Please specify a Unique Document Text Signature Keyword."); return; }
    
    try {
      await api.post('/statements/save-template/', { 
        templateName,
        accountId: selectedAccountId,
        matchingKeyword, 
        boundsConfig: {
          date_max: dateBounds,
          value_date_max: valueDateBounds,
          particulars_max: particularsBounds,
          trantype_max: typeBounds,
          cheque_max: chequeBounds,
          withdrawals_max: withdrawalsBounds,
          deposits_max: depositsBounds,
          balance_max: balanceBounds,
          indicator_max: 100 
        }
      });
      alert(`Universal layout blueprint framework structure loaded successfully!`);
      fetchAvailableBlueprints(); 
    } catch (err) {
      console.error("Error committing mapping boundaries:", err);
    }
  };

  const renderCell = (value: string, isRightAligned = false, customColor = "") => {
    if (!value) return <span className="text-zinc-800 opacity-20 select-none block text-center font-bold">-</span>;
    return (
      <div 
        className={`w-full truncate font-mono text-[11px] tracking-tight whitespace-nowrap ${customColor}`} 
        style={{ textAlign: isRightAligned ? 'right' : 'left' }}
        title={value}
      >
        {value}
      </div>
    );
  };

  return (
    <div className="w-full space-y-4 animate-fade-in text-zinc-100 px-0 text-left">
      
      {/* Header */}
      <div className="w-full flex justify-between items-center border-b border-zinc-800 pb-2">
        <div>
          <h2 className="text-lg font-bold tracking-tight text-white">Universal Visual Coordinate Bounding Box Mapper</h2>
          <p className="text-[11px] text-zinc-400 mt-0.5">Map up to 9 consecutive columns by their exact spatial position layout. Set unused fields to 0%.</p>
        </div>
      </div>

      {/* 🧱 STRUCTURAL LAYOUT TABLE */}
      <table className="w-full border-none border-collapse p-0 m-0 layout-fixed" style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
        <tbody>
          <tr>
            {/* Left Cell: Controls & Sliders (33% width) */}
            <td style={{ width: '33%', verticalAlign: 'top', padding: '0 16px 0 0' }}>
              <div className="p-4 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl space-y-3.5 h-full">
                
                {/* 🛠️ Template Workspace Mode Selector dropdown card element */}
                <div className="bg-zinc-950/50 p-3 rounded-lg border border-zinc-800 space-y-1.5">
                  <label className="block text-[11px] font-bold text-emerald-400 uppercase tracking-wider">🛠️ Workspace Mode</label>
                  <select
                    value={selectedEditId}
                    onChange={handleEditSelectionChange}
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-xs text-white font-medium focus:outline-none focus:border-emerald-500 transition-all"
                  >
                    <option value="NEW" className="font-bold text-emerald-400">✨ CREATE NEW BLUEPRINT</option>
                    <optgroup label="Modify Registered Blueprints">
                      {availableTemplates.map((tmpl) => (
                        <option key={tmpl.id} value={tmpl.id.toString()} className="text-zinc-200">
                          ⚙️ {tmpl.template_name}
                        </option>
                      ))}
                    </optgroup>
                  </select>
                </div>

                <div className="space-y-3">
                  <div>
                    <label className="block text-[11px] font-medium text-zinc-400 mb-1">Target Bank Account</label>
                    <select
                      value={selectedAccountId}
                      onChange={(e) => setSelectedAccountId(e.target.value)}
                      className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-xs text-zinc-200 focus:outline-none"
                    >
                      <option value="">-- Select Account Channel --</option>
                      {accounts.map((acc) => (
                        <option key={acc.id} value={acc.id}>{acc.name} {acc.account_number ? `(•••• ${acc.account_number})` : ''}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium text-zinc-400 mb-1">Statement Document</label>
                    <div
                      onDragOver={handleDragOver} onDrop={handleDrop}
                      onClick={() => document.getElementById('fileInput')?.click()}
                      className="border border-dashed border-zinc-800 rounded-xl p-3 text-center cursor-pointer bg-zinc-950/40 hover:border-zinc-700 text-[11px] text-zinc-400"
                    >
                      <input type="file" id="fileInput" className="hidden" accept=".pdf,.csv" onChange={(e) => e.target.files?.[0] && triggerExtractionPipeline(e.target.files[0], selectedAccountId)} />
                      {file ? <span className="text-emerald-400 font-mono break-all">📄 {file.name}</span> : 'Click or drop file here'}
                    </div>
                  </div>
                </div>

                {spatialMatrix.length > 0 && (
                  <div className="border-t border-zinc-800 pt-3 space-y-2">
                    <h3 className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider">📐 Universal Cutoff Margins</h3>
                    
                    <div>
                      <label className="block text-[10px] text-zinc-500 mb-0.5">Blueprint Registry Code Name</label>
                      <input type="text" value={templateName} onChange={(e) => setTemplateName(e.target.value)} placeholder="e.g., SIB_FORMAT_PROD" className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-xs text-white focus:outline-none" />
                    </div>

                    <div>
                      <label className="block text-[10px] text-zinc-500 mb-0.5">Unique Text Signature Keyword (Fingerprint)</label>
                      <input type="text" value={matchingKeyword} onChange={(e) => setMatchingKeyword(e.target.value)} placeholder="e.g., SOUTH INDIAN BANK" className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-xs text-emerald-400 font-mono focus:outline-none" />
                    </div>

                    <div className="space-y-0.5">
                      <div className="flex justify-between text-[11px] font-mono text-blue-400"><span>1. Date Bound</span><span className="font-bold">{dateBounds}%</span></div>
                      <input type="range" min="0" max="25" value={dateBounds} onChange={(e) => setDateBounds(Number(e.target.value))} className="w-full accent-blue-500 h-1" />
                    </div>

                    <div className="space-y-0.5">
                      <div className="flex justify-between text-[11px] font-mono text-orange-400"><span>2. Value Date Bound</span><span className="font-bold">{valueDateBounds}%</span></div>
                      <input type="range" min="0" max="30" value={valueDateBounds} onChange={(e) => setValueDateBounds(Number(e.target.value))} className="w-full accent-orange-500 h-1" />
                    </div>

                    <div className="space-y-0.5">
                      <div className="flex justify-between text-[11px] font-mono text-purple-400"><span>3. Particulars Bound</span><span className="font-bold">{particularsBounds}%</span></div>
                      <input type="range" min="0" max="65" value={particularsBounds} onChange={(e) => setParticularsBounds(Number(e.target.value))} className="w-full accent-purple-500 h-1" />
                    </div>

                    <div className="space-y-0.5">
                      <div className="flex justify-between text-[11px] font-mono text-indigo-400"><span>4. Txn Type Bound</span><span className="font-bold">{typeBounds}%</span></div>
                      <input type="range" min="0" max="70" value={typeBounds} onChange={(e) => setTypeBounds(Number(e.target.value))} className="w-full accent-indigo-500 h-1" />
                    </div>

                    <div className="space-y-0.5">
                      <div className="flex justify-between text-[11px] font-mono text-sky-400"><span>5. Cheque Details Bound</span><span className="font-bold">{chequeBounds}%</span></div>
                      <input type="range" min="0" max="75" value={chequeBounds} onChange={(e) => setChequeBounds(Number(e.target.value))} className="w-full accent-sky-500 h-1" />
                    </div>

                    <div className="space-y-0.5">
                      <div className="flex justify-between text-[11px] font-mono text-red-400"><span>6. Withdrawals (Dr) Bound</span><span className="font-bold">{withdrawalsBounds}%</span></div>
                      <input type="range" min="0" max="86" value={withdrawalsBounds} onChange={(e) => setWithdrawalsBounds(Number(e.target.value))} className="w-full accent-red-500 h-1" />
                    </div>

                    <div className="space-y-0.5">
                      <div className="flex justify-between text-[11px] font-mono text-emerald-400"><span>7. Deposits (Cr) Bound</span><span className="font-bold">{depositsBounds}%</span></div>
                      <input type="range" min="0" max="93" value={depositsBounds} onChange={(e) => setDepositsBounds(Number(e.target.value))} className="w-full accent-emerald-500 h-1" />
                    </div>

                    <div className="space-y-0.5">
                      <div className="flex justify-between text-[11px] font-mono text-cyan-400"><span>8. Balance Bound</span><span className="font-bold">{balanceBounds}%</span></div>
                      <input type="range" min="0" max="99" value={balanceBounds} onChange={(e) => setBalanceBounds(Number(e.target.value))} className="w-full accent-cyan-500 h-1" />
                    </div>

                    <button type="button" onClick={saveTemplateAndProcess} className="w-full bg-emerald-600 hover:bg-emerald-500 py-2 rounded-lg text-xs font-bold tracking-wide text-white transition-all mt-2 shadow-md cursor-pointer">
                      {selectedEditId === 'NEW' ? 'Save New Blueprint' : 'Update Existing Blueprint'}
                    </button>
                  </div>
                )}
              </div>
            </td>

            {/* Right Cell: Coordinate Overlay Deck (67% width) */}
            <td style={{ width: '67%', verticalAlign: 'top', padding: '0' }}>
              <div className="p-4 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl h-full flex flex-col justify-between">
                <div className="w-full">
                  <div className="mb-2">
                    <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-wider">1. Rigid Coordinate Layout Overlay Deck</h3>
                    <p className="text-[10px] text-zinc-500 mt-0.5">Absolute token positions mapped out in real-time horizontal bounds.</p>
                  </div>
                  
                  {loading ? (
                    <div className="h-48 flex flex-col items-center justify-center space-y-2">
                      <div className="w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
                      <p className="text-[11px] text-zinc-500 font-mono">Processing coordinates...</p>
                    </div>
                  ) : spatialMatrix.length > 0 ? (
                    <div className="w-full overflow-x-auto rounded-xl border border-zinc-800 bg-zinc-950 p-2">
                      <div 
                        ref={canvasRef} onMouseMove={handleMouseMove} onMouseLeave={handleMouseLeaveCanvas}
                        className="relative p-4 py-6 min-h-[350px] font-mono text-[11px] select-none cursor-crosshair"
                        style={{ width: '1300px', minWidth: '1300px' }}
                      >
                        {/* Vertical slicing tracking lines on Canvas */}
                        {dateBounds > 0 && <div className="absolute top-0 bottom-0 border-r border-blue-500/70 z-20 pointer-events-none" style={{ left: `${dateBounds}%` }} />}
                        {valueDateBounds > 0 && <div className="absolute top-0 bottom-0 border-r border-orange-500/70 z-20 pointer-events-none" style={{ left: `${valueDateBounds}%` }} />}
                        {particularsBounds > 0 && <div className="absolute top-0 bottom-0 border-r border-purple-500/70 z-20 pointer-events-none" style={{ left: `${particularsBounds}%` }} />}
                        {typeBounds > 0 && <div className="absolute top-0 bottom-0 border-r border-indigo-500/70 z-20 pointer-events-none" style={{ left: `${typeBounds}%` }} />}
                        {chequeBounds > 0 && <div className="absolute top-0 bottom-0 border-r border-sky-500/70 z-20 pointer-events-none" style={{ left: `${chequeBounds}%` }} />}
                        {withdrawalsBounds > 0 && <div className="absolute top-0 bottom-0 border-r border-red-500/70 z-20 pointer-events-none" style={{ left: `${withdrawalsBounds}%` }} />}
                        {depositsBounds > 0 && <div className="absolute top-0 bottom-0 border-r border-emerald-500/70 z-20 pointer-events-none" style={{ left: `${depositsBounds}%` }} />}
                        {balanceBounds > 0 && <div className="absolute top-0 bottom-0 border-r border-cyan-500/70 z-20 pointer-events-none" style={{ left: `${balanceBounds}%` }} />}

                        {hoverX !== null && (
                          <div className="absolute top-0 bottom-0 border-r border-emerald-400 z-30 pointer-events-none" style={{ left: `${hoverX}%` }}>
                            <span className="absolute top-1 left-1 bg-emerald-500 text-black font-sans text-[8px] font-bold px-1 rounded shadow">{hoverX.toFixed(1)}%</span>
                          </div>
                        )}

                        <div className="space-y-4 relative z-10">
                          {spatialMatrix.map((row, rowIndex) => (
                            <div key={rowIndex} className="relative h-4 w-full hover:bg-zinc-900/40 rounded border border-transparent transition-all">
                              <span className="absolute left-0 -ml-4 text-[8px] text-zinc-700 font-bold select-none">R{rowIndex}</span>
                              {row.map((token, tokenIndex) => {
                                let color = "text-zinc-500 bg-zinc-900/10 border-zinc-800";
                                
                                if (dateBounds > 0 && token.x_pct <= dateBounds) color = "text-blue-300 bg-blue-950/10 border-blue-900/30 font-semibold";
                                else if (valueDateBounds > 0 && token.x_pct <= valueDateBounds) color = "text-orange-300 bg-orange-950/10 border-orange-900/20";
                                else if (particularsBounds > 0 && token.x_pct <= particularsBounds) color = "text-purple-300 bg-purple-950/10 border-purple-900/20";
                                else if (typeBounds > 0 && token.x_pct <= typeBounds) color = "text-indigo-300 bg-indigo-950/10 border-indigo-900/30 font-bold";
                                else if (chequeBounds > 0 && token.x_pct <= chequeBounds) color = "text-sky-300 bg-sky-950/10 border-sky-900/30 font-bold";
                                else if (withdrawalsBounds > 0 && token.x_pct <= withdrawalsBounds) color = "text-red-300 bg-red-950/10 border-red-900/30 font-bold";
                                else if (depositsBounds > 0 && token.x_pct <= depositsBounds) color = "text-emerald-300 bg-emerald-950/10 border-emerald-900/30 font-bold";
                                else if (balanceBounds > 0 && token.x_pct <= balanceBounds) color = "text-cyan-300 bg-cyan-950/10 border-cyan-900/30 font-bold";
                                else color = "text-zinc-400 bg-zinc-900/40 border-zinc-700 font-medium";

                                return (
                                  <span key={tokenIndex} className={`absolute px-0.5 rounded text-[10px] tracking-tight whitespace-nowrap transition-all ${color}`} style={{ left: `${token.x_pct}%` }}>
                                    {token.text}
                                  </span>
                                );
                              })}
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="h-48 flex flex-col items-center justify-center border border-dashed border-zinc-800 text-zinc-500 text-xs rounded-xl">
                      Stage target bank account channel and upload raw statement file to begin tracking.
                    </div>
                  )}
                </div>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      {/* 🟢 RE-ENGINEERED VIEWPORT: Reads directly from computedTransactions with zero reload overhead */}
      {computedTransactions.length > 0 && !loading && (
        <div className="p-4 bg-zinc-900 border border-zinc-800 rounded-xl shadow-xl space-y-3 w-full">
          <div>
            <h3 className="text-xs font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
              <span>✨ 2. Universal Matrix Simulation Grid Viewport</span>
            </h3>
            <p className="text-[10px] text-zinc-500 mt-0.5">Horizontal container active. Scroll sideways if your display aspect bounds clip the rightmost columns.</p>
          </div>

          <div className="overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-950 w-full custom-scrollbar">
            <table className="text-left text-xs font-mono table-fixed border-collapse" style={{ width: "1200px", minWidth: "1200px" }}>
              <thead>
                <tr className="border-b border-zinc-800 text-zinc-500 bg-zinc-900/40 text-[10px] uppercase font-bold tracking-wider">
                  <th className="p-2 border-r border-zinc-800/60 text-blue-400" style={{ width: "105px" }}>Date</th>
                  <th className="p-2 border-r border-zinc-800/60 text-orange-400" style={{ width: "105px" }}>Val Date</th>
                  <th className="p-2 border-r border-zinc-800/60 text-purple-400" style={{ width: "420px" }}>Particulars Narration</th>
                  <th className="p-2 border-r border-zinc-800/60 text-indigo-400 text-center" style={{ width: "80px" }}>Type</th>
                  <th className="p-2 border-r border-zinc-800/60 text-sky-400" style={{ width: "130px" }}>Chq/Ref</th>
                  <th className="p-2 border-r border-zinc-800/60 text-right text-red-400" style={{ width: "115px" }}>Withdrawals (-)</th>
                  <th className="p-2 border-r border-zinc-800/60 text-right text-emerald-400" style={{ width: "115px" }}>Deposits (+)</th>
                  <th className="p-2 border-r border-zinc-800/60 text-right text-cyan-400" style={{ width: "115px" }}>Balance</th>
                  <th className="p-2 text-zinc-400 text-center" style={{ width: "45px" }}>Ind</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800 text-zinc-300">
                {computedTransactions.map((tx, rowIndex) => (
                  <tr key={rowIndex} className="hover:bg-zinc-900/40 transition-colors border-b border-zinc-800/50">
                    <td className="p-2 border-r border-blue-500/20 text-blue-300 bg-blue-950/5">{renderCell(tx.date)}</td>
                    <td className="p-2 border-r border-orange-500/20 text-orange-300 bg-orange-950/5">{renderCell(tx.vDate)}</td>
                    <td className="p-2 border-r border-purple-500/20 text-zinc-100 truncate">{renderCell(tx.particulars, false, "text-zinc-200")}</td>
                    <td className="p-2 border-r border-indigo-500/20 text-center bg-indigo-950/5" style={{ textAlign: 'center' }}>
                      {tx.type ? <span className="inline-block px-1 py-0.5 text-[8px] bg-indigo-900/40 border border-indigo-700/40 text-indigo-300 rounded font-bold uppercase">{tx.type}</span> : renderCell("")}
                    </td>
                    <td className="p-2 border-r border-sky-500/20 text-sky-300 font-mono">{renderCell(tx.chqRef)}</td>
                    <td className="p-2 border-r border-red-500/20 bg-red-950/5" style={{ textAlign: 'right' }}>{renderCell(tx.debit, true, "text-red-400 font-bold")}</td>
                    <td className="p-2 border-r border-emerald-500/20 bg-emerald-950/5" style={{ textAlign: 'right' }}>{renderCell(tx.credit, true, "text-emerald-400 font-bold")}</td>
                    <td className="p-2 border-r border-cyan-500/20 bg-cyan-950/5" style={{ textAlign: 'right' }}>{renderCell(tx.balance, true, "text-cyan-300 font-bold")}</td>
                    <td className="p-1 text-center font-bold text-zinc-400" style={{ textAlign: 'center' }}>{tx.indicator || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}