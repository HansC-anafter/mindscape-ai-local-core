import '@testing-library/jest-dom/vitest';
import React from 'react';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CapabilityWorkbenchCommandHeader } from './CapabilityWorkbenchCommandHeader';

describe('CapabilityWorkbenchCommandHeader', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the fixed command slots in order', () => {
    render(
      <CapabilityWorkbenchCommandHeader
        brandSlot={<span>Demo Capability</span>}
        modeSlot={<button type="button">Inspect</button>}
        primaryToolbarSlot={<button type="button">Select</button>}
        contextToolbarSlot={<span>Item item01</span>}
        statusSlot={<span>Ready</span>}
        utilitySlot={<button type="button">Load</button>}
      />,
    );

    const header = screen.getByTestId('capability-workbench-command-header');
    expect(header).toHaveClass('min-h-[56px]');
    expect(header.className).toContain('flex-wrap');
    expect(screen.getByTestId('capability-workbench-command-header-brand')).toHaveTextContent('Demo Capability');
    expect(screen.getByTestId('capability-workbench-command-header-mode')).toHaveTextContent('Inspect');
    expect(screen.getByTestId('capability-workbench-command-header-primary-toolbar')).toHaveTextContent('Select');
    expect(screen.getByTestId('capability-workbench-command-header-context-toolbar')).toHaveTextContent('Item item01');
    expect(screen.getByTestId('capability-workbench-command-header-status')).toHaveTextContent('Ready');
    expect(screen.getByTestId('capability-workbench-command-header-utility')).toHaveTextContent('Load');
  });

  it('does not render metadata when the pack does not provide metadata slots', () => {
    render(
      <CapabilityWorkbenchCommandHeader
        brandSlot={<span>Demo Desk</span>}
        modeSlot={<span>Generate</span>}
      />,
    );

    expect(screen.queryByText(/Workspace:/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Storyboard:/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Artifact:/i)).not.toBeInTheDocument();
    expect(screen.queryByTestId('capability-workbench-command-header-utility')).not.toBeInTheDocument();
  });

  it('uses the compact mobile layout only when requested by the pack', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({
      matches: true,
      media: '(max-width: 767px)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));

    render(
      <CapabilityWorkbenchCommandHeader
        brandSlot={<span>Demo Desk</span>}
        modeSlot={<span>Generate</span>}
        contextToolbarSlot={<span>Grid / All</span>}
        statusSlot={<span>Ready</span>}
        utilitySlot={<button type="button">Refresh</button>}
        mobileVariant="compact"
      />,
    );

    expect(screen.getByTestId('capability-workbench-command-header')).toHaveAttribute('data-mobile-variant', 'compact');
    expect(screen.getByTestId('capability-workbench-command-header-mobile-meta-strip')).toBeInTheDocument();
    expect(screen.getByTestId('capability-workbench-command-header-context-toolbar')).toHaveTextContent('Grid / All');
    expect(screen.getByTestId('capability-workbench-command-header-status')).toHaveTextContent('Ready');
  });
});
