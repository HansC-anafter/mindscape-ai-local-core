'use client';

import React from 'react';

import {
  WorkspaceInteractionTargetError,
  freezeWorkspaceInteractionTarget,
  type FrozenWorkspaceInteractionTarget,
  type WorkspaceInteractionResult,
  type WorkspaceInteractionTarget,
  type WorkspaceVoiceAudioTurn,
} from './workspaceInteractionTarget';

type RegisteredTarget = {
  registrationId: number;
  scopeId: string;
  target: WorkspaceInteractionTarget;
};

type WorkspaceInteractionIngressValue = {
  workspaceId: string;
  targets: WorkspaceInteractionTarget[];
  activeTarget: WorkspaceInteractionTarget | null;
  registerTarget: (scopeId: string, target: WorkspaceInteractionTarget) => () => void;
  activateTarget: (targetId: string, source: 'explicit_terminal_focus') => void;
  freezeActiveTarget: () => FrozenWorkspaceInteractionTarget;
  assertFrozenTarget: (snapshot: FrozenWorkspaceInteractionTarget) => WorkspaceInteractionTarget;
  submitFrozenVoiceTurn: (
    snapshot: FrozenWorkspaceInteractionTarget,
    turn: WorkspaceVoiceAudioTurn,
  ) => Promise<WorkspaceInteractionResult>;
};

const WorkspaceInteractionIngressContext =
  React.createContext<WorkspaceInteractionIngressValue | null>(null);

export function WorkspaceInteractionIngressProvider({
  workspaceId,
  children,
}: {
  workspaceId: string;
  children: React.ReactNode;
}) {
  const nextRegistrationId = React.useRef(0);
  const targetsRef = React.useRef<Record<string, RegisteredTarget>>({});
  const explicitActiveTargetIdRef = React.useRef<string | null>(null);
  const [targets, setTargets] = React.useState<Record<string, RegisteredTarget>>({});
  const [explicitActiveTargetId, setExplicitActiveTargetId] =
    React.useState<string | null>(null);

  const updateTargets = React.useCallback((
    updater: (current: Record<string, RegisteredTarget>) => Record<string, RegisteredTarget>,
  ) => {
    setTargets((current) => {
      const next = updater(current);
      targetsRef.current = next;
      return next;
    });
  }, []);

  const registerTarget = React.useCallback((
    scopeId: string,
    target: WorkspaceInteractionTarget,
  ) => {
    nextRegistrationId.current += 1;
    const registrationId = nextRegistrationId.current;
    updateTargets((current) => ({
      ...current,
      [scopeId]: { registrationId, scopeId, target },
    }));

    return () => {
      updateTargets((current) => {
        if (current[scopeId]?.registrationId !== registrationId) {
          return current;
        }
        const next = { ...current };
        delete next[scopeId];
        return next;
      });
    };
  }, [updateTargets]);

  const activateTarget = React.useCallback((
    targetId: string,
    _source: 'explicit_terminal_focus',
  ) => {
    const matches = Object.values(targetsRef.current)
      .filter((entry) => entry.target.targetId === targetId);
    if (matches.length !== 1) {
      throw new WorkspaceInteractionTargetError('unknown_target');
    }
    explicitActiveTargetIdRef.current = targetId;
    setExplicitActiveTargetId(targetId);
  }, []);

  const registeredTargets = React.useMemo(
    () => Object.values(targets).map((entry) => entry.target),
    [targets],
  );
  const activeTarget = React.useMemo(() => {
    const explicitMatches = explicitActiveTargetId
      ? Object.values(targets)
        .filter((entry) => entry.target.targetId === explicitActiveTargetId)
      : [];
    const explicit = explicitMatches.length === 1 ? explicitMatches[0].target : null;
    if (explicit) {
      return explicit;
    }
    return registeredTargets.length === 1 ? registeredTargets[0] : null;
  }, [explicitActiveTargetId, registeredTargets, targets]);

  const resolveCurrentActiveTarget = React.useCallback(() => {
    const currentTargets = targetsRef.current;
    const explicitTargetId = explicitActiveTargetIdRef.current;
    if (explicitTargetId) {
      const explicitMatches = Object.values(currentTargets)
        .filter((entry) => entry.target.targetId === explicitTargetId);
      if (explicitMatches.length === 1) {
        return explicitMatches[0].target;
      }
    }
    const current = Object.values(currentTargets);
    if (current.length === 0) {
      throw new WorkspaceInteractionTargetError('no_active_target');
    }
    if (current.length !== 1) {
      throw new WorkspaceInteractionTargetError('ambiguous_target');
    }
    return current[0].target;
  }, []);

  const freezeActiveTarget = React.useCallback(() => (
    freezeWorkspaceInteractionTarget(workspaceId, resolveCurrentActiveTarget())
  ), [resolveCurrentActiveTarget, workspaceId]);

  const assertFrozenTarget = React.useCallback((
    snapshot: FrozenWorkspaceInteractionTarget,
  ) => {
    if (snapshot.workspaceId !== workspaceId) {
      throw new WorkspaceInteractionTargetError('workspace_mismatch');
    }
    const currentMatches = Object.values(targetsRef.current)
      .filter((entry) => entry.target.targetId === snapshot.targetId);
    const current = currentMatches.length === 1 ? currentMatches[0].target : null;
    if (!current || current.revision !== snapshot.targetRevision) {
      throw new WorkspaceInteractionTargetError('stale_target');
    }
    return current;
  }, [workspaceId]);

  const submitFrozenVoiceTurn = React.useCallback(async (
    snapshot: FrozenWorkspaceInteractionTarget,
    turn: WorkspaceVoiceAudioTurn,
  ) => {
    const current = assertFrozenTarget(snapshot);
    return current.submitVoiceTurn(turn, snapshot);
  }, [assertFrozenTarget]);

  const value = React.useMemo<WorkspaceInteractionIngressValue>(() => ({
    workspaceId,
    targets: registeredTargets,
    activeTarget,
    registerTarget,
    activateTarget,
    freezeActiveTarget,
    assertFrozenTarget,
    submitFrozenVoiceTurn,
  }), [
    activeTarget,
    activateTarget,
    assertFrozenTarget,
    freezeActiveTarget,
    registerTarget,
    registeredTargets,
    submitFrozenVoiceTurn,
    workspaceId,
  ]);

  return (
    <WorkspaceInteractionIngressContext.Provider value={value}>
      {children}
    </WorkspaceInteractionIngressContext.Provider>
  );
}

export function useWorkspaceInteractionIngress(): WorkspaceInteractionIngressValue {
  const value = React.useContext(WorkspaceInteractionIngressContext);
  if (!value) {
    throw new Error(
      'useWorkspaceInteractionIngress must be used inside WorkspaceInteractionIngressProvider',
    );
  }
  return value;
}

export function useOptionalWorkspaceInteractionIngress():
  WorkspaceInteractionIngressValue | null {
  return React.useContext(WorkspaceInteractionIngressContext);
}

export function useWorkspaceInteractionTargetRegistration(
  target: WorkspaceInteractionTarget | null,
) {
  const ingress = useOptionalWorkspaceInteractionIngress();
  const activateTarget = ingress?.activateTarget;
  const registerTarget = ingress?.registerTarget;

  React.useEffect(() => {
    if (!target || !registerTarget) {
      return undefined;
    }
    return registerTarget(target.targetId, target);
  }, [registerTarget, target]);

  return React.useCallback(() => {
    if (target && activateTarget) {
      activateTarget(target.targetId, 'explicit_terminal_focus');
    }
  }, [activateTarget, target]);
}
