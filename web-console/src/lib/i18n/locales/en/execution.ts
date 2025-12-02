/**
 * Execution i18n messages (English)
 * Playbook execution, workspace execution inspector, and related UI
 */
import type { MessageKey } from '../../keys';

export const executionEn = {
  // Playbook Execution Inspector
  runInsightDraftChanges: 'Run Insight & Draft Changes',
  reviewAISuggestions: 'Review AI suggestions and apply changes to improve this playbook',
  aiAnalysis: 'AI Analysis',
  apply: 'Apply',
  discard: 'Discard',
  step: 'Step',
  noRevisionSuggestions: 'No revision suggestions yet.',
  chatWithPlaybookInspector: 'Chat with the Playbook Inspector to get suggestions.',
  revisionDraft: 'Revision Draft',
  aiSuggestedChangesWillAppear: 'AI-suggested changes will appear here',
  stepsTimeline: 'Steps Timeline',
  eventStream: 'Event Stream',
  noEventsYet: 'No events yet',
  toolCalls: 'Tool Calls',
  selectStepToViewDetails: 'Select a step to view details',
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

  // Execution Header
  runNumber: 'Run #{number}',
  stepProgress: 'Step {current} / {total}',
  startedAt: 'Started {time}',
  byUser: 'by {user}',
  unknownUser: 'unknown',
  unknownPlaybook: 'Unknown Playbook',
  errorLabel: 'Error:',

  // Step Details
  noEvents: 'No events yet',
  agent: 'Agent:',
  tool: 'Tool:',
  collaboration: 'Collaboration:',
  startingPlaybookExecution: 'Starting Playbook execution: {playbook}',
  stepNumber: 'Step {number}',
  unnamed: 'Unnamed',
  tools: 'tools',

  // Execution Messages
  thisExecutionFailed: 'This execution failed: {reason}. Review the steps timeline to identify the issue.',

  // Playbook Inspector
  playbookInspector: 'Playbook Inspector',
  playbookRun: 'Playbook - Run #{number}',
  askPlaybookInspector: 'Ask the Playbook Inspector about this run. It knows the steps, events, and errors.',
  explainWhyFailed: 'Explain why this execution failed',
  suggestNextSteps: 'Suggest next steps',
  reviewPlaybookSteps: 'Review playbook steps',
  explainWhyFailedPrompt: 'Can you explain why this execution failed? What went wrong and how can I fix it?',
  explainWhyFailedPromptAlt: 'What is the current status of this execution?',
  suggestNextStepsPrompt: 'What should I do next to resolve this issue or continue the execution?',
  reviewPlaybookStepsPrompt: 'Can you review the playbook steps and suggest any improvements?',
  playbookConversation: 'Playbook Conversation',

  // Workspace Loading
  workspaceNotFound: 'Workspace not found',
  failedToLoadWorkspace: 'Failed to load workspace',
  loadingWorkspace: 'Loading workspace...',
  rateLimitExceeded: 'Rate limit exceeded. Please wait {seconds} seconds and refresh the page.',
  retryButton: 'Retry',

  // Timeline Panel
  returnToWorkspaceOverview: 'Return to Workspace Overview',
  currentExecution: 'Current Execution',
  otherExecutionsOfSamePlaybook: 'Other Executions of Same Playbook',
  otherPlaybooksExecutions: 'Other Playbooks Executions',
  recentFailures: 'Recent Failures',

  // Execution Chat
  discussPlaybookExecution: 'Discuss this playbook execution with AI...',
  itKnowsStepsEventsErrors: 'It knows the steps, events, and errors.',
  executionChatDescription: 'This is a discussion panel for asking about execution status, understanding steps, or getting suggestions. For actions (retry, cancel, etc.), please use buttons in the main execution interface.',
  recommended: '(Recommended)',
  autoStart: 'Auto-start:',
  aiThinking: 'AI is thinking...',
} as const satisfies Partial<Record<MessageKey, string>>;

