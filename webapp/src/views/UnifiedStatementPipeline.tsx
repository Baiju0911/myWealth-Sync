import React, { useState } from 'react';
import UniversalStatementIngestView from './UniversalStatementIngestView';
import StagingQueueEvaluator from './StagingQueueEvaluator';
import LedgerDashboard from './LedgerDashboard';

export const UnifiedStatementPipeline: React.FC = () => {
  const [activeStep, setActiveStep] = useState<1 | 2 | 3>(1);

  const steps = [
    { id: 1, label: '1. Statement Ingestion', desc: 'Upload & Parse Files' },
    { id: 2, label: '2. Staging & Auto-Sweep', desc: 'Node 99 Rules & Cluster Cleanup' },
    { id: 3, label: '3. Ledger Dashboard', desc: 'Final Double-Entry Ledger' },
  ];

  return (
    <div className="w-full flex flex-col gap-4">
      {/* Stepper Ribbon */}
      <div className="bg-zinc-900 border border-zinc-800 p-3 rounded-xl flex items-center justify-between gap-2 overflow-x-auto">
        <div className="flex items-center gap-3">
          {steps.map((step) => {
            const isActive = activeStep === step.id;
            const isPassed = activeStep > step.id;

            return (
              <button
                key={step.id}
                onClick={() => setActiveStep(step.id as 1 | 2 | 3)}
                className={`flex items-center gap-2.5 px-3 py-1.5 rounded-lg border text-xs font-bold transition-all cursor-pointer ${
                  isActive
                    ? 'bg-emerald-600 text-white border-emerald-500 shadow-md shadow-emerald-950'
                    : isPassed
                    ? 'bg-zinc-900 text-emerald-400 border-emerald-900/50'
                    : 'bg-zinc-950 text-zinc-500 border-zinc-800'
                }`}
              >
                <span className="font-mono">{isPassed ? '✓' : step.id}</span>
                <div className="text-left">
                  <div>{step.label}</div>
                  <div className="text-[9px] font-normal opacity-80">{step.desc}</div>
                </div>
              </button>
            );
          })}
        </div>

        <div className="text-[11px] font-mono text-zinc-400 hidden sm:block">
          Pipeline Active: <span className="text-amber-400 font-bold">Step {activeStep} / 3</span>
        </div>
      </div>

      {/* Dynamic Step Viewport */}
      <div className="w-full">
        {activeStep === 1 && (
          <UniversalStatementIngestView onIngestionComplete={() => setActiveStep(2)} />
        )}
        {activeStep === 2 && (
          <StagingQueueEvaluator onSweepComplete={() => setActiveStep(3)} />
        )}
        {activeStep === 3 && (
          <LedgerDashboard />
        )}
      </div>
    </div>
  );
};

export default UnifiedStatementPipeline;