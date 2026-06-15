import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { usePathname } from 'next/navigation';

import WorkspaceLayout from './layout';

vi.mock('next/navigation', () => ({
  usePathname: vi.fn(),
}));

describe('WorkspaceLayout', () => {
  it('preserves a fixed-height flex scroll chain for capability surface routes', () => {
    vi.mocked(usePathname).mockReturnValue('/workspaces/ws_test/capability-ui-hosts/ig/main');

    render(
      <WorkspaceLayout params={{ workspaceId: 'ws_test' }}>
        <section data-testid="capability-surface">Capability surface</section>
      </WorkspaceLayout>,
    );

    const main = screen.getByTestId('capability-surface').closest('main');

    expect(main).toHaveClass('flex', 'min-h-0', 'flex-1', 'overflow-hidden');
    expect(main?.parentElement).toHaveClass('relative', 'flex', 'min-h-0', 'flex-1', 'overflow-hidden');
    expect(main?.parentElement?.parentElement).toHaveClass('h-dvh');
  });
});
