'use client';

import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Clipboard,
  Database,
  HardDrive,
  Play,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';
import { t } from '../../../../lib/i18n';
import { Card } from '../Card';
import { settingsApi } from '../../utils/settingsApi';
import { showNotification } from '../../hooks/useSettingsNotification';

interface BackupConfig {
  backup_root: string;
  mirror_root: string;
  retention_local_count: number;
  retention_mirror_count: number;
  min_free_gb: number;
  require_mirror: boolean;
  base_interval_hours: number;
  mirror_scopes: string[];
}

interface BackupSummary {
  backup_name: string;
  created_at?: string;
  path: string;
  host_backup_dir: string;
  git_commit?: string | null;
  artifact_count: number;
  total_bytes: number;
  mode?: string;
  base_backup_id?: string | null;
  file_snapshot_id?: string | null;
  options?: Record<string, boolean>;
  profile_state?: {
    valid: boolean;
    profiles?: number;
    invalid_profiles?: number;
    invalid?: Array<{ profile?: string; error?: string }>;
    error?: string;
  } | null;
}

interface BackupJob {
  job_id: string;
  state: 'running' | 'succeeded' | 'failed' | string;
  pid?: number;
  started_at?: string;
  completed_at?: string;
  backup_name?: string;
  backup_dir?: string;
  error?: string;
  log_tail?: string[];
}

interface BackupStatus {
  config: BackupConfig;
  backup_root: string;
  policy?: {
    mode?: string;
    primary_root?: string;
    mirror_root?: string;
    retention_local_count?: number;
    retention_mirror_count?: number;
    min_free_gb?: number;
    require_mirror?: boolean;
    base_interval_hours?: number;
    mirror_scopes?: string[];
    wal_archive_root?: string;
  };
  primary_free_bytes?: number | null;
  mirror_free_bytes?: number | null;
  postgres_archive_mode?: string | null;
  postgres_wal_ready_count?: number | null;
  postgres_wal_bytes?: number | null;
  wal_archive_dir?: string | null;
  wal_segment_count?: number | null;
  wal_archive_bytes?: number | null;
  base_backup_id?: string | null;
  base_backup_created_at?: string | null;
  base_backup_age_hours?: number | null;
  base_backup_required?: boolean | null;
  latest_file_snapshot_id?: string | null;
  can_run: boolean;
  blocking_reasons: string[];
  script_available: boolean;
  verify_script_available: boolean;
  host_project_root: string;
  device_node_available: boolean;
  latest_backup?: BackupSummary | null;
  latest_job?: BackupJob | null;
  commands: Record<'create' | 'dry_run' | 'verify_latest', string>;
  warnings: string[];
}

const mirrorScopeOptions = [
  'postgres_chain',
  'runtime_metadata',
  'auth_state',
  'blob_storage',
  'model_cache',
  'workspace_artifacts',
] as const;

function formatBytes(bytes?: number): string {
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

function formatDate(value?: string): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function commandOutput(payload: any): string {
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

export function RuntimeBackupSettings() {
  const [status, setStatus] = useState<BackupStatus | null>(null);
  const [config, setConfig] = useState<BackupConfig>({
    backup_root: '',
    mirror_root: '',
    retention_local_count: 7,
    retention_mirror_count: 3,
    min_free_gb: 20,
    require_mirror: false,
    base_interval_hours: 168,
    mirror_scopes: ['postgres_chain', 'runtime_metadata', 'auth_state'],
  });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [output, setOutput] = useState('');

  const latestJob = status?.latest_job || null;
  const jobRunning = latestJob?.state === 'running';
  const controlsAvailable = Boolean(
    status?.device_node_available &&
    status?.script_available &&
    status?.verify_script_available
  );
  const canStart = Boolean(controlsAvailable && status?.can_run);

  const loadStatus = async () => {
    try {
      const data = await settingsApi.get<BackupStatus>('/api/v1/system-settings/backups/local-runtime');
      setStatus(data);
      setConfig(data.config);
      setLoadError(null);
    } catch (error: any) {
      const message = error.message || t('localRuntimeBackupLoadFailed' as any);
      setLoadError(message);
      showNotification('error', message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  useEffect(() => {
    if (!jobRunning) return;
    const timer = window.setInterval(() => {
      loadStatus();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [jobRunning]);

  const configChanged = useMemo(() => {
    if (!status) return false;
    return JSON.stringify(status.config) !== JSON.stringify(config);
  }, [status, config]);

  const updateConfig = (key: keyof BackupConfig, value: BackupConfig[keyof BackupConfig]) => {
    setConfig((current) => ({ ...current, [key]: value }));
  };

  const toggleMirrorScope = (scope: string, enabled: boolean) => {
    if (scope === 'postgres_chain') return;
    setConfig((current) => {
      const base = new Set(current.mirror_scopes || []);
      base.add('postgres_chain');
      if (enabled) {
        base.add(scope);
      } else {
        base.delete(scope);
      }
      return { ...current, mirror_scopes: mirrorScopeOptions.filter((item) => base.has(item)) };
    });
  };

  const saveConfig = async () => {
    try {
      setBusyAction('save');
      const data = await settingsApi.put<BackupStatus>(
        '/api/v1/system-settings/backups/local-runtime/config',
        config
      );
      setStatus(data);
      setConfig(data.config);
      showNotification('success', t('localRuntimeBackupConfigSaved' as any));
    } catch (error: any) {
      showNotification('error', error.message || t('localRuntimeBackupSaveFailed' as any));
    } finally {
      setBusyAction(null);
    }
  };

  const runAction = async (action: 'dry-run' | 'start' | 'verify') => {
    try {
      setBusyAction(action);
      setOutput('');
      const endpoint =
        action === 'verify'
          ? '/api/v1/system-settings/backups/local-runtime/verify'
          : `/api/v1/system-settings/backups/local-runtime/${action}`;
      const payload = action === 'verify' ? {} : config;
      const result = await settingsApi.post<any>(endpoint, payload);
      setOutput(commandOutput(result));
      await loadStatus();
      showNotification('success', t(`localRuntimeBackup${action === 'dry-run' ? 'DryRun' : action === 'start' ? 'Started' : 'Verified'}` as any));
    } catch (error: any) {
      showNotification('error', error.message || t('localRuntimeBackupActionFailed' as any));
    } finally {
      setBusyAction(null);
    }
  };

  const copyCommand = async (command: string) => {
    try {
      await navigator.clipboard.writeText(command);
      showNotification('success', t('copied' as any) || 'Copied');
    } catch {
      showNotification('error', t('copyFailed' as any) || 'Copy failed');
    }
  };

  if (loading) {
    return (
      <Card>
        <div className="text-sm text-secondary dark:text-gray-400">{t('loading' as any)}...</div>
      </Card>
    );
  }

  const latest = status?.latest_backup || null;
  const profileState = latest?.profile_state;
  const policy = status?.policy || {};
  const archiveMode = status?.postgres_archive_mode || '-';
  const walReadyCount = status?.postgres_wal_ready_count ?? 0;
  const walBytes = status?.postgres_wal_bytes ?? 0;
  const blockingReasons = status?.blocking_reasons || [];
  const displayMode =
    policy.mode === 'incremental_runtime_backup'
      ? t('localRuntimeBackupIncrementalMode' as any)
      : policy.mode || '-';

  return (
    <Card className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold text-primary dark:text-gray-100">
            {t('localRuntimeBackup' as any)}
          </h2>
          <p className="mt-1 text-sm text-secondary dark:text-gray-400">
            {t('localRuntimeBackupDescription' as any)}
          </p>
        </div>
        <button
          type="button"
          onClick={loadStatus}
          disabled={busyAction !== null}
          className="inline-flex items-center gap-2 rounded-md border border-default px-3 py-2 text-sm font-medium text-primary hover:bg-surface-accent disabled:opacity-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700"
        >
          <RefreshCw className="h-4 w-4" />
          {t('refresh' as any) || 'Refresh'}
        </button>
      </div>

      {status?.warnings?.length ? (
        <div className="rounded-md border border-yellow-300 bg-yellow-50 p-3 text-sm text-yellow-900 dark:border-yellow-700 dark:bg-yellow-900/20 dark:text-yellow-200">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle className="h-4 w-4" />
            {t('localRuntimeBackupWarnings' as any)}
          </div>
          <ul className="mt-2 list-disc pl-5">
            {status.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-md border border-default p-3 dark:border-gray-700">
          <div className="flex items-center gap-2 text-sm font-medium text-secondary dark:text-gray-400">
            <HardDrive className="h-4 w-4" />
            {t('localRuntimeBackupPrimaryRoot' as any)}
          </div>
          <div className="mt-2 break-all font-mono text-sm text-primary dark:text-gray-100">
            {policy.primary_root || config.backup_root || status?.backup_root || '-'}
          </div>
          <div className="mt-2 text-xs text-secondary dark:text-gray-400">
            {t('localRuntimeBackupFree' as any)}: {formatBytes(status?.primary_free_bytes || 0)}
          </div>
        </div>
        <div className="rounded-md border border-default p-3 dark:border-gray-700">
          <div className="flex items-center gap-2 text-sm font-medium text-secondary dark:text-gray-400">
            <Database className="h-4 w-4" />
            {t('localRuntimeBackupIncrementalCard' as any)}
          </div>
          <div className="mt-2 text-sm text-primary dark:text-gray-100">
            {t('localRuntimeBackupMode' as any)}: {displayMode}
          </div>
          <div className="mt-2 text-xs text-secondary dark:text-gray-400">
            {t('localRuntimeBackupWalArchive' as any)}: {archiveMode}; {t('localRuntimeBackupWalReady' as any)}: {walReadyCount}; pg_wal: {formatBytes(walBytes)}
          </div>
          <div className="mt-1 text-xs text-secondary dark:text-gray-400">
            {t('localRuntimeBackupBaseBackup' as any)}: {status?.base_backup_id || '-'}
          </div>
        </div>
        <div className="rounded-md border border-default p-3 dark:border-gray-700">
          <div className="flex items-center gap-2 text-sm font-medium text-secondary dark:text-gray-400">
            <ShieldCheck className="h-4 w-4" />
            {t('localRuntimeBackupDeviceNode' as any)}
          </div>
          <div className="mt-2 flex items-center gap-2 text-sm">
            {loadError ? (
              <>
                <AlertTriangle className="h-4 w-4 text-yellow-600" />
                <span className="text-yellow-700 dark:text-yellow-300">{t('statusUnavailable' as any)}</span>
              </>
            ) : status?.device_node_available ? (
              <>
                <CheckCircle2 className="h-4 w-4 text-green-600" />
                <span className="text-green-700 dark:text-green-300">{t('available' as any)}</span>
              </>
            ) : (
              <>
                <AlertTriangle className="h-4 w-4 text-yellow-600" />
                <span className="text-yellow-700 dark:text-yellow-300">{t('notConfigured' as any)}</span>
              </>
            )}
          </div>
          <div className="mt-2 text-xs text-secondary dark:text-gray-400">
            {t('latestBackup' as any)}: {latest ? `${formatBytes(latest.total_bytes)} - ${latest.artifact_count} ${t('artifacts' as any)}` : t('none' as any)}
          </div>
        </div>
      </div>

      {blockingReasons.length ? (
        <div className="rounded-md border border-yellow-300 bg-yellow-50 p-3 text-sm text-yellow-900 dark:border-yellow-700 dark:bg-yellow-900/20 dark:text-yellow-200">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle className="h-4 w-4" />
            {t('localRuntimeBackupBlockingReasons' as any)}
          </div>
          <ul className="mt-2 list-disc pl-5">
            {blockingReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <section className="space-y-3">
        <h3 className="text-base font-semibold text-primary dark:text-gray-100">
          {t('localRuntimeBackupPolicy' as any)}
        </h3>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="text-sm">
            <span className="font-medium text-primary dark:text-gray-100">{t('localRuntimeBackupPrimaryRoot' as any)}</span>
            <span className="block text-secondary dark:text-gray-400">{t('localRuntimeBackupPrimaryRootHelp' as any)}</span>
            <input
              type="text"
              value={config.backup_root}
              onChange={(event) => updateConfig('backup_root', event.target.value)}
              className="mt-1 w-full rounded-md border border-default bg-surface-primary px-3 py-2 text-sm text-primary dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
            />
          </label>
          <label className="text-sm">
            <span className="font-medium text-primary dark:text-gray-100">{t('localRuntimeBackupMirrorRoot' as any)}</span>
            <span className="block text-secondary dark:text-gray-400">{t('localRuntimeBackupMirrorRootHelp' as any)}</span>
            <input
              type="text"
              value={config.mirror_root}
              onChange={(event) => updateConfig('mirror_root', event.target.value)}
              className="mt-1 w-full rounded-md border border-default bg-surface-primary px-3 py-2 text-sm text-primary dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
            />
          </label>
          <label className="flex items-center gap-3 text-sm">
            <input
              type="checkbox"
              checked={config.require_mirror}
              onChange={(event) => updateConfig('require_mirror', event.target.checked)}
            />
            <span>
              <span className="font-medium text-primary dark:text-gray-100">{t('localRuntimeBackupRequireMirror' as any)}</span>
              <span className="block text-secondary dark:text-gray-400">{t('localRuntimeBackupRequireMirrorHelp' as any)}</span>
            </span>
          </label>
          <label className="text-sm">
            <span className="font-medium text-primary dark:text-gray-100">{t('localRuntimeBackupLocalRetention' as any)}</span>
            <input
              type="number"
              min={1}
              value={config.retention_local_count}
              onChange={(event) => updateConfig('retention_local_count', Number(event.target.value))}
              className="mt-1 w-full rounded-md border border-default bg-surface-primary px-3 py-2 text-sm text-primary dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
            />
          </label>
          <label className="text-sm">
            <span className="font-medium text-primary dark:text-gray-100">{t('localRuntimeBackupMirrorRetention' as any)}</span>
            <input
              type="number"
              min={1}
              value={config.retention_mirror_count}
              onChange={(event) => updateConfig('retention_mirror_count', Number(event.target.value))}
              className="mt-1 w-full rounded-md border border-default bg-surface-primary px-3 py-2 text-sm text-primary dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
            />
          </label>
          <label className="text-sm">
            <span className="font-medium text-primary dark:text-gray-100">{t('localRuntimeBackupMinimumFreeSpace' as any)}</span>
            <input
              type="number"
              min={1}
              value={config.min_free_gb}
              onChange={(event) => updateConfig('min_free_gb', Number(event.target.value))}
              className="mt-1 w-full rounded-md border border-default bg-surface-primary px-3 py-2 text-sm text-primary dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
            />
          </label>
          <label className="text-sm">
            <span className="font-medium text-primary dark:text-gray-100">{t('localRuntimeBackupBaseIntervalHours' as any)}</span>
            <input
              type="number"
              min={1}
              value={config.base_interval_hours}
              onChange={(event) => updateConfig('base_interval_hours', Number(event.target.value))}
              className="mt-1 w-full rounded-md border border-default bg-surface-primary px-3 py-2 text-sm text-primary dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
            />
          </label>
          <div className="rounded-md border border-default p-3 text-sm dark:border-gray-700">
            <div className="font-medium text-primary dark:text-gray-100">{t('localRuntimeBackupMirrorStatus' as any)}</div>
            <div className="mt-1 break-all text-secondary dark:text-gray-400">
              {policy.mirror_root || config.mirror_root || '-'}
            </div>
            <div className="mt-1 text-secondary dark:text-gray-400">
              {t('localRuntimeBackupFree' as any)}: {formatBytes(status?.mirror_free_bytes || 0)}
            </div>
            <div className="mt-1 text-secondary dark:text-gray-400">
              {t('localRuntimeBackupMirrorScopes' as any)}: {(config.mirror_scopes || []).join(', ')}
            </div>
          </div>
        </div>
        <div className="space-y-2 rounded-md border border-default p-3 dark:border-gray-700">
          <div className="text-sm font-medium text-primary dark:text-gray-100">
            {t('localRuntimeBackupMirrorScopes' as any)}
          </div>
          <div className="text-xs text-secondary dark:text-gray-400">
            {t('localRuntimeBackupMirrorScopesHelp' as any)}
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {mirrorScopeOptions.map((scope) => (
              <label key={scope} className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={(config.mirror_scopes || []).includes(scope) || scope === 'postgres_chain'}
                  disabled={scope === 'postgres_chain'}
                  onChange={(event) => toggleMirrorScope(scope, event.target.checked)}
                  className="mt-1"
                />
                <span>
                  <span className="font-medium text-primary dark:text-gray-100">
                    {t(`localRuntimeBackupMirrorScope${scope.replace(/(^|_)([a-z])/g, (_match, _sep, char) => char.toUpperCase())}` as any)}
                  </span>
                  <span className="block text-secondary dark:text-gray-400">
                    {t(`localRuntimeBackupMirrorScope${scope.replace(/(^|_)([a-z])/g, (_match, _sep, char) => char.toUpperCase())}Help` as any)}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={saveConfig}
            disabled={!configChanged || busyAction !== null}
            className="rounded-md bg-gray-700 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50 dark:bg-gray-600 dark:hover:bg-gray-500"
          >
            {busyAction === 'save' ? t('saving' as any) : t('save' as any)}
          </button>
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-base font-semibold text-primary dark:text-gray-100">
          {t('backupControls' as any)}
        </h3>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => runAction('dry-run')}
            disabled={!controlsAvailable || busyAction !== null}
            className="inline-flex items-center gap-2 rounded-md border border-default px-4 py-2 text-sm font-medium text-primary hover:bg-surface-accent disabled:opacity-50 dark:border-gray-600 dark:text-gray-100 dark:hover:bg-gray-700"
          >
            <RefreshCw className="h-4 w-4" />
            {busyAction === 'dry-run' ? t('checking' as any) || 'Checking...' : t('backupDryRun' as any)}
          </button>
          <button
            type="button"
            onClick={() => runAction('start')}
            disabled={!canStart || busyAction !== null || jobRunning}
            className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            <Play className="h-4 w-4" />
            {busyAction === 'start' ? t('starting' as any) || 'Starting...' : t('startBackup' as any)}
          </button>
          <button
            type="button"
            onClick={() => runAction('verify')}
            disabled={!controlsAvailable || busyAction !== null || !latest}
            className="inline-flex items-center gap-2 rounded-md border border-default px-4 py-2 text-sm font-medium text-primary hover:bg-surface-accent disabled:opacity-50 dark:border-gray-600 dark:text-gray-100 dark:hover:bg-gray-700"
          >
            <ShieldCheck className="h-4 w-4" />
            {busyAction === 'verify' ? t('verifying' as any) || 'Verifying...' : t('verifyLatestBackup' as any)}
          </button>
        </div>
        {!controlsAvailable ? (
          <p className="text-sm text-yellow-700 dark:text-yellow-300">
            {loadError
              ? t('localRuntimeBackupApiUnavailable' as any)
              : t('localRuntimeBackupDeviceNodeRequired' as any)}
          </p>
        ) : null}
      </section>

      {latest ? (
        <section className="space-y-3">
          <h3 className="text-base font-semibold text-primary dark:text-gray-100">
            {t('latestBackup' as any)}
          </h3>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-2 text-sm">
              <div><span className="text-secondary dark:text-gray-400">{t('name' as any)}: </span>{latest.backup_name}</div>
              <div><span className="text-secondary dark:text-gray-400">{t('createdAt' as any)}: </span>{formatDate(latest.created_at)}</div>
              <div><span className="text-secondary dark:text-gray-400">{t('localRuntimeBackupMode' as any)}: </span>{latest.mode || '-'}</div>
              <div><span className="text-secondary dark:text-gray-400">Git: </span>{latest.git_commit || '-'}</div>
              <div className="break-all"><span className="text-secondary dark:text-gray-400">{t('path' as any)}: </span>{latest.path}</div>
            </div>
            <div className="space-y-2 text-sm">
              <div>
                <span className="text-secondary dark:text-gray-400">{t('profileState' as any)}: </span>
                {profileState ? (
                  profileState.valid ? (
                    <span className="text-green-700 dark:text-green-300">{t('valid' as any) || 'Valid'}</span>
                  ) : (
                    <span className="text-red-700 dark:text-red-300">
                      {profileState.invalid_profiles || 0} invalid / {profileState.profiles || 0}
                    </span>
                  )
                ) : '-'}
              </div>
              <div><span className="text-secondary dark:text-gray-400">{t('artifacts' as any)}: </span>{latest.artifact_count}</div>
              <div><span className="text-secondary dark:text-gray-400">{t('size' as any)}: </span>{formatBytes(latest.total_bytes)}</div>
              <div><span className="text-secondary dark:text-gray-400">{t('localRuntimeBackupBaseBackup' as any)}: </span>{latest.base_backup_id || '-'}</div>
              <div><span className="text-secondary dark:text-gray-400">{t('localRuntimeBackupFileSnapshot' as any)}: </span>{latest.file_snapshot_id || '-'}</div>
            </div>
          </div>
        </section>
      ) : null}

      {latestJob ? (
        <section className="space-y-3">
          <h3 className="text-base font-semibold text-primary dark:text-gray-100">
            {t('backupJob' as any)}
          </h3>
          <div className="space-y-2 text-sm">
            <div>
              <span className="text-secondary dark:text-gray-400">{t('status' as any)}: </span>
              <span className={latestJob.state === 'failed' ? 'text-red-700 dark:text-red-300' : latestJob.state === 'succeeded' ? 'text-green-700 dark:text-green-300' : 'text-blue-700 dark:text-blue-300'}>
                {latestJob.state}
              </span>
            </div>
            <div><span className="text-secondary dark:text-gray-400">Job: </span>{latestJob.job_id}</div>
            <div><span className="text-secondary dark:text-gray-400">{t('startedAt' as any)}: </span>{formatDate(latestJob.started_at)}</div>
            {latestJob.error ? <div className="text-red-700 dark:text-red-300">{latestJob.error}</div> : null}
            {latestJob.log_tail?.length ? (
              <pre className="max-h-48 overflow-auto rounded-md bg-gray-950 p-3 text-xs text-gray-100">
                {latestJob.log_tail.join('\n')}
              </pre>
            ) : null}
          </div>
        </section>
      ) : null}

      {output ? (
        <section className="space-y-3">
          <h3 className="text-base font-semibold text-primary dark:text-gray-100">
            {t('commandOutput' as any)}
          </h3>
          <pre className="max-h-64 overflow-auto rounded-md bg-gray-950 p-3 text-xs text-gray-100">
            {output}
          </pre>
        </section>
      ) : null}

      {status?.commands ? (
        <section className="space-y-3">
          <h3 className="text-base font-semibold text-primary dark:text-gray-100">
            {t('backupCommands' as any)}
          </h3>
          {Object.entries(status.commands).map(([key, command]) => (
            <div key={key} className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-medium text-secondary dark:text-gray-400">{key}</div>
                <button
                  type="button"
                  onClick={() => copyCommand(command)}
                  className="inline-flex items-center gap-1 rounded-md border border-default px-2 py-1 text-xs text-primary hover:bg-surface-accent dark:border-gray-600 dark:text-gray-100 dark:hover:bg-gray-700"
                >
                  <Clipboard className="h-3 w-3" />
                  {t('copy' as any) || 'Copy'}
                </button>
              </div>
              <pre className="overflow-auto rounded-md bg-gray-100 p-3 text-xs text-gray-800 dark:bg-gray-900 dark:text-gray-100">
                {command}
              </pre>
            </div>
          ))}
        </section>
      ) : null}
    </Card>
  );
}
