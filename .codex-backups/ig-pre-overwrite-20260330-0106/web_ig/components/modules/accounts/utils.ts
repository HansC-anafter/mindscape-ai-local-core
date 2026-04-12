export function parseCountTextToNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value !== 'string') return undefined;

  const raw = value.trim();
  if (!raw) return undefined;

  const normalized = raw.replace(/,/g, '');

  const match = normalized.match(/(\d+(?:\.\d+)?)(?:\s*([KMB]))?/i);
  if (!match) return undefined;

  const num = Number(match[1]);
  if (!Number.isFinite(num)) return undefined;

  const suffix = (match[2] || '').toUpperCase();
  if (suffix === 'K') return Math.round(num * 1_000);
  if (suffix === 'M') return Math.round(num * 1_000_000);
  if (suffix === 'B') return Math.round(num * 1_000_000_000);

  if (normalized.includes('億')) return Math.round(num * 100_000_000);
  if (normalized.includes('萬')) return Math.round(num * 10_000);

  return Math.round(num);
}

export function formatCount(value: number): string {
  try {
    return new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(value);
  } catch {
    return String(value);
  }
}

export function getProxiedImageUrl(apiUrl: string, rawUrl?: string): string | undefined {
  if (!rawUrl) return undefined;
  if (rawUrl.startsWith('data:') || rawUrl.startsWith('blob:')) return rawUrl;
  if (rawUrl.startsWith('/')) return rawUrl;
  try {
    const parsed = new URL(rawUrl);
    const host = (parsed.hostname || '').toLowerCase();
    if (
      host.endsWith('.fbcdn.net') ||
      host.endsWith('.cdninstagram.com') ||
      host === 'cdninstagram.com' ||
      host.endsWith('.instagram.com') ||
      host === 'instagram.com'
    ) {
      // Use media-proxy port directly (8202) to bypass Next.js rewrites which time out
      // In production, this should be configurable via env var
      const mediaProxyBase = typeof window !== 'undefined'
        ? `${window.location.protocol}//${window.location.hostname}:8202`
        : 'http://localhost:8202';
      return `${mediaProxyBase}/api/v1/media/image?url=${encodeURIComponent(rawUrl)}`;
    }
  } catch {
    // ignore
  }
  return rawUrl;
}

function getBrowserImageBase(apiUrl: string): string {
  if (apiUrl) {
    return apiUrl.replace(/\/$/, '');
  }
  if (typeof window !== 'undefined') {
    return window.location.origin;
  }
  return '';
}

export function getPostThumbnailUrl(apiUrl: string, shortcode: string): string {
    return `${getBrowserImageBase(apiUrl)}/api/v1/ig/post-thumbnail/${encodeURIComponent(shortcode)}`;
}

export function getReferenceImageUrl(apiUrl: string, workspaceId: string, referenceId: string): string {
  const base = getBrowserImageBase(apiUrl);
  const params = new URLSearchParams({ workspace_id: workspaceId });
  return `${base}/api/v1/ig/references/${encodeURIComponent(referenceId)}/image?${params.toString()}`;
}

/**
 * Get avatar URL for an Instagram username using the backend proxy.
 * Falls back to DiceBear avatar if no username provided.
 * Pass cacheBuster (e.g. fetched_at) to invalidate browser cache
 * when account data changes — no short TTL, no polling.
 */
export function getAvatarUrl(username?: string, cacheBuster?: string): string {
  if (!username) {
    return 'https://api.dicebear.com/7.x/initials/svg?seed=IG&backgroundColor=6366f1';
  }
  const base = getBrowserImageBase('');
  const suffix = cacheBuster ? `?t=${encodeURIComponent(cacheBuster)}` : '';
  return `${base}/api/v1/ig/avatar/${encodeURIComponent(username)}${suffix}`;
}
