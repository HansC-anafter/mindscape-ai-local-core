import { buildCloudProviderPayload, markInstalledPacks } from './formState';
import type {
  CloudProviderFormData,
  InstallDefaultPacksResult,
  Pack,
  Provider,
} from './types';

export const cloudPlaybookProviderSettingsEndpoints = {
  providers: () => '/api/v1/cloud-providers',
  provider: (providerId: string) => `/api/v1/cloud-providers/${providerId}`,
  providerTest: (providerId: string) => `/api/v1/cloud-providers/${providerId}/test`,
  providerPacks: (providerId: string) => `/api/v1/cloud-providers/${providerId}/packs`,
  installedCapabilityPacks: () => '/api/v1/capability-packs',
  installDefaultPacks: (providerId: string) => `/api/v1/cloud-providers/${providerId}/install-default?bundle=default`,
};

async function getErrorMessage(response: Response, fallback: string): Promise<string> {
  const error = await response.json().catch(() => null);
  return error?.detail || error?.message || fallback;
}

export async function loadCloudProviders(): Promise<Provider[]> {
  const response = await fetch(cloudPlaybookProviderSettingsEndpoints.providers());
  if (!response.ok) {
    throw new Error('Failed to load cloud providers');
  }
  return response.json();
}

export async function saveCloudProvider(
  formData: CloudProviderFormData,
  isEditing: boolean,
): Promise<void> {
  const url = isEditing
    ? cloudPlaybookProviderSettingsEndpoints.provider(formData.provider_id)
    : cloudPlaybookProviderSettingsEndpoints.providers();
  const method = isEditing ? 'PUT' : 'POST';

  const response = await fetch(url, {
    method,
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(buildCloudProviderPayload(formData)),
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(
      response,
      isEditing ? 'Failed to update provider' : 'Failed to create provider',
    ));
  }
}

export async function deleteCloudProvider(providerId: string): Promise<void> {
  const response = await fetch(cloudPlaybookProviderSettingsEndpoints.provider(providerId), {
    method: 'DELETE',
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to delete provider'));
  }
}

export async function testCloudProvider(providerId: string): Promise<{ success: boolean; message?: string }> {
  const response = await fetch(cloudPlaybookProviderSettingsEndpoints.providerTest(providerId), {
    method: 'POST',
  });
  return response.json();
}

export async function loadCloudProviderPacks(providerId: string): Promise<Pack[]> {
  const response = await fetch(cloudPlaybookProviderSettingsEndpoints.providerPacks(providerId));
  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to load packs'));
  }

  const data = await response.json();
  const packsList: Pack[] = data.packs || [];

  try {
    const installedResponse = await fetch(cloudPlaybookProviderSettingsEndpoints.installedCapabilityPacks(), {
      signal: AbortSignal.timeout(5000),
    });
    if (!installedResponse.ok) {
      return packsList;
    }

    const installedPacks = await installedResponse.json();
    return markInstalledPacks(packsList, installedPacks);
  } catch (error: any) {
    if (error.name !== 'AbortError') {
      console.debug('Failed to check installed packs (non-critical):', error.message);
    }
    return packsList;
  }
}

export async function installDefaultCloudProviderPacks(
  providerId: string,
): Promise<InstallDefaultPacksResult> {
  const response = await fetch(cloudPlaybookProviderSettingsEndpoints.installDefaultPacks(providerId), {
    method: 'POST',
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to install packs'));
  }

  return response.json();
}
