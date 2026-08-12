import React, { useState, useEffect, useRef } from 'react';
import { Sidebar, PRESET_TENANTS } from './components/Sidebar';
import { Navbar } from './components/Navbar';
import { ThoughtTracker } from './components/ThoughtTracker';
import { DataGrid } from './components/DataGrid';
import { ChartViewer } from './components/ChartViewer';
import { DiagramViewer } from './components/DiagramViewer';
import { ToolCallBadge } from './components/ToolCallBadge';
import { SchemaDrawer } from './components/SchemaDrawer';
import { ChatInput } from './components/ChatInput';
import { CodeBlock } from './components/CodeBlock';
import { useAgentStream } from './hooks/useAgentStream';
import ReactMarkdown from 'react-markdown';
import {
  Database,
  Sparkles,
  User,
  ShieldCheck,
  Server,
  BarChart3,
  ArrowUpRight,
  Copy,
  Check,
  Code2,
  FileSpreadsheet,
  TrendingUp,
  Terminal,
} from 'lucide-react';

export const App: React.FC = () => {
  const [selectedTenant, setSelectedTenant] = useState<string>(PRESET_TENANTS[0].id);
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(() => {
    return typeof window !== 'undefined' ? window.innerWidth >= 1024 : true;
  });
  const [isSchemaOpen, setIsSchemaOpen] = useState(false);
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);
  const [visibleSqlMsgIds, setVisibleSqlMsgIds] = useState<Record<string, boolean>>({});

  const {
    sessions,
    activeSessionId,
    activeSession,
    messages,
    currentMessage,
    isStreaming,
    sendPrompt,
    cancelStream,
    createNewSession,
    switchSession,
    deleteSession,
    renameSession,
    clearCurrentHistory,
  } = useAgentStream(selectedTenant);

  const feedEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, currentMessage]);

  const activeTenantObj =
    PRESET_TENANTS.find((t) => t.id === selectedTenant) || PRESET_TENANTS[0];

  const handleCopySummary = (msgId: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedMsgId(msgId);
    setTimeout(() => setCopiedMsgId(null), 2000);
  };

  const toggleInlineSql = (msgId: string) => {
    setVisibleSqlMsgIds((prev) => ({ ...prev, [msgId]: !prev[msgId] }));
  };

  const handleExportSession = () => {
    if (!messages || messages.length === 0) return;

    let transcript = `# PostgreSQL AI Studio Session: ${activeSession?.title || 'Query Session'}\n`;
    transcript += `**Date:** ${new Date().toLocaleString()}\n`;
    transcript += `**Tenant Scope:** ${activeTenantObj.name} (RLS Active)\n\n---\n\n`;

    messages.forEach((m) => {
      if (m.sender === 'user') {
        transcript += `### User Query [${m.timestamp}]\n> ${m.prompt}\n\n`;
      } else {
        transcript += `### AI Database Copilot Response [${m.timestamp}]\n`;
        if (m.summary) {
          transcript += `${m.summary}\n\n`;
        }
        if (m.sqlQuery) {
          transcript += `\`\`\`sql\n${m.sqlQuery}\n\`\`\`\n\n`;
        }
        if (m.rawResults && m.rawResults.length > 0) {
          transcript += `*Returned ${m.rawResults.length} records.*\n\n`;
        }
      }
      transcript += `---\n\n`;
    });

    const blob = new Blob([transcript], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ai_db_session_${Date.now()}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#131314] text-zinc-100 selection:bg-zinc-700 selection:text-white font-sans">
      {/* Left Sidebar */}
      <Sidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={switchSession}
        onNewSession={() => createNewSession()}
        onDeleteSession={deleteSession}
        onRenameSession={renameSession}
        selectedTenant={selectedTenant}
        onSelectTenant={setSelectedTenant}
        onOpenSchema={() => setIsSchemaOpen(true)}
        isStreaming={isStreaming}
        isOpen={isSidebarOpen}
        onToggleOpen={() => setIsSidebarOpen((prev) => !prev)}
      />

      {/* Main Viewport */}
      <div
        className={`flex flex-1 flex-col h-full overflow-hidden transition-all duration-200 ${
          isSidebarOpen ? 'lg:pl-72' : 'lg:pl-16'
        }`}
      >
        {/* Top Navbar */}
        <Navbar
          sidebarOpen={isSidebarOpen}
          onToggleSidebar={() => setIsSidebarOpen((prev) => !prev)}
          selectedTenant={selectedTenant}
          onSelectTenant={setSelectedTenant}
          onToggleSchema={() => setIsSchemaOpen(true)}
          onClearHistory={clearCurrentHistory}
          onExportSession={messages.length > 0 ? handleExportSession : undefined}
          sessionTitle={activeSession?.title}
          isStreaming={isStreaming}
        />

        {/* Schema Catalog Explorer Drawer */}
        <SchemaDrawer isOpen={isSchemaOpen} onClose={() => setIsSchemaOpen(false)} />

        {/* Central Canvas */}
        <main className="flex-1 overflow-y-auto px-3 sm:px-6 py-6">
          <div className="mx-auto max-w-3xl space-y-5">
            {/* Welcome Screen when Session is Empty */}
            {messages.length === 0 && !currentMessage && (
              <div className="flex flex-col items-center justify-center min-h-[60vh] w-full max-w-3xl mx-auto animate-fadeIn">
                <div className="flex items-center gap-3 mb-8">
                  <img src="/logo.png" alt="WonderDB Logo" className="h-10 w-10 object-contain" />
                  <h1 className="text-4xl font-serif text-zinc-100 tracking-tight">
                    WonderDB Agent
                  </h1>
                </div>
                <ChatInput 
                  onSend={(prompt) => sendPrompt(prompt, selectedTenant)} 
                  onCancel={cancelStream}
                  isStreaming={isStreaming} 
                  className="bg-transparent"
                />
              </div>
            )}

            {/* Historical Messages Feed */}
            {messages.map((msg) => (
              <div key={msg.id} className="space-y-3 animate-fadeIn">
                {msg.sender === 'user' ? (
                  /* User Message */
                  <div className="flex items-start justify-end gap-2.5">
                    <div className="max-w-2xl rounded-2xl rounded-tr-sm bg-[#1e1f20] p-4 text-[15px] text-zinc-100 shadow-sm">
                      <p className="leading-relaxed whitespace-pre-wrap">{msg.prompt}</p>
                      <div className="mt-1.5 flex items-center justify-end gap-2 text-[10px] font-mono text-zinc-400">
                        <span>{activeTenantObj.name}</span>
                        <span>•</span>
                        <span>{msg.timestamp}</span>
                      </div>
                    </div>
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-300 shrink-0 mt-0.5">
                      <User className="h-3.5 w-3.5" />
                    </div>
                  </div>
                ) : (
                  /* Assistant Message: Ordered exactly as Thinking -> Summary -> Table -> Chart */
                  <div className="flex items-start gap-4">
                    <div className="flex-1 overflow-hidden space-y-4">
                      {/* 1. Sleek Claude Thinking bar */}
                      <ThoughtTracker message={msg} />

                      {/* 3. Mermaid Diagrams (ER / Process / Decision) — shown BEFORE AI Insight */}
                      {msg.diagramSpec && msg.diagramSpec.length > 0 && (
                        msg.diagramSpec.map((spec, idx) => (
                          <DiagramViewer key={idx} spec={spec} />
                        ))
                      )}

                      {/* 4. Table (Data Grid) */}
                      {msg.rawResults && msg.rawResults.length > 0 && (
                        <DataGrid data={msg.rawResults} />
                      )}

                      {/* 5. Chart (Chart.js Visualization) */}
                      {msg.chartSpec && msg.chartSpec.type !== 'table' && (
                        <ChartViewer spec={msg.chartSpec} />
                      )}

                      {/* 6. AI Insight — shown AFTER diagrams, table, and chart so it explains everything above */}
                      {msg.summary && (
                        <div className="text-[15px] text-zinc-200 leading-relaxed font-sans">
                          <div className="prose prose-sm prose-invert max-w-none prose-p:leading-relaxed prose-pre:bg-[#1e1f20] prose-pre:border prose-pre:border-zinc-800">
                            <ReactMarkdown>{msg.summary}</ReactMarkdown>
                          </div>

                          {/* Action Toolbar */}
                          <div className="mt-2 flex items-center justify-start gap-2 text-xs text-zinc-400">
                            <button
                              onClick={() => handleCopySummary(msg.id, msg.summary || '')}
                              className="p-1.5 rounded-full hover:bg-zinc-800/50 hover:text-zinc-200 transition-colors"
                              title="Copy answer"
                            >
                              {copiedMsgId === msg.id ? (
                                <Check className="h-4 w-4 text-emerald-400" />
                              ) : (
                                <Copy className="h-4 w-4" />
                              )}
                            </button>
                          </div>
                        </div>
                      )}

                      {/* Code Block for SQL */}
                      {msg.sqlQuery && (
                        <CodeBlock code={msg.sqlQuery} language="SQL" />
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}

            {/* Active Streaming Message */}
            {currentMessage && (
              <div className="space-y-3 animate-fadeIn">
                <div className="flex items-start gap-4">
                  <div className="flex-1 overflow-hidden space-y-4">
                    {/* 1. Sleek Claude Thinking bar */}
                    <ThoughtTracker message={currentMessage} />

                    {/* 2. Mermaid Diagrams — shown first so AI Insight explains them */}
                    {currentMessage.diagramSpec && currentMessage.diagramSpec.length > 0 && (
                      currentMessage.diagramSpec.map((spec, idx) => (
                        <DiagramViewer key={idx} spec={spec} />
                      ))
                    )}

                    {/* 3. Table (Data Grid) */}
                    {currentMessage.rawResults && currentMessage.rawResults.length > 0 && (
                      <DataGrid data={currentMessage.rawResults} />
                    )}

                    {/* 4. Chart (Chart.js Visualization) */}
                    {currentMessage.chartSpec && currentMessage.chartSpec.type !== 'table' && (
                      <ChartViewer spec={currentMessage.chartSpec} />
                    )}

                    {/* 5. AI Insight — shown AFTER diagrams, table, and chart */}
                    {currentMessage.summary && (
                      <div className="text-[15px] text-zinc-200 leading-relaxed font-sans">
                        <div className="prose prose-sm prose-invert max-w-none prose-p:leading-relaxed prose-pre:bg-[#1e1f20] prose-pre:border prose-pre:border-zinc-800">
                          <ReactMarkdown>{currentMessage.summary}</ReactMarkdown>
                        </div>
                      </div>
                    )}

                    {/* Code Block for SQL */}
                    {currentMessage.sqlQuery && (
                      <CodeBlock code={currentMessage.sqlQuery} language="SQL" />
                    )}
                  </div>
                </div>
              </div>
            )}

            <div ref={feedEndRef} />
          </div>
        </main>

        {/* Input Bar */}
        {(messages.length > 0 || currentMessage) && (
          <ChatInput
            onSend={(prompt) => sendPrompt(prompt, selectedTenant)}
            onCancel={cancelStream}
            isStreaming={isStreaming}
            className="sticky bottom-0 z-20 bg-[#131314] pt-2 pb-6 px-3 sm:px-6"
          />
        )}
      </div>
    </div>
  );
};
