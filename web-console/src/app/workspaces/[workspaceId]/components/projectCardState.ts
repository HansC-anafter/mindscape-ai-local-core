import type { Project } from '@/types/project';
import { parseServerTimestamp } from '@/lib/time';
import type {
  ProjectCardData,
  ProjectCardProgressValues,
  WorkflowEvidenceValues,
} from './projectCardTypes';

export const EMPTY_WORKFLOW_EVIDENCE: WorkflowEvidenceValues = {
  profile: null,
  scope: null,
  selectedLineCount: null,
  totalLineBudget: null,
  totalCandidateCount: null,
  totalDroppedCount: null,
  renderedSectionCount: null,
  budgetUtilizationRatio: null,
};

export function formatRelativeTime(timestamp: string): string {
  const date = parseServerTimestamp(timestamp);
  if (!date) return timestamp;
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins} min ago`;
  if (diffHours < 24) return `${diffHours} hr ago`;
  if (diffDays < 7) return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
  return date.toLocaleDateString('en-US');
}

export function formatProjectCreatedDate(timestamp?: string): string {
  if (!timestamp) return '';
  return parseServerTimestamp(timestamp)?.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }) ?? '';
}

export function isMeetingEnabled(cardData: ProjectCardData | null, project: Project): boolean {
  return Boolean(cardData?.meeting?.enabled ?? project.metadata?.meeting_enabled);
}

export function isMeetingActive(cardData: ProjectCardData | null): boolean {
  return Boolean(cardData?.meeting?.active);
}

export function workflowEvidenceFromEventPayload(payload: Record<string, any>): WorkflowEvidenceValues {
  return {
    profile: payload.workflow_evidence_profile || null,
    scope: payload.workflow_evidence_scope || null,
    selectedLineCount: payload.workflow_evidence_selected_line_count ?? null,
    totalLineBudget: payload.workflow_evidence_total_line_budget ?? null,
    totalCandidateCount: payload.workflow_evidence_total_candidate_count ?? null,
    totalDroppedCount: payload.workflow_evidence_total_dropped_count ?? null,
    renderedSectionCount: payload.workflow_evidence_rendered_section_count ?? null,
    budgetUtilizationRatio: payload.workflow_evidence_budget_utilization_ratio ?? null,
  };
}

export function workflowEvidenceFromSession(session: any): WorkflowEvidenceValues {
  const diagnostics = session?.metadata?.workflow_evidence_diagnostics || {};
  return {
    profile: diagnostics.profile || null,
    scope: diagnostics.scope || null,
    selectedLineCount: diagnostics.selected_line_count ?? null,
    totalLineBudget: diagnostics.total_line_budget ?? null,
    totalCandidateCount: diagnostics.total_candidate_count ?? null,
    totalDroppedCount: diagnostics.total_dropped_count ?? null,
    renderedSectionCount: diagnostics.rendered_section_count ?? null,
    budgetUtilizationRatio: diagnostics.budget_utilization_ratio ?? null,
  };
}

export function meetingDataForToggle(
  previous: Partial<NonNullable<ProjectCardData['meeting']>> | undefined,
  enabled: boolean,
): ProjectCardData['meeting'] {
  return {
    enabled,
    active: enabled ? true : false,
    session_id: previous?.session_id ?? null,
    status: enabled ? 'active' : null,
    round_count: previous?.round_count ?? 0,
    max_rounds: previous?.max_rounds ?? 5,
    action_item_count: previous?.action_item_count ?? 0,
    last_activity: previous?.last_activity ?? null,
    minutes_preview: previous?.minutes_preview ?? '',
  };
}

export function calculateProjectProgress(cardData: ProjectCardData | null): ProjectCardProgressValues {
  const progressPercentage = cardData
    ? Math.max(cardData.progress.current, 1)
    : 1;
  const totalPlaybooks = cardData?.stats.totalPlaybooks || 0;
  const nextNextTaskProgress = totalPlaybooks > 0
    ? Math.min(progressPercentage + (200 / totalPlaybooks), 100)
    : progressPercentage;
  const scanRangeStart = progressPercentage;
  const scanRangeEnd = nextNextTaskProgress;

  return {
    progressPercentage,
    scanRangeStart,
    scanRangeEnd,
    scanRangeWidth: scanRangeEnd - scanRangeStart,
  };
}

export function filterEventsForProject(
  events: ProjectCardData['recentEvents'],
  projectId: string,
): ProjectCardData['recentEvents'] {
  return events.filter((event) => {
    if (event.projectId) {
      return event.projectId === projectId;
    }
    return true;
  });
}

export function firstExecutionId(cardData: ProjectCardData | null): string | null {
  if (!cardData || cardData.stats.runningExecutions <= 0) {
    return null;
  }
  const firstEvent = cardData.recentEvents?.[0];
  return firstEvent?.executionId || null;
}

export function buildMeetingRoute(workspaceId: string, projectId: string, sessionId?: string | null): string {
  const params = new URLSearchParams(
    sessionId
      ? { project_id: projectId, session_id: sessionId }
      : { project_id: projectId },
  );
  return `/workspaces/${workspaceId}/meetings?${params.toString()}`;
}

export function buildMeetingScenePatchRoute(workspaceId: string, projectId: string, sessionId?: string | null): string {
  const params = new URLSearchParams({ project_id: projectId, open_patch: '1' });
  if (sessionId) {
    params.set('session_id', sessionId);
  }
  return `/workspaces/${workspaceId}/meetings?${params.toString()}`;
}

export function buildExecutionTimelineRoute(workspaceId: string, projectId: string): string {
  return `/workspaces/${workspaceId}/executions/timeline?project_id=${projectId}`;
}

export function buildMeetingMessage(projectTitle: string, projectType: string): string {
  return `[Meeting Started] Start project meeting for "${projectTitle}" (${projectType})`;
}
