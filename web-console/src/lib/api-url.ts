import { shouldUseSameOriginProxyForBrowser } from './api-origin';

export function getApiBaseUrl(): string {
  const configuredUrl = process.env.NEXT_PUBLIC_API_URL;

  if (typeof window !== 'undefined') {
    if (shouldUseSameOriginProxyForBrowser(configuredUrl)) {
      return '';
    }
    return configuredUrl as string;
  }

  if (configuredUrl && configuredUrl.startsWith('http')) {
    return configuredUrl;
  }

  return 'http://localhost:8220';
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
