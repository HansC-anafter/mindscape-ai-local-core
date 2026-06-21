import type { TimelineItem, UnifiedEvent } from './types';

export function eventToTimelineItem(event: UnifiedEvent): TimelineItem | null {
  const importantTypes = [
    'decision_required',
    'run_state_changed',
    'artifact_created',
    'tool_result',
    'playbook_step',
    'branch_proposed',
    'meeting_start',
    'memory_writeback',
  ];

  if (!importantTypes.includes(event.type)) {
    return null;
  }

  let summary = '';
  let targetCardId: string | undefined;
  let navigationHref: string | undefined;

  switch (event.type) {
    case 'decision_required':
      summary = `Decision required: ${event.payload.selected_playbook_code || 'Confirm decision'}`;
      targetCardId = event.payload.decision_id;
      break;
    case 'run_state_changed':
      summary = `Execution state: ${event.payload.previous_state} → ${event.payload.new_state}`;
      break;
    case 'artifact_created':
      summary = `Artifact created: ${event.payload.title || 'New artifact'}`;
      break;
    case 'tool_result':
      summary = `Tool execution: ${event.payload.tool_fqn || 'Tool call'}`;
      break;
    case 'playbook_step':
      summary = `Playbook step: ${event.payload.step_id || 'Step execution'}`;
      break;
    case 'branch_proposed':
      summary = `Branch proposed: ${event.payload.alternatives?.length || 0} candidate plans`;
      targetCardId = event.payload.branch_id;
      break;
    case 'meeting_start': {
      const profile = event.payload.workflow_evidence_profile || 'general';
      const scope = event.payload.workflow_evidence_scope || 'none';
      summary = `Meeting started: ${event.payload.meeting_type || 'general'} · ${profile} packet from ${scope} scope`;
      if (event.workspace_id && event.payload.meeting_session_id) {
        const params = new URLSearchParams();
        params.set('session_id', event.payload.meeting_session_id);
        if (event.project_id) {
          params.set('project_id', event.project_id);
        }
        navigationHref = `/workspaces/${event.workspace_id}/meetings?${params.toString()}`;
      }
      break;
    }
    case 'memory_writeback':
      summary = `Governed memory linked: ${event.payload.memory_item_id || 'canonical item created'}`;
      if (event.workspace_id && event.payload.memory_item_id) {
        const params = new URLSearchParams();
        params.set('tab', 'memory');
        params.set('memoryId', event.payload.memory_item_id);
        navigationHref = `/workspaces/${event.workspace_id}/governance?${params.toString()}`;
      }
      break;
    default:
      summary = `${event.type} event`;
  }

  return {
    id: event.id,
    timestamp: event.timestamp,
    type: event.type,
    summary,
    clickable: !!targetCardId || !!navigationHref,
    targetCardId,
    navigationHref,
    memoryItemId: event.payload.memory_item_id,
    memoryLifecycleStatus: event.payload.lifecycle_status,
    memoryVerificationStatus: event.payload.verification_status,
    meetingEvidenceProfile: event.payload.workflow_evidence_profile,
    meetingEvidenceScope: event.payload.workflow_evidence_scope,
    meetingEvidenceSelectedLines: event.payload.workflow_evidence_selected_line_count,
    meetingEvidenceTotalBudget: event.payload.workflow_evidence_total_line_budget,
    meetingEvidenceTotalCandidates: event.payload.workflow_evidence_total_candidate_count,
    meetingEvidenceTotalDropped: event.payload.workflow_evidence_total_dropped_count,
    meetingEvidenceRenderedSections:
      event.payload.workflow_evidence_rendered_section_count,
    meetingEvidenceBudgetUtilizationRatio:
      event.payload.workflow_evidence_budget_utilization_ratio,
  };
}
