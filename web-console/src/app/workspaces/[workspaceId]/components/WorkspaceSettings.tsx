'use client';

import React, { useState, useEffect } from 'react';
import PathChangeConfirmDialog from '@/components/PathChangeConfirmDialog';
import ResourceBindingPanel from './ResourceBindingPanel';
import ToolOverlayPanel from './ToolOverlayPanel';
import DataSourceOverlayPanel from './DataSourceOverlayPanel';
import CapabilityExtensionSlot from './CapabilityExtensionSlot';

type ExecutionMode = 'qa' | 'execution' | 'hybrid';
type ExecutionPriority = 'low' | 'medium' | 'high';
type ProjectAssignmentMode = 'auto_silent' | 'assistive' | 'manual_first';

interface Workspace {
  id: string;
  title: string;
  storage_base_path?: string;
  artifacts_dir?: string;
  storage_config?: any;
  execution_mode?: ExecutionMode;
  expected_artifacts?: string[];
  execution_priority?: ExecutionPriority;
  project_assignment_mode?: ProjectAssignmentMode;
  playbook_auto_execution_config?: Record<string, {
    auto_execute?: boolean;
    confidence_threshold?: number;
  }>;
}

interface WorkspaceSettingsProps {
  workspace: Workspace | null;
  workspaceId: string;
  apiUrl: string;
  onUpdate?: () => void;
}

const EXECUTION_MODE_OPTIONS: { value: ExecutionMode; label: string; icon: string; description: string }[] = [
  { value: 'qa', label: 'Chat First', icon: 'chat', description: 'Conversation-oriented, execution as supplement' },
  { value: 'execution', label: 'Execution First', icon: 'zap', description: 'Action-oriented, direct output' },
  { value: 'hybrid', label: 'Chat & Execute', icon: 'refresh', description: 'Balance conversation with action' },
];

const EXECUTION_PRIORITY_OPTIONS: { value: ExecutionPriority; label: string; description: string }[] = [
  { value: 'low', label: 'Conservative', description: 'Execute only at high confidence (90%)' },
  { value: 'medium', label: 'Balanced', description: 'Medium confidence threshold (80%)' },
  { value: 'high', label: 'Aggressive', description: 'Low threshold, fast execution (60%)' },
];

const PROJECT_ASSIGNMENT_MODE_OPTIONS: { value: ProjectAssignmentMode; label: string; description: string }[] = [
  { value: 'auto_silent', label: 'Auto Classify', description: 'Auto classify with labels, prompt only when uncertain' },
  { value: 'assistive', label: 'Assisted', description: 'Auto classify, prompt for confirmation at medium-low confidence' },
  { value: 'manual_first', label: 'Manual', description: 'Manual selection required, AI provides suggestions only' },
];

const COMMON_ARTIFACTS = ['docx', 'pptx', 'xlsx', 'pdf', 'md', 'html'];

export default function WorkspaceSettings({
  workspace,
  workspaceId,
  apiUrl,
  onUpdate
}: WorkspaceSettingsProps) {
  // Storage settings state
  const [storageBasePath, setStorageBasePath] = useState('');
  const [artifactsDir, setArtifactsDir] = useState('artifacts');
  const [originalStorageBasePath, setOriginalStorageBasePath] = useState('');
  const [originalArtifactsDir, setOriginalArtifactsDir] = useState('');
  const [storagePathChanged, setStoragePathChanged] = useState(false);

  // Execution mode settings state
  const [executionMode, setExecutionMode] = useState<ExecutionMode>('hybrid');
  const [executionPriority, setExecutionPriority] = useState<ExecutionPriority>('medium');
  const [projectAssignmentMode, setProjectAssignmentMode] = useState<ProjectAssignmentMode>('auto_silent');
  const [expectedArtifacts, setExpectedArtifacts] = useState<string[]>([]);
  const [originalExecutionMode, setOriginalExecutionMode] = useState<ExecutionMode>('hybrid');
  const [originalExecutionPriority, setOriginalExecutionPriority] = useState<ExecutionPriority>('medium');
  const [originalProjectAssignmentMode, setOriginalProjectAssignmentMode] = useState<ProjectAssignmentMode>('auto_silent');
  const [originalExpectedArtifacts, setOriginalExpectedArtifacts] = useState<string[]>([]);
  const [executionSettingsChanged, setExecutionSettingsChanged] = useState(false);

  // Intent extraction auto-execution settings
  const [intentExtractionAutoExecute, setIntentExtractionAutoExecute] = useState(false);
  const [intentExtractionThreshold, setIntentExtractionThreshold] = useState(0.8);
  const [originalIntentExtractionAutoExecute, setOriginalIntentExtractionAutoExecute] = useState(false);
  const [originalIntentExtractionThreshold, setOriginalIntentExtractionThreshold] = useState(0.8);
  const [savingIntentExtraction, setSavingIntentExtraction] = useState(false);
  const [intentExtractionError, setIntentExtractionError] = useState<string | null>(null);
  const [intentExtractionSuccess, setIntentExtractionSuccess] = useState(false);

  // UI state
  const [saving, setSaving] = useState(false);
  const [savingExecution, setSavingExecution] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [executionError, setExecutionError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [executionSuccess, setExecutionSuccess] = useState(false);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);


  useEffect(() => {
    if (workspace) {
      // Storage settings
      const basePath = workspace.storage_base_path || '';
      const dir = workspace.artifacts_dir || 'artifacts';
      setStorageBasePath(basePath);
      setArtifactsDir(dir);
      setOriginalStorageBasePath(basePath);
      setOriginalArtifactsDir(dir);
      setStoragePathChanged(false);

      // Execution mode settings
      const mode = workspace.execution_mode || 'hybrid';
      const priority = workspace.execution_priority || 'medium';
      const assignmentMode = workspace.project_assignment_mode || 'auto_silent';
      const artifacts = workspace.expected_artifacts || [];
      setExecutionMode(mode);
      setExecutionPriority(priority);
      setProjectAssignmentMode(assignmentMode);
      setExpectedArtifacts(artifacts);
      setOriginalExecutionMode(mode);
      setOriginalExecutionPriority(priority);
      setOriginalProjectAssignmentMode(assignmentMode);
      setOriginalExpectedArtifacts(artifacts);
      setExecutionSettingsChanged(false);

      // Intent extraction auto-execution settings
      const intentConfig = workspace.playbook_auto_execution_config?.intent_extraction;
      const autoExecute = intentConfig?.auto_execute || false;
      const threshold = intentConfig?.confidence_threshold || 0.8;
      setIntentExtractionAutoExecute(autoExecute);
      setIntentExtractionThreshold(threshold);
      setOriginalIntentExtractionAutoExecute(autoExecute);
      setOriginalIntentExtractionThreshold(threshold);
    }
  }, [workspace]);

  useEffect(() => {
    const pathChanged =
      storageBasePath !== originalStorageBasePath ||
      artifactsDir !== originalArtifactsDir;
    setStoragePathChanged(pathChanged);
  }, [storageBasePath, artifactsDir, originalStorageBasePath, originalArtifactsDir]);

  useEffect(() => {
    const changed =
      executionMode !== originalExecutionMode ||
      executionPriority !== originalExecutionPriority ||
      projectAssignmentMode !== originalProjectAssignmentMode ||
      JSON.stringify(expectedArtifacts.sort()) !== JSON.stringify(originalExpectedArtifacts.sort());
    setExecutionSettingsChanged(changed);
  }, [executionMode, executionPriority, projectAssignmentMode, expectedArtifacts, originalExecutionMode, originalExecutionPriority, originalProjectAssignmentMode, originalExpectedArtifacts]);

  const handleToggleArtifact = (artifact: string) => {
    setExpectedArtifacts(prev =>
      prev.includes(artifact)
        ? prev.filter(a => a !== artifact)
        : [...prev, artifact]
    );
  };

  const handleSaveExecutionSettings = async () => {
    setSavingExecution(true);
    setExecutionError(null);
    setExecutionSuccess(false);

    try {
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          execution_mode: executionMode,
          execution_priority: executionPriority,
          project_assignment_mode: projectAssignmentMode,
          expected_artifacts: expectedArtifacts,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to update' }));
        throw new Error(errorData.detail || 'Failed to update execution settings');
      }

      const updated = await response.json();
      setOriginalExecutionMode(updated.execution_mode || 'hybrid');
      setOriginalExecutionPriority(updated.execution_priority || 'medium');
      setOriginalProjectAssignmentMode(updated.project_assignment_mode || 'auto_silent');
      setOriginalExpectedArtifacts(updated.expected_artifacts || []);
      setExecutionSettingsChanged(false);
      setExecutionSuccess(true);
      setTimeout(() => setExecutionSuccess(false), 3000);

      if (onUpdate) {
        onUpdate();
      }
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
      // Call backend API to open folder
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/open-folder`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: storageBasePath })
        }
      );

      if (!response.ok) {
        throw new Error('Failed to open folder');
      }
      // TODO: Show success toast
    } catch (err) {
      console.error('Failed to open folder:', err);
      // Fallback: Show path in alert
      alert(`Path: ${storageBasePath}\n\nPlease open this path manually in your file manager.`);
    }
  };

  const handleSaveStorageSettings = async () => {
    if (!storageBasePath.trim()) {
      setError('Please enter a base storage path');
      return;
    }

    // If path changed, show confirmation dialog
    if (storagePathChanged) {
      setShowConfirmDialog(true);
      return;
    }

    // If no change, save directly
    await performSave();
  };

  const performSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);
    setShowConfirmDialog(false);

    try {
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          storage_base_path: storageBasePath.trim(),
          artifacts_dir: artifactsDir.trim() || 'artifacts',
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to update workspace' }));
        throw new Error(errorData.detail || 'Failed to update workspace');
      }

      const updatedWorkspace = await response.json();
      setOriginalStorageBasePath(updatedWorkspace.storage_base_path || '');
      setOriginalArtifactsDir(updatedWorkspace.artifacts_dir || 'artifacts');
      setStoragePathChanged(false);
      setSuccess(true);

      // Clear success message after 3 seconds
      setTimeout(() => setSuccess(false), 3000);

      if (onUpdate) {
        onUpdate();
      }
    } catch (err: any) {
      setError(err.message || 'Save failed, please try again later');
      console.error('Failed to save storage settings:', err);
    } finally {
      setSaving(false);
    }
  };

  if (!workspace) {
    return (
      <div className="p-6">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  return (
    <>
      {/* Path Change Confirmation Dialog */}
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
        {/* Execution Mode Settings */}
        <div className="space-y-4">
          <div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">Execution Mode</h2>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Configure the AI assistant behavior mode to balance conversation and execution.
            </p>
          </div>

          {/* Execution Mode Selector */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Behavior Mode
            </label>
            <div className="grid grid-cols-3 gap-3">
              {EXECUTION_MODE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  onClick={() => setExecutionMode(option.value)}
                  className={`
                  p-3 rounded-lg border-2 text-left transition-all
                  ${executionMode === option.value
                      ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                      : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                    }
                `}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-lg">{option.icon}</span>
                    <span className={`font-medium ${executionMode === option.value ? 'text-blue-700 dark:text-blue-300' : 'text-gray-900 dark:text-gray-100'}`}>
                      {option.label}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{option.description}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Execution Priority (only show when not in QA mode) */}
          {executionMode !== 'qa' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Auto-Trigger Threshold
              </label>
              <div className="flex gap-2">
                {EXECUTION_PRIORITY_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    onClick={() => setExecutionPriority(option.value)}
                    className={`
                    px-4 py-2 rounded-lg border text-sm transition-all
                    ${executionPriority === option.value
                        ? 'border-amber-500 bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300'
                        : 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:border-gray-300'
                      }
                  `}
                    title={option.description}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                {EXECUTION_PRIORITY_OPTIONS.find(o => o.value === executionPriority)?.description}
              </p>
            </div>
          )}

          {/* Project Assignment Mode */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Project Classification Mode
            </label>
            <div className="flex gap-2">
              {PROJECT_ASSIGNMENT_MODE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  onClick={() => setProjectAssignmentMode(option.value)}
                  className={`
                  px-4 py-2 rounded-lg border text-sm transition-all
                  ${projectAssignmentMode === option.value
                      ? 'border-purple-500 bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300'
                      : 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:border-gray-300'
                    }
                `}
                  title={option.description}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {PROJECT_ASSIGNMENT_MODE_OPTIONS.find(o => o.value === projectAssignmentMode)?.description}
            </p>
          </div>

          {/* Intent Extraction Auto-Execution */}
          <div className="border-t border-gray-200 dark:border-gray-700 pt-4 mt-4">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Intent Extraction Auto-Execute
            </label>
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="intent-extraction-auto-execute"
                  checked={intentExtractionAutoExecute}
                  onChange={(e) => setIntentExtractionAutoExecute(e.target.checked)}
                  className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
                />
                <label htmlFor="intent-extraction-auto-execute" className="text-sm text-gray-700 dark:text-gray-300">
                  Auto-execute intent extraction when confidence meets threshold
                </label>
              </div>
              {intentExtractionAutoExecute && (
                <div className="ml-7 space-y-2">
                  <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                    <span>Confidence Threshold</span>
                    <span className="text-purple-700 dark:text-purple-300 font-bold">
                      {intentExtractionThreshold.toFixed(1)}
                    </span>
                  </div>
                  <input
                    type="range"
                    min={0.5}
                    max={1.0}
                    step={0.1}
                    value={intentExtractionThreshold}
                    onChange={(e) => setIntentExtractionThreshold(parseFloat(e.target.value))}
                    className="w-full accent-purple-600"
                  />
                  <div className="flex justify-between text-[10px] text-gray-400 dark:text-gray-500">
                    {[0.5, 0.6, 0.7, 0.8, 0.9, 1.0].map(v => (
                      <span key={v}>{v.toFixed(1)}</span>
                    ))}
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    When intent extraction confidence >= {intentExtractionThreshold.toFixed(1)}, auto-execute without manual confirmation
                  </p>
                </div>
              )}
              <button
                onClick={async () => {
                  setSavingIntentExtraction(true);
                  setIntentExtractionError(null);
                  setIntentExtractionSuccess(false);

                  try {
                    const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/playbook-auto-exec-config`, {
                      method: 'PATCH',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({
                        playbook_code: 'intent_extraction',
                        auto_execute: intentExtractionAutoExecute,
                        confidence_threshold: intentExtractionThreshold,
                      }),
                    });

                    if (!response.ok) {
                      const errorData = await response.json().catch(() => ({ detail: 'Failed to update' }));
                      throw new Error(errorData.detail || 'Failed to update intent extraction settings');
                    }

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
                }}
                disabled={savingIntentExtraction ||
                  (intentExtractionAutoExecute === originalIntentExtractionAutoExecute &&
                    intentExtractionThreshold === originalIntentExtractionThreshold)}
                className="px-3 py-1.5 text-sm bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
              >
                {savingIntentExtraction ? 'Saving...' : 'Save Intent Extraction Settings'}
              </button>
              {intentExtractionError && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-2">
                  <p className="text-xs text-red-700 dark:text-red-300">{intentExtractionError}</p>
                </div>
              )}
              {intentExtractionSuccess && (
                <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-2">
                  <p className="text-xs text-green-700 dark:text-green-300">Intent extraction settings saved</p>
                </div>
              )}
            </div>
          </div>

          {/* Expected Artifacts */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Expected Output Types
            </label>
            <div className="flex flex-wrap gap-2">
              {COMMON_ARTIFACTS.map((artifact) => (
                <button
                  key={artifact}
                  onClick={() => handleToggleArtifact(artifact)}
                  className={`
                  px-3 py-1.5 rounded-full text-sm transition-all
                  ${expectedArtifacts.includes(artifact)
                      ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-700'
                      : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700 hover:bg-gray-200 dark:hover:bg-gray-700'
                    }
                `}
                >
                  {artifact.toUpperCase()}
                </button>
              ))}
            </div>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Select the output file types for this workspace. AI will prioritize producing these document types.
            </p>
          </div>

          {/* Execution Settings Error */}
          {executionError && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
              <p className="text-sm text-red-700 dark:text-red-300">{executionError}</p>
            </div>
          )}

          {/* Execution Settings Success */}
          {executionSuccess && (
            <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-3">
              <p className="text-sm text-green-700 dark:text-green-300">Execution mode settings saved</p>
            </div>
          )}

          {/* Save Execution Settings Button */}
          <div className="flex justify-end">
            <button
              onClick={handleSaveExecutionSettings}
              disabled={savingExecution || !executionSettingsChanged}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
            >
              {savingExecution ? 'Saving...' : 'Save Execution Mode'}
            </button>
          </div>
        </div>

        {/* Divider */}
        <hr className="border-gray-200 dark:border-gray-700" />

        {/* Storage Settings */}
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">Storage Settings</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Configure the workspace file storage path. All Playbook artifacts will be stored under this path.
          </p>
        </div>

        {/* Warning if no storage path */}
        {!workspace.storage_base_path && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3 flex-1">
                <h3 className="text-sm font-medium text-yellow-800">Warning: Storage path not configured</h3>
                <p className="mt-1 text-sm text-yellow-700">
                  Storage path not configured for this workspace. Please set a path, or go to{' '}
                  <a href="/settings" className="underline font-medium">System Settings</a>{' '}
                  to enable Local File System access.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Storage Settings Form */}
        <div className="space-y-4">
          {/* Storage Base Path */}
          <div>
            <label htmlFor="storage-base-path" className="block text-sm font-medium text-gray-700 mb-1">
              Base Storage Path
            </label>
            <div className="flex items-center gap-2">
              <input
                id="storage-base-path"
                type="text"
                value={storageBasePath}
                onChange={(e) => setStorageBasePath(e.target.value)}
                placeholder="/path/to/storage"
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
              {storageBasePath && (
                <button
                  onClick={handleOpenFolder}
                  className="px-3 py-2 text-sm bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 transition-colors"
                  title="Open containing folder"
                >
                  Open Folder
                </button>
              )}
            </div>
            <p className="mt-1 text-xs text-gray-500">
              All Playbook artifacts will be stored in subdirectories under this path
            </p>
          </div>

          {/* Artifacts Directory */}
          <div>
            <label htmlFor="artifacts-dir" className="block text-sm font-medium text-gray-700 mb-1">
              Artifacts Directory
            </label>
            <input
              id="artifacts-dir"
              type="text"
              value={artifactsDir}
              onChange={(e) => setArtifactsDir(e.target.value)}
              placeholder="artifacts"
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            <p className="mt-1 text-xs text-gray-500">
              Artifacts will be stored in this subdirectory under the base path (default: artifacts)
            </p>
          </div>

          {/* Path Change Warning */}
          {storagePathChanged && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
              <div className="flex items-start">
                <div className="flex-shrink-0">
                  <svg className="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                  </svg>
                </div>
                <div className="ml-3 flex-1">
                  <h3 className="text-sm font-medium text-yellow-800">Storage Path Change Warning</h3>
                  <p className="mt-1 text-sm text-yellow-700">
                    Changing storage path affects future file archiving. Existing files may not be found automatically.
                    Please confirm you understand the impact of this change.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <div className="flex items-start">
                <div className="flex-shrink-0">
                  <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                  </svg>
                </div>
                <div className="ml-3 flex-1">
                  <p className="text-sm text-red-700">{error}</p>
                </div>
              </div>
            </div>
          )}

          {/* Success Message */}
          {success && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
              <div className="flex items-start">
                <div className="flex-shrink-0">
                  <svg className="h-5 w-5 text-green-400" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                  </svg>
                </div>
                <div className="ml-3 flex-1">
                  <p className="text-sm text-green-700">Storage settings saved successfully</p>
                </div>
              </div>
            </div>
          )}

          {/* Save Button */}
          <div className="flex items-center justify-end gap-2">
            <button
              onClick={handleSaveStorageSettings}
              disabled={saving || !storagePathChanged}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </div>

        {/* Divider */}
        <hr className="border-gray-200 dark:border-gray-700" />

        {/* Resource Bindings */}
        <div>
          <ResourceBindingPanel workspaceId={workspaceId} />
        </div>

        {/* Divider */}
        <hr className="border-gray-200 dark:border-gray-700" />

        {/* Tool Overlay */}
        <div>
          <ToolOverlayPanel workspaceId={workspaceId} />
        </div>

        {/* Divider */}
        <hr className="border-gray-200 dark:border-gray-700" />

        {/* Data Source Overlay */}
        <div>
          <DataSourceOverlayPanel workspaceId={workspaceId} />
        </div>

        {/* Capability Extension Panels */}
        <hr className="border-gray-200 dark:border-gray-700" />
        <CapabilityExtensionSlot
          section="runtime-environments"
          workspaceId={workspaceId}
        />
      </div>
    </>
  );
}

