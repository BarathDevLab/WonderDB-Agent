import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Download, Maximize2, Minus, Plus, RotateCcw, X } from 'lucide-react';

interface VisualizationModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  onDownload?: () => void | Promise<void>;
  children: (zoom: number) => React.ReactNode;
}

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 3;
const ZOOM_STEP = 0.25;

export const VisualizationModal: React.FC<VisualizationModalProps> = ({
  open,
  title,
  onClose,
  onDownload,
  children,
}) => {
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    if (!open) return;

    setZoom(1);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if ((event.ctrlKey || event.metaKey) && (event.key === '+' || event.key === '=')) {
        event.preventDefault();
        setZoom((value) => Math.min(MAX_ZOOM, value + ZOOM_STEP));
      }
      if ((event.ctrlKey || event.metaKey) && event.key === '-') {
        event.preventDefault();
        setZoom((value) => Math.max(MIN_ZOOM, value - ZOOM_STEP));
      }
      if ((event.ctrlKey || event.metaKey) && event.key === '0') {
        event.preventDefault();
        setZoom(1);
      }
    };
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [open, onClose]);

  if (!open) return null;

  const zoomOut = () => setZoom((value) => Math.max(MIN_ZOOM, value - ZOOM_STEP));
  const zoomIn = () => setZoom((value) => Math.min(MAX_ZOOM, value + ZOOM_STEP));

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex flex-col bg-black/85 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={`${title} expanded view`}
    >
      <div className="flex min-h-14 items-center justify-between gap-4 border-b border-zinc-800 bg-[#18181b] px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-2">
          <Maximize2 className="h-4 w-4 shrink-0 text-indigo-400" />
          <span className="truncate text-sm font-semibold text-zinc-100">{title}</span>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={zoomOut}
            disabled={zoom <= MIN_ZOOM}
            className="rounded-md p-2 text-zinc-300 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-35"
            aria-label="Zoom out"
            title="Zoom out"
          >
            <Minus className="h-4 w-4" />
          </button>
          <span className="w-14 text-center font-mono text-xs text-zinc-400" aria-live="polite">
            {Math.round(zoom * 100)}%
          </span>
          <button
            type="button"
            onClick={zoomIn}
            disabled={zoom >= MAX_ZOOM}
            className="rounded-md p-2 text-zinc-300 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-35"
            aria-label="Zoom in"
            title="Zoom in"
          >
            <Plus className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setZoom(1)}
            className="ml-1 flex items-center gap-1.5 rounded-md px-2 py-2 text-xs text-zinc-300 hover:bg-zinc-800"
            title="Reset zoom"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Reset</span>
          </button>
          {onDownload && (
            <button
              type="button"
              onClick={() => void onDownload()}
              className="ml-1 flex items-center gap-1.5 rounded-md px-2 py-2 text-xs text-zinc-300 hover:bg-zinc-800"
              title="Download rendered image"
            >
              <Download className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">PNG</span>
            </button>
          )}
          <div className="mx-2 h-5 w-px bg-zinc-700" />
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-2 text-zinc-300 hover:bg-zinc-800 hover:text-white"
            aria-label="Close expanded view"
            title="Close (Esc)"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>

      <div
        className="flex-1 overflow-auto bg-[#111113] p-4 sm:p-6"
        onWheel={(event) => {
          if (!event.ctrlKey && !event.metaKey) return;
          event.preventDefault();
          setZoom((value) => Math.min(MAX_ZOOM, Math.max(
            MIN_ZOOM,
            value + (event.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP),
          )));
        }}
      >
        {children(zoom)}
      </div>

      <div className="border-t border-zinc-800 bg-[#18181b] px-4 py-1.5 text-center text-[10px] text-zinc-500">
        Ctrl/Cmd + scroll to zoom · Esc to close
      </div>
    </div>,
    document.body,
  );
};
