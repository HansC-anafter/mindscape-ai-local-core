import { toTimestampMs } from '@/lib/time';

export interface ExecutionStats {
  running: number;
  paused: number;
  queued: number;
  completed: number;
  failed: number;
}

export interface ExecutionSummary {
  executionId: string;
  runNumber: number;
  status: string;
  startedAt: string;
  currentStep?: {
    index: number;
    name: string;
    status: 'running' | 'waiting_confirmation';
  };
  totalSteps: number;
  playbookCode: string;
  playbookName: string;
}

export interface PlaybookGroup {
  playbookCode: string;
  playbookName: string;
  executions: ExecutionSummary[];
  stats: ExecutionStats;
  projectId?: string;
  projectName?: string;
}

interface LoadExecutionSidebarDataOptions {
  apiUrl: string;
  projectId: string;
  workspaceId: string;
}

export interface ExecutionSidebarDataResult {
  playbookGroups?: PlaybookGroup[];
  projectName?: string;
}

function createEmptyStats(): ExecutionStats {
  return { running: 0, paused: 0, queued: 0, completed: 0, failed: 0 };
}

function applyStatusToStats(stats: ExecutionStats, status: string) {
  if (status === 'running') stats.running++;
  else if (status === 'paused') stats.paused++;
  else if (status === 'queued') stats.queued++;
  else if (status === 'completed' || status === 'succeeded') stats.completed++;
  else if (status === 'failed') stats.failed++;
}

function currentStepForExecution(exec: any): ExecutionSummary['currentStep'] {
  const currentStepIndex = exec.current_step_index;
  const currentStepName = exec.current_step_name;
  if (currentStepIndex === null || currentStepIndex === undefined) {
    return undefined;
  }
  return {
    index: currentStepIndex + 1,
    name: currentStepName || 'Step',
    status: exec.status === 'paused' ? 'waiting_confirmation' : 'running',
  };
}

function executionStartedAt(exec: any): string {
  return exec.started_at || exec.created_at || new Date().toISOString();
}

function sortByStartedAt<T extends { startedAt: string }>(items: T[]): T[] {
  return items.sort((a, b) => (toTimestampMs(a.startedAt) ?? 0) - (toTimestampMs(b.startedAt) ?? 0));
}

async function fetchOrNull(url: string): Promise<Response | null> {
  try {
    return await fetch(url);
  } catch {
    return null;
  }
}

function buildProjectExecutionGroups(treeData: any): PlaybookGroup[] | undefined {
  if (!treeData.playbookGroups || !Array.isArray(treeData.playbookGroups) || treeData.playbookGroups.length === 0) {
    return undefined;
  }

  const orderedExecutions: Array<{ exec: any; group: any; startedAt: string }> = [];
  treeData.playbookGroups.forEach((group: any) => {
    if (group.executions && group.executions.length > 0) {
      group.executions.forEach((exec: any) => {
        orderedExecutions.push({ exec, group, startedAt: exec.started_at || exec.created_at });
      });
    }
  });

  sortByStartedAt(orderedExecutions);
  const runNumbers = new Map<any, number>();
  orderedExecutions.forEach((item, index) => {
    runNumbers.set(item.exec, index + 1);
  });

  return treeData.playbookGroups.map((group: any) => {
    let groupProjectId: string | undefined;
    let groupProjectName: string | undefined;
    const executionSummaries: ExecutionSummary[] = [];

    if (group.executions && group.executions.length > 0) {
      const firstExec = group.executions[0];
      groupProjectId = firstExec.project_id || firstExec.execution_context?.project_id;
      groupProjectName = firstExec.project_name || firstExec.execution_context?.project_name;

      group.executions.forEach((exec: any) => {
        executionSummaries.push({
          executionId: exec.execution_id,
          runNumber: runNumbers.get(exec) || exec.run_number || 0,
          status: exec.status?.toLowerCase() || 'queued',
          startedAt: executionStartedAt(exec),
          currentStep: currentStepForExecution(exec),
          totalSteps: exec.total_steps || 1,
          playbookCode: exec.playbook_code || group.playbookCode || 'unknown',
          playbookName: exec.playbook_title || group.playbookName || exec.playbook_code || 'unknown',
        });
      });

      sortByStartedAt(executionSummaries);
    }

    if (group.project_id) {
      groupProjectId = group.project_id;
    }
    if (group.project_name) {
      groupProjectName = group.project_name;
    }

    return {
      playbookCode: group.playbookCode || 'unknown',
      playbookName: group.playbookName || group.playbookCode || 'unknown',
      executions: executionSummaries,
      stats: group.stats || createEmptyStats(),
      projectId: groupProjectId,
      projectName: groupProjectName,
    };
  });
}

function buildWorkspaceExecutionGroups(executions: any[]): PlaybookGroup[] {
  const allExecutionsWithData = executions.map((exec: any) => ({
    exec,
    playbookCode: exec.playbook_code || exec.pack_id || 'unknown',
    startedAt: executionStartedAt(exec),
  }));

  sortByStartedAt(allExecutionsWithData);
  allExecutionsWithData.forEach((item, index) => {
    item.exec._globalRunNumber = index + 1;
  });

  const groupMap = new Map<string, PlaybookGroup>();
  allExecutionsWithData.forEach(({ exec }: { exec: any }) => {
    const playbookCode = exec.playbook_code || exec.pack_id || 'unknown';
    if (!groupMap.has(playbookCode)) {
      const execProjectId = exec.project_id || exec.execution_context?.project_id;
      const execProjectName = exec.project_name || exec.execution_context?.project_name;
      groupMap.set(playbookCode, {
        playbookCode,
        playbookName: exec.playbook_title || playbookCode,
        executions: [],
        stats: createEmptyStats(),
        projectId: execProjectId,
        projectName: execProjectName,
      });
    }

    const group = groupMap.get(playbookCode)!;
    const status = exec.status?.toLowerCase() || 'queued';
    group.executions.push({
      executionId: exec.execution_id,
      runNumber: exec._globalRunNumber,
      status,
      startedAt: executionStartedAt(exec),
      currentStep: currentStepForExecution(exec),
      totalSteps: exec.total_steps || 1,
      playbookCode,
      playbookName: exec.playbook_title || playbookCode,
    });
    applyStatusToStats(group.stats, status);
  });

  groupMap.forEach((group) => {
    sortByStartedAt(group.executions);
  });

  return Array.from(groupMap.values());
}

export async function loadExecutionSidebarData({
  apiUrl,
  projectId,
  workspaceId,
}: LoadExecutionSidebarDataOptions): Promise<ExecutionSidebarDataResult> {
  if (projectId && projectId.trim() !== '') {
    const [projectResponse, executionTreeResponse] = await Promise.all([
      fetchOrNull(`${apiUrl}/api/v1/workspaces/${workspaceId}/projects/${projectId}`),
      fetchOrNull(`${apiUrl}/api/v1/workspaces/${workspaceId}/projects/${projectId}/execution-tree`),
    ]);

    const result: ExecutionSidebarDataResult = {};
    if (projectResponse?.ok) {
      const projectData = await projectResponse.json();
      result.projectName = projectData.name || projectData.title || 'Project';
    }

    if (executionTreeResponse?.ok) {
      const treeData = await executionTreeResponse.json();
      if (!treeData.detail) {
        const playbookGroups = buildProjectExecutionGroups(treeData);
        if (playbookGroups) {
          result.playbookGroups = playbookGroups;
        }
      }
    }

    return result;
  }

  try {
    const execResponse = await fetch(
      `${apiUrl}/api/v1/workspaces/${workspaceId}/tasks?limit=50&task_type=execution&include_completed=true`,
    );
    if (execResponse.ok) {
      const execData = await execResponse.json();
      return {
        playbookGroups: buildWorkspaceExecutionGroups(execData.tasks || []),
        projectName: 'All Executions',
      };
    }
  } catch {
  }

  return {};
}
