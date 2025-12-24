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
  initialFile?: string | null;
}

export default function SandboxModalWrapper({
  isOpen,
  onClose,
  workspaceId,
  sandboxId,
  projectId,
  executionId,
  initialFile,
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
      initialFile={initialFile}
    />
  );
}
