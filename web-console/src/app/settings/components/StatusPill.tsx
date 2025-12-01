'use client';

import React from 'react';

interface StatusPillProps {
  status: 'connected' | 'not_configured' | 'inactive' | 'local' | 'enabled' | 'disabled' | 'unavailable' | 'registered_but_not_connected';
  label: string;
  icon?: string;
}

const statusStyles: Record<StatusPillProps['status'], string> = {
  connected: 'bg-green-100 text-green-800',
  enabled: 'bg-green-100 text-green-800',
  not_configured: 'bg-gray-100 text-gray-600',
  inactive: 'bg-gray-100 text-gray-600',
  local: 'bg-blue-100 text-blue-800',
  disabled: 'bg-gray-100 text-gray-600',
  unavailable: 'bg-red-100 text-red-800',
  registered_but_not_connected: 'bg-yellow-100 text-yellow-800',
};

export function StatusPill({ status, label, icon }: StatusPillProps) {
  return (
    <span className={`text-sm px-2 py-1 rounded ${statusStyles[status]}`}>
      {icon && <span className="mr-1">{icon}</span>}
      {label}
    </span>
  );
}
