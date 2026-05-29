import { shouldUseSameOriginProxyForBrowser } from './api-origin';
import { getServiceEndpointUrl } from '../../../packages/core/src/api';

function getRuntimeEnv(name: string): string | undefined {
  const runtimeGlobal = globalThis as typeof globalThis & {
    process?: { env?: Record<string, string | undefined> };
  };
  return runtimeGlobal.process?.env?.[name];
}

export function getApiBaseUrl(): string {
  const configuredUrl = getRuntimeEnv('NEXT_PUBLIC_API_URL');

  if (typeof window !== 'undefined') {
    if (shouldUseSameOriginProxyForBrowser(configuredUrl)) {
      return '';
    }
    return configuredUrl as string;
  }

  if (configuredUrl && configuredUrl.startsWith('http')) {
    return configuredUrl;
  }

  return (
    getServiceEndpointUrl('local_core.control_api', 'server_internal') ||
    getRuntimeEnv('WEB_CONSOLE_BACKEND_URL') ||
    getRuntimeEnv('BACKEND_URL') ||
    ''
  );
}

export async function getApiUrl(): Promise<string> {
  try {
    const settingsApiModule = await import('../app/settings/utils/settingsApi') as any;
    const getDynamicApiUrl = settingsApiModule.getApiUrl;
    return await getDynamicApiUrl();
  } catch {
    return getApiBaseUrl();
  }
}
