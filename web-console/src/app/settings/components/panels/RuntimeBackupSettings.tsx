'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { useT } from '../../../../lib/i18n';
import { Card } from '../Card';
import { settingsApi } from '../../utils/settingsApi';
import { showNotification } from '../../hooks/useSettingsNotification';
import {
  commandOutput,
  defaultBackupConfig,
  normalizeConfig,
} from './runtime-backup/model';
import { RuntimeBackupActionSections } from './runtime-backup/RuntimeBackupActionSections';
import { RuntimeBackupPolicySection } from './runtime-backup/RuntimeBackupPolicySection';
import { RuntimeBackupStatusSummary } from './runtime-backup/RuntimeBackupStatusSummary';
import {
  mirrorScopeOptions,
  type BackupAction,
  type BackupBusyAction,
  type BackupConfig,
  type BackupConfigUpdate,
  type BackupStatus,
  type MirrorScope,
} from './runtime-backup/types';

export function RuntimeBackupSettings() {
  const t = useT();
  const [status, setStatus] = useState<BackupStatus | null>(null);
  const [config, setConfig] = useState<BackupConfig>(defaultBackupConfig);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<BackupBusyAction>(null);
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
      setConfig(normalizeConfig(data.config));
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
    }, 30000);
    return () => window.clearInterval(timer);
  }, [jobRunning]);

  const configChanged = useMemo(() => {
    if (!status) return false;
    return JSON.stringify(normalizeConfig(status.config)) !== JSON.stringify(config);
  }, [status, config]);

  const updateConfig: BackupConfigUpdate = (key, value) => {
    setConfig((current) => ({ ...current, [key]: value }));
  };

  const toggleMirrorScope = (scope: MirrorScope, enabled: boolean) => {
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
      setConfig(normalizeConfig(data.config));
      showNotification('success', t('localRuntimeBackupConfigSaved' as any));
    } catch (error: any) {
      showNotification('error', error.message || t('localRuntimeBackupSaveFailed' as any));
    } finally {
      setBusyAction(null);
    }
  };

  const runAction = async (action: BackupAction) => {
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
      const actionKey = action === 'dry-run' ? 'DryRun' : action === 'start' ? 'Started' : 'Verified';
      showNotification('success', t(`localRuntimeBackup${actionKey}` as any));
    } catch (error: any) {
      showNotification('error', error.message || t('localRuntimeBackupActionFailed' as any));
    } finally {
      setBusyAction(null);
    }
  };

  const applyGoogleDriveDefaults = () => {
    const googleDrive = status?.google_drive_sync;
    if (!googleDrive?.available) return;
    const recommendedScopes = new Set(
      googleDrive.recommended_mirror_scopes?.length
        ? googleDrive.recommended_mirror_scopes
        : defaultBackupConfig.mirror_scopes
    );
    recommendedScopes.add('postgres_chain');
    setConfig((current) => ({
      ...current,
      mirror_root: googleDrive.recommended_mirror_root || current.mirror_root,
      require_mirror: true,
      mirror_scopes: mirrorScopeOptions.filter((item) => recommendedScopes.has(item)),
      google_drive_resource_sync_enabled: true,
      google_drive_resource_root: googleDrive.recommended_resource_root || current.google_drive_resource_root,
    }));
  };

  const prepareGoogleDriveSync = async () => {
    try {
      setBusyAction('prepare-google-drive');
      setOutput('');
      const result = await settingsApi.post<any>(
        '/api/v1/system-settings/backups/local-runtime/google-drive/prepare',
        {
          mirror_root: config.mirror_root,
          resource_root: config.google_drive_resource_root,
        }
      );
      setOutput(commandOutput(result));
      await loadStatus();
      showNotification('success', t('localRuntimeBackupGoogleDrivePrepared' as any));
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

      <RuntimeBackupStatusSummary status={status} config={config} loadError={loadError} />

      <RuntimeBackupPolicySection
        status={status}
        config={config}
        busyAction={busyAction}
        configChanged={configChanged}
        updateConfig={updateConfig}
        toggleMirrorScope={toggleMirrorScope}
        saveConfig={saveConfig}
        applyGoogleDriveDefaults={applyGoogleDriveDefaults}
        prepareGoogleDriveSync={prepareGoogleDriveSync}
      />

      <RuntimeBackupActionSections
        status={status}
        busyAction={busyAction}
        controlsAvailable={controlsAvailable}
        canStart={canStart}
        jobRunning={jobRunning}
        loadError={loadError}
        output={output}
        runAction={runAction}
        copyCommand={copyCommand}
      />
    </Card>
  );
}
