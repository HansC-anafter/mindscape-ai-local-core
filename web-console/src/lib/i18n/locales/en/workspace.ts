/**
 * workspace i18n messages (English)
 */
import type { MessageKey } from '../../keys';

export const workspaceEn = {
  // Workspace creation wizard
  createWorkspace: 'Create Workspace',
  selectCreationMethod: 'Select Creation Method',
  quickCreate: 'Quick Create',
  quickCreateDescription: 'Enter name only, quick start',
  llmGuidedCreate: 'LLM Guided Create',
  llmGuidedCreateDescription: 'Let AI help you configure workspace',
  workspaceName: 'Workspace Name',
  workspaceNameRequired: 'Workspace Name *',
  workspaceDescription: 'Workspace Description',
  workspaceDescriptionRequired: 'Workspace Description (Required)',
  workspaceDescriptionOptional: 'Description (Optional)',
  workspaceNamePlaceholder: 'e.g., Project Management, Daily Tasks, etc.',
  workspaceDescriptionPlaceholder: 'Describe the purpose of this workspace...',
  workspaceDescriptionLLMPlaceholder: 'Describe in detail the purpose, goals, workflow of this workspace, let AI help you configure...',
  addReferenceSeed: 'Add Reference Seed (Optional)',
  addReferenceSeedDescription: 'Can be skipped, add later; this step will not write to external tools',
  pasteText: 'Paste Text',
  pasteTextPlaceholder: 'Please paste your requirements or description (5-30 lines)...',
  createAndComplete: 'Create and Complete',
  pleaseSelectCreationMethod: 'Please select a creation method first',
  back: 'Back',
  next: 'Next',
  previous: 'Previous',

  // Workspace launchpad
  workspaceBrief: 'workspaceBrief',
  firstPlaybook: 'firstPlaybook',
  recommendedPlaybook: 'recommendedPlaybook',
  runFirstPlaybook: 'runFirstPlaybook',
  startWork: 'startWork',
  startWorkDescription: 'startWorkDescription',
  openWorkspace: 'openWorkspace',
  nextIntents: 'nextIntents',
  items: 'items',
  toolConnections: 'Tool Connections',
  editBlueprint: 'editBlueprint',

  // Workspace status
  ready: 'Ready',
  pending: 'Pending',
  active: 'Active',

  // Workspace empty state
  workspaceNotConfigured: 'Workspace Not Configured',
  workspaceNotConfiguredDescription: 'This workspace requires initial setup. You can quickly create a workspace through "Minimum File Reference" or manually configure the blueprint.',
  configureWorkspace: 'Configure Workspace',
  startWorkDirectly: 'Start Work Directly',

  // Setup drawer
  assembleWorkspace: 'Assemble Workspace',
  minimumFileReference: 'Minimum File Reference (MFR)',
  minimumFileReferenceDescription: 'Quick workspace creation: paste text, upload a file, or paste URLs, the system will automatically generate workspace blueprint.',
  referenceTextToStartWorkspace: 'Reference Text to Start Workspace',
  close: 'Close',
  processing: 'Processing...',
  workspaceConfigured: 'Workspace configured successfully!',
  configurationFailed: 'Configuration failed:',
  creationFailed: 'Creation failed:',

  // Other methods (coming soon)
  otherMethods: 'Other methods (Coming soon):',
  uploadFile: '📄 Upload File',
  pasteUrl: '🔗 Paste URL',

  // Error messages
  errorLoadingWorkspace: 'Error Loading Workspace',
  workspaceNotFound: 'Workspace not found',
  loadingWorkspace: 'Loading workspace...',
} as const satisfies Partial<Record<MessageKey, string>>;

