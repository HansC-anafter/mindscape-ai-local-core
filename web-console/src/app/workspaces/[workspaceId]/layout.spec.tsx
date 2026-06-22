import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import WorkspaceLayout from './layout';

vi.mock('next/navigation', () => ({
  usePathname: () => '/workspaces/ws_test/capability-ui-hosts/demo_capability',
}));

describe('WorkspaceLayout', () => {
  it('keeps capability routes on the lightweight viewport seam without loading workspace chrome', () => {
    render(
      <WorkspaceLayout params={{ workspaceId: 'ws_test' }}>
        <section data-testid="capability-surface">Capability surface</section>
      </WorkspaceLayout>,
    );

    expect(screen.getByTestId('capability-surface')).toHaveTextContent('Capability surface');
    expect(screen.getByTestId('capability-surface').closest('main')).toHaveClass('flex');
  });
});
