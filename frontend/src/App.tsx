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
import { useAgentStream } from './hooks/useAgentStream';
import {
  Database,
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
    <div className="flex h-screen w-screen overflow-hidden bg-[#090a0d] text-zinc-100 selection:bg-zinc-700 selection:text-white">
      {/* Left Sidebar */}
      <Sidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={switchSession}
        onNewSession={() => createNewSession(selectedTenant)}
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
              <div className="my-6 rounded-2xl border border-zinc-800 bg-[#111216] p-6 sm:p-8 shadow-lg animate-fadeIn">
                <div className="flex flex-col items-center text-center">
                  <div className="mb-3.5 flex h-11 w-11 items-center justify-center rounded-xl bg-zinc-800 border border-zinc-700 text-zinc-200">
                    <Database className="h-5 w-5" />
                  </div>
                  <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-zinc-100 mb-1.5">
                    PostgreSQL AI Database Copilot
                  </h2>
                  <p className="max-w-lg text-xs sm:text-sm text-zinc-400 leading-relaxed mb-6">
                    Query relational schemas in natural language with pgvector semantic catalog matching, AST safety gates, and multi-tenant RLS isolation.
                  </p>

                  {/* Architecture Feature Cards */}
                  <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3 w-full text-left mb-6">
                    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3.5 hover:border-zinc-700 transition-colors">
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-zinc-200 mb-1">
                        <Server className="h-3.5 w-3.5 text-zinc-400" />
                        <span>pgvector RAG</span>
                      </div>
                      <p className="text-[11px] text-zinc-400 leading-relaxed">
                        1536-d dense embeddings match schema tables, columns, and foreign key relations.
                      </p>
                    </div>

                    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3.5 hover:border-zinc-700 transition-colors">
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-zinc-200 mb-1">
                        <ShieldCheck className="h-3.5 w-3.5 text-zinc-400" />
                        <span>AST & Cost Gate</span>
                      </div>
                      <p className="text-[11px] text-zinc-400 leading-relaxed">
                        sqlglot static analysis guards against DDL/DML, while EXPLAIN validates query plan cost.
                      </p>
                    </div>

                    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3.5 hover:border-zinc-700 transition-colors">
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-zinc-200 mb-1">
                        <BarChart3 className="h-3.5 w-3.5 text-zinc-400" />
                        <span>PII & Visuals</span>
                      </div>
                      <p className="text-[11px] text-zinc-400 leading-relaxed">
                        Automated PII data masking with interactive Chart.js visualization generation.
                      </p>
                    </div>
                  </div>

                  {/* Quick Starter Prompts */}
                  <div className="w-full text-left">
                    <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-500 font-semibold mb-2 block">
                      Starter Questions:
                    </span>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {[
                        {
                          icon: TrendingUp,
                          title: 'Monthly Revenue',
                          prompt: 'Show me total revenue and monthly sales performance',
                        },
                        {
                          icon: User,
                          title: 'Top Customers',
                          prompt:
                            'Who are our top customers by total spent and what is their contact info?',
                        },
                        {
                          icon: FileSpreadsheet,
                          title: 'Product Catalog',
                          prompt: 'List available products and their pricing categories',
                        },
                        {
                          icon: Database,
                          title: 'Order Statuses',
                          prompt: 'Calculate total order count grouped by order status',
                        },
                      ].map((item) => (
                        <button
                          key={item.title}
                          onClick={() => sendPrompt(item.prompt, selectedTenant)}
                          className="flex items-center justify-between rounded-xl border border-zinc-800 bg-zinc-900/60 hover:bg-zinc-800 hover:border-zinc-700 p-3 text-xs text-zinc-300 hover:text-zinc-100 transition-colors text-left group"
                        >
                          <div className="flex items-center gap-2 truncate pr-2">
                            <item.icon className="h-3.5 w-3.5 text-zinc-400 shrink-0" />
                            <span className="truncate">{item.prompt}</span>
                          </div>
                          <ArrowUpRight className="h-3.5 w-3.5 text-zinc-500 group-hover:text-zinc-300 shrink-0" />
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Historical Messages Feed */}
            {messages.map((msg) => (
              <div key={msg.id} className="space-y-3 animate-fadeIn">
                {msg.sender === 'user' ? (
                  /* User Message */
                  <div className="flex items-start justify-end gap-2.5">
                    <div className="max-w-2xl rounded-2xl rounded-tr-sm bg-[#1a1b22] border border-zinc-700/70 p-3.5 text-xs sm:text-sm text-zinc-100 shadow-sm">
                      <p className="leading-relaxed">{msg.prompt}</p>
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
                  <div className="flex items-start gap-2.5">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-300 shrink-0 mt-0.5">
                      <Terminal className="h-3.5 w-3.5" />
                    </div>
                    <div className="flex-1 overflow-hidden space-y-2">
                      {/* 1. Sleek Claude Thinking bar */}
                      <ThoughtTracker message={msg} />

                      {/* Tool Calls Badge */}
                      {msg.toolCalls && msg.toolCalls.length > 0 && (
                        <ToolCallBadge calls={msg.toolCalls} />
                      )}

                      {/* 3. Mermaid Diagrams (ER / Process / Decision) — shown BEFORE AI Insight */}
                      {msg.diagramSpec && msg.diagramSpec.length > 0 && (
                        msg.diagramSpec.map((spec, idx) => (
                          <DiagramViewer key={idx} spec={spec} />
                        ))
                      )}

                      {/* 4. AI Insight — shown AFTER diagrams so it explains everything above */}
                      {msg.summary && (
                        <div className="text-xs sm:text-sm text-zinc-200 leading-relaxed font-sans bg-[#121316] border border-zinc-800 rounded-xl overflow-hidden">
                          {/* Label bar */}
                          <div className="flex items-center gap-2 px-3.5 py-2 border-b border-zinc-800 bg-[#0f1013]">
                            <TrendingUp className="h-3.5 w-3.5 text-indigo-400" />
                            <span className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wide">AI Insight</span>
                          </div>
                          <div className="px-3.5 py-3">
                            <p className="whitespace-pre-wrap">{msg.summary}</p>

                            {/* Action Toolbar */}
                            <div className="mt-2.5 pt-2 border-t border-zinc-800 flex items-center justify-between text-xs text-zinc-400">
                              <div className="flex items-center gap-1.5">
                                <button
                                  onClick={() => handleCopySummary(msg.id, msg.summary || '')}
                                  className="flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-zinc-800 hover:text-zinc-200 transition-colors text-[11px] font-mono"
                                  title="Copy answer"
                                >
                                  {copiedMsgId === msg.id ? (
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

                                {msg.sqlQuery && (
                                  <button
                                    onClick={() => toggleInlineSql(msg.id)}
                                    className="flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-zinc-800 hover:text-zinc-200 transition-colors text-[11px] font-mono text-zinc-400"
                                  >
                                    <Code2 className="h-3 w-3" />
                                    <span>{visibleSqlMsgIds[msg.id] ? 'Hide SQL' : 'View SQL'}</span>
                                  </button>
                                )}
                              </div>

                              <span className="text-[10px] font-mono text-zinc-500">
                                RLS Enforced
                              </span>
                            </div>

                            {/* Inline SQL Viewer */}
                            {visibleSqlMsgIds[msg.id] && msg.sqlQuery && (
                              <div className="mt-2.5 rounded border border-zinc-800 bg-[#07080a] p-3 overflow-x-auto">
                                <pre className="font-mono text-xs text-zinc-300 leading-relaxed select-all">
                                  <code>{msg.sqlQuery}</code>
                                </pre>
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      {/* 5. Table (Data Grid) */}
                      {msg.rawResults && msg.rawResults.length > 0 && (
                        <DataGrid data={msg.rawResults} />
                      )}

                      {/* 6. Chart (Chart.js Visualization) */}
                      {msg.chartSpec && msg.chartSpec.type !== 'table' && (
                        <ChartViewer spec={msg.chartSpec} />
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}

            {/* Active Streaming Message */}
            {currentMessage && (
              <div className="space-y-3 animate-fadeIn">
                <div className="flex items-start gap-2.5">
                  <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-300 shrink-0 mt-0.5">
                    <Terminal className="h-3.5 w-3.5 animate-pulse" />
                  </div>
                  <div className="flex-1 overflow-hidden space-y-2">
                    {/* 1. Sleek Claude Thinking bar */}
                    <ThoughtTracker message={currentMessage} />

                    {/* Tool Calls Badge */}
                    {currentMessage.toolCalls && currentMessage.toolCalls.length > 0 && (
                      <ToolCallBadge calls={currentMessage.toolCalls} />
                    )}

                    {/* 2. Mermaid Diagrams — shown first so AI Insight explains them */}
                    {currentMessage.diagramSpec && currentMessage.diagramSpec.length > 0 && (
                      currentMessage.diagramSpec.map((spec, idx) => (
                        <DiagramViewer key={idx} spec={spec} />
                      ))
                    )}

                    {/* 3. AI Insight — shown AFTER diagrams */}
                    {currentMessage.summary && (
                      <div className="text-xs sm:text-sm text-zinc-200 leading-relaxed font-sans bg-[#121316] border border-zinc-800 rounded-xl overflow-hidden">
                        <div className="flex items-center gap-2 px-3.5 py-2 border-b border-zinc-800 bg-[#0f1013]">
                          <TrendingUp className="h-3.5 w-3.5 text-indigo-400" />
                          <span className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wide">AI Insight</span>
                        </div>
                        <div className="px-3.5 py-3">
                          <p className="whitespace-pre-wrap">{currentMessage.summary}</p>
                        </div>
                      </div>
                    )}

                    {/* 4. Table (Data Grid) */}
                    {currentMessage.rawResults && currentMessage.rawResults.length > 0 && (
                      <DataGrid data={currentMessage.rawResults} />
                    )}

                    {/* 5. Chart (Chart.js Visualization) */}
                    {currentMessage.chartSpec && currentMessage.chartSpec.type !== 'table' && (
                      <ChartViewer spec={currentMessage.chartSpec} />
                    )}
                  </div>
                </div>
              </div>
            )}

            <div ref={feedEndRef} />
          </div>
        </main>

        {/* Input Bar */}
        <ChatInput
          onSend={(prompt) => sendPrompt(prompt, selectedTenant)}
          onCancel={cancelStream}
          isStreaming={isStreaming}
        />
      </div>
    </div>
  );
};
