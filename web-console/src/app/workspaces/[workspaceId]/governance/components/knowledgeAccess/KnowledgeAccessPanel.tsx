'use client';

import { useState } from 'react';

import { KnowledgeAccessDetail } from './KnowledgeAccessDetail';
import { KnowledgeAccessReviewDialog } from './KnowledgeAccessReviewDialog';
import { KnowledgeAccessSummaryList } from './KnowledgeAccessSummaryList';
import { useKnowledgeAccess } from './useKnowledgeAccess';

type Props = {
  workspaceId: string;
};

export function KnowledgeAccessPanel({ workspaceId }: Props) {
  const [reviewOpen, setReviewOpen] = useState(false);
  const {
    summary,
    detail,
    selectedResourceId,
    summaryLoading,
    detailLoading,
    mutationLoading,
    actionReceipt,
    error,
    selectResource,
    replace,
    runAction,
  } = useKnowledgeAccess(workspaceId);

  if (summaryLoading) {
    return <div className="py-8 text-center text-sm text-gray-500">Loading knowledge access…</div>;
  }

  if (!summary) {
    return (
      <div className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-950/30 dark:text-red-200">
        {error || 'Knowledge access could not be loaded.'}
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="knowledge-access-panel">
      <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          Knowledge access
        </h2>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
          Review per-resource human grants, GraphRAG projection state, and truthful modality channel coverage.
        </p>
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-600 dark:text-gray-300">
          <span>{summary.total_count} resources</span>
          {Object.entries(summary.state_counts).map(([state, count]) => (
            <span key={state} className="rounded bg-gray-100 px-2 py-1 dark:bg-gray-700">
              {state}: {count}
            </span>
          ))}
          <span className="rounded bg-emerald-50 px-2 py-1 text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-200">
            polling: off
          </span>
        </div>
      </div>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950/30 dark:text-red-200">
          {error}
        </div>
      )}

      {summary.items.length === 0 ? (
        <div className="rounded border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500 dark:border-gray-700">
          No retrievable knowledge resources are registered for this workspace.
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(280px,0.8fr)_minmax(0,1.5fr)]">
          <KnowledgeAccessSummaryList
            items={summary.items}
            selectedResourceId={selectedResourceId}
            onSelect={(resourceId) => void selectResource(resourceId)}
          />
          <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
            {detailLoading ? (
              <div className="py-8 text-center text-sm text-gray-500">Loading selected resource…</div>
            ) : detail ? (
              <KnowledgeAccessDetail
                detail={detail}
                onEdit={() => setReviewOpen(true)}
                onAction={(action) => void runAction(action)}
                actionReceipt={actionReceipt}
                actionPending={mutationLoading}
              />
            ) : (
              <div className="py-8 text-center text-sm text-gray-500">
                Select one resource to load its bounded detail.
              </div>
            )}
          </div>
        </div>
      )}

      {reviewOpen && detail && (
        <KnowledgeAccessReviewDialog
          detail={detail}
          saving={mutationLoading}
          onCancel={() => setReviewOpen(false)}
          onSubmit={async (command) => {
            await replace(command);
            setReviewOpen(false);
          }}
        />
      )}
    </div>
  );
}
