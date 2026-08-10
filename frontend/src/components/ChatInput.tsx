import React, { useState, useRef, useEffect } from 'react';
import { ArrowUp, Square, HelpCircle, Mic, MicOff } from 'lucide-react';

interface ChatInputProps {
  onSend: (prompt: string) => void;
  onCancel: () => void;
  isStreaming: boolean;
}

export const PROMPT_SUGGESTIONS = [
  { label: 'Monthly Revenue', prompt: 'Show me total revenue and monthly sales performance' },
  { label: 'Top Customers', prompt: 'Who are our top customers by total spent and what is their contact info?' },
  { label: 'Product Catalog', prompt: 'List available products and their pricing categories' },
  { label: 'Order Statuses', prompt: 'Calculate total order count grouped by order status' },
];

export const ChatInput: React.FC<ChatInputProps> = ({
  onSend,
  onCancel,
  isStreaming,
}) => {
  const [prompt, setPrompt] = useState('');
  const [isListening, setIsListening] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const recognitionRef = useRef<any>(null);

  const toggleListening = () => {
    if (isListening) {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
      setIsListening(false);
      return;
    }

    if (typeof window !== 'undefined') {
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (SpeechRecognition) {
        try {
          const recognition = new SpeechRecognition();
          // Change continuous to false. Some browsers/OS combinations kill continuous immediately.
          recognition.continuous = false;
          recognition.interimResults = false;

          recognition.onstart = () => {
            setIsListening(true);
          };

          recognition.onresult = (event: any) => {
            const transcript = event.results[event.results.length - 1][0].transcript;
            setPrompt((prev) => prev + (prev && !prev.endsWith(' ') ? ' ' : '') + transcript);
          };

          recognition.onerror = (event: any) => {
            console.error("Speech recognition error:", event.error);
            if (event.error !== 'no-speech') {
              alert("Microphone error: " + event.error + ". Make sure you are on localhost or HTTPS, and have granted permissions.");
            }
            setIsListening(false);
          };

          recognition.onend = () => {
            setIsListening(false);
          };

          recognitionRef.current = recognition;
          recognition.start();
        } catch (e) {
          console.error("Failed to start speech recognition:", e);
          setIsListening(false);
        }
      } else {
        alert("Speech recognition is not supported in this browser.");
      }
    }
  };

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [prompt]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isListening) recognitionRef.current?.stop();
    if (!prompt.trim() || isStreaming) return;
    onSend(prompt.trim());
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
    <div className="sticky bottom-0 z-20 w-full bg-gradient-to-t from-[#090a0d] via-[#090a0d]/95 to-transparent pt-3 pb-4 px-3 sm:px-6">
      <div className="mx-auto max-w-3xl space-y-2.5">
        {/* Suggestion Chips */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs no-scrollbar">
          <span className="text-[11px] font-mono text-zinc-500 uppercase tracking-wider font-medium shrink-0 mr-1">
            Presets:
          </span>
          {PROMPT_SUGGESTIONS.map((item) => (
            <button
              key={item.label}
              onClick={() => onSend(item.prompt)}
              disabled={isStreaming}
              className="shrink-0 rounded-md border border-zinc-800 bg-zinc-900/80 hover:bg-zinc-800 hover:border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 hover:text-zinc-100 transition-colors disabled:opacity-40"
            >
              {item.label}
            </button>
          ))}
        </div>

        {/* Input Box */}
        <form onSubmit={handleSubmit} className="relative">
          <div className="relative flex flex-col rounded-2xl border border-zinc-800 bg-[#121316] shadow-xl focus-within:border-zinc-600 focus-within:ring-1 focus-within:ring-zinc-600 transition-all">
            <textarea
              ref={textareaRef}
              rows={1}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask anything about PostgreSQL schema or business metrics..."
              disabled={isStreaming}
              className="w-full resize-none bg-transparent px-4 sm:px-5 pt-3.5 pb-2 text-xs sm:text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none disabled:opacity-50 max-h-40 leading-relaxed"
            />

            {/* Bottom Actions Row inside Prompt Box */}
            <div className="flex items-center justify-between px-3 sm:px-4 pb-2.5 pt-1">
              <div className="flex items-center gap-1.5 text-[10px] font-mono text-zinc-500">
                <span>pgvector RAG • AST Cost Gate</span>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono text-zinc-500 hidden md:inline">
                  Enter ↵
                </span>

                <button
                  type="button"
                  onClick={toggleListening}
                  className={`flex h-7 w-7 items-center justify-center rounded-md transition-colors ${
                    isListening
                      ? 'bg-rose-500/20 text-rose-500 animate-pulse'
                      : 'bg-zinc-800/50 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-300'
                  }`}
                  title={isListening ? "Stop listening" : "Start voice input"}
                >
                  {isListening ? <Mic className="h-3.5 w-3.5" /> : <MicOff className="h-3.5 w-3.5" />}
                </button>

                {isStreaming ? (
                  <button
                    type="button"
                    onClick={onCancel}
                    className="flex h-7 w-7 items-center justify-center rounded-md bg-rose-600 hover:bg-rose-500 text-white transition-colors"
                    title="Stop generation"
                  >
                    <Square className="h-3 w-3" />
                  </button>
                ) : (
                  <button
                    type="submit"
                    disabled={!prompt.trim()}
                    className="flex h-7 w-7 items-center justify-center rounded-md bg-zinc-100 hover:bg-white text-zinc-950 font-bold transition-all disabled:opacity-30 disabled:cursor-not-allowed active:scale-95"
                    title="Execute query"
                  >
                    <ArrowUp className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>
          </div>
        </form>

        {/* Footer Microcopy */}
        <div className="flex items-center justify-between text-[10px] text-zinc-500 font-mono px-1">
          <span>Protected with pgvector RAG, AST static analysis & RLS isolation</span>
          <span className="hidden sm:inline">PostgreSQL Copilot</span>
        </div>
      </div>
    </div>
  );
};
