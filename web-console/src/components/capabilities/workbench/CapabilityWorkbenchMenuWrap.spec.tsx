import '@testing-library/jest-dom/vitest';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CapabilityWorkbenchMenuWrap } from './CapabilityWorkbenchMenuWrap';

describe('CapabilityWorkbenchMenuWrap', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders all menu levels inline on desktop', () => {
    render(
      <CapabilityWorkbenchMenuWrap
        ariaLabel="Pack navigation"
        primarySlot={<button type="button">Accounts</button>}
        secondarySlot={<button type="button">Targets</button>}
        trailingSlot={<button type="button">Grid</button>}
      />,
    );

    expect(screen.getByTestId('capability-workbench-menu-wrap')).toHaveAttribute('data-workbench-placement', 'desktop');
    expect(screen.getByRole('button', { name: 'Accounts' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Targets' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Grid' })).toBeInTheDocument();
  });

  it('collapses mobile menu levels behind one shared toggle', async () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({
      matches: true,
      media: '(max-width: 767px)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));

    render(
      <CapabilityWorkbenchMenuWrap
        ariaLabel="Pack navigation"
        activeLabel="Accounts / Targets"
        primarySlot={<button type="button">Accounts</button>}
        secondarySlot={<button type="button">Targets</button>}
      />,
    );

    const wrap = await screen.findByTestId('capability-workbench-menu-wrap');
    expect(wrap).toHaveAttribute('data-workbench-placement', 'mobile');
    expect(wrap).toHaveAttribute('data-mobile-collapsed', 'true');
    expect(screen.getByTestId('capability-workbench-menu-wrap-mobile-summary-row').className).toContain('pr-12');
    expect(screen.queryByRole('button', { name: 'Accounts' })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Expand Pack navigation' }));

    expect(wrap).toHaveAttribute('data-mobile-collapsed', 'false');
    expect(screen.getByRole('button', { name: 'Accounts' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Targets' })).toBeInTheDocument();
  });
});
