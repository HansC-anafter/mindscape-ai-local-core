'use client';

import React from 'react';

import { useOptionalWorkspaceGlobalToolRail } from '@/app/workspaces/[workspaceId]/components/useWorkspaceGlobalToolRail';
import { useT } from '@/lib/i18n';
import {
  useWorkspaceInteractionIngress,
  useWorkspaceInteractionTargetRegistration,
} from '@/lib/workspace-interaction/WorkspaceInteractionIngressProvider';
import type { WorkspaceInteractionTarget } from '@/lib/workspace-interaction/workspaceInteractionTarget';
import {
  buildWorkspaceVoiceMeetingCommandContext,
  buildWorkspaceVoiceMeetingScope,
  ensureWorkspaceVoiceMeetingSession,
} from '@/lib/workspace-interaction/workspaceVoiceMeetingBootstrapClient';

import { createWorkspaceVoiceMeetingTarget } from './workspaceVoiceMeetingTarget';

export type WorkspaceVoiceMeetingBootstrapStatus =
  | 'idle'
  | 'starting'
  | 'ready'
  | 'failed';

type WorkspaceVoiceMeetingBootstrapValue = {
  status: WorkspaceVoiceMeetingBootstrapStatus;
  error: string | null;
  ensureMeetingTarget: () => Promise<WorkspaceInteractionTarget>;
};

const WorkspaceVoiceMeetingBootstrapContext =
  React.createContext<WorkspaceVoiceMeetingBootstrapValue | null>(null);

type BootstrapState = {
  contextKey: string;
  status: WorkspaceVoiceMeetingBootstrapStatus;
  error: string | null;
  target: WorkspaceInteractionTarget | null;
};

export function WorkspaceVoiceMeetingBootstrapProvider({
  apiUrl,
  workspaceId,
  children,
}: {
  apiUrl: string;
  workspaceId: string;
  children: React.ReactNode;
}) {
  const t = useT();
  const rail = useOptionalWorkspaceGlobalToolRail();
  const ingress = useWorkspaceInteractionIngress();
  const capabilityCode = rail?.activeCapabilityCode ?? null;
  const scope = React.useMemo(
    () => buildWorkspaceVoiceMeetingScope(capabilityCode),
    [capabilityCode],
  );
  const contextKey = `${workspaceId}:${scope.threadId}`;
  const currentContextKeyRef = React.useRef(contextKey);
  currentContextKeyRef.current = contextKey;
  const targetsByContextRef = React.useRef(new Map<string, WorkspaceInteractionTarget>());
  const inflightByContextRef = React.useRef(
    new Map<string, Promise<WorkspaceInteractionTarget>>(),
  );
  const [state, setState] = React.useState<BootstrapState>({
    contextKey,
    status: 'idle',
    error: null,
    target: null,
  });
  const currentTarget = state.contextKey === contextKey ? state.target : null;
  useWorkspaceInteractionTargetRegistration(currentTarget);

  const ensureMeetingTarget = React.useCallback(async () => {
    const cached = targetsByContextRef.current.get(contextKey);
    if (cached) {
      setState({
        contextKey,
        status: 'ready',
        error: null,
        target: cached,
      });
      return cached;
    }
    const externalTargets = ingress.targets.filter(
      (target) => !Array.from(targetsByContextRef.current.values()).includes(target),
    );
    if (externalTargets.length > 0) {
      if (ingress.activeTarget) {
        return ingress.activeTarget;
      }
      throw new Error('ambiguous_target');
    }
    let inflight = inflightByContextRef.current.get(contextKey);
    if (!inflight) {
      setState({
        contextKey,
        status: 'starting',
        error: null,
        target: null,
      });
      inflight = ensureWorkspaceVoiceMeetingSession({
        apiUrl,
        workspaceId,
        activeCapabilityCode: capabilityCode,
      }).then((session) => {
        const target = createWorkspaceVoiceMeetingTarget({
          apiUrl,
          workspaceId,
          meetingId: session.id,
          commandContext: buildWorkspaceVoiceMeetingCommandContext(
            session,
            capabilityCode,
          ),
          targetLabel: t('workspaceVoiceTargetWorkspaceMeeting' as any),
        });
        targetsByContextRef.current.set(contextKey, target);
        return target;
      }).finally(() => {
        inflightByContextRef.current.delete(contextKey);
      });
      inflightByContextRef.current.set(contextKey, inflight);
    }
    try {
      const target = await inflight;
      if (currentContextKeyRef.current === contextKey) {
        setState({
          contextKey,
          status: 'ready',
          error: null,
          target,
        });
      }
      return target;
    } catch (caught) {
      if (currentContextKeyRef.current === contextKey) {
        setState({
          contextKey,
          status: 'failed',
          error: caught instanceof Error
            ? caught.message
            : 'workspace_voice_meeting_bootstrap_failed',
          target: null,
        });
      }
      throw caught;
    }
  }, [
    apiUrl,
    capabilityCode,
    contextKey,
    ingress.activeTarget,
    ingress.targets,
    t,
    workspaceId,
  ]);

  const value = React.useMemo<WorkspaceVoiceMeetingBootstrapValue>(() => {
    if (state.contextKey !== contextKey) {
      return {
        status: 'idle',
        error: null,
        ensureMeetingTarget,
      };
    }
    return {
      status: state.status,
      error: state.error,
      ensureMeetingTarget,
    };
  }, [contextKey, ensureMeetingTarget, state]);

  return (
    <WorkspaceVoiceMeetingBootstrapContext.Provider value={value}>
      {children}
    </WorkspaceVoiceMeetingBootstrapContext.Provider>
  );
}
export function useWorkspaceVoiceMeetingBootstrap():
  WorkspaceVoiceMeetingBootstrapValue {
  const value = React.useContext(WorkspaceVoiceMeetingBootstrapContext);
  if (!value) {
    throw new Error(
      'useWorkspaceVoiceMeetingBootstrap must be used inside '
      + 'WorkspaceVoiceMeetingBootstrapProvider',
    );
  }
  return value;
}
