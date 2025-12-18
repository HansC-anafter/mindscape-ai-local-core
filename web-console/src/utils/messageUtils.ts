import type { ChatMessage } from '@/hooks/useChatEvents';

/**
 * Format execution results summary message.
 *
 * @param executedTasks - Array of executed tasks
 * @param suggestionCards - Array of suggestion cards
 * @returns Formatted summary message
 */
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
    summaryContent = `✅ **執行完成！**\n\n已建立 ${taskCount} 個任務，並產生 ${suggestionCount} 個建議。`;
  } else if (taskCount > 0) {
    summaryContent = `✅ **執行完成！**\n\n已建立 ${taskCount} 個任務。`;
  } else if (suggestionCount > 0) {
    summaryContent = `✅ **執行完成！**\n\n已產生 ${suggestionCount} 個建議。`;
  }

  if (taskCount > 0 && Array.isArray(executedTasks)) {
    const taskNames = executedTasks
      .map((task: any) => {
        return task.title || task.name || task.intent || task.task_name || task.id || '';
      })
      .filter((name: string) => name && name.trim().length > 0)
      .slice(0, 5);

    if (taskNames.length > 0) {
      summaryContent += '\n\n**已建立的任務：**\n';
      taskNames.forEach((name: string, index: number) => {
        summaryContent += `${index + 1}. ${name}\n`;
      });
      if (taskCount > 5) {
        summaryContent += `\n... 還有 ${taskCount - 5} 個任務`;
      }
    }
  }

  return summaryContent;
}

/**
 * Create error chat message from playbook trigger error.
 *
 * @param playbookCode - Playbook code
 * @param error - Error object or message
 * @returns Chat message with error content
 */
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

/**
 * Create agent mode parsed message.
 *
 * @param part1 - Part 1: Understanding & Response
 * @param part2 - Part 2: Executable Next Steps
 * @param executableTasks - Array of executable tasks
 * @returns Chat message with agent mode content
 */
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

/**
 * Create execution mode playbook executed message.
 *
 * @param playbookCode - Playbook code
 * @param executionId - Execution ID
 * @returns Chat message with execution info
 */
export function createExecutionModeMessage(
  playbookCode: string,
  executionId?: string
): ChatMessage {
  return {
    id: `exec-${Date.now()}`,
    role: 'assistant',
    content: `已開始執行 playbook "${playbookCode}"，請查看執行面板查看進度。`,
    timestamp: new Date(),
    triggered_playbook: {
      playbook_code: playbookCode,
      execution_id: executionId,
      status: 'executed',
    },
  };
}

