'use client';

import React from 'react';
import SandboxModal from '@/components/sandbox/SandboxModal';

export interface SandboxModalWrapperProps {
  isOpen: boolean;
  onClose: () => void;
  workspaceId: string;
  sandboxId: string;
  projectId?: string;
  executionId: string;
}

export default function SandboxModalWrapper({
  isOpen,
  onClose,
  workspaceId,
  sandboxId,
  projectId,
  executionId,
}: SandboxModalWrapperProps) {
  if (!isOpen || !sandboxId) {
    return null;
  }

  return (
    <SandboxModal
      isOpen={isOpen}
      onClose={onClose}
      workspaceId={workspaceId}
      sandboxId={sandboxId}
      projectId={projectId}
      executionId={executionId}
    />
  );
}
