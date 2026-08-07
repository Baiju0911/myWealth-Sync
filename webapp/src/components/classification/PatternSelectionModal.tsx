
import React, { useEffect, useState, useRef } from 'react';
import { 
  fetchCandidatePatterns, 
  validatePatternAnchor, 
  type PatternValidationResponse 
} from '../../api';

interface Props {
  isOpen: boolean;
  selectedTxnIds: string[];
  targetCategory: string;
  targetSubcategory: string;
  activeVendorName?: string;
  upiStrategy?: 'vendor' | 'auto_consolidate';
  onClose: () => void;
  onConfirm: (selectedPatterns: string[]) => void;
  isSubmitting?: boolean;
}

export const PatternSelectionModal: React.FC<Props> = ({
  isOpen,
  selectedTxnIds,
  targetCategory,
  targetSubcategory,
  activeVendorName = '',
  upiStrategy = 'vendor',
  onClose,
  onConfirm,
  isSubmitting = false,
}) => {
  const [loading, setLoading] = useState<boolean>(false);
  const [selectablePatterns, setSelectablePatterns] = useState<string[]>([]);
  const [disabledPatterns, setDisabledPatterns] = useState<string[]>([]);
  const [chosenPatterns, setChosenPatterns] = useState<string[]>([]);

  // Custom Input & Validation State
  const [customInput, setCustomInput] = useState<string>('');
  const [validating, setValidating] = useState<boolean>(false);
  const [evaluation, setEvaluation] = useState<PatternValidationResponse | null>(null);

  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!isOpen || !selectedTxnIds || selectedTxnIds.length === 0) {
      setSelectablePatterns([]);
      setDisabledPatterns([]);
      setChosenPatterns([]);
      setCustomInput('');
      setEvaluation(null);
      return;
    }

    // ⚡ Strategy 1: Auto-Consolidate as UPI Merchant (Apply Normalizer)
    if (upiStrategy === 'auto_consolidate') {
      const genericChips = ['⚡ P2M_UPI_MERCHANT_SWEEP', 'GENERIC_QR_NORMALIZER'];
      setSelectablePatterns(genericChips);
      setChosenPatterns([genericChips[0]]);
      setDisabledPatterns([]);
      setLoading(false);
      return;
    }

    // 🏷️ Strategy 2: Anchor to Clean Vendor Name Only
    let isMounted = true;
    setLoading(true);

    fetchCandidatePatterns(selectedTxnIds)
      .then((data) => {
        if (!isMounted) return;
        let clean = data.selectable_patterns || [];
        const disabled = data.disabled_patterns || [];

        // Fallback to activeVendorName if backend returns an empty array
        if (clean.length === 0 && activeVendorName.trim()) {
          clean = [activeVendorName.trim()];
        }

        setSelectablePatterns(clean);
        setDisabledPatterns(disabled);

        if (clean.length > 0) {
          setChosenPatterns([clean[0]]);
        }
      })
      .catch((err) => {
        console.error('Error fetching pattern suggestions:', err);
        if (isMounted && activeVendorName.trim()) {
          setSelectablePatterns([activeVendorName.trim()]);
          setChosenPatterns([activeVendorName.trim()]);
        }
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [isOpen, selectedTxnIds, upiStrategy, activeVendorName]);

  const handleInputChange = (value: string) => {
    setCustomInput(value);

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    const trimmed = value.trim();

    if (!trimmed || trimmed.length < 2) {
      setEvaluation(null);
      setValidating(false);
      return;
    }

    setValidating(true);
    debounceTimerRef.current = setTimeout(() => {
      validatePatternAnchor(trimmed)
        .then((res) => setEvaluation(res))
        .catch((err) => {
          console.error('Pattern validation error:', err);
          setEvaluation(null);
        })
        .finally(() => setValidating(false));
    }, 400);
  };

  if (!isOpen) return null;

  const handleTogglePattern = (pattern: string) => {
    setChosenPatterns((prev) =>
      prev.includes(pattern) ? prev.filter((p) => p !== pattern) : [...prev, pattern]
    );
  };

  const handleAddCustomPattern = () => {
    if (!evaluation || !evaluation.is_valid || !evaluation.clean_pattern) return;

    const targetPattern = evaluation.clean_pattern;

    if (!selectablePatterns.includes(targetPattern)) {
      setSelectablePatterns((prev) => [...prev, targetPattern]);
    }
    if (!chosenPatterns.includes(targetPattern)) {
      setChosenPatterns((prev) => [...prev, targetPattern]);
    }

    setCustomInput('');
    setEvaluation(null);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAddCustomPattern();
    }
  };

  const isAddDisabled = !evaluation || !evaluation.is_valid || validating;

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0,0,0,0.8)',
        zIndex: 9999999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          backgroundColor: '#18181b',
          border: '1px solid #3f3f46',
          borderRadius: '12px',
          padding: '24px',
          maxWidth: '540px',
          width: '100%',
          color: '#f4f4f5',
          boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '14px', fontWeight: 'bold', color: '#f59e0b', textTransform: 'uppercase' }}>
              Confirm Reclassification & Learned Rule
            </h3>
            <span style={{ fontSize: '11px', color: '#a1a1aa' }}>
              Reclassifying {selectedTxnIds.length} item(s) to <strong>{targetCategory} ➔ {targetSubcategory}</strong>
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: '#a1a1aa', cursor: 'pointer', fontSize: '18px' }}
          >
            ✕
          </button>
        </div>

        {/* Pattern Selection Box */}
        <div style={{ backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '16px', marginBottom: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <span style={{ fontSize: '11px', fontWeight: 'bold', color: '#38bdf8', textTransform: 'uppercase' }}>
              💡 Select Rule Anchors for Future Auto-Matching ({upiStrategy === 'auto_consolidate' ? 'Rail Mode' : 'Entity Mode'})
            </span>
          </div>

          {loading ? (
            <div style={{ fontSize: '12px', color: '#a1a1aa', padding: '12px 0', textAlign: 'center' }}>
              ⏳ Extracting clean vendor phrases from narrations...
            </div>
          ) : (
            <>
              {/* Selectable Clean Chips */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '16px' }}>
                {selectablePatterns.length === 0 ? (
                  <span style={{ fontSize: '11px', color: '#71717a' }}>
                    No specific vendor anchor detected. Type a custom keyword below or reclassify without learning.
                  </span>
                ) : (
                  selectablePatterns.map((pat) => {
                    const isChecked = chosenPatterns.includes(pat);
                    return (
                      <label
                        key={pat}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '6px',
                          padding: '6px 12px',
                          borderRadius: '20px',
                          fontSize: '11px',
                          fontWeight: '600',
                          backgroundColor: isChecked ? '#1e1b4b' : '#18181b',
                          color: isChecked ? '#818cf8' : '#a1a1aa',
                          border: `1px solid ${isChecked ? '#6366f1' : '#3f3f46'}`,
                          cursor: 'pointer',
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => handleTogglePattern(pat)}
                          style={{ accentColor: '#6366f1', width: '14px', height: '14px', cursor: 'pointer' }}
                        />
                        {pat}
                      </label>
                    );
                  })
                )}
              </div>

              {/* Manual Custom Pattern Input Section */}
              <div style={{ borderTop: '1px solid #1f1f23', paddingTop: '12px', marginBottom: '12px' }}>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <input
                    type="text"
                    value={customInput}
                    onChange={(e) => handleInputChange(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Type custom keyword anchor (e.g. INT.PD, SUMEE S)..."
                    style={{
                      flex: 1,
                      backgroundColor: '#18181b',
                      border: '1px solid #3f3f46',
                      borderRadius: '6px',
                      padding: '6px 12px',
                      fontSize: '11px',
                      color: '#f4f4f5',
                      outline: 'none',
                    }}
                  />
                  <button
                    type="button"
                    onClick={handleAddCustomPattern}
                    disabled={isAddDisabled}
                    style={{
                      padding: '6px 14px',
                      backgroundColor: !isAddDisabled ? '#6366f1' : '#27272a',
                      border: 'none',
                      borderRadius: '6px',
                      color: !isAddDisabled ? '#ffffff' : '#71717a',
                      fontSize: '11px',
                      fontWeight: 'bold',
                      cursor: !isAddDisabled ? 'pointer' : 'not-allowed',
                      opacity: !isAddDisabled ? 1 : 0.6,
                      transition: 'all 0.15s ease-in-out',
                    }}
                  >
                    + Add Tag
                  </button>
                </div>

                {/* Fixed Height Feedback Container */}
                <div style={{ minHeight: '28px', marginTop: '6px' }}>
                  {validating && (
                    <div style={{ fontSize: '10px', color: '#71717a', padding: '4px 0' }}>
                      ⏳ Checking engine rules...
                    </div>
                  )}

                  {!validating && evaluation && (
                    <div
                      style={{
                        fontSize: '11px',
                        padding: '6px 10px',
                        borderRadius: '6px',
                        fontWeight: '500',
                        backgroundColor:
                          evaluation.status === 'GOOD' ? '#064e3b' :
                          evaluation.status === 'BAD' ? '#451a03' : '#4c0519',
                        color:
                          evaluation.status === 'GOOD' ? '#6ee7b7' :
                          evaluation.status === 'BAD' ? '#fcd34d' : '#fda4af',
                        border: `1px solid ${
                          evaluation.status === 'GOOD' ? '#047857' :
                          evaluation.status === 'BAD' ? '#b45309' : '#9f1239'
                        }`,
                      }}
                    >
                      {evaluation.message}
                    </div>
                  )}
                </div>
              </div>

              {/* Auto-Blocked Noise Tokens */}
              {disabledPatterns.length > 0 && (
                <div style={{ borderTop: '1px solid #1f1f23', paddingTop: '10px' }}>
                  <span style={{ fontSize: '10px', color: '#71717a', display: 'block', marginBottom: '6px', fontWeight: 'bold', textTransform: 'uppercase' }}>
                    🛡️ Auto-Filtered System Noise (Blocked):
                  </span>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                    {disabledPatterns.map((token) => (
                      <span
                        key={`disabled-${token}`}
                        title={`Auto-filtered system noise token: '${token}'`}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          padding: '3px 8px',
                          borderRadius: '12px',
                          fontSize: '10px',
                          backgroundColor: '#18181b',
                          color: '#52525b',
                          border: '1px solid #27272a',
                          textDecoration: 'line-through',
                          cursor: 'not-allowed',
                          userSelect: 'none',
                        }}
                      >
                        🛡️ {token}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer Actions */}
        <div style={{ display: 'flex', gap: '12px' }}>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            style={{
              flex: 1,
              padding: '10px',
              backgroundColor: '#27272a',
              border: 'none',
              borderRadius: '6px',
              color: '#a1a1aa',
              fontSize: '12px',
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(chosenPatterns)}
            disabled={isSubmitting || loading}
            style={{
              flex: 1.5,
              padding: '10px',
              backgroundColor: '#f59e0b',
              border: 'none',
              borderRadius: '6px',
              color: '#09090b',
              fontSize: '12px',
              fontWeight: 'bold',
              cursor: isSubmitting || loading ? 'wait' : 'pointer',
            }}
          >
            {isSubmitting ? 'Applying Reclassification...' : 'Confirm & Apply'}
          </button>
        </div>
      </div>
    </div>
  );
};


// import React, { useEffect, useState, useRef } from 'react';
// import { 
//   fetchCandidatePatterns, 
//   validatePatternAnchor, 
//   type PatternValidationResponse 
// } from '../../api';

// interface Props {
//   isOpen: boolean;
//   selectedTxnIds: string[];
//   targetCategory: string;
//   targetSubcategory: string;
//   onClose: () => void;
//   onConfirm: (selectedPatterns: string[]) => void;
//   isSubmitting?: boolean;
// }

// export const PatternSelectionModal: React.FC<Props> = ({
//   isOpen,
//   selectedTxnIds,
//   targetCategory,
//   targetSubcategory,
//   onClose,
//   onConfirm,
//   isSubmitting = false,
// }) => {
//   const [loading, setLoading] = useState<boolean>(false);
//   const [selectablePatterns, setSelectablePatterns] = useState<string[]>([]);
//   const [disabledPatterns, setDisabledPatterns] = useState<string[]>([]);
//   const [chosenPatterns, setChosenPatterns] = useState<string[]>([]);

//   // Custom Input & Validation State
//   const [customInput, setCustomInput] = useState<string>('');
//   const [validating, setValidating] = useState<boolean>(false);
//   const [evaluation, setEvaluation] = useState<PatternValidationResponse | null>(null);

//   const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

//   useEffect(() => {
//     if (!isOpen || !selectedTxnIds || selectedTxnIds.length === 0) {
//       setSelectablePatterns([]);
//       setDisabledPatterns([]);
//       setChosenPatterns([]);
//       setCustomInput('');
//       setEvaluation(null);
//       return;
//     }

//     let isMounted = true;
//     setLoading(true);

//     fetchCandidatePatterns(selectedTxnIds)
//       .then((data) => {
//         if (!isMounted) return;
//         const clean = data.selectable_patterns || [];
//         const disabled = data.disabled_patterns || [];

//         setSelectablePatterns(clean);
//         setDisabledPatterns(disabled);

//         if (clean.length > 0) {
//           setChosenPatterns([clean[0]]);
//         }
//       })
//       .catch((err) => console.error('Error fetching pattern suggestions:', err))
//       .finally(() => {
//         if (isMounted) setLoading(false);
//       });

//     return () => {
//       isMounted = false;
//     };
//   }, [isOpen, selectedTxnIds]);

//   const handleInputChange = (value: string) => {
//     setCustomInput(value);

//     if (debounceTimerRef.current) {
//       clearTimeout(debounceTimerRef.current);
//     }

//     const trimmed = value.trim();

//     if (!trimmed || trimmed.length < 2) {
//       setEvaluation(null);
//       setValidating(false);
//       return;
//     }

//     setValidating(true);
//     debounceTimerRef.current = setTimeout(() => {
//       validatePatternAnchor(trimmed)
//         .then((res) => setEvaluation(res))
//         .catch((err) => {
//           console.error('Pattern validation error:', err);
//           setEvaluation(null);
//         })
//         .finally(() => setValidating(false));
//     }, 400);
//   };

//   if (!isOpen) return null;

//   const handleTogglePattern = (pattern: string) => {
//     setChosenPatterns((prev) =>
//       prev.includes(pattern) ? prev.filter((p) => p !== pattern) : [...prev, pattern]
//     );
//   };

//   const handleAddCustomPattern = () => {
//     if (!evaluation || !evaluation.is_valid || !evaluation.clean_pattern) return;

//     const targetPattern = evaluation.clean_pattern;

//     if (!selectablePatterns.includes(targetPattern)) {
//       setSelectablePatterns((prev) => [...prev, targetPattern]);
//     }
//     if (!chosenPatterns.includes(targetPattern)) {
//       setChosenPatterns((prev) => [...prev, targetPattern]);
//     }

//     setCustomInput('');
//     setEvaluation(null);
//   };

//   const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
//     if (e.key === 'Enter') {
//       e.preventDefault();
//       handleAddCustomPattern();
//     }
//   };

//   const isAddDisabled = !evaluation || !evaluation.is_valid || validating;

//   return (
//     <div
//       onClick={onClose}
//       style={{
//         position: 'fixed',
//         inset: 0,
//         backgroundColor: 'rgba(0,0,0,0.8)',
//         zIndex: 9999999,
//         display: 'flex',
//         alignItems: 'center',
//         justifyContent: 'center',
//         padding: '16px',
//       }}
//     >
//       <div
//         onClick={(e) => e.stopPropagation()}
//         style={{
//           backgroundColor: '#18181b',
//           border: '1px solid #3f3f46',
//           borderRadius: '12px',
//           padding: '24px',
//           maxWidth: '540px',
//           width: '100%',
//           color: '#f4f4f5',
//           boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
//         }}
//       >
//         {/* Header */}
//         <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
//           <div>
//             <h3 style={{ margin: 0, fontSize: '14px', fontWeight: 'bold', color: '#f59e0b', textTransform: 'uppercase' }}>
//               Confirm Reclassification & Learned Rule
//             </h3>
//             <span style={{ fontSize: '11px', color: '#a1a1aa' }}>
//               Reclassifying {selectedTxnIds.length} item(s) to <strong>{targetCategory} ➔ {targetSubcategory}</strong>
//             </span>
//           </div>
//           <button
//             type="button"
//             onClick={onClose}
//             style={{ background: 'none', border: 'none', color: '#a1a1aa', cursor: 'pointer', fontSize: '18px' }}
//           >
//             ✕
//           </button>
//         </div>

//         {/* Pattern Selection Box */}
//         <div style={{ backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '16px', marginBottom: '20px' }}>
//           <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
//             <span style={{ fontSize: '11px', fontWeight: 'bold', color: '#38bdf8', textTransform: 'uppercase' }}>
//               💡 Select Rule Anchors for Future Auto-Matching
//             </span>
//           </div>

//           {loading ? (
//             <div style={{ fontSize: '12px', color: '#a1a1aa', padding: '12px 0', textAlign: 'center' }}>
//               ⏳ Extracting clean vendor phrases from narrations...
//             </div>
//           ) : (
//             <>
//               {/* Selectable Clean Chips */}
//               <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '16px' }}>
//                 {selectablePatterns.length === 0 ? (
//                   <span style={{ fontSize: '11px', color: '#71717a' }}>
//                     No specific vendor anchor detected. Type a custom keyword below or reclassify without learning.
//                   </span>
//                 ) : (
//                   selectablePatterns.map((pat) => {
//                     const isChecked = chosenPatterns.includes(pat);
//                     return (
//                       <label
//                         key={pat}
//                         style={{
//                           display: 'inline-flex',
//                           alignItems: 'center',
//                           gap: '6px',
//                           padding: '6px 12px',
//                           borderRadius: '20px',
//                           fontSize: '11px',
//                           fontWeight: '600',
//                           backgroundColor: isChecked ? '#1e1b4b' : '#18181b',
//                           color: isChecked ? '#818cf8' : '#a1a1aa',
//                           border: `1px solid ${isChecked ? '#6366f1' : '#3f3f46'}`,
//                           cursor: 'pointer',
//                         }}
//                       >
//                         <input
//                           type="checkbox"
//                           checked={isChecked}
//                           onChange={() => handleTogglePattern(pat)}
//                           style={{ accentColor: '#6366f1', width: '14px', height: '14px', cursor: 'pointer' }}
//                         />
//                         {pat}
//                       </label>
//                     );
//                   })
//                 )}
//               </div>

//               {/* Manual Custom Pattern Input Section */}
//               <div style={{ borderTop: '1px solid #1f1f23', paddingTop: '12px', marginBottom: '12px' }}>
//                 <div style={{ display: 'flex', gap: '8px' }}>
//                   <input
//                     type="text"
//                     value={customInput}
//                     onChange={(e) => handleInputChange(e.target.value)}
//                     onKeyDown={handleKeyDown}
//                     placeholder="Type custom keyword anchor (e.g. INT.PD, SUMEE S)..."
//                     style={{
//                       flex: 1,
//                       backgroundColor: '#18181b',
//                       border: '1px solid #3f3f46',
//                       borderRadius: '6px',
//                       padding: '6px 12px',
//                       fontSize: '11px',
//                       color: '#f4f4f5',
//                       outline: 'none',
//                     }}
//                   />
//                   <button
//                     type="button"
//                     onClick={handleAddCustomPattern}
//                     disabled={isAddDisabled}
//                     style={{
//                       padding: '6px 14px',
//                       backgroundColor: !isAddDisabled ? '#6366f1' : '#27272a',
//                       border: 'none',
//                       borderRadius: '6px',
//                       color: !isAddDisabled ? '#ffffff' : '#71717a',
//                       fontSize: '11px',
//                       fontWeight: 'bold',
//                       cursor: !isAddDisabled ? 'pointer' : 'not-allowed',
//                       opacity: !isAddDisabled ? 1 : 0.6,
//                       transition: 'all 0.15s ease-in-out',
//                     }}
//                   >
//                     + Add Tag
//                   </button>
//                 </div>

//                 {/* Fixed Height Feedback Container to Prevent UI Jitter */}
//                 <div style={{ minHeight: '28px', marginTop: '6px' }}>
//                   {validating && (
//                     <div style={{ fontSize: '10px', color: '#71717a', padding: '4px 0' }}>
//                       ⏳ Checking engine rules...
//                     </div>
//                   )}

//                   {!validating && evaluation && (
//                     <div
//                       style={{
//                         fontSize: '11px',
//                         padding: '6px 10px',
//                         borderRadius: '6px',
//                         fontWeight: '500',
//                         backgroundColor:
//                           evaluation.status === 'GOOD' ? '#064e3b' :
//                           evaluation.status === 'BAD' ? '#451a03' : '#4c0519',
//                         color:
//                           evaluation.status === 'GOOD' ? '#6ee7b7' :
//                           evaluation.status === 'BAD' ? '#fcd34d' : '#fda4af',
//                         border: `1px solid ${
//                           evaluation.status === 'GOOD' ? '#047857' :
//                           evaluation.status === 'BAD' ? '#b45309' : '#9f1239'
//                         }`,
//                       }}
//                     >
//                       {evaluation.message}
//                     </div>
//                   )}
//                 </div>
//               </div>

//               {/* Auto-Blocked Noise Tokens */}
//               {disabledPatterns.length > 0 && (
//                 <div style={{ borderTop: '1px solid #1f1f23', paddingTop: '10px' }}>
//                   <span style={{ fontSize: '10px', color: '#71717a', display: 'block', marginBottom: '6px', fontWeight: 'bold', textTransform: 'uppercase' }}>
//                     🛡️ Auto-Filtered System Noise (Blocked):
//                   </span>
//                   <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
//                     {disabledPatterns.map((token) => (
//                       <span
//                         key={`disabled-${token}`}
//                         title={`Auto-filtered system noise token: '${token}'`}
//                         style={{
//                           display: 'inline-flex',
//                           alignItems: 'center',
//                           padding: '3px 8px',
//                           borderRadius: '12px',
//                           fontSize: '10px',
//                           backgroundColor: '#18181b',
//                           color: '#52525b',
//                           border: '1px solid #27272a',
//                           textDecoration: 'line-through',
//                           cursor: 'not-allowed',
//                           userSelect: 'none',
//                         }}
//                       >
//                         🛡️ {token}
//                       </span>
//                     ))}
//                   </div>
//                 </div>
//               )}
//             </>
//           )}
//         </div>

//         {/* Footer Actions */}
//         <div style={{ display: 'flex', gap: '12px' }}>
//           <button
//             type="button"
//             onClick={onClose}
//             disabled={isSubmitting}
//             style={{
//               flex: 1,
//               padding: '10px',
//               backgroundColor: '#27272a',
//               border: 'none',
//               borderRadius: '6px',
//               color: '#a1a1aa',
//               fontSize: '12px',
//               cursor: 'pointer',
//             }}
//           >
//             Cancel
//           </button>
//           <button
//             type="button"
//             onClick={() => onConfirm(chosenPatterns)}
//             disabled={isSubmitting || loading}
//             style={{
//               flex: 1.5,
//               padding: '10px',
//               backgroundColor: '#f59e0b',
//               border: 'none',
//               borderRadius: '6px',
//               color: '#09090b',
//               fontSize: '12px',
//               fontWeight: 'bold',
//               cursor: isSubmitting || loading ? 'wait' : 'pointer',
//             }}
//           >
//             {isSubmitting ? 'Applying Reclassification...' : 'Confirm & Apply'}
//           </button>
//         </div>
//       </div>
//     </div>
//   );
// };

// // import React, { useEffect, useState, useRef } from 'react';
// // import { fetchCandidatePatterns, validatePatternAnchor, type PatternValidationResponse } from '../../api';

// // interface Props {
// //   isOpen: boolean;
// //   selectedTxnIds: string[];
// //   targetCategory: string;
// //   targetSubcategory: string;
// //   onClose: () => void;
// //   onConfirm: (selectedPatterns: string[]) => void;
// //   isSubmitting?: boolean;
// // }

// // export const PatternSelectionModal: React.FC<Props> = ({
// //   isOpen,
// //   selectedTxnIds,
// //   targetCategory,
// //   targetSubcategory,
// //   onClose,
// //   onConfirm,
// //   isSubmitting = false,
// // }) => {
// //   const [loading, setLoading] = useState<boolean>(false);
// //   const [selectablePatterns, setSelectablePatterns] = useState<string[]>([]);
// //   const [disabledPatterns, setDisabledPatterns] = useState<string[]>([]);
// //   const [chosenPatterns, setChosenPatterns] = useState<string[]>([]);

// //   // Custom Input & Validation State
// //   const [customInput, setCustomInput] = useState<string>('');
// //   const [validating, setValidating] = useState<boolean>(false);
// //   const [evaluation, setEvaluation] = useState<PatternValidationResponse | null>(null);

// //   const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

// //   useEffect(() => {
// //     if (!isOpen || !selectedTxnIds || selectedTxnIds.length === 0) {
// //       setSelectablePatterns([]);
// //       setDisabledPatterns([]);
// //       setChosenPatterns([]);
// //       setCustomInput('');
// //       setEvaluation(null);
// //       return;
// //     }

// //     let isMounted = true;
// //     setLoading(true);

// //     fetchCandidatePatterns(selectedTxnIds)
// //       .then((data) => {
// //         if (!isMounted) return;
// //         const clean = data.selectable_patterns || [];
// //         const disabled = data.disabled_patterns || [];

// //         setSelectablePatterns(clean);
// //         setDisabledPatterns(disabled);

// //         if (clean.length > 0) {
// //           setChosenPatterns([clean[0]]);
// //         }
// //       })
// //       .catch((err) => console.error('Error fetching pattern suggestions:', err))
// //       .finally(() => {
// //         if (isMounted) setLoading(false);
// //       });

// //     return () => {
// //       isMounted = false;
// //     };
// //   }, [isOpen, selectedTxnIds]);

// //   // Debounced Live Backend Pattern Evaluation
// //   // const handleInputChange = (value: string) => {
// //   //   setCustomInput(value);

// //   //   if (debounceTimerRef.current) {
// //   //     clearTimeout(debounceTimerRef.current);
// //   //   }

// //   //   if (!value.trim()) {
// //   //     setEvaluation(null);
// //   //     setValidating(false);
// //   //     return;
// //   //   }

// //   //   setValidating(true);
// //   //   debounceTimerRef.current = setTimeout(() => {
// //   //     validatePatternAnchor(value)
// //   //       .then((res) => setEvaluation(res))
// //   //       .catch((err) => console.error('Pattern validation error:', err))
// //   //       .finally(() => setValidating(false));
// //   //   }, 350);
// //   // };
// // //   const handleInputChange = (value: string) => {
// // //   setCustomInput(value);

// // //   if (debounceTimerRef.current) {
// // //     clearTimeout(debounceTimerRef.current);
// // //   }

// // //   if (!value.trim()) {
// // //     setEvaluation(null);
// // //     setValidating(false);
// // //     return;
// // //   }

// // //   setValidating(true);
// // //   console.log(`[PATTERN DEBUG] Triggering validation for input: "${value}"`);

// // //   debounceTimerRef.current = setTimeout(() => {
// // //     validatePatternAnchor(value)
// // //       .then((res) => {
// // //         console.log('[PATTERN DEBUG] Validation Response from Backend:', res);
// // //         setEvaluation(res);
// // //       })
// // //       .catch((err) => {
// // //         console.error('[PATTERN DEBUG] Validation API Call Failed:', err);
// // //         setEvaluation(null);
// // //       })
// // //       .finally(() => setValidating(false));
// // //   }, 350);
// // // };

// //   const handleInputChange = (value: string) => {
// //   setCustomInput(value);

// //   if (debounceTimerRef.current) {
// //     clearTimeout(debounceTimerRef.current);
// //   }

// //   const trimmed = value.trim();

// //   // Don't trigger backend calls for empty or single-character inputs
// //   if (!trimmed || trimmed.length < 2) {
// //     setEvaluation(null);
// //     setValidating(false);
// //     return;
// //   }

// //   setValidating(true);
// //   debounceTimerRef.current = setTimeout(() => {
// //     validatePatternAnchor(trimmed)
// //       .then((res) => setEvaluation(res))
// //       .catch((err) => {
// //         console.error('Pattern validation error:', err);
// //         setEvaluation(null);
// //       })
// //       .finally(() => setValidating(false));
// //   }, 400); // 400ms feels slightly smoother while typing
// // };

// //   if (!isOpen) return null;

// //   const handleTogglePattern = (pattern: string) => {
// //     setChosenPatterns((prev) =>
// //       prev.includes(pattern) ? prev.filter((p) => p !== pattern) : [...prev, pattern]
// //     );
// //   };

// //   // Add Custom Keyword Chip using Backend's Cleaned String
// //   const handleAddCustomPattern = () => {
// //     if (!evaluation || !evaluation.is_valid || !evaluation.clean_pattern) return;

// //     const targetPattern = evaluation.clean_pattern;

// //     if (!selectablePatterns.includes(targetPattern)) {
// //       setSelectablePatterns((prev) => [...prev, targetPattern]);
// //     }
// //     if (!chosenPatterns.includes(targetPattern)) {
// //       setChosenPatterns((prev) => [...prev, targetPattern]);
// //     }

// //     setCustomInput('');
// //     setEvaluation(null);
// //   };

// //   const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
// //     if (e.key === 'Enter') {
// //       e.preventDefault();
// //       handleAddCustomPattern();
// //     }
// //   };

// //   const isAddDisabled = !evaluation || !evaluation.is_valid || validating;

// //   return (
// //     <div
// //       onClick={onClose}
// //       style={{
// //         position: 'fixed',
// //         inset: 0,
// //         backgroundColor: 'rgba(0,0,0,0.8)',
// //         zIndex: 9999999,
// //         display: 'flex',
// //         alignItems: 'center',
// //         justifyContent: 'center',
// //         padding: '16px',
// //       }}
// //     >
// //       <div
// //         onClick={(e) => e.stopPropagation()}
// //         style={{
// //           backgroundColor: '#18181b',
// //           border: '1px solid #3f3f46',
// //           borderRadius: '12px',
// //           padding: '24px',
// //           maxWidth: '540px',
// //           width: '100%',
// //           color: '#f4f4f5',
// //           boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
// //         }}
// //       >
// //         {/* Header */}
// //         <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
// //           <div>
// //             <h3 style={{ margin: 0, fontSize: '14px', fontWeight: 'bold', color: '#f59e0b', textTransform: 'uppercase' }}>
// //               Confirm Reclassification & Learned Rule
// //             </h3>
// //             <span style={{ fontSize: '11px', color: '#a1a1aa' }}>
// //               Reclassifying {selectedTxnIds.length} item(s) to <strong>{targetCategory} ➔ {targetSubcategory}</strong>
// //             </span>
// //           </div>
// //           <button
// //             type="button"
// //             onClick={onClose}
// //             style={{ background: 'none', border: 'none', color: '#a1a1aa', cursor: 'pointer', fontSize: '18px' }}
// //           >
// //             ✕
// //           </button>
// //         </div>

// //         {/* Pattern Selection Box */}
// //         <div style={{ backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '16px', marginBottom: '20px' }}>
// //           <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
// //             <span style={{ fontSize: '11px', fontWeight: 'bold', color: '#38bdf8', textTransform: 'uppercase' }}>
// //               💡 Select Rule Anchors for Future Auto-Matching
// //             </span>
// //           </div>

// //           {loading ? (
// //             <div style={{ fontSize: '12px', color: '#a1a1aa', padding: '12px 0', textAlign: 'center' }}>
// //               ⏳ Extracting clean vendor phrases from narrations...
// //             </div>
// //           ) : (
// //             <>
// //               {/* Selectable Clean Chips */}
// //               <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '16px' }}>
// //                 {selectablePatterns.length === 0 ? (
// //                   <span style={{ fontSize: '11px', color: '#71717a' }}>
// //                     No specific vendor anchor detected. Type a custom keyword below or reclassify without learning.
// //                   </span>
// //                 ) : (
// //                   selectablePatterns.map((pat) => {
// //                     const isChecked = chosenPatterns.includes(pat);
// //                     return (
// //                       <label
// //                         key={pat}
// //                         style={{
// //                           display: 'inline-flex',
// //                           alignItems: 'center',
// //                           gap: '6px',
// //                           padding: '6px 12px',
// //                           borderRadius: '20px',
// //                           fontSize: '11px',
// //                           fontWeight: '600',
// //                           backgroundColor: isChecked ? '#1e1b4b' : '#18181b',
// //                           color: isChecked ? '#818cf8' : '#a1a1aa',
// //                           border: `1px solid ${isChecked ? '#6366f1' : '#3f3f46'}`,
// //                           cursor: 'pointer',
// //                         }}
// //                       >
// //                         <input
// //                           type="checkbox"
// //                           checked={isChecked}
// //                           onChange={() => handleTogglePattern(pat)}
// //                           style={{ accentColor: '#6366f1', width: '14px', height: '14px', cursor: 'pointer' }}
// //                         />
// //                         {pat}
// //                       </label>
// //                     );
// //                   })
// //                 )}
// //               </div>

// //               {/* Manual Custom Pattern Input Section */}
// // <div style={{ borderTop: '1px solid #1f1f23', paddingTop: '12px', marginBottom: '12px' }}>
// //   <div style={{ display: 'flex', gap: '8px' }}>
// //     <input
// //       type="text"
// //       value={customInput}
// //       onChange={(e) => handleInputChange(e.target.value)}
// //       onKeyDown={handleKeyDown}
// //       placeholder="Type custom keyword anchor (e.g. INT.PD, SUMEE S)..."
// //       style={{
// //         flex: 1,
// //         backgroundColor: '#18181b',
// //         border: '1px solid #3f3f46',
// //         borderRadius: '6px',
// //         padding: '6px 12px',
// //         fontSize: '11px',
// //         color: '#f4f4f5',
// //         outline: 'none',
// //       }}
// //     />
// //     <button
// //       type="button"
// //       onClick={handleAddCustomPattern}
// //       disabled={isAddDisabled}
// //       style={{
// //         padding: '6px 14px',
// //         backgroundColor: !isAddDisabled ? '#6366f1' : '#27272a',
// //         border: 'none',
// //         borderRadius: '6px',
// //         color: !isAddDisabled ? '#ffffff' : '#71717a',
// //         fontSize: '11px',
// //         fontWeight: 'bold',
// //         cursor: !isAddDisabled ? 'pointer' : 'not-allowed',
// //         opacity: !isAddDisabled ? 1 : 0.6,
// //         transition: 'all 0.15s ease-in-out',
// //       }}
// //     >
// //       + Add Tag
// //     </button>
// //   </div>

// //   {/* Fixed Height Container to Stop UI Jitter/Flicker */}
// //   <div style={{ minHeight: '28px', marginTop: '6px' }}>
// //     {validating && (
// //       <div style={{ fontSize: '10px', color: '#71717a', padding: '4px 0' }}>
// //         ⏳ Checking engine rules...
// //       </div>
// //     )}

// //     {!validating && evaluation && (
// //       <div
// //         style={{
// //           fontSize: '11px',
// //           padding: '6px 10px',
// //           borderRadius: '6px',
// //           fontWeight: '500',
// //           backgroundColor:
// //             evaluation.status === 'GOOD' ? '#064e3b' :
// //             evaluation.status === 'BAD' ? '#451a03' : '#4c0519',
// //           color:
// //             evaluation.status === 'GOOD' ? '#6ee7b7' :
// //             evaluation.status === 'BAD' ? '#fcd34d' : '#fda4af',
// //           border: `1px solid ${
// //             evaluation.status === 'GOOD' ? '#047857' :
// //             evaluation.status === 'BAD' ? '#b45309' : '#9f1239'
// //           }`,
// //         }}
// //       >
// //         {evaluation.message}
// //       </div>
// //     )}
// //   </div>
// // </div>


// //               {/* Auto-Blocked Noise Tokens */}
// //               {disabledPatterns.length > 0 && (
// //                 <div style={{ borderTop: '1px solid #1f1f23', paddingTop: '10px' }}>
// //                   <span style={{ fontSize: '10px', color: '#71717a', display: 'block', marginBottom: '6px', fontWeight: 'bold', textTransform: 'uppercase' }}>
// //                     🛡️ Auto-Filtered System Noise (Blocked):
// //                   </span>
// //                   <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
// //                     {disabledPatterns.map((token) => (
// //                       <span
// //                         key={`disabled-${token}`}
// //                         title={`Auto-filtered system noise token: '${token}'`}
// //                         style={{
// //                           display: 'inline-flex',
// //                           alignItems: 'center',
// //                           padding: '3px 8px',
// //                           borderRadius: '12px',
// //                           fontSize: '10px',
// //                           backgroundColor: '#18181b',
// //                           color: '#52525b',
// //                           border: '1px solid #27272a',
// //                           textDecoration: 'line-through',
// //                           cursor: 'not-allowed',
// //                           userSelect: 'none',
// //                         }}
// //                       >
// //                         🛡️ {token}
// //                       </span>
// //                     ))}
// //                   </div>
// //                 </div>
// //               )}
// //             </>
// //           )}
// //         </div>

// //         {/* Footer Actions */}
// //         <div style={{ display: 'flex', gap: '12px' }}>
// //           <button
// //             type="button"
// //             onClick={onClose}
// //             disabled={isSubmitting}
// //             style={{
// //               flex: 1,
// //               padding: '10px',
// //               backgroundColor: '#27272a',
// //               border: 'none',
// //               borderRadius: '6px',
// //               color: '#a1a1aa',
// //               fontSize: '12px',
// //               cursor: 'pointer',
// //             }}
// //           >
// //             Cancel
// //           </button>
// //           <button
// //             type="button"
// //             onClick={() => onConfirm(chosenPatterns)}
// //             disabled={isSubmitting || loading}
// //             style={{
// //               flex: 1.5,
// //               padding: '10px',
// //               backgroundColor: '#f59e0b',
// //               border: 'none',
// //               borderRadius: '6px',
// //               color: '#09090b',
// //               fontSize: '12px',
// //               fontWeight: 'bold',
// //               cursor: isSubmitting || loading ? 'wait' : 'pointer',
// //             }}
// //           >
// //             {isSubmitting ? 'Applying Reclassification...' : 'Confirm & Apply'}
// //           </button>
// //         </div>
// //       </div>
// //     </div>
// //   );
// // };

// // // import React, { useEffect, useState } from 'react';
// // // import { fetchCandidatePatterns } from '../../api';

// // // interface Props {
// // //   isOpen: boolean;
// // //   selectedTxnIds: string[];
// // //   targetCategory: string;
// // //   targetSubcategory: string;
// // //   onClose: () => void;
// // //   onConfirm: (selectedPatterns: string[]) => void;
// // //   isSubmitting?: boolean;
// // // }

// // // export const PatternSelectionModal: React.FC<Props> = ({
// // //   isOpen,
// // //   selectedTxnIds,
// // //   targetCategory,
// // //   targetSubcategory,
// // //   onClose,
// // //   onConfirm,
// // //   isSubmitting = false,
// // // }) => {
// // //   const [loading, setLoading] = useState<boolean>(false);
// // //   const [selectablePatterns, setSelectablePatterns] = useState<string[]>([]);
// // //   const [disabledPatterns, setDisabledPatterns] = useState<string[]>([]);
// // //   const [chosenPatterns, setChosenPatterns] = useState<string[]>([]);

// // //   useEffect(() => {
// // //     if (!isOpen || !selectedTxnIds || selectedTxnIds.length === 0) {
// // //       setSelectablePatterns([]);
// // //       setDisabledPatterns([]);
// // //       setChosenPatterns([]);
// // //       return;
// // //     }

// // //     let isMounted = true;
// // //     setLoading(true);

// // //     fetchCandidatePatterns(selectedTxnIds)
// // //       .then((data) => {
// // //         if (!isMounted) return;
// // //         const clean = data.selectable_patterns || [];
// // //         const disabled = data.disabled_patterns || [];
        
// // //         setSelectablePatterns(clean);
// // //         setDisabledPatterns(disabled);

// // //         // Auto-check the top compound phrase by default (e.g. "PARKING BOOTH")
// // //         if (clean.length > 0) {
// // //           setChosenPatterns([clean[0]]);
// // //         }
// // //       })
// // //       .catch((err) => console.error('Error fetching pattern suggestions:', err))
// // //       .finally(() => {
// // //         if (isMounted) setLoading(false);
// // //       });

// // //     return () => {
// // //       isMounted = false;
// // //     };
// // //   }, [isOpen, selectedTxnIds]);

// // //   if (!isOpen) return null;

// // //   const handleTogglePattern = (pattern: string) => {
// // //     setChosenPatterns((prev) =>
// // //       prev.includes(pattern) ? prev.filter((p) => p !== pattern) : [...prev, pattern]
// // //     );
// // //   };

// // //   return (
// // //     <div
// // //       onClick={onClose}
// // //       style={{
// // //         position: 'fixed',
// // //         inset: 0,
// // //         backgroundColor: 'rgba(0,0,0,0.8)',
// // //         zIndex: 9999999,
// // //         display: 'flex',
// // //         alignItems: 'center',
// // //         justifyContent: 'center',
// // //         padding: '16px',
// // //       }}
// // //     >
// // //       <div
// // //         onClick={(e) => e.stopPropagation()}
// // //         style={{
// // //           backgroundColor: '#18181b',
// // //           border: '1px solid #3f3f46',
// // //           borderRadius: '12px',
// // //           padding: '24px',
// // //           maxWidth: '520px',
// // //           width: '100%',
// // //           color: '#f4f4f5',
// // //           boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
// // //         }}
// // //       >
// // //         {/* Header */}
// // //         <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
// // //           <div>
// // //             <h3 style={{ margin: 0, fontSize: '14px', fontWeight: 'bold', color: '#f59e0b', textTransform: 'uppercase' }}>
// // //               Confirm Reclassification & Learned Rule
// // //             </h3>
// // //             <span style={{ fontSize: '11px', color: '#a1a1aa' }}>
// // //               Reclassifying {selectedTxnIds.length} item(s) to <strong>{targetCategory} ➔ {targetSubcategory}</strong>
// // //             </span>
// // //           </div>
// // //           <button
// // //             type="button"
// // //             onClick={onClose}
// // //             style={{ background: 'none', border: 'none', color: '#a1a1aa', cursor: 'pointer', fontSize: '18px' }}
// // //           >
// // //             ✕
// // //           </button>
// // //         </div>

// // //         {/* Pattern Selection Box */}
// // //         <div style={{ backgroundColor: '#09090b', border: '1px solid #27272a', borderRadius: '8px', padding: '16px', marginBottom: '20px' }}>
// // //           <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
// // //             <span style={{ fontSize: '11px', fontWeight: 'bold', color: '#38bdf8', textTransform: 'uppercase' }}>
// // //               💡 Select Rule Anchors for Future Auto-Matching
// // //             </span>
// // //           </div>

// // //           {loading ? (
// // //             <div style={{ fontSize: '12px', color: '#a1a1aa', padding: '12px 0', textAlign: 'center' }}>
// // //               ⏳ Extracting clean vendor phrases from narrations...
// // //             </div>
// // //           ) : (
// // //             <>
// // //               {/* Selectable Clean Chips */}
// // //               <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '12px' }}>
// // //                 {selectablePatterns.length === 0 ? (
// // //                   <span style={{ fontSize: '11px', color: '#71717a' }}>No specific vendor anchor detected. Reclassifying without saving a new rule pattern.</span>
// // //                 ) : (
// // //                   selectablePatterns.map((pat) => {
// // //                     const isChecked = chosenPatterns.includes(pat);
// // //                     return (
// // //                       <label
// // //                         key={pat}
// // //                         style={{
// // //                           display: 'inline-flex',
// // //                           alignItems: 'center',
// // //                           gap: '6px',
// // //                           padding: '6px 12px',
// // //                           borderRadius: '20px',
// // //                           fontSize: '11px',
// // //                           fontWeight: '600',
// // //                           backgroundColor: isChecked ? '#1e1b4b' : '#18181b',
// // //                           color: isChecked ? '#818cf8' : '#a1a1aa',
// // //                           border: `1px solid ${isChecked ? '#6366f1' : '#3f3f46'}`,
// // //                           cursor: 'pointer',
// // //                         }}
// // //                       >
// // //                         <input
// // //                           type="checkbox"
// // //                           checked={isChecked}
// // //                           onChange={() => handleTogglePattern(pat)}
// // //                           style={{ accentColor: '#6366f1', width: '14px', height: '14px', cursor: 'pointer' }}
// // //                         />
// // //                         {pat}
// // //                       </label>
// // //                     );
// // //                   })
// // //                 )}
// // //               </div>

// // //               {/* Auto-Blocked Noise Tokens */}
// // //               {disabledPatterns.length > 0 && (
// // //                 <div style={{ borderTop: '1px solid #1f1f23', paddingTop: '10px', marginTop: '10px' }}>
// // //                   <span style={{ fontSize: '10px', color: '#71717a', display: 'block', marginBottom: '6px', fontWeight: 'bold', textTransform: 'uppercase' }}>
// // //                     🛡️ Auto-Filtered System Noise (Blocked):
// // //                   </span>
// // //                   <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
// // //                     {disabledPatterns.map((token) => (
// // //                       <span
// // //                         key={`disabled-${token}`}
// // //                         title={`Auto-filtered system noise token: '${token}'`}
// // //                         style={{
// // //                           display: 'inline-flex',
// // //                           alignItems: 'center',
// // //                           padding: '3px 8px',
// // //                           borderRadius: '12px',
// // //                           fontSize: '10px',
// // //                           backgroundColor: '#18181b',
// // //                           color: '#52525b',
// // //                           border: '1px solid #27272a',
// // //                           textDecoration: 'line-through',
// // //                           cursor: 'not-allowed',
// // //                           userSelect: 'none',
// // //                         }}
// // //                       >
// // //                         🛡️ {token}
// // //                       </span>
// // //                     ))}
// // //                   </div>
// // //                 </div>
// // //               )}
// // //             </>
// // //           )}
// // //         </div>

// // //         {/* Footer Actions */}
// // //         <div style={{ display: 'flex', gap: '12px' }}>
// // //           <button
// // //             type="button"
// // //             onClick={onClose}
// // //             disabled={isSubmitting}
// // //             style={{
// // //               flex: 1,
// // //               padding: '10px',
// // //               backgroundColor: '#27272a',
// // //               border: 'none',
// // //               borderRadius: '6px',
// // //               color: '#a1a1aa',
// // //               fontSize: '12px',
// // //               cursor: 'pointer',
// // //             }}
// // //           >
// // //             Cancel
// // //           </button>
// // //           <button
// // //             type="button"
// // //             onClick={() => onConfirm(chosenPatterns)}
// // //             disabled={isSubmitting || loading}
// // //             style={{
// // //               flex: 1.5,
// // //               padding: '10px',
// // //               backgroundColor: '#f59e0b',
// // //               border: 'none',
// // //               borderRadius: '6px',
// // //               color: '#09090b',
// // //               fontSize: '12px',
// // //               fontWeight: 'bold',
// // //               cursor: isSubmitting || loading ? 'wait' : 'pointer',
// // //             }}
// // //           >
// // //             {isSubmitting ? 'Applying Reclassification...' : 'Confirm & Apply'}
// // //           </button>
// // //         </div>
// // //       </div>
// // //     </div>
// // //   );
// // // };