'use client';

import React from 'react';
import { X } from 'lucide-react';

interface WorkspaceFloatingSettingsPanelProps {
  open: boolean;
  title: string;
  closeLabel: string;
  children: React.ReactNode;
  onClose: () => void;
}

export function WorkspaceFloatingSettingsPanel({
  open,
  title,
  closeLabel,
  children,
  onClose,
}: WorkspaceFloatingSettingsPanelProps) {
  if (!open) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-[90] bg-black/25 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div className="mx-auto flex h-full max-w-6xl flex-col overflow-hidden rounded border border-gray-200 bg-white shadow-xl dark:border-gray-800 dark:bg-gray-950">
        <div className="flex h-11 shrink-0 items-center justify-between border-b border-gray-200 px-3 dark:border-gray-800">
          <div className="min-w-0 truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
            {title}
          </div>
          <button
            type="button"
            aria-label={closeLabel}
            className="inline-flex h-8 w-8 items-center justify-center rounded text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-100"
            onClick={onClose}
          >
            <X aria-hidden="true" className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {children}
        </div>
      </div>
    </div>
  );
}
