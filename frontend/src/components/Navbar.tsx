import React, { useEffect, useState } from 'react';
import { Database, Activity, Shield, Layers, Trash2, Cpu, CheckCircle, AlertCircle } from 'lucide-react';
import { Tenant } from '../types';

interface NavbarProps {
  selectedTenant: string;
  onSelectTenant: (id: string) => void;
  onToggleSchema: () => void;
  onClearHistory: () => void;
  isStreaming: boolean;
}

export const PRESET_TENANTS: Tenant[] = [
  {
    id: 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    name: 'Acme Corporation',
    tier: 'Enterprise Production',
    recordCount: 8,
  },
  {
    id: 'b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22',
    name: 'Globex Industries',
    tier: 'Multi-Tenant Sandbox',
    recordCount: 3,
  },
];

export const Navbar: React.FC<NavbarProps> = ({
  selectedTenant,
  onSelectTenant,
  onToggleSchema,
  onClearHistory,
  isStreaming,
}) => {
  const [isBackendHealthy, setIsBackendHealthy] = useState<boolean | null>(null);

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch('/api/v1/health');
        setIsBackendHealthy(res.ok);
      } catch {
        setIsBackendHealthy(false);
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  const activeTenantObj = PRESET_TENANTS.find((t) => t.id === selectedTenant) || {
    id: selectedTenant,
    name: 'Custom Tenant Scope',
    tier: 'Dynamic Workspace',
    recordCount: 0,
  };

  return (
    <header className="sticky top-0 z-40 w-full border-b border-white/[0.08] bg-[#070a13]/85 backdrop-blur-xl px-4 py-3 sm:px-6">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
        {/* Brand & Identity */}
        <div className="flex items-center gap-3">
          <div className="relative flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500/20 via-indigo-500/20 to-purple-500/20 border border-cyan-500/40 shadow-[0_0_15px_rgba(6,182,212,0.3)]">
            <Database className="h-5 w-5 text-cyan-400 animate-pulse" />
            <span className="absolute -bottom-0.5 -right-0.5 flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-cyan-500"></span>
            </span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-display text-base sm:text-lg font-bold tracking-tight text-white flex items-center gap-1.5">
                DATABASE<span className="text-cyan-400">AGENT</span>
              </h1>
              <span className="inline-flex items-center gap-1 rounded-full border border-cyan-500/30 bg-cyan-950/50 px-2 py-0.5 text-[10px] font-mono font-medium text-cyan-300">
                <Cpu className="h-2.5 w-2.5" />
                LangGraph + pgvector
              </span>
            </div>
            <p className="hidden text-xs text-slate-400 sm:block">
              Enterprise Text-to-SQL & Real-Time Analytics Telemetry
            </p>
          </div>
        </div>

        {/* Center/Right Controls */}
        <div className="flex items-center gap-2 sm:gap-3">
          {/* Backend Status Pill */}
          <div
            className={`hidden md:flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-mono transition-all ${
              isBackendHealthy
                ? 'border-emerald-500/30 bg-emerald-950/30 text-emerald-300'
                : isBackendHealthy === false
                ? 'border-rose-500/30 bg-rose-950/30 text-rose-300'
                : 'border-slate-700 bg-slate-900/50 text-slate-400'
            }`}
          >
            {isBackendHealthy ? (
              <>
                <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                <span>Engine Online</span>
              </>
            ) : isBackendHealthy === false ? (
              <>
                <AlertCircle className="h-3.5 w-3.5 text-rose-400" />
                <span>Engine Offline</span>
              </>
            ) : (
              <span>Checking...</span>
            )}
          </div>

          {/* Multi-Tenant Selector */}
          <div className="relative flex items-center">
            <div className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-slate-900/80 px-3 py-1.5 shadow-inner">
              <Shield className="h-3.5 w-3.5 text-indigo-400" />
              <div className="flex flex-col">
                <span className="text-[9px] uppercase font-mono tracking-wider text-slate-400">
                  RLS Tenant Scope
                </span>
                <select
                  value={selectedTenant}
                  onChange={(e) => onSelectTenant(e.target.value)}
                  disabled={isStreaming}
                  className="bg-transparent text-xs font-semibold text-white focus:outline-none cursor-pointer pr-2"
                >
                  {PRESET_TENANTS.map((t) => (
                    <option key={t.id} value={t.id} className="bg-slate-900 text-white">
                      {t.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Schema Explorer Button */}
          <button
            onClick={onToggleSchema}
            className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-slate-900/70 hover:bg-slate-800/90 hover:border-cyan-500/40 px-3 py-2 text-xs font-medium text-slate-200 transition-all shadow-sm active:scale-95"
            title="Inspect Database Schema Catalog"
          >
            <Layers className="h-3.5 w-3.5 text-cyan-400" />
            <span className="hidden sm:inline">Schema RAG</span>
          </button>

          {/* Clear Session */}
          <button
            onClick={onClearHistory}
            disabled={isStreaming}
            className="flex items-center justify-center h-9 w-9 rounded-xl border border-white/10 bg-slate-900/70 hover:bg-rose-950/40 hover:border-rose-500/40 text-slate-400 hover:text-rose-300 transition-all disabled:opacity-40"
            title="Clear Chat History"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </header>
  );
};
