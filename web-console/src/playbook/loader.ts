import { PlaybookRegistry } from './registry';
import { loadInstalledPlaybooksFromAPI } from './api-loader';
import { getApiBaseUrl } from '../lib/api-url';

export async function loadInstalledPlaybooks(
  registry: PlaybookRegistry,
  _context?: any
): Promise<void> {
  const apiUrl = getApiBaseUrl();
  await loadInstalledPlaybooksFromAPI(registry, apiUrl);
}

let globalRegistry: PlaybookRegistry | null = null;

export function getPlaybookRegistry(): PlaybookRegistry {
  if (!globalRegistry) {
    globalRegistry = new PlaybookRegistry();
  }
  return globalRegistry;
}
