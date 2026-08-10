import React from 'react';
import { ToolCall } from '../types';
import { Wrench, CheckCircle2, Clock, AlertCircle } from 'lucide-react';

interface ToolCallBadgeProps {
  calls?: ToolCall[];
}

export const ToolCallBadge: React.FC<ToolCallBadgeProps> = ({ calls }) => {
  if (!calls || calls.length === 0) return null;

  return (
    <div className="my-2 flex flex-wrap items-center gap-1.5">
      <span className="flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider text-zinc-400 mr-1">
        <Wrench className="h-3 w-3 text-zinc-400" />
        MCP Tools Executed:
      </span>
      {calls.map((c, i) => (
        <div
          key={i}
          className="flex items-center gap-1.5 rounded-md border border-zinc-800 bg-[#14151a] px-2 py-0.5 text-[11px] font-mono text-zinc-300"
        >
          {c.status === 'done' ? (
            <CheckCircle2 className="h-3 w-3 text-emerald-400 shrink-0" />
          ) : c.status === 'error' ? (
            <AlertCircle className="h-3 w-3 text-rose-400 shrink-0" />
          ) : (
            <Clock className="h-3 w-3 text-amber-400 animate-spin shrink-0" />
          )}
          <span className="font-semibold text-zinc-200">{c.tool}</span>
          {c.duration_ms !== undefined && (
            <span className="text-[10px] text-zinc-400">({c.duration_ms}ms)</span>
          )}
        </div>
      ))}
    </div>
  );
};
