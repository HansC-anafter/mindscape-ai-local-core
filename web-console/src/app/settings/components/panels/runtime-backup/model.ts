import type { BackupConfig, GoogleDriveSyncStatus } from './types';

export const defaultBackupConfig: BackupConfig = {
  backup_root: '',
  mirror_root: '',
  retention_local_count: 7,
  retention_mirror_count: 3,
  min_free_gb: 20,
  require_mirror: false,
  base_interval_hours: 168,
  mirror_scopes: ['postgres_chain', 'runtime_metadata', 'auth_state'],
  google_drive_resource_sync_enabled: false,
  google_drive_resource_root: '',
};

export function normalizeConfig(config?: Partial<BackupConfig>): BackupConfig {
  return {
    ...defaultBackupConfig,
    ...(config || {}),
    mirror_scopes: config?.mirror_scopes?.length
      ? config.mirror_scopes
      : defaultBackupConfig.mirror_scopes,
  };
}

export function deriveGoogleDriveStatusFromConfig(config: BackupConfig): GoogleDriveSyncStatus | null {
  const sourcePath = config.mirror_root || config.google_drive_resource_root;
  const match = sourcePath.match(/^(.*\/GoogleDrive-[^/]+\/(?:我的雲端硬碟|My Drive))(?:\/.*)?$/);
  if (!match) return null;

  const myDrivePath = match[1];
  const mountPath = myDrivePath.replace(/\/(?:我的雲端硬碟|My Drive)$/, '');
  const accountLabel = mountPath.split('/').pop()?.replace(/^GoogleDrive-/, '') || '';
  return {
    available: true,
    account_label: accountLabel,
    mount_path: mountPath,
    my_drive_path: myDrivePath,
    recommended_mirror_root: config.mirror_root || `${myDrivePath}/Mindscape/local-core-runtime-backups`,
    recommended_resource_root:
      config.google_drive_resource_root || `${myDrivePath}/Mindscape/local-core-resource-collaboration`,
    recommended_mirror_scopes: defaultBackupConfig.mirror_scopes,
    mirror_root_active: Boolean(config.mirror_root),
    resource_sync_enabled: config.google_drive_resource_sync_enabled,
    resource_root: config.google_drive_resource_root,
    warnings: [],
  };
}

export function formatBytes(bytes?: number): string {
  if (!bytes || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

export function formatDate(value?: string): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function commandOutput(payload: any): string {
  if (!payload) return '';
  const parts = [
    payload.stdout,
    payload.stderr,
    payload.raw,
    Array.isArray(payload.log_tail) ? payload.log_tail.join('\n') : '',
  ].filter(Boolean);
  if (parts.length > 0) return parts.join('\n');
  return JSON.stringify(payload, null, 2);
}

export function mirrorScopeTranslationSuffix(scope: string): string {
  return scope.replace(/(^|_)([a-z])/g, (_match, _sep, char) => char.toUpperCase());
}
