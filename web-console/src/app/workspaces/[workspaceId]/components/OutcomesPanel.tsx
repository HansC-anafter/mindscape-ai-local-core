'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useConflictHandler } from '@/hooks/useConflictHandler';
import { useToast } from '@/components/Toast';
import { getInstalledCapabilities } from '@/lib/capability-packs/installed-capabilities-cache';

import {
  buildArtifactCopyUrl,
  buildArtifactExternalUrl,
  buildArtifactFileUrl,
  buildExecutionDetailUrl,
  buildExecutionSandboxUrl,
  fetchWorkspaceArtifacts,
} from './outcomesPanelApi';
import { OutcomesPanelView } from './OutcomesPanelView';
import {
  collectMatchingComponents,
  extractSandboxIdFromPath,
  resolveArtifactDisplayInfo,
  resolveSandboxOpenTarget,
} from './outcomesPanelState';
import type {
  Artifact,
  MatchingCapabilityComponent,
  OutcomesPanelProps,
  SandboxModalState,
} from './outcomesPanelTypes';

export type { Artifact } from './outcomesPanelTypes';

const HIGHLIGHT_CLEAR_MS = 5000;
const CHAT_UPDATE_DEBOUNCE_MS = 1000;
const CHAT_UPDATE_FALLBACK_MS = 5000;

const closedSandboxModal: SandboxModalState = {
  show: false,
  sandboxId: null,
  initialFile: null,
  executionId: null,
};

export default function OutcomesPanel({
  workspaceId,
  apiUrl,
  onArtifactClick,
}: OutcomesPanelProps) {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [highlightedArtifactIds, setHighlightedArtifactIds] = useState<Set<string>>(new Set());
  const previousArtifactsRef = useRef<Artifact[]>([]);
  const { conflictDialog, handleConflict } = useConflictHandler();
  const { showToast, ToastComponent } = useToast();
  const [sandboxModal, setSandboxModal] = useState<SandboxModalState>(closedSandboxModal);
  const [installedCapabilities, setInstalledCapabilities] = useState<any[]>([]);
  const [matchingComponents, setMatchingComponents] = useState<MatchingCapabilityComponent[]>([]);
  const loadArtifactsInFlightRef = useRef<Promise<void> | null>(null);

  const loadArtifacts = useCallback(async () => {
    if (loadArtifactsInFlightRef.current) {
      return loadArtifactsInFlightRef.current;
    }

    const request = (async () => {
      try {
        setLoading(true);
        setError(null);
        const newArtifacts = await fetchWorkspaceArtifacts(apiUrl, workspaceId);

        if (previousArtifactsRef.current.length > 0) {
          const previousIds = new Set(previousArtifactsRef.current.map((artifact) => artifact.id));
          const newArtifactsList = newArtifacts.filter((artifact: Artifact) => !previousIds.has(artifact.id));

          if (newArtifactsList.length > 0) {
            if (newArtifactsList.length === 1) {
              const newArtifact = newArtifactsList[0];
              showToast({
                message: `Added 1 outcome: "${newArtifact.title}"`,
                type: 'success',
                duration: 5000,
                action: onArtifactClick ? {
                  label: 'Open Outcome Card',
                  onClick: () => onArtifactClick(newArtifact),
                } : undefined,
              });
            } else {
              showToast({
                message: `Added ${newArtifactsList.length} outcomes`,
                type: 'success',
                duration: 5000,
              });
            }

            const newIds = new Set<string>(newArtifactsList.map((artifact: Artifact) => artifact.id));
            setHighlightedArtifactIds(newIds);
            setTimeout(() => {
              setHighlightedArtifactIds(new Set());
            }, HIGHLIGHT_CLEAR_MS);
          }
        }

        setArtifacts(newArtifacts);
        previousArtifactsRef.current = newArtifacts;
      } catch (err) {
        console.error('Failed to load artifacts:', err);
        setError(err instanceof Error ? err.message : 'Failed to load artifacts');
      } finally {
        setLoading(false);
      }
    })();

    loadArtifactsInFlightRef.current = request;
    try {
      await request;
    } finally {
      if (loadArtifactsInFlightRef.current === request) {
        loadArtifactsInFlightRef.current = null;
      }
    }
  }, [apiUrl, workspaceId, showToast, onArtifactClick]);

  useEffect(() => {
    const loadCapabilities = async () => {
      try {
        const capabilities = await getInstalledCapabilities(apiUrl, workspaceId);
        setInstalledCapabilities(capabilities);
      } catch {
        // Capabilities are optional for the outcomes list.
      }
    };

    loadCapabilities();
  }, [apiUrl, workspaceId]);

  useEffect(() => {
    if (artifacts.length === 0 || installedCapabilities.length === 0) {
      setMatchingComponents([]);
      return;
    }
    setMatchingComponents(collectMatchingComponents(artifacts, installedCapabilities));
  }, [artifacts, installedCapabilities]);

  useEffect(() => {
    loadArtifacts();

    let debounceTimer: ReturnType<typeof setTimeout> | null = null;
    let isPending = false;
    let timeoutTimer: ReturnType<typeof setTimeout> | null = null;
    let lastRefreshTime = Date.now();

    const setupTimeoutRefresh = () => {
      if (timeoutTimer) {
        clearTimeout(timeoutTimer);
      }
      timeoutTimer = setTimeout(() => {
        const timeSinceLastRefresh = Date.now() - lastRefreshTime;
        if (timeSinceLastRefresh >= CHAT_UPDATE_FALLBACK_MS && !isPending) {
          isPending = true;
          loadArtifacts().finally(() => {
            isPending = false;
            lastRefreshTime = Date.now();
          });
        }
      }, CHAT_UPDATE_FALLBACK_MS);
    };

    const handleChatUpdate = () => {
      lastRefreshTime = Date.now();
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
      debounceTimer = setTimeout(() => {
        if (!isPending) {
          isPending = true;
          loadArtifacts().finally(() => {
            isPending = false;
            lastRefreshTime = Date.now();
            setupTimeoutRefresh();
          });
        }
      }, CHAT_UPDATE_DEBOUNCE_MS);
      setupTimeoutRefresh();
    };

    setupTimeoutRefresh();

    window.addEventListener('workspace-chat-updated', handleChatUpdate);
    return () => {
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
      if (timeoutTimer) {
        clearTimeout(timeoutTimer);
      }
      window.removeEventListener('workspace-chat-updated', handleChatUpdate);
    };
  }, [loadArtifacts]);

  const handleManualRefresh = async () => {
    try {
      await loadArtifacts();
      showToast({
        message: 'Outcome list refreshed',
        type: 'success',
        duration: 2000,
      });
    } catch {
      showToast({
        message: 'Refresh failed. Please try again later.',
        type: 'error',
        duration: 3000,
      });
    }
  };

  const handleCopy = async (artifact: Artifact, event: React.MouseEvent) => {
    event.stopPropagation();
    try {
      const response = await fetch(buildArtifactCopyUrl(apiUrl, workspaceId, artifact.id), { method: 'POST' });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        await handleConflict(
          { ...errorData, status: response.status },
          async () => {
            const retryResponse = await fetch(buildArtifactCopyUrl(apiUrl, workspaceId, artifact.id, true), { method: 'POST' });
            if (!retryResponse.ok) {
              throw new Error('Failed to copy artifact');
            }
            return await retryResponse.json();
          },
          async (data) => {
            await navigator.clipboard.writeText(data.content);
            showToast({
              message: 'Copied to clipboard',
              type: 'success',
              duration: 3000,
            });
          },
          (err) => {
            console.error('Failed to copy artifact:', err);
            showToast({
              message: 'Copy failed. Please try again.',
              type: 'error',
              duration: 3000,
            });
          },
        );
        return;
      }

      const data = await response.json();
      await navigator.clipboard.writeText(data.content);
      showToast({
        message: 'Copied to clipboard',
        type: 'success',
        duration: 3000,
      });
    } catch (err) {
      console.error('Failed to copy artifact:', err);
      showToast({
        message: 'Copy failed. Please try again.',
        type: 'error',
        duration: 3000,
      });
    }
  };

  const handleOpenExternal = async (artifact: Artifact, event: React.MouseEvent) => {
    event.stopPropagation();
    try {
      const response = await fetch(buildArtifactExternalUrl(apiUrl, workspaceId, artifact.id));
      if (!response.ok) {
        throw new Error('Failed to get external URL');
      }
      const data = await response.json();
      window.open(data.url, '_blank');
    } catch (err) {
      console.error('Failed to open external URL:', err);
      showToast({
        message: 'Open failed. Please try again.',
        type: 'error',
        duration: 3000,
      });
    }
  };

  const handleArtifactFileClick = (artifact: Artifact, event: React.MouseEvent) => {
    event.stopPropagation();
    const display = resolveArtifactDisplayInfo(artifact);
    const metadata = artifact.metadata && typeof artifact.metadata === 'object' ? artifact.metadata as any : null;
    const actualFilePath = (artifact as any).file_path || (metadata && metadata.actual_file_path);
    const sandboxTarget = resolveSandboxOpenTarget(artifact, display.executionId);

    if (sandboxTarget) {
      setSandboxModal({
        show: true,
        sandboxId: sandboxTarget.sandboxId,
        initialFile: sandboxTarget.relativeFilePath,
        executionId: sandboxTarget.executionId,
      });
    } else if (onArtifactClick) {
      onArtifactClick(artifact);
    } else if (display.filePath || actualFilePath) {
      window.open(buildArtifactFileUrl(apiUrl, workspaceId, artifact.id), '_blank');
    }
  };

  const handleSandboxClick = (artifact: Artifact, event: React.MouseEvent) => {
    event.stopPropagation();
    const display = resolveArtifactDisplayInfo(artifact);

    if (display.executionId) {
      window.open(buildExecutionDetailUrl(workspaceId, display.executionId), '_blank');
      return;
    }

    const sandboxId = extractSandboxIdFromPath(display.filePath);
    if (sandboxId) {
      window.open(buildExecutionSandboxUrl(workspaceId, sandboxId), '_blank');
      return;
    }

    handleArtifactFileClick(artifact, event);
  };

  const handleCloseSandbox = () => {
    setSandboxModal(closedSandboxModal);
  };

  return (
    <OutcomesPanelView
      artifacts={artifacts}
      conflictDialog={conflictDialog}
      error={error}
      highlightedArtifactIds={highlightedArtifactIds}
      loading={loading}
      matchingComponents={matchingComponents}
      sandboxModal={sandboxModal}
      ToastComponent={ToastComponent}
      workspaceId={workspaceId}
      onArtifactFileClick={handleArtifactFileClick}
      onCloseSandbox={handleCloseSandbox}
      onOpenExternal={handleOpenExternal}
      onSandboxClick={handleSandboxClick}
    />
  );
}
