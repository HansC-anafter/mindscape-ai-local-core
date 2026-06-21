import type { ExecutionStep } from '@/components/execution';
import { calculateProgress } from './progress';
import type { ExecutionStateSnapshot, ExecutionUIState, TimelineEntry, TreeStep } from './types';

export async function loadExecutionStateSnapshot(
  workspaceId: string,
  apiUrl: string,
): Promise<ExecutionStateSnapshot | null> {
  try {
    const eventsResponse = await fetch(
      `${apiUrl}/api/v1/workspaces/${workspaceId}/events?event_types=execution_plan&limit=10`,
    );

    if (!eventsResponse.ok) {
      return null;
    }

    const eventsData = await eventsResponse.json();
    const executionPlanEvents = eventsData.events || [];

    if (executionPlanEvents.length === 0) {
      return null;
    }

    const latestPlanEvent = executionPlanEvents[0];
    const planPayload = latestPlanEvent.payload;

    if (!planPayload || !planPayload.steps) {
      return null;
    }

    const treeSteps = buildTreeSteps(planPayload.steps);
    const trainSteps = buildTrainSteps(planPayload.steps);
    const timelineEntries = buildTimelineEntries(executionPlanEvents);
    const timelineEntry = buildLatestTimelineEntry(latestPlanEvent, planPayload);
    let isExecuting = false;
    const runningPlaybookCodes = new Set<string>();
    const recentPlaybookCodes = new Set<string>();

    const executionsResponse = await fetch(
      `${apiUrl}/api/v1/workspaces/${workspaceId}/tasks?limit=20&task_type=execution`,
    );

    if (executionsResponse.ok) {
      const tasksData = await executionsResponse.json();
      const allExecutions = (tasksData.tasks || []).map((task: any) => ({
        execution_id: task.id,
        status: task.status,
        task,
        playbook_code: task.pack_id,
        steps: [],
      }));

      const activeExecutions = allExecutions.filter((execution: any) =>
        execution.status === 'running' || execution.status === 'pending' || execution.status === 'queued'
      );

      activeExecutions.forEach((execution: any) => {
        const playbookCode = execution.playbook_code || execution.task?.execution_context?.playbook_code;
        if (playbookCode) {
          runningPlaybookCodes.add(playbookCode);
        }
      });

      allExecutions
        .filter((execution: any) => {
          const playbookCode = execution.playbook_code || execution.task?.execution_context?.playbook_code;
          return playbookCode && playbookCode !== 'execution_status_query';
        })
        .slice(0, 5)
        .forEach((execution: any) => {
          const playbookCode = execution.playbook_code || execution.task?.execution_context?.playbook_code;
          if (playbookCode) {
            recentPlaybookCodes.add(playbookCode);
          }
        });

      if (activeExecutions.length > 0) {
        isExecuting = true;
        timelineEntry.status = 'in_progress';
        applyActiveExecutionStepStatus(activeExecutions[0], treeSteps, trainSteps);
      }
    }

    const aiTeamMembers = await loadAiTeamMembers(
      workspaceId,
      apiUrl,
      planPayload,
      runningPlaybookCodes.size > 0 ? runningPlaybookCodes : recentPlaybookCodes,
    );

    return {
      trainSteps,
      executionTree: treeSteps,
      thinkingTimeline: timelineEntries,
      thinkingSummary: planPayload.plan_summary,
      overallProgress: calculateProgress(trainSteps),
      isExecuting,
      aiTeamMembers,
    };
  } catch {
    return null;
  }
}

function buildTreeSteps(steps: any[]): TreeStep[] {
  return steps.map((step: any) => ({
    id: step.step_id || step.id || `step-${Math.random().toString(36).substr(2, 9)}`,
    name: step.intent || step.name || 'Unknown Step',
    status: (step.status as TreeStep['status']) || 'pending',
  }));
}

function buildTrainSteps(steps: any[]): ExecutionStep[] {
  return steps.map((step: any) => ({
    id: step.step_id || step.id || `step-${Math.random().toString(36).substr(2, 9)}`,
    name: step.intent || step.name || 'Unknown Step',
    icon: step.artifacts?.[0] === 'pptx' ? 'PPT' :
      step.artifacts?.[0] === 'xlsx' ? 'XLS' :
        step.artifacts?.[0] === 'docx' ? 'DOC' : 'DOC',
    status: (step.status as ExecutionStep['status']) || 'pending',
  }));
}

function buildLatestTimelineEntry(latestPlanEvent: any, planPayload: any): TimelineEntry {
  return {
    id: `plan-${latestPlanEvent.id}`,
    timestamp: latestPlanEvent.timestamp || new Date().toISOString(),
    summary: planPayload.plan_summary || `Execution Plan: ${planPayload.steps?.length || 0} steps`,
    stepCount: planPayload.steps?.length || 0,
    status: 'completed',
  };
}

function buildTimelineEntries(executionPlanEvents: any[]): TimelineEntry[] {
  return executionPlanEvents
    .slice(0, 10)
    .map((event: any) => {
      const payload = event.payload || {};
      return {
        id: `plan-${event.id}`,
        timestamp: event.timestamp || new Date().toISOString(),
        summary: payload.plan_summary || `Execution Plan: ${payload.steps?.length || 0} steps`,
        stepCount: payload.steps?.length || 0,
        status: 'completed' as const,
      };
    });
}

function applyActiveExecutionStepStatus(
  execution: any,
  treeSteps: TreeStep[],
  trainSteps: ExecutionStep[],
) {
  if (!execution.steps || execution.steps.length === 0) {
    return;
  }

  treeSteps.forEach(step => {
    const execStep = execution.steps.find((candidate: any) =>
      candidate.step_name === step.name || candidate.id === step.id
    );
    if (execStep) {
      step.status = mapExecutionStepStatus(execStep.status);
    }
  });

  trainSteps.forEach(step => {
    const execStep = execution.steps.find((candidate: any) =>
      candidate.step_name === step.name || candidate.id === step.id
    );
    if (execStep) {
      step.status = mapExecutionStepStatus(execStep.status);
    }
  });
}

function mapExecutionStepStatus(status: string): 'pending' | 'in_progress' | 'completed' | 'error' {
  return status === 'running' ? 'in_progress' :
    status === 'completed' ? 'completed' :
      status === 'failed' ? 'error' : 'pending';
}

async function loadAiTeamMembers(
  workspaceId: string,
  apiUrl: string,
  planPayload: any,
  playbookCodesToFetch: Set<string>,
): Promise<ExecutionUIState['aiTeamMembers']> {
  const aiTeamMembers = (planPayload.ai_team_members && planPayload.ai_team_members.length > 0)
    ? planPayload.ai_team_members.map((member: any) => ({
      id: member.pack_id || member.id,
      name: member.name || member.pack_id,
      name_zh: member.name_zh,
      role: member.role || '',
      icon: member.icon || 'AI',
      status: 'pending' as const,
    }))
    : [];

  if (playbookCodesToFetch.size === 0) {
    return aiTeamMembers;
  }

  try {
    const playbookCodesArray = Array.from(playbookCodesToFetch);
    const membersResponse = await fetch(
      `${apiUrl}/api/v1/workspaces/${workspaceId}/ai-team-members?playbook_codes=${playbookCodesArray.join(',')}`,
    );

    if (!membersResponse.ok) {
      return aiTeamMembers;
    }

    const membersData = await membersResponse.json();
    const executionMembers = (membersData.members || []).map((member: any) => ({
      id: member.pack_id || member.id,
      name: member.name || member.pack_id,
      name_zh: member.name_zh,
      role: member.role || '',
      icon: member.icon || 'AI',
      status: 'in_progress' as const,
    }));

    const existingIds = new Set(aiTeamMembers.map((member: any) => member.id));
    executionMembers.forEach((member: any) => {
      if (!existingIds.has(member.id)) {
        aiTeamMembers.push(member);
      }
    });
  } catch {
  }

  return aiTeamMembers;
}
