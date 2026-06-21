import type { CloudProviderFormData, Provider } from './types';

export function createEmptyCloudProviderForm(): CloudProviderFormData {
  return {
    provider_id: '',
    provider_type: 'generic_http',
    enabled: true,
    config: {
      api_url: '',
      license_key: '',
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
    provider_type: provider.provider_type as CloudProviderFormData['provider_type'],
    enabled: provider.enabled,
    config: {
      api_url: provider.config.api_url || '',
      license_key: provider.config.license_key || '',
      name: provider.config.name || provider.provider_id,
      auth: {
        auth_type: provider.config.auth?.auth_type || 'bearer',
        token: provider.config.auth?.token || '',
        api_key: provider.config.auth?.api_key || '',
      },
    },
  };
}

export function buildCloudProviderPayload(formData: CloudProviderFormData) {
  const payload: {
    provider_id: string;
    provider_type: string;
    enabled: boolean;
    config: Record<string, any>;
  } = {
    provider_id: formData.provider_id,
    provider_type: formData.provider_type,
    enabled: formData.enabled,
    config: {},
  };

  if (formData.provider_type === 'official') {
    payload.config = {
      api_url: formData.config.api_url,
      license_key: formData.config.license_key,
    };
  } else if (formData.provider_type === 'generic_http') {
    payload.config = {
      name: formData.config.name || formData.provider_id,
      api_url: formData.config.api_url,
      auth: {
        auth_type: formData.config.auth.auth_type,
        ...(formData.config.auth.auth_type === 'bearer' && { token: formData.config.auth.token }),
        ...(formData.config.auth.auth_type === 'api_key' && { api_key: formData.config.auth.api_key }),
      },
    };
  }

  return payload;
}
