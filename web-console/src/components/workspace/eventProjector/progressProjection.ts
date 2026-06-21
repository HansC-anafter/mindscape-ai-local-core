import type { ExecutionStatus, UnifiedEvent } from './types';

export function eventToProgress(
  events: UnifiedEvent[]
): { status: ExecutionStatus; artifacts: any[] } {
  const stateEvents = events.filter(e => e.type === 'run_state_changed');
  const latestState = stateEvents[stateEvents.length - 1];

  const blockerEvents = events.filter(e =>
    e.type === 'decision_required' &&
    e.payload.requires_user_approval
  );

  let executionStatus: ExecutionStatus = {
    status: 'UNKNOWN',
    message: 'Status unknown',
  };

  if (blockerEvents.length > 0) {
    const reasons = blockerEvents.map(e => {
      const reasons: string[] = [];
      if (e.payload.missing_inputs && e.payload.missing_inputs.length > 0) {
        reasons.push(`Missing inputs: ${e.payload.missing_inputs.join(', ')}`);
      }
      if (e.payload.clarification_questions && e.payload.clarification_questions.length > 0) {
        reasons.push('Clarification needed');
      }
      if (e.payload.conflicts && e.payload.conflicts.length > 0) {
        reasons.push(`Conflicts: ${e.payload.conflicts.map(c => c.type).join(', ')}`);
      }
      return reasons.join('; ');
    }).filter(Boolean);

    const uniqueReasons = [...new Set(reasons)];

    executionStatus = {
      status: 'WAITING_HUMAN',
      message: `Waiting for your confirmation (${blockerEvents.length} blockers)`,
      detailedMessage: uniqueReasons.length > 0
        ? `Blocking reasons: ${uniqueReasons.join('; ')}`
        : 'Your confirmation is required to continue',
      blockers: blockerEvents.map(e => ({
        id: e.payload.decision_id || e.id,
        reason: uniqueReasons[0] || 'Your confirmation required',
        type: e.payload.card_type || 'decision',
      })),
    };
  } else if (latestState) {
    const newState = latestState.payload.new_state;
    if (newState === 'READY') {
      executionStatus = {
        status: 'READY',
        message: 'Ready (one-click start available)',
      };
    } else if (newState === 'RUNNING') {
      executionStatus = {
        status: 'RUNNING',
        message: 'Executing...',
      };
    } else if (newState === 'DONE') {
      executionStatus = {
        status: 'DONE',
        message: 'Execution completed',
      };
    }
  }

  const artifactEvents = events.filter(e => e.type === 'artifact_created');
  const artifacts = artifactEvents.map(e => ({
    id: e.payload.artifact_id,
    type: e.payload.artifact_type,
    title: e.payload.title,
    summary: e.payload.summary,
    file_path: e.payload.file_path,
    storage_ref: e.payload.storage_ref,
    timestamp: e.timestamp,
  }));

  return {
    status: executionStatus,
    artifacts,
  };
}
