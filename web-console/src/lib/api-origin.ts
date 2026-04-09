function isLoopbackHostname(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1';
}

export function normalizeBrowserReachableUrl(configuredUrl?: string): string | undefined {
  if (!configuredUrl || !configuredUrl.startsWith('http')) {
    return configuredUrl;
  }

  try {
    const url = new URL(configuredUrl);
    const hostname = url.hostname.trim().toLowerCase();
    if (hostname === 'localhost' || hostname === '::1') {
      url.hostname = '127.0.0.1';
      return url.toString().replace(/\/$/, '');
    }
    return configuredUrl.replace(/\/$/, '');
  } catch {
    return configuredUrl;
  }
}

function isPrivateIpv4(hostname: string): boolean {
  if (!/^\d+\.\d+\.\d+\.\d+$/.test(hostname)) {
    return false;
  }

  const parts = hostname.split('.').map((part) => Number(part));
  if (parts.length !== 4 || parts.some((part) => Number.isNaN(part) || part < 0 || part > 255)) {
    return false;
  }

  const [a, b] = parts;
  if (a === 10) return true;
  if (a === 127) return true;
  if (a === 169 && b === 254) return true;
  if (a === 172 && b >= 16 && b <= 31) return true;
  if (a === 192 && b === 168) return true;
  if (a === 100 && b >= 64 && b <= 127) return true;
  return false;
}

function isBrowserInternalHostname(hostname: string): boolean {
  const normalized = hostname.trim().toLowerCase();
  if (!normalized) {
    return true;
  }

  if (isLoopbackHostname(normalized) || isPrivateIpv4(normalized)) {
    return true;
  }

  if (
    normalized === 'backend' ||
    normalized === 'host.docker.internal' ||
    normalized.endsWith('.internal') ||
    normalized.endsWith('.local') ||
    normalized.endsWith('.docker')
  ) {
    return true;
  }

  // Docker/K8s-style service names and other bare internal hosts are not browser-resolvable.
  return !normalized.includes('.');
}

export function shouldUseSameOriginProxyForBrowser(configuredUrl?: string): boolean {
  if (typeof window === 'undefined') {
    return false;
  }

  if (!configuredUrl || !configuredUrl.startsWith('http')) {
    return true;
  }

  try {
    const url = new URL(configuredUrl);
    const configuredHost = url.hostname.trim().toLowerCase();
    const browserHost = window.location.hostname.trim().toLowerCase();
    const configuredIsDirectBrowserHost =
      isLoopbackHostname(configuredHost) || isPrivateIpv4(configuredHost);
    const browserIsDirectBrowserHost =
      isLoopbackHostname(browserHost) || isPrivateIpv4(browserHost);

    // In local-core dev/runtime, NEXT_PUBLIC_API_URL typically points to a
    // browser-reachable backend URL such as localhost:8200. Sending those
    // requests through Next rewrites is less stable than hitting the backend
    // directly, and backend CORS already allows the frontend origin.
    if (configuredHost === browserHost) {
      return false;
    }

    if (configuredIsDirectBrowserHost && browserIsDirectBrowserHost) {
      return false;
    }

    return isBrowserInternalHostname(configuredHost);
  } catch {
    return true;
  }
}
