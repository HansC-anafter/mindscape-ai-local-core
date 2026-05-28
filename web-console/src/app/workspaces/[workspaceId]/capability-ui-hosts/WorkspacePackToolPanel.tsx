'use client';

import React from 'react';

import { PackPanel } from '../components/PackPanel';

interface WorkspacePackToolPanelProps {
  workspaceId: string;
  apiUrl: string;
}

export default function WorkspacePackToolPanel({
  workspaceId,
  apiUrl,
}: WorkspacePackToolPanelProps) {
  return (
    <div className="h-full min-h-0">
      <PackPanel workspaceId={workspaceId} apiUrl={apiUrl} />
    </div>
  );
}
