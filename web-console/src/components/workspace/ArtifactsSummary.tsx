'use client';

import React from 'react';
import { useT } from '@/lib/i18n';

export interface Artifact {
  id: string;
  name: string;
  type: string;
  createdAt?: string;
  url?: string;
}

interface ArtifactsSummaryProps {
  count: number;
  onViewAll: () => void;
}

export function ArtifactsSummary({ count, onViewAll }: ArtifactsSummaryProps) {
  const t = useT();

  if (count === 0) return null;

  return (
    <div className="artifacts-summary mt-3">
      <div className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
        <span className="text-xs text-gray-600 dark:text-gray-400">
          本輪已產出 {count} 個成果
        </span>
        <button
          onClick={onViewAll}
          className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 hover:underline transition-colors"
        >
          → 查看全部
        </button>
      </div>
    </div>
  );
}

