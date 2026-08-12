import React, { useState, useRef, useEffect } from 'react';
import { ArrowUp, Square, HelpCircle, Mic, MicOff } from 'lucide-react';

interface ChatInputProps {
  onSend: (prompt: string) => void;
  onCancel: () => void;
  isStreaming: boolean;
  className?: string;
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
  className = '',
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
    <div className={`sticky bottom-0 z-20 w-full bg-[#131314] pt-2 pb-6 px-3 sm:px-6 ${className}`}>
      <div className="mx-auto max-w-3xl space-y-3">
        {/* Input Box */}
        <form onSubmit={handleSubmit} className="relative">
          <div className="relative flex items-center rounded-full bg-[#1e1f20] px-3 py-1.5 focus-within:ring-1 focus-within:ring-zinc-600 transition-all">
            {/* Textarea */}
            <textarea
              ref={textareaRef}
              rows={1}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask Database Agent..."
              disabled={isStreaming}
              className="flex-1 resize-none bg-transparent px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none disabled:opacity-50 max-h-32 leading-relaxed"
            />

            {/* Right Actions */}
            <div className="flex items-center gap-1 shrink-0 px-1">
              <button
                type="button"
                onClick={toggleListening}
                className={`flex h-9 w-9 items-center justify-center rounded-full transition-colors ${
                  isListening
                    ? 'bg-rose-500/20 text-rose-500 animate-pulse'
                    : 'text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200'
                }`}
                title={isListening ? "Stop listening" : "Start voice input"}
              >
                {isListening ? <Mic className="h-4 w-4" /> : <MicOff className="h-4 w-4" />}
              </button>

              {isStreaming ? (
                <button
                  type="button"
                  onClick={onCancel}
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-zinc-200 hover:bg-white text-zinc-900 transition-colors ml-1"
                  title="Stop generation"
                >
                  <Square className="h-3 w-3 fill-current" />
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!prompt.trim()}
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-500/10 border border-emerald-500/20 hover:bg-emerald-500/20 text-emerald-400 transition-all ml-1 active:scale-95 disabled:border-transparent disabled:bg-zinc-800 disabled:text-zinc-500 disabled:cursor-not-allowed"
                  title="Send message"
                >
                  <ArrowUp className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>
        </form>

        {/* Footer Microcopy */}
        <div className="mt-2 text-center text-[10px] text-zinc-500">
          Database agent may display inaccurate info, including about people, so double-check its responses.
        </div>
      </div>
    </div>
  );
};
