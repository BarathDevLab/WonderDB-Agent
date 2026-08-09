import React from 'react';
import { Search, ShieldAlert, Zap, BarChart2, CheckCircle2, Loader2, RotateCcw, AlertTriangle } from 'lucide-react';
import { ChatMessage } from '../types';

interface ThoughtTrackerProps {
  message: ChatMessage;
}

export const ThoughtTracker: React.FC<ThoughtTrackerProps> = ({ message }) => {
  const { phase, statusMessage, retryCount, errorMessage } = message;

  const steps = [
    {
      id: 'planning',
      title: 'pgvector Schema RAG',
      desc: '1536-d dense embedding & FK expansion',
      icon: Search,
    },
    {
      id: 'executing',
      title: 'AST & EXPLAIN Gate',
      desc: 'sqlglot safety & cost threshold check',
      icon: ShieldAlert,
    },
    {
      id: 'summarizing',
      title: 'RLS DB Execution',
      desc: 'Multi-tenant isolated query execution',
      icon: Zap,
    },
    {
      id: 'complete',
      title: 'PII & Visual Synthesis',
      desc: 'Sensitive field masking & Chart.js spec',
      icon: BarChart2,
    },
  ];

  const getStepStatus = (stepId: string) => {
    if (errorMessage && phase === 'error') {
      return 'error';
    }
    const phaseOrder = ['planning', 'executing', 'summarizing', 'complete'];
    const currentIdx = phaseOrder.indexOf(phase || 'planning');
    const stepIdx = phaseOrder.indexOf(stepId);

    if (phase === 'complete') return 'done';
    if (stepIdx < currentIdx) return 'done';
    if (stepIdx === currentIdx) return 'active';
    return 'pending';
  };

  return (
    <div className="my-3 rounded-xl border border-white/[0.08] bg-[#090d1a]/90 p-3 sm:p-4 backdrop-blur-md shadow-lg">
      {/* Self Correction Notification */}
      {retryCount && retryCount > 0 ? (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-950/30 px-3 py-2 text-xs text-amber-300">
          <RotateCcw className="h-4 w-4 animate-spin text-amber-400" />
          <span>
            <strong>Self-Correction Active:</strong> AST/Execution error triggered reflection retry #{retryCount}. Repairing SQL query candidate...
          </span>
        </div>
      ) : null}

      {/* Error Notification */}
      {errorMessage ? (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-rose-500/30 bg-rose-950/40 px-3 py-2 text-xs text-rose-300">
          <AlertTriangle className="h-4 w-4 text-rose-400" />
          <span>
            <strong>Security or Execution Error:</strong> {errorMessage}
          </span>
        </div>
      ) : null}

      {/* Pipeline Steps Grid */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {steps.map((step, idx) => {
          const status = getStepStatus(step.id);
          const StepIcon = step.icon;

          return (
            <div
              key={step.id}
              className={`relative flex flex-col rounded-lg border p-2.5 transition-all ${
                status === 'done'
                  ? 'border-emerald-500/30 bg-emerald-950/20 text-emerald-300'
                  : status === 'active'
                  ? 'border-cyan-500/50 bg-cyan-950/30 text-cyan-200 shadow-[0_0_15px_rgba(6,182,212,0.15)]'
                  : 'border-white/[0.04] bg-slate-900/30 text-slate-500'
              }`}
            >
              <div className="flex items-center justify-between gap-1 mb-1">
                <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase font-bold tracking-wider">
                  <span className="opacity-60">0{idx + 1}</span>
                  <StepIcon className="h-3.5 w-3.5" />
                </div>
                {status === 'done' ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                ) : status === 'active' ? (
                  <Loader2 className="h-3.5 w-3.5 text-cyan-400 animate-spin" />
                ) : (
                  <span className="h-2 w-2 rounded-full bg-slate-700" />
                )}
              </div>
              <span className="text-xs font-semibold text-white tracking-tight">{step.title}</span>
              <span className="text-[10px] text-slate-400 line-clamp-1">{step.desc}</span>
            </div>
          );
        })}
      </div>

      {/* Live Status Message Telemetry */}
      {statusMessage && (
        <div className="mt-2.5 flex items-center gap-2 font-mono text-[11px] text-cyan-300/90 bg-cyan-950/30 border border-cyan-500/20 rounded-md px-2.5 py-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-ping" />
          <span className="truncate">{statusMessage}</span>
        </div>
      )}
    </div>
  );
};
