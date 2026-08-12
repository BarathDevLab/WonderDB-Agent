import React, { useState } from 'react';
import { Download, Copy, Check } from 'lucide-react';

interface CodeBlockProps {
  code: string;
  language?: string;
}

export const CodeBlock: React.FC<CodeBlockProps> = ({ code, language = 'SQL' }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([code], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `query_${Date.now()}.sql`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Simple SQL syntax highlighting matching the screenshot
  const highlightCode = (text: string) => {
    if (!text) return null;
    
    // Split into tokens (simplified regex for basic SQL highlighting)
    const tokenRegex = /(\b(?:WITH|AS|SELECT|FROM|WHERE|GROUP BY|ORDER BY|PARTITION BY|OVER|LEAD|LAG|JOIN|INNER JOIN|LEFT JOIN|ON|AND|OR|NOT|IN|IS NULL|IS NOT NULL)\b)|(\b(?:COUNT|SUM|MAX|MIN|AVG|COALESCE)\b)|('[^']*')|([0-9]+)|(--.*$)|([a-zA-Z_][a-zA-Z0-9_]*)/gm;

    const parts = [];
    let match;
    let lastIndex = 0;

    while ((match = tokenRegex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push({ type: 'text', content: text.substring(lastIndex, match.index) });
      }
      
      if (match[1]) {
        parts.push({ type: 'keyword', content: match[1] }); // purple/blue
      } else if (match[2]) {
        parts.push({ type: 'function', content: match[2] }); // blue
      } else if (match[3]) {
        parts.push({ type: 'string', content: match[3] }); // green
      } else if (match[4]) {
        parts.push({ type: 'number', content: match[4] }); // orange
      } else if (match[5]) {
        parts.push({ type: 'comment', content: match[5] }); // gray
      } else if (match[6]) {
        parts.push({ type: 'identifier', content: match[6] }); // light blue/white
      }

      lastIndex = tokenRegex.lastIndex;
    }
    
    if (lastIndex < text.length) {
      parts.push({ type: 'text', content: text.substring(lastIndex) });
    }

    return parts.map((part, i) => {
      switch (part.type) {
        case 'keyword':
          return <span key={i} className="text-[#c678dd]">{part.content}</span>;
        case 'function':
          return <span key={i} className="text-[#61afef]">{part.content}</span>;
        case 'string':
          return <span key={i} className="text-[#98c379]">{part.content}</span>;
        case 'number':
          return <span key={i} className="text-[#d19a66]">{part.content}</span>;
        case 'comment':
          return <span key={i} className="text-[#5c6370] italic">{part.content}</span>;
        case 'identifier':
          return <span key={i} className="text-[#abb2bf]">{part.content}</span>;
        default:
          return <span key={i} className="text-[#abb2bf]">{part.content}</span>;
      }
    });
  };

  return (
    <div className="mt-4 mb-2 rounded-2xl overflow-hidden bg-[#1e1f20] border border-zinc-800/50 shadow-md max-w-4xl font-sans">
      <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800/50 bg-[#1e1f20]">
        <div className="text-[13px] font-semibold text-zinc-300">
          {language}
        </div>
        <div className="flex items-center gap-1.5">
          <button 
            onClick={handleDownload}
            className="p-1.5 rounded-full hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
            title="Download code"
          >
            <Download className="h-4 w-4" />
          </button>
          <button 
            onClick={handleCopy}
            className="p-1.5 rounded-full hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
            title="Copy code"
          >
            {copied ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
          </button>
        </div>
      </div>
      <div className="p-4 overflow-x-auto">
        <pre className="font-mono text-[13px] leading-relaxed whitespace-pre-wrap select-all">
          <code>{highlightCode(code)}</code>
        </pre>
      </div>
    </div>
  );
};
