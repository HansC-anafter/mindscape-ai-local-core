/**
 * Playbook Loader - Dynamic loader for playbook packages
 *
 * Automatically discovers and loads playbook packages from node_modules/@mindscape/playbook-*
 * This is a frontend TypeScript implementation for browser environment.
 *
 * Note: Full dynamic loading requires build-time or runtime module resolution.
 * For Next.js, we use dynamic imports at build time.
 */

import { PlaybookRegistry, PlaybookPackage } from './registry';

interface PlaybookPackageInfo {
  name: string;
  version: string;
  playbookCode?: string;
  registerFunction?: string;
}

/**
 * Load installed playbooks into registry
 *
 * In browser environment, we need to know which playbooks are installed
 * at build time. This function should be called during app initialization.
 *
 * For development, playbooks can be manually registered.
 * For production, playbooks are discovered from package.json dependencies.
 */
export async function loadInstalledPlaybooks(
  registry: PlaybookRegistry
): Promise<void> {
  const installedPlaybooks = await discoverInstalledPlaybooks();

  for (const playbookInfo of installedPlaybooks) {
    try {
      await loadPlaybookPackage(playbookInfo, registry);
    } catch (error) {
      console.error(
        `Failed to load playbook ${playbookInfo.name}:`,
        error
      );
    }
  }
}

/**
 * Discover installed playbook packages
 *
 * In browser environment, we check package.json dependencies
 * or use a manifest file generated at build time.
 */
async function discoverInstalledPlaybooks(): Promise<PlaybookPackageInfo[]> {
  const playbooks: PlaybookPackageInfo[] = [];

  try {
    const manifest = await fetch('/api/v1/playbooks/manifest');
    if (manifest.ok) {
      const data = await manifest.json();
      return data.playbooks || [];
    }
  } catch (error) {
    console.warn('Failed to fetch playbook manifest, using empty list');
  }

  return playbooks;
}

/**
 * Load a playbook package dynamically
 */
async function loadPlaybookPackage(
  playbookInfo: PlaybookPackageInfo,
  registry: PlaybookRegistry
): Promise<void> {
  try {
    const module = await import(playbookInfo.name);

    let registerFunction: ((registry: PlaybookRegistry) => void) | null = null;

    if (playbookInfo.registerFunction) {
      registerFunction = module[playbookInfo.registerFunction];
    } else {
      registerFunction = findRegisterFunction(module);
    }

    if (registerFunction) {
      registerFunction(registry);
      console.log(
        `Loaded playbook: ${playbookInfo.name}@${playbookInfo.version}`
      );
    } else {
      console.warn(
        `No register function found in ${playbookInfo.name}`
      );
    }
  } catch (error) {
    console.error(`Failed to import playbook ${playbookInfo.name}:`, error);
    throw error;
  }
}

/**
 * Find register function in module
 */
function findRegisterFunction(module: any): ((registry: PlaybookRegistry) => void) | null {
  for (const key in module) {
    if (key.startsWith('register') && key.endsWith('Playbook')) {
      const func = module[key];
      if (typeof func === 'function') {
        return func;
      }
    }
  }

  if (module.default && typeof module.default === 'function') {
    return module.default;
  }

  if (module.register && typeof module.register === 'function') {
    return module.register;
  }

  return null;
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

