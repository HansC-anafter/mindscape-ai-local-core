'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { InlineAlert } from '../InlineAlert';
import { DirectorySelectionSection } from './localFilesystemManager/DirectorySelectionSection';
import { PathInputDialog } from './localFilesystemManager/PathInputDialog';
import {
  extractUsername,
  getCommonDirectories,
  getFilteredCommonDirectories,
} from './localFilesystemManager/pathUtils';
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
  const [playbookStorageConfig, setPlaybookStorageConfig] = useState<Record<string, PlaybookStorageConfig>>(
    initialPlaybookStorageConfig || {}
  );
  const [usedPlaybooks, setUsedPlaybooks] = useState<string[]>([]);
  const [loadingPlaybooks, setLoadingPlaybooks] = useState(false);

  const actualUsername = extractUsername(initialStorageBasePath);
  const filteredCommonDirs = getFilteredCommonDirectories({
    actualUsername,
    commonDirectories,
    isWindows,
    workspaceMode,
  });

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

  const loadUsedPlaybooks = useCallback(async () => {
    if (!workspaceId || apiUrl == null) return;

    setLoadingPlaybooks(true);
    try {
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts`);
      if (response.ok) {
        const data = await response.json();
        const playbooks = new Set<string>();
        if (data.artifacts && Array.isArray(data.artifacts)) {
          data.artifacts.forEach((artifact: any) => {
            if (artifact.playbook_code) {
              playbooks.add(artifact.playbook_code);
            }
          });
        }
        setUsedPlaybooks(Array.from(playbooks).sort());
      }
    } catch (err) {
      console.error('Failed to load used playbooks:', err);
    } finally {
      setLoadingPlaybooks(false);
    }
  }, [apiUrl, workspaceId]);

  const loadConfiguredDirectories = useCallback(async () => {
    try {
      setLoading(true);
      const data = await settingsApi.get<{ connections?: ConfiguredDirectory[] }>(
        '/api/v1/tools/local-filesystem/directories'
      );
      const connections = data.connections || [];
      setConfiguredDirs(connections);

      if (connections.length > 0) {
        const firstConn = connections[0];
        if (firstConn.allowed_directories.length > 0) {
          let dirConfigs: DirectoryConfig[];
          if (firstConn.directory_configs && firstConn.directory_configs.length > 0) {
            dirConfigs = firstConn.directory_configs.map((dc: any) => ({
              path: dc.path,
              allowWrite: dc.allow_write || false
            }));
          } else {
            dirConfigs = firstConn.allowed_directories.map((path: string) => ({
              path,
              allowWrite: firstConn.allow_write || false
            }));
          }
          setDirectories(dirConfigs);
        }
      }
    } catch (err) {
      console.error('Failed to load directories:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleAddDirectory = () => {
    const trimmed = newDirectory.trim();
    if (workspaceMode) {
      if (trimmed) {
        setDirectories([{ path: trimmed, allowWrite: false }]);
        setNewDirectory('');
        setError(null);
      }
    } else {
      const existingPaths = directories.map(d => d.path);
      if (trimmed && !existingPaths.includes(trimmed)) {
        setDirectories([...directories, { path: trimmed, allowWrite: false }]);
        setNewDirectory('');
        setError(null);
      } else if (trimmed && existingPaths.includes(trimmed)) {
        setError('Directory already added');
      }
    }
  };

  const handleRemoveDirectory = (index: number) => {
    const removed = directories[index];
    setDirectories(directories.filter((_, i) => i !== index));
    if (selectedCommonDirs.has(removed.path)) {
      const newSelected = new Set(selectedCommonDirs);
      newSelected.delete(removed.path);
      setSelectedCommonDirs(newSelected);
    }
  };

  const handleToggleCommonDirectory = (path: string) => {
    if (workspaceMode) {
      setDirectories([{ path, allowWrite: false }]);
      const newSelected = new Set([path]);
      setSelectedCommonDirs(newSelected);
    } else {
      const existingPaths = directories.map(d => d.path);
      const newSelected = new Set(selectedCommonDirs);
      if (newSelected.has(path)) {
        newSelected.delete(path);
        setDirectories(directories.filter(d => d.path !== path));
      } else {
        newSelected.add(path);
        if (!existingPaths.includes(path)) {
          setDirectories([...directories, { path, allowWrite: false }]);
        }
      }
      setSelectedCommonDirs(newSelected);
    }
  };

  const handleDirectoryPicker = async () => {
    if ('showDirectoryPicker' in window) {
      try {
        const dirHandle = await (window as any).showDirectoryPicker({
          mode: 'read',
        });

        const dirName = dirHandle.name;

        if (workspaceMode) {
          let actualPath = '';

          if ((dirHandle as any).path) {
            actualPath = (dirHandle as any).path;
          }

          if (!actualPath) {
            const currentPath = directories.length > 0 ? directories[0].path : '';

            if (currentPath && currentPath.trim()) {
              const trimmedPath = currentPath.trim();
              const separator = isWindows ? '\\' : '/';

              if (trimmedPath.endsWith(separator) || trimmedPath.endsWith('/') || trimmedPath.endsWith('\\')) {
                actualPath = `${trimmedPath}${dirName}`;
              } else {
                if (trimmedPath.includes(separator) || trimmedPath.includes('/') || trimmedPath.includes('\\')) {
                  const pathParts = trimmedPath.split(/[/\\]/).filter(p => p);
                  pathParts[pathParts.length - 1] = dirName;
                  actualPath = (isWindows ? 'C:' : '') + separator + pathParts.join(separator);
                } else {
                  actualPath = `${trimmedPath}${separator}${dirName}`;
                }
              }
            } else if (initialStorageBasePath) {
              const basePath = initialStorageBasePath.trim();
              if (basePath) {
                if (basePath.includes('\\')) {
                  const winParts = basePath.split('\\');
                  const parentPath = winParts.slice(0, -1).join('\\');
                  if (parentPath) {
                    actualPath = `${parentPath}\\${dirName}`;
                  }
                } else {
                  const pathParts = basePath.split('/');
                  const parentPath = pathParts.slice(0, -1).join('/') || '/';
                  actualPath = `${parentPath}/${dirName}`;
                }
              }
            }
          }

          if (actualPath) {
            setDirectories([{ path: actualPath, allowWrite: false }]);
            setError(null);
            return;
          }

          let defaultPath = '';
          if (directories.length > 0 && directories[0].path.trim()) {
            const currentPath = directories[0].path.trim();
            const separator = isWindows ? '\\' : '/';
            if (currentPath.endsWith(separator) || currentPath.endsWith('/') || currentPath.endsWith('\\')) {
              defaultPath = `${currentPath}${dirName}`;
            } else {
              defaultPath = `${currentPath}${separator}${dirName}`;
            }
          } else if (initialStorageBasePath) {
            const basePath = initialStorageBasePath.trim();
            if (basePath) {
              if (basePath.includes('\\')) {
                const winParts = basePath.split('\\');
                const parentPath = winParts.slice(0, -1).join('\\');
                if (parentPath) {
                  defaultPath = `${parentPath}\\${dirName}`;
                }
              } else {
                const pathParts = basePath.split('/');
                const parentPath = pathParts.slice(0, -1).join('/') || '/';
                defaultPath = `${parentPath}/${dirName}`;
              }
            }
          }

          if (!defaultPath) {
            defaultPath = isWindows
              ? `C:\\Users\\${dirName}`
              : `/Users/${dirName}`;
          }

          setSelectedDirName(dirName);
          setPathInputValue(defaultPath);
          setShowPathInputDialog(true);
          setError(null);
          return;
        }

        const promptMessage = `Selected directory: "${dirName}"\n\nPlease enter the full directory path:\n(e.g., ~/Documents/${dirName} or C:\\Users\\...\\Documents\\${dirName})`;
        const defaultPath = `~/Documents/${dirName}`;
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
          let defaultPath = '';
          if (initialStorageBasePath) {
            const pathParts = initialStorageBasePath.split('/');
            if (pathParts.length >= 3 && pathParts[0] === '' && pathParts[1] === 'Users') {
              defaultPath = `${pathParts.slice(0, 3).join('/')}/${dirName}`;
            } else if (initialStorageBasePath.includes('\\')) {
              const winParts = initialStorageBasePath.split('\\');
              if (winParts.length >= 3 && winParts[0].match(/^[A-Za-z]:$/) && winParts[1] === 'Users') {
                defaultPath = `${winParts.slice(0, 3).join('\\')}\\${dirName}`;
              }
            }
          }

          if (!defaultPath) {
            defaultPath = isWindows
              ? `C:\\Users\\${dirName}`
              : `/Users/${dirName}`;
          }

          setSelectedDirName(dirName);
          setPathInputValue(defaultPath);
          setShowPathInputDialog(true);
          setError(null);
          return;
        }

        const promptMessage = `Selected directory: "${dirName}"\n\nPlease enter the full directory path:\n(e.g., ~/Documents/${dirName} or C:\\Users\\...\\Documents\\${dirName})`;
        const defaultPath = `~/Documents/${dirName}`;
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
      if (!path.startsWith('/') && !path.match(/^[A-Za-z]:/)) {
        setError('Workspace storage path must be an absolute path. Please use full path, e.g., /Users/.../Documents or C:\\Users\\...\\Documents');
        return;
      }
    }

    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      if (workspaceMode && workspaceId && apiUrl) {
        let storageBasePath = directories[0]?.path?.trim() || '';
        storageBasePath = storageBasePath.replace(/\/+$/, '');

        const artifactsDirValue = artifactsDir.trim() || 'artifacts';
        const requestBody: any = {
          storage_base_path: storageBasePath,
          artifacts_dir: artifactsDirValue,
        };

        const playbookConfigToSave: Record<string, PlaybookStorageConfig> = {};
        Object.keys(playbookStorageConfig).forEach(playbookCode => {
          const config = playbookStorageConfig[playbookCode];
          if (config.base_path && config.base_path.trim()) {
            playbookConfigToSave[playbookCode] = {
              base_path: config.base_path.trim(),
              artifacts_dir: config.artifacts_dir?.trim() || artifactsDirValue,
            };
          }
        });
        if (Object.keys(playbookConfigToSave).length > 0) {
          requestBody.playbook_storage_config = playbookConfigToSave;
        }

        const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(requestBody),
        });

        if (!response.ok) {
          let errorMessage = 'Failed to update workspace';
          try {
            const errorData = await response.json();
            if (errorData.detail) {
              errorMessage = errorData.detail;
            } else if (errorData.message) {
              errorMessage = errorData.message;
            } else if (errorData.error) {
              errorMessage = errorData.error;
            } else {
              errorMessage = JSON.stringify(errorData);
            }
          } catch (e) {
            const responseText = await response.text();
            errorMessage = responseText || `HTTP ${response.status}: ${response.statusText}`;
          }
          setError(errorMessage);
          setSaving(false);
          return;
        }

        const responseData = await response.json();

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
        const response = await settingsApi.post<{
          success: boolean;
          env_update?: {
            host_path: string;
            container_path: string;
            requires_restart: boolean;
          };
          message?: string;
        }>('/api/v1/tools/local-filesystem/configure', {
          connection_id: 'local-fs-default',
          name: 'Local File System',
          allowed_directories: directories.map(d => d.path),
          directory_configs: directories.map(d => ({
            path: d.path,
            allow_write: d.allowWrite
          })),
        });

        if (response.env_update) {
          try {
            await settingsApi.put('/api/v1/system/env', {
              key: 'HOST_DOCUMENTS_PATH',
              value: response.env_update.host_path,
              comment: 'Local filesystem mount path (auto-configured)'
            });

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
      if (!trimmedPath.startsWith('/') && !trimmedPath.match(/^[A-Za-z]:/)) {
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
        {workspaceMode && !hasSelectedPath && (
          <div className="absolute inset-0 bg-white dark:bg-gray-800 bg-opacity-95 dark:bg-opacity-95 rounded-lg z-10 flex flex-col items-center justify-center p-8">
            <div className="text-center max-w-md w-full">
              {error && (
                <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                  <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
                </div>
              )}
              <div className="mb-6">
                <h3 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">
                  Select Project Root Directory
                </h3>
                <p className="text-gray-600 dark:text-gray-400 mb-6">
                  Please use the button below to select your project root directory. The system will automatically fill in the complete path.
                </p>
              </div>
              <button
                type="button"
                onClick={handleDirectoryPicker}
                className="px-8 py-4 bg-accent dark:bg-blue-700 hover:bg-accent/90 dark:hover:bg-blue-600 text-white rounded-lg text-lg font-medium flex items-center space-x-3 shadow-lg transition-colors mx-auto"
                title={typeof window !== 'undefined' && 'showDirectoryPicker' in window
                  ? 'Open system directory picker (Chrome/Edge)'
                  : 'Not available in this browser. Use quick select or manual input.'}
              >
                <span>Browse Directory {typeof window !== 'undefined' && 'showDirectoryPicker' in window ? '(Chrome/Edge)' : '(Not Available)'}</span>
              </button>
              <p className="mt-4 text-xs text-gray-500 dark:text-gray-400">
                {typeof window !== 'undefined' && 'showDirectoryPicker' in window
                  ? 'Click this button to open the system directory picker and select your project root directory'
                  : 'Directory picker is not available in this browser. Please use manual input below'}
              </p>
            </div>
          </div>
        )}

        {showHeader && (
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">{workspaceMode ? t('configureWorkspaceStoragePath' as any) : t('localFileSystemConfig' as any)}</h2>
            {onClose && (
              <button onClick={onClose} className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300">
                ×
              </button>
            )}
          </div>
        )}

        {error && (
          <InlineAlert
            type="error"
            message={error}
            onDismiss={() => setError(null)}
            className="mb-4"
          />
        )}

        {success && (
          <div className="mb-4">
            <InlineAlert
              type="success"
              message={success}
              onDismiss={() => {
                setSuccess(null);
                setRequiresRestart(false);
              }}
              className="mb-2"
            />
            {requiresRestart && (
              <div className="mt-3 p-3 bg-accent-10 dark:bg-blue-900/20 border border-accent/30 dark:border-blue-800 rounded-lg">
                <p className="text-sm text-accent dark:text-blue-300 mb-2">
                  {t('restartRequired' as any)}
                </p>
                <button
                  type="button"
                  onClick={async () => {
                    setRestarting(true);
                    try {
                      const response = await settingsApi.post<{ success: boolean; message?: string }>('/api/v1/system-settings/restart');
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
                  }}
                  disabled={restarting}
                  className="px-4 py-2 bg-accent hover:bg-accent/90 disabled:bg-gray-400 text-white rounded-md text-sm font-medium transition-colors"
                >
                  {restarting ? t('restarting' as any) : t('restartService' as any)}
                </button>
                <p className="text-xs text-accent dark:text-blue-400 mt-2">
                  {t('orManuallyRun' as any)}
                </p>
              </div>
            )}
          </div>
        )}

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

          {workspaceMode && (
            <div className="border-t dark:border-gray-700 pt-4">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {t('artifactsDirectory' as any)}
              </label>
              <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">
                {t('artifactsDirectoryDescription' as any)}
                <br />
                {t('artifactsDirectoryDefault' as any)}: <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">artifacts</code>
              </p>
              <input
                type="text"
                value={artifactsDir}
                onChange={(e) => setArtifactsDir(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-accent/50 dark:focus:ring-blue-400 focus:border-transparent"
                placeholder="artifacts"
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                {t('artifactsWillBeStoredAt' as any)} <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">{directories[0]?.path || '...'}/{artifactsDir || 'artifacts'}</code>
              </p>
            </div>
          )}

          {workspaceMode && (
            <div className="border-t dark:border-gray-700 pt-4">
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('playbookStorageConfiguration' as any)}
                </label>
                {loadingPlaybooks && (
                  <span className="text-xs text-gray-500 dark:text-gray-400">{t('loadingPlaybooks' as any)}</span>
                )}
              </div>
              <p className="text-xs text-gray-600 dark:text-gray-400 mb-3">
                {t('playbookStorageConfigurationDescription' as any)}
              </p>

              {usedPlaybooks.length > 0 && (
                <div className="space-y-3 mb-4">
                  {usedPlaybooks.map((playbookCode) => {
                    const config = playbookStorageConfig[playbookCode] || {};
                    const useCustom = !!(config.base_path && config.base_path.trim());

                    return (
                      <div key={playbookCode} className="p-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-200 dark:border-gray-700">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={useCustom}
                              onChange={(e) => {
                                const newConfig = { ...playbookStorageConfig };
                                if (e.target.checked) {
                                  newConfig[playbookCode] = {
                                    base_path: directories[0]?.path || '',
                                    artifacts_dir: artifactsDir,
                                  };
                                } else {
                                  delete newConfig[playbookCode];
                                }
                                setPlaybookStorageConfig(newConfig);
                              }}
                              className="rounded"
                            />
                            <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{playbookCode}</span>
                          </div>
                          {useCustom && (
                            <button
                              onClick={() => {
                                const newConfig = { ...playbookStorageConfig };
                                delete newConfig[playbookCode];
                                setPlaybookStorageConfig(newConfig);
                              }}
                              className="text-xs text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300"
                            >
                              {t('remove' as any)}
                            </button>
                          )}
                        </div>
                        {useCustom && (
                          <div className="space-y-2 mt-2">
                            <div>
                              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                                {t('basePath' as any)}
                              </label>
                              <input
                                type="text"
                                value={config.base_path || ''}
                                onChange={(e) => {
                                  const newConfig = { ...playbookStorageConfig };
                                  newConfig[playbookCode] = {
                                    ...config,
                                    base_path: e.target.value,
                                  };
                                  setPlaybookStorageConfig(newConfig);
                                }}
                                className="w-full px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-accent/50 dark:focus:ring-blue-400"
                                placeholder={directories[0]?.path || 'Enter base path'}
                              />
                            </div>
                            <div>
                              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                                {t('artifactsDirectory' as any)}
                              </label>
                              <input
                                type="text"
                                value={config.artifacts_dir || artifactsDir}
                                onChange={(e) => {
                                  const newConfig = { ...playbookStorageConfig };
                                  newConfig[playbookCode] = {
                                    ...config,
                                    artifacts_dir: e.target.value,
                                  };
                                  setPlaybookStorageConfig(newConfig);
                                }}
                                className="w-full px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-accent/50 dark:focus:ring-blue-400"
                                placeholder={artifactsDir || 'artifacts'}
                              />
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {usedPlaybooks.length === 0 && !loadingPlaybooks && (
                <p className="text-xs text-gray-500 dark:text-gray-400 italic">
                  {t('noPlaybooksUsedYet' as any)}
                </p>
              )}
            </div>
          )}

          {configuredDirs.length > 0 && (
            <div className="border-t dark:border-gray-700 pt-4">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">{t('configuredDirectories' as any)}</h3>
              <div className="space-y-2">
                {configuredDirs.map((conn, idx) => (
                  <div key={idx} className="p-3 bg-gray-50 dark:bg-gray-800/50 rounded">
                    <div className="flex items-center justify-between mb-2">
                      <div className="font-medium text-sm text-gray-900 dark:text-gray-100">{conn.name}</div>
                      {conn.enabled !== undefined && (
                        <span className={`text-xs px-2 py-0.5 rounded ${conn.enabled
                            ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                            : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                          }`}>
                          {conn.enabled ? t('enabled' as any) : t('disabled' as any)}
                        </span>
                      )}
                    </div>
                    <div className="space-y-1.5">
                      {conn.allowed_directories.map((dir, dirIdx) => {
                        const isEnabled = conn.enabled !== false;
                        return (
                          <div key={dirIdx} className="flex items-center space-x-2">
                            {isEnabled && (
                              <span className="text-green-600 dark:text-green-400 text-sm font-semibold" title={t('enabled' as any)}>✓</span>
                            )}
                            {!isEnabled && (
                              <span className="text-gray-400 dark:text-gray-500 text-sm" title={t('disabled' as any)}>✗</span>
                            )}
                            <span className="text-xs text-gray-600 dark:text-gray-400 flex-1 font-mono">{dir}</span>
                          </div>
                        );
                      })}
                    </div>
                    {conn.allow_write && (
                      <span className="text-xs text-orange-600 dark:text-orange-400 mt-2 block">
                        {t('writeEnabled' as any)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {showHeader && (
          <div className="flex justify-end space-x-3 pt-4 border-t dark:border-gray-700 mt-4">
            {onClose && (
              <button
                onClick={onClose}
                className="px-4 py-2 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800"
              >
                {t('cancel' as any)}
              </button>
            )}
            <button
              onClick={handleSave}
              disabled={saving || directories.length === 0}
              className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? t('saving' as any) : t('save' as any)}
            </button>
          </div>
        )}
      </div>
    </>
  );
}
