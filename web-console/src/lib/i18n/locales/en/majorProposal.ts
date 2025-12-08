/**
 * majorProposal i18n messages (English)
 */
import type { MessageKey } from '../../keys';

export const majorProposalEn = {

  // Major Proposal errors
  majorProposalDraftGenerated: 'Chapter draft generated!',
  majorProposalGenerateFailed: 'Generation failed: {error}',
  majorProposalAssembleFailed: 'Assembly failed: {error}',
  majorProposalAssembled: 'File assembly complete!\n\nMarkdown content generated.\nDOCX file path: {path}',
  majorProposalEnterContent: 'Please enter some content',
  majorProposalSaved: 'Saved',
  majorProposalSaveFailed: 'Save failed: {error}',
  majorProposalSelectTemplate: 'Please select a template',
  majorProposalEnterProjectName: 'Please enter project name',
  majorProposalCreateProjectFailed: 'Failed to create project: {error}',
  majorProposalTemplateCreated: 'Template created successfully! ID: {id}',
  majorProposalUploadFailed: 'Upload failed: {error}',
  majorProposalSelectAtLeastOneFile: 'Please select at least one file',
  majorProposalProjectNotFound: 'Project not found',
  majorProposalTemplateNotFound: 'Template not found',
  majorProposalAssembling: 'Assembling...',
  majorProposalAssembleComplete: 'Assemble Complete File',
  majorProposalGenerating: 'Generating...',
  majorProposalGenerateDraft: 'Generate Chapter Draft',
  majorProposalSaving: 'Saving...',
  majorProposalSaveEdit: 'Save Edit',
  majorProposalEnterInfo: 'Please enter relevant information...',
  majorProposalEnterProjectNamePlaceholder: 'e.g., My startup grant application',
  majorProposalCreating: 'Creating...',
  majorProposalCreateProject: 'Create Project',
  majorProposalUploading: 'Uploading...',
  majorProposalUpload: 'Upload',
  majorProposalEnterTemplateNamePlaceholder: 'e.g., 2025 Startup Grant Application',
  majorProposalWordLimit: 'Word limit: {min} - {max} words',
  majorProposalNoWordLimit: 'Word limit: {min} - No limit words',

} as const satisfies Partial<Record<MessageKey, string>>;
