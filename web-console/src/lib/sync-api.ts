/**
 * Cloud Sync API Client
 * Provides API functions for cloud sync operations
 */

const API_URL = typeof window !== 'undefined'
  ? (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000')
  : 'http://localhost:8000';

// Helper function to create fetch with timeout
async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs: number = 5000
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    return response;
  } catch (error) {
    clearTimeout(timeoutId);
    throw error;
  }
}

export interface SyncStatus {
  configured: boolean;
  online: boolean;
  pending_changes: number;
}

export interface VersionCheckRequest {
  client_version: string;
  capabilities: Array<{ code: string; version: string }>;
  assets: Array<{ uri: string; version: string; cached_at?: string }>;
  license_id?: string;
  device_id?: string;
}

export interface ClientUpdateInfo {
  available: boolean;
  current: string;
  latest: string;
  priority: 'required' | 'recommended' | 'optional';
  download_url?: string;
  changelog?: string;
}

export interface CapabilityUpdateInfo {
  code: string;
  current: string;
  latest: string;
  priority: 'required' | 'recommended' | 'optional';
  changelog?: string;
  affected_assets: string[];
}

export interface AssetUpdateInfo {
  uri: string;
  current: string;
  latest: string;
  priority: 'required' | 'recommended' | 'optional';
  size_bytes?: number;
}

export interface LicenseInfo {
  status: 'active' | 'expired' | 'grace_period';
  expires_at?: string;
  features: string[];
  quota: {
    brands_limit?: number;
    brands_used?: number;
  };
}

export interface VersionCheckResponse {
  server_time: string;
  client_update: ClientUpdateInfo;
  capability_updates: CapabilityUpdateInfo[];
  asset_updates: AssetUpdateInfo[];
  license: LicenseInfo;
}

export interface PendingChange {
  change_id: string;
  created_at: string;
  type: string;
  instance_type?: string;
  instance_id?: string;
  synced: boolean;
}

export interface ChangeSummary {
  total_changes: number;
  affected_instances: number;
  instances_with_changes: Array<{
    instance_type: string;
    instance_id: string;
    change_count: number;
  }>;
}

/**
 * Get sync status
 */
export async function getSyncStatus(): Promise<SyncStatus> {
  const response = await fetchWithTimeout(
    `${API_URL}/api/v1/cloud-sync/status`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    },
    5000 // 5 second timeout
  );

  if (!response.ok) {
    throw new Error(`Failed to get sync status: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Check for version updates
 */
export async function checkVersions(request: VersionCheckRequest): Promise<VersionCheckResponse> {
  const response = await fetchWithTimeout(
    `${API_URL}/api/v1/cloud-sync/versions/check`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    },
    5000 // 5 second timeout
  );

  if (!response.ok) {
    throw new Error(`Failed to check versions: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Sync pending changes
 */
export async function syncPendingChanges(): Promise<{
  total_changes: number;
  synced: number;
  failed: number;
  conflicts: number;
}> {
  const response = await fetchWithTimeout(
    `${API_URL}/api/v1/cloud-sync/sync/pending`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    },
    10000 // 10 second timeout for sync operations
  );

  if (!response.ok) {
    throw new Error(`Failed to sync pending changes: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get pending changes
 */
export async function getPendingChanges(): Promise<PendingChange[]> {
  const response = await fetchWithTimeout(
    `${API_URL}/api/v1/cloud-sync/changes/pending`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    },
    5000 // 5 second timeout
  );

  if (!response.ok) {
    throw new Error(`Failed to get pending changes: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get change summary
 */
export async function getChangeSummary(): Promise<ChangeSummary> {
  const response = await fetchWithTimeout(
    `${API_URL}/api/v1/cloud-sync/changes/summary`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    },
    5000 // 5 second timeout
  );

  if (!response.ok) {
    throw new Error(`Failed to get change summary: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Cleanup expired cache
 */
export async function cleanupCache(): Promise<{ cleared: number }> {
  const response = await fetchWithTimeout(
    `${API_URL}/api/v1/cloud-sync/cache/cleanup`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    },
    10000 // 10 second timeout
  );

  if (!response.ok) {
    throw new Error(`Failed to cleanup cache: ${response.statusText}`);
  }

  return response.json();
}

