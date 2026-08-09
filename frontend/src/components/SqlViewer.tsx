import React, { useState } from 'react';
import { Terminal, Copy, Check, Sparkles, Gauge, Database } from 'lucide-react';

interface SqlViewerProps {
  sql: string;
  strategy?: string;
  cost?: number;
  rowCount?: number;
}

export const SqlViewer: React.FC<SqlViewerProps> = ({ sql, strategy, cost, rowCount }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Basic SQL Syntax Highlighting
  const renderHighlightedSql = (text: string) => {
    const keywords = [
      'SELECT', 'FROM', 'WHERE', 'JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'INNER JOIN',
      'GROUP BY', 'ORDER BY', 'HAVING', 'LIMIT', 'OFFSET', 'AS', 'ON', 'AND', 'OR',
      'DESC', 'ASC', 'DATE_TRUNC', 'SUM', 'COUNT', 'AVG', 'MIN', 'MAX'
    ];

    // Simple tokenizer for display
    const regex = new RegExp(`\\b(${keywords.join('|')})\\b`, 'gi');
    const parts = text.split(regex);

    return parts.map((part, i) => {
      if (keywords.some((kw) => kw.toUpperCase() === part.toUpperCase())) {
        return (
          <span key={i} className="font-bold text-cyan-400">
            {part}
          </span>
        );
      }
      if (/^'.*'$/.test(part) || /^".*"$/.test(part)) {
        return (
          <span key={i} className="text-emerald-300">
            {part}
          </span>
        );
      }
      if (/^\d+(\.\d+)?$/.test(part)) {
        return (
          <span key={i} className="text-amber-300">
            {part}
          </span>
        );
      }
      return <span key={i} className="text-slate-200">{part}</span>;
    });
  };

  return (
    <div className="my-3 overflow-hidden rounded-xl border border-white/[0.08] bg-[#070a14] shadow-md">
      {/* Strategy Ribbon */}
      {strategy && (
        <div className="flex items-center gap-2 border-b border-white/[0.06] bg-slate-900/60 px-3.5 py-2 text-xs text-indigo-300">
          <Sparkles className="h-3.5 w-3.5 text-indigo-400 shrink-0" />
          <span className="font-medium text-slate-400">Strategy:</span>
          <span className="font-semibold text-indigo-200 truncate">{strategy}</span>
        </div>
      )}

      {/* Header bar */}
      <div className="flex items-center justify-between border-b border-white/[0.06] bg-[#0c1222] px-3.5 py-2">
        <div className="flex items-center gap-2 font-mono text-xs text-slate-400">
          <Terminal className="h-3.5 w-3.5 text-cyan-400" />
          <span className="font-semibold text-slate-300">Synthesized SQL Query</span>
        </div>

        <div className="flex items-center gap-2.5">
          {cost !== undefined && (
            <div className="flex items-center gap-1 font-mono text-[11px] text-amber-300 bg-amber-950/40 border border-amber-500/20 px-2 py-0.5 rounded">
              <Gauge className="h-3 w-3 text-amber-400" />
              <span>Cost: {cost.toFixed(2)}</span>
            </div>
          )}

          {rowCount !== undefined && (
            <div className="flex items-center gap-1 font-mono text-[11px] text-emerald-300 bg-emerald-950/40 border border-emerald-500/20 px-2 py-0.5 rounded">
              <Database className="h-3 w-3 text-emerald-400" />
              <span>{rowCount} rows</span>
            </div>
          )}

          <button
            onClick={handleCopy}
            className="flex items-center gap-1 rounded bg-slate-800 hover:bg-slate-700 px-2 py-1 text-[11px] font-mono text-slate-300 hover:text-white transition-all active:scale-95"
            title="Copy SQL to Clipboard"
          >
            {copied ? (
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
      </div>

      {/* SQL Body */}
      <div className="p-3.5 overflow-x-auto bg-[#070a14]">
        <pre className="font-mono text-xs sm:text-[13px] leading-relaxed select-all">
          <code>{renderHighlightedSql(sql)}</code>
        </pre>
      </div>
    </div>
  );
};
