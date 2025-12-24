'use client';

import React from 'react';
import { BaseModal } from '@/components/BaseModal';
import SandboxViewer from './SandboxViewer';

interface SandboxModalProps {
  isOpen: boolean;
  onClose: () => void;
  workspaceId: string;
  sandboxId: string;
  projectId?: string;
  executionId?: string;
  initialFile?: string | null;
}

export default function SandboxModal({
  isOpen,
  onClose,
  workspaceId,
  sandboxId,
  projectId,
  executionId,
  initialFile,
}: SandboxModalProps) {
  if (!isOpen) return null;

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      title="Sandbox Viewer"
      maxWidth="max-w-6xl"
    >
      <div className="h-[80vh]">
        <SandboxViewer
          workspaceId={workspaceId}
          sandboxId={sandboxId}
          projectId={projectId}
          executionId={executionId}
          initialFile={initialFile}
        />
      </div>
    </BaseModal>
  );
}

