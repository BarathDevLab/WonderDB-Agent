import React, { useState, useRef, useEffect } from 'react';
import { Send, Square, Sparkles, CornerDownLeft } from 'lucide-react';

interface ChatInputProps {
  onSend: (prompt: string) => void;
  onCancel: () => void;
  isStreaming: boolean;
}

const PROMPT_SUGGESTIONS = [
  { label: 'Monthly Revenue', prompt: 'Show me total revenue and monthly sales performance' },
  { label: 'Top Customers', prompt: 'Who are our top customers by total spent and what is their contact info?' },
  { label: 'Product Catalog', prompt: 'List available products and their pricing categories' },
  { label: 'Order Statuses', prompt: 'Calculate total order count grouped by order status' },
];

export const ChatInput: React.FC<ChatInputProps> = ({ onSend, onCancel, isStreaming }) => {
  const [prompt, setPrompt] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  }, [prompt]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || isStreaming) return;
    onSend(prompt);
    setPrompt('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="sticky bottom-0 z-30 w-full border-t border-white/[0.08] bg-[#070a13]/90 backdrop-blur-xl px-4 py-3 sm:px-6">
      <div className="mx-auto max-w-4xl space-y-2.5">
        {/* Quick Suggestion Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs no-scrollbar">
          <span className="flex items-center gap-1 text-[11px] font-mono text-slate-500 uppercase tracking-wider shrink-0 mr-1">
            <Sparkles className="h-3 w-3 text-cyan-400" />
            Quick:
          </span>
          {PROMPT_SUGGESTIONS.map((item) => (
            <button
              key={item.label}
              onClick={() => onSend(item.prompt)}
              disabled={isStreaming}
              className="shrink-0 rounded-full border border-white/10 bg-slate-900/80 hover:bg-slate-800 hover:border-cyan-500/40 px-3 py-1 text-xs text-slate-300 hover:text-white transition-all disabled:opacity-40"
            >
              {item.label}
            </button>
          ))}
        </div>

        {/* Input Area Form */}
        <form onSubmit={handleSubmit} className="relative flex items-center">
          <div className="relative flex w-full items-end rounded-2xl border border-white/10 bg-slate-900/90 shadow-2xl focus-within:border-cyan-500/60 focus-within:ring-2 focus-within:ring-cyan-500/20 transition-all">
            <textarea
              ref={textareaRef}
              rows={1}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask any question about your database (e.g. 'Show monthly sales trends')..."
              disabled={isStreaming}
              className="w-full resize-none bg-transparent px-4 py-3.5 text-xs sm:text-sm text-white placeholder-slate-500 focus:outline-none disabled:opacity-50 max-h-32"
            />

            <div className="flex items-center gap-2 p-2.5">
              {isStreaming ? (
                <button
                  type="button"
                  onClick={onCancel}
                  className="flex h-9 w-9 items-center justify-center rounded-xl bg-rose-600 hover:bg-rose-500 text-white transition-all shadow-md active:scale-95"
                  title="Stop Stream"
                >
                  <Square className="h-4 w-4" />
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!prompt.trim()}
                  className="flex h-9 items-center gap-1.5 rounded-xl bg-gradient-to-r from-cyan-500 to-indigo-600 px-3 text-xs font-semibold text-white transition-all hover:from-cyan-400 hover:to-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed shadow-[0_0_15px_rgba(6,182,212,0.3)] active:scale-95"
                >
                  <span>Query</span>
                  <CornerDownLeft className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>
        </form>

        <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono">
          <span>Protected with SQL AST Validation, EXPLAIN Cost Gate & PII Redaction</span>
          <span className="hidden sm:inline">Press Enter ↵ to send, Shift+Enter for multiline</span>
        </div>
      </div>
    </div>
  );
};
