'use client';

import React from 'react';
import { InlineAlert } from '../InlineAlert';

interface WizardShellProps {
  title: string;
  onClose: () => void;
  error?: string | null;
  success?: string | null;
  onDismissError?: () => void;
  onDismissSuccess?: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

export function WizardShell({
  title,
  onClose,
  error,
  success,
  onDismissError,
  onDismissSuccess,
  children,
  footer,
  className = '',
}: WizardShellProps) {
  return (
    <div className={`bg-white rounded-lg shadow-lg p-6 border-2 border-purple-200 ${className}`}>
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600"
          aria-label="Close"
        >
          ✕
        </button>
      </div>

      {error && (
        <InlineAlert
          type="error"
          message={error}
          onDismiss={onDismissError}
          className="mb-4"
        />
      )}

      {success && (
        <InlineAlert
          type="success"
          message={success}
          onDismiss={onDismissSuccess}
          className="mb-4"
        />
      )}

      <div className="space-y-4">{children}</div>

      {footer && <div className="flex justify-end space-x-3 pt-4 border-t mt-4">{footer}</div>}
    </div>
  );
}
