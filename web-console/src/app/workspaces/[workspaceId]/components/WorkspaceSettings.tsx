'use client';

import { useEffect, useState } from 'react';
import PathChangeConfirmDialog from '@/components/PathChangeConfirmDialog';
import ResourceBindingPanel from './ResourceBindingPanel';
import ToolOverlayPanel from './ToolOverlayPanel';
import DataSourceOverlayPanel from './DataSourceOverlayPanel';
import CapabilityExtensionSlot from './CapabilityExtensionSlot';
import WorkspaceSettingsExecutionSection from './WorkspaceSettingsExecutionSection';
import WorkspaceSettingsStorageSection from './WorkspaceSettingsStorageSection';
import {
  buildExecutionSettingsRequestPayload,
  buildStorageSettingsRequestPayload,
  openWorkspaceFolder,
  updateIntentExtractionSettings,
  updateWorkspaceExecutionSettings,
  updateWorkspaceSgrSettings,
  updateWorkspaceStorageSettings,
} from './workspaceSettingsApi';
import {
  buildIntentExtractionRequestPayload,
  buildSgrSettingsRequestPayload,
  deriveWorkspaceSettings,
  hasExecutionSettingsChanged,
  hasStorageSettingsChanged,
  toggleExpectedArtifact,
} from './workspaceSettingsState';
import type {
  ExecutionMode,
  ExecutionPriority,
  ProjectAssignmentMode,
  SgrMode,
  WorkspaceSettingsProps,
} from './workspaceSettingsTypes';

export default function WorkspaceSettings({
  workspace,
  workspaceId,
  apiUrl,
  onUpdate
}: WorkspaceSettingsProps) {
  const [storageBasePath, setStorageBasePath] = useState('');
  const [artifactsDir, setArtifactsDir] = useState('artifacts');
  const [originalStorageBasePath, setOriginalStorageBasePath] = useState('');
  const [originalArtifactsDir, setOriginalArtifactsDir] = useState('');
  const [storagePathChanged, setStoragePathChanged] = useState(false);

  const [executionMode, setExecutionMode] = useState<ExecutionMode>('hybrid');
  const [executionPriority, setExecutionPriority] = useState<ExecutionPriority>('medium');
  const [projectAssignmentMode, setProjectAssignmentMode] = useState<ProjectAssignmentMode>('auto_silent');
  const [expectedArtifacts, setExpectedArtifacts] = useState<string[]>([]);
  const [originalExecutionMode, setOriginalExecutionMode] = useState<ExecutionMode>('hybrid');
  const [originalExecutionPriority, setOriginalExecutionPriority] = useState<ExecutionPriority>('medium');
  const [originalProjectAssignmentMode, setOriginalProjectAssignmentMode] = useState<ProjectAssignmentMode>('auto_silent');
  const [originalExpectedArtifacts, setOriginalExpectedArtifacts] = useState<string[]>([]);
  const [executionSettingsChanged, setExecutionSettingsChanged] = useState(false);

  const [intentExtractionAutoExecute, setIntentExtractionAutoExecute] = useState(false);
  const [intentExtractionThreshold, setIntentExtractionThreshold] = useState(0.8);
  const [originalIntentExtractionAutoExecute, setOriginalIntentExtractionAutoExecute] = useState(false);
  const [originalIntentExtractionThreshold, setOriginalIntentExtractionThreshold] = useState(0.8);
  const [savingIntentExtraction, setSavingIntentExtraction] = useState(false);
  const [intentExtractionError, setIntentExtractionError] = useState<string | null>(null);
  const [intentExtractionSuccess, setIntentExtractionSuccess] = useState(false);

  const [sgrEnabled, setSgrEnabled] = useState(false);
  const [sgrMode, setSgrMode] = useState<SgrMode>('inline');
  const [originalSgrEnabled, setOriginalSgrEnabled] = useState(false);
  const [originalSgrMode, setOriginalSgrMode] = useState<SgrMode>('inline');
  const [savingSgr, setSavingSgr] = useState(false);
  const [sgrError, setSgrError] = useState<string | null>(null);
  const [sgrSuccess, setSgrSuccess] = useState(false);

  const [saving, setSaving] = useState(false);
  const [savingExecution, setSavingExecution] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [executionError, setExecutionError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [executionSuccess, setExecutionSuccess] = useState(false);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  useEffect(() => {
    if (!workspace) {
      return;
    }

    const settings = deriveWorkspaceSettings(workspace);
    setStorageBasePath(settings.storage.storageBasePath);
    setArtifactsDir(settings.storage.artifactsDir);
    setOriginalStorageBasePath(settings.storage.storageBasePath);
    setOriginalArtifactsDir(settings.storage.artifactsDir);
    setStoragePathChanged(false);

    setExecutionMode(settings.execution.executionMode);
    setExecutionPriority(settings.execution.executionPriority);
    setProjectAssignmentMode(settings.execution.projectAssignmentMode);
    setExpectedArtifacts(settings.execution.expectedArtifacts);
    setOriginalExecutionMode(settings.execution.executionMode);
    setOriginalExecutionPriority(settings.execution.executionPriority);
    setOriginalProjectAssignmentMode(settings.execution.projectAssignmentMode);
    setOriginalExpectedArtifacts(settings.execution.expectedArtifacts);
    setExecutionSettingsChanged(false);

    setIntentExtractionAutoExecute(settings.intentExtraction.autoExecute);
    setIntentExtractionThreshold(settings.intentExtraction.threshold);
    setOriginalIntentExtractionAutoExecute(settings.intentExtraction.autoExecute);
    setOriginalIntentExtractionThreshold(settings.intentExtraction.threshold);

    setSgrEnabled(settings.sgr.enabled);
    setSgrMode(settings.sgr.mode);
    setOriginalSgrEnabled(settings.sgr.enabled);
    setOriginalSgrMode(settings.sgr.mode);
  }, [workspace]);

  useEffect(() => {
    setStoragePathChanged(hasStorageSettingsChanged(
      { storageBasePath, artifactsDir },
      { storageBasePath: originalStorageBasePath, artifactsDir: originalArtifactsDir },
    ));
  }, [storageBasePath, artifactsDir, originalStorageBasePath, originalArtifactsDir]);

  useEffect(() => {
    setExecutionSettingsChanged(hasExecutionSettingsChanged(
      { executionMode, executionPriority, projectAssignmentMode, expectedArtifacts },
      {
        executionMode: originalExecutionMode,
        executionPriority: originalExecutionPriority,
        projectAssignmentMode: originalProjectAssignmentMode,
        expectedArtifacts: originalExpectedArtifacts,
      },
    ));
  }, [
    executionMode,
    executionPriority,
    projectAssignmentMode,
    expectedArtifacts,
    originalExecutionMode,
    originalExecutionPriority,
    originalProjectAssignmentMode,
    originalExpectedArtifacts,
  ]);

  const handleSaveExecutionSettings = async () => {
    setSavingExecution(true);
    setExecutionError(null);
    setExecutionSuccess(false);

    try {
      const updated = await updateWorkspaceExecutionSettings(
        { apiUrl, workspaceId },
        buildExecutionSettingsRequestPayload({
          executionMode,
          executionPriority,
          projectAssignmentMode,
          expectedArtifacts,
        }),
      );
      setOriginalExecutionMode(updated.execution_mode || 'hybrid');
      setOriginalExecutionPriority(updated.execution_priority || 'medium');
      setOriginalProjectAssignmentMode(updated.project_assignment_mode || 'auto_silent');
      setOriginalExpectedArtifacts(updated.expected_artifacts || []);
      setExecutionSettingsChanged(false);
      setExecutionSuccess(true);
      setTimeout(() => setExecutionSuccess(false), 3000);
      onUpdate?.();
    } catch (err: any) {
      setExecutionError(err.message || 'Save failed');
      console.error('Failed to save execution settings:', err);
    } finally {
      setSavingExecution(false);
    }
  };

  const handleOpenFolder = async () => {
    if (!storageBasePath) {
      alert('Please configure the base storage path first');
      return;
    }

    try {
      await openWorkspaceFolder({ apiUrl, workspaceId }, storageBasePath);
    } catch (err) {
      console.error('Failed to open folder:', err);
      alert(`Path: ${storageBasePath}\n\nPlease open this path manually in your file manager.`);
    }
  };

  const handleSaveStorageSettings = async () => {
    if (!storageBasePath.trim()) {
      setError('Please enter a base storage path');
      return;
    }

    if (storagePathChanged) {
      setShowConfirmDialog(true);
      return;
    }

    await performSave();
  };

  const performSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);
    setShowConfirmDialog(false);

    try {
      const updatedWorkspace = await updateWorkspaceStorageSettings(
        { apiUrl, workspaceId },
        buildStorageSettingsRequestPayload({ storageBasePath, artifactsDir }),
      );
      setOriginalStorageBasePath(updatedWorkspace.storage_base_path || '');
      setOriginalArtifactsDir(updatedWorkspace.artifacts_dir || 'artifacts');
      setStoragePathChanged(false);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
      onUpdate?.();
    } catch (err: any) {
      setError(err.message || 'Save failed, please try again later');
      console.error('Failed to save storage settings:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveIntentExtraction = async () => {
    setSavingIntentExtraction(true);
    setIntentExtractionError(null);
    setIntentExtractionSuccess(false);

    try {
      await updateIntentExtractionSettings(
        { apiUrl, workspaceId },
        buildIntentExtractionRequestPayload({
          autoExecute: intentExtractionAutoExecute,
          threshold: intentExtractionThreshold,
        }),
      );
      setOriginalIntentExtractionAutoExecute(intentExtractionAutoExecute);
      setOriginalIntentExtractionThreshold(intentExtractionThreshold);
      setIntentExtractionSuccess(true);
      setTimeout(() => setIntentExtractionSuccess(false), 3000);
      onUpdate?.();
    } catch (err: any) {
      setIntentExtractionError(err.message || 'Failed to save settings');
    } finally {
      setSavingIntentExtraction(false);
    }
  };

  const handleSaveSgr = async () => {
    setSavingSgr(true);
    setSgrError(null);
    setSgrSuccess(false);

    try {
      await updateWorkspaceSgrSettings(
        { apiUrl, workspaceId },
        buildSgrSettingsRequestPayload(workspace, {
          enabled: sgrEnabled,
          mode: sgrMode,
        }),
      );
      setOriginalSgrEnabled(sgrEnabled);
      setOriginalSgrMode(sgrMode);
      setSgrSuccess(true);
      setTimeout(() => setSgrSuccess(false), 3000);
      onUpdate?.();
    } catch (err: any) {
      setSgrError(err.message || 'Failed to save settings');
    } finally {
      setSavingSgr(false);
    }
  };

  if (!workspace) {
    return (
      <div className="p-6">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  const intentExtractionChanged =
    intentExtractionAutoExecute !== originalIntentExtractionAutoExecute ||
    intentExtractionThreshold !== originalIntentExtractionThreshold;
  const sgrChanged = sgrEnabled !== originalSgrEnabled || sgrMode !== originalSgrMode;

  return (
    <>
      <PathChangeConfirmDialog
        isOpen={showConfirmDialog}
        oldPath={originalStorageBasePath}
        newPath={storageBasePath}
        oldArtifactsDir={originalArtifactsDir}
        newArtifactsDir={artifactsDir}
        onConfirm={performSave}
        onCancel={() => setShowConfirmDialog(false)}
      />

      <div className="p-6 space-y-8">
        <WorkspaceSettingsExecutionSection
          executionMode={executionMode}
          executionPriority={executionPriority}
          projectAssignmentMode={projectAssignmentMode}
          expectedArtifacts={expectedArtifacts}
          executionSettingsChanged={executionSettingsChanged}
          savingExecution={savingExecution}
          executionError={executionError}
          executionSuccess={executionSuccess}
          intentExtractionAutoExecute={intentExtractionAutoExecute}
          intentExtractionThreshold={intentExtractionThreshold}
          intentExtractionChanged={intentExtractionChanged}
          savingIntentExtraction={savingIntentExtraction}
          intentExtractionError={intentExtractionError}
          intentExtractionSuccess={intentExtractionSuccess}
          sgrEnabled={sgrEnabled}
          sgrMode={sgrMode}
          sgrChanged={sgrChanged}
          savingSgr={savingSgr}
          sgrError={sgrError}
          sgrSuccess={sgrSuccess}
          onExecutionModeChange={setExecutionMode}
          onExecutionPriorityChange={setExecutionPriority}
          onProjectAssignmentModeChange={setProjectAssignmentMode}
          onToggleArtifact={(artifact) => setExpectedArtifacts((current) => toggleExpectedArtifact(current, artifact))}
          onIntentExtractionAutoExecuteChange={setIntentExtractionAutoExecute}
          onIntentExtractionThresholdChange={setIntentExtractionThreshold}
          onSgrEnabledChange={setSgrEnabled}
          onSgrModeChange={setSgrMode}
          onSaveExecutionSettings={handleSaveExecutionSettings}
          onSaveIntentExtraction={handleSaveIntentExtraction}
          onSaveSgr={handleSaveSgr}
        />

        <hr className="border-gray-200 dark:border-gray-700" />

        <WorkspaceSettingsStorageSection
          hasWorkspaceStoragePath={Boolean(workspace.storage_base_path)}
          storageBasePath={storageBasePath}
          artifactsDir={artifactsDir}
          storagePathChanged={storagePathChanged}
          saving={saving}
          error={error}
          success={success}
          onStorageBasePathChange={setStorageBasePath}
          onArtifactsDirChange={setArtifactsDir}
          onOpenFolder={handleOpenFolder}
          onSaveStorageSettings={handleSaveStorageSettings}
        />

        <hr className="border-gray-200 dark:border-gray-700" />

        <div>
          <ResourceBindingPanel workspaceId={workspaceId} />
        </div>

        <hr className="border-gray-200 dark:border-gray-700" />

        <div>
          <ToolOverlayPanel workspaceId={workspaceId} />
        </div>

        <hr className="border-gray-200 dark:border-gray-700" />

        <div>
          <DataSourceOverlayPanel workspaceId={workspaceId} />
        </div>

        <hr className="border-gray-200 dark:border-gray-700" />
        <CapabilityExtensionSlot
          section="runtime-environments"
          workspaceId={workspaceId}
        />
      </div>
    </>
  );
}
