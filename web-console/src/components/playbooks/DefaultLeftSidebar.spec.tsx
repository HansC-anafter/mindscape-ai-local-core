import React from 'react';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import DefaultLeftSidebar from './DefaultLeftSidebar';

vi.mock('../../lib/api-url', () => ({
  getApiBaseUrl: () => 'http://api.test',
}));

vi.mock('@/lib/i18n', () => ({
  useT: () => (() => null),
}));

vi.mock('../../app/workspaces/components/TimelinePanel', async () => {
  const ReactModule = await import('react');
  return {
    default: () => ReactModule.createElement('div', { 'data-testid': 'timeline-panel' }, 'Timeline'),
  };
});

vi.mock('../../app/workspaces/[workspaceId]/components/OutcomesPanel', async () => {
  const ReactModule = await import('react');
  return {
    default: () => ReactModule.createElement('div', { 'data-testid': 'outcomes-panel' }, 'Outcomes'),
  };
});

describe('DefaultLeftSidebar', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('keeps Pack out of the default left sidebar', () => {
    render(<DefaultLeftSidebar workspaceId="ws_test" />);

    expect(screen.getByRole('button', { name: /Scheduling/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Outcomes/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Pack/ })).toBeNull();
  });
});
