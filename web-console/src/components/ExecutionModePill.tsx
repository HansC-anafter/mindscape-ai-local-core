'use client';

import React from 'react';

export type ExecutionMode = 'qa' | 'execution' | 'hybrid' | null;
export type ExecutionPriority = 'low' | 'medium' | 'high' | null;

interface ExecutionModePillProps {
  mode: ExecutionMode;
  priority?: ExecutionPriority;
  onClick?: () => void;
  className?: string;
}

const modeConfig: Record<NonNullable<ExecutionMode>, {
  label: string;
  icon: string;
  bgColor: string;
  textColor: string;
  description: string;
}> = {
  qa: {
    label: '對話',
    icon: '💬',
    bgColor: 'bg-slate-100 dark:bg-slate-800',
    textColor: 'text-slate-600 dark:text-slate-400',
    description: '對話模式：討論為主，執行為輔',
  },
  execution: {
    label: '執行',
    icon: '⚡',
    bgColor: 'bg-amber-100 dark:bg-amber-900/30',
    textColor: 'text-amber-700 dark:text-amber-400',
    description: '執行模式：行動優先，直接產出',
  },
  hybrid: {
    label: '混合',
    icon: '🔄',
    bgColor: 'bg-violet-100 dark:bg-violet-900/30',
    textColor: 'text-violet-700 dark:text-violet-400',
    description: '混合模式：平衡對話與執行',
  },
};

const priorityIndicator: Record<NonNullable<ExecutionPriority>, string> = {
  low: '▽',
  medium: '◇',
  high: '△',
};

export default function ExecutionModePill({
  mode,
  priority,
  onClick,
  className = '',
}: ExecutionModePillProps) {
  if (!mode) return null;

  const config = modeConfig[mode];

  return (
    <button
      onClick={onClick}
      className={`
        inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium
        transition-all duration-200
        ${config.bgColor} ${config.textColor}
        ${onClick ? 'cursor-pointer hover:opacity-80' : 'cursor-default'}
        ${className}
      `}
      title={config.description}
    >
      <span>{config.icon}</span>
      <span>{config.label}</span>
      {priority && (
        <span className="opacity-60 text-[10px]">
          {priorityIndicator[priority]}
        </span>
      )}
    </button>
  );
}

