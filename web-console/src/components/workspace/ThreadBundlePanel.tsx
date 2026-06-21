'use client';

import React, { useCallback, useState } from 'react';

import { useThreadBundle } from '@/hooks/useThreadBundle';
import { getApiBaseUrl } from '@/lib/api-url';

import { ThreadBundlePanelView } from './threadBundlePanel/ThreadBundlePanelView';
import type {
  BundleSection,
  ThreadBundlePanelProps,
} from './threadBundlePanel/types';

export function ThreadBundlePanel({
  threadId,
  workspaceId,
  isOpen,
  onClose,
  apiUrl = getApiBaseUrl(),
  embedded = false,
}: ThreadBundlePanelProps) {
  const { bundle, loading, error } = useThreadBundle(workspaceId, threadId, apiUrl);
  const [activeSection, setActiveSection] = useState<BundleSection>('overview');

  const handleReferenceAdded = useCallback(() => {
    window.location.reload();
  }, []);

  if (!isOpen) return null;

  return (
    <ThreadBundlePanelView
      activeSection={activeSection}
      apiUrl={apiUrl}
      bundle={bundle}
      embedded={embedded}
      error={error}
      loading={loading}
      threadId={threadId}
      workspaceId={workspaceId}
      onClose={onClose}
      onReferenceAdded={handleReferenceAdded}
      onSectionChange={setActiveSection}
    />
  );
}
