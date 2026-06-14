export function buildApiUrls(apiUrl: string, path: string): string[] {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const normalizedApiUrl = apiUrl.replace(/\/$/, '');
  const primaryUrl = normalizedApiUrl ? `${normalizedApiUrl}${normalizedPath}` : normalizedPath;
  return primaryUrl === normalizedPath ? [normalizedPath] : [primaryUrl, normalizedPath];
}

export async function fetchApiJson(
  apiUrl: string,
  path: string,
  signal?: AbortSignal,
): Promise<unknown> {
  let lastError: unknown = null;
  for (const url of buildApiUrls(apiUrl, path)) {
    try {
      const response = await fetch(url, { credentials: 'same-origin', signal });
      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      lastError = error;
      if (signal?.aborted) {
        throw error;
      }
    }
  }

  throw lastError instanceof Error ? lastError : new Error('Request failed');
}

export async function postApiJson(
  apiUrl: string,
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<unknown> {
  let lastError: unknown = null;
  for (const url of buildApiUrls(apiUrl, path)) {
    try {
      const response = await fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal,
      });
      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      lastError = error;
      if (signal?.aborted) {
        throw error;
      }
    }
  }

  throw lastError instanceof Error ? lastError : new Error('Request failed');
}
