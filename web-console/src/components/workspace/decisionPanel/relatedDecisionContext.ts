import type { RelatedDecisionContext } from './types';

export const emptyRelatedDecisionContext: RelatedDecisionContext = {
  memoryId: null,
  meetingSessionId: null,
};

export function getRelatedDecisionContextFromMeetingPayload(
  payload: any
): Partial<RelatedDecisionContext> {
  return {
    meetingSessionId: payload.meeting_session_id || null,
    workflowEvidenceProfile: payload.workflow_evidence_profile,
    workflowEvidenceScope: payload.workflow_evidence_scope,
    workflowEvidenceSelectedLines: payload.workflow_evidence_selected_line_count,
    workflowEvidenceTotalBudget: payload.workflow_evidence_total_line_budget,
    workflowEvidenceTotalCandidates: payload.workflow_evidence_total_candidate_count,
    workflowEvidenceTotalDropped: payload.workflow_evidence_total_dropped_count,
    workflowEvidenceRenderedSections: payload.workflow_evidence_rendered_section_count,
    workflowEvidenceUtilizationRatio: payload.workflow_evidence_budget_utilization_ratio,
  };
}

export function getRelatedDecisionContextFromEvents(
  latestMeetingStartEvent: any,
  latestMemoryEvent: any
): RelatedDecisionContext {
  return {
    ...emptyRelatedDecisionContext,
    ...getRelatedDecisionContextFromMeetingPayload(latestMeetingStartEvent?.payload || {}),
    memoryId: latestMemoryEvent?.payload?.memory_item_id || null,
    memoryLifecycleStatus: latestMemoryEvent?.payload?.lifecycle_status,
    memoryVerificationStatus: latestMemoryEvent?.payload?.verification_status,
  };
}
