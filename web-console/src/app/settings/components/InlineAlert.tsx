'use client';

import React from 'react';

interface InlineAlertProps {
  type: 'error' | 'success' | 'warning' | 'info';
  message: string;
  onDismiss?: () => void;
  className?: string;
}

const alertStyles = {
  error: 'bg-red-50 border-red-200 text-red-700',
  success: 'bg-green-50 border-green-200 text-green-700',
  warning: 'bg-yellow-50 border-yellow-200 text-yellow-700',
  info: 'bg-blue-50 border-blue-200 text-blue-700',
};

export function InlineAlert({ type, message, onDismiss, className = '' }: InlineAlertProps) {
  return (
    <div className={`mb-4 border px-4 py-3 rounded ${alertStyles[type]} ${className}`}>
      <div className="flex items-center justify-between">
        <span>{message}</span>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="ml-4 text-gray-400 hover:text-gray-600"
            aria-label="Dismiss"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );
}
