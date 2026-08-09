import React, { useState, useEffect, useRef } from 'react';
import { Navbar, PRESET_TENANTS } from './components/Navbar';
import { ThoughtTracker } from './components/ThoughtTracker';
import { SqlViewer } from './components/SqlViewer';
import { DataGrid } from './components/DataGrid';
import { ChartViewer } from './components/ChartViewer';
import { SchemaDrawer } from './components/SchemaDrawer';
import { ChatInput } from './components/ChatInput';
import { useAgentStream } from './hooks/useAgentStream';
import { Database, User, Bot, Sparkles, Shield, Cpu, Zap, ArrowUpRight } from 'lucide-react';

export const App: React.FC = () => {
  const [selectedTenant, setSelectedTenant] = useState<string>(PRESET_TENANTS[0].id);
  const [isSchemaOpen, setIsSchemaOpen] = useState(false);
  const { messages, currentMessage, isStreaming, sendPrompt, cancelStream, clearHistory } = useAgentStream();
  const feedEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, currentMessage]);

  const activeTenantName = PRESET_TENANTS.find((t) => t.id === selectedTenant)?.name || 'Tenant Database';

  return (
    <div className="flex min-h-screen flex-col bg-[#060911] text-slate-100 selection:bg-cyan-500/30 selection:text-cyan-200">
      {/* Top Navbar */}
      <Navbar
        selectedTenant={selectedTenant}
        onSelectTenant={setSelectedTenant}
        onToggleSchema={() => setIsSchemaOpen(true)}
        onClearHistory={clearHistory}
        isStreaming={isStreaming}
      />

      {/* Schema Catalog Explorer Drawer */}
      <SchemaDrawer isOpen={isSchemaOpen} onClose={() => setIsSchemaOpen(false)} />

      {/* Main Chat Feed Workspace */}
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-4xl space-y-6">
          {/* Welcome Screen when Empty */}
          {messages.length === 0 && !currentMessage && (
            <div className="my-8 rounded-2xl border border-white/[0.08] bg-gradient-to-b from-[#0e1628]/80 to-[#070a13]/90 p-6 sm:p-10 backdrop-blur-xl shadow-2xl">
              <div className="flex flex-col items-center text-center">
                <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-cyan-500/10 border border-cyan-500/30 shadow-[0_0_25px_rgba(6,182,212,0.25)]">
                  <Database className="h-7 w-7 text-cyan-400" />
                </div>
                <h2 className="font-display text-xl sm:text-2xl font-bold tracking-tight text-white mb-2">
                  Enterprise AI Database Copilot
                </h2>
                <p className="max-w-xl text-xs sm:text-sm text-slate-400 leading-relaxed mb-6">
                  Ask natural language analytical questions against PostgreSQL with dense{' '}
                  <span className="text-cyan-300 font-semibold">pgvector schema RAG</span>, strict{' '}
                  <span className="text-indigo-300 font-semibold">AST security validation</span>, and multi-tenant{' '}
                  <span className="text-emerald-300 font-semibold">Row-Level Security (RLS)</span>.
                </p>

                {/* Architecture Highlights Grid */}
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 w-full text-left mb-6">
                  <div className="rounded-xl border border-white/[0.06] bg-slate-900/50 p-3.5">
                    <div className="flex items-center gap-2 text-xs font-bold text-cyan-300 mb-1">
                      <Cpu className="h-4 w-4" />
                      <span>pgvector RAG</span>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      1536-d dense embeddings match intent with foreign key relational graph traversal.
                    </p>
                  </div>

                  <div className="rounded-xl border border-white/[0.06] bg-slate-900/50 p-3.5">
                    <div className="flex items-center gap-2 text-xs font-bold text-indigo-300 mb-1">
                      <Shield className="h-4 w-4" />
                      <span>AST & Cost Gate</span>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      sqlglot static analysis blocks DDL/DML, and EXPLAIN guards heavy query plans.
                    </p>
                  </div>

                  <div className="rounded-xl border border-white/[0.06] bg-slate-900/50 p-3.5">
                    <div className="flex items-center gap-2 text-xs font-bold text-emerald-300 mb-1">
                      <Zap className="h-4 w-4" />
                      <span>PII Redaction</span>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      Sensitive customer data (emails, SSNs) is masked before streaming.
                    </p>
                  </div>
                </div>

                {/* Example Quick Start Prompts */}
                <div className="w-full text-left">
                  <span className="text-[11px] font-mono uppercase tracking-wider text-slate-400 font-semibold mb-2 block">
                    Select a starter prompt:
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {[
                      'Show me total revenue and monthly sales performance',
                      'Who are our top customers by total spent and what is their contact info?',
                      'List available products and their pricing categories',
                      'Calculate total order count grouped by order status',
                    ].map((samplePrompt) => (
                      <button
                        key={samplePrompt}
                        onClick={() => sendPrompt(samplePrompt, selectedTenant)}
                        className="flex items-center justify-between rounded-xl border border-white/[0.06] bg-slate-900/60 hover:bg-slate-800/80 hover:border-cyan-500/40 p-3 text-xs text-slate-300 hover:text-white transition-all text-left group"
                      >
                        <span className="truncate pr-2">{samplePrompt}</span>
                        <ArrowUpRight className="h-3.5 w-3.5 text-slate-500 group-hover:text-cyan-400 shrink-0" />
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
                /* User Prompt Bubble */
                <div className="flex items-start justify-end gap-3">
                  <div className="max-w-2xl rounded-2xl rounded-tr-sm bg-gradient-to-r from-cyan-600/30 to-indigo-600/30 border border-cyan-500/30 p-4 text-xs sm:text-sm text-white shadow-md">
                    <p className="font-medium leading-relaxed">{msg.prompt}</p>
                    <div className="mt-2 flex items-center justify-end gap-2 text-[10px] font-mono text-cyan-300/80">
                      <span>{activeTenantName}</span>
                      <span>•</span>
                      <span>{msg.timestamp}</span>
                    </div>
                  </div>
                  <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-cyan-950 border border-cyan-500/40 text-cyan-400 shrink-0">
                    <User className="h-4 w-4" />
                  </div>
                </div>
              ) : (
                /* Agent Response Bubble */
                <div className="flex items-start gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-950 border border-indigo-500/40 text-indigo-400 shrink-0 mt-1">
                    <Bot className="h-4 w-4" />
                  </div>
                  <div className="flex-1 overflow-hidden">
                    {/* Pipeline Thought Telemetry */}
                    <ThoughtTracker message={msg} />

                    {/* Synthesized SQL Code Block */}
                    {msg.sqlQuery && (
                      <SqlViewer
                        sql={msg.sqlQuery}
                        strategy={msg.strategy}
                        cost={msg.explainCost}
                        rowCount={msg.rawResults?.length}
                      />
                    )}

                    {/* Summary Text */}
                    {msg.summary && (
                      <div className="my-2 text-xs sm:text-sm text-slate-200 leading-relaxed font-sans bg-slate-900/40 border border-white/[0.04] rounded-xl p-3.5">
                        <p>{msg.summary}</p>
                      </div>
                    )}

                    {/* Interactive Visuals (Chart.js) */}
                    {msg.chartSpec && msg.chartSpec.type !== 'table' && (
                      <ChartViewer spec={msg.chartSpec} />
                    )}

                    {/* Interactive Tabular Data Grid */}
                    {msg.rawResults && msg.rawResults.length > 0 && (
                      <DataGrid data={msg.rawResults} />
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}

          {/* Active Streaming Message */}
          {currentMessage && (
            <div className="space-y-3 animate-fadeIn">
              <div className="flex items-start gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-950 border border-indigo-500/40 text-indigo-400 shrink-0 mt-1">
                  <Bot className="h-4 w-4 animate-pulse" />
                </div>
                <div className="flex-1 overflow-hidden">
                  {/* Live Thought Tracker */}
                  <ThoughtTracker message={currentMessage} />

                  {/* Live SQL as it becomes ready */}
                  {currentMessage.sqlQuery && (
                    <SqlViewer
                      sql={currentMessage.sqlQuery}
                      strategy={currentMessage.strategy}
                      cost={currentMessage.explainCost}
                      rowCount={currentMessage.rawResults?.length}
                    />
                  )}

                  {/* Live Chart preview */}
                  {currentMessage.chartSpec && currentMessage.chartSpec.type !== 'table' && (
                    <ChartViewer spec={currentMessage.chartSpec} />
                  )}

                  {/* Live Data Grid */}
                  {currentMessage.rawResults && currentMessage.rawResults.length > 0 && (
                    <DataGrid data={currentMessage.rawResults} />
                  )}
                </div>
              </div>
            </div>
          )}

          <div ref={feedEndRef} />
        </div>
      </main>

      {/* Fixed Bottom Input Bar */}
      <ChatInput
        onSend={(prompt) => sendPrompt(prompt, selectedTenant)}
        onCancel={cancelStream}
        isStreaming={isStreaming}
      />
    </div>
  );
};
