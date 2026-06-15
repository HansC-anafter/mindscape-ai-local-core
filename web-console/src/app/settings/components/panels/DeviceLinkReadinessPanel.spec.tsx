import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DeviceLinkReadinessPanel } from './DeviceLinkReadinessPanel';

describe('DeviceLinkReadinessPanel', () => {
  it('shows local-core device guidance and the pack workbench handoff', () => {
    render(<DeviceLinkReadinessPanel workspaceId="ws_device" />);

    expect(screen.getByTestId('device-link-readiness-panel')).toBeInTheDocument();
    expect(screen.getByText('Device Link readiness')).toBeInTheDocument();
    expect(screen.getByText('Motion Source owns pairing')).toBeInTheDocument();
    expect(screen.getByText('Yoga/Dance owns practice')).toBeInTheDocument();
    expect(screen.getByText('Requires trusted LAN HTTPS')).toBeInTheDocument();
    expect(screen.getByText('node web-console/dev-proxy/device-link-https-readiness.mjs')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Open Motion Source rail/i })).toHaveAttribute(
      'href',
      '/workspaces/ws_device?tool=motion_source',
    );
  });
});
