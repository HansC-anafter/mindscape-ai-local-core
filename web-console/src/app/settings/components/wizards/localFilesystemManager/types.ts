'use client';

export interface PlaybookStorageConfig {
  base_path?: string;
  artifacts_dir?: string;
}

export interface DirectoryConfig {
  path: string;
  allowWrite: boolean;
}

export interface ConfiguredDirectory {
  name: string;
  allowed_directories: string[];
  allow_write: boolean;
  enabled?: boolean;
  directory_configs?: Array<{ path: string; allow_write: boolean }>;
}

export interface CommonDirectory {
  label: string;
  path: string;
  platform: 'all' | 'windows';
}
