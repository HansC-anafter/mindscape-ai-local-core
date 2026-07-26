import { AlertTriangle, CheckCircle2, Cloud, FolderSync } from 'lucide-react';
import { useT } from '../../../../../lib/i18n';
import {
  defaultBackupConfig,
  deriveGoogleDriveStatusFromConfig,
  formatBytes,
  mirrorScopeTranslationSuffix,
} from './model';
import {
  mirrorScopeOptions,
  type BackupBusyAction,
  type BackupConfig,
  type BackupConfigUpdate,
  type BackupStatus,
  type MirrorScope,
} from './types';

interface RuntimeBackupPolicySectionProps {
  status: BackupStatus | null;
  config: BackupConfig;
  busyAction: BackupBusyAction;
  configChanged: boolean;
  updateConfig: BackupConfigUpdate;
  toggleMirrorScope: (scope: MirrorScope, enabled: boolean) => void;
  saveConfig: () => void;
  applyGoogleDriveDefaults: () => void;
  prepareGoogleDriveSync: () => void;
}

export function RuntimeBackupPolicySection({
  status,
  config,
  busyAction,
  configChanged,
  updateConfig,
  toggleMirrorScope,
  saveConfig,
  applyGoogleDriveDefaults,
  prepareGoogleDriveSync,
}: RuntimeBackupPolicySectionProps) {
  const t = useT();
  const policy = status?.policy || {};
  const googleDrive =
    status?.google_drive_sync?.available
      ? status.google_drive_sync
      : deriveGoogleDriveStatusFromConfig(config) || status?.google_drive_sync || null;

  return (
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
                  {t(`localRuntimeBackupMirrorScope${mirrorScopeTranslationSuffix(scope)}` as any)}
                </span>
                <span className="block text-secondary dark:text-gray-400">
                  {t(`localRuntimeBackupMirrorScope${mirrorScopeTranslationSuffix(scope)}Help` as any)}
                </span>
              </span>
            </label>
          ))}
        </div>
      </div>
      <div className="space-y-3 rounded-md border border-default p-3 dark:border-gray-700">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium text-primary dark:text-gray-100">
              <Cloud className="h-4 w-4" />
              {t('localRuntimeBackupGoogleDriveSync' as any)}
            </div>
            <div className="mt-1 text-xs text-secondary dark:text-gray-400">
              {t('localRuntimeBackupGoogleDriveSyncHelp' as any)}
            </div>
          </div>
          <div className="inline-flex items-center gap-2 text-xs">
            {googleDrive?.available ? (
              <>
                <CheckCircle2 className="h-4 w-4 text-green-600" />
                <span className="text-green-700 dark:text-green-300">
                  {googleDrive.account_label || t('available' as any)}
                </span>
              </>
            ) : (
              <>
                <AlertTriangle className="h-4 w-4 text-yellow-600" />
                <span className="text-yellow-700 dark:text-yellow-300">{t('notConfigured' as any)}</span>
              </>
            )}
          </div>
        </div>

        {googleDrive?.available ? (
          <div className="space-y-2 text-xs text-secondary dark:text-gray-400">
            <div className="break-all">
              {t('localRuntimeBackupGoogleDriveMyDrive' as any)}: {googleDrive.my_drive_path || '-'}
            </div>
            <div className="break-all">
              {t('localRuntimeBackupGoogleDriveRecommendedMirror' as any)}: {googleDrive.recommended_mirror_root || '-'}
            </div>
            <div className="break-all">
              {t('localRuntimeBackupGoogleDriveRecommendedResource' as any)}: {googleDrive.recommended_resource_root || '-'}
            </div>
          </div>
        ) : (
          <p className="text-xs text-yellow-700 dark:text-yellow-300">
            {googleDrive?.warnings?.[0] || t('localRuntimeBackupGoogleDriveUnavailable' as any)}
          </p>
        )}

        <div className="grid gap-3 md:grid-cols-2">
          <label className="flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              checked={config.google_drive_resource_sync_enabled}
              onChange={(event) => updateConfig('google_drive_resource_sync_enabled', event.target.checked)}
              className="mt-1"
            />
            <span>
              <span className="font-medium text-primary dark:text-gray-100">
                {t('localRuntimeBackupGoogleDriveResourceSync' as any)}
              </span>
              <span className="block text-secondary dark:text-gray-400">
                {t('localRuntimeBackupGoogleDriveResourceSyncHelp' as any)}
              </span>
            </span>
          </label>
          <label className="text-sm">
            <span className="font-medium text-primary dark:text-gray-100">
              {t('localRuntimeBackupGoogleDriveResourceRoot' as any)}
            </span>
            <input
              type="text"
              value={config.google_drive_resource_root}
              onChange={(event) => updateConfig('google_drive_resource_root', event.target.value)}
              className="mt-1 w-full rounded-md border border-default bg-surface-primary px-3 py-2 text-sm text-primary dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
            />
          </label>
        </div>

        <div className="rounded-md bg-yellow-50 p-3 text-xs text-yellow-900 dark:bg-yellow-900/20 dark:text-yellow-200">
          {t('localRuntimeBackupGoogleDriveSafetyNote' as any)}
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={applyGoogleDriveDefaults}
            disabled={!googleDrive?.available || busyAction !== null}
            className="inline-flex items-center gap-2 rounded-md border border-default px-3 py-2 text-sm font-medium text-primary hover:bg-surface-accent disabled:opacity-50 dark:border-gray-600 dark:text-gray-100 dark:hover:bg-gray-700"
          >
            <FolderSync className="h-4 w-4" />
            {t('localRuntimeBackupApplyGoogleDrive' as any)}
          </button>
          <button
            type="button"
            onClick={prepareGoogleDriveSync}
            disabled={!googleDrive?.available || busyAction !== null || !config.mirror_root || !config.google_drive_resource_root}
            className="inline-flex items-center gap-2 rounded-md border border-default px-3 py-2 text-sm font-medium text-primary hover:bg-surface-accent disabled:opacity-50 dark:border-gray-600 dark:text-gray-100 dark:hover:bg-gray-700"
          >
            <FolderSync className="h-4 w-4" />
            {busyAction === 'prepare-google-drive'
              ? t('checking' as any)
              : t('localRuntimeBackupPrepareGoogleDrive' as any)}
          </button>
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
  );
}
