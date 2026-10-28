import React, { useState } from 'react';
import { Copy, Check, Sparkles, Building2 } from 'lucide-react';

interface Props {
  item: {
    narration?: string;
    raw_narration?: string;
    universal_narration?: string;
    display_text?: string;
    remarks?: any;
  };
}

export const DualNarrationViewer: React.FC<Props> = ({ item }) => {
  const [viewMode, setViewMode] = useState<'smart' | 'raw'>('smart');
  const [copied, setCopied] = useState<boolean>(false);

  // Fallback checks across all possible payload fields
  const smartNarration =
    item.universal_narration ||
    item.display_text ||
    item.remarks?.universal_narration ||
    item.narration ||
    '';

  const rawNarration =
    item.raw_narration ||
    item.remarks?.raw_narration ||
    item.remarks?.narration ||
    item.narration ||
    '';

  const currentText = viewMode === 'smart' ? smartNarration : rawNarration;

  const handleCopy = () => {
    if (!currentText) return;
    navigator.clipboard.writeText(currentText);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  return (
    <div style={{ marginBottom: '16px' }}>
      {/* Top Toggle Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
        <div style={{ display: 'flex', gap: '4px', backgroundColor: '#09090b', padding: '3px', borderRadius: '8px', border: '1px solid #27272a' }}>
          <button
            type="button"
            onClick={() => setViewMode('smart')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
              padding: '4px 10px',
              borderRadius: '6px',
              fontSize: '11px',
              fontWeight: 'bold',
              cursor: 'pointer',
              border: viewMode === 'smart' ? '1px solid #f59e0b55' : '1px solid transparent',
              backgroundColor: viewMode === 'smart' ? '#f59e0b22' : 'transparent',
              color: viewMode === 'smart' ? '#fbbf24' : '#a1a1aa',
              transition: 'all 0.15s ease',
            }}
          >
            <Sparkles style={{ width: '12px', height: '12px' }} />
            Smart Narrative
          </button>

          <button
            type="button"
            onClick={() => setViewMode('raw')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
              padding: '4px 10px',
              borderRadius: '6px',
              fontSize: '11px',
              fontWeight: 'bold',
              cursor: 'pointer',
              border: viewMode === 'raw' ? '1px solid #38bdf855' : '1px solid transparent',
              backgroundColor: viewMode === 'raw' ? '#0284c722' : 'transparent',
              color: viewMode === 'raw' ? '#38bdf8' : '#a1a1aa',
              transition: 'all 0.15s ease',
            }}
          >
            <Building2 style={{ width: '12px', height: '12px' }} />
            Raw Bank Statement
          </button>
        </div>

        <button
          type="button"
          onClick={handleCopy}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            padding: '4px 8px',
            backgroundColor: '#27272a',
            border: '1px solid #3f3f46',
            borderRadius: '6px',
            color: copied ? '#34d399' : '#d4d4d8',
            fontSize: '10px',
            cursor: 'pointer',
            fontWeight: 'bold',
          }}
          title="Copy displayed narration"
        >
          {copied ? <Check style={{ width: '12px', height: '12px' }} /> : <Copy style={{ width: '12px', height: '12px' }} />}
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>
      </div>

      {/* Output Display Container */}
      <div
        style={{
          backgroundColor: '#09090b',
          border: `1px solid ${viewMode === 'smart' ? '#f59e0b44' : '#0284c744'}`,
          padding: '10px 12px',
          borderRadius: '8px',
          fontSize: '11px',
          fontFamily: viewMode === 'raw' ? 'monospace' : 'inherit',
          color: viewMode === 'smart' ? '#f4f4f5' : '#38bdf8',
          wordBreak: 'break-word',
          lineHeight: '1.5',
          minHeight: '48px',
        }}
      >
        {currentText || 'No narration data recorded.'}
      </div>
    </div>
  );
};