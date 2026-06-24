import { X } from 'lucide-react';

import type React from 'react';

export function ProviderWizardFrame({
  children,
  onClose,
  title,
}: {
  children: React.ReactNode;
  onClose: () => void;
  title: string;
}) {
  return (
    <div
      className="mt-2 flex min-h-48 max-h-[min(34rem,calc(100vh-12rem))] resize-y flex-col overflow-hidden rounded-lg border border-sky-200 bg-sky-50/60 shadow-sm dark:border-sky-900 dark:bg-sky-950/20"
      data-testid="capture-provider-wizard"
      role="dialog"
      aria-modal="false"
      aria-labelledby="capture-provider-wizard-title"
    >
      <div className="flex items-center justify-between gap-3 border-b border-sky-200 bg-white px-3 py-2 dark:border-sky-900 dark:bg-gray-950">
        <div>
          <div
            id="capture-provider-wizard-title"
            className="text-sm font-semibold text-gray-900 dark:text-gray-100"
          >
            {title}
          </div>
          <div className="text-[11px] text-gray-500 dark:text-gray-400">
            Provider setup wizard
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-gray-300 p-1 text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-900"
          aria-label="Close provider setup"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3 text-xs" data-testid="capture-provider-wizard-body">
        {children}
      </div>
    </div>
  );
}
