import React, { useState } from 'react';
import { type EmailPayload } from '../../api/emailIngestApi';
import { 
  CheckCircle, 
  Copy, 
  AlertTriangle, 
  ArrowUpRight, 
  ArrowDownLeft, 
  Check, 
  GitMerge, 
  Mail, 
  Smartphone, 
  ShieldAlert 
} from 'lucide-react';

interface Props {
  payload: EmailPayload | any | null;
  onClose: () => void;
}

export const PayloadInspectorModal: React.FC<Props> = ({ payload, onClose }) => {
  const [activeTab, setActiveTab] = useState<'text' | 'raw'>('text');
  const [copied, setCopied] = useState<boolean>(false);

  if (!payload) return null;

  // Extract nested audit structures safely
  const rawPayload = payload.raw_item?.raw_payload || payload.raw_payload || {};
  const headersJson = rawPayload.headers_json || payload.headers_json || {};
  const mergeDetails = rawPayload.merge_details || headersJson.merge_details || payload.merge_details;
  const signals = headersJson.signals || {};
 // const bodyContent = payload.body || (payload as any).decrypted_body;

  const isMerged = 
    payload.source === 'MERGED_STREAM' || 
    payload.status === 'MATCHED_2_WAY' || 
    Boolean(mergeDetails) || 
    Boolean(headersJson.is_merged);

  const isDuplicate = payload.status === 'DUPLICATE' || payload.is_duplicate;

  const renderStatusBadge = (status: string) => {
    switch (status) {
      case 'MATCHED_2_WAY':
        return (
          <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-indigo-950/90 text-indigo-400 border border-indigo-700/60 inline-flex items-center gap-1 font-mono">
            <GitMerge className="w-3 h-3" /> MATCHED 2-WAY
          </span>
        );
      case 'PARSED':
      case 'COMPLETED':
        return (
          <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-emerald-950/80 text-emerald-400 border border-emerald-800/60 inline-flex items-center gap-1 font-mono">
            <CheckCircle className="w-3 h-3" /> {status}
          </span>
        );
      case 'DUPLICATE':
        return (
          <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-amber-950/80 text-amber-400 border border-amber-800/60 inline-flex items-center gap-1 font-mono">
            <Copy className="w-3 h-3" /> DUPLICATE
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-rose-950/80 text-rose-400 border border-rose-800/60 inline-flex items-center gap-1 font-mono">
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

  const bodyContent = payload.body || payload.decrypted_body || rawPayload.decrypted_body || '';
  const isCredit = payload.txn_type === 'CREDIT';
  const taxonomy = payload.taxonomy_payload?.taxonomy;

  const handleCopyContent = () => {
    const textToCopy = activeTab === 'text' 
      ? cleanEmailBody(bodyContent) 
      : JSON.stringify(payload, null, 2);
    
    navigator.clipboard.writeText(textToCopy);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-3xl w-full p-6 space-y-4 shadow-2xl max-h-[92vh] overflow-y-auto text-slate-200 font-sans">
        
        {/* Modal Header */}
        <div className="flex justify-between items-start border-b border-slate-800 pb-3">
          <div>
            <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              Payload Details
              {renderStatusBadge(payload.status)}
            </h3>
            <p className="text-xs text-slate-500 font-mono mt-0.5 break-all">{payload.id}</p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 text-lg font-bold px-2 cursor-pointer transition-colors"
          >
            ✕
          </button>
        </div>

        {/* 🚨 DUPLICATE ALERT BANNER */}
        {isDuplicate && (
          <div className="p-3 bg-amber-950/40 border border-amber-800/70 rounded-lg flex items-start gap-2.5 text-xs font-mono text-amber-200">
            <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <div className="space-y-1 overflow-hidden">
              <span className="font-bold text-amber-300 block">Identified Ingestion Conflict</span>
              <p className="text-amber-200/90 leading-relaxed font-sans text-xs">
                This item matches a pre-existing record in Vault with identical signature key or RRN ref:
              </p>
              <div className="bg-slate-950/80 p-2 rounded border border-amber-900/40 text-[11px] text-amber-400 break-all space-y-0.5">
                <div><span className="text-slate-500">Hash/FP:</span> {payload.payload_hash || payload.txn_fingerprint || 'Matched on RRN + Amount'}</div>
                {payload.upi_ref && <div><span className="text-slate-500">Conflict RRN:</span> {payload.upi_ref}</div>}
              </div>
            </div>
          </div>
        )}

        {/* 🔀 MERGED STREAM BREAKDOWN SECTION */}
        {isMerged && (
          <div className="p-3.5 bg-indigo-950/30 border border-indigo-700/50 rounded-xl space-y-3 font-mono">
            <div className="flex items-center justify-between border-b border-indigo-800/40 pb-2">
              <span className="text-xs font-bold text-indigo-300 flex items-center gap-1.5">
                <GitMerge className="w-4 h-4 text-indigo-400" />
                Cross-Channel Merged Provenance
              </span>
              <span className="text-[10px] bg-indigo-900/80 text-indigo-200 px-2 py-0.5 rounded border border-indigo-600/50">
                Tier 1 Reference Hash
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              {/* Channel 1: Gmail API */}
              <div className="p-2.5 bg-slate-950/80 rounded-lg border border-slate-800 space-y-1.5">
                <div className="flex items-center gap-1.5 text-slate-400 text-[11px] font-bold">
                  <Mail className="w-3.5 h-3.5 text-blue-400" /> Gmail Ingestion Stream
                </div>
                <div className="text-[11px] text-slate-300 bg-slate-900 p-2 rounded max-h-24 overflow-y-auto whitespace-pre-wrap font-sans">
                  {mergeDetails?.gmail_body || mergeDetails?.email_body || signals?.gmail_api?.raw_text || 'Linked from Gmail notification stream.'}
                </div>
              </div>

              {/* Channel 2: iOS SMS */}
              <div className="p-2.5 bg-slate-950/80 rounded-lg border border-slate-800 space-y-1.5">
                <div className="flex items-center gap-1.5 text-slate-400 text-[11px] font-bold">
                  <Smartphone className="w-3.5 h-3.5 text-amber-400" /> iOS SMS Alert Stream
                </div>
                <div className="text-[11px] text-slate-300 bg-slate-900 p-2 rounded max-h-24 overflow-y-auto whitespace-pre-wrap font-sans">
                  {mergeDetails?.sms_body || signals?.ios_sms?.raw_text || 'Linked from SMS alert stream.'}
                </div>
              </div>
            </div>

            {/* Final Derived Narration */}
            <div className="p-2 bg-indigo-950/50 rounded border border-indigo-800/60 text-[11px] flex items-center justify-between">
              <span className="text-slate-400">Resolved Narration:</span>
              <span className="font-bold text-emerald-400 truncate max-w-[70%]">
                {mergeDetails?.resolved_narration || payload.full_narration || payload.merchant}
              </span>
            </div>
          </div>
        )}

        {/* 🎯 Financial & Ingest Meta Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 p-3 bg-slate-950/60 rounded-lg border border-slate-800/80 text-xs font-mono">
          <div>
            <span className="text-[10px] text-slate-500 uppercase tracking-wider block">Bank & Account</span>
            <span className="font-semibold text-slate-200 block">{payload.bank_name || 'SOUTH INDIAN BANK'}</span>
            <span className="text-[11px] text-indigo-400">
              {payload.account_last4 ? `A/c X${payload.account_last4}` : 'A/c —'}
            </span>
          </div>

          <div>
            <span className="text-[10px] text-slate-500 uppercase tracking-wider block">Amount & Type</span>
            {payload.amount !== null && payload.amount !== undefined ? (
              <span className={`font-bold text-sm inline-flex items-center gap-0.5 ${isCredit ? 'text-emerald-400' : 'text-rose-400'}`}>
                {isCredit ? <ArrowDownLeft className="w-3.5 h-3.5" /> : <ArrowUpRight className="w-3.5 h-3.5" />}
                ₹{Number(payload.amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            ) : (
              <span className="text-slate-500">—</span>
            )}
          </div>

          <div>
            <span className="text-[10px] text-slate-500 uppercase tracking-wider block">Available Balance</span>
            <span className="font-bold text-slate-200 block">
              {payload.balance ? `₹${Number(payload.balance).toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : '—'}
            </span>
          </div>

          <div>
            <span className="text-[10px] text-slate-500 uppercase tracking-wider block">UPI Ref / RRN</span>
            <span className="text-slate-300 block truncate">{payload.upi_ref || '—'}</span>
          </div>

          <div>
            <span className="text-[10px] text-slate-500 uppercase tracking-wider block">Channel Source</span>
            <span className={`font-bold block ${isMerged ? 'text-emerald-400' : 'text-indigo-400'}`}>
              {payload.source || 'IOS_SMS'}
            </span>
          </div>

          <div>
            <span className="text-[10px] text-slate-500 uppercase tracking-wider block">Received Date</span>
            <span className="text-slate-300 block">
              {payload.email_date ? new Date(payload.email_date).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' }) : '—'}
            </span>
          </div>
        </div>

        {/* 🎯 Taxonomy Classification Banner */}
        <div className="p-2.5 bg-indigo-950/30 border border-indigo-800/40 rounded-lg flex items-center justify-between text-xs font-mono">
          <div className="flex items-center gap-2">
            <span className="text-indigo-400 font-bold">Taxonomy:</span>
            {taxonomy?.category_name ? (
              <span className="text-slate-200">
                <span className="text-indigo-300 font-semibold">{taxonomy.category_name}</span>
                {taxonomy.subcategory_name && <span className="text-slate-500"> ❯ </span>}
                <span className="text-emerald-400">{taxonomy.subcategory_name}</span>
              </span>
            ) : (
              <span className="text-slate-500 italic">Unclassified (Pending Assignment)</span>
            )}
          </div>
        </div>

        {/* Sender & Narration Details */}
        <div className="space-y-2 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-slate-500 font-semibold w-16">Sender:</span>
            <span className="font-mono text-indigo-400 truncate">{payload.email_from || payload.sender || '—'}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-slate-500 font-semibold w-16">Narration:</span>
            <p className="text-xs bg-slate-950 px-2.5 py-1.5 rounded border border-slate-800 text-slate-300 font-mono flex-1 truncate">
              {payload.full_narration || payload.merchant || payload.subject || '—'}
            </p>
          </div>
        </div>

        {/* Body Viewer Controls & Output */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-slate-400">Payload Content Viewer</span>
            <div className="flex items-center gap-2">
              <button
                onClick={handleCopyContent}
                className="px-2 py-1 text-[11px] font-mono rounded bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center gap-1 cursor-pointer transition-colors"
              >
                {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                {copied ? 'Copied' : 'Copy'}
              </button>
              <div className="flex gap-1">
                <button
                  onClick={() => setActiveTab('text')}
                  className={`px-2.5 py-1 text-xs font-mono rounded cursor-pointer transition-colors ${
                    activeTab === 'text'
                      ? 'bg-indigo-600 text-white font-bold'
                      : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Clean Text
                </button>
                <button
                  onClick={() => setActiveTab('raw')}
                  className={`px-2.5 py-1 text-xs font-mono rounded cursor-pointer transition-colors ${
                    activeTab === 'raw'
                      ? 'bg-indigo-600 text-white font-bold'
                      : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Raw JSON
                </button>
              </div>
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