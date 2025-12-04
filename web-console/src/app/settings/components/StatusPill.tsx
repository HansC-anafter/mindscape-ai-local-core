'use client';

import React from 'react';

interface StatusPillProps {
  status: 'connected' | 'not_configured' | 'inactive' | 'local' | 'enabled' | 'disabled' | 'unavailable' | 'registered_but_not_connected';
  label: string;
  icon?: string;
}

const statusStyles: Record<StatusPillProps['status'], string> = {
  connected: 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300',
  enabled: 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300',
  not_configured: 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400',
  inactive: 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400',
  local: 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300',
  disabled: 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400',
  unavailable: 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300',
  registered_but_not_connected: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300',
};

export function StatusPill({ status, label, icon }: StatusPillProps) {
  return (
    <span className={`text-sm px-2 py-1 rounded ${statusStyles[status]}`}>
      {icon && <span className="mr-1">{icon}</span>}
      {label}
    </span>
  );
}
