import { formatLocalDateTime } from '@/lib/time';

import {
  badgeClass,
  prettyLabel,
  translateMemoryStatus,
} from './formatters';
import type {
  GoalLedgerProjectionSummary,
  MemoryEdgeSummary,
  MemoryVersionSummary,
  PersonalKnowledgeProjectionSummary,
  TranslateFn,
} from './types';

interface VersionsSectionProps {
  t: TranslateFn;
  versions: MemoryVersionSummary[];
}

export function GovernedMemoryVersionsSection({ t, versions }: VersionsSectionProps) {
  return (
    <div className="rounded-lg border border-default dark:border-gray-700 p-4">
      <div className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
        {t('versions' as any) || 'Versions'}
      </div>
      <div className="space-y-3">
        {versions.length === 0 ? (
          <div className="text-sm text-secondary dark:text-gray-400">
            {t('noVersions' as any) || 'No versions recorded.'}
          </div>
        ) : (
          versions.map((version) => (
            <div key={version.id} className="rounded bg-surface-accent dark:bg-gray-900/40 p-3">
              <div className="flex items-center justify-between gap-3 mb-1">
                <div className="text-xs font-medium text-primary dark:text-gray-100">
                  v{version.version_no}
                </div>
                <div className="text-xs text-secondary dark:text-gray-400">
                  {prettyLabel(version.update_mode)}
                </div>
              </div>
              <div className="text-xs text-secondary dark:text-gray-400 mb-2">
                {formatLocalDateTime(version.created_at)}
              </div>
              <div className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                {version.summary_snapshot || version.claim_snapshot}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

interface RelatedSectionsProps {
  t: TranslateFn;
  personalKnowledgeProjections: PersonalKnowledgeProjectionSummary[];
  goalProjections: GoalLedgerProjectionSummary[];
}

export function GovernedMemoryRelatedSections({
  t,
  personalKnowledgeProjections,
  goalProjections,
}: RelatedSectionsProps) {
  return (
    <>
      <div className="rounded-lg border border-default dark:border-gray-700 p-4">
        <div className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
          {t('relatedKnowledge' as any) || 'Related Knowledge'}
        </div>
        <div className="space-y-3">
          {personalKnowledgeProjections.length === 0 ? (
            <div className="text-sm text-secondary dark:text-gray-400">
              {t('noKnowledgeProjections' as any) || 'No personal knowledge projections.'}
            </div>
          ) : (
            personalKnowledgeProjections.map((entry) => (
              <div key={entry.id} className="rounded bg-surface-accent dark:bg-gray-900/40 p-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
                    {entry.knowledge_type}
                  </span>
                  <span className={`px-2 py-1 text-xs rounded ${badgeClass(entry.status)}`}>
                    {translateMemoryStatus(entry.status, t)}
                  </span>
                </div>
                <div className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                  {entry.content}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="rounded-lg border border-default dark:border-gray-700 p-4">
        <div className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
          {t('relatedGoals' as any) || 'Related Goals'}
        </div>
        <div className="space-y-3">
          {goalProjections.length === 0 ? (
            <div className="text-sm text-secondary dark:text-gray-400">
              {t('noGoalProjections' as any) || 'No goal projections.'}
            </div>
          ) : (
            goalProjections.map((entry) => (
              <div key={entry.id} className="rounded bg-surface-accent dark:bg-gray-900/40 p-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`px-2 py-1 text-xs rounded ${badgeClass(entry.status)}`}>
                    {translateMemoryStatus(entry.status, t)}
                  </span>
                  <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
                    {prettyLabel(entry.horizon)}
                  </span>
                </div>
                <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {entry.title}
                </div>
                <div className="text-sm text-gray-700 dark:text-gray-300">
                  {entry.description}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </>
  );
}

interface EdgesSectionProps {
  t: TranslateFn;
  outgoingEdges: MemoryEdgeSummary[];
  onSelectMemoryItem: (memoryItemId: string | null) => void;
}

export function GovernedMemoryEdgesSection({
  t,
  outgoingEdges,
  onSelectMemoryItem,
}: EdgesSectionProps) {
  return (
    <div className="rounded-lg border border-default dark:border-gray-700 p-4">
      <div className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
        {t('outgoingEdges' as any) || 'Outgoing Edges'}
      </div>
      <div className="space-y-3">
        {outgoingEdges.length === 0 ? (
          <div className="text-sm text-secondary dark:text-gray-400">
            {t('noOutgoingEdges' as any) || 'No outgoing edges recorded.'}
          </div>
        ) : (
          outgoingEdges.map((edge) => (
            <div key={edge.id} className="rounded bg-surface-accent dark:bg-gray-900/40 p-3">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
                  {prettyLabel(edge.edge_type)}
                </span>
                <span className="text-xs text-secondary dark:text-gray-400">
                  {formatLocalDateTime(edge.created_at)}
                </span>
              </div>
              <button
                onClick={() => onSelectMemoryItem(edge.to_memory_id)}
                className="text-xs text-blue-700 dark:text-blue-300 font-mono break-all hover:underline"
              >
                {edge.to_memory_id}
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
