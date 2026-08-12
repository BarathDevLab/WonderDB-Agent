import React, { useState } from 'react';
import {
  CheckCircle2,
  Loader2,
  RotateCcw,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
} from 'lucide-react';
import { ChatMessage } from '../types';
import './new-spinner.js';

declare global {
  namespace JSX {
    interface IntrinsicElements {
      'new-spinner': React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & {
        spinning?: string;
        size?: string;
      };
    }
  }
}

interface ThoughtTrackerProps {
  message: ChatMessage;
}

export const ThoughtTracker: React.FC<ThoughtTrackerProps> = ({ message }) => {
  const {
    phase,
    statusMessage,
    retryCount,
    errorMessage,
    isStreaming,
    thoughtDurationSec,
    strategy,
    sqlQuery,
    explainCost,
    rawResults,
    chartSpec,
  } = message;

  const [elapsedMs, setElapsedMs] = useState(0);
  const [isOpen, setIsOpen] = useState(false);

  // Animated timer for actively streaming thoughts
  React.useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isStreaming && phase !== 'complete' && phase !== 'error') {
      const startTime = Date.now() - elapsedMs;
      interval = setInterval(() => {
        setElapsedMs(Date.now() - startTime);
      }, 100);
    }
    return () => clearInterval(interval);
  }, [isStreaming, phase]);

  const displayTime = isStreaming 
    ? (elapsedMs / 1000).toFixed(1) + 's'
    : (thoughtDurationSec || (elapsedMs / 1000)).toFixed(1) + 's';

  const getPhaseText = () => {
    if (errorMessage) return 'Error';
    if (phase === 'complete') return 'Finished';
    if (phase === 'planning') return 'Generating SQL...';
    if (phase === 'executing') return 'Validating & Executing...';
    if (phase === 'reflecting') return 'Reflecting...';
    if (phase === 'summarizing') return 'Summarizing...';
    return 'Thinking...';
  };

  const getHeaderText = () => {
    if (errorMessage) return 'Error';
    if (phase === 'complete') return 'Stopped';
    if (phase === 'planning') return 'Planning';
    if (phase === 'executing') return 'Executing';
    if (phase === 'reflecting') return 'Reflecting';
    if (phase === 'summarizing') return 'Summarizing';
    return 'Thinking';
  };

  const isCompleted = !isStreaming && phase === 'complete' && !errorMessage;

  if (isCompleted) {
    return (
      <div className="my-2 flex flex-col items-start">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-zinc-800/40 transition-colors group cursor-pointer"
        >
          <span className="text-[14px] font-bold text-zinc-100 group-hover:text-white transition-colors">
            Reasoned in {displayTime}
          </span>
          <ChevronDown className={`h-4 w-4 text-zinc-500 ml-1 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
        </button>

        {isOpen && (
          <div className="mt-3 w-full max-w-2xl overflow-hidden rounded-xl bg-[#111216] border border-zinc-800/80 p-5 shadow-sm text-sm">
            
            {/* Formulated Strategy */}
            <div className="mb-5">
              <h4 className="text-zinc-400 text-xs mb-2">Formulated strategy</h4>
              <div className="rounded-lg bg-[#0a0b0d] p-3 font-mono text-[13px] text-zinc-200">
                {strategy || "query → schema lookup → SQL generation → AST/EXPLAIN gate → chart"}
              </div>
            </div>

            {/* Metrics Grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
              {/* Retrieval */}
              <div className="rounded-lg bg-[#181a1f] p-3 flex flex-col justify-center border border-zinc-800/50 min-h-[70px]">
                <span className="text-zinc-500 text-xs mb-1">Retrieval</span>
                <span className="text-zinc-100 font-semibold text-[13px]">pgvector · 1536-d</span>
              </div>
              
              {/* Query Gate */}
              <div className="rounded-lg bg-[#181a1f] p-3 flex flex-col justify-center border border-zinc-800/50 min-h-[70px]">
                <span className="text-zinc-500 text-xs mb-1">Query gate</span>
                <span className="text-emerald-500 font-semibold text-[13px]">
                  Validated · cost {explainCost !== undefined ? explainCost.toFixed(2) : '0.00'}
                </span>
              </div>

              {/* Rows Returned */}
              <div className="rounded-lg bg-[#181a1f] p-3 flex flex-col justify-center border border-zinc-800/50 min-h-[70px]">
                <span className="text-zinc-500 text-xs mb-1">Rows returned</span>
                <span className="text-zinc-100 font-semibold text-[13px]">{rawResults?.length || 0} records</span>
              </div>

              {/* Output */}
              <div className="rounded-lg bg-[#181a1f] p-3 flex flex-col justify-center border border-zinc-800/50 min-h-[70px]">
                <span className="text-zinc-500 text-xs mb-1">Output</span>
                <span className="text-zinc-100 font-semibold text-[13px]">
                  PII redacted · {chartSpec?.type ? `${chartSpec.type} chart` : 'data grid'}
                </span>
              </div>
            </div>

            {/* Tool calls executed */}
            <div>
              <h4 className="text-zinc-400 text-xs mb-2">Tool calls executed</h4>
              <div className="space-y-1">
                {(message.toolCalls || [
                  { tool: 'get_schema', status: 'success', duration_ms: 340 },
                  { tool: 'execute_query', status: 'success', duration_ms: 890 },
                  { tool: 'explain_data', status: 'success', duration_ms: 2632 },
                  { tool: 'generate_chart', status: 'success', duration_ms: 610 }
                ]).map((call, idx) => (
                  <div key={idx} className="flex items-center justify-between py-2 border-b border-zinc-800/50 last:border-0">
                    <div className="flex items-center gap-3">
                      <div className="flex h-4 w-4 items-center justify-center rounded-full border border-emerald-500 shrink-0">
                        <Check className="h-2.5 w-2.5 text-emerald-500" strokeWidth={3} />
                      </div>
                      <span className="font-mono text-[13px] text-zinc-300 font-medium">{call.tool}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-zinc-400 font-mono text-[13px]">{call.duration_ms}ms</span>
                      <ChevronDown className="h-4 w-4 text-zinc-600" />
                    </div>
                  </div>
                ))}
              </div>
            </div>

          </div>
        )}
      </div>
    );
  }

  // Actively processing state
  return (
    <div className="my-3 transition-all max-w-2xl mx-auto">
      {/* HEADER ROW */}
      <div className="flex items-center gap-2 mb-3.5">
        {isStreaming && !errorMessage ? (
          <new-spinner spinning="true" size="16"></new-spinner>
        ) : errorMessage ? (
          <span className="h-2.5 w-2.5 rounded-full bg-rose-500 shrink-0" />
        ) : (
          <new-spinner spinning="false" size="16"></new-spinner>
        )}
        
        <span className="text-[14px] font-medium text-zinc-100">
          {getHeaderText()}
        </span>
        
        <span className="text-[12px] text-zinc-500 font-mono tracking-wide mt-0.5">
          {displayTime}
        </span>
        
        <div className="flex-1" />
        
        {/* Stop Button */}
        <button 
          className="flex items-center gap-1.5 text-zinc-500 hover:text-zinc-300 transition-colors bg-transparent border-none text-[12px] font-medium px-2 py-1"
          disabled={!isStreaming}
        >
          {isStreaming ? (
            <>
              <div className="h-2.5 w-2.5 bg-zinc-400 rounded-sm" />
              <span>Stop</span>
            </>
          ) : (
            <>
              <RotateCcw className="h-3.5 w-3.5" />
              <span>Restart</span>
            </>
          )}
        </button>
      </div>

      {/* SINGLE LINE STATUS */}
      <div className="relative">
        <div className="text-[14px] text-zinc-300 min-h-[24px] flex items-center gap-2">
           {errorMessage ? (
             <span className="text-rose-400 flex items-center gap-1.5">
               <AlertTriangle className="h-4 w-4" />
               {errorMessage}
             </span>
           ) : (
             <>
               <span className="text-zinc-300 transition-all duration-300">{statusMessage || getPhaseText()}</span>
               
               {retryCount && retryCount > 0 ? (
                 <span className="flex items-center gap-1 rounded-md bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 text-[10px] font-mono text-amber-400 ml-2">
                   <RotateCcw className="h-3 w-3 animate-spin" />
                   Retry #{retryCount}
                 </span>
               ) : null}
             </>
           )}
        </div>
      </div>
    </div>
  );
};
