/**
 * Playbook API Loader - Load playbooks via API instead of dynamic imports
 *
 * This replaces the dynamic import mechanism to avoid webpack warnings.
 * Playbooks are loaded through API endpoints, and UI components are loaded
 * using React dynamic rendering (similar to capability-ui-loader).
 *
 * Architecture:
 * 1. Fetch playbook metadata from API (/api/v1/playbooks/manifest)
 * 2. Register playbook metadata to registry (no dynamic import needed)
 * 3. Load UI components via API if needed (similar to capability components)
 */

import { PlaybookRegistry, PlaybookPackage } from './registry';

interface PlaybookPackageInfo {
  name: string;
  version: string;
  playbookCode?: string;
  registerFunction?: string;
}

interface PlaybookMetadata {
  playbook_code: string;
  name: string;
  description: string;
  version: string;
  locale: string;
  tags: string[];
  icon?: string;
  entry_agent_type?: string;
  onboarding_task?: string;
  required_tools: string[];
  kind?: string;
  scope?: 'system' | 'tenant' | 'profile' | 'workspace';
  capability_code?: string;
  has_personal_variant?: boolean;
  default_variant_name?: string;
}

/**
 * Load playbook metadata from API and register to registry
 *
 * This replaces the dynamic import mechanism. Instead of importing NPM packages,
 * we fetch playbook metadata from the backend API and register it directly.
 *
 * This approach:
 * 1. Fetches playbook manifest (list of installed playbooks)
 * 2. Registers playbooks directly from manifest data
 * 3. Avoids dynamic imports that cause webpack warnings
 * 4. UI components are loaded separately via API when needed
 */
export async function loadInstalledPlaybooksFromAPI(
  registry: PlaybookRegistry,
  apiUrl: string = ''
): Promise<void> {
  try {
    // Fetch playbook manifest from API
    const manifestUrl = apiUrl
      ? `${apiUrl}/api/v1/playbooks/manifest`
      : '/api/v1/playbooks/manifest';

    const response = await fetch(manifestUrl);
    if (!response.ok) {
      console.warn('Failed to fetch playbook manifest from API');
      return;
    }

    const data = await response.json();
    const playbookInfos: PlaybookPackageInfo[] = data.playbooks || [];

    // Register each playbook directly from manifest
    // No need to fetch individual playbook metadata - we'll fetch it when needed
    for (const playbookInfo of playbookInfos) {
      try {
        await registerPlaybookFromManifest(playbookInfo, registry);
      } catch (error) {
        console.error(
          `Failed to register playbook ${playbookInfo.name}:`,
          error
        );
      }
    }
  } catch (error) {
    console.error('Failed to load playbooks from API:', error);
  }
}

/**
 * Register a playbook from manifest data
 *
 * Instead of dynamically importing the NPM package, we:
 * 1. Use manifest data to create PlaybookPackage
 * 2. Register it to the registry
 * 3. UI layout and components will be loaded separately via API when needed
 *
 * This avoids webpack warnings about dynamic dependencies.
 */
async function registerPlaybookFromManifest(
  playbookInfo: PlaybookPackageInfo,
  registry: PlaybookRegistry
): Promise<void> {
  const playbookCode = playbookInfo.playbookCode ||
    playbookInfo.name.replace('@mindscape/playbook-', '').replace(/^playbook-/, '');

  if (!playbookCode) {
    console.warn(`Cannot determine playbook code for ${playbookInfo.name}`);
    return;
  }

  // Create PlaybookPackage with manifest data
  // UI layout and components will be loaded separately when needed via API
  const playbookPackage: PlaybookPackage = {
    playbookCode: playbookCode,
    version: playbookInfo.version,
    playbookSpec: {
      version: playbookInfo.version,
      playbook_code: playbookCode,
      kind: 'system', // Default, can be updated when fetching full metadata
    },
    // UI layout will be loaded separately if playbook has UI components
    // This avoids the need for dynamic import
    uiLayout: undefined,
    components: undefined,
  };

  // Register to registry
  registry.register(playbookPackage);

  console.log(
    `Registered playbook from API manifest: ${playbookCode}@${playbookInfo.version}`
  );
}

/**
 * Load playbook UI layout from API if available
 *
 * Similar to capability UI components, playbook UI layouts can be loaded
 * via API when needed, avoiding dynamic imports.
 */
export async function loadPlaybookUILayout(
  playbookCode: string,
  apiUrl: string = ''
): Promise<any> {
  try {
    const layoutUrl = apiUrl
      ? `${apiUrl}/api/v1/playbooks/${playbookCode}/ui-layout`
      : `/api/v1/playbooks/${playbookCode}/ui-layout`;

    const response = await fetch(layoutUrl);
    if (!response.ok) {
      // UI layout not available, return undefined
      return undefined;
    }

    const layout = await response.json();
    return layout;
  } catch (error) {
    console.warn(`Failed to load UI layout for playbook ${playbookCode}:`, error);
    return undefined;
  }
}

