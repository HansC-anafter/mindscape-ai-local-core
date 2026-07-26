'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useT } from '../../../../lib/i18n';
import { ConfiguredDirectoriesSection } from './localFilesystemManager/ConfiguredDirectoriesSection';
import { DirectorySelectionSection } from './localFilesystemManager/DirectorySelectionSection';
import { LocalFilesystemFooterSection, LocalFilesystemStatusSection } from './localFilesystemManager/LocalFilesystemStatusSection';
import { PathInputDialog } from './localFilesystemManager/PathInputDialog';
import {
  configureLocalFilesystem,
  loadConfiguredFilesystemDirectories,
  loadUsedPlaybookCodes,
  restartSystemSettings,
  saveWorkspaceStorageConfig,
  toDirectoryConfigs,
  updateHostDocumentsPath,
} from './localFilesystemManager/resourceActions';
import { WorkspaceDirectoryRequiredOverlay } from './localFilesystemManager/WorkspaceDirectoryRequiredOverlay';
import { WorkspaceStorageSections } from './localFilesystemManager/WorkspaceStorageSections';
import {
  addDirectorySelection,
  deriveWorkspaceDirectoryPickerPath,
  deriveWorkspaceFileInputDefaultPath,
  extractUsername,
  getCommonDirectories,
  getDirectoryPrompt,
  getFilteredCommonDirectories,
  isAbsoluteStoragePath,
  removeDirectorySelection,
  toggleCommonDirectorySelection,
} from './localFilesystemManager/pathUtils';
import type { DirectoryActionResult } from './localFilesystemManager/pathUtils';
import {
  CommonDirectory,
  ConfiguredDirectory,
  DirectoryConfig,
  PlaybookStorageConfig,
} from './localFilesystemManager/types';

export interface LocalFilesystemManagerContentProps {
  onClose?: () => void;
  onSuccess: () => void;
  workspaceId?: string;
  apiUrl?: string;
  workspaceTitle?: string;
  workspaceMode?: boolean;
  initialStorageBasePath?: string;
  initialArtifactsDir?: string;
  initialPlaybookStorageConfig?: Record<string, PlaybookStorageConfig>;
  showHeader?: boolean;
}

export function LocalFilesystemManagerContent({
  onClose,
  onSuccess,
  workspaceId,
  apiUrl,
  workspaceMode = false,
  workspaceTitle,
  initialStorageBasePath,
  initialArtifactsDir,
  initialPlaybookStorageConfig,
  showHeader = true,
}: LocalFilesystemManagerContentProps) {
  const t = useT();
  const [saving, setSaving] = useState(false);
  const [directories, setDirectories] = useState<DirectoryConfig[]>([]);
  const [newDirectory, setNewDirectory] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [requiresRestart, setRequiresRestart] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [configuredDirs, setConfiguredDirs] = useState<ConfiguredDirectory[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCommonDirs, setSelectedCommonDirs] = useState<Set<string>>(new Set());
  const [savedStorageBasePath, setSavedStorageBasePath] = useState<string | undefined>(initialStorageBasePath);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [commonDirectories] = useState<CommonDirectory[]>(() => getCommonDirectories());
  const isWindows = typeof window !== 'undefined' && navigator.platform.toLowerCase().includes('win');
  const [showPathInputDialog, setShowPathInputDialog] = useState(false);
  const [selectedDirName, setSelectedDirName] = useState('');
  const [pathInputValue, setPathInputValue] = useState('');
  const [artifactsDir, setArtifactsDir] = useState<string>(initialArtifactsDir || 'artifacts');
  const [playbookStorageConfig, setPlaybookStorageConfig] = useState<Record<string, PlaybookStorageConfig>>(initialPlaybookStorageConfig || {});
  const [usedPlaybooks, setUsedPlaybooks] = useState<string[]>([]);
  const [loadingPlaybooks, setLoadingPlaybooks] = useState(false);

  const actualUsername = extractUsername(initialStorageBasePath);
  const filteredCommonDirs = getFilteredCommonDirectories({
    actualUsername,
    commonDirectories,
    isWindows,
    workspaceMode,
  });

  const loadUsedPlaybooks = useCallback(async () => {
    if (!workspaceId || apiUrl == null) return;

    setLoadingPlaybooks(true);
    try {
      setUsedPlaybooks(await loadUsedPlaybookCodes({ apiUrl, workspaceId }));
    } catch (err) {
      console.error('Failed to load used playbooks:', err);
    } finally {
      setLoadingPlaybooks(false);
    }
  }, [apiUrl, workspaceId]);

  const loadConfiguredDirectories = useCallback(async () => {
    try {
      setLoading(true);
      const connections = await loadConfiguredFilesystemDirectories();
      setConfiguredDirs(connections);

      if (connections.length > 0) {
        const firstConn = connections[0];
        if (firstConn.allowed_directories.length > 0) {
          setDirectories(toDirectoryConfigs(firstConn));
        }
      }
    } catch (err) {
      console.error('Failed to load directories:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (workspaceMode) {
      if (initialStorageBasePath) {
        setDirectories([{ path: initialStorageBasePath, allowWrite: false }]);
        setSavedStorageBasePath(initialStorageBasePath);
      } else {
        setDirectories([]);
      }
      if (initialArtifactsDir) {
        setArtifactsDir(initialArtifactsDir);
      }
      if (initialPlaybookStorageConfig) {
        setPlaybookStorageConfig(initialPlaybookStorageConfig);
      }
      setLoading(false);
      if (workspaceId && apiUrl) {
        loadUsedPlaybooks();
      }
    } else {
      loadConfiguredDirectories();
    }
  }, [
    apiUrl,
    initialArtifactsDir,
    initialPlaybookStorageConfig,
    initialStorageBasePath,
    loadConfiguredDirectories,
    loadUsedPlaybooks,
    workspaceId,
    workspaceMode,
  ]);

  const applyDirectoryAction = (result: DirectoryActionResult) => {
    if (result.directories) setDirectories(result.directories);
    if (result.selectedCommonDirs) setSelectedCommonDirs(result.selectedCommonDirs);
    if (result.newDirectory !== undefined) setNewDirectory(result.newDirectory);
    if ('error' in result) setError(result.error ?? null);
  };

  const handleAddDirectory = () =>
    applyDirectoryAction(addDirectorySelection({ directories, newDirectory, workspaceMode }));

  const handleRemoveDirectory = (index: number) =>
    applyDirectoryAction(removeDirectorySelection({ directories, index, selectedCommonDirs }));

  const handleToggleCommonDirectory = (path: string) =>
    applyDirectoryAction(toggleCommonDirectorySelection({ directories, path, selectedCommonDirs, workspaceMode }));

  const handleDirectoryPicker = async () => {
    if ('showDirectoryPicker' in window) {
      try {
        const dirHandle = await (window as any).showDirectoryPicker({
          mode: 'read',
        });

        const dirName = dirHandle.name;

        if (workspaceMode) {
          const pathResult = deriveWorkspaceDirectoryPickerPath({
            currentPath: directories.length > 0 ? directories[0].path : '',
            dirName,
            initialStorageBasePath,
            isWindows,
            selectedPath: (dirHandle as any).path,
          });

          if (pathResult.actualPath) {
            setDirectories([{ path: pathResult.actualPath, allowWrite: false }]);
            setError(null);
            return;
          }

          setSelectedDirName(dirName);
          setPathInputValue(pathResult.defaultPath);
          setShowPathInputDialog(true);
          setError(null);
          return;
        }

        const { defaultPath, promptMessage } = getDirectoryPrompt(dirName);
        const userPath = prompt(promptMessage, defaultPath);

        if (userPath && userPath.trim()) {
          const trimmedPath = userPath.trim();
          const existingPaths = directories.map(d => d.path);
          if (!existingPaths.includes(trimmedPath)) {
            setDirectories([...directories, { path: trimmedPath, allowWrite: false }]);
            setError(null);
          } else {
            setError('Directory already added');
          }
        }
      } catch (err: any) {
        if (err.name !== 'AbortError') {
          console.error('Directory picker error:', err);
          setError('Failed to open directory picker. Please use quick select or manual input.');
        }
      }
    } else {
      fileInputRef.current?.click();
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const firstFile = files[0];
      const webkitPath = (firstFile as any).webkitRelativePath;

      if (webkitPath) {
        const dirName = webkitPath.split('/')[0];

        if (workspaceMode) {
          setSelectedDirName(dirName);
          setPathInputValue(
            deriveWorkspaceFileInputDefaultPath({
              dirName,
              initialStorageBasePath,
              isWindows,
            })
          );
          setShowPathInputDialog(true);
          setError(null);
          return;
        }

        const { defaultPath, promptMessage } = getDirectoryPrompt(dirName);
        const userPath = prompt(promptMessage, defaultPath);

        if (userPath && userPath.trim()) {
          const trimmedPath = userPath.trim();
          const existingPaths = directories.map(d => d.path);
          if (!existingPaths.includes(trimmedPath)) {
            setDirectories([...directories, { path: trimmedPath, allowWrite: false }]);
            setError(null);
          } else {
            setError('Directory already added');
          }
        }
      }
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleSave = async () => {
    if (directories.length === 0) {
      setError('At least one directory must be configured');
      return;
    }

    if (workspaceMode) {
      const path = directories[0]?.path?.trim() || '';
      if (!isAbsoluteStoragePath(path)) {
        setError('Workspace storage path must be an absolute path. Please use full path, e.g., /Users/.../Documents or C:\\Users\\...\\Documents');
        return;
      }
    }

    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      if (workspaceMode && workspaceId && apiUrl) {
        const result = await saveWorkspaceStorageConfig({
          apiUrl,
          artifactsDir,
          directories,
          playbookStorageConfig,
          workspaceId,
        });

        if (!result.ok) {
          setError(result.errorMessage);
          return;
        }

        const responseData = result.data;

        if (responseData.storage_base_path) {
          setSavedStorageBasePath(responseData.storage_base_path);
        }
        if (responseData.artifacts_dir) {
          setArtifactsDir(responseData.artifacts_dir);
        }

        setSuccess(t('storagePathConfigured' as any));
        setTimeout(() => {
          onSuccess();
        }, 1500);
      } else {
        const response = await configureLocalFilesystem(directories);

        if (response.env_update) {
          try {
            await updateHostDocumentsPath(response.env_update.host_path);

            setSuccess(t('configSavedEnvUpdated' as any));
            setRequiresRestart(true);
          } catch (envErr) {
            console.error('Failed to update .env:', envErr);
            setSuccess(
              `${t('configSavedEnvUpdateFailed' as any)}\nHOST_DOCUMENTS_PATH=${response.env_update.host_path}`
            );
            setRequiresRestart(true);
          }
        } else {
          setSuccess(t('configSaved' as any));
        }

        await loadConfiguredDirectories();

        setTimeout(() => {
          onSuccess();
        }, 3000);
      }
    } catch (err) {
      console.error('Failed to save configuration:', err);
      const errorMessage = err instanceof Error ? err.message : 'Configuration failed';
      setError(errorMessage);
      setSuccess(null);
      setRequiresRestart(false);
    } finally {
      setSaving(false);
    }
  };

  const hasSelectedPath = workspaceMode && directories.length > 0 && directories[0]?.path?.trim() !== '';

  const handlePathInputConfirm = () => {
    const trimmedPath = pathInputValue.trim();
    if (!trimmedPath) {
      setError('Please enter a path');
      return;
    }

    if (workspaceMode) {
      if (!isAbsoluteStoragePath(trimmedPath)) {
        setError('Workspace storage path must be an absolute path. Please use full path, e.g., /Users/.../Documents or C:\\Users\\...\\Documents');
        return;
      }
      setDirectories([{ path: trimmedPath, allowWrite: false }]);
      setError(null);
      setShowPathInputDialog(false);
      setSelectedDirName('');
      setPathInputValue('');
    }
  };

  const handlePathInputCancel = () => {
    setShowPathInputDialog(false);
    setSelectedDirName('');
    setPathInputValue('');
    setError(null);
  };

  const handleRestart = async () => {
    setRestarting(true);
    try {
      const response = await restartSystemSettings();
      if (response.success) {
        setSuccess(t('configSaved' as any));
        setRequiresRestart(false);
        setTimeout(() => {
          window.location.reload();
        }, 5000);
      } else {
        setError(response.message || t('restartFailed' as any));
        setRequiresRestart(true);
      }
    } catch (err) {
      console.error('Failed to restart service:', err);
      setError(t('restartFailed' as any));
      setRequiresRestart(true);
    } finally {
      setRestarting(false);
    }
  };

  if (loading) {
    return <div className="p-6 text-center text-gray-500 dark:text-gray-400">Loading...</div>;
  }

  return (
    <>
      {showPathInputDialog && (
        <PathInputDialog
          error={error}
          initialStorageBasePath={initialStorageBasePath}
          isWindows={isWindows}
          pathInputValue={pathInputValue}
          selectedDirName={selectedDirName}
          onCancel={handlePathInputCancel}
          onConfirm={handlePathInputConfirm}
          onPathInputValueChange={setPathInputValue}
        />
      )}

      <div className="relative">
        <WorkspaceDirectoryRequiredOverlay
          error={error}
          hasSelectedPath={hasSelectedPath}
          onBrowseDirectory={handleDirectoryPicker}
          workspaceMode={workspaceMode}
        />

        <LocalFilesystemStatusSection
          error={error}
          onClose={onClose}
          onDismissError={() => setError(null)}
          onDismissSuccess={() => {
            setSuccess(null);
            setRequiresRestart(false);
          }}
          onRestart={handleRestart}
          requiresRestart={requiresRestart}
          restarting={restarting}
          showHeader={showHeader}
          success={success}
          workspaceMode={workspaceMode}
        />

        <div className="space-y-4">
          <DirectorySelectionSection
            actualUsername={actualUsername}
            directories={directories}
            fileInputRef={fileInputRef}
            filteredCommonDirs={filteredCommonDirs}
            handleAddDirectory={handleAddDirectory}
            handleDirectoryPicker={handleDirectoryPicker}
            handleFileInputChange={handleFileInputChange}
            handleRemoveDirectory={handleRemoveDirectory}
            handleToggleCommonDirectory={handleToggleCommonDirectory}
            initialStorageBasePath={initialStorageBasePath}
            isWindows={isWindows}
            newDirectory={newDirectory}
            savedStorageBasePath={savedStorageBasePath}
            selectedCommonDirs={selectedCommonDirs}
            setDirectories={setDirectories}
            setError={setError}
            setNewDirectory={setNewDirectory}
            workspaceMode={workspaceMode}
            workspaceTitle={workspaceTitle}
          />

          <WorkspaceStorageSections
            artifactsDir={artifactsDir}
            directories={directories}
            loadingPlaybooks={loadingPlaybooks}
            playbookStorageConfig={playbookStorageConfig}
            setArtifactsDir={setArtifactsDir}
            setPlaybookStorageConfig={setPlaybookStorageConfig}
            usedPlaybooks={usedPlaybooks}
            workspaceMode={workspaceMode}
          />

          <ConfiguredDirectoriesSection configuredDirs={configuredDirs} />
        </div>

        <LocalFilesystemFooterSection
          directories={directories}
          onClose={onClose}
          onSave={handleSave}
          saving={saving}
          showHeader={showHeader}
        />
      </div>
    </>
  );
}
