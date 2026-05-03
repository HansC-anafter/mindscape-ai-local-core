import { PlaybookRegistry, PlaybookPackage } from './registry';

interface PlaybookPackageInfo {
  name: string;
  version: string;
  playbookCode?: string;
  registerFunction?: string;
}

export async function loadInstalledPlaybooksFromAPI(
  registry: PlaybookRegistry,
  apiUrl: string = ''
): Promise<void> {
  try {
    const manifestUrl = apiUrl
      ? `${apiUrl}/api/v1/playbooks/manifest`
      : '/api/v1/playbooks/manifest';

    const response = await fetch(manifestUrl);
    if (!response.ok) {
      return;
    }

    const data = await response.json();
    const playbookInfos: PlaybookPackageInfo[] = data.playbooks || [];

    for (const playbookInfo of playbookInfos) {
      try {
        await registerPlaybookFromManifest(playbookInfo, registry);
      } catch {
      }
    }
  } catch {
  }
}

async function registerPlaybookFromManifest(
  playbookInfo: PlaybookPackageInfo,
  registry: PlaybookRegistry
): Promise<void> {
  const playbookCode = playbookInfo.playbookCode ||
    playbookInfo.name.replace('@mindscape/playbook-', '').replace(/^playbook-/, '');

  if (!playbookCode) {
    return;
  }

  const playbookPackage: PlaybookPackage = {
    playbookCode: playbookCode,
    version: playbookInfo.version,
    playbookSpec: {
      version: playbookInfo.version,
      playbook_code: playbookCode,
      kind: 'system',
    },
    uiLayout: undefined,
    components: undefined,
  };

  registry.register(playbookPackage);
}

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
      return undefined;
    }

    const layout = await response.json();
    return layout;
  } catch {
    return undefined;
  }
}
