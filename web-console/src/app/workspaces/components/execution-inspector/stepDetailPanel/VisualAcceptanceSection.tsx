import React from 'react';

import type { ReviewBundleArtifact } from '../types/execution';
import {
  buildCapabilityWorkbenchHref,
  capabilitySupportsWorkbenchRoute,
} from './stepDetailPanelState';

export function VisualAcceptanceSection({
  apiUrl,
  installedCapabilities,
  reviewBundleArtifacts,
  reviewBundlesLoading,
  selectedReviewBundle,
  workspaceId,
  onReviewBundleSelect,
}: {
  apiUrl?: string;
  installedCapabilities: any[];
  reviewBundleArtifacts: ReviewBundleArtifact[];
  reviewBundlesLoading: boolean;
  selectedReviewBundle: ReviewBundleArtifact | null;
  workspaceId?: string;
  onReviewBundleSelect: (artifactId: string) => void;
}) {
  return (
    <div className="mt-4">
      <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
        Visual Acceptance
      </h4>
      {reviewBundlesLoading ? (
        <div className="rounded border border-default bg-surface-accent p-4 text-xs text-gray-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
          Loading review bundles...
        </div>
      ) : !reviewBundleArtifacts.length ? (
        <div className="rounded border border-dashed border-default bg-surface-accent p-4 text-xs text-gray-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
          This execution does not have a matching visual acceptance bundle yet.
        </div>
      ) : (
        <div className="space-y-3">
          <div className="grid gap-2 md:grid-cols-2">
            {reviewBundleArtifacts.map((artifact) => {
              const content = artifact.content || {};
              const latestDecision = content.latest_review_decision?.decision || content.status;
              const isSelected = artifact.id === selectedReviewBundle?.id;
              return (
                <button
                  key={artifact.id}
                  type="button"
                  onClick={() => onReviewBundleSelect(artifact.id)}
                  className={`rounded border px-3 py-3 text-left transition ${
                    isSelected
                      ? 'border-blue-300 bg-blue-50 dark:border-blue-700 dark:bg-blue-950/20'
                      : 'border-default bg-surface-accent hover:bg-tertiary dark:border-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700'
                  }`}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {content.scene_id || artifact.name}
                    </span>
                    <span className="rounded-full border border-default px-2 py-0.5 text-[10px] text-gray-600 dark:border-gray-700 dark:text-gray-300">
                      {content.source_kind || 'bundle'}
                    </span>
                  </div>
                  <div className="mt-2 space-y-1 text-[11px] text-gray-500 dark:text-gray-400">
                    <div>run_id={content.run_id || '-'}</div>
                    <div>scene_id={content.scene_id || '-'}</div>
                    <div>decision={latestDecision || '-'}</div>
                  </div>
                </button>
              );
            })}
          </div>

          {selectedReviewBundle ? (
            <div className="rounded border border-default bg-surface-accent p-4 dark:border-gray-700 dark:bg-gray-800">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                    {selectedReviewBundle.content?.scene_id || selectedReviewBundle.name || selectedReviewBundle.id}
                  </div>
                  <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    artifact={selectedReviewBundle.id} / bundle={selectedReviewBundle.content?.review_bundle_id || '-'}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {renderWorkbenchLink({
                    installedCapabilities,
                    selectedReviewBundle,
                    workspaceId,
                  })}
                  {workspaceId && apiUrl ? (
                    <a
                      href={`${apiUrl}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/artifacts/${encodeURIComponent(selectedReviewBundle.id)}/file`}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded border border-default bg-white px-3 py-2 text-xs font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800"
                    >
                      Open Manifest
                    </a>
                  ) : null}
                </div>
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <VisualAcceptanceMetric title="State" lines={[
                  `review=${selectedReviewBundle.content?.latest_review_decision?.decision || selectedReviewBundle.content?.status || '-'}`,
                  `source=${selectedReviewBundle.content?.source_kind || '-'}`,
                ]} />
                <VisualAcceptanceMetric title="Lineage" lines={[
                  `package=${selectedReviewBundle.content?.package_id || '-'}`,
                  `preset=${selectedReviewBundle.content?.preset_id || '-'}`,
                ]} />
                <VisualAcceptanceMetric title="Owner" lines={[
                  selectedReviewBundle.content?.owning_capability_code || '-',
                  `run=${selectedReviewBundle.content?.run_id || '-'}`,
                ]} />
                <VisualAcceptanceMetric title="Workload" lines={[
                  `impact=${String(selectedReviewBundle.content?.scene_context?.object_workload_snapshot?.impact_region_mode || '-')}`,
                  `gate=${String(selectedReviewBundle.content?.scene_context?.object_workload_snapshot?.quality_gate_state || '-')}`,
                ]} />
              </div>

              <div className="mt-4 text-xs text-gray-500 dark:text-gray-400">
                Detailed compare, checklist, and decision workflow now live in the capability-owned workbench. Execution Inspector stays as a fallback bundle viewer and launcher.
              </div>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

function renderWorkbenchLink({
  installedCapabilities,
  selectedReviewBundle,
  workspaceId,
}: {
  installedCapabilities: any[];
  selectedReviewBundle: ReviewBundleArtifact;
  workspaceId?: string;
}) {
  const capabilityCode = selectedReviewBundle.content?.owning_capability_code;
  if (!capabilitySupportsWorkbenchRoute(installedCapabilities, capabilityCode)) {
    return null;
  }
  const href = buildCapabilityWorkbenchHref({
    workspaceId,
    capabilityCode,
    artifactId: selectedReviewBundle.id,
    runId: selectedReviewBundle.content?.run_id,
    sceneId: selectedReviewBundle.content?.scene_id,
  });
  if (!href) {
    return null;
  }
  return (
    <a
      href={href}
      className="rounded border border-blue-300 bg-blue-50 px-3 py-2 text-xs font-medium text-blue-700 transition hover:border-blue-400 hover:bg-blue-100 dark:border-blue-700 dark:bg-blue-950/20 dark:text-blue-200"
    >
      Open Pack Workbench
    </a>
  );
}

function VisualAcceptanceMetric({
  lines,
  title,
}: {
  lines: string[];
  title: string;
}) {
  return (
    <div className="rounded border border-default bg-white px-3 py-3 text-xs text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300">
      <div className="font-medium text-gray-900 dark:text-gray-100">{title}</div>
      {lines.map((line, index) => (
        <div key={`${title}-${index}`} className={index === 0 ? 'mt-2' : 'mt-1'}>
          {line}
        </div>
      ))}
    </div>
  );
}
