import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import https from 'node:https';
import { fileURLToPath } from 'node:url';

import { isLoopbackDeviceLinkPublicOrigin } from './device-link-https.mjs';

const DEFAULT_DEVICE_LINK_HTTPS_PORT = 8343;

function gate(name, status, message, details = {}) {
  return {
    name,
    status,
    message,
    ...details,
  };
}

export function shellQuote(value) {
  return `'${String(value).replace(/'/g, `'\\''`)}'`;
}

export function normalizeDeviceLinkPublicOrigin(rawOrigin = '') {
  const normalized = String(rawOrigin || '').trim().replace(/\/+$/, '');
  if (!normalized) {
    return { ok: false, error: 'DEVICE_LINK_PUBLIC_ORIGIN_required' };
  }
  let parsed;
  try {
    parsed = new URL(normalized);
  } catch {
    return { ok: false, error: 'DEVICE_LINK_PUBLIC_ORIGIN_invalid_url', value: normalized };
  }
  if (parsed.protocol !== 'https:') {
    return { ok: false, error: 'DEVICE_LINK_PUBLIC_ORIGIN_must_use_https', value: normalized };
  }
  if (parsed.pathname !== '/' || parsed.search || parsed.hash) {
    return { ok: false, error: 'DEVICE_LINK_PUBLIC_ORIGIN_must_not_include_path', value: normalized };
  }
  if (isLoopbackDeviceLinkPublicOrigin(parsed.origin)) {
    return { ok: false, error: 'DEVICE_LINK_PUBLIC_ORIGIN_must_be_lan_reachable', value: parsed.origin };
  }
  return {
    ok: true,
    origin: parsed.origin,
    hostname: parsed.hostname.replace(/^\[|\]$/g, ''),
    port: parsed.port ? Number.parseInt(parsed.port, 10) : 443,
  };
}

export function isIpAddressHost(hostname = '') {
  const host = String(hostname).replace(/^\[|\]$/g, '');
  return /^\d{1,3}(\.\d{1,3}){3}$/.test(host) || host.includes(':');
}

export function extractSubjectAltNameTokens(subjectAltNameText = '') {
  return String(subjectAltNameText)
    .split(/[\n,]/)
    .map((token) => token.trim())
    .filter((token) => token.startsWith('DNS:') || token.startsWith('IP Address:'));
}

export function subjectAltNameMatchesHost(subjectAltNameText = '', hostname = '') {
  const host = String(hostname).replace(/^\[|\]$/g, '').toLowerCase();
  const expectedPrefix = isIpAddressHost(host) ? 'IP Address:' : 'DNS:';
  return extractSubjectAltNameTokens(subjectAltNameText).some((token) => {
    if (!token.startsWith(expectedPrefix)) {
      return false;
    }
    return token.slice(expectedPrefix.length).trim().toLowerCase() === host;
  });
}

export function buildDeviceLinkComposeCommand({
  publicOrigin,
  certHostFile,
  keyHostFile,
  hostPort = DEFAULT_DEVICE_LINK_HTTPS_PORT,
} = {}) {
  return [
    `DEVICE_LINK_PUBLIC_ORIGIN=${shellQuote(publicOrigin || 'https://<lan-ip>:8343')}`,
    `DEVICE_LINK_HTTPS_CERT_HOST_FILE=${shellQuote(certHostFile || '/path/to/lan-trusted-cert.pem')}`,
    `DEVICE_LINK_HTTPS_KEY_HOST_FILE=${shellQuote(keyHostFile || '/path/to/lan-trusted-key.pem')}`,
    `DEVICE_LINK_HTTPS_HOST_PORT=${shellQuote(String(hostPort || DEFAULT_DEVICE_LINK_HTTPS_PORT))}`,
    'docker compose -f docker-compose.yml -f docker-compose.device-link-https.yml up -d frontend',
  ].join(' ');
}

export function getFileInfoFromFs(filePath) {
  if (!filePath) {
    return { exists: false, size: 0 };
  }
  try {
    const stat = fs.statSync(filePath);
    return { exists: stat.isFile(), size: stat.size };
  } catch {
    return { exists: false, size: 0 };
  }
}

export function readCertificateSubjectAltNameWithOpenSsl(certHostFile) {
  return execFileSync('openssl', ['x509', '-in', certHostFile, '-noout', '-ext', 'subjectAltName'], {
    encoding: 'utf8',
    timeout: 3000,
  });
}

export function checkDeviceLinkHealth(publicOrigin, timeoutMs = 2500) {
  return new Promise((resolve) => {
    let settled = false;
    const healthUrl = new URL('/device-link/health', publicOrigin);
    const request = https.get(
      healthUrl,
      {
        rejectUnauthorized: false,
        timeout: timeoutMs,
      },
      (response) => {
        const chunks = [];
        response.on('data', (chunk) => chunks.push(chunk));
        response.on('end', () => {
          if (settled) {
            return;
          }
          settled = true;
          const body = Buffer.concat(chunks).toString('utf8');
          let parsedBody = null;
          try {
            parsedBody = JSON.parse(body);
          } catch {
            parsedBody = null;
          }
          resolve({
            ok: response.statusCode === 200 && parsedBody?.service === 'device-link-https',
            statusCode: response.statusCode,
            service: parsedBody?.service || null,
          });
        });
      },
    );
    request.on('timeout', () => {
      if (!settled) {
        settled = true;
        request.destroy();
        resolve({ ok: false, error: 'device_link_https_health_timeout' });
      }
    });
    request.on('error', (error) => {
      if (!settled) {
        settled = true;
        resolve({ ok: false, error: error.code || error.message });
      }
    });
  });
}

export async function buildDeviceLinkHttpsReadinessReport({
  env = process.env,
  getFileInfo = getFileInfoFromFs,
  readCertificateSubjectAltName = readCertificateSubjectAltNameWithOpenSsl,
  checkHealth = checkDeviceLinkHealth,
} = {}) {
  const publicOriginInput = String(env.DEVICE_LINK_PUBLIC_ORIGIN || '').trim();
  const certHostFile = String(env.DEVICE_LINK_HTTPS_CERT_HOST_FILE || '').trim();
  const keyHostFile = String(env.DEVICE_LINK_HTTPS_KEY_HOST_FILE || '').trim();
  const hostPort = Number.parseInt(
    String(env.DEVICE_LINK_HTTPS_HOST_PORT || DEFAULT_DEVICE_LINK_HTTPS_PORT),
    10,
  );
  const gates = [];
  const origin = normalizeDeviceLinkPublicOrigin(publicOriginInput);

  if (!origin.ok) {
    gates.push(gate('public_origin', 'blocked', origin.error, { value: origin.value || publicOriginInput }));
  } else if (origin.port !== hostPort) {
    gates.push(
      gate('public_origin', 'blocked', 'DEVICE_LINK_PUBLIC_ORIGIN_port_must_match_host_port', {
        public_origin: origin.origin,
        origin_port: origin.port,
        expected_host_port: hostPort,
      }),
    );
  } else {
    gates.push(gate('public_origin', 'passed', 'trusted_lan_https_origin', { public_origin: origin.origin }));
  }

  const certInfo = getFileInfo(certHostFile);
  const keyInfo = getFileInfo(keyHostFile);
  if (!certHostFile || !keyHostFile || !certInfo.exists || certInfo.size <= 0 || !keyInfo.exists || keyInfo.size <= 0) {
    gates.push(
      gate('certificate_files', 'blocked', 'DEVICE_LINK_HTTPS_CERT_HOST_FILE_and_KEY_HOST_FILE_required', {
        cert_host_file: certHostFile || null,
        key_host_file: keyHostFile || null,
        cert_exists: Boolean(certInfo.exists && certInfo.size > 0),
        key_exists: Boolean(keyInfo.exists && keyInfo.size > 0),
      }),
    );
  } else {
    gates.push(gate('certificate_files', 'passed', 'certificate_and_key_files_present', { cert_host_file: certHostFile, key_host_file: keyHostFile }));
  }

  const canCheckSan = origin.ok && gates.find((item) => item.name === 'certificate_files')?.status === 'passed';
  let sanMatched = false;
  if (!canCheckSan) {
    gates.push(gate('certificate_san', 'blocked', 'skipped_until_public_origin_and_certificate_files_are_ready'));
  } else {
    try {
      const subjectAltNameText = readCertificateSubjectAltName(certHostFile);
      sanMatched = subjectAltNameMatchesHost(subjectAltNameText, origin.hostname);
      gates.push(
        gate(
          'certificate_san',
          sanMatched ? 'passed' : 'blocked',
          sanMatched ? 'certificate_san_matches_public_origin_host' : 'certificate_san_missing_public_origin_host',
          { public_origin_host: origin.hostname },
        ),
      );
    } catch (error) {
      gates.push(
        gate('certificate_san', 'blocked', 'certificate_san_unreadable', {
          error: error?.code || error?.message || 'unknown_error',
        }),
      );
    }
  }

  const canCheckHealth = origin.ok && sanMatched;
  if (!canCheckHealth) {
    gates.push(gate('device_link_health', 'blocked', 'skipped_until_origin_and_certificate_san_are_ready'));
  } else {
    const health = await checkHealth(origin.origin);
    gates.push(
      gate(
        'device_link_health',
        health.ok ? 'passed' : 'blocked',
        health.ok ? 'device_link_https_health_ok' : 'device_link_https_health_unavailable',
        health,
      ),
    );
  }

  const readyForPhoneSmoke = gates.every((item) => item.status === 'passed');
  const readyToStartProxy =
    !readyForPhoneSmoke &&
    gates.find((item) => item.name === 'public_origin')?.status === 'passed' &&
    gates.find((item) => item.name === 'certificate_files')?.status === 'passed' &&
    gates.find((item) => item.name === 'certificate_san')?.status === 'passed';

  return {
    status: readyForPhoneSmoke ? 'ready_for_phone_smoke' : 'blocked_device_link_https_readiness',
    ready_for_phone_smoke: readyForPhoneSmoke,
    ready_to_start_proxy: readyToStartProxy,
    public_origin: origin.ok ? origin.origin : publicOriginInput || null,
    host_port: Number.isInteger(hostPort) ? hostPort : DEFAULT_DEVICE_LINK_HTTPS_PORT,
    gates,
    start_command: buildDeviceLinkComposeCommand({
      publicOrigin: origin.ok ? origin.origin : publicOriginInput,
      certHostFile,
      keyHostFile,
      hostPort: Number.isInteger(hostPort) ? hostPort : DEFAULT_DEVICE_LINK_HTTPS_PORT,
    }),
    resource_policy: {
      db_migration: false,
      worker_queue: false,
      pgbouncer_pool: false,
      ux_polling: false,
      raw_media_persist: false,
    },
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const report = await buildDeviceLinkHttpsReadinessReport();
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  process.exitCode = report.ready_for_phone_smoke ? 0 : 2;
}
