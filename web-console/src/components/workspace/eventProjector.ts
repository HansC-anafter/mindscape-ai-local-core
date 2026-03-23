/**
 * Event Projector
 *
 * Projects unified event stream to UI components:
 * - Right panel: DECISION_REQUIRED events → blocker cards
 * - Left panel: RUN_STATE_CHANGED / ARTIFACT_CREATED events → progress
 * - Center panel: All events → timeline
 */

import { DecisionCardData } from './DecisionCard';
import { getApiBaseUrl } from '@/lib/api-url';

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
  thread_id?: string;
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
    card_type?: 'decision' | 'input' | 'review' | 'assignment' | 'governance';
    priority?: 'blocker' | 'high' | 'normal';
    selected_playbook_code?: string;
    rationale?: string;

    // GOVERNANCE_DECISION
    governance_decision?: {
      type: 'cost_exceeded' | 'node_rejected' | 'policy_violation' | 'preflight_failed';
      layer: 'cost' | 'node' | 'policy' | 'preflight';
      approved: boolean;
      reason?: string;
      cost_governance?: {
        estimated_cost: number;
        quota_limit: number;
        current_usage: number;
        downgrade_suggestion?: {
          profile: string;
          estimated_cost: number;
        };
      };
      node_governance?: {
        rejection_reason: 'blacklist' | 'risk_label' | 'throttle';
        affected_playbooks?: string[];
        alternatives?: string[];
      };
      policy_violation?: {
        violation_type: 'role' | 'data_domain' | 'pii';
        policy_id?: string;
        violation_items: string[];
        request_permission_url?: string;
      };
      preflight_failure?: {
        missing_inputs: string[];
        missing_credentials: string[];
        environment_issues: string[];
        recommended_alternatives?: string[];
      };
    };

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

  // Check for governance decision
  if (payload.governance_decision) {
    return governanceDecisionToCard(event);
  }
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
        clarificationQuestions: payload.clarification_questions,
      },
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
 * Project governance decision event to governance decision card
 */
function governanceDecisionToCard(event: UnifiedEvent): DecisionCardData | null {
  const payload = event.payload;
  const govDecision = payload.governance_decision;

  if (!govDecision) {
    return null;
  }

  const decisionId = payload.decision_id || event.id;
  let title = 'Governance Decision Required';
  let description = govDecision.reason || 'A governance check has blocked this execution';
  let status: DecisionCardData['status'] = govDecision.approved ? 'OPEN' : 'REJECTED';
  let priority: DecisionCardData['priority'] = 'blocker';

  // Build title and description based on governance type
  switch (govDecision.type) {
    case 'cost_exceeded':
      title = 'Cost Limit Exceeded';
      if (govDecision.cost_governance) {
        const { estimated_cost, quota_limit, current_usage, downgrade_suggestion } = govDecision.cost_governance;
        description = `Estimated cost ($${estimated_cost.toFixed(2)}) exceeds your daily quota ($${quota_limit.toFixed(2)}). Current usage: $${current_usage.toFixed(2)}.`;
        if (downgrade_suggestion) {
          description += `\n\nSuggestion: Use ${downgrade_suggestion.profile} profile (estimated cost: $${downgrade_suggestion.estimated_cost.toFixed(2)})`;
        }
      }
      break;
    case 'node_rejected':
      title = 'Playbook Not Allowed';
      if (govDecision.node_governance) {
        const { rejection_reason, affected_playbooks, alternatives } = govDecision.node_governance;
        description = `Playbook rejected: ${rejection_reason}`;
        if (affected_playbooks && affected_playbooks.length > 0) {
          description += `\n\nAffected playbooks: ${affected_playbooks.join(', ')}`;
        }
        if (alternatives && alternatives.length > 0) {
          description += `\n\nAlternatives: ${alternatives.join(', ')}`;
        }
      }
      break;
    case 'policy_violation':
      title = 'Policy Violation';
      if (govDecision.policy_violation) {
        const { violation_type, violation_items } = govDecision.policy_violation;
        description = `Policy violation detected: ${violation_type}`;
        if (violation_items && violation_items.length > 0) {
          description += `\n\nViolations: ${violation_items.join(', ')}`;
        }
      }
      break;
    case 'preflight_failed':
      title = 'Preflight Check Failed';
      if (govDecision.preflight_failure) {
        const { missing_inputs, missing_credentials, environment_issues } = govDecision.preflight_failure;
        const issues: string[] = [];
        if (missing_inputs && missing_inputs.length > 0) {
          issues.push(`Missing inputs: ${missing_inputs.join(', ')}`);
        }
        if (missing_credentials && missing_credentials.length > 0) {
          issues.push(`Missing credentials: ${missing_credentials.join(', ')}`);
        }
        if (environment_issues && environment_issues.length > 0) {
          issues.push(`Environment issues: ${environment_issues.join(', ')}`);
        }
        description = issues.join('\n');
        status = 'NEED_INFO';
      }
      break;
  }

  const handleAction = async () => {
    window.dispatchEvent(new CustomEvent('decision-card-action', {
      detail: {
        decisionId,
        actionType: govDecision.approved ? 'confirm' : 'reject',
        event,
        payload,
      },
    }));
  };

  return {
    id: decisionId,
    type: 'governance',
    governance_type: govDecision.type,
    title,
    description,
    blocks: {
      steps: [],
      count: 0,
      stepNames: [],
    },
    action: {
      type: govDecision.approved ? 'confirm' : 'reject',
      label: govDecision.approved ? 'Approve' : 'Review Decision',
      onClick: handleAction,
    },
    result: {
      autoRun: false,
      message: govDecision.approved
        ? 'Execution can proceed after approval'
        : 'Execution blocked by governance policy',
    },
    expandable: {
      evidence: {
        decision_id: decisionId,
        governance_decision: govDecision,
      },
      governance_data: {
        cost_governance: govDecision.cost_governance,
        node_governance: govDecision.node_governance,
        policy_violation: govDecision.policy_violation,
        preflight_failure: govDecision.preflight_failure,
      },
    },
    status,
    priority,
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
 * Shared SSE connection per workspace.
 * All subscribers fan-out from a single EventSource to avoid exhausting
 * the browser's 6-connection-per-origin limit.
 */
interface StreamSubscriber {
  eventTypes?: Set<string>;
  onEvent: (event: UnifiedEvent) => void;
  onError?: (error: Error) => void;
}

interface SharedStream {
  eventSource: EventSource;
  subscribers: Set<StreamSubscriber>;
  url: string;
  key: string;
}

const sharedStreams = new Map<string, SharedStream>();

function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

function resolveEventStreamBaseUrl(apiUrl: string): string {
  const explicit = apiUrl.trim();
  if (explicit) {
    return stripTrailingSlash(explicit);
  }

  const configuredDirectUrl = (
    process.env.NEXT_PUBLIC_LOCAL_CORE_API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    ''
  ).trim();
  if (configuredDirectUrl.startsWith('http')) {
    return stripTrailingSlash(configuredDirectUrl);
  }

  const fallback = getApiBaseUrl().trim();
  if (fallback) {
    return stripTrailingSlash(fallback);
  }

  if (typeof window !== 'undefined') {
    return stripTrailingSlash(window.location.origin);
  }

  return 'http://localhost:8200';
}

function getOrCreateStream(workspaceId: string, apiUrl: string): SharedStream {
  const baseUrl = resolveEventStreamBaseUrl(apiUrl);
  const key = `${baseUrl}::${workspaceId}`;
  const existing = sharedStreams.get(key);
  if (existing && existing.eventSource.readyState !== EventSource.CLOSED) {
    return existing;
  }

  // Close stale stream if exists
  if (existing) {
    existing.eventSource.close();
  }

  // SSE requires direct backend connection; Next.js rewrites buffer chunked responses.
  // Subscribe to ALL event types; client-side filtering per subscriber
  const url = `${baseUrl}/api/v1/workspaces/${workspaceId}/events/stream`;

  console.log('[EventStream] Opening shared connection:', url);

  const eventSource = new EventSource(url);
  const stream: SharedStream = { eventSource, subscribers: new Set(), url, key };

  const dispatch = (data: any) => {
    if (data.type === 'connected' || data.type === 'error') {
      if (data.type === 'error') {
        stream.subscribers.forEach(sub => {
          sub.onError?.(new Error(data.message));
        });
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
      thread_id: data.thread_id || data.payload?.thread_id || data.metadata?.thread_id || data.payload?.session_id,
      payload: data.payload || data,
      entity_ids: data.entity_ids,
      metadata: data.metadata,
    };

    stream.subscribers.forEach(sub => {
      // Client-side event type filter
      if (sub.eventTypes && sub.eventTypes.size > 0 && !sub.eventTypes.has(event.type)) {
        return;
      }
      try {
        sub.onEvent(event);
      } catch (err) {
        console.error('[EventStream] Subscriber handler error:', err);
      }
    });
  };

  const handleEvent = (e: MessageEvent) => {
    try {
      dispatch(JSON.parse(e.data));
    } catch (err) {
      console.error('[EventStream] Failed to parse event:', err, e.data);
    }
  };

  eventSource.onmessage = handleEvent;

  // Register ALL known backend event types so no named SSE event is missed.
  // Source: backend/app/models/mindscape.py EventType enum + useMessageStream subscriptions.
  const allEventTypes = [
    // Core events ('message' is handled by onmessage, not listed here to avoid double dispatch)
    'tool_call',
    'tool_result',
    'playbook_step',
    'insight',
    'habit_observation',
    'project_created',
    'project_updated',
    'intent_created',
    'intent_updated',
    'agent_execution',
    'execution_chat',
    'obsidian_note_updated',
    'execution_plan',
    'phase_summary',
    'pipeline_stage',
    // Decision & ReAct events
    'decision_required',
    'branch_proposed',
    'artifact_created',
    'artifact_updated',
    'run_state_changed',
    // Runtime profile events
    'policy_check',
    'loop_budget_exhausted',
    'quality_gate_check',
    'agent_turn',
    'decision_proposal',
    'decision_final',
    'action_item',
    'meeting_round',
    // Governance events
    'meeting_start',
    'meeting_end',
    'decision_made',
    'reasoning_committed',
    'intent_patched',
    'state_vector_computed',
    'mode_transition',
    // Execution lifecycle (useMessageStream subscriptions)
    'run_started',
    'run_completed',
    'run_failed',
    'step_start',
    'step_progress',
    'step_complete',
    'step_error',
    // Meeting real-time streaming (Redis Pub/Sub → SSE relay)
    'chunk',
    'stream_start',
    'stream_end',
    'meeting_stage',
  ];

  for (const eventType of allEventTypes) {
    eventSource.addEventListener(eventType, handleEvent);
  }

  eventSource.onerror = (err) => {
    const target = err.target as EventSource;
    if (target?.readyState === EventSource.CLOSED) {
      console.warn('[EventStream] Shared connection closed, will reconnect:', url);
    } else if (target?.readyState === EventSource.CONNECTING) {
      // Reconnecting automatically
    } else {
      console.error('[EventStream] Shared connection error:', err);
    }
  };

  eventSource.onopen = () => {
    console.log('[EventStream] Shared connection opened:', url);
  };

  sharedStreams.set(key, stream);
  return stream;
}

/**
 * Subscribe to event stream (SSE)
 *
 * Uses a shared EventSource per workspace — multiple subscribers fan-out
 * from a single connection. Event type filtering is done client-side.
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

  const stream = getOrCreateStream(workspaceId, apiUrl);

  const subscriber: StreamSubscriber = {
    eventTypes: eventTypes ? new Set(eventTypes) : undefined,
    onEvent: (event) => {
      // Additional project_id filter if specified
      if (projectId && event.project_id && event.project_id !== projectId) {
        return;
      }
      onEvent(event);
    },
    onError,
  };

  stream.subscribers.add(subscriber);

  // Return unsubscribe function
  return () => {
    stream.subscribers.delete(subscriber);

    // If no subscribers remain, close the shared connection
    if (stream.subscribers.size === 0) {
      stream.eventSource.close();
      sharedStreams.delete(stream.key);
      console.log('[EventStream] Closed shared connection (no subscribers):', stream.url);
    }
  };
}
