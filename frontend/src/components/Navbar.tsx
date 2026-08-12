import React from 'react';
import { Menu, Trash2, Share2, Database } from 'lucide-react';
import { PRESET_TENANTS } from './Sidebar';

interface NavbarProps {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  selectedTenant: string;
  onSelectTenant: (id: string) => void;
  onToggleSchema: () => void;
  onClearHistory: () => void;
  onExportSession?: () => void;
  sessionTitle?: string;
  isStreaming: boolean;
}

export { PRESET_TENANTS };

export const Navbar: React.FC<NavbarProps> = ({
  sidebarOpen,
  onToggleSidebar,
  selectedTenant,
  onSelectTenant,
  onToggleSchema,
  onClearHistory,
  onExportSession,
  sessionTitle,
  isStreaming,
}) => {
  return (
    <header className="sticky top-0 z-30 flex h-14 w-full items-center justify-between border-b border-zinc-800/80 bg-[#090a0d]/90 backdrop-blur-md px-4 sm:px-6">
      {/* Left side */}
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900/60 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors lg:hidden"
          title="Toggle menu"
        >
          <Menu className="h-4 w-4" />
        </button>

        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-emerald-500" />
          <span className="text-sm font-medium text-zinc-200 truncate max-w-[200px] sm:max-w-[360px]">
            {sessionTitle || 'New Query'}
          </span>
        </div>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-1.5">
        {onExportSession && (
          <button
            onClick={onExportSession}
            disabled={isStreaming}
            className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors disabled:opacity-40"
            title="Export session transcript"
          >
            <Share2 className="h-3.5 w-3.5" />
          </button>
        )}

        <button
          onClick={onClearHistory}
          disabled={isStreaming}
          className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors disabled:opacity-40"
          title="Clear current messages"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </header>
  );
};
