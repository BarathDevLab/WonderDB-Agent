import React, { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';
import { DiagramSpec } from '../types';
import { GitFork, Network, Workflow, Copy, Check } from 'lucide-react';

mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  securityLevel: 'loose',
  fontFamily: 'ui-sans-serif, system-ui, sans-serif',
  themeVariables: {
    darkMode: true,
    background: '#1e1f20',
    primaryColor: '#6366f1',
    primaryTextColor: '#f4f4f5',
    primaryBorderColor: '#4f46e5',
    lineColor: '#818cf8',
    secondaryColor: '#a855f7',
    tertiaryColor: '#14b8a6',
  },
});

interface DiagramViewerProps {
  spec: DiagramSpec;
}

export const DiagramViewer: React.FC<DiagramViewerProps> = ({ spec }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svgContent, setSvgContent] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const mermaidCode = spec?.mermaid || '';
  const diagramType = spec?.diagram_type || 'process';

  useEffect(() => {
    if (!mermaidCode.trim()) return;

    let isMounted = true;
    const renderId = `mermaid-${Math.random().toString(36).substring(2, 9)}`;

    mermaid
      .render(renderId, mermaidCode)
      .then(({ svg }) => {
        if (isMounted) {
          setSvgContent(svg);
          setError(null);
        }
      })
      .catch((err) => {
        if (isMounted) {
          console.error('Mermaid render error:', err);
          setError('Failed to render diagram visually.');
        }
      });

    return () => {
      isMounted = false;
      const elem = document.getElementById(renderId);
      if (elem) elem.remove();
    };
  }, [mermaidCode]);

  if (!mermaidCode.trim()) return null;

  const getTitle = () => {
    switch (diagramType) {
      case 'er':
        return 'Entity-Relationship (ER) Schema Diagram';
      case 'decision':
        return 'Decision Tree Process Map';
      case 'process':
      default:
        return 'Process Flow Diagram';
    }
  };

  const getIcon = () => {
    switch (diagramType) {
      case 'er':
        return <Network className="h-4 w-4 text-indigo-400" />;
      case 'decision':
        return <GitFork className="h-4 w-4 text-purple-400" />;
      case 'process':
      default:
        return <Workflow className="h-4 w-4 text-teal-400" />;
    }
  };

  const handleCopyMermaid = () => {
    navigator.clipboard.writeText(mermaidCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="mt-4 mb-2 rounded-2xl border border-zinc-800/50 bg-[#1e1f20] overflow-hidden shadow-md max-w-4xl">
      {/* Diagram Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800/50 bg-[#1e1f20]">
        <div className="flex items-center gap-2">
          {getIcon()}
          <span className="text-xs font-semibold text-zinc-200">{getTitle()}</span>
          <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] font-mono uppercase text-zinc-400">
            Mermaid
          </span>
        </div>
        <button
          onClick={handleCopyMermaid}
          className="flex items-center gap-1 rounded px-2 py-1 text-[11px] font-mono text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition-colors"
          title="Copy Mermaid Code"
        >
          {copied ? (
            <>
              <Check className="h-3 w-3 text-emerald-400" />
              <span className="text-emerald-400">Copied</span>
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" />
              <span>Copy Code</span>
            </>
          )}
        </button>
      </div>

      {/* Diagram Render Body */}
      <div className="p-4 overflow-x-auto flex justify-center items-center min-h-[160px]">
        {error ? (
          <div className="w-full">
            <p className="text-xs text-amber-400 font-mono mb-2">{error}</p>
            <pre className="text-[11px] font-mono text-zinc-400 bg-black/20 p-3 rounded overflow-x-auto">
              {mermaidCode}
            </pre>
          </div>
        ) : svgContent ? (
          <div
            ref={containerRef}
            className="w-full flex justify-center [&>svg]:max-w-full [&>svg]:h-auto [&>svg]:mx-auto"
            dangerouslySetInnerHTML={{ __html: svgContent }}
          />
        ) : (
          <div className="flex items-center gap-2 text-xs text-zinc-500 font-mono">
            <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
            <span>Rendering diagram...</span>
          </div>
        )}
      </div>
    </div>
  );
};
