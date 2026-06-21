'use client';

import { t } from '../../../../../lib/i18n';
import type { ModelItem } from './types';

interface ModelDetailsSectionProps {
  model: ModelItem;
}

export function ModelDetailsSection({ model }: ModelDetailsSectionProps) {
  return (
    <div className="grid grid-cols-2 gap-4">
      {model.dimensions && (
        <div>
          <span className="text-xs text-gray-500 dark:text-gray-400">{t('dimensions' as any) || 'Dimensions'}</span>
          <div className="text-sm font-medium text-gray-900 dark:text-gray-100">{model.dimensions}</div>
        </div>
      )}
      {model.context_window && (
        <div>
          <span className="text-xs text-gray-500 dark:text-gray-400">{t('contextWindow' as any) || 'Context Window'}</span>
          <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {model.context_window.toLocaleString()}
          </div>
        </div>
      )}
    </div>
  );
}
