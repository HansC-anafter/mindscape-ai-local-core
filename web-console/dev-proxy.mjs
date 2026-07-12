import crypto from 'node:crypto';
import { spawn } from 'node:child_process';

import {
  buildInternalApiUrl,
} from './dev-proxy/api-target.mjs';
import {
  prepareCapabilityHostRuntimeAssets,
} from './dev-proxy/capability-host-bootstrap.mjs';
import {
  resolveDeviceLinkHttpsConfig,
  startDeviceLinkHttpsProxy,
} from './dev-proxy/device-link-https.mjs';
import {
  createFrontendProxyServer,
} from './dev-proxy/frontend-proxy-server.mjs';
import {
  createCloudflareAccessJwtVerifier,
  loadMobileWorkbenchGatewayRuntimeConfig,
  resolveMobileWorkbenchGatewayConfig,
} from './dev-proxy/mobile-workbench-gateway.mjs';
import {
  createMobileWorkbenchGatewayPolicyResolver,
} from './dev-proxy/mobile-workbench-gateway-policy-resolver.mjs';
import {
  prewarmNextDevRoutes,
} from './dev-proxy/prewarm.mjs';
import {
  resolveNextDevArgs,
} from './dev-proxy/proxy-http.mjs';
import {
  startRemoteWorkbenchListener,
} from './dev-proxy/remote-workbench-listener.mjs';

export { resolveFrontendPrewarmPaths } from './dev-proxy/prewarm.mjs';
export { resolveApiRoutePlane } from './dev-proxy/api-route-plane.mjs';
export {
  DEFAULT_FRONTEND_DOCUMENT_SINGLEFLIGHT_MAX_BODY_BYTES,
  createFrontendDocumentSingleflight,
  isFrontendDocumentRequest,
  normalizeFrontendDocumentSingleflightKey,
} from './dev-proxy/document-singleflight.mjs';
export {
  isFrontendDocumentHeadReadinessRequest,
  writeFrontendDocumentHeadReadiness,
} from './dev-proxy/head-readiness.mjs';
export {
  isCapabilityHostBootstrapRequest,
  isCapabilityHostRuntimeAssetRequest,
  parseCapabilityHostBootstrapRoute,
  writeCapabilityHostBootstrap,
  writeCapabilityHostRuntimeAsset,
} from './dev-proxy/capability-host-bootstrap.mjs';
export {
  isAllowedDeviceLinkHttpsPath,
  isDeviceLinkHttpsReadinessPath,
  resolveDeviceLinkHttpsConfig,
  startDeviceLinkHttpsProxy,
} from './dev-proxy/device-link-https.mjs';
export {
  authorizeRemoteWorkbenchRequest,
  createCloudflareAccessJwtVerifier,
  createRemoteJwkSet,
  deriveAuthConfigFingerprint,
  extractMobileWorkbenchGatewayRequestContext,
  formatMobileWorkbenchGatewayConfig,
  loadMobileWorkbenchGatewayRuntimeConfig,
  normalizeEffectiveWorkspacePolicy,
  normalizeRuntimeAccessPolicy,
  parseAccessTokenFromHeaders,
  resolveMobileWorkbenchGatewayConfig,
} from './dev-proxy/mobile-workbench-gateway.mjs';
export { createRemoteWorkbenchObservability } from './dev-proxy/remote-workbench-observability.mjs';
export {
  buildInternalApiUrl,
  isDevApiProxyPath,
  isFrontendLivenessPath,
  resolveDevApiProxyTarget,
} from './dev-proxy/api-target.mjs';
export {
  copyProxyRequestHeaders,
  copyProxyResponseHeaders,
  copyProxyUpgradeHeaders,
} from './dev-proxy/proxy-headers.mjs';
export {
  clearDevApiReadCacheForTests,
  resolveDevApiReadCacheTtlMs,
} from './dev-proxy/dev-api-read-cache.mjs';
export { clearFrontendDocumentSingleflightForTests } from './dev-proxy/frontend-document-stream.mjs';
export { isDeviceLinkHttpsHealthRequest } from './dev-proxy/local-control-endpoints.mjs';
export {
  classifyProxyUpstream,
  normalizeProxyLogPath,
  resolveNextDevArgs,
  shouldWriteProxyTimingLog,
} from './dev-proxy/proxy-http.mjs';
export {
  createFrontendProxyServer,
  isForegroundFrontendRequest,
} from './dev-proxy/frontend-proxy-server.mjs';
export { startRemoteWorkbenchListener } from './dev-proxy/remote-workbench-listener.mjs';

const LOCAL_HOST = process.env.FRONTEND_PROXY_HOST || '0.0.0.0';
const LOCAL_PORT = Number.parseInt(process.env.PORT || '3000', 10);
const REMOTE_HOST = '0.0.0.0';
const REMOTE_PORT = 3001;
const PREWARM_ENABLED = process.env.FRONTEND_PREWARM_ENABLED === '1';
const PREWARM_DELAY_MS = Number.parseInt(process.env.FRONTEND_PREWARM_DELAY_MS || '8000', 10);
const PREWARM_IDLE_MS = Number.parseInt(process.env.FRONTEND_PREWARM_IDLE_MS || '45000', 10);
const PREWARM_FOREGROUND_GRACE_MS = Number.parseInt(
  process.env.FRONTEND_PREWARM_FOREGROUND_GRACE_MS || '15000',
  10,
);

export function computeNextDevRestartDelayMs(restartCount) {
  const boundedCount = Math.max(0, Math.min(Number(restartCount) || 0, 5));
  return Math.min(30_000, 1_000 * (2 ** boundedCount));
}

export function resolvePrewarmIdleDelayMs(lastForegroundActivityAt, now = Date.now(), idleMs = PREWARM_IDLE_MS) {
  const normalizedIdleMs = Math.max(0, Number(idleMs) || 0);
  const normalizedLastActivityAt = Math.max(0, Number(lastForegroundActivityAt) || 0);
  if (!normalizedIdleMs || !normalizedLastActivityAt) {
    return 0;
  }
  return Math.max(0, normalizedIdleMs - Math.max(0, Number(now) - normalizedLastActivityAt));
}

export function createDeviceLinkIngressToken() {
  return crypto.randomBytes(32).toString('hex');
}

export function start() {
  const nextRunningRef = { current: false };
  const gatewayConfigRef = { current: resolveMobileWorkbenchGatewayConfig() };
  const deviceLinkIngressToken = createDeviceLinkIngressToken();
  const policyResolver = createMobileWorkbenchGatewayPolicyResolver({ buildInternalApiUrl });
  let nextProcess = null;
  let restartTimer = null;
  let prewarmTimer = null;
  let deviceLinkHttpsServer = null;
  let remoteServer = null;
  let restartCount = 0;
  let shuttingDown = false;
  let lastForegroundActivityAt = Date.now();

  const recordForegroundActivity = (activityAt = Date.now()) => {
    lastForegroundActivityAt = Math.max(lastForegroundActivityAt, Number(activityAt) || Date.now());
  };
  const hasRecentForegroundActivity = () => (
    resolvePrewarmIdleDelayMs(lastForegroundActivityAt, Date.now(), PREWARM_FOREGROUND_GRACE_MS) > 0
  );
  const localServer = createFrontendProxyServer({
    ingressMode: 'local',
    nextRunningRef,
    getMobileWorkbenchGatewayConfig: () => gatewayConfigRef.current,
    policyResolver,
    recordForegroundActivity,
  });

  const schedulePrewarm = (delayMs = PREWARM_DELAY_MS) => {
    if (shuttingDown || !PREWARM_ENABLED) {
      return;
    }
    if (prewarmTimer) {
      clearTimeout(prewarmTimer);
    }
    prewarmTimer = setTimeout(() => {
      prewarmTimer = null;
      const idleDelayMs = resolvePrewarmIdleDelayMs(lastForegroundActivityAt, Date.now(), PREWARM_IDLE_MS);
      if (idleDelayMs > 0) {
        schedulePrewarm(idleDelayMs);
        return;
      }
      void prewarmNextDevRoutes(undefined, {
        shouldContinue: () => !hasRecentForegroundActivity(),
        stopReason: 'foreground_activity',
      });
    }, Math.max(0, Number(delayMs) || 0));
  };

  const launchNextDev = () => {
    if (shuttingDown) {
      return;
    }
    nextRunningRef.current = false;
    nextProcess = spawn('pnpm', resolveNextDevArgs(), {
      cwd: process.cwd(),
      env: process.env,
      stdio: 'inherit',
    });
    nextProcess.on('spawn', () => {
      nextRunningRef.current = true;
      if (PREWARM_ENABLED) {
        lastForegroundActivityAt = Date.now();
        schedulePrewarm(PREWARM_DELAY_MS);
      }
    });
    nextProcess.on('exit', (code, signal) => {
      nextRunningRef.current = false;
      if (prewarmTimer) {
        clearTimeout(prewarmTimer);
        prewarmTimer = null;
      }
      console.error(`[frontend-proxy] next dev exited code=${code ?? 'null'} signal=${signal ?? 'null'}`);
      if (!shuttingDown) {
        const delayMs = computeNextDevRestartDelayMs(restartCount);
        restartCount += 1;
        restartTimer = setTimeout(() => {
          restartTimer = null;
          launchNextDev();
        }, delayMs);
      }
    });
  };

  launchNextDev();
  localServer.listen(LOCAL_PORT, LOCAL_HOST, () => {
    console.log(`[frontend-proxy] local listener ${LOCAL_HOST}:${LOCAL_PORT}`);
    void prepareCapabilityHostRuntimeAssets();
    deviceLinkHttpsServer = startDeviceLinkHttpsProxy({
      targetHost: '127.0.0.1',
      targetPort: LOCAL_PORT,
      ingressToken: deviceLinkIngressToken,
    });
    void startRemoteWorkbenchListener({
      loadRuntimeConfig: () => loadMobileWorkbenchGatewayRuntimeConfig({ buildInternalApiUrl }),
      createVerifier: (runtimePolicy) => createCloudflareAccessJwtVerifier({
        accessIssuer: runtimePolicy.accessIssuer,
        accessAudience: runtimePolicy.accessAudience,
      }),
      createServer: ({ verifier }) => createFrontendProxyServer({
        ingressMode: 'remote',
        nextRunningRef,
        getMobileWorkbenchGatewayConfig: () => gatewayConfigRef.current,
        verifyAccessToken: verifier,
        policyResolver,
        recordForegroundActivity,
      }),
      configRef: gatewayConfigRef,
      host: REMOTE_HOST,
      port: REMOTE_PORT,
    }).then((result) => {
      remoteServer = result.server;
      if (remoteServer) {
        console.log(`[frontend-proxy] remote listener ${REMOTE_HOST}:${REMOTE_PORT}`);
      } else {
        console.error('[frontend-proxy] remote listener closed: runtime policy is not ready');
      }
    }).catch((error) => {
      console.error(`[frontend-proxy] remote listener failed: ${error?.message || 'unknown_error'}`);
    });
  });

  const shutdown = () => {
    shuttingDown = true;
    if (restartTimer) clearTimeout(restartTimer);
    if (prewarmTimer) clearTimeout(prewarmTimer);
    deviceLinkHttpsServer?.close();
    remoteServer?.close();
    localServer.close(() => nextProcess?.kill('SIGTERM'));
    setTimeout(() => {
      nextProcess?.kill('SIGKILL');
      process.exit(0);
    }, 10_000).unref();
  };
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  start();
}
