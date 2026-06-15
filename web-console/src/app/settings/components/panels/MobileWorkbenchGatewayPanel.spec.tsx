import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MobileWorkbenchGatewayPanel } from './MobileWorkbenchGatewayPanel';

const getMock = vi.fn();

vi.mock('../../utils/settingsApi', () => ({
  settingsApi: {
    get: (...args: unknown[]) => getMock(...args),
  },
}));

describe('MobileWorkbenchGatewayPanel', () => {
  beforeEach(() => {
    getMock.mockReset();
    getMock.mockResolvedValue({
      status: 'ok',
      service: 'mobile-workbench-gateway',
      enabled: true,
      gateway: {
        enabled: true,
        reason: 'enabled',
        errors: [],
        allowed_prefix_rules: ['/favicon.ico'],
        allowed_regex_rules: [],
        extra_allowed_rules: [],
        extra_allowed_rules_count: 0,
        allowlist_emails: ['admin@mindscape.ai'],
        allowlist_groups: [],
        workspace_allowlist: ['ws-1'],
        public_origin: 'https://remote-workbench.mindscapeai.app',
        jwt_audience: ['remote-workbench'],
        jwt_issuer: ['https://identity.example.com'],
        jwt_clock_skew_seconds: 30,
        jwt_signature_verification_required: true,
        jwt_verify_enabled: true,
        jwt_public_key_configured: true,
        gateway_policy_enabled: true,
      },
    });
  });

  it('frames settings as diagnostics and points capability access back to the workspace pack policy workbench', async () => {
    render(<MobileWorkbenchGatewayPanel />);

    expect(await screen.findByText('Workspace capability access')).toBeInTheDocument();
    expect(screen.getByTestId('mobile-workbench-gateway-workspace-access-note')).toHaveTextContent(
      'Pack capability ingress is managed per workspace from the Pack panel through Gateway policy.',
    );
    expect(screen.getByText('Operator guardrails')).toBeInTheDocument();
    expect(screen.getByText('Workspace brakes')).toBeInTheDocument();
  });
});
