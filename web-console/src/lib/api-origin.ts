function isLoopbackHostname(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1';
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
    return url.hostname === window.location.hostname || isBrowserInternalHostname(url.hostname);
  } catch {
    return true;
  }
}
