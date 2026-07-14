import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { MobileWorkbenchGatewayPanel } from './MobileWorkbenchGatewayPanel';

vi.mock('../../../../lib/api-url', () => ({
  getApiBaseUrl: () => 'http://api.test',
}));

const readyHealth = {
  status: 'ok',
  service: 'mobile-workbench-gateway',
  enabled: true,
  errors: [],
  gateway: {
    enabled: true,
    reason: 'strict_runtime_policy_ready',
    errors: [],
    public_origin: 'https://remote-workbench.mindscapeai.app',
    auth_config_source: 'runtime_policy',
    auth_config_fingerprint: 'sha256-example',
    remote_access_state: 'enforced',
    runtime_policy_revision: 4,
    startup_config_get_count: 1,
    remote_listener_ready: true,
    jwt_signature_verification_required: true,
    jwt_issuer_ready: true,
    jwt_audience_ready: true,
    effective_policy_cache_entries: 2,
    capability_support_cache_entries: 3,
    upstream_effective_policy_calls: 4,
    upstream_capability_support_calls: 5,
    upstream_in_flight: 0,
    upstream_rejected: 0,
    max_upstream_in_flight: 4,
  },
};

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response;
}

describe('MobileWorkbenchGatewayPanel', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(readyHealth)));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('is monitor-only, links to the owner, and never polls', async () => {
    render(<MobileWorkbenchGatewayPanel />);

    expect(await screen.findByText('Gateway readiness')).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      'http://api.test/api/v1/host/services/mobile-workbench-gateway/health',
      expect.objectContaining({ cache: 'no-store', signal: expect.any(AbortSignal) }),
    );
    expect(screen.getByTestId('mobile-workbench-gateway-policy-owner-note')).toHaveTextContent(
      'Global verified administrators are managed only from Remote Workbench Access.',
    );
    expect(screen.getByRole('link', { name: 'Remote Workbench Access' })).toHaveAttribute(
      'href',
      '/settings?tab=remote_workbench_access',
    );
    expect(screen.queryByText('Emails')).not.toBeInTheDocument();
    expect(screen.queryByText(/MOBILE_WORKBENCH_GATEWAY_JWT/)).not.toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('parses the intentional 503 diagnostics body and reports Blocked, not Disabled', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({
      ...readyHealth,
      status: 'blocked',
      errors: ['runtime_access_policy_not_loaded'],
      gateway: {
        ...readyHealth.gateway,
        reason: 'runtime_policy_unavailable',
        remote_listener_ready: false,
        jwt_issuer_ready: false,
      },
    }, 503));

    render(<MobileWorkbenchGatewayPanel />);

    expect(await screen.findByText('Blocked')).toBeInTheDocument();
    expect(screen.queryByText('Disabled')).not.toBeInTheDocument();
    expect(screen.getByText(/runtime_access_policy_not_loaded/)).toBeInTheDocument();
  });

  it('reports a transport failure instead of manufacturing an empty health object', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error('network unavailable'));

    render(<MobileWorkbenchGatewayPanel />);

    expect(await screen.findByRole('alert')).toHaveTextContent('network unavailable');
    expect(screen.queryByText('Disabled')).not.toBeInTheDocument();
  });

  it('rejects malformed health payloads', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse([]));

    render(<MobileWorkbenchGatewayPanel />);

    expect(await screen.findByRole('alert')).toHaveTextContent('malformed health payload');
  });

  it('aborts and reports the fixed 10 second timeout without retrying', async () => {
    vi.mocked(fetch).mockImplementationOnce(async (_url, init) => (
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          reject(new DOMException('aborted', 'AbortError'));
        });
      })
    ));

    render(<MobileWorkbenchGatewayPanel />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(await screen.findByRole('alert')).toHaveTextContent('timed out after 10 seconds');
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('aborts the in-flight request and suppresses state writes after unmount', async () => {
    let resolveResponse!: (response: Response) => void;
    let requestSignal: AbortSignal | undefined;
    vi.mocked(fetch).mockImplementationOnce(async (_url, init) => {
      requestSignal = init?.signal as AbortSignal;
      return new Promise<Response>((resolve) => {
        resolveResponse = resolve;
      });
    });

    const { unmount } = render(<MobileWorkbenchGatewayPanel />);
    await act(async () => Promise.resolve());
    unmount();

    expect(requestSignal?.aborted).toBe(true);
    await act(async () => {
      resolveResponse(jsonResponse(readyHealth));
      await Promise.resolve();
    });
  });
});
