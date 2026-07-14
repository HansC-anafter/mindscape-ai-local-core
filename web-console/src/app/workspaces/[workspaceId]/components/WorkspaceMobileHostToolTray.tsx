'use client';

import React from 'react';
import { PanelRight, X } from 'lucide-react';

interface UseWorkspaceMobileHostToolTrayOptions {
  enabled: boolean;
  activePanelOpen: boolean;
  onDismiss: () => void;
}

export function useWorkspaceMobileHostToolTray({
  enabled,
  activePanelOpen,
  onDismiss,
}: UseWorkspaceMobileHostToolTrayOptions) {
  const [open, setOpen] = React.useState(false);
  const anchorRef = React.useRef<HTMLDivElement>(null);
  const panelRef = React.useRef<HTMLElement>(null);

  const close = React.useCallback(() => {
    setOpen(false);
    onDismiss();
  }, [onDismiss]);

  const show = React.useCallback(() => {
    setOpen(true);
  }, []);

  const toggle = React.useCallback(() => {
    if (open) {
      close();
      return;
    }
    show();
  }, [close, open, show]);

  React.useEffect(() => {
    if (!enabled) {
      setOpen(false);
      return;
    }
    if (activePanelOpen) {
      setOpen(true);
    }
  }, [activePanelOpen, enabled]);

  React.useEffect(() => {
    if (!enabled || !open || typeof document === 'undefined') {
      return undefined;
    }

    function dismiss(event?: Event) {
      const target = event?.target;
      if (
        target instanceof Node
        && (anchorRef.current?.contains(target) || panelRef.current?.contains(target))
      ) {
        return;
      }
      close();
    }

    document.addEventListener('click', dismiss, true);
    document.addEventListener('scroll', dismiss, true);
    window.addEventListener('scroll', dismiss, true);
    return () => {
      document.removeEventListener('click', dismiss, true);
      document.removeEventListener('scroll', dismiss, true);
      window.removeEventListener('scroll', dismiss, true);
    };
  }, [close, enabled, open]);

  return {
    anchorRef,
    panelRef,
    open,
    close,
    show,
    toggle,
  };
}

interface WorkspaceMobileHostToolTrayProps {
  anchorRef: React.RefObject<HTMLDivElement>;
  open: boolean;
  onToggle: () => void;
  rail: React.ReactNode;
  panel: React.ReactNode;
}

export function WorkspaceMobileHostToolTray({
  anchorRef,
  open,
  onToggle,
  rail,
  panel,
}: WorkspaceMobileHostToolTrayProps) {
  return (
    <>
      {panel}
      <div
        className="absolute right-2 top-40 z-50 flex flex-col items-end gap-2"
        data-testid="workspace-mobile-host-rail-controls"
      >
        <div
          ref={anchorRef}
          className="flex flex-col items-end gap-2"
          data-testid="workspace-global-tool-tray-anchor"
        >
          <button
            type="button"
            className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-gray-200 bg-white/95 text-gray-700 shadow-lg backdrop-blur transition hover:bg-white dark:border-gray-800 dark:bg-gray-950/95 dark:text-gray-200"
            aria-label={open ? 'Close workspace tools' : 'Open workspace tools'}
            aria-expanded={open}
            data-testid="workspace-global-tool-tray-toggle"
            onClick={onToggle}
          >
            {open ? (
              <X aria-hidden="true" className="h-4 w-4" />
            ) : (
              <PanelRight aria-hidden="true" className="h-4 w-4" />
            )}
          </button>
          {open ? rail : null}
        </div>
      </div>
    </>
  );
}
