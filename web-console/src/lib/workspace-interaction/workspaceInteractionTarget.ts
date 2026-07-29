export type WorkspaceInteractionTargetKind =
  | 'workspace_chat'
  | 'meeting_command'
  | 'host_runtime_prompt';

export type WorkspaceInteractionSubmissionPolicy =
  | 'direct_submit'
  | 'review_then_submit';

export type WorkspaceVoiceAudioTurn = {
  clientTurnId: string;
  audioBase64: string;
  mimeType: string;
  language: string;
};

export type WorkspaceInteractionContext = Readonly<Record<string, unknown>>;

export type WorkspaceInteractionResult = {
  status: 'draft_updated' | 'submitted' | 'ignored_empty_transcript';
  transcript?: string | null;
  commandResponse?: unknown;
};

export type WorkspaceRealtimeVoiceTransport = {
  kind: 'meeting_realtime';
  handleCommandAccepted: (input: {
    transcript: string;
    commandResponse: unknown;
  }) => void;
};

export type WorkspaceInteractionTarget = {
  targetId: string;
  targetKind: WorkspaceInteractionTargetKind;
  targetLabel: string;
  revision: string;
  submissionPolicy: WorkspaceInteractionSubmissionPolicy;
  freezeContext: () => WorkspaceInteractionContext;
  submitVoiceTurn: (
    turn: WorkspaceVoiceAudioTurn,
    snapshot: FrozenWorkspaceInteractionTarget,
  ) => Promise<WorkspaceInteractionResult>;
  realtimeTransport?: WorkspaceRealtimeVoiceTransport;
};

export type FrozenWorkspaceInteractionTarget = {
  workspaceId: string;
  targetId: string;
  targetKind: WorkspaceInteractionTargetKind;
  targetLabel: string;
  targetRevision: string;
  submissionPolicy: WorkspaceInteractionSubmissionPolicy;
  context: WorkspaceInteractionContext;
  contextHash: string;
};

export type WorkspaceInteractionTargetErrorCode =
  | 'no_active_target'
  | 'ambiguous_target'
  | 'unknown_target'
  | 'stale_target'
  | 'workspace_mismatch';

export class WorkspaceInteractionTargetError extends Error {
  readonly code: WorkspaceInteractionTargetErrorCode;

  constructor(code: WorkspaceInteractionTargetErrorCode) {
    super(code);
    this.name = 'WorkspaceInteractionTargetError';
    this.code = code;
  }
}

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(stableValue);
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, nested]) => [key, stableValue(nested)]),
    );
  }
  return value;
}

function deepFreezeValue<T>(value: T): T {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value);
    Object.values(value as Record<string, unknown>).forEach(deepFreezeValue);
  }
  return value;
}

export function stableWorkspaceInteractionValue(value: unknown): string {
  return JSON.stringify(stableValue(value));
}

export function workspaceInteractionFingerprint(value: unknown): string {
  const source = stableWorkspaceInteractionValue(value);
  let hash = 2166136261;
  for (let index = 0; index < source.length; index += 1) {
    hash ^= source.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `fnv1a32:${(hash >>> 0).toString(16).padStart(8, '0')}`;
}

export function workspaceInteractionRevision(
  targetKind: WorkspaceInteractionTargetKind,
  value: unknown,
): string {
  return `${targetKind}:${workspaceInteractionFingerprint(value)}`;
}

export function freezeWorkspaceInteractionTarget(
  workspaceId: string,
  target: WorkspaceInteractionTarget,
): FrozenWorkspaceInteractionTarget {
  const context = deepFreezeValue(
    stableValue(target.freezeContext()) as WorkspaceInteractionContext,
  );
  return deepFreezeValue({
    workspaceId,
    targetId: target.targetId,
    targetKind: target.targetKind,
    targetLabel: target.targetLabel,
    targetRevision: target.revision,
    submissionPolicy: target.submissionPolicy,
    context,
    contextHash: workspaceInteractionFingerprint(context),
  });
}
