import type { ChatMessage } from '@/hooks/useChatEvents';

export function formatExecutionSummary(
  executedTasks: any[],
  suggestionCards: any[]
): string {
  const taskCount = Array.isArray(executedTasks) ? executedTasks.length : 0;
  const suggestionCount = Array.isArray(suggestionCards) ? suggestionCards.length : 0;

  if (taskCount === 0 && suggestionCount === 0) {
    return '';
  }

  let summaryContent = '';

  if (taskCount > 0 && suggestionCount > 0) {
    summaryContent = `**Execution complete.**\n\nCreated ${taskCount} tasks and generated ${suggestionCount} suggestions.`;
  } else if (taskCount > 0) {
    summaryContent = `**Execution complete.**\n\nCreated ${taskCount} tasks.`;
  } else if (suggestionCount > 0) {
    summaryContent = `**Execution complete.**\n\nGenerated ${suggestionCount} suggestions.`;
  }

  if (taskCount > 0 && Array.isArray(executedTasks)) {
    const taskNames = executedTasks
      .map((task: any) => {
        return task.title || task.name || task.intent || task.task_name || task.id || '';
      })
      .filter((name: string) => name && name.trim().length > 0)
      .slice(0, 5);

    if (taskNames.length > 0) {
      summaryContent += '\n\n**Created tasks:**\n';
      taskNames.forEach((name: string, index: number) => {
        summaryContent += `${index + 1}. ${name}\n`;
      });
      if (taskCount > 5) {
        summaryContent += `\n... plus ${taskCount - 5} more tasks`;
      }
    }
  }

  return summaryContent;
}

export function createPlaybookErrorMessage(
  playbookCode: string,
  error: any
): ChatMessage {
  let errorMessage: string;
  if (error && typeof error === 'object' && error.user_message) {
    errorMessage = error.user_message;
  } else if (error?.message) {
    errorMessage = error.message;
  } else if (typeof error === 'string') {
    errorMessage = error;
  } else {
    errorMessage = `Playbook "${playbookCode}" execution failed`;
  }

  return {
    id: `playbook-error-${Date.now()}`,
    role: 'assistant',
    content: errorMessage,
    timestamp: new Date(),
    event_type: 'error',
  };
}

export function createAgentModeMessage(
  part1: string,
  part2: string,
  executableTasks: string[] = []
): ChatMessage {
  return {
    id: `agent-${Date.now()}`,
    role: 'assistant',
    content: part1,
    timestamp: new Date(),
    agentMode: {
      part1,
      part2,
      executable_tasks: executableTasks || [],
    },
  };
}

export function createExecutionModeMessage(
  playbookCode: string,
  executionId?: string
): ChatMessage {
  return {
    id: `exec-${Date.now()}`,
    role: 'assistant',
    content: `Started playbook "${playbookCode}". Open the execution panel to track progress.`,
    timestamp: new Date(),
    triggered_playbook: {
      playbook_code: playbookCode,
      execution_id: executionId,
      status: 'executed',
    },
  };
}
