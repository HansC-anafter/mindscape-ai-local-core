/**
 * Common i18n messages (English)
 * Shared across all modules
 */

import type { MessageKey } from '../../keys';

export const commonEn = {

  // Status
  status: 'Status',
  statusActive: 'Active',
  statusCompleted: 'Completed',
  statusIdentified: 'Identified',
  statusPendingAdd: 'Pending Add',
  statusAdded: 'Added',
  statusPaused: 'Paused',
  statusArchived: 'Archived',

  // Priority
  priorityLow: 'Low',
  priorityMedium: 'Medium',
  priorityHigh: 'High',
  priorityCritical: 'Critical',

  // Actions
  save: 'Save',
  cancel: 'Cancel',
  delete: 'Delete',
  edit: 'Edit',
  create: 'Create',
  update: 'Update',
  search: 'Search',
  add: 'Add',
  accept: 'Accept',
  skip: 'Skip',
  copy: 'Copy',
  open: 'Open',
  download: 'Download',
  sourceIntent: 'Source Intent',
  noOutcomes: 'No outcomes yet',

  // Common
  loading: 'Loading...',
  saving: 'Saving...',
  error: 'Error',
  success: 'Success',
  noData: 'No data',
  notice: 'Notice',
  hint: 'Hint',
  times: 'times',
  retryFailed: 'Retry failed',
  unknownError: 'Unknown error',
  storageLocationNotSpecified: 'Storage location not specified',
  actionRequired: 'Action required',
  configureStoragePathNow: 'Configure storage path now',
  retryArtifactCreation: 'Retry artifact creation',
  llmConfidenceScore: 'LLM Confidence Score: {confidence} (range: 0~1)',
  requiresExternalSetup: 'Requires External Setup',
  generalIntegrations: 'General Integrations',
  generalIntegrationsLocalDescription: 'Common tool integrations that work with local core mode',
  generalIntegrationsDescription: 'Common tool integrations',
  developerIntegrations: 'Developer Integrations',
  developerIntegrationsDescription: 'Advanced integrations requiring external environments or technical collaboration, primarily for technology partners',

  // Pending Tasks
  intentBasedOnAISuggestion: 'Intent based on AI suggestion:',
  editIntentLabel: 'Edit intent label',
  backgroundExecution: 'Background Execution',
  backgroundExecutionDescription: 'This task will execute automatically in the background, no LLM analysis required',
  enableBackgroundTask: 'Enable Background Task',
  enableFailed: 'Enable failed',
  confidence: 'Confidence:',
  executionSuccessUpdating: 'Execution successful, updating...',

  // Background Tasks
  disabled: 'Disabled',
  runningNormally: 'Running Normally',
  executionFailed: 'Execution Failed',
  enabled: 'Enabled',
  noBackgroundTasks: 'No background tasks',
  processing: 'Processing...',
  disable: 'Disable',
  enable: 'Enable',
  lastExecution: 'Last Execution:',
  nextExecution: 'Next Execution:',
  lastExecutionFailed: 'Last execution failed',
  operationFailed: 'Operation failed',
  executionAISuggested: 'AI Suggested',
  executionRequiresConfirmation: 'Requires confirmation',
  executionSelectStepForDetails: 'Please select a step to view details',
  executionCancel: 'Cancel Execution',
  executionSummary: 'Execution Summary',
  executionWaitingConfirmation: 'Waiting for Confirmation',
  executionConfirmationMessage: 'This step requires your confirmation to continue',
  executionConfirmContinue: 'Confirm and Continue',
  executionReject: 'Reject',
  timelineRunning: 'Running',
  timelinePendingConfirmation: 'Pending Confirmation',
  timelineArchived: 'Archived',
  timelineHistory: 'History',
  noRunningExecutions: 'No running executions',
  noPendingConfirmations: 'No steps pending confirmation',
  noArchivedExecutions: 'No archived executions',
  retry: 'Retry',
  viewArtifact: 'View Artifact',
  timelineItemNotFound: 'Associated Timeline Item not found',
  timelineItemUnavailable: 'Unable to fetch Timeline Item',
  ready: 'Ready',
  needsSetup: 'Needs Setup',
  unsupported: 'Unsupported',
  toolsNeedConfiguration: 'Tools need configuration',
  requiredToolsNotSupported: 'Required tools not supported',
  // Tool Status Labels
  statusNotConfigured: 'Not configured',
  statusNotConnected: 'Not connected',
  statusConnected: 'Connected',
  statusEnabled: 'Enabled',
  statusDisabled: 'Disabled',
  statusLocalMode: 'Local mode',
  statusNotSupported: 'Not supported',
  nextStep: 'Next Step',
  startedAt: 'Started At',

  // Sidebar Tabs
  tabScheduling: 'Scheduling',
  tabOutcomes: 'Outcomes',
  tabBackgroundTasks: 'Background Tasks',
  backgroundTasksPanel: 'Background Tasks Panel',
  running: 'Running',
  pending: 'Pending',
  createdAt: 'Created At',
  activeExecutions: 'Active Executions',
  backgroundRoutines: 'Background Routines',
  systemTools: 'System Tools',
  systemTool: 'System Tool',

  // Copy actions
  copyAll: 'Copy All',
  copyAllMessages: 'Copy All Messages',
  copyMessage: 'Copy Message',
  copied: 'Copied',
  user: 'User',
  assistant: 'Assistant',

  // Modal titles
  configureTool: 'Configure Tool',
  configureWorkflow: 'Configure Workflow',
  editMCPServer: 'Edit MCP Server',
  addMCPServer: 'Add MCP Server',
  closeModal: 'Close Modal',

  // Modal content
  unsupportedToolType: 'Unsupported tool type',
  closeButton: 'Close',

  // New keys added to fix warnings
  disconnected: 'Disconnected',
  confirmDelete: 'Confirm Delete',
  deleting: 'Deleting',
  failedToLoad: 'Failed to Load',
  dimensions: 'Dimensions',
  contextWindow: 'Context Window',
  executionStatusCancelled: 'Cancelled',

  // Common labels
  name: 'Name',
  description: 'Description',
  type: 'Type',
  location: 'Location',
  provider: 'Provider',
  override: 'Override',

} as const satisfies Partial<Record<MessageKey, string>>;
