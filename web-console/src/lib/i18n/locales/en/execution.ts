/**
 * Execution i18n messages (English)
 * Playbook execution, workspace execution inspector, and related UI
 */
import type { MessageKey } from '../../keys';

export const executionEn = {
  // Playbook Execution Inspector
  runInsightDraftChanges: 'Execution insights and draft changes',
  reviewAISuggestions: 'Review AI suggestions to improve this playbook',
  aiAnalysis: 'AI Analysis',
  apply: 'Apply',
  discard: 'Discard',
  step: 'Step',
  noRevisionSuggestions: 'No revision suggestions yet.',
  chatWithPlaybookInspector: 'Chat with Playbook Inspector for suggestions.',
  revisionDraft: 'Revision Draft',
  aiSuggestedChangesWillAppear: 'AI suggested changes will appear here',
  stepsTimeline: 'Steps Timeline',
  eventStream: 'Event Stream',
  noEventsYet: 'No events yet',
  toolCalls: 'Tool Calls',
  selectStepToViewDetails: 'Select step to view details',
  editPlaybook: 'Edit Playbook',

  // Execution Status
  executionStatusRunning: 'Running',
  executionStatusSucceeded: 'Succeeded',
  executionStatusFailed: 'Failed',
  executionStatusPaused: 'Paused',
  executionStatusUnknown: 'Unknown',

  // Trigger Source
  triggerSourceAuto: 'Auto',
  triggerSourceSuggested: 'Suggested',
  triggerSourceManual: 'Manual',
  triggerSourceUnknown: 'Unknown',

  // Actions
  stop: 'Stop',
  stopping: 'Stopping...',
  reload: 'Reload',
  reloading: 'Reloading...',
  restart: 'Reset',
  restarting: 'Resetting...',
  reloadPlaybook: 'Reload Playbook',
  restartExecution: 'Reset Execution',
  confirmRestartExecution: 'Reset this execution?\n\nThis will create a new execution and cancel the current one.',
  restartingExecution: 'Resetting execution, please wait...',
  executionRestarted: 'Execution reset',
  executionRestartFailed: 'Execution reset failed',
  view: 'View',

  // Execution Header
  runNumber: 'Run #{number}',
  stepProgress: 'Step {current} / {total}',
  startedAt: 'Started at {time}',
  byUser: 'By user: {user}',
  unknownUser: 'Unknown user',
  unknownPlaybook: 'Unknown playbook',
  errorLabel: 'Error: ',

  // Step Details
  noEvents: 'No events yet',
  agent: 'Agent: ',
  tool: 'Tool: ',
  collaboration: 'Collaboration: ',
  startingPlaybookExecution: 'Starting playbook execution: {playbook}',
  stepNumber: 'Step {number}',
  unnamed: 'Unnamed',
  tools: 'Tools',
  pending: 'Pending',

  // Execution Messages
  thisExecutionFailed: 'This execution failed: {reason}. Check the steps timeline to diagnose the issue.',

  // Playbook Inspector
  playbookInspector: 'Playbook Inspector',
  playbookRun: 'Playbook - Run #{number}',
  askPlaybookInspector: 'Ask Playbook Inspector about this execution. Knows steps, events, and errors.',
  explainWhyFailed: 'Explain why this execution failed',
  suggestNextSteps: 'Suggest next steps',
  reviewPlaybookSteps: 'Review playbook steps',
  explainWhyFailedPrompt: 'Explain why this execution failed and how to fix it.',
  explainWhyFailedPromptAlt: 'What is the current status of this execution?',
  suggestNextStepsPrompt: 'What should be done next to resolve this issue?',
  reviewPlaybookStepsPrompt: 'Review playbook steps and provide improvement suggestions.',
  playbookConversation: 'Playbook Conversation',

  // Workspace Loading
  workspaceNotFound: 'Workspace not found',
  failedToLoadWorkspace: 'Failed to load workspace',
  loadingWorkspace: 'Loading workspace...',
  rateLimitExceeded: 'Rate limit exceeded. Wait {seconds} seconds before refreshing.',
  retryButton: 'Retry',

  // Timeline Panel
  returnToWorkspaceOverview: 'Return to workspace overview',
  currentExecution: 'Current execution',
  otherExecutionsOfSamePlaybook: 'Other executions of the same playbook',
  otherPlaybooksExecutions: 'Other playbooks executions',
  recentFailures: 'Recent failures',

  // Execution Chat
  discussPlaybookExecution: 'Discuss this playbook execution with AI...',
  itKnowsStepsEventsErrors: 'It knows steps, events, and errors.',
  executionChatDescription: 'Discussion panel for execution status, steps, or suggestions. Use main interface buttons for actions.',
  recommended: '(Recommended)',
  autoStart: 'Auto start: ',
  aiThinking: 'AI thinking...',
  enterResponseToContinue: 'Enter response to continue execution...',
  playbookWaitingForResponse: 'Playbook is waiting for your response',
  sendMessageToContinue: 'Sending a message continues execution to next step.',
} as const satisfies Partial<Record<MessageKey, string>>;

