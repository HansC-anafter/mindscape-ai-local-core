'use client';

import React from 'react';
import { t } from '@/lib/i18n';

export type WorkspaceMode = 'research' | 'publishing' | 'planning' | null;

interface WorkspaceModeSelectorProps {
  currentMode: WorkspaceMode;
  onModeChange: (mode: WorkspaceMode) => void;
  disabled?: boolean;
}

export default function WorkspaceModeSelector({
  currentMode,
  onModeChange,
  disabled = false
}: WorkspaceModeSelectorProps) {
  const modes: Array<{ value: WorkspaceMode; label: string; icon: string; description: string }> = [
    {
      value: 'research',
      label: t('modeResearch' as any),
      icon: '🔬',
      description: t('modeResearchDescription' as any)
    },
    {
      value: 'publishing',
      label: t('modePublishing' as any),
      icon: '✍️',
      description: t('modePublishingDescription' as any)
    },
    {
      value: 'planning',
      label: t('modePlanning' as any),
      icon: '🗓',
      description: t('modePlanningDescription' as any)
    }
  ];

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-medium text-gray-700">{t('workspaceMode' as any)}:</span>
      <div className="flex gap-1.5">
        {modes.map((mode) => (
          <button
            key={mode.value}
            onClick={() => !disabled && onModeChange(mode.value)}
            disabled={disabled}
            className={`
              px-2 py-1 text-xs font-medium rounded transition-all
              ${
                currentMode === mode.value
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }
              ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
            `}
            title={mode.description}
          >
            <span className="mr-1">{mode.icon}</span>
            {mode.label}
          </button>
        ))}
        {currentMode && (
          <button
            onClick={() => !disabled && onModeChange(null)}
            disabled={disabled}
            className={`
              px-2 py-1 text-xs font-medium rounded transition-all
              bg-gray-100 text-gray-600 hover:bg-gray-200
              ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
            `}
            title={t('clearMode' as any)}
          >
            {t('clear' as any)}
          </button>
        )}
      </div>
    </div>
  );
}
