'use client';

import React from 'react';
import { getPlaybookRegistry } from '@/playbook';
import { SurfaceLayout } from './SurfaceLayout';

interface PlaybookSurfaceProps {
  playbookCode: string;
  workspaceId: string;
}

/**
 * PlaybookSurface - Renders the main surface for a playbook
 *
 * Dynamically renders the main surface components registered by the playbook.
 * Uses SurfaceLayout to arrange components according to the playbook's layout config.
 */
export function PlaybookSurface({
  playbookCode,
  workspaceId
}: PlaybookSurfaceProps) {
  const registry = getPlaybookRegistry();
  const playbook = registry.get(playbookCode);

  if (!playbook || !playbook.uiLayout) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        Playbook surface not found
      </div>
    );
  }

  const { main_surface } = playbook.uiLayout;
  const { layout, components } = main_surface;

  return (
    <SurfaceLayout type={layout}>
      {components.map((componentConfig, index) => {
        const Component = registry.getComponent(
          playbookCode,
          componentConfig.type
        );

        if (!Component) {
          console.warn(
            `Component ${componentConfig.type} not found for playbook ${playbookCode}`
          );
          return null;
        }

        return (
          <Component
            key={componentConfig.type}
            workspaceId={workspaceId}
            playbookCode={playbookCode}
            config={componentConfig.config}
            position={componentConfig.position}
          />
        );
      })}
    </SurfaceLayout>
  );
}

