import type { AddressableObjectRole } from '@/lib/addressable-object-layer';
import {
  IDLE_RUNTIME_SHELL_STATE,
  type AOLRuntimeShellState,
  type AOLRuntimeSurfaceContext,
} from './AOLRuntimeShellContext';
import type { MeetingPaneSizePreset } from './RuntimeShellPanel';

export const MEETING_PANE_DEFAULT_HEIGHT = 360;
export const MEETING_PANE_MIN_HEIGHT = 240;
const MEETING_PANE_MAX_HEIGHT_RATIO = 0.72;

export const ADDRESSABLE_OBJECT_ROLE_OPTIONS: Array<{
  role: AddressableObjectRole;
  label: string;
  title: string;
}> = [
  {
    role: 'target',
    label: 'Target',
    title: 'Primary object this meeting may change or review',
  },
  {
    role: 'source',
    label: 'Source',
    title: 'Reference or input object for this meeting',
  },
  {
    role: 'baseline',
    label: 'Base',
    title: 'Current state used for comparison',
  },
  {
    role: 'constraint',
    label: 'Rule',
    title: 'Constraint, policy, budget, or boundary',
  },
  {
    role: 'evidence',
    label: 'Proof',
    title: 'Evidence, preview, or prior decision',
  },
];

export function buildCapabilitySurfaceId(capabilityCode: string, componentCode: string): string {
  return `capability_page:${capabilityCode}:${componentCode}`;
}

export function buildSelectingState(
  activeSurface: AOLRuntimeSurfaceContext | null,
  contextRole: AddressableObjectRole = 'source',
): AOLRuntimeShellState {
  return {
    ...IDLE_RUNTIME_SHELL_STATE,
    mode: 'selecting',
    activeSurface,
    contextRole,
  };
}

export function buildStatusCopy(state: AOLRuntimeShellState): { title: string; description: string } {
  const summary = state.resolvedObject?.summary ?? null;

  switch (state.mode) {
    case 'selecting':
      return {
        title: 'Select an object on this page',
        description: 'Click a supported object in the current workbench to bring it into the AOL flow.',
      };
    case 'resolving':
      return {
        title: state.selection?.label || 'Resolving object',
        description: 'Resolving object context through the shared Local-Core runtime...',
      };
    case 'disambiguating':
      return {
        title: state.selection?.label || 'Choose object',
        description: 'Resolve this selection to one object before opening the meeting.',
      };
    case 'selected':
      return {
        title: summary?.title || state.selection?.label || 'Object selected',
        description: state.currentMeetingId
          ? 'The selected object is already attached. Reopen the meeting pane or choose another object.'
          : summary?.summary_text || 'The selected object is ready to open in a meeting pane.',
      };
    case 'attaching':
      return {
        title: summary?.title || state.selection?.label || 'Attaching object',
        description: 'Opening a meeting pane with the selected object already attached...',
      };
    case 'meeting_opened':
      return {
        title: summary?.title || state.selection?.label || 'Meeting opened',
        description: 'The meeting pane is open and already includes this object context.',
      };
    case 'error':
      return {
        title: summary?.title || state.selection?.label || 'AOL action failed',
        description: state.error || 'The shared AOL flow could not complete this step.',
      };
    case 'idle':
    default:
      return {
        title: 'AOL tool',
        description: 'Select an object on this page and open a meeting with it already attached.',
      };
  }
}

export function findAttachToMeetingAction(state: AOLRuntimeShellState) {
  return state.resolvedObject?.actions.find((action) => action.action_code === 'attach_to_meeting') ?? null;
}

export function canAttachCurrentObjectToMeeting(state: AOLRuntimeShellState): boolean {
  return (
    Boolean(state.resolvedObject) &&
    Boolean(findAttachToMeetingAction(state)) &&
    !state.currentMeetingId &&
    (state.mode === 'selected' || state.mode === 'error')
  );
}

export function isSameSurface(
  left: AOLRuntimeSurfaceContext | null,
  right: AOLRuntimeSurfaceContext,
): boolean {
  return Boolean(
    left &&
      left.surfaceId === right.surfaceId &&
      left.route === right.route &&
      left.capabilityCode === right.capabilityCode,
  );
}

export function clampMeetingPaneHeight(nextHeight: number, rootHeight: number): number {
  const safeRootHeight = Number.isFinite(rootHeight) && rootHeight > 0 ? rootHeight : MEETING_PANE_DEFAULT_HEIGHT;
  const maxHeight = Math.max(MEETING_PANE_MIN_HEIGHT, Math.floor(safeRootHeight * MEETING_PANE_MAX_HEIGHT_RATIO));
  return Math.min(Math.max(nextHeight, MEETING_PANE_MIN_HEIGHT), maxHeight);
}

export function getMeetingPanePresetHeight(preset: MeetingPaneSizePreset, rootHeight: number): number {
  if (preset === 'compact') {
    return MEETING_PANE_MIN_HEIGHT;
  }

  if (preset === 'expanded') {
    return Math.floor(rootHeight * MEETING_PANE_MAX_HEIGHT_RATIO);
  }

  return MEETING_PANE_DEFAULT_HEIGHT;
}
