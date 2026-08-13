import React, { useState, useEffect, useMemo, useRef } from 'react';
import { API_BASE_URL } from '../utils/api';
import {
  Plus,
  MessageSquare,
  Trash2,
  Edit2,
  Check,
  X,
  Search,
  Database,
  ShieldCheck,
  Layers,
  RotateCcw,
  ChevronLeft,
  ChevronRight,
  Server,
  AlertCircle,
  Sun,
  Moon,
} from 'lucide-react';
import { ChatSession, Tenant } from '../types';

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

interface SidebarProps {
  sessions: ChatSession[];
  activeSessionId: string;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  onDeleteSession: (id: string) => void;
  onRenameSession: (id: string, newTitle: string) => void;
  selectedTenant: string;
  onSelectTenant: (tenantId: string) => void;
  onOpenSchema: () => void;
  isStreaming: boolean;
  isOpen: boolean;
  onToggleOpen: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  onDeleteSession,
  onRenameSession,
  selectedTenant,
  onSelectTenant,
  onOpenSchema,
  isStreaming,
  isOpen,
  onToggleOpen,
}) => {
  const [searchFilter, setSearchFilter] = useState('');
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [isBackendHealthy, setIsBackendHealthy] = useState<boolean | null>(null);
  const [cacheFlushStatus, setCacheFlushStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [isTenantPopoverOpen, setIsTenantPopoverOpen] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [isDatabaseInfoOpen, setIsDatabaseInfoOpen] = useState(false);

  const tenantPopoverRef = useRef<HTMLDivElement>(null);
  const dbInfoRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dbInfoRef.current && !dbInfoRef.current.contains(e.target as Node)) {
        setIsDatabaseInfoOpen(false);
      }
    };
    if (isDatabaseInfoOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isDatabaseInfoOpen]);

  useEffect(() => {
    // Check initial preference from localStorage or body class
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'light' || document.documentElement.classList.contains('light-theme')) {
      setIsDarkMode(false);
      document.documentElement.classList.add('light-theme');
    } else {
      setIsDarkMode(true);
      document.documentElement.classList.remove('light-theme');
    }
  }, []);

  const toggleTheme = () => {
    if (isDarkMode) {
      document.documentElement.classList.add('light-theme');
      localStorage.setItem('theme', 'light');
      setIsDarkMode(false);
    } else {
      document.documentElement.classList.remove('light-theme');
      localStorage.setItem('theme', 'dark');
      setIsDarkMode(true);
    }
  };

  const checkHealth = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/health`);
      setIsBackendHealthy(res.ok);
    } catch {
      setIsBackendHealthy(false);
    }
  };

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (tenantPopoverRef.current && !tenantPopoverRef.current.contains(e.target as Node)) {
        setIsTenantPopoverOpen(false);
      }
    };
    if (isTenantPopoverOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isTenantPopoverOpen]);

  const handleStartRename = (session: ChatSession, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingSessionId(session.id);
    setEditingTitle(session.title);
  };

  const handleSaveRename = (id: string, e: React.MouseEvent | React.FormEvent) => {
    e.stopPropagation();
    if (editingTitle.trim()) {
      onRenameSession(id, editingTitle.trim());
    }
    setEditingSessionId(null);
  };

  const handleCancelRename = (e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingSessionId(null);
  };

  const handleFlushCache = async () => {
    setCacheFlushStatus('loading');
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/cache/clear`, { method: 'POST' });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || `Cache flush failed with HTTP ${response.status}`);
      }
      const result = await response.json();
      if (result.remaining !== 0) {
        throw new Error(`Cache flush incomplete: ${result.remaining} key(s) remain.`);
      }
      setCacheFlushStatus('success');
      setTimeout(() => setCacheFlushStatus('idle'), 2500);
    } catch (e) {
      console.error(e);
      setCacheFlushStatus('error');
      setTimeout(() => setCacheFlushStatus('idle'), 4000);
    }
  };

  const groupedSessions = useMemo(() => {
    const filtered = sessions.filter((s) =>
      s.title.toLowerCase().includes(searchFilter.toLowerCase())
    );

    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const startOfYesterday = startOfToday - 86400000;
    const startOfLast7Days = startOfToday - 86400000 * 7;

    const groups: { label: string; items: ChatSession[] }[] = [
      { label: 'Today', items: [] },
      { label: 'Yesterday', items: [] },
      { label: 'Previous 7 Days', items: [] },
      { label: 'Older', items: [] },
    ];

    filtered.forEach((session) => {
      const time = session.updatedAt || session.createdAt;
      if (time >= startOfToday) {
        groups[0].items.push(session);
      } else if (time >= startOfYesterday) {
        groups[1].items.push(session);
      } else if (time >= startOfLast7Days) {
        groups[2].items.push(session);
      } else {
        groups[3].items.push(session);
      }
    });

    return groups.filter((g) => g.items.length > 0);
  }, [sessions, searchFilter]);

  const activeTenantObj =
    PRESET_TENANTS.find((t) => t.id === selectedTenant) || PRESET_TENANTS[0];

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          onClick={onToggleOpen}
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden transition-opacity"
        />
      )}

      {/* Sidebar Shell */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex flex-col border-r border-zinc-800/80 bg-[#0d0e12] transition-all duration-200 ease-in-out ${
          isOpen
            ? 'w-72 translate-x-0'
            : '-translate-x-full lg:translate-x-0 lg:w-16'
        }`}
      >
        {/* ========================================================================= */}
        {/* STATE A: EXPANDED SIDEBAR (w-72)                                          */}
        {/* ========================================================================= */}
        {isOpen ? (
          <div className="flex flex-col h-full w-72">
            {/* 1. TOP HEADER */}
            <div className="flex items-center justify-between px-4 py-3.5 border-b border-zinc-800/80">
              <div className="flex items-center gap-2.5">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg overflow-hidden">
                  <img src="/logo.png" alt="WonderDB-Agent Logo" className="h-full w-full object-cover" />
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="font-semibold text-sm tracking-tight text-zinc-100">
                    WonderDB-Agent
                  </span>
                  <span className="rounded bg-zinc-800 border border-zinc-700 px-1 py-0.2 text-[9px] font-mono text-zinc-400">
                    v1.0
                  </span>
                </div>
              </div>

              <button
                onClick={onToggleOpen}
                className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition-colors"
                title="Collapse sidebar"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
            </div>

            {/* 2. PRIMARY ACTION: NEW QUERY BUTTON */}
            <div className="p-3 border-b border-zinc-800/80">
              <button
                onClick={onNewSession}
                disabled={isStreaming}
                className="flex w-full items-center justify-between rounded-lg bg-emerald-500/10 border border-emerald-500/20 hover:bg-emerald-500/20 text-emerald-400 p-2 text-xs font-semibold shadow-sm transition-all active:scale-[0.99] disabled:opacity-50"
              >
                <div className="flex items-center gap-2">
                  <Plus className="h-3.5 w-3.5" />
                  <span>New Query</span>
                </div>
                <span className="text-[10px] font-mono text-emerald-400/80 border border-emerald-500/20 px-1 rounded bg-emerald-500/10">
                  ⌘N
                </span>
              </button>
            </div>



            {/* Search History Filter */}
            {sessions.length > 3 && (
              <div className="px-3 pb-2">
                <div className="relative flex items-center">
                  <Search className="absolute left-2.5 h-3.5 w-3.5 text-zinc-500" />
                  <input
                    type="text"
                    placeholder="Search queries..."
                    value={searchFilter}
                    onChange={(e) => setSearchFilter(e.target.value)}
                    className="w-full rounded-md border border-zinc-800 bg-zinc-900/40 pl-8 pr-2.5 py-1 text-xs text-zinc-300 placeholder-zinc-500 focus:border-zinc-600 focus:outline-none"
                  />
                </div>
              </div>
            )}

            {/* 4. RECENT CHATS LIST */}
            <div className="flex-1 overflow-y-auto px-3 space-y-3 py-2">
              {sessions.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-center px-2">
                  <MessageSquare className="h-5 w-5 text-zinc-600 mb-2" />
                  <p className="text-xs font-medium text-zinc-400">No previous queries</p>
                </div>
              ) : (
                groupedSessions.map((group) => (
                  <div key={group.label} className="space-y-0.5">
                    <span className="px-2 text-[10px] font-mono uppercase tracking-wider text-zinc-500 font-semibold block">
                      {group.label}
                    </span>

                    {group.items.map((session) => {
                      const isActive = session.id === activeSessionId;
                      const isEditing = session.id === editingSessionId;

                      return (
                        <div
                          key={session.id}
                          onClick={() => !isEditing && onSelectSession(session.id)}
                          className={`group relative flex items-center justify-between rounded-lg px-2.5 py-1.5 text-xs transition-colors cursor-pointer ${
                            isActive
                              ? 'bg-zinc-800 text-zinc-100 font-medium'
                              : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200'
                          }`}
                        >
                          {isEditing ? (
                            <div
                              className="flex items-center gap-1 w-full"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <input
                                type="text"
                                value={editingTitle}
                                onChange={(e) => setEditingTitle(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') handleSaveRename(session.id, e);
                                  if (e.key === 'Escape') setEditingSessionId(null);
                                }}
                                autoFocus
                                className="w-full rounded bg-zinc-900 px-1.5 py-0.5 text-xs text-white border border-zinc-600 focus:outline-none"
                              />
                              <button
                                onClick={(e) => handleSaveRename(session.id, e)}
                                className="text-zinc-300 hover:text-white p-0.5"
                              >
                                <Check className="h-3.5 w-3.5" />
                              </button>
                              <button
                                onClick={handleCancelRename}
                                className="text-zinc-500 hover:text-zinc-300 p-0.5"
                              >
                                <X className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          ) : (
                            <>
                              <div className="flex items-center gap-2 truncate pr-2">
                                <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-70" />
                                <span className="truncate">{session.title}</span>
                              </div>

                              <div className="hidden group-hover:flex items-center gap-1 shrink-0">
                                <button
                                  onClick={(e) => handleStartRename(session, e)}
                                  className="p-1 text-zinc-500 hover:text-zinc-200 rounded hover:bg-zinc-700/50 transition-colors"
                                  title="Rename session"
                                >
                                  <Edit2 className="h-3 w-3" />
                                </button>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    onDeleteSession(session.id);
                                  }}
                                  className="p-1 text-zinc-500 hover:text-rose-400 rounded hover:bg-zinc-700/50 transition-colors"
                                  title="Delete session"
                                >
                                  <Trash2 className="h-3 w-3" />
                                </button>
                              </div>
                            </>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ))
              )}
            </div>

            {/* 5. FOOTER UTILITY BAR */}
            <div className="p-3 border-t border-zinc-800/80 space-y-2 bg-[#0a0b0e]">
              <div className="relative" ref={isOpen ? dbInfoRef : null}>
                <button
                  onClick={() => setIsDatabaseInfoOpen(!isDatabaseInfoOpen)}
                  className="flex w-full items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/50 hover:bg-zinc-800 hover:border-zinc-700 px-3 py-2 text-xs font-medium text-zinc-300 hover:text-zinc-100 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <Database className="h-3.5 w-3.5 text-zinc-400" />
                    <span>Database Info</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {isBackendHealthy ? (
                      <span className="h-2 w-2 rounded-full bg-emerald-500" title="Online" />
                    ) : isBackendHealthy === false ? (
                      <span className="h-2 w-2 rounded-full bg-rose-500" title="Offline" />
                    ) : null}
                  </div>
                </button>

                {isDatabaseInfoOpen && (
                  <div className="absolute bottom-full left-0 mb-2 w-full rounded-xl border border-zinc-800 bg-[#0d0e12] p-2 shadow-xl z-50">
                    <button
                      onClick={() => { onOpenSchema(); setIsDatabaseInfoOpen(false); }}
                      className="flex w-full items-center justify-between rounded-lg hover:bg-zinc-800/50 px-3 py-2 text-xs font-medium text-zinc-300 hover:text-zinc-100 transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        <Layers className="h-3.5 w-3.5 text-zinc-400" />
                        <span>Schema Catalog</span>
                      </div>
                      <span className="rounded bg-zinc-800 border border-zinc-700 px-1.5 py-0.2 text-[10px] font-mono text-zinc-400">
                        5 tables
                      </span>
                    </button>
                    
                    <button
                      onClick={() => { handleFlushCache(); setIsDatabaseInfoOpen(false); }}
                      className="flex w-full items-center justify-between rounded-lg hover:bg-zinc-800/50 px-3 py-2 text-xs font-medium text-zinc-300 hover:text-zinc-100 transition-colors mt-1"
                    >
                      <div className="flex items-center gap-2">
                        <RotateCcw className={`h-3.5 w-3.5 text-zinc-400 ${cacheFlushStatus === 'loading' ? 'animate-spin' : ''}`} />
                        <span>Semantic Cache</span>
                      </div>
                      <span className="text-[10px] font-mono text-zinc-500">
                        {cacheFlushStatus === 'loading' ? 'Flushing' : cacheFlushStatus === 'success' ? 'Flushed' : cacheFlushStatus === 'error' ? 'Failed' : 'Flush'}
                      </span>
                    </button>

                      {/* Engine Status Card */}
              <div
                onClick={checkHealth}
                className="flex items-center justify-between rounded-lg bg-zinc-900/60 border border-zinc-800 px-3 py-2 text-xs cursor-pointer hover:bg-zinc-800 transition-colors"
                title="Click to refresh engine status"
              >
                <div className="flex items-center gap-2">
                  <Server className="h-3.5 w-3.5 text-zinc-400" />
                  <span className="text-[11px] text-zinc-300 font-medium">Database Engine</span>
                </div>
                <div className="flex items-center gap-1.5">
                  {isBackendHealthy ? (
                    <>
                      <span className="h-2 w-2 rounded-full bg-emerald-500" />
                      <span className="text-[10px] font-mono text-emerald-400 font-medium">Online</span>
                    </>
                  ) : isBackendHealthy === false ? (
                    <>
                      <span className="h-2 w-2 rounded-full bg-rose-500" />
                      <span className="text-[10px] font-mono text-rose-400 font-medium">Offline</span>
                    </>
                  ) : (
                    <span className="text-[10px] font-mono text-zinc-500">Checking...</span>
                  )}
                </div>
              </div>

                  </div>
                )}
              </div>

              <button
                onClick={toggleTheme}
                className="flex w-full items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/50 hover:bg-zinc-800 hover:border-zinc-700 px-3 py-2 text-xs font-medium text-zinc-300 hover:text-zinc-100 transition-colors"
                title={isDarkMode ? 'Switch to light mode' : 'Switch to dark mode'}
              >
                <div className="flex items-center gap-2">
                  {isDarkMode ? <Sun className="h-3.5 w-3.5 text-zinc-400" /> : <Moon className="h-3.5 w-3.5 text-zinc-400" />}
                  <span>{isDarkMode ? 'Light Mode' : 'Dark Mode'}</span>
                </div>
              </button>

            
            </div>
          </div>
        ) : (
          /* ========================================================================= */
          /* STATE B: COLLAPSED MINI-RAIL (w-16) - EXACT SAME ORDER TOP TO BOTTOM       */
          /* ========================================================================= */
          <div className="hidden lg:flex flex-col items-center justify-between h-full w-16 py-3 px-2">
            {/* TOP SECTION */}
            <div className="flex flex-col items-center gap-2.5 w-full">
              {/* 1. Logo / Expand */}
              <button
                onClick={onToggleOpen}
                className="flex h-9 w-9 items-center justify-center rounded-lg transition-colors overflow-hidden p-0.5"
                title="Expand sidebar"
              >
                <img src="/logo.png" alt="WonderDB-Agent Logo" className="h-full w-full object-contain rounded-md" />
              </button>

              {/* 2. New Query Button */}
              <button
                onClick={onNewSession}
                disabled={isStreaming}
                className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/10 border border-emerald-500/20 hover:bg-emerald-500/20 text-emerald-400 font-bold transition-all shadow-sm disabled:opacity-40"
                title="New Query (⌘N)"
              >
                <Plus className="h-4 w-4" />
              </button>



              {/* 4. Recent Chats Icon */}
              <button
                onClick={onToggleOpen}
                className="relative flex h-9 w-9 items-center justify-center rounded-lg bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
                title="Recent Queries (Click to expand list)"
              >
                <MessageSquare className="h-4 w-4" />
                {sessions.length > 0 && (
                  <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-zinc-700 text-[8px] font-mono font-bold text-zinc-200">
                    {sessions.length}
                  </span>
                )}
              </button>
            </div>

            {/* BOTTOM SECTION */}
            <div className="flex flex-col items-center gap-2.5 w-full pt-2 border-t border-zinc-800/80" ref={!isOpen ? dbInfoRef : null}>
              {/* Database Info */}
              <div className="relative w-full flex justify-center">
                <button
                  onClick={() => setIsDatabaseInfoOpen(!isDatabaseInfoOpen)}
                  className="relative flex h-9 w-9 items-center justify-center rounded-lg bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
                  title="Database Info"
                >
                  <Database className="h-4 w-4" />
                  {isBackendHealthy ? (
                    <span className="absolute -top-0.5 -right-0.5 flex h-2 w-2 rounded-full bg-emerald-500 ring-2 ring-[#0d0e12]" />
                  ) : isBackendHealthy === false ? (
                    <span className="absolute -top-0.5 -right-0.5 flex h-2 w-2 rounded-full bg-rose-500 ring-2 ring-[#0d0e12]" />
                  ) : null}
                </button>

                {isDatabaseInfoOpen && (
                  <div className="absolute bottom-2 left-14 w-64 rounded-xl border border-zinc-800 bg-[#0d0e12] p-2 shadow-xl z-50">
                    <button
                      onClick={() => { onOpenSchema(); setIsDatabaseInfoOpen(false); }}
                      className="flex w-full items-center justify-between rounded-lg hover:bg-zinc-800/50 px-3 py-2 text-xs font-medium text-zinc-300 hover:text-zinc-100 transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        <Layers className="h-3.5 w-3.5 text-zinc-400" />
                        <span>Schema Catalog</span>
                      </div>
                      <span className="rounded bg-zinc-800 border border-zinc-700 px-1.5 py-0.2 text-[10px] font-mono text-zinc-400">
                        5 tables
                      </span>
                    </button>
                    
                    <button
                      onClick={() => { handleFlushCache(); setIsDatabaseInfoOpen(false); }}
                      className="flex w-full items-center justify-between rounded-lg hover:bg-zinc-800/50 px-3 py-2 text-xs font-medium text-zinc-300 hover:text-zinc-100 transition-colors mt-1"
                    >
                      <div className="flex items-center gap-2">
                        <RotateCcw className={`h-3.5 w-3.5 text-zinc-400 ${cacheFlushStatus === 'loading' ? 'animate-spin' : ''}`} />
                        <span>Semantic Cache</span>
                      </div>
                      <span className="text-[10px] font-mono text-zinc-500">
                        {cacheFlushStatus === 'loading' ? 'Flushing' : cacheFlushStatus === 'success' ? 'Flushed' : cacheFlushStatus === 'error' ? 'Failed' : 'Flush'}
                      </span>
                    </button>

                  </div>
                )}
              </div>

              {/* Mini expand toggle */}
              <button
                onClick={onToggleOpen}
                className="flex h-6 w-6 items-center justify-center rounded-md text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors mt-0.5"
                title="Expand sidebar"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}
      </aside>
    </>
  );
};
