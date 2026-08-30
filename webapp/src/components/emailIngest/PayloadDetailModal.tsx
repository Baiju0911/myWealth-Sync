import React, { useState } from 'react';
import { type EmailPayload } from '../../api/emailIngestApi';
import { CheckCircle, Copy, AlertTriangle } from 'lucide-react';

interface Props {
  payload: EmailPayload | null;
  onClose: () => void;
}

export const PayloadDetailModal: React.FC<Props> = ({ payload, onClose }) => {
  const [activeTab, setActiveTab] = useState<'text' | 'raw'>('text');

  if (!payload) return null;

  const renderStatusBadge = (status: EmailPayload['status']) => {
    switch (status) {
      case 'PARSED':
        return (
          <span className="px-2 py-1 text-xs font-semibold rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800/50 inline-flex items-center gap-1">
            <CheckCircle className="w-3 h-3" /> PARSED
          </span>
        );
      case 'DUPLICATE':
        return (
          <span className="px-2 py-1 text-xs font-semibold rounded-full bg-slate-800 text-slate-300 border border-slate-700 inline-flex items-center gap-1">
            <Copy className="w-3 h-3" /> DUPLICATE
          </span>
        );
      default:
        return (
          <span className="px-2 py-1 text-xs font-semibold rounded-full bg-rose-950 text-rose-400 border border-rose-800/50 inline-flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" /> {status}
          </span>
        );
    }
  };

  const cleanEmailBody = (htmlString?: string) => {
    if (!htmlString) return 'No raw body content available.';
    let clean = htmlString.replace(/<(style|script)[^>]*>[\s\S]*?<\/\1>/gi, '');
    clean = clean.replace(/<(br|p|div|tr|td)[^>]*>/gi, '\n');
    clean = clean.replace(/<[^>]+>/g, '');
    return clean.replace(/\n\s*\n/g, '\n\n').trim();
  };

  const bodyContent = payload.body || payload.decrypted_body;

  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-2xl w-full p-6 space-y-4 shadow-2xl max-h-[90vh] overflow-y-auto text-slate-200">
        <div className="flex justify-between items-start border-b border-slate-800 pb-3">
          <div>
            <h3 className="text-lg font-bold text-slate-100">Payload Details</h3>
            <p className="text-xs text-slate-500 font-mono">{payload.id}</p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 text-lg font-bold px-2 cursor-pointer"
          >
            ✕
          </button>
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-xs font-semibold text-slate-500 block">Bank</span>
            <span className="font-medium text-slate-200">{payload.bank_name || 'N/A'}</span>
          </div>
          <div>
            <span className="text-xs font-semibold text-slate-500 block">Status</span>
            {renderStatusBadge(payload.status)}
          </div>
          <div>
            <span className="text-xs font-semibold text-slate-500 block">From</span>
            <span className="font-mono text-xs text-indigo-400">{payload.email_from}</span>
          </div>
          <div>
            <span className="text-xs font-semibold text-slate-500 block">Source</span>
            <span className="font-mono text-xs text-slate-300">{payload.source}</span>
          </div>
        </div>

        <div>
          <span className="text-xs font-semibold text-slate-500 block mb-1">Subject</span>
          <p className="text-sm bg-slate-950 p-2.5 rounded border border-slate-800 text-slate-300">
            {payload.subject || 'N/A'}
          </p>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-slate-500">Email Payload Content</span>
            <div className="flex gap-2">
              <button
                onClick={() => setActiveTab('text')}
                className={`px-2.5 py-1 text-xs font-mono rounded cursor-pointer ${
                  activeTab === 'text'
                    ? 'bg-indigo-600 text-white font-bold'
                    : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                Clean Text
              </button>
              <button
                onClick={() => setActiveTab('raw')}
                className={`px-2.5 py-1 text-xs font-mono rounded cursor-pointer ${
                  activeTab === 'raw'
                    ? 'bg-indigo-600 text-white font-bold'
                    : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                Raw JSON
              </button>
            </div>
          </div>

          {activeTab === 'text' ? (
            <pre className="text-xs bg-slate-950 text-slate-200 p-3.5 rounded-lg overflow-x-auto font-mono max-h-56 border border-slate-800 whitespace-pre-wrap leading-relaxed">
              {cleanEmailBody(bodyContent)}
            </pre>
          ) : (
            <pre className="text-xs bg-slate-950 text-emerald-400 p-3 rounded-lg overflow-x-auto font-mono max-h-56 border border-slate-800">
              {JSON.stringify(payload, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
};