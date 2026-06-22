import { describe, expect, it } from 'vitest';

import {
  createAccessJwt,
  extractMobileWorkbenchGatewayRequestContext,
  isMobileWorkbenchGatewayPathAllowed,
  isMobileWorkbenchGatewayRequestAllowed,
  isMobileWorkbenchGatewayRequestAllowedAsync,
  resolveMobileWorkbenchGatewayConfig,
} from './mobile-workbench-gateway.test-support.mjs';

describe('mobile workbench gateway pack policy', () => {
  it('rejects expired access tokens even when identity allowlist matches', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_ALLOWLIST_EMAILS: 'expired@mindscape.ai',
      MOBILE_WORKBENCH_GATEWAY_JWT_CLOCK_SKEW_SECONDS: '0',
    });
    const token = createAccessJwt({
      email: 'expired@mindscape.ai',
      exp: Math.floor(Date.now() / 1000) - 10,
      groups: ['default'],
      workspace_id: 'ws-1',
    });
    const result = isMobileWorkbenchGatewayRequestAllowed(
      '/api/v1/capability-packs/ig/ui-assets/bundle.js?workspace_id=ws-1',
      {
        CF_Authorization: `Bearer ${token}`,
      },
      config,
    );

    expect(result).toMatchObject({
      allowed: false,
      reason: 'mobile_workbench_gateway_access_denied',
      reason_code: 'expired_or_not_ready_token',
      status_code: 403,
    });
  });

  it('collects path parse errors while staying enabled for defaults', () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_EXTRA_PATH_RULES: 'badprefix,regex:^(abc',
    });
    expect(config).toMatchObject({
      enabled: true,
      reason: 'enabled_with_invalid_rules',
    });
    expect(config.errors).toEqual([
      'invalid_path_pattern:badprefix',
      'invalid_regex_pattern:regex:^(abc',
    ]);
    expect(isMobileWorkbenchGatewayPathAllowed('/workspaces/ws-1/capability-ui-hosts/ig', config)).toBe(true);
    expect(isMobileWorkbenchGatewayPathAllowed('/admin/tools', config)).toBe(false);
  });

  it('extracts capability scope from referer for shared workspace support paths', () => {
    expect(
      extractMobileWorkbenchGatewayRequestContext(
        '/api/v1/workspaces/ws-1/tasks?limit=20',
        {
          referer: 'https://remote-workbench.mindscapeai.app/workspaces/ws-1/capability-ui-hosts/yogacoach?component=YogaPracticeWorkbenchPage',
        },
      ),
    ).toMatchObject({
      workspaceId: 'ws-1',
      capabilityCode: 'yogacoach',
    });
  });

  it('enforces pack-owned workspace capability policy before allowing shared support paths', async () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
    });

    const denied = await isMobileWorkbenchGatewayRequestAllowedAsync(
      '/workspaces/ws-1/capability-ui-hosts/yogacoach',
      {
        referer: 'https://remote-workbench.mindscapeai.app/workspaces/ws-1/capability-ui-hosts/yogacoach',
      },
      config,
      {
        resolveWorkspaceCapabilityPolicy: async () => ({
          capabilityAllowed: false,
          supported: true,
          allowedPathRules: [
            {
              type: 'regex',
              value: /^\/workspaces\/[^/]+\/capability-ui-hosts\/yogacoach(?:\/.*)?$/,
            },
          ],
        }),
      },
    );

    expect(denied).toMatchObject({
      allowed: false,
      reason_code: 'capability_not_allowed',
      status_code: 403,
      context: {
        workspaceId: 'ws-1',
        capabilityCode: 'yogacoach',
      },
    });

    const allowed = await isMobileWorkbenchGatewayRequestAllowedAsync(
      '/api/v1/workspaces/ws-1/tasks?limit=20',
      {
        referer: 'https://remote-workbench.mindscapeai.app/workspaces/ws-1/capability-ui-hosts/yogacoach',
      },
      config,
      {
        resolveWorkspaceCapabilityPolicy: async () => ({
          capabilityAllowed: true,
          supported: true,
          allowedPathRules: [
            {
              type: 'regex',
              value: /^\/workspaces\/[^/]+\/capability-ui-hosts\/yogacoach(?:\/.*)?$/,
            },
          ],
        }),
      },
    );

    expect(allowed).toMatchObject({
      allowed: true,
      context: {
        workspaceId: 'ws-1',
        capabilityCode: 'yogacoach',
      },
    });
  });

  it('ignores deprecated capability allowlist env and defers capability access to workspace policy', async () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_CAPABILITY_ALLOWLIST: 'ig',
    });

    const allowed = await isMobileWorkbenchGatewayRequestAllowedAsync(
      '/workspaces/ws-1/capability-ui-hosts/makeup_practice_coach',
      {
        referer: 'https://remote-workbench.mindscapeai.app/workspaces/ws-1/capability-ui-hosts/makeup_practice_coach',
      },
      config,
      {
        resolveWorkspaceCapabilityPolicy: async () => ({
          capabilityAllowed: true,
          supported: true,
          allowedPathRules: [
            {
              type: 'regex',
              value: /^\/workspaces\/[^/]+\/capability-ui-hosts\/makeup_practice_coach(?:\/.*)?$/,
            },
          ],
        }),
      },
    );

    expect(allowed).toMatchObject({
      allowed: true,
      context: {
        workspaceId: 'ws-1',
        capabilityCode: 'makeup_practice_coach',
      },
    });
  });

  it('allows social_video_refs API reads through the workspace pack policy', async () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
    });

    const allowed = await isMobileWorkbenchGatewayRequestAllowedAsync(
      '/api/v1/capabilities/social-video-refs/hierarchy/instruction-refs?workspace_id=ws-1&limit=20',
      {
        referer: 'https://remote-workbench.mindscapeai.app/workspaces/ws-1/capability-ui-hosts/social_video_refs',
      },
      config,
      {
        resolveWorkspaceCapabilityPolicy: async ({ capabilityCode }) => ({
          capabilityAllowed: capabilityCode === 'social_video_refs',
          supported: true,
          allowedPathRules: [
            {
              type: 'regex',
              value: /^\/api\/v1\/capabilities\/social-video-refs(?:\/.*)?$/,
            },
            {
              type: 'regex',
              value: /^\/workspaces\/[^/]+\/capability-ui-hosts\/social_video_refs(?:\/.*)?$/,
            },
          ],
        }),
      },
    );

    expect(allowed).toMatchObject({
      allowed: true,
      context: {
        workspaceId: 'ws-1',
        capabilityCode: 'social_video_refs',
        routeCapabilityCode: 'social-video-refs',
      },
    });
  });

  it('allows the pack-embedded remote gateway control page when the target capability is allowed', async () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
    });

    const allowed = await isMobileWorkbenchGatewayRequestAllowedAsync(
      '/workspaces/ws-1/capability-ui-hosts/mindscape_cloud_integration?component=MindscapeMobileWorkbenchGatewayPage&target_capability=yogacoach',
      {},
      config,
      {
        resolveWorkspaceCapabilityPolicy: async () => ({
          capabilityAllowed: true,
          supported: true,
          allowedPathRules: [
            {
              type: 'regex',
              value: /^\/workspaces\/[^/]+\/capability-ui-hosts\/yogacoach(?:\/.*)?$/,
            },
          ],
        }),
      },
    );

    expect(allowed).toMatchObject({
      allowed: true,
      context: {
        workspaceId: 'ws-1',
        capabilityCode: 'yogacoach',
        routeCapabilityCode: 'mindscape_cloud_integration',
        gatewayControlPlaneTargeted: true,
      },
    });
  });

  it('allows control-plane asset and observability requests when they inherit the target capability from the referer', async () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
    });
    const referer =
      'https://remote-workbench.mindscapeai.app/workspaces/ws-1/capability-ui-hosts/mindscape_cloud_integration?component=MindscapeMobileWorkbenchGatewayPage&target_capability=yogacoach';

    const assetRequest = await isMobileWorkbenchGatewayRequestAllowedAsync(
      '/api/v1/capability-packs/installed-capabilities/mindscape_cloud_integration/ui-assets/1.0.0/components/MindscapeMobileWorkbenchGatewayPage.mjs',
      { referer },
      config,
      {
        resolveWorkspaceCapabilityPolicy: async () => ({
          capabilityAllowed: true,
          supported: true,
          allowedPathRules: [
            {
              type: 'regex',
              value: /^\/workspaces\/[^/]+\/capability-ui-hosts\/yogacoach(?:\/.*)?$/,
            },
          ],
        }),
      },
    );

    expect(assetRequest).toMatchObject({
      allowed: true,
      context: {
        workspaceId: 'ws-1',
        capabilityCode: 'yogacoach',
        routeCapabilityCode: 'mindscape_cloud_integration',
        gatewayControlPlaneTargeted: true,
      },
    });

    const summaryRequest = await isMobileWorkbenchGatewayRequestAllowedAsync(
      '/api/v1/host/services/mobile-workbench-gateway/summary?workspace_id=ws-1&capability_code=yogacoach',
      { referer },
      config,
      {
        resolveWorkspaceCapabilityPolicy: async () => ({
          capabilityAllowed: true,
          supported: true,
          allowedPathRules: [
            {
              type: 'regex',
              value: /^\/workspaces\/[^/]+\/capability-ui-hosts\/yogacoach(?:\/.*)?$/,
            },
          ],
        }),
      },
    );

    expect(summaryRequest).toMatchObject({
      allowed: true,
      context: {
        workspaceId: 'ws-1',
        capabilityCode: 'yogacoach',
        gatewayControlPlaneTargeted: true,
      },
    });
  });

  it('keeps non-gateway cloud integration components outside the remote pack allowlist', async () => {
    const config = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
    });

    const denied = await isMobileWorkbenchGatewayRequestAllowedAsync(
      '/workspaces/ws-1/capability-ui-hosts/mindscape_cloud_integration?component=MindscapeCloudChannelBindingPanel&target_capability=yogacoach',
      {},
      config,
      {
        resolveWorkspaceCapabilityPolicy: async () => ({
          capabilityAllowed: true,
          supported: true,
          allowedPathRules: [
            {
              type: 'regex',
              value: /^\/workspaces\/[^/]+\/capability-ui-hosts\/yogacoach(?:\/.*)?$/,
            },
          ],
        }),
      },
    );

    expect(denied).toMatchObject({
      allowed: false,
      reason: 'mobile_workbench_gateway_path_not_allowed',
      status_code: 404,
    });
  });
});
