import { formatLocalDateTime } from '@/lib/time';

import {
  badgeClass,
  prettyLabel,
  translateMemoryStatus,
} from './formatters';
import type { TranslateFn, WorkspaceMemoryItemSummary } from './types';

interface GovernedMemoryListProps {
  t: TranslateFn;
  loading: boolean;
  items: WorkspaceMemoryItemSummary[];
  selectedMemoryId: string | null;
  onSelectMemoryItem: (memoryItemId: string) => void;
}

export function GovernedMemoryList({
  t,
  loading,
  items,
  selectedMemoryId,
  onSelectMemoryItem,
}: GovernedMemoryListProps) {
  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 text-center text-secondary dark:text-gray-400">
        {t('loading' as any) || 'Loading...'}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 text-center text-secondary dark:text-gray-400">
        {t('noGovernedMemory' as any) || 'No governed memory found for this workspace.'}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {items.map((item) => (
        <button
          key={item.id}
          onClick={() => onSelectMemoryItem(item.id)}
          className={`w-full text-left rounded-lg border p-4 transition-colors ${
            selectedMemoryId === item.id
              ? 'border-blue-500 dark:border-blue-400 bg-blue-50 dark:bg-blue-900/20'
              : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700/50'
          }`}
        >
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className={`px-2 py-1 text-xs font-medium rounded ${badgeClass(item.lifecycle_status)}`}>
              {translateMemoryStatus(item.lifecycle_status, t)}
            </span>
            <span className={`px-2 py-1 text-xs font-medium rounded ${badgeClass(item.verification_status)}`}>
              {translateMemoryStatus(item.verification_status, t)}
            </span>
            <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
              {prettyLabel(item.kind)}
            </span>
          </div>
          <div className="text-sm font-semibold text-primary dark:text-gray-100 mb-1">
            {item.title}
          </div>
          <div className="text-xs text-secondary dark:text-gray-400 mb-2">
            {prettyLabel(item.layer)} · {formatLocalDateTime(item.observed_at)}
          </div>
          <p className="text-sm text-gray-700 dark:text-gray-300 line-clamp-3">
            {item.summary || item.claim}
          </p>
        </button>
      ))}
    </div>
  );
}
