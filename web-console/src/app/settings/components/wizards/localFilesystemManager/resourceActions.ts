'use client';

import { settingsApi } from '@/app/settings/utils/settingsApi';

import type { ConfiguredDirectory, DirectoryConfig, PlaybookStorageConfig } from './types';

interface WorkspaceStorageSaveInput {
  apiUrl: string;
  artifactsDir: string;
  directories: DirectoryConfig[];
  playbookStorageConfig: Record<string, PlaybookStorageConfig>;
  workspaceId: string;
}

interface WorkspaceStorageResponse {
  storage_base_path?: string;
  artifacts_dir?: string;
}

interface WorkspaceStorageSaveSuccess {
  ok: true;
  data: WorkspaceStorageResponse;
}

interface WorkspaceStorageSaveFailure {
  ok: false;
  errorMessage: string;
}

export type WorkspaceStorageSaveResult = WorkspaceStorageSaveSuccess | WorkspaceStorageSaveFailure;

export interface LocalFilesystemConfigureResponse {
  success: boolean;
  env_update?: {
    host_path: string;
    container_path: string;
    requires_restart: boolean;
  };
  message?: string;
}

export async function loadUsedPlaybookCodes({
  apiUrl,
  workspaceId,
}: {
  apiUrl: string;
  workspaceId: string;
}): Promise<string[]> {
  const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts`);
  if (!response.ok) {
    return [];
  }

  const data = await response.json();
  const playbooks = new Set<string>();
  if (data.artifacts && Array.isArray(data.artifacts)) {
    data.artifacts.forEach((artifact: any) => {
      if (artifact.playbook_code) {
        playbooks.add(artifact.playbook_code);
      }
    });
  }

  return Array.from(playbooks).sort();
}

export async function loadConfiguredFilesystemDirectories(): Promise<ConfiguredDirectory[]> {
  const data = await settingsApi.get<{ connections?: ConfiguredDirectory[] }>(
    '/api/v1/tools/local-filesystem/directories'
  );
  return data.connections || [];
}

export function toDirectoryConfigs(connection: ConfiguredDirectory): DirectoryConfig[] {
  if (connection.directory_configs && connection.directory_configs.length > 0) {
    return connection.directory_configs.map((directoryConfig: any) => ({
      path: directoryConfig.path,
      allowWrite: directoryConfig.allow_write || false,
    }));
  }

  return connection.allowed_directories.map((path: string) => ({
    path,
    allowWrite: connection.allow_write || false,
  }));
}

export async function saveWorkspaceStorageConfig({
  apiUrl,
  artifactsDir,
  directories,
  playbookStorageConfig,
  workspaceId,
}: WorkspaceStorageSaveInput): Promise<WorkspaceStorageSaveResult> {
  const storageBasePath = (directories[0]?.path?.trim() || '').replace(/\/+$/, '');
  const artifactsDirValue = artifactsDir.trim() || 'artifacts';
  const requestBody: {
    storage_base_path: string;
    artifacts_dir: string;
    playbook_storage_config?: Record<string, PlaybookStorageConfig>;
  } = {
    storage_base_path: storageBasePath,
    artifacts_dir: artifactsDirValue,
  };

  const playbookConfigToSave: Record<string, PlaybookStorageConfig> = {};
  Object.keys(playbookStorageConfig).forEach((playbookCode) => {
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
    return {
      ok: false,
      errorMessage: await getResponseErrorMessage(response),
    };
  }

  return {
    ok: true,
    data: await response.json(),
  };
}

export function configureLocalFilesystem(directories: DirectoryConfig[]): Promise<LocalFilesystemConfigureResponse> {
  return settingsApi.post<LocalFilesystemConfigureResponse>('/api/v1/tools/local-filesystem/configure', {
    connection_id: 'local-fs-default',
    name: 'Local File System',
    allowed_directories: directories.map((directory) => directory.path),
    directory_configs: directories.map((directory) => ({
      path: directory.path,
      allow_write: directory.allowWrite,
    })),
  });
}

export function updateHostDocumentsPath(hostPath: string): Promise<unknown> {
  return settingsApi.put('/api/v1/system/env', {
    key: 'HOST_DOCUMENTS_PATH',
    value: hostPath,
    comment: 'Local filesystem mount path (auto-configured)',
  });
}

export function restartSystemSettings(): Promise<{ success: boolean; message?: string }> {
  return settingsApi.post<{ success: boolean; message?: string }>('/api/v1/system-settings/restart');
}

async function getResponseErrorMessage(response: Response): Promise<string> {
  try {
    const errorData = await response.json();
    if (errorData.detail) {
      return errorData.detail;
    }
    if (errorData.message) {
      return errorData.message;
    }
    if (errorData.error) {
      return errorData.error;
    }
    return JSON.stringify(errorData);
  } catch (e) {
    const responseText = await response.text();
    return responseText || `HTTP ${response.status}: ${response.statusText}`;
  }
}
