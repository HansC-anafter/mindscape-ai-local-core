import { buildCloudProviderPayload } from './formState';
import type {
  CloudProviderFormData,
  InstallDefaultPacksResult,
  Pack,
  Provider,
} from './types';

async function getErrorMessage(response: Response, fallback: string): Promise<string> {
  const error = await response.json().catch(() => null);
  return error?.detail || error?.message || fallback;
}

export async function loadCloudFrontendUrlSetting(): Promise<string> {
  const response = await fetch('/api/v1/system-settings/cloud_frontend_url');
  if (!response.ok) {
    return '';
  }
  const data = await response.json();
  return data.value || '';
}

export async function saveCloudFrontendUrlSetting(value: string): Promise<void> {
  const params = new URLSearchParams({
    value,
    category: 'cloud',
    description: 'Cloud frontend URL for navigation',
  });
  const response = await fetch(`/api/v1/system-settings/cloud_frontend_url?${params.toString()}`, {
    method: 'PUT',
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to save cloud frontend URL'));
  }
}

export async function loadCloudProviders(): Promise<Provider[]> {
  const response = await fetch('/api/v1/cloud-providers');
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
    ? `/api/v1/cloud-providers/${formData.provider_id}`
    : '/api/v1/cloud-providers';
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
  const response = await fetch(`/api/v1/cloud-providers/${providerId}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to delete provider'));
  }
}

export async function testCloudProvider(providerId: string): Promise<{ success: boolean; message?: string }> {
  const response = await fetch(`/api/v1/cloud-providers/${providerId}/test`, {
    method: 'POST',
  });
  return response.json();
}

export async function loadCloudProviderPacks(providerId: string): Promise<Pack[]> {
  const response = await fetch(`/api/v1/cloud-providers/${providerId}/packs`);
  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to load packs'));
  }

  const data = await response.json();
  const packsList: Pack[] = data.packs || [];

  try {
    const installedResponse = await fetch('/api/v1/capability-packs/', {
      signal: AbortSignal.timeout(5000),
    });
    if (!installedResponse.ok) {
      return packsList;
    }

    const installedPacks = await installedResponse.json();
    const installedIds = new Set(
      installedPacks
        .map((pack: any) => pack.id || pack.code)
        .filter(Boolean),
    );

    return packsList.map((pack) => {
      const packRefId = pack.pack_ref?.split(':')[1]?.split('@')[0];
      return {
        ...pack,
        installed: installedIds.has(pack.code) || installedIds.has(packRefId || ''),
      };
    });
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
  const response = await fetch(`/api/v1/cloud-providers/${providerId}/install-default?bundle=default`, {
    method: 'POST',
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Failed to install packs'));
  }

  return response.json();
}
