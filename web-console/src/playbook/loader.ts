/**
 * Playbook Loader - API-based loader for playbook packages
 *
 * DEPRECATED: This file is kept for backward compatibility.
 * New implementation uses API-based loading (api-loader.ts) to avoid webpack warnings.
 *
 * This loader now delegates to the API-based loader instead of using dynamic imports.
 */

import { PlaybookRegistry } from './registry';
import { loadInstalledPlaybooksFromAPI } from './api-loader';
import { getApiBaseUrl } from '../lib/api-url';

/**
 * Load installed playbooks into registry
 *
 * This function now uses API-based loading instead of dynamic imports.
 * This avoids webpack warnings about dynamic dependencies.
 *
 * @param registry - PlaybookRegistry instance
 * @param context - ExecutionContext (optional, kept for backward compatibility)
 * @deprecated Use loadInstalledPlaybooksFromAPI directly for better control
 */
export async function loadInstalledPlaybooks(
  registry: PlaybookRegistry,
  context?: any
): Promise<void> {
  const apiUrl = getApiBaseUrl();
  await loadInstalledPlaybooksFromAPI(registry, apiUrl);
}

/**
 * Create a singleton registry instance
 */
let globalRegistry: PlaybookRegistry | null = null;

export function getPlaybookRegistry(): PlaybookRegistry {
  if (!globalRegistry) {
    globalRegistry = new PlaybookRegistry();
  }
  return globalRegistry;
}

