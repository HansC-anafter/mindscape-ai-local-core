'use client';

import React from 'react';
import { useParams } from 'next/navigation';
import { PlaybookSurface } from '@/components/playbooks/PlaybookSurface';

/**
 * PlaybookSurfacePage - Dynamic page for playbook surfaces
 *
 * Renders the playbook surface based on the playbookCode in the URL.
 * The actual components are loaded from registered playbook packages.
 */
export default function PlaybookSurfacePage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const playbookCode = params.playbookCode as string;

  if (!playbookCode) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        Playbook code not found
      </div>
    );
  }

  return (
    <PlaybookSurface
      playbookCode={playbookCode}
      workspaceId={workspaceId}
    />
  );
}

