'use client';

import React from 'react';
import { t } from '../../../lib/i18n';
import { Card } from './Card';
import { StatusPill } from './StatusPill';
import type { RegisteredTool } from '../types';

interface RegisteredToolListProps {
  tools: RegisteredTool[];
  maxDisplay?: number;
}

export function RegisteredToolList({ tools, maxDisplay = 10 }: RegisteredToolListProps) {
  if (tools.length === 0) {
    return null;
  }

  const displayTools = tools.slice(0, maxDisplay);

  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">{t('registeredTools' as any)}</h3>
      <div className="space-y-2">
        {displayTools.map((tool) => (
          <div
            key={tool.tool_id}
            className="flex items-center justify-between p-3 border border-gray-200 dark:border-gray-700 rounded"
          >
            <div>
              <span className="font-medium text-gray-900 dark:text-gray-100">{tool.display_name}</span>
              <span className="ml-2 text-sm text-gray-500 dark:text-gray-400">{tool.category}</span>
            </div>
            <StatusPill
              status={tool.enabled ? 'enabled' : 'disabled'}
              label={tool.enabled ? t('toolEnabled' as any) : t('toolDisabled' as any)}
            />
          </div>
        ))}
      </div>
      {tools.length > maxDisplay && (
        <p className="mt-4 text-sm text-gray-500 dark:text-gray-400 text-center">
          {t('showing' as any)} {maxDisplay} {t('of' as any)} {tools.length} {t('toolsCountLabel' as any)}
        </p>
      )}
    </Card>
  );
}
