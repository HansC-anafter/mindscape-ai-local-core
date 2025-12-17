'use client';

import React from 'react';
import ExecutionChatPanel from '../ExecutionChatPanel';
import type { PlaybookMetadata } from './types/execution';

export interface ExecutionChatWrapperProps {
  executionId: string;
  workspaceId: string;
  apiUrl: string;
  playbookMetadata: PlaybookMetadata | null;
  executionStatus?: string;
  runNumber: number;
}

export default function ExecutionChatWrapper({
  executionId,
  workspaceId,
  apiUrl,
  playbookMetadata,
  executionStatus,
  runNumber,
}: ExecutionChatWrapperProps) {
  if (!playbookMetadata?.supports_execution_chat) {
    return null;
  }

  return (
    <div className="flex-1 overflow-hidden">
      <ExecutionChatPanel
        key={executionId}
        executionId={executionId}
        workspaceId={workspaceId}
        apiUrl={apiUrl}
        playbookMetadata={playbookMetadata}
        executionStatus={executionStatus}
        runNumber={runNumber}
        collapsible={true}
        defaultCollapsed={false}
      />
    </div>
  );
}
