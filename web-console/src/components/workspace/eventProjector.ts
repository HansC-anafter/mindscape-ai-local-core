/**
 * Event Projector
 *
 * Projects unified event stream to UI components:
 * - Right panel: DECISION_REQUIRED events → blocker cards
 * - Left panel: RUN_STATE_CHANGED / ARTIFACT_CREATED events → progress
 * - Center panel: All events → timeline
 */

import { DecisionCardData } from './DecisionCard';

/**
 * Unified event type (maps to backend EventType)
 */
export interface UnifiedEvent {
  id: string;
  type: string;
  timestamp: string;
  actor: string;
  workspace_id?: string;
  project_id?: string;
  profile_id: string;
  payload: {
    // DECISION_REQUIRED
    decision_id?: string;
    intent_log_id?: string;
    requires_user_approval?: boolean;
    can_auto_execute?: boolean;
    missing_inputs?: string[];
    clarification_questions?: string[];
    conflicts?: Array<{ type: string; description: string; layers: string[] }>;
    blocking_steps?: string[];
    card_type?: 'decision' | 'input' | 'review' | 'assignment';
    priority?: 'blocker' | 'high' | 'normal';
    selected_playbook_code?: string;
    rationale?: string;

    // RUN_STATE_CHANGED
    execution_id?: string;
    previous_state?: string;
    new_state?: 'WAITING_HUMAN' | 'READY' | 'RUNNING' | 'DONE';
    reason?: string;
    playbook_code?: string;
    blocker_count?: number;

    // ARTIFACT_CREATED
    artifact_id?: string;
    artifact_type?: string;
    title?: string;
    summary?: string;
    file_path?: string;
    storage_ref?: string;

    // TOOL_RESULT
    tool_fqn?: string;
    tool_call_id?: string;
    step_id?: string;
    status?: string;
    result_summary?: string;

    // BRANCH_PROPOSED
    branch_id?: string;
    alternatives?: Array<{
      playbook_code: string;
      confidence: number;
      rationale: string;
      differences?: string[];
    }>;
    recommended_branch?: string;
  };
  entity_ids?: Record<string, string>;
  metadata?: Record<string, any>;
}

/**
 * Execution status
 */
export interface ExecutionStatus {
  status: 'WAITING_HUMAN' | 'READY' | 'RUNNING' | 'DONE' | 'UNKNOWN';
  message: string;
  detailedMessage?: string;
  blockers?: Array<{
    id: string;
    reason: string;
    type: string;
  }>;
  readyCount?: number;
}

/**
 * Timeline item
 */
export interface TimelineItem {
  id: string;
  timestamp: string;
  type: string;
  summary: string;
  clickable: boolean;
  targetCardId?: string;
}

/**
 * Project DECISION_REQUIRED or BRANCH_PROPOSED event to blocker card
 */
export function eventToBlockerCard(event: UnifiedEvent): DecisionCardData | null {
  if (event.type !== 'decision_required' && event.type !== 'branch_proposed') {
    return null;
  }

  if (event.type === 'branch_proposed') {
    return eventToBranchCard(event);
  }

  const payload = event.payload;
  const blockedSteps = payload.blocking_steps || [];

  const reasons: string[] = [];
  if (payload.requires_user_approval) {
    reasons.push('User approval required');
  }
  if (payload.missing_inputs && payload.missing_inputs.length > 0) {
    reasons.push(`Missing inputs: ${payload.missing_inputs.join(', ')}`);
  }
  if (payload.clarification_questions && payload.clarification_questions.length > 0) {
    reasons.push('Clarification needed');
  }
  if (payload.conflicts && payload.conflicts.length > 0) {
    reasons.push(`Conflicts: ${payload.conflicts.map(c => c.type || c.description || 'Unknown').join(', ')}`);
  }

  let status: DecisionCardData['status'] = 'OPEN';
  if (payload.clarification_questions && payload.clarification_questions.length > 0) {
    status = 'NEED_INFO';
  } else if (payload.missing_inputs && payload.missing_inputs.length > 0) {
    status = 'NEED_INFO';
  } else if (payload.can_auto_execute) {
    status = 'READY';
  }

  const title = payload.selected_playbook_code || 'Decision Required';
  let description = payload.rationale || '';
  if (payload.clarification_questions && payload.clarification_questions.length > 0) {
    description += `\n\nClarification needed: ${payload.clarification_questions.join(', ')}`;
  }
  if (payload.missing_inputs && payload.missing_inputs.length > 0) {
    description += `\n\nMissing inputs: ${payload.missing_inputs.join(', ')}`;
  }

  const actionType = payload.card_type === 'input' ? 'upload' :
                     payload.card_type === 'review' ? 'review' :
                     'confirm';
  const actionLabel = payload.card_type === 'input' ? 'Provide Missing Inputs' :
                      payload.card_type === 'review' ? 'Resolve Conflicts' :
                      'Confirm Decision';

  const handleAction = async () => {
    const decisionId = payload.decision_id || event.id;
    window.dispatchEvent(new CustomEvent('decision-card-action', {
      detail: {
        decisionId,
        actionType,
        event,
        payload,
      },
    }));
  };

  return {
    id: payload.decision_id || event.id,
    type: (payload.card_type as any) || 'decision',
    title,
    description,
    blocks: {
      steps: blockedSteps,
      count: blockedSteps.length,
      stepNames: blockedSteps,
    },
    action: {
      type: actionType as any,
      label: actionLabel,
      onClick: handleAction,
    },
    result: {
      autoRun: payload.can_auto_execute || false,
      message: payload.can_auto_execute
        ? 'Execution will start automatically after confirmation'
        : 'Manual execution trigger required after confirmation',
    },
    expandable: {
      evidence: {
        decision_id: payload.decision_id,
        conflicts: payload.conflicts,
      },
      clarificationQuestions: payload.clarification_questions,
    },
    status,
    priority: (payload.priority as any) || 'normal',
  };
}

/**
 * Project BRANCH_PROPOSED event to branch selection card (ToT)
 */
function eventToBranchCard(event: UnifiedEvent): DecisionCardData | null {
  const payload = event.payload;

  if (!payload.alternatives || payload.alternatives.length === 0) {
    return null;
  }

  const title = `Select Execution Plan (${payload.alternatives.length} candidates)`;
  let description = 'Multiple feasible execution plans, please select one to continue';

  const differences = payload.alternatives
    .flatMap((alt: any) => alt.differences || [])
    .filter((d: string, i: number, arr: string[]) => arr.indexOf(d) === i)
    .slice(0, 3);

  if (differences.length > 0) {
    description += `\n\nKey differences: ${differences.join(', ')}`;
  }

  const handleAction = async () => {
    const branchId = payload.branch_id || event.id;
    window.dispatchEvent(new CustomEvent('branch-selection', {
      detail: {
        branchId,
        alternatives: payload.alternatives,
        recommendedBranch: payload.recommended_branch,
        event,
      },
    }));
  };

  return {
    id: payload.branch_id || event.id,
    type: 'review',
    title,
    description,
    blocks: {
      steps: [],
      count: 0,
      stepNames: [],
    },
    action: {
      type: 'select',
      label: 'Select Plan',
      onClick: handleAction,
    },
    result: {
      autoRun: false,
      message: 'Selected plan will be used to continue execution',
    },
    expandable: {
      evidence: {
        alternatives: payload.alternatives,
        recommendedBranch: payload.recommended_branch,
      },
      risk: payload.alternatives.length > 3
        ? 'Multiple plans available, compare differences carefully'
        : undefined,
    },
    status: 'OPEN',
    priority: 'high',
  };
}

/**
 * Project RUN_STATE_CHANGED / ARTIFACT_CREATED events to progress
 */
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

/**
 * Project all events to timeline
 */
export function eventToTimelineItem(event: UnifiedEvent): TimelineItem | null {
  const importantTypes = [
    'decision_required',
    'run_state_changed',
    'artifact_created',
    'tool_result',
    'playbook_step',
    'branch_proposed',
  ];

  if (!importantTypes.includes(event.type)) {
    return null;
  }

  let summary = '';
  let targetCardId: string | undefined;

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
    default:
      summary = `${event.type} event`;
  }

  return {
    id: event.id,
    timestamp: event.timestamp,
    type: event.type,
    summary,
    clickable: !!targetCardId,
    targetCardId,
  };
}

/**
 * Subscribe to event stream (SSE)
 */
export function subscribeEventStream(
  workspaceId: string,
  options: {
    apiUrl?: string;
    eventTypes?: string[];
    projectId?: string;
    onEvent: (event: UnifiedEvent) => void;
    onError?: (error: Error) => void;
  }
): () => void {
  const { apiUrl = '', eventTypes, projectId, onEvent, onError } = options;

  const params = new URLSearchParams();
  if (eventTypes && eventTypes.length > 0) {
    params.append('event_types', eventTypes.join(','));
  }
  if (projectId) {
    params.append('project_id', projectId);
  }

  const baseUrl = apiUrl || (typeof window !== 'undefined' ? window.location.origin : '');
  const url = `${baseUrl}/api/v1/workspaces/${workspaceId}/events/stream?${params.toString()}`;

  console.log('[EventStream] Connecting to:', url);

  const eventSource = new EventSource(url);

  let hasLoggedConnection = false;
  const handleEvent = (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);

      if (data.type === 'connected') {
        if (!hasLoggedConnection) {
          console.log('[EventStream] Connected to workspace:', data.workspace_id);
          hasLoggedConnection = true;
        }
        return;
      }

      if (data.type === 'error') {
        console.error('[EventStream] Error:', data.message);
        if (onError) {
          onError(new Error(data.message));
        }
        return;
      }

      const event: UnifiedEvent = {
        id: data.id,
        type: data.type,
        timestamp: data.timestamp,
        actor: data.actor,
        workspace_id: data.workspace_id,
        project_id: data.project_id,
        profile_id: data.profile_id,
        payload: data.payload,
        entity_ids: data.entity_ids,
        metadata: data.metadata,
      };

      onEvent(event);
    } catch (err) {
      console.error('[EventStream] Failed to parse event:', err, e.data);
      if (onError) {
        onError(err as Error);
      }
    }
  };

  eventSource.onmessage = handleEvent;

  const importantTypes = [
    'message',
    'tool_call',
    'tool_result',
    'playbook_step',
    'decision_required',
    'branch_proposed',
    'run_state_changed',
    'artifact_created',
    'artifact_updated',
  ];

  for (const eventType of importantTypes) {
    eventSource.addEventListener(eventType, handleEvent);
  }

  eventSource.onerror = (err) => {
    const target = err.target as EventSource;
    if (target?.readyState === EventSource.CLOSED) {
      console.warn('[EventStream] Connection closed, will reconnect automatically:', url);
    } else if (target?.readyState === EventSource.CONNECTING) {
      console.log('[EventStream] Reconnecting...');
    } else {
      console.error('[EventStream] Connection error:', err);
      if (onError && target?.readyState !== EventSource.CONNECTING) {
        onError(new Error('Event stream connection error'));
      }
    }
  };

  eventSource.onopen = () => {
    console.log('[EventStream] Connection opened:', url);
  };

  return () => {
    eventSource.close();
  };
}

