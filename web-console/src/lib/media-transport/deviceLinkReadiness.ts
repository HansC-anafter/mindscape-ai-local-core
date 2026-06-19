export type DeviceLinkReadinessState = 'ready' | 'blocked';

export type DeviceLinkReadiness = {
  state: DeviceLinkReadinessState;
  origin: string;
  message: string;
  qrReady: boolean;
};

const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '::1', '0.0.0.0']);

function normalizeOrigin(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, '');
  if (!trimmed) {
    return '';
  }
  try {
    return new URL(trimmed).origin;
  } catch {
    return trimmed;
  }
}

export function isLoopbackDeviceLinkHost(hostname: string): boolean {
  return LOOPBACK_HOSTS.has(hostname.toLowerCase());
}

function isLanLikeDeviceLinkHost(hostname: string): boolean {
  const normalized = hostname.toLowerCase();
  if (normalized.endsWith('.local') || normalized.endsWith('.lan')) {
    return true;
  }
  const octets = normalized.split('.').map((part) => Number(part));
  if (octets.length !== 4 || octets.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) {
    return false;
  }
  const first = octets[0] ?? -1;
  const second = octets[1] ?? -1;
  return first === 10
    || (first === 172 && second >= 16 && second <= 31)
    || (first === 192 && second === 168)
    || (first === 169 && second === 254);
}

function isLoopbackOrigin(origin: string): boolean {
  try {
    const parsed = new URL(origin);
    return isLoopbackDeviceLinkHost(parsed.hostname);
  } catch {
    return false;
  }
}

export function assessDeviceLinkOriginReadiness(origin: string): DeviceLinkReadiness {
  const normalizedOrigin = normalizeOrigin(origin);
  if (!normalizedOrigin) {
    return {
      state: 'blocked',
      origin: '',
      message: 'Phone capture requires a configured HTTPS origin.',
      qrReady: false,
    };
  }
  let parsed: URL;
  try {
    parsed = new URL(normalizedOrigin);
  } catch {
    return {
      state: 'blocked',
      origin: normalizedOrigin,
      message: 'Phone origin must be a valid URL.',
      qrReady: false,
    };
  }
  if (parsed.protocol !== 'https:') {
    return {
      state: 'blocked',
      origin: normalizedOrigin,
      message: 'Phone camera capture requires HTTPS.',
      qrReady: false,
    };
  }
  if (isLoopbackDeviceLinkHost(parsed.hostname)) {
    return {
      state: 'blocked',
      origin: normalizedOrigin,
      message: 'localhost is not reachable from the phone.',
      qrReady: false,
    };
  }
  const readyMessage = isLanLikeDeviceLinkHost(parsed.hostname)
    ? 'Ready for a phone on the same LAN with trusted HTTPS.'
    : 'Ready for remote phone capture over HTTPS.';
  return {
    state: 'ready',
    origin: normalizedOrigin,
    message: readyMessage,
    qrReady: true,
  };
}

export function resolveDeviceLinkPublicOrigin({
  overrideOrigin,
  fallbackOrigin,
  allowFallbackLoopbackOnly = false,
  allowFallbackHttpsOrigin = false,
}: {
  overrideOrigin: string;
  fallbackOrigin: string;
  allowFallbackLoopbackOnly?: boolean;
  allowFallbackHttpsOrigin?: boolean;
}): string {
  const normalizedOverrideOrigin = normalizeOrigin(overrideOrigin);
  if (normalizedOverrideOrigin) {
    return normalizedOverrideOrigin;
  }
  const normalizedFallbackOrigin = normalizeOrigin(fallbackOrigin);
  if (!normalizedFallbackOrigin) {
    return '';
  }
  if (allowFallbackLoopbackOnly && !isLoopbackOrigin(normalizedFallbackOrigin)) {
    if (!allowFallbackHttpsOrigin) {
      return '';
    }
    try {
      const parsed = new URL(normalizedFallbackOrigin);
      if (parsed.protocol !== 'https:') {
        return '';
      }
    } catch {
      return '';
    }
  }
  return normalizedFallbackOrigin;
}
