'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';

import { PerformanceDirectionStartSurface } from '@/app/capabilities/performance_direction/components/storyboardEditor/PerformanceDirectionStartSurface';
import {
  readResponseDetail,
  resolveCapabilityApiBase,
} from '@/app/capabilities/performance_direction/components/storyboardEditor/apiUtils';
import type {
  DirectionSessionSummaryRecord,
  DirectorCompileResultRecord,
  PdStartContextCardRecord,
} from '@/app/capabilities/performance_direction/components/storyboardEditor/types';
import {
  AOLRuntimeShell,
} from '@/components/capabilities/aol-runtime-shell/AOLRuntimeShell';
import {
  buildCapabilitySurfaceId,
} from '@/components/capabilities/aol-runtime-shell/runtimeShellState';
import { getApiBaseUrl } from '@/lib/api-url';

type PerformanceDirectionLauncherHostProps = {
  workspaceId: string;
  sessionRouteBasePath: string;
};

function parseReferenceIdInput(value: string): string[] {
  return String(value || '')
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function buildStartContextCards({
  workspaceId,
  fallbackSessionId,
}: {
  workspaceId: string;
  fallbackSessionId: string;
}): PdStartContextCardRecord[] {
  if (typeof window === 'undefined' || !workspaceId.trim()) {
    return [];
  }

  const trimmedWorkspaceId = workspaceId.trim();
  const igSessionId =
    window.localStorage.getItem(`ig.references.scene_preview.pd_session:${trimmedWorkspaceId}`) || '';
  const igProjectId =
    window.localStorage.getItem(`ig.references.scene_preview.project:${trimmedWorkspaceId}`) || '';
  const igSceneScope =
    window.localStorage.getItem(`ig.references.scene_preview.scope:${trimmedWorkspaceId}`) || '';
  const igVariantId =
    window.localStorage.getItem(`ig.references.scene_preview.variant:${trimmedWorkspaceId}`) || '';
  const cards: PdStartContextCardRecord[] = [];

  if (igSessionId.trim()) {
    cards.push({
      id: `ig-scene-preview-${trimmedWorkspaceId}`,
      title: 'Continue IG Scene Preview Session',
      summary: [
        igProjectId.trim() ? `Project ${igProjectId.trim()}` : '',
        igSceneScope.trim() ? `scope ${igSceneScope.trim()}` : '',
        igVariantId.trim() ? `variant ${igVariantId.trim()}` : '',
      ]
        .filter(Boolean)
        .join(' · ') || 'Resume the PD session configured from IG scene preview.',
      sourceLabel: 'IG continuation',
      sessionId: igSessionId.trim(),
      projectId: igProjectId.trim() || undefined,
      sceneScope: igSceneScope.trim() || undefined,
      variantId: igVariantId.trim() || undefined,
      actionLabel: 'Resume in PD',
    });
  }

  if (fallbackSessionId.trim() && fallbackSessionId.trim() !== igSessionId.trim()) {
    cards.push({
      id: `session-loader-${fallbackSessionId.trim()}`,
      title: 'Continue Current Session Draft',
      summary: 'Use the currently selected session id and continue into the PD editor.',
      sourceLabel: 'Session handoff',
      sessionId: fallbackSessionId.trim(),
      actionLabel: 'Open session',
    });
  }

  return cards;
}

export default function PerformanceDirectionLauncherHost({
  workspaceId,
  sessionRouteBasePath,
}: PerformanceDirectionLauncherHostProps) {
  const router = useRouter();
  const pathname = usePathname();
  const apiUrl = getApiBaseUrl();
  const baseApiUrl = useMemo(() => resolveCapabilityApiBase(apiUrl), [apiUrl]);
  const normalizedSessionRouteBasePath = sessionRouteBasePath.trim().replace(/\/$/, '');

  const [sessionId, setSessionId] = useState('');
  const [loadError, setLoadError] = useState<string | null>(null);
  const [recentSessions, setRecentSessions] = useState<DirectionSessionSummaryRecord[]>([]);
  const [recentSessionsLoading, setRecentSessionsLoading] = useState(false);
  const [recentSessionsError, setRecentSessionsError] = useState<string | null>(null);
  const [createIntentSummary, setCreateIntentSummary] = useState('');
  const [createReferenceIds, setCreateReferenceIds] = useState('');
  const [creatingSession, setCreatingSession] = useState(false);
  const [createSessionError, setCreateSessionError] = useState<string | null>(null);
  const [createSessionResult, setCreateSessionResult] = useState<string | null>(null);
  const [compilingDirector, setCompilingDirector] = useState(false);
  const [directorCompileError, setDirectorCompileError] = useState<string | null>(null);
  const [directorCompileResult, setDirectorCompileResult] =
    useState<DirectorCompileResultRecord | null>(null);

  const startContextCards = useMemo(
    () =>
      buildStartContextCards({
        workspaceId,
        fallbackSessionId: sessionId,
      }),
    [sessionId, workspaceId],
  );

  const openSession = useCallback(
    (nextSessionId: string) => {
      const trimmedSessionId = nextSessionId.trim();
      if (!trimmedSessionId) {
        setLoadError('Enter a Direction session ID first.');
        return;
      }
      setLoadError(null);
      router.push(`${normalizedSessionRouteBasePath}/${encodeURIComponent(trimmedSessionId)}`);
    },
    [normalizedSessionRouteBasePath, router],
  );

  const loadRecentSessions = useCallback(async () => {
    const targetWorkspaceId = workspaceId.trim();
    if (!targetWorkspaceId) {
      setRecentSessions([]);
      setRecentSessionsError(null);
      return;
    }

    setRecentSessionsLoading(true);
    setRecentSessionsError(null);
    try {
      const response = await fetch(
        `${baseApiUrl}/sessions?workspace_id=${encodeURIComponent(targetWorkspaceId)}&limit=8`,
        {
          credentials: 'same-origin',
        },
      );
      if (!response.ok) {
        throw new Error(await readResponseDetail(response));
      }
      const payload = await response.json();
      setRecentSessions((payload.sessions || []) as DirectionSessionSummaryRecord[]);
    } catch (error) {
      setRecentSessions([]);
      setRecentSessionsError(error instanceof Error ? error.message : 'load_recent_sessions_failed');
    } finally {
      setRecentSessionsLoading(false);
    }
  }, [baseApiUrl, workspaceId]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadRecentSessions();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadRecentSessions]);

  const handleCompileDirector = useCallback(async () => {
    const creatorIntent = createIntentSummary.trim();
    if (!creatorIntent) {
      setDirectorCompileError('creator_intent_missing');
      setDirectorCompileResult(null);
      return;
    }

    setCompilingDirector(true);
    setDirectorCompileError(null);
    setDirectorCompileResult(null);
    try {
      const response = await fetch(`${baseApiUrl}/director-compile`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: workspaceId.trim(),
          creator_intent: creatorIntent,
          reference_ids: parseReferenceIdInput(createReferenceIds),
        }),
      });
      if (!response.ok) {
        throw new Error(await readResponseDetail(response));
      }
      const payload = (await response.json()) as DirectorCompileResultRecord;
      setDirectorCompileResult(payload);
    } catch (error) {
      setDirectorCompileError(error instanceof Error ? error.message : 'director_compile_failed');
    } finally {
      setCompilingDirector(false);
    }
  }, [baseApiUrl, createIntentSummary, createReferenceIds, workspaceId]);

  const handleCreateSession = useCallback(async () => {
    const targetWorkspaceId = workspaceId.trim();
    if (!targetWorkspaceId) {
      setCreateSessionError('workspace_id_missing');
      return;
    }

    setCreatingSession(true);
    setCreateSessionError(null);
    setCreateSessionResult(null);
    try {
      const response = await fetch(`${baseApiUrl}/sessions`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: targetWorkspaceId,
          intent: createIntentSummary.trim()
            ? {
                summary: createIntentSummary.trim(),
              }
            : undefined,
          reference_ids: parseReferenceIdInput(createReferenceIds),
        }),
      });
      if (!response.ok) {
        throw new Error(await readResponseDetail(response));
      }
      const payload = await response.json();
      const createdSessionId = String(payload?.session?.session_id || '').trim();
      if (createdSessionId) {
        setCreateSessionResult(`Created ${createdSessionId}. Opening PD editor...`);
        openSession(createdSessionId);
        return;
      }
      setCreateSessionResult('Direction session created.');
      await loadRecentSessions();
    } catch (error) {
      setCreateSessionError(error instanceof Error ? error.message : 'create_direction_session_failed');
    } finally {
      setCreatingSession(false);
    }
  }, [
    baseApiUrl,
    createIntentSummary,
    createReferenceIds,
    loadRecentSessions,
    openSession,
    workspaceId,
  ]);

  const handleContinueFromContext = useCallback(
    (card: PdStartContextCardRecord) => {
      if (card.sessionId?.trim()) {
        openSession(card.sessionId);
      }
    },
    [openSession],
  );

  return (
    <AOLRuntimeShell
      apiUrl={apiUrl}
      workspaceId={workspaceId}
      capabilityCode="performance_direction"
      route={pathname}
      surfaceId={buildCapabilitySurfaceId(
        'performance_direction',
        'PerformanceDirectionStartSurface',
      )}
    >
      {() => (
        <div
          className="h-full overflow-y-auto overflow-x-hidden bg-stone-100 text-slate-900"
          data-testid="pd-launcher-scroll-shell"
        >
          <div className="mx-auto max-w-[1800px] px-4 py-6 md:px-6">
            <PerformanceDirectionStartSurface
              workspaceLabel={workspaceId}
              sessionId={sessionId}
              onChangeSessionId={setSessionId}
              onLoadStoryboard={() => openSession(sessionId)}
              loading={false}
              loadError={loadError}
              recentSessions={recentSessions}
              recentSessionsLoading={recentSessionsLoading}
              recentSessionsError={recentSessionsError}
              onOpenRecentSession={openSession}
              createIntentSummary={createIntentSummary}
              onChangeCreateIntentSummary={setCreateIntentSummary}
              createReferenceIds={createReferenceIds}
              onChangeCreateReferenceIds={setCreateReferenceIds}
              creatingSession={creatingSession}
              createSessionError={createSessionError}
              createSessionResult={createSessionResult}
              onCreateSession={() => void handleCreateSession()}
              compilingDirector={compilingDirector}
              directorCompileError={directorCompileError}
              directorCompileResult={directorCompileResult}
              onCompileDirector={() => void handleCompileDirector()}
              startContextCards={startContextCards}
              onContinueFromContext={handleContinueFromContext}
            />
          </div>
        </div>
      )}
    </AOLRuntimeShell>
  );
}
