import type { DecisionCardData } from '../DecisionCard';
import type { UnifiedEvent } from './types';

export function eventToBlockerCard(event: UnifiedEvent): DecisionCardData | null {
  if (event.type !== 'decision_required' && event.type !== 'branch_proposed') {
    return null;
  }

  if (event.type === 'branch_proposed') {
    return eventToBranchCard(event);
  }

  const payload = event.payload;

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
