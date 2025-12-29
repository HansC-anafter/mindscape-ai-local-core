'use client';

import React from 'react';
import { t } from '@/lib/i18n';

interface GraphControlsProps {
  activeLens: 'all' | 'direction' | 'action';
  onLensChange: (lens: 'all' | 'direction' | 'action') => void;
}

export function GraphControls({ activeLens, onLensChange }: GraphControlsProps) {
  const lensOptions = [
    { value: 'all', label: t('graphLensAll'), icon: '🌐' },
    { value: 'direction', label: t('graphLensDirection'), icon: '🧭' },
    { value: 'action', label: t('graphLensAction'), icon: '⚡' },
  ] as const;

  return (
    <div className="flex gap-2 p-4 bg-white rounded-lg shadow-sm border border-gray-200">
      <span className="text-sm text-gray-500 self-center mr-2">{t('graphLensLabel')}</span>
      {lensOptions.map((option) => (
        <button
          key={option.value}
          onClick={() => onLensChange(option.value)}
          className={`
            px-4 py-2 rounded-lg text-sm font-medium transition-all
            ${activeLens === option.value
              ? 'bg-indigo-600 text-white shadow-md'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }
          `}
        >
          {option.icon} {option.label}
        </button>
      ))}
    </div>
  );
}

