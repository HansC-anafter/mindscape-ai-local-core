'use client';

import React, { useState, useEffect, useRef } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { InlineAlert } from '../InlineAlert';

interface PlaybookStorageConfig {
  base_path?: string;
  artifacts_dir?: string;
}

interface LocalFilesystemManagerProps {
  onClose: () => void;
  onSuccess: () => void;
  workspaceId?: string;
  apiUrl?: string;
  workspaceTitle?: string;
  workspaceMode?: boolean;
  initialStorageBasePath?: string;
  initialArtifactsDir?: string;
  initialPlaybookStorageConfig?: Record<string, PlaybookStorageConfig>;
}

interface ConfiguredDirectory {
  name: string;
  allowed_directories: string[];
  allow_write: boolean;
}

// Detect platform for common directories
const getCommonDirectories = () => {
  // Note: This runs at module load time, so we need to check at runtime in component
  // For now, provide both formats and let user choose
  const commonDirs = [
    { label: 'Documents', path: '~/Documents', icon: '', platform: 'all' },
    { label: 'Downloads', path: '~/Downloads', icon: '', platform: 'all' },
    { label: 'Desktop', path: '~/Desktop', icon: '', platform: 'all' },
    { label: 'Pictures', path: '~/Pictures', icon: '', platform: 'all' },
    { label: 'Music', path: '~/Music', icon: '', platform: 'all' },
    { label: 'Videos', path: '~/Videos', icon: '', platform: 'all' },
    { label: 'Documents (Win)', path: '%USERPROFILE%\\Documents', icon: '', platform: 'windows' },
    { label: 'Downloads (Win)', path: '%USERPROFILE%\\Downloads', icon: '', platform: 'windows' },
    { label: 'Data Directory', path: './data', icon: '', platform: 'all' },
    { label: 'Data Documents', path: './data/documents', icon: '', platform: 'all' },
  ];

  return commonDirs;
};

// Helper component for empty path input with workspace name button
function EmptyPathInputWithWorkspaceName({
  workspaceTitle,
  isWindows,
  initialStorageBasePath,
  onPathChange,
  currentPath
}: {
  workspaceTitle?: string;
  isWindows: boolean;
  initialStorageBasePath?: string;
  onPathChange: (path: string) => void;
  currentPath?: string;
}) {
  const [inputValue, setInputValue] = useState(currentPath || '');

  // Sync with parent's currentPath when it changes (but don't override if user is typing)
  useEffect(() => {
    // Only sync if currentPath is different from inputValue and is not empty
    // This prevents overwriting user input while typing
    if (currentPath !== undefined && currentPath !== inputValue && currentPath.trim() !== '') {
      setInputValue(currentPath);
    }
  }, [currentPath]);

  const sanitizeWorkspaceTitle = (title: string): string => {
    // Remove only dangerous path characters, keep Unicode characters (including Chinese)
    // Remove: / \ : * ? " < > | and other control characters
    return title
      .replace(/[\/\\:*?"<>|\x00-\x1F\x7F]/g, '')  // Remove path separators and control chars
      .trim()
      .replace(/[-\s]+/g, '-');
  };

  const appendWorkspaceTitle = (currentPath: string): string => {
    if (!workspaceTitle) return currentPath;
    const sanitized = sanitizeWorkspaceTitle(workspaceTitle);
    if (!sanitized) return currentPath;

    const trimmedPath = currentPath.trim();
    if (!trimmedPath) return sanitized;

    // Check if workspace title is already at the end
    const separator = isWindows ? '\\' : '/';
    if (trimmedPath.endsWith(separator + sanitized) ||
        trimmedPath.endsWith('/' + sanitized) ||
        trimmedPath.endsWith('\\' + sanitized)) {
      return trimmedPath; // Already has workspace title
    }

    // Append workspace title
    const pathEndsWithSeparator = trimmedPath.endsWith(separator) ||
                                   trimmedPath.endsWith('/') ||
                                   trimmedPath.endsWith('\\');
    return pathEndsWithSeparator
      ? `${trimmedPath}${sanitized}`
      : `${trimmedPath}${separator}${sanitized}`;
  };

  const handleAppendWorkspaceName = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    console.log('Button clicked!', { inputValue, workspaceTitle, hasWorkspaceTitle: !!workspaceTitle });
    const newPath = appendWorkspaceTitle(inputValue);
    console.log('handleAppendWorkspaceName called:', { inputValue, newPath, workspaceTitle });
    // Update local state first
    setInputValue(newPath);
    // Then update parent state - this will trigger a re-render
    // but the newPath will be preserved because we set it above
    onPathChange(newPath);
  };

  return (
    <div className="flex items-center space-x-2 p-2 bg-gray-50 rounded-md">
      <input
        type="text"
        value={inputValue}
        onChange={(e) => {
          const value = e.target.value;
          setInputValue(value);
          onPathChange(value);
        }}
        className="flex-1 px-2 py-1 text-sm text-gray-700 font-mono border border-gray-300 rounded bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        placeholder={initialStorageBasePath || (isWindows ? "C:\\Users\\...\\Documents\\..." : "/Users/.../Documents/...")}
      />
      {workspaceTitle ? (
        <button
          type="button"
          onClick={(e) => {
            console.log('Button onClick triggered!', { workspaceTitle, inputValue });
            e.preventDefault();
            e.stopPropagation();
            handleAppendWorkspaceName(e);
          }}
          className="px-3 py-1 text-xs bg-green-100 text-green-700 border border-green-300 rounded hover:bg-green-200 transition-colors whitespace-nowrap"
          title={`附加工作區名稱: ${workspaceTitle}`}
        >
          + 工作區名稱
        </button>
      ) : (
        <div className="text-xs text-red-500">No workspaceTitle!</div>
      )}
    </div>
  );
}

export function LocalFilesystemManager({
  onClose,
  onSuccess,
  workspaceId,
  apiUrl,
  workspaceMode = false,
  workspaceTitle,
  initialStorageBasePath,
  initialArtifactsDir,
  initialPlaybookStorageConfig,
}: LocalFilesystemManagerProps) {
  const [saving, setSaving] = useState(false);
  const [directories, setDirectories] = useState<string[]>([]);
  const [newDirectory, setNewDirectory] = useState('');
  const [allowWrite, setAllowWrite] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [configuredDirs, setConfiguredDirs] = useState<ConfiguredDirectory[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCommonDirs, setSelectedCommonDirs] = useState<Set<string>>(new Set());
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [commonDirectories] = useState(() => getCommonDirectories());
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

  // Extract actual username from initialStorageBasePath if available
  const extractUsername = (path?: string): string | null => {
    if (!path) return null;

    if (path.includes('\\')) {
      // Windows path: C:\Users\username\...
      const winParts = path.split('\\');
      if (winParts.length >= 3 && winParts[0].match(/^[A-Za-z]:$/) && winParts[1] === 'Users') {
        return winParts[2];
      }
    } else {
      // macOS/Linux path: /Users/username/...
      const pathParts = path.split('/');
      if (pathParts.length >= 3 && pathParts[0] === '' && pathParts[1] === 'Users') {
        return pathParts[2];
      }
    }
    return null;
  };

  const actualUsername = extractUsername(initialStorageBasePath);

  // Filter common directories based on platform
  // Show all directories that are either platform-agnostic or match current platform
  let filteredCommonDirs = commonDirectories.filter(dir =>
    dir.platform === 'all' || (dir.platform === 'windows' && isWindows)
  );

  if (workspaceMode) {
    if (actualUsername) {
      const absolutePathOptions = isWindows ? [
        { label: 'Documents', path: `C:\\Users\\${actualUsername}\\Documents`, icon: '', platform: 'windows' },
        { label: 'Downloads', path: `C:\\Users\\${actualUsername}\\Downloads`, icon: '', platform: 'windows' },
        { label: 'Desktop', path: `C:\\Users\\${actualUsername}\\Desktop`, icon: '', platform: 'windows' },
      ] : [
        { label: 'Documents', path: `/Users/${actualUsername}/Documents`, icon: '', platform: 'all' },
        { label: 'Downloads', path: `/Users/${actualUsername}/Downloads`, icon: '', platform: 'all' },
        { label: 'Desktop', path: `/Users/${actualUsername}/Desktop`, icon: '', platform: 'all' },
        { label: 'Home', path: `/Users/${actualUsername}`, icon: '', platform: 'all' },
      ];
      filteredCommonDirs = absolutePathOptions;
    } else {
      filteredCommonDirs = [];
    }
  }

  useEffect(() => {
    if (workspaceMode) {
      // Always set directories, even if initialStorageBasePath is empty/undefined
      // This ensures the input field is always visible
      if (initialStorageBasePath) {
        setDirectories([initialStorageBasePath]);
      } else {
        // If no path is set, initialize with empty array to show input field
        setDirectories([]);
      }
      if (initialArtifactsDir) {
        setArtifactsDir(initialArtifactsDir);
      }
      if (initialPlaybookStorageConfig) {
        setPlaybookStorageConfig(initialPlaybookStorageConfig);
      }
      setLoading(false);
      // Load used playbooks from artifacts
      if (workspaceId && apiUrl) {
        loadUsedPlaybooks();
      }
    } else {
      loadConfiguredDirectories();
    }
  }, [workspaceMode, initialStorageBasePath, initialArtifactsDir, initialPlaybookStorageConfig, workspaceId, apiUrl]);

  const loadUsedPlaybooks = async () => {
    if (!workspaceId || !apiUrl) return;

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
  };

  const loadConfiguredDirectories = async () => {
    try {
      setLoading(true);
      const data = await settingsApi.get<{ connections?: ConfiguredDirectory[] }>(
        '/api/tools/local-filesystem/directories'
      );
      setConfiguredDirs(data.connections || []);
    } catch (err) {
      console.error('Failed to load directories:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleAddDirectory = () => {
    const trimmed = newDirectory.trim();
    if (workspaceMode) {
      if (trimmed) {
        setDirectories([trimmed]);
        setNewDirectory('');
        setError(null);
      }
    } else {
      if (trimmed && !directories.includes(trimmed)) {
        setDirectories([...directories, trimmed]);
        setNewDirectory('');
        setError(null);
      } else if (trimmed && directories.includes(trimmed)) {
        setError('Directory already added');
      }
    }
  };

  const handleRemoveDirectory = (index: number) => {
    const removed = directories[index];
    setDirectories(directories.filter((_, i) => i !== index));
    // Also remove from selected common dirs if it was a common dir
    if (selectedCommonDirs.has(removed)) {
      const newSelected = new Set(selectedCommonDirs);
      newSelected.delete(removed);
      setSelectedCommonDirs(newSelected);
    }
  };

  const handleToggleCommonDirectory = (path: string) => {
    if (workspaceMode) {
      setDirectories([path]);
      const newSelected = new Set([path]);
      setSelectedCommonDirs(newSelected);
    } else {
      const newSelected = new Set(selectedCommonDirs);
      if (newSelected.has(path)) {
        newSelected.delete(path);
        setDirectories(directories.filter(d => d !== path));
      } else {
        newSelected.add(path);
        if (!directories.includes(path)) {
          setDirectories([...directories, path]);
        }
      }
      setSelectedCommonDirs(newSelected);
    }
  };

  const handleDirectoryPicker = async () => {
    // Try File System Access API first (Chrome/Edge 86+, requires HTTPS)
    if ('showDirectoryPicker' in window) {
      try {
        const dirHandle = await (window as any).showDirectoryPicker({
          mode: 'read',
        });

        // Get directory name
        const dirName = dirHandle.name;

        if (workspaceMode) {
          let actualPath = '';

          // Try to get path from dirHandle.path (if available)
          if ((dirHandle as any).path) {
            actualPath = (dirHandle as any).path;
          }

          // If path is not available, try to construct from current input or initial path
          if (!actualPath) {
            // First, try to use current directories value (user's current input)
            const currentPath = directories.length > 0 ? directories[0] : '';

            if (currentPath && currentPath.trim()) {
              // User has a path in input, try to get parent and append selected directory
              const trimmedPath = currentPath.trim();
              const separator = isWindows ? '\\' : '/';

              if (trimmedPath.endsWith(separator) || trimmedPath.endsWith('/') || trimmedPath.endsWith('\\')) {
                actualPath = `${trimmedPath}${dirName}`;
              } else {
                // Get parent directory and append selected directory
                if (trimmedPath.includes(separator) || trimmedPath.includes('/') || trimmedPath.includes('\\')) {
                  const pathParts = trimmedPath.split(/[/\\]/).filter(p => p);
                  pathParts[pathParts.length - 1] = dirName;
                  actualPath = (isWindows ? 'C:' : '') + separator + pathParts.join(separator);
                } else {
                  actualPath = `${trimmedPath}${separator}${dirName}`;
                }
              }
            } else if (initialStorageBasePath) {
              // Fallback to initial path
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

          // If we have a path, update directories directly
          if (actualPath) {
            setDirectories([actualPath]);
            setError(null);
            return;
          }

          // If still no path, show dialog for user to confirm/enter path
          let defaultPath = '';
          if (directories.length > 0 && directories[0].trim()) {
            // Use current input as base
            const currentPath = directories[0].trim();
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

        // Non-workspace mode, use prompt
        const promptMessage = `Selected directory: "${dirName}"\n\nPlease enter the full directory path:\n(e.g., ~/Documents/${dirName} or C:\\Users\\...\\Documents\\${dirName})`;
        const defaultPath = `~/Documents/${dirName}`;
        const userPath = prompt(promptMessage, defaultPath);

        if (userPath && userPath.trim()) {
          const trimmedPath = userPath.trim();
          if (!directories.includes(trimmedPath)) {
            setDirectories([...directories, trimmedPath]);
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
      // Fallback: Use file input with webkitdirectory (Chrome/Edge, but limited path access)
      fileInputRef.current?.click();
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      // Get the directory path from the first file
      const firstFile = files[0];
      const webkitPath = (firstFile as any).webkitRelativePath;

      if (webkitPath) {
        // Extract directory name from webkitRelativePath
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

        // Non-workspace mode, use prompt
        const promptMessage = `Selected directory: "${dirName}"\n\nPlease enter the full directory path:\n(e.g., ~/Documents/${dirName} or C:\\Users\\...\\Documents\\${dirName})`;
        const defaultPath = `~/Documents/${dirName}`;
        const userPath = prompt(promptMessage, defaultPath);

        if (userPath && userPath.trim()) {
          const trimmedPath = userPath.trim();
          if (!directories.includes(trimmedPath)) {
            setDirectories([...directories, trimmedPath]);
            setError(null);
          } else {
            setError('Directory already added');
          }
        }
      }
    }
    // Reset input
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
      const path = directories[0].trim();
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
        let storageBasePath = directories[0].trim();
        storageBasePath = storageBasePath.replace(/\/+$/, '');
        const artifactsDirValue = artifactsDir.trim() || 'artifacts';
        const requestBody: any = {
          storage_base_path: storageBasePath,
          artifacts_dir: artifactsDirValue,
        };

        // Include playbook_storage_config if any playbook has custom config
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

        console.log('Saving workspace storage path:', requestBody);

        const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(requestBody),
        });

        if (!response.ok) {
          let errorMessage = 'Failed to update workspace';
          let errorData = null;
          try {
            errorData = await response.json();
            console.error('Workspace update error:', errorData);
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
            console.error('Failed to parse error response:', e);
            const responseText = await response.text();
            errorMessage = responseText || `HTTP ${response.status}: ${response.statusText}`;
          }
          setError(errorMessage);
          setSaving(false);
          return;
        }

        setSuccess(t('configSaved'));
        setTimeout(() => {
          onSuccess();
        }, 1500);
      } else {
        await settingsApi.post('/api/tools/local-filesystem/configure', {
          connection_id: 'local-fs-default',
          name: 'Local File System',
          allowed_directories: directories,
          allow_write: allowWrite,
        });

        setSuccess(t('configSaved'));
        await loadConfiguredDirectories();
        setTimeout(() => {
          onSuccess();
        }, 1500);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Configuration failed';
      setError(errorMessage);
    } finally {
      setSaving(false);
    }
  };
  const hasSelectedPath = workspaceMode && directories.length > 0 && directories[0].trim() !== '';

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
      setDirectories([trimmedPath]);
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

  return (
    <>
      {/* Path Input Dialog */}
      {showPathInputDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-[60]">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-lg w-full mx-4">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">
              Enter Full Path
            </h3>
            <div className="mb-4">
              <p className="text-sm text-gray-600 mb-2">
                Selected directory: <span className="font-medium">"{selectedDirName}"</span>
              </p>
              <p className="text-xs text-gray-500 mb-3">
                Please enter the full absolute path
              </p>
              <input
                type="text"
                value={pathInputValue}
                onChange={(e) => setPathInputValue(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handlePathInputConfirm()}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder={initialStorageBasePath || (isWindows ? "C:\\Users\\...\\Documents\\..." : "/Users/.../Documents/...")}
                autoFocus
              />
              <p className="mt-2 text-xs text-gray-500">
                Example: {isWindows
                  ? `C:\\Users\\...\\Documents\\${selectedDirName}`
                  : `/Users/.../Documents/${selectedDirName}`}
              </p>
            </div>
            {error && (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-700">{error}</p>
              </div>
            )}
            <div className="flex justify-end space-x-3">
              <button
                onClick={handlePathInputCancel}
                className="px-4 py-2 text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50"
              >
                {t('cancel')}
              </button>
              <button
                onClick={handlePathInputConfirm}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto relative">
        {/* Overlay for workspace mode when no path selected */}
        {workspaceMode && !hasSelectedPath && (
          <div className="absolute inset-0 bg-white bg-opacity-95 rounded-lg z-10 flex flex-col items-center justify-center p-8">
            <div className="text-center max-w-md w-full">
              {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                  <p className="text-sm text-red-700">{error}</p>
                </div>
              )}
              <div className="mb-6">
                <h3 className="text-2xl font-bold text-gray-900 mb-2">
                  Select Project Root Directory
                </h3>
                <p className="text-gray-600 mb-6">
                  Please use the button below to select your project root directory. The system will automatically fill in the complete path.
                </p>
              </div>
              <button
                type="button"
                onClick={handleDirectoryPicker}
                className="px-8 py-4 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-lg font-medium flex items-center space-x-3 shadow-lg transition-colors mx-auto"
                title={typeof window !== 'undefined' && 'showDirectoryPicker' in window
                  ? 'Open system directory picker (Chrome/Edge)'
                  : 'Not available in this browser. Use quick select or manual input.'}
              >
                <span>Browse Directory {typeof window !== 'undefined' && 'showDirectoryPicker' in window ? '(Chrome/Edge)' : '(Not Available)'}</span>
              </button>
              <p className="mt-4 text-xs text-gray-500">
                {typeof window !== 'undefined' && 'showDirectoryPicker' in window
                  ? 'Click this button to open the system directory picker and select your project root directory'
                  : 'Directory picker is not available in this browser. Please use manual input below'}
              </p>
            </div>
          </div>
        )}

        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-gray-900">{workspaceMode ? "Configure Workspace Storage Path" : t('localFileSystemConfig')}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            ×
          </button>
        </div>

        {error && (
          <InlineAlert
            type="error"
            message={error}
            onDismiss={() => setError(null)}
            className="mb-4"
          />
        )}

        {success && (
          <InlineAlert
            type="success"
            message={success}
            onDismiss={() => setSuccess(null)}
            className="mb-4"
          />
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              {workspaceMode ? "Workspace Storage Path" : t('allowedDirectories')}
            </label>
            {workspaceMode && (
              <p className="text-xs text-gray-600 mb-2">
                Set the file storage path for the Workspace. All Playbook artifacts will be stored under this path.
                <br />
                <span className="text-orange-600 font-medium">Please use absolute path (e.g., {initialStorageBasePath || (isWindows ? 'C:\\Users\\...\\Documents' : '/Users/.../Documents')}).</span>
              </p>
            )}

            {/* Directory Picker Button (for browsers that support it) - Show first in workspace mode */}
            <div className="mb-4">
              {workspaceMode && (
                <div className="mb-3 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                  <p className="text-sm font-medium text-blue-900 mb-2">
                    Please use the button below to select project root directory
                  </p>
                  <p className="text-xs text-blue-700">
                    Click the "Browse Directory" button to select your project root directory. The system will automatically fill in the complete path.
                  </p>
                </div>
              )}
              <button
                type="button"
                onClick={handleDirectoryPicker}
                className={`px-6 py-3 ${workspaceMode ? 'bg-blue-600 hover:bg-blue-700 text-lg font-medium' : 'px-4 py-2 bg-blue-600 hover:bg-blue-700 text-sm'} text-white rounded-md flex items-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-md`}
                title={typeof window !== 'undefined' && 'showDirectoryPicker' in window
                  ? 'Open system directory picker (Chrome/Edge)'
                  : 'Not available in this browser. Use quick select or manual input.'}
              >
                <span>Browse Directory {typeof window !== 'undefined' && 'showDirectoryPicker' in window ? '(Chrome/Edge)' : '(Not Available)'}</span>
              </button>
              <p className="mt-1 text-xs text-gray-500">
                {workspaceMode ? (
                  'Click this button to open the system directory picker and select your project root directory. Please confirm the path is correct after selection.'
                ) : (
                  typeof window !== 'undefined' && 'showDirectoryPicker' in window
                    ? 'Opens system directory picker. You may need to enter the full path after selection.'
                    : 'Directory picker not available in this browser. Use quick select buttons above or manual input below.'
                )}
              </p>
              <input
                ref={fileInputRef}
                type="file"
                {...({ webkitdirectory: '' } as any)}
                {...({ directory: '' } as any)}
                multiple
                style={{ display: 'none' }}
                onChange={handleFileInputChange}
              />
            </div>

            {/* Common Directories Quick Selection - Show after directory picker in workspace mode */}
            {workspaceMode && (
              <div className="mb-2">
                <p className="text-xs text-gray-500 font-medium">Or use quick select:</p>
              </div>
            )}
            <div className="mb-4">
              <p className="text-xs text-gray-600 mb-2">
                {workspaceMode ? (
                  <>
                    Quick Select Workspace Storage Path:
                    {!actualUsername && (
                      <>
                        <br />
                      </>
                    )}
                  </>
                ) : (
                  `Quick Select Common Directories (${isWindows ? 'Windows' : 'Mac/Linux'}):`
                )}
              </p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {filteredCommonDirs.map((commonDir) => {
                    const isSelected = selectedCommonDirs.has(commonDir.path) || directories.includes(commonDir.path);
                    return (
                      <button
                        key={commonDir.path}
                        type="button"
                        onClick={() => handleToggleCommonDirectory(commonDir.path)}
                        className={`
                          flex items-center space-x-2 px-3 py-2 rounded-md border text-sm
                          transition-colors
                          ${isSelected
                            ? 'bg-purple-100 border-purple-500 text-purple-700'
                            : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
                          }
                        `}
                      >
                        <span className="truncate">{commonDir.label}</span>
                        {isSelected && <span className="text-purple-600">✓</span>}
                      </button>
                    );
                  })}
                </div>
              </div>

            {!workspaceMode && (
              <div className="mb-4">
                <p className="text-xs text-gray-600 mb-2">Or Enter Custom Path:</p>
                <div className="flex space-x-2">
                  <input
                    type="text"
                    value={newDirectory}
                    onChange={(e) => setNewDirectory(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && handleAddDirectory()}
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm"
                    placeholder={isWindows
                      ? "e.g., C:\\Users\\...\\Documents or .\\data"
                      : "e.g., ~/Documents or ./data/documents"}
                  />
                  <button
                    onClick={handleAddDirectory}
                    disabled={!newDirectory.trim()}
                    className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                  >
                    {t('add')}
                  </button>
                </div>
              </div>
            )}

            {/* Selected Directories List */}
            {(directories.length > 0 || workspaceMode) && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-gray-700">{workspaceMode ? "Workspace Storage Path:" : "Selected Directories:"}</p>
                {workspaceMode && directories.length === 0 ? (
                  // Show input field even when directories is empty in workspace mode
                  <EmptyPathInputWithWorkspaceName
                    workspaceTitle={workspaceTitle}
                    isWindows={isWindows}
                    initialStorageBasePath={initialStorageBasePath}
                    currentPath=""
                    onPathChange={(path) => {
                      const trimmedPath = path.trim();
                      if (trimmedPath) {
                        setDirectories([trimmedPath]);
                      } else {
                        setDirectories([]);
                      }
                      setError(null);
                    }}
                  />
                ) : (
                  directories.map((dir, index) => {
                    // Helper function to sanitize workspace title for path
                    // Remove only dangerous path characters, keep Unicode characters (including Chinese)
                    const sanitizeWorkspaceTitle = (title: string): string => {
                      return title
                        .replace(/[\/\\:*?"<>|\x00-\x1F\x7F]/g, '')  // Remove path separators and control chars
                        .trim()
                        .replace(/[-\s]+/g, '-');
                    };

                    // Helper function to append workspace title to path
                    const appendWorkspaceTitle = (currentPath: string): string => {
                      if (!workspaceTitle) return currentPath;
                      const sanitized = sanitizeWorkspaceTitle(workspaceTitle);
                      if (!sanitized) return currentPath;

                      const trimmedPath = currentPath.trim();
                      if (!trimmedPath) return sanitized;

                      // Check if workspace title is already at the end
                      const separator = isWindows ? '\\' : '/';
                      if (trimmedPath.endsWith(separator + sanitized) || trimmedPath.endsWith('/' + sanitized) || trimmedPath.endsWith('\\' + sanitized)) {
                        return trimmedPath; // Already has workspace title
                      }

                      // Append workspace title
                      const pathEndsWithSeparator = trimmedPath.endsWith(separator) || trimmedPath.endsWith('/') || trimmedPath.endsWith('\\');
                      return pathEndsWithSeparator
                        ? `${trimmedPath}${sanitized}`
                        : `${trimmedPath}${separator}${sanitized}`;
                    };

                    return (
                      <div key={index} className="flex items-center space-x-2 p-2 bg-gray-50 rounded-md">
                        {workspaceMode ? (
                          <>
                            <input
                              type="text"
                              value={dir}
                              onChange={(e) => {
                                const newDirs = [...directories];
                                newDirs[index] = e.target.value;
                                setDirectories(newDirs);
                                setError(null);
                              }}
                              className="flex-1 px-2 py-1 text-sm text-gray-700 font-mono border border-gray-300 rounded bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                              placeholder={initialStorageBasePath || (isWindows ? "C:\\Users\\...\\Documents\\..." : "/Users/.../Documents/...")}
                            />
                            {workspaceTitle ? (
                              <button
                                type="button"
                                onClick={(e) => {
                                  console.log('Button clicked in directories.map!', { dir, workspaceTitle, index });
                                  e.preventDefault();
                                  e.stopPropagation();
                                  const newDirs = [...directories];
                                  const newPath = appendWorkspaceTitle(dir);
                                  console.log('Appending workspace title:', { dir, newPath, workspaceTitle });
                                  newDirs[index] = newPath;
                                  setDirectories(newDirs);
                                  setError(null);
                                }}
                                className="px-3 py-1 text-xs bg-green-100 text-green-700 border border-green-300 rounded hover:bg-green-200 transition-colors whitespace-nowrap"
                                title={`附加工作區名稱: ${workspaceTitle}`}
                              >
                                + 工作區名稱
                              </button>
                            ) : (
                              <div className="text-xs text-red-500">No title</div>
                            )}
                          </>
                        ) : (
                          <span className="flex-1 text-sm text-gray-700 font-mono">{dir}</span>
                        )}
                        {!workspaceMode && (
                          <button
                            onClick={() => handleRemoveDirectory(index)}
                            className="px-2 py-1 text-red-600 hover:text-red-700 text-sm"
                            title="Remove"
                          >
                            ×
                          </button>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            )}

            <p className="mt-2 text-xs text-gray-500">
              {workspaceMode ? (
                <>
                  Supported formats (must use absolute path):{' '}
                  {isWindows ? (
                    <>
                      <code className="bg-gray-100 px-1 rounded">C:\Users\...\Documents</code>
                    </>
                  ) : (
                    <>
                      <code className="bg-gray-100 px-1 rounded">/Users/.../Documents</code>
                    </>
                  )}
                </>
              ) : (
                <>
                  Supported formats:{' '}
                  {isWindows ? (
                    <>
                      <code className="bg-gray-100 px-1 rounded">C:\Users\...\Documents</code>,{' '}
                      <code className="bg-gray-100 px-1 rounded">%USERPROFILE%\Documents</code>,{' '}
                      <code className="bg-gray-100 px-1 rounded">.\data</code>
                    </>
                  ) : (
                    <>
                      <code className="bg-gray-100 px-1 rounded">~/Documents</code>,{' '}
                      <code className="bg-gray-100 px-1 rounded">./data</code>,{' '}
                      <code className="bg-gray-100 px-1 rounded">/Users/.../Documents</code>
                    </>
                  )}
                </>
              )}
            </p>
          </div>

          {/* Artifacts Directory Input (Workspace Mode Only) */}
          {workspaceMode && (
            <div className="border-t pt-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Artifacts Directory
              </label>
              <p className="text-xs text-gray-600 mb-2">
                Directory name for storing playbook artifacts under the workspace storage path.
                <br />
                Default: <code className="bg-gray-100 px-1 rounded">artifacts</code>
              </p>
              <input
                type="text"
                value={artifactsDir}
                onChange={(e) => setArtifactsDir(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="artifacts"
              />
              <p className="mt-1 text-xs text-gray-500">
                Artifacts will be stored at: <code className="bg-gray-100 px-1 rounded">{directories[0] || '...'}/{artifactsDir || 'artifacts'}</code>
              </p>
            </div>
          )}

          {/* Playbook Storage Configuration (Workspace Mode Only) */}
          {workspaceMode && (
            <div className="border-t pt-4">
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-gray-700">
                  Playbook Storage Configuration
                </label>
                {loadingPlaybooks && (
                  <span className="text-xs text-gray-500">Loading playbooks...</span>
                )}
              </div>
              <p className="text-xs text-gray-600 mb-3">
                Configure custom storage paths for specific playbooks. Playbooks without custom configuration will use the workspace default.
              </p>

              {/* List of used playbooks */}
              {usedPlaybooks.length > 0 && (
                <div className="space-y-3 mb-4">
                  {usedPlaybooks.map((playbookCode) => {
                    const config = playbookStorageConfig[playbookCode] || {};
                    const useCustom = !!(config.base_path && config.base_path.trim());

                    return (
                      <div key={playbookCode} className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={useCustom}
                              onChange={(e) => {
                                const newConfig = { ...playbookStorageConfig };
                                if (e.target.checked) {
                                  newConfig[playbookCode] = {
                                    base_path: directories[0] || '',
                                    artifacts_dir: artifactsDir,
                                  };
                                } else {
                                  delete newConfig[playbookCode];
                                }
                                setPlaybookStorageConfig(newConfig);
                              }}
                              className="rounded"
                            />
                            <span className="text-sm font-medium text-gray-900">{playbookCode}</span>
                          </div>
                          {useCustom && (
                            <button
                              onClick={() => {
                                const newConfig = { ...playbookStorageConfig };
                                delete newConfig[playbookCode];
                                setPlaybookStorageConfig(newConfig);
                              }}
                              className="text-xs text-red-600 hover:text-red-700"
                            >
                              Remove
                            </button>
                          )}
                        </div>
                        {useCustom && (
                          <div className="space-y-2 mt-2">
                            <div>
                              <label className="block text-xs font-medium text-gray-700 mb-1">
                                Base Path
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
                                className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                                placeholder={directories[0] || 'Enter base path'}
                              />
                            </div>
                            <div>
                              <label className="block text-xs font-medium text-gray-700 mb-1">
                                Artifacts Directory
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
                                className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                <p className="text-xs text-gray-500 italic">
                  No playbooks have been used in this workspace yet. Playbook-specific storage configuration will appear here once playbooks are executed.
                </p>
              )}
            </div>
          )}

          {!workspaceMode && (
            <div className="border-t pt-4">
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={allowWrite}
                  onChange={(e) => setAllowWrite(e.target.checked)}
                  className="mr-2"
                />
                <span className="text-sm font-medium text-gray-700">{t('allowWriteOperations')}</span>
              </label>
              <p className="mt-2 text-xs text-gray-500">{t('allowWriteDescription')}</p>
            </div>
          )}

          {configuredDirs.length > 0 && (
            <div className="border-t pt-4">
              <h3 className="text-sm font-medium text-gray-700 mb-2">{t('configuredDirectories')}</h3>
              <div className="space-y-2">
                {configuredDirs.map((conn, idx) => (
                  <div key={idx} className="p-3 bg-gray-50 rounded">
                    <div className="font-medium text-sm">{conn.name}</div>
                    <div className="text-xs text-gray-600 mt-1">
                      {conn.allowed_directories.join(', ')}
                    </div>
                    {conn.allow_write && (
                      <span className="text-xs text-orange-600 mt-1 block">
                        {t('writeEnabled')}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="flex justify-end space-x-3 pt-4 border-t mt-4">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50"
          >
            {t('cancel')}
          </button>
          <button
            onClick={handleSave}
            disabled={saving || directories.length === 0}
            className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50"
          >
            {saving ? t('saving') : t('save')}
          </button>
        </div>
      </div>
    </div>
    </>
  );
}
