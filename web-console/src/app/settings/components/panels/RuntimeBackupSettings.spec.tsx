import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { RuntimeBackupSettings } from './RuntimeBackupSettings';

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  post: vi.fn(),
}));

const translations = vi.hoisted<Record<string, string>>(() => ({
  artifacts: 'artifacts',
  available: 'Available',
  backupControls: 'Backup Controls',
  backupDryRun: 'Dry Run',
  backupJob: 'Backup Job',
  backupRoot: 'Backup Root',
  checking: 'Checking...',
  commandOutput: 'Command Output',
  copy: 'Copy',
  createdAt: 'Created At',
  latestBackup: 'Latest Backup',
  loading: 'Loading',
  localRuntimeBackup: 'Backup Settings',
  localRuntimeBackupBaseBackup: 'Base backup',
  localRuntimeBackupBlockingReasons: 'Blocking reasons',
  localRuntimeBackupDescription: 'Manage Docker local runtime backup options, latest backup status, and host-side backup controls.',
  localRuntimeBackupDeviceNode: 'Device Node',
  localRuntimeBackupFileSnapshot: 'File snapshot',
  localRuntimeBackupFree: 'Free',
  localRuntimeBackupGoogleDriveMyDrive: 'My Drive',
  localRuntimeBackupGoogleDrivePrepared: 'Google Drive folders prepared',
  localRuntimeBackupGoogleDriveRecommendedMirror: 'Recommended backup mirror',
  localRuntimeBackupGoogleDriveRecommendedResource: 'Recommended resource collaboration root',
  localRuntimeBackupGoogleDriveResourceRoot: 'Resource collaboration root',
  localRuntimeBackupGoogleDriveResourceSync: 'Resource collaboration',
  localRuntimeBackupGoogleDriveResourceSyncHelp: 'Create a Drive-backed folder for resource manifests, indexes, incoming bundles, and outgoing bundles.',
  localRuntimeBackupGoogleDriveSafetyNote: 'Do not sync whole data disks, live runtime databases, dependency folders, model caches, or temporary workspaces through Google Drive.',
  localRuntimeBackupGoogleDriveSync: 'Google Drive Sync',
  localRuntimeBackupGoogleDriveSyncHelp: 'Use the local Google Drive mount for verified backup copies and small resource collaboration folders.',
  localRuntimeBackupGoogleDriveUnavailable: 'Google Drive for desktop is not mounted on this host.',
  localRuntimeBackupApplyGoogleDrive: 'Use Google Drive paths',
  localRuntimeBackupIncrementalCard: 'Incremental Runtime Backup',
  localRuntimeBackupIncrementalMode: 'Incremental runtime backup',
  localRuntimeBackupMirrorRoot: 'Mirror Root',
  localRuntimeBackupMirrorRootHelp: 'Verified second copy target',
  localRuntimeBackupMirrorScopeAuthState: 'Auth state',
  localRuntimeBackupMirrorScopeAuthStateHelp: 'Device key and browser profile state needed to resume local sessions.',
  localRuntimeBackupMirrorScopeBlobStorage: 'Blob storage',
  localRuntimeBackupMirrorScopeBlobStorageHelp: 'Uploads, user documents, and pack storage blobs. Disabled by default.',
  localRuntimeBackupMirrorScopeModelCache: 'Model cache',
  localRuntimeBackupMirrorScopeModelCacheHelp: 'Local model files under the runtime secrets volume. Disabled by default.',
  localRuntimeBackupMirrorScopePostgresChain: 'PostgreSQL chain',
  localRuntimeBackupMirrorScopePostgresChainHelp: 'Always mirror base backups, WAL archive, and backup metadata.',
  localRuntimeBackupMirrorScopeRuntimeMetadata: 'Runtime metadata',
  localRuntimeBackupMirrorScopeRuntimeMetadataHelp: 'Runtime contracts, object catalog, workspace metadata, and compatibility state.',
  localRuntimeBackupMirrorScopeWorkspaceArtifacts: 'Workspace artifacts',
  localRuntimeBackupMirrorScopeWorkspaceArtifactsHelp: 'Generated workspace outputs and sandbox artifacts. Disabled by default.',
  localRuntimeBackupMirrorScopes: 'Mirror Scopes',
  localRuntimeBackupMirrorScopesHelp: 'Choose which app-data scopes are copied to the mirror.',
  localRuntimeBackupMirrorStatus: 'Mirror Status',
  localRuntimeBackupMode: 'Mode',
  localRuntimeBackupPolicy: 'Backup Policy',
  localRuntimeBackupPrepareGoogleDrive: 'Prepare folders',
  localRuntimeBackupPrimaryRoot: 'Primary Root',
  localRuntimeBackupPrimaryRootHelp: 'Incremental runtime backup target',
  localRuntimeBackupRequireMirror: 'Require Mirror',
  localRuntimeBackupRequireMirrorHelp: 'Block backup when mirror is unavailable',
  localRuntimeBackupWalArchive: 'WAL archive',
  localRuntimeBackupWalReady: 'ready',
  name: 'Name',
  none: 'None',
  notConfigured: 'Not Configured',
  path: 'Path',
  profileState: 'Profile State',
  refresh: 'Refresh',
  save: 'Save',
  saving: 'Saving',
  size: 'Size',
  startBackup: 'Start Incremental Backup',
  startedAt: 'Started At',
  starting: 'Starting...',
  status: 'Status',
  statusUnavailable: 'Unavailable',
  valid: 'Valid',
  verifyLatestBackup: 'Verify Latest Backup',
  verifying: 'Verifying...',
}));

vi.mock('../../../../lib/i18n', () => ({
  t: (key: string) => translations[key] || key,
}));

vi.mock('../../utils/settingsApi', () => ({
  settingsApi: apiMock,
}));

vi.mock('../../hooks/useSettingsNotification', () => ({
  showNotification: vi.fn(),
}));

const backupStatus = {
  config: {
    backup_root: '/primary/backups',
    mirror_root: '/mirror/backups',
    retention_local_count: 7,
    retention_mirror_count: 3,
    min_free_gb: 20,
    require_mirror: true,
    base_interval_hours: 168,
    mirror_scopes: ['postgres_chain', 'runtime_metadata', 'auth_state'],
    google_drive_resource_sync_enabled: false,
    google_drive_resource_root: '',
  },
  backup_root: '/primary/backups',
  policy: {
    mode: 'incremental_runtime_backup',
    primary_root: '/primary/backups',
    mirror_root: '/mirror/backups',
    retention_local_count: 7,
    retention_mirror_count: 3,
    min_free_gb: 20,
    require_mirror: true,
    base_interval_hours: 168,
    mirror_scopes: ['postgres_chain', 'runtime_metadata', 'auth_state'],
    wal_archive_root: '/primary/backups/postgres-wal-archive',
  },
  primary_free_bytes: 214748364800,
  mirror_free_bytes: 107374182400,
  postgres_archive_mode: 'on',
  postgres_wal_ready_count: 0,
  postgres_wal_bytes: 536870912,
  wal_archive_dir: '/primary/backups/postgres-wal-archive',
  wal_segment_count: 2,
  wal_archive_bytes: 1048576,
  base_backup_id: 'base_20260520T000000Z',
  base_backup_created_at: '2026-05-20T00:00:00Z',
  base_backup_age_hours: 1,
  base_backup_required: false,
  latest_file_snapshot_id: 'snapshot_20260520T010000Z',
  can_run: true,
  blocking_reasons: [],
  script_available: true,
  verify_script_available: true,
  host_project_root: '/repo',
  device_node_available: true,
  latest_backup: null,
  latest_job: null,
  google_drive_sync: {
    available: true,
    account_label: 'hans@anafter.co',
    mount_path: '/Users/shock/Library/CloudStorage/GoogleDrive-hans@anafter.co',
    my_drive_path: '/Users/shock/Library/CloudStorage/GoogleDrive-hans@anafter.co/我的雲端硬碟',
    recommended_mirror_root: '/Users/shock/Library/CloudStorage/GoogleDrive-hans@anafter.co/我的雲端硬碟/Mindscape/local-core-runtime-backups',
    recommended_resource_root: '/Users/shock/Library/CloudStorage/GoogleDrive-hans@anafter.co/我的雲端硬碟/Mindscape/local-core-resource-collaboration',
    recommended_mirror_scopes: ['postgres_chain', 'runtime_metadata', 'auth_state'],
    mirror_root_active: false,
    resource_sync_enabled: false,
    resource_root: '',
    warnings: [],
  },
  commands: {
    create: 'python3 scripts/local_runtime_backup_job.py start',
    dry_run: 'python3 scripts/local_runtime_backup_job.py plan',
    verify_latest: 'scripts/verify_local_runtime_backup.sh <backup-dir>',
  },
  warnings: [],
};

describe('RuntimeBackupSettings', () => {
  beforeEach(() => {
    apiMock.get.mockReset();
    apiMock.put.mockReset();
    apiMock.post.mockReset();
    apiMock.get.mockResolvedValue(backupStatus);
    apiMock.post.mockResolvedValue({ success: true, stdout: '{"can_run": true}' });
  });

  it('renders the incremental runtime backup policy and WAL archive state', async () => {
    render(<RuntimeBackupSettings />);

    await waitFor(() => {
      expect(screen.getByText('Backup Policy')).toBeInTheDocument();
    });

    expect(screen.getByText('Incremental Runtime Backup')).toBeInTheDocument();
    expect(screen.getByText((_content, element) => element?.textContent === 'Mode: Incremental runtime backup')).toBeInTheDocument();
    expect(screen.getByText(/WAL archive: on; ready: 0/)).toBeInTheDocument();
    expect(screen.getByDisplayValue('/primary/backups')).toBeInTheDocument();
    expect(screen.getByDisplayValue('/mirror/backups')).toBeInTheDocument();
    expect(screen.getByDisplayValue('168')).toBeInTheDocument();
    expect(screen.getByText('Mirror Scopes')).toBeInTheDocument();
    expect(screen.getByText('Google Drive Sync')).toBeInTheDocument();
    expect(screen.getByText('Use Google Drive paths')).toBeInTheDocument();
    expect(screen.getByLabelText(/Blob storage/)).not.toBeChecked();
    expect(screen.getByLabelText(/Model cache/)).not.toBeChecked();
    expect(screen.getByLabelText(/Workspace artifacts/)).not.toBeChecked();
    expect(screen.getByText('Start Incremental Backup')).toBeInTheDocument();
    expect(screen.queryByText('Include service logs')).not.toBeInTheDocument();
  });

  it('starts backups with the configured primary and mirror roots', async () => {
    render(<RuntimeBackupSettings />);

    await waitFor(() => {
      expect(screen.getByText('Start Incremental Backup')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Start Incremental Backup'));

    await waitFor(() => {
      expect(apiMock.post).toHaveBeenCalledWith(
        '/api/v1/system-settings/backups/local-runtime/start',
        expect.objectContaining({
          backup_root: '/primary/backups',
          mirror_root: '/mirror/backups',
          require_mirror: true,
          base_interval_hours: 168,
          mirror_scopes: ['postgres_chain', 'runtime_metadata', 'auth_state'],
        }),
      );
    });
  });

  it('applies the detected Google Drive mirror and collaboration roots', async () => {
    render(<RuntimeBackupSettings />);

    await waitFor(() => {
      expect(screen.getByText('Use Google Drive paths')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Use Google Drive paths'));

    expect(screen.getByDisplayValue('/Users/shock/Library/CloudStorage/GoogleDrive-hans@anafter.co/我的雲端硬碟/Mindscape/local-core-runtime-backups')).toBeInTheDocument();
    expect(screen.getByDisplayValue('/Users/shock/Library/CloudStorage/GoogleDrive-hans@anafter.co/我的雲端硬碟/Mindscape/local-core-resource-collaboration')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /Resource collaboration/ })).toBeChecked();
  });

  it('arms a single 30 second status poll only while a backup job is running', async () => {
    const setIntervalSpy = vi.spyOn(window, 'setInterval');
    const clearIntervalSpy = vi.spyOn(window, 'clearInterval');
    apiMock.get.mockResolvedValue({
      ...backupStatus,
      latest_job: {
        job_id: 'backup-job-running',
        state: 'running',
        started_at: '2026-05-20T00:00:00Z',
      },
    });

    const { unmount } = render(<RuntimeBackupSettings />);

    await waitFor(() => {
      expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), 30000);
    });
    const pollingCallIndex = setIntervalSpy.mock.calls.findIndex((call) => call[1] === 30000);
    const pollingCalls = setIntervalSpy.mock.calls.filter((call) => call[1] === 30000);
    expect(pollingCalls).toHaveLength(1);

    unmount();

    expect(clearIntervalSpy).toHaveBeenCalledWith(setIntervalSpy.mock.results[pollingCallIndex].value);
    setIntervalSpy.mockRestore();
    clearIntervalSpy.mockRestore();
  });
});
