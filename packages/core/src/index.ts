/**
 * @mindscape-ai/core - Core utilities for Mindscape AI
 *
 * This package provides:
 * - API utilities (getApiBaseUrl, getApiUrl)
 * - Context hooks (useWorkspaceData, useWorkspaceDataOptional)
 *
 * Note: This package does NOT include capability pack components.
 * Capability packs should import shared components directly from their own paths.
 */

// API utilities
export {
  clearServiceEndpointSnapshotCache,
  getApiBaseUrl,
  getApiUrl,
  getServiceEndpointSnapshot,
  getServiceEndpointUrl,
} from './api';
export type {
  EndpointAudience,
  ServiceEndpoint,
  ServiceEndpointSnapshot,
} from './api';

// Context hooks
export {
  WorkspaceDataProvider,
  useWorkspaceData,
  useWorkspaceDataOptional
} from './contexts';
