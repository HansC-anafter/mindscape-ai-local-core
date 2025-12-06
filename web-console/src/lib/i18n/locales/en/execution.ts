/**
 * Execution i18n messages (English)
 * Playbook execution, workspace execution inspector, and related UI
 */
import type { MessageKey } from '../../keys';

export const executionEn = {
  // Playbook Execution Inspector
  runInsightDraftChanges: 'Execution insights and draft changes',
  reviewAISuggestions: 'Review AI suggestions and apply changes to improve this playbook',
  aiAnalysis: 'AI Analysis',
  apply: 'Apply',
  discard: 'Discard',
  step: 'Step',
  noRevisionSuggestions: 'No revision suggestions yet.',
  chatWithPlaybookInspector: 'Chat with Playbook Inspector to get suggestions.',
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
  confirmRestartExecution: 'Are you sure you want to reset this execution?\n\nThis will create a new execution from the beginning and cancel the current one.',
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
  askPlaybookInspector: 'Ask the Playbook Inspector about this execution. It knows steps, events, and errors.',
  explainWhyFailed: 'Explain why this execution failed',
  suggestNextSteps: 'Suggest next steps',
  reviewPlaybookSteps: 'Review playbook steps',
  explainWhyFailedPrompt: 'Can you explain why this execution failed? What went wrong and how to fix it?',
  explainWhyFailedPromptAlt: 'What is the current status of this execution?',
  suggestNextStepsPrompt: 'What should be done next to resolve this issue or continue the execution?',
  reviewPlaybookStepsPrompt: 'Can you review the playbook steps and provide improvement suggestions?',
  playbookConversation: 'Playbook Conversation',

  // Workspace Loading
  workspaceNotFound: 'Workspace not found',
  failedToLoadWorkspace: 'Failed to load workspace',
  loadingWorkspace: 'Loading workspace...',
  rateLimitExceeded: 'Rate limit exceeded. Please wait {seconds} seconds before refreshing the page.',
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
  executionChatDescription: 'This is a discussion panel for asking about execution status, understanding steps, or getting suggestions. For actions (retry, cancel, etc.), use the buttons in the main execution interface.',
  recommended: '(Recommended)',
  autoStart: 'Auto start: ',
  aiThinking: 'AI thinking...',
} as const satisfies Partial<Record<MessageKey, string>>;

