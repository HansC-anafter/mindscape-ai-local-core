'use client';

import React from 'react';

import { getApiBaseUrl } from '@/lib/api-url';
import { WorkspaceInteractionIngressProvider } from '@/lib/workspace-interaction/WorkspaceInteractionIngressProvider';

import { WorkspaceVoiceInteractionToolRegistration } from './WorkspaceVoiceInteractionToolRegistration';

export function WorkspaceInteractionIngressHost({
  workspaceId,
  children,
}: {
  workspaceId: string;
  children: React.ReactNode;
}) {
  return (
    <WorkspaceInteractionIngressProvider workspaceId={workspaceId}>
      <WorkspaceVoiceInteractionToolRegistration apiUrl={getApiBaseUrl()} />
      {children}
    </WorkspaceInteractionIngressProvider>
  );
}
