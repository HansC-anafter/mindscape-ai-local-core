import { normalizeBrowserReachableUrl } from './api-origin';

function normalizeBase(baseUrl: string | undefined): string {
  return (normalizeBrowserReachableUrl(baseUrl) || '').replace(/\/$/, '');
}

export function resolveApiUrl(baseUrl: string | undefined, path: string): string {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }

  const normalizedBase = normalizeBase(baseUrl);
  if (!normalizedBase) {
    return path.startsWith('/') ? path : `/${path}`;
  }

  return path.startsWith('/') ? `${normalizedBase}${path}` : `${normalizedBase}/${path}`;
}

export function getApiFallbackBases(preferredBase?: string): string[] {
  const bases: string[] = [];
  const configuredBase = normalizeBase(process.env.NEXT_PUBLIC_API_URL);
  const preferred = normalizeBase(preferredBase);

  const pushBase = (value: string) => {
    if (!bases.includes(value)) {
      bases.push(value);
    }
  };

  if (preferred) pushBase(preferred);
  if (configuredBase) pushBase(configuredBase);
  pushBase('');

  return bases;
}

export async function fetchWithApiFallback(
  path: string,
  init?: RequestInit,
  preferredBase?: string,
): Promise<Response> {
  const bases = getApiFallbackBases(preferredBase);
  let lastResponse: Response | null = null;
  let lastError: unknown = null;

  for (const base of bases) {
    try {
      const response = await fetch(resolveApiUrl(base, path), init);
      if (response.ok || response.status < 500) {
        return response;
      }
      lastResponse = response;
    } catch (error) {
      lastError = error;
    }
  }

  if (lastResponse) {
    return lastResponse;
  }

  if (lastError instanceof Error) {
    throw lastError;
  }

  throw new Error('api_fetch_failed');
}
