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

export function assessDeviceLinkOriginReadiness(origin: string): DeviceLinkReadiness {
  const normalizedOrigin = normalizeOrigin(origin);
  if (!normalizedOrigin) {
    return {
      state: 'blocked',
      origin: '',
      message: 'Phone capture requires a configured HTTPS LAN origin.',
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
  return {
    state: 'ready',
    origin: normalizedOrigin,
    message: 'Ready for a phone on the same LAN with trusted HTTPS.',
    qrReady: true,
  };
}

export function resolveDeviceLinkPublicOrigin({
  overrideOrigin,
  fallbackOrigin,
}: {
  overrideOrigin: string;
  fallbackOrigin: string;
}): string {
  return normalizeOrigin(overrideOrigin) || normalizeOrigin(fallbackOrigin);
}
