import type { KnowledgeAccessSummaryItem } from './types';

type Props = {
  items: KnowledgeAccessSummaryItem[];
  selectedResourceId: string | null;
  onSelect: (resourceId: string) => void;
};

export function KnowledgeAccessSummaryList({
  items,
  selectedResourceId,
  onSelect,
}: Props) {
  return (
    <div className="space-y-2" data-testid="knowledge-access-summary-list">
      {items.map((item) => (
        <button
          type="button"
          key={item.knowledge_resource_id}
          onClick={() => onSelect(item.knowledge_resource_id)}
          className={`w-full rounded-lg border p-3 text-left transition-colors ${
            selectedResourceId === item.knowledge_resource_id
              ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/30'
              : 'border-gray-200 bg-white hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700/60'
          }`}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
                {item.source_ref}
              </p>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                {item.owner_capability_code} · {item.source_kind}
              </p>
            </div>
            <span className="rounded bg-gray-100 px-2 py-1 text-xs text-gray-700 dark:bg-gray-700 dark:text-gray-200">
              {item.projection_status || (item.resource_active ? 'missing' : 'revoked')}
            </span>
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-600 dark:text-gray-300">
            <span>ACL r{item.authz_revision}</span>
            <span>{item.grant_count} grants</span>
            {item.deny_present && (
              <span className="font-medium text-red-700 dark:text-red-300">deny</span>
            )}
            <span>{item.relation_count || 0} relations</span>
          </div>
        </button>
      ))}
    </div>
  );
}
