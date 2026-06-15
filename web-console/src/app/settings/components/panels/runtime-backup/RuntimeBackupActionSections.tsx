import { Clipboard, Play, RefreshCw, ShieldCheck } from 'lucide-react';
import { t } from '../../../../../lib/i18n';
import { formatBytes, formatDate } from './model';
import type { BackupAction, BackupBusyAction, BackupStatus } from './types';

interface RuntimeBackupActionSectionsProps {
  status: BackupStatus | null;
  busyAction: BackupBusyAction;
  controlsAvailable: boolean;
  canStart: boolean;
  jobRunning: boolean;
  loadError: string | null;
  output: string;
  runAction: (action: BackupAction) => void;
  copyCommand: (command: string) => void;
}

export function RuntimeBackupActionSections({
  status,
  busyAction,
  controlsAvailable,
  canStart,
  jobRunning,
  loadError,
  output,
  runAction,
  copyCommand,
}: RuntimeBackupActionSectionsProps) {
  const latest = status?.latest_backup || null;
  const latestJob = status?.latest_job || null;
  const profileState = latest?.profile_state;

  return (
    <>
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
    </>
  );
}
