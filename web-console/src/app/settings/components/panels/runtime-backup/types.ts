export interface BackupConfig {
  backup_root: string;
  mirror_root: string;
  retention_local_count: number;
  retention_mirror_count: number;
  min_free_gb: number;
  require_mirror: boolean;
  base_interval_hours: number;
  mirror_scopes: string[];
  google_drive_resource_sync_enabled: boolean;
  google_drive_resource_root: string;
}

export interface BackupSummary {
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

export interface BackupJob {
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

export interface GoogleDriveSyncStatus {
  available: boolean;
  account_label: string;
  mount_path: string;
  my_drive_path: string;
  recommended_mirror_root: string;
  recommended_resource_root: string;
  recommended_mirror_scopes: string[];
  mirror_root_active: boolean;
  resource_sync_enabled: boolean;
  resource_root: string;
  warnings: string[];
}

export interface BackupStatus {
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
  google_drive_sync?: GoogleDriveSyncStatus;
  warnings: string[];
}

export const mirrorScopeOptions = [
  'postgres_chain',
  'runtime_metadata',
  'auth_state',
  'blob_storage',
  'model_cache',
  'workspace_artifacts',
] as const;

export type MirrorScope = (typeof mirrorScopeOptions)[number];

export type BackupAction = 'dry-run' | 'start' | 'verify';

export type BackupBusyAction = BackupAction | 'save' | 'prepare-google-drive' | null;

export type BackupConfigUpdate = <Key extends keyof BackupConfig>(
  key: Key,
  value: BackupConfig[Key]
) => void;
