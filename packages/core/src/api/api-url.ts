import { getServiceEndpointUrl } from './service-endpoints';

function getRuntimeEnv(name: string): string | undefined {
  const runtimeGlobal = globalThis as typeof globalThis & {
    process?: { env?: Record<string, string | undefined> };
  };
  return runtimeGlobal.process?.env?.[name];
}

/**
 * Get initial API URL (synchronous version, for initialization)
 */
export function getApiBaseUrl(): string {
  if (typeof window !== 'undefined') {
    return getServiceEndpointUrl('local_core.control_api', 'browser_public');
  }

  return (
    getServiceEndpointUrl('local_core.control_api', 'server_internal') ||
    getRuntimeEnv('WEB_CONSOLE_BACKEND_URL') ||
    getRuntimeEnv('BACKEND_URL') ||
    getRuntimeEnv('NEXT_PUBLIC_BACKEND_URL') ||
    ''
  );
}

/**
 * Get dynamic API URL (async version, supports getting from port configuration service)
 * This function will try to get the latest URL from port configuration service,
 * falling back to initial URL if it fails
 */
export async function getApiUrl(): Promise<string> {
  return getApiBaseUrl();
}
