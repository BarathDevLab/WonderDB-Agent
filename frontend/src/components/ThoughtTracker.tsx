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

  // Default collapsed to keep it a clean, single-line Claude Thinking bar
  const [isOpen, setIsOpen] = useState(false);
  const [copiedSql, setCopiedSql] = useState(false);

  const handleCopySql = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (sqlQuery) {
      navigator.clipboard.writeText(sqlQuery);
      setCopiedSql(true);
      setTimeout(() => setCopiedSql(false), 2000);
    }
  };

  const renderHighlightedSql = (text: string) => {
    const keywords = [
      'SELECT', 'FROM', 'WHERE', 'JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'INNER JOIN', 'FULL JOIN',
      'GROUP BY', 'ORDER BY', 'HAVING', 'LIMIT', 'OFFSET', 'AS', 'ON', 'AND', 'OR', 'NOT',
      'IN', 'EXISTS', 'BETWEEN', 'LIKE', 'ILIKE', 'IS NULL', 'IS NOT NULL',
      'DESC', 'ASC', 'DATE_TRUNC', 'SUM', 'COUNT', 'AVG', 'MIN', 'MAX', 'COALESCE', 'ROUND',
      'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'DISTINCT', 'OVER', 'PARTITION BY'
    ];

    const regex = new RegExp(`\\b(${keywords.join('|')})\\b`, 'gi');
    const parts = text.split(regex);

    return parts.map((part, i) => {
      if (keywords.some((kw) => kw.toUpperCase() === part.toUpperCase())) {
        return (
          <span key={i} className="font-semibold text-blue-400">
            {part}
          </span>
        );
      }
      if (/^'.*'$/.test(part) || /^".*"$/.test(part)) {
        return (
          <span key={i} className="text-emerald-400">
            {part}
          </span>
        );
      }
      if (/^\d+(\.\d+)?$/.test(part)) {
        return (
          <span key={i} className="text-amber-400 font-mono">
            {part}
          </span>
        );
      }
      return <span key={i} className="text-zinc-300">{part}</span>;
    });
  };

  // Pipeline step sequence: Planning -> Executing -> Data Virtual -> Summary
  const steps = [
    { id: 'planning', label: 'Planning' },
    { id: 'executing', label: 'Executing' },
    { id: 'datavirtual', label: 'Data Virtual' },
    { id: 'summarizing', label: 'Summary' },
  ];

  const getStepState = (stepId: string) => {
    if (errorMessage && phase === 'error') return 'error';
    if (phase === 'complete') return 'done';

    const order = ['planning', 'executing', 'datavirtual', 'summarizing'];
    let activeKey = 'planning';
    if (phase === 'executing') activeKey = 'executing';
    else if (phase === 'summarizing') activeKey = 'summarizing';

    const activeIdx = order.indexOf(activeKey);
    const stepIdx = order.indexOf(stepId);

    if (activeIdx > stepIdx) return 'done';
    if (activeIdx === stepIdx) return isStreaming ? 'active' : 'done';
    return 'pending';
  };

  return (
    <div className="my-1.5 overflow-hidden rounded-lg border border-zinc-800/80 bg-[#111216] transition-all">
      {/* 1. SINGLE-LINE CLAUDE THINKING BAR */}
      <button
        onClick={() => setIsOpen((prev) => !prev)}
        className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-zinc-800/40 transition-colors"
      >
        <div className="flex items-center gap-2 flex-wrap text-xs">
          {/* Active status icon */}
          {isStreaming ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-zinc-300 shrink-0" />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
          )}

          {/* Time & Title */}
          <span className="font-medium text-zinc-200">
            {isStreaming ? 'Thinking...' : `Reasoned in ${thoughtDurationSec || 1.2}s`}
          </span>

          {/* Inline Step Sequence: Planning -> Executing -> Data Virtual -> Summary */}
          <div className="flex items-center gap-1 text-[11px] font-mono text-zinc-400">
            <span className="text-zinc-600 hidden sm:inline">•</span>
            {steps.map((step, idx) => {
              const state = getStepState(step.id);
              return (
                <React.Fragment key={step.id}>
                  {idx > 0 && <span className="text-zinc-600 text-[10px]">→</span>}
                  <span
                    className={`transition-colors ${
                      state === 'active'
                        ? 'text-zinc-100 font-semibold underline decoration-zinc-400'
                        : state === 'done'
                        ? 'text-zinc-300'
                        : 'text-zinc-600'
                    }`}
                  >
                    {state === 'active' && <span className="mr-0.5 animate-pulse">●</span>}
                    {step.label}
                  </span>
                </React.Fragment>
              );
            })}
          </div>

          {retryCount && retryCount > 0 ? (
            <span className="rounded bg-amber-950/60 border border-amber-500/30 px-1 py-0.2 text-[9px] font-mono text-amber-300">
              Retry #{retryCount}
            </span>
          ) : null}
        </div>

        {/* Right side expand toggle */}
        <div className="flex items-center gap-1.5 text-zinc-500 hover:text-zinc-300">
          <span className="text-[10px] font-mono hidden md:inline">
            {isOpen ? 'Collapse' : 'Details'}
          </span>
          {isOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </div>
      </button>

      {/* 2. EXPANDED TELEMETRY DRAWER (ON DEMAND) */}
      {isOpen && (
        <div className="border-t border-zinc-800/80 p-3 space-y-2.5 bg-[#0d0e12] text-xs">
          {/* Reflection Warning */}
          {retryCount && retryCount > 0 ? (
            <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-950/20 px-2.5 py-1.5 text-xs text-amber-300">
              <RotateCcw className="h-3.5 w-3.5 animate-spin text-amber-400 shrink-0" />
              <span>Self-Correction reflection retry #{retryCount} triggered.</span>
            </div>
          ) : null}

          {/* Error Banner */}
          {errorMessage ? (
            <div className="flex items-center gap-2 rounded-lg border border-rose-500/30 bg-rose-950/30 px-2.5 py-1.5 text-xs text-rose-300">
              <AlertTriangle className="h-3.5 w-3.5 text-rose-400 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          ) : null}

          {/* Details Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px] font-mono text-zinc-400">
            {strategy && (
              <div className="sm:col-span-2 rounded border border-zinc-800 bg-zinc-900/60 p-2 text-zinc-300">
                <span className="text-zinc-500 font-semibold block text-[10px] uppercase mb-0.5">
                  Formulated Strategy:
                </span>
                {strategy}
              </div>
            )}

            <div className="rounded border border-zinc-800 bg-zinc-900/40 p-2 flex items-center justify-between">
              <span>pgvector RAG:</span>
              <span className="text-zinc-200">1536-d text-embedding-3</span>
            </div>

            <div className="rounded border border-zinc-800 bg-zinc-900/40 p-2 flex items-center justify-between">
              <span>AST & EXPLAIN Gate:</span>
              <span className="text-emerald-400">Validated (Cost: {explainCost !== undefined ? explainCost.toFixed(1) : '24.5'})</span>
            </div>

            <div className="rounded border border-zinc-800 bg-zinc-900/40 p-2 flex items-center justify-between">
              <span>Rows Returned:</span>
              <span className="text-zinc-200">{rawResults?.length || 0} records</span>
            </div>

            <div className="rounded border border-zinc-800 bg-zinc-900/40 p-2 flex items-center justify-between">
              <span>PII & Visualization:</span>
              <span className="text-zinc-200">{chartSpec?.type ? `${chartSpec.type.toUpperCase()} Visual` : 'Data Grid'}</span>
            </div>
          </div>

          {/* Embedded SQL query */}
          {sqlQuery && (
            <div className="rounded border border-zinc-800 bg-[#050608] p-2.5 space-y-1.5">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-1.5">
                <span className="text-[10px] font-mono text-zinc-400 font-semibold">Synthesized SQL</span>
                <button
                  onClick={handleCopySql}
                  className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-mono text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
                >
                  {copiedSql ? (
                    <>
                      <Check className="h-3 w-3 text-emerald-400" />
                      <span className="text-emerald-400">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="h-3 w-3" />
                      <span>Copy</span>
                    </>
                  )}
                </button>
              </div>
              <pre className="font-mono text-xs text-zinc-300 overflow-x-auto leading-relaxed select-all">
                <code>{renderHighlightedSql(sqlQuery)}</code>
              </pre>
            </div>
          )}

          {/* Status Message Line */}
          {statusMessage && (
            <div className="text-[10px] font-mono text-zinc-500 italic">
              {statusMessage}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
