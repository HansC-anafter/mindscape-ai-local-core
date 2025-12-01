'use client';

import React from 'react';

export type ToolConnectionStatus = 'unavailable' | 'registered_but_not_connected' | 'connected';

interface ToolStatusChipProps {
  toolType: string;
  status: ToolConnectionStatus;
  onClick?: () => void;
  className?: string;
}

const statusConfig: Record<ToolConnectionStatus, { icon: string; label: string; colorClass: string }> = {
  connected: {
    icon: '✅',
    label: 'Connected',
    colorClass: 'bg-green-100 text-green-700 border-green-300',
  },
  registered_but_not_connected: {
    icon: '⚠️',
    label: 'Not connected',
    colorClass: 'bg-yellow-100 text-yellow-700 border-yellow-300',
  },
  unavailable: {
    icon: '🔴',
    label: 'Not supported',
    colorClass: 'bg-red-100 text-red-700 border-red-300',
  },
};

export function ToolStatusChip({ toolType, status, onClick, className = '' }: ToolStatusChipProps) {
  const config = statusConfig[status];

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded border font-medium ${
        onClick ? 'cursor-pointer hover:opacity-80 transition-opacity' : ''
      } ${config.colorClass} ${className}`}
      onClick={onClick}
      title={onClick ? `Click to configure ${toolType}` : undefined}
    >
      <span>{config.icon}</span>
      <span>{toolType}</span>
      <span className="opacity-75">{config.label}</span>
    </span>
  );
}

