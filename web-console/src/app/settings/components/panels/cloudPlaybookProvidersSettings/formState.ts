import type {
  CloudProviderFormData,
  CloudProviderPayload,
  Pack,
  Provider,
} from './types';

export function createEmptyCloudProviderForm(): CloudProviderFormData {
  return {
    provider_id: '',
    provider_type: 'generic_http',
    enabled: true,
    config: {
      api_url: '',
      name: '',
      auth: {
        auth_type: 'bearer',
        token: '',
        api_key: '',
      },
    },
  };
}

export function buildCloudProviderFormFromProvider(provider: Provider): CloudProviderFormData {
  return {
    provider_id: provider.provider_id,
    provider_type: 'generic_http',
    enabled: provider.enabled,
    config: {
      api_url: provider.config.api_url || '',
      name: provider.config.name || provider.provider_id,
      auth: {
        auth_type: provider.config.auth?.auth_type || 'bearer',
        token: provider.config.auth?.token || '',
        api_key: provider.config.auth?.api_key || provider.config.license_key || '',
      },
    },
  };
}

export function buildCloudProviderPayload(formData: CloudProviderFormData): CloudProviderPayload {
  return {
    provider_id: formData.provider_id,
    provider_type: formData.provider_type,
    enabled: formData.enabled,
    config: {
      name: formData.config.name || formData.provider_id,
      api_url: formData.config.api_url,
      auth: {
        auth_type: formData.config.auth.auth_type,
        ...(formData.config.auth.auth_type === 'bearer' && { token: formData.config.auth.token }),
        ...(formData.config.auth.auth_type === 'api_key' && { api_key: formData.config.auth.api_key }),
      },
    },
  };
}

export function collectInstalledPackIds(installedPacks: Array<Record<string, any>>): Set<string> {
  return new Set(
    installedPacks
      .map((pack) => pack.id || pack.code)
      .filter(Boolean),
  );
}

export function getPackRefId(packRef?: string): string | null {
  return packRef?.split(':')[1]?.split('@')[0] || null;
}

export function markInstalledPacks(
  packsList: Pack[],
  installedPacks: Array<Record<string, any>>,
): Pack[] {
  const installedIds = collectInstalledPackIds(installedPacks);

  return packsList.map((pack) => {
    const packRefId = getPackRefId(pack.pack_ref);
    return {
      ...pack,
      installed: installedIds.has(pack.code) || installedIds.has(packRefId || ''),
    };
  });
}
