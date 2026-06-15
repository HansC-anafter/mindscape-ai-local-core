import { AlertTriangle, CheckCircle2, Database, HardDrive, ShieldCheck } from 'lucide-react';
import { t } from '../../../../../lib/i18n';
import { formatBytes } from './model';
import type { BackupConfig, BackupStatus } from './types';

interface RuntimeBackupStatusSummaryProps {
  status: BackupStatus | null;
  config: BackupConfig;
  loadError: string | null;
}

export function RuntimeBackupStatusSummary({
  status,
  config,
  loadError,
}: RuntimeBackupStatusSummaryProps) {
  const latest = status?.latest_backup || null;
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
    <>
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
    </>
  );
}
