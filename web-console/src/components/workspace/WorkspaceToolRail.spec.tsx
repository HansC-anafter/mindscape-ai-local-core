import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { WorkspaceToolRail } from './WorkspaceToolRail';

describe('WorkspaceToolRail', () => {
  it('renders grouped workspace tools without owning pack-specific behavior', () => {
    render(
      <WorkspaceToolRail
        ariaLabel="Workspace tools"
        groups={[
          {
            id: 'object',
            label: 'Select',
            testId: 'object-group',
            children: <button type="button">Object</button>,
          },
          {
            id: 'flow',
            label: 'Flow',
            testId: 'flow-group',
            children: <button type="button">Flow</button>,
          },
        ]}
      />,
    );

    expect(screen.getByTestId('workspace-tool-rail')).toHaveAttribute(
      'data-workspace-tool-rail',
      'true',
    );
    expect(screen.getByTestId('object-group')).toHaveTextContent('Select');
    expect(screen.getByTestId('flow-group')).toHaveTextContent('Flow');
    expect(screen.getByRole('button', { name: 'Object' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Flow' })).toBeInTheDocument();
  });

  it('supports bottom placement for narrow workbench frames', () => {
    render(
      <WorkspaceToolRail
        ariaLabel="Workspace tools"
        placement="bottom"
        groups={[
          {
            id: 'runtime',
            label: 'Runtime',
            children: <button type="button">Runtime</button>,
          },
        ]}
      />,
    );

    expect(screen.getByTestId('workspace-tool-rail')).toHaveAttribute(
      'data-workspace-tool-rail-placement',
      'bottom',
    );
    expect(screen.getByTestId('workspace-tool-rail').className).toContain('border-t');
  });
});
