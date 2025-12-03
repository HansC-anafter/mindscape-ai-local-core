'use client';

import React from 'react';

interface InlineAlertProps {
  type: 'error' | 'success' | 'warning' | 'info';
  message: string;
  onDismiss?: () => void;
  className?: string;
}

const alertStyles = {
  error: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-700 dark:text-red-300',
  success: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800 text-green-700 dark:text-green-300',
  warning: 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800 text-yellow-700 dark:text-yellow-300',
  info: 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800 text-blue-700 dark:text-blue-300',
};

export function InlineAlert({ type, message, onDismiss, className = '' }: InlineAlertProps) {
  const isCompact = className.includes('mb-0');
  const isInHeader = className.includes('mb-0');
  return (
    <div className={`${isCompact ? 'mb-0' : 'mb-4'} border ${isCompact ? 'px-3 py-1.5' : 'px-4 py-3'} rounded text-sm ${alertStyles[type]} ${className} ${isInHeader ? 'max-w-full' : ''}`}>
      <div className="flex items-center justify-between gap-2 min-w-0">
        <span className={isInHeader ? 'truncate' : 'whitespace-nowrap'}>{message}</span>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="ml-2 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 flex-shrink-0"
            aria-label="Dismiss"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );
}
