import http from 'node:http';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';
import {
  prewarmNextDevRoutes,
} from './dev-proxy/prewarm.mjs';
import { resolveApiRoutePlane } from './dev-proxy/api-route-plane.mjs';
import {
  DEFAULT_FRONTEND_DOCUMENT_SINGLEFLIGHT_MAX_BODY_BYTES,
  isFrontendDocumentRequest,
  normalizeFrontendDocumentSingleflightKey,
} from './dev-proxy/document-singleflight.mjs';
import {
  isFrontendDocumentHeadReadinessRequest,
  writeFrontendDocumentHeadReadiness,
} from './dev-proxy/head-readiness.mjs';
import {
  resolveDeviceLinkHttpsConfig,
  startDeviceLinkHttpsProxy,
} from './dev-proxy/device-link-https.mjs';
import {
  isMobileWorkbenchGatewayPathAllowed,
  isMobileWorkbenchGatewayRequestAllowed,
  isMobileWorkbenchGatewayRequestAllowedAsync,
  isLoopbackControlPlaneRequest,
  formatMobileWorkbenchGatewayConfig,
  resolveMobileWorkbenchGatewayConfig,
} from './dev-proxy/mobile-workbench-gateway.mjs';
import {
  createMobileWorkbenchGatewayPolicyResolver,
} from './dev-proxy/mobile-workbench-gateway-policy-resolver.mjs';
import {
  createRemoteWorkbenchObservability,
} from './dev-proxy/remote-workbench-observability.mjs';
import {
  buildInternalApiUrl,
  isDevApiProxyPath,
  isFrontendLivenessPath,
  resolveDevApiProxyTarget,
} from './dev-proxy/api-target.mjs';
import {
  copyProxyResponseHeaders,
  copyProxyUpgradeHeaders,
} from './dev-proxy/proxy-headers.mjs';
import {
  clearDevApiReadCacheForTests,
  resolveDevApiReadCacheTtlMs,
} from './dev-proxy/dev-api-read-cache.mjs';
import {
  clearFrontendDocumentSingleflightForTests,
} from './dev-proxy/frontend-document-stream.mjs';
import {
  isDeviceLinkHttpsHealthRequest,
  isMobileWorkbenchGatewayAuditRequest,
  isMobileWorkbenchGatewayHealthRequest,
  isMobileWorkbenchGatewaySummaryRequest,
  writeDeviceLinkHttpsHealth,
  writeFrontendLiveness,
  writeMobileWorkbenchGatewayAudit,
  writeMobileWorkbenchGatewayHealth,
  writeMobileWorkbenchGatewayRejection,
  writeMobileWorkbenchGatewaySummary,
} from './dev-proxy/local-control-endpoints.mjs';
import {
  classifyProxyUpstream,
  loadRemoteWorkbenchRunnerSnapshot,
  normalizeProxyLogPath,
  proxyHttpRequest,
  resolveNextDevArgs,
  shouldWriteProxyTimingLog,
} from './dev-proxy/proxy-http.mjs';
import {
  proxyUpgrade,
} from './dev-proxy/proxy-upgrade.mjs';

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
  isAllowedDeviceLinkHttpsPath,
  isDeviceLinkHttpsReadinessPath,
  resolveDeviceLinkHttpsConfig,
  startDeviceLinkHttpsProxy,
} from './dev-proxy/device-link-https.mjs';
export {
  isMobileWorkbenchGatewayPathAllowed,
  isMobileWorkbenchGatewayRequestAllowed,
  isMobileWorkbenchGatewayRequestAllowedAsync,
  isLoopbackControlPlaneRequest,
  formatMobileWorkbenchGatewayConfig,
  resolveMobileWorkbenchGatewayConfig,
} from './dev-proxy/mobile-workbench-gateway.mjs';
export {
  createRemoteWorkbenchObservability,
} from './dev-proxy/remote-workbench-observability.mjs';
export {
  buildInternalApiUrl,
  isDevApiProxyPath,
  isFrontendLivenessPath,
  resolveDevApiProxyTarget,
} from './dev-proxy/api-target.mjs';
export {
  copyProxyResponseHeaders,
  copyProxyUpgradeHeaders,
} from './dev-proxy/proxy-headers.mjs';
export {
  clearDevApiReadCacheForTests,
  resolveDevApiReadCacheTtlMs,
} from './dev-proxy/dev-api-read-cache.mjs';
export {
  clearFrontendDocumentSingleflightForTests,
} from './dev-proxy/frontend-document-stream.mjs';
export {
  isDeviceLinkHttpsHealthRequest,
} from './dev-proxy/local-control-endpoints.mjs';
export {
  classifyProxyUpstream,
  normalizeProxyLogPath,
  resolveNextDevArgs,
  shouldWriteProxyTimingLog,
} from './dev-proxy/proxy-http.mjs';

const PUBLIC_HOST = process.env.FRONTEND_PROXY_HOST || '0.0.0.0';
const PUBLIC_PORT = Number.parseInt(process.env.PORT || '3000', 10);
const NEXT_HOST = process.env.NEXT_DEV_HOST || '127.0.0.1';
const NEXT_PORT = Number.parseInt(process.env.NEXT_DEV_PORT || '3001', 10);
const PREWARM_ENABLED = process.env.FRONTEND_PREWARM_ENABLED === '1';
const PREWARM_DELAY_MS = Number.parseInt(process.env.FRONTEND_PREWARM_DELAY_MS || '8000', 10);
let requestSequence = 0;

export function computeNextDevRestartDelayMs(restartCount) {
  const boundedCount = Math.max(0, Math.min(Number(restartCount) || 0, 5));
  return Math.min(30_000, 1_000 * (2 ** boundedCount));
}

export function createDeviceLinkIngressToken() {
  return crypto.randomBytes(32).toString('hex');
}

export function createFrontendProxyServer({
  nextRunningRef = { current: false },
  nextProxyTarget = null,
  mobileWorkbenchGatewayConfig = resolveMobileWorkbenchGatewayConfig(),
  deviceLinkIngressToken = '',
  remoteWorkbenchObservability = createRemoteWorkbenchObservability({
    loadRunnerSnapshot: loadRemoteWorkbenchRunnerSnapshot,
  }),
} = {}) {
  const resolveWorkspaceCapabilityPolicy = createMobileWorkbenchGatewayPolicyResolver({
    buildInternalApiUrl,
  });

  const server = http.createServer((req, res) => {
    void (async () => {
      if (isDeviceLinkHttpsHealthRequest(req.url, req.method)) {
        writeDeviceLinkHttpsHealth(res);
        return;
      }
      if (isMobileWorkbenchGatewayHealthRequest(req.url, req.method)) {
        writeMobileWorkbenchGatewayHealth(res, mobileWorkbenchGatewayConfig);
        return;
      }
      if (isMobileWorkbenchGatewaySummaryRequest(req.url, req.method)) {
        if (!isLoopbackControlPlaneRequest(req.headers)) {
          writeMobileWorkbenchGatewayRejection(
            res,
            { reason: 'mobile_workbench_gateway_path_not_allowed', status_code: 404 },
            req.url,
          );
          return;
        }
        await writeMobileWorkbenchGatewaySummary(res, remoteWorkbenchObservability, req.url);
        return;
      }
      if (isMobileWorkbenchGatewayAuditRequest(req.url, req.method)) {
        if (!isLoopbackControlPlaneRequest(req.headers)) {
          writeMobileWorkbenchGatewayRejection(
            res,
            { reason: 'mobile_workbench_gateway_path_not_allowed', status_code: 404 },
            req.url,
          );
          return;
        }
        await writeMobileWorkbenchGatewayAudit(res, remoteWorkbenchObservability, req.url);
        return;
      }
      if (isFrontendLivenessPath(req.url)) {
        writeFrontendLiveness(res, nextRunningRef.current);
        return;
      }
      if (isFrontendDocumentHeadReadinessRequest(req.method, req.url)) {
        writeFrontendDocumentHeadReadiness(res, nextRunningRef.current);
        return;
      }

      const requestId = ++requestSequence;
      const requestResult = await isMobileWorkbenchGatewayRequestAllowedAsync(
        req.url,
        req.headers,
        mobileWorkbenchGatewayConfig,
        {
          deviceLinkIngressToken,
          requestMethod: req.method,
          resolveWorkspaceCapabilityPolicy,
        },
      );
      const requestObservation = remoteWorkbenchObservability.createObservation({
        requestId,
        requestUrl: req.url,
        requestMethod: req.method,
        requestHeaders: req.headers,
        requestResult,
        mobileWorkbenchGatewayConfig,
      });
      if (!requestResult.allowed) {
        const rejection = writeMobileWorkbenchGatewayRejection(res, requestResult, req.url);
        void remoteWorkbenchObservability.recordDeniedRequest(requestObservation, {
          requestResult,
          statusCode: rejection.statusCode,
          responseBytes: rejection.bodyBytes,
        });
        return;
      }

      proxyHttpRequest(req, res, {
        requestId,
        nextProxyTarget,
        onComplete: (event) => {
          void remoteWorkbenchObservability.recordCompletedRequest(requestObservation, event);
        },
      });
    })().catch((error) => {
      if (!res.headersSent) {
        res.writeHead(500, { 'content-type': 'application/json', 'cache-control': 'no-store' });
      }
      if (!res.writableEnded) {
        res.end(JSON.stringify({
          error: 'frontend_proxy_request_failed',
          detail: error?.message || 'unknown_error',
        }));
      }
    });
  });

  server.on('upgrade', (req, socket, head) => {
    void proxyUpgrade(
      req,
      socket,
      head,
      mobileWorkbenchGatewayConfig,
      deviceLinkIngressToken,
      resolveWorkspaceCapabilityPolicy,
      nextProxyTarget,
    ).catch(() => {
      socket.destroy();
    });
  });
  server.on('clientError', (_error, socket) => {
    socket.end('HTTP/1.1 400 Bad Request\r\n\r\n');
  });

  return server;
}

export function start() {
  const nextRunningRef = { current: false };
  const deviceLinkIngressToken = createDeviceLinkIngressToken();
  let nextProcess = null;
  let restartTimer = null;
  let prewarmTimer = null;
  let deviceLinkHttpsServer = null;
  let restartCount = 0;
  let shuttingDown = false;
  const server = createFrontendProxyServer({ nextRunningRef, deviceLinkIngressToken });

  const launchNextDev = () => {
    if (shuttingDown) {
      return;
    }

    nextRunningRef.current = false;
    nextProcess = spawn(
      'pnpm',
      resolveNextDevArgs(),
      {
        cwd: process.cwd(),
        env: process.env,
        stdio: 'inherit',
      },
    );

    nextProcess.on('spawn', () => {
      nextRunningRef.current = true;
      if (PREWARM_ENABLED) {
        prewarmTimer = setTimeout(() => {
          prewarmTimer = null;
          void prewarmNextDevRoutes();
        }, PREWARM_DELAY_MS);
      }
    });

    nextProcess.on('exit', (code, signal) => {
      nextRunningRef.current = false;
      if (prewarmTimer) {
        clearTimeout(prewarmTimer);
        prewarmTimer = null;
      }
      console.error(`[frontend-proxy] next dev exited code=${code ?? 'null'} signal=${signal ?? 'null'}`);

      if (shuttingDown) {
        return;
      }

      const delayMs = computeNextDevRestartDelayMs(restartCount);
      restartCount += 1;
      console.error(`[frontend-proxy] restarting next dev in ${delayMs}ms`);
      restartTimer = setTimeout(() => {
        restartTimer = null;
        launchNextDev();
      }, delayMs);
    });
  };

  launchNextDev();

  server.listen(PUBLIC_PORT, PUBLIC_HOST, () => {
    console.log(`[frontend-proxy] listening on ${PUBLIC_HOST}:${PUBLIC_PORT}, proxying to ${NEXT_HOST}:${NEXT_PORT}`);
    deviceLinkHttpsServer = startDeviceLinkHttpsProxy({
      targetHost: '127.0.0.1',
      targetPort: PUBLIC_PORT,
      ingressToken: deviceLinkIngressToken,
    });
  });

  const shutdown = () => {
    shuttingDown = true;
    if (restartTimer) {
      clearTimeout(restartTimer);
      restartTimer = null;
    }
    if (prewarmTimer) {
      clearTimeout(prewarmTimer);
      prewarmTimer = null;
    }
    deviceLinkHttpsServer?.close();
    deviceLinkHttpsServer = null;
    server.close(() => {
      nextProcess?.kill('SIGTERM');
    });
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
