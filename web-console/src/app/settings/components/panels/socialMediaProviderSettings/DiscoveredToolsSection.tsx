import React from 'react';

import { useT } from '../../../../../lib/i18n';
import type { RegisteredTool } from './types';

interface DiscoveredToolsSectionProps {
  loadingTools: boolean;
  tools: RegisteredTool[];
}

export function DiscoveredToolsSection({ loadingTools, tools }: DiscoveredToolsSectionProps) {
  const t = useT();
  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-medium text-gray-900 dark:text-gray-100">
          {t('discoveredTools' as any) || 'Discovered Tools'}
        </h3>
        {loadingTools && (
          <span className="text-sm text-gray-500 dark:text-gray-400">{t('loading' as any)}</span>
        )}
      </div>
      {tools.length > 0 ? (
        <div className="space-y-2">
          {tools.map((tool) => (
            <div
              key={tool.tool_id}
              className="flex items-center justify-between p-3 border border-gray-200 dark:border-gray-700 rounded bg-gray-50 dark:bg-gray-800/50"
            >
              <div className="flex-1">
                <div className="font-medium text-gray-900 dark:text-gray-100">
                  {tool.display_name}
                </div>
                <div className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                  {tool.description || tool.category}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`px-2 py-1 text-xs rounded ${
                    tool.enabled
                      ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                  }`}
                >
                  {tool.enabled ? t('enabled' as any) : t('disabled' as any)}
                </span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
          {loadingTools ? t('loading' as any) : t('noToolsDiscovered' as any) || 'No tools discovered yet'}
        </p>
      )}
    </div>
  );
}
