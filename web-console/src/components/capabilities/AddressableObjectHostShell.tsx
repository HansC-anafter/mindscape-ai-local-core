'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { GitBranch, Maximize2, Minimize2, MousePointer2, PanelBottom } from 'lucide-react';

import {
  attachAddressableObjectToMeeting,
  resolveAddressableSelection,
  type AddressableObjectHostBridge,
  type AddressableObjectHostMode,
  type AddressableObjectRole,
  type AddressableObjectSummary,
  type AddressableRuntimeError,
  type AddressableSelectionTarget,
  type ObjectMeetingAttachResponse,
  type ResolvedAddressableObject,
} from '@/lib/addressable-object-layer';
import AOLMeetingBottomShell from './meeting-workbench/AOLMeetingBottomShell';

type AddressableObjectSurfaceContext = {
  apiUrl: string;
  workspaceId: string;
  capabilityCode: string;
  route: string;
  surfaceId: string;
};

interface RegisteredSurfaceContext extends AddressableObjectSurfaceContext {
  registrationId: string;
}

interface AOLPanelState {
  mode: AddressableObjectHostMode;
  activeSurface: AddressableObjectSurfaceContext | null;
  selection: AddressableSelectionTarget | null;
  resolvedObject: ResolvedAddressableObject | null;
  warnings: AddressableRuntimeError[];
  attachResponse: ObjectMeetingAttachResponse | null;
  currentMeetingId: string | null;
  error: string | null;
}

interface AddressableObjectHostShellProps extends AddressableObjectSurfaceContext {
  children: (hostBridge: AddressableObjectHostBridge) => React.ReactNode;
}

interface AddressableObjectHostProviderProps {
  workspaceId: string;
  children: React.ReactNode;
}

interface AddressableObjectHostController {
  state: AOLPanelState;
  activateSurface: (surface: AddressableObjectSurfaceContext, registrationId: string) => void;
  deactivateSurface: (surface: AddressableObjectSurfaceContext, registrationId: string) => void;
  requestObjectTargeting: () => void;
  cancelObjectTargeting: () => void;
  clearCurrentObject: () => void;
  openCurrentMeeting: () => void;
  closeCurrentMeeting: () => void;
  captureSelection: (
    surface: AddressableObjectSurfaceContext,
    selection: AddressableSelectionTarget,
  ) => Promise<void>;
  attachCurrentObject: () => Promise<void>;
}

const IDLE_PANEL_STATE: AOLPanelState = {
  mode: 'idle',
  activeSurface: null,
  selection: null,
  resolvedObject: null,
  warnings: [],
  attachResponse: null,
  currentMeetingId: null,
  error: null,
};

const AddressableObjectHostContext = createContext<AddressableObjectHostController | null>(null);

export function buildCapabilitySurfaceId(capabilityCode: string, componentCode: string): string {
  return `capability_page:${capabilityCode}:${componentCode}`;
}

function buildSelectingState(activeSurface: AddressableObjectSurfaceContext | null): AOLPanelState {
  return {
    ...IDLE_PANEL_STATE,
    mode: 'selecting',
    activeSurface,
  };
}

function buildStatusCopy(state: AOLPanelState): { title: string; description: string } {
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

function findAttachToMeetingAction(state: AOLPanelState) {
  return state.resolvedObject?.actions.find((action) => action.action_code === 'attach_to_meeting') ?? null;
}

function canAttachCurrentObjectToMeeting(state: AOLPanelState): boolean {
  return (
    Boolean(state.resolvedObject) &&
    Boolean(findAttachToMeetingAction(state)) &&
    !state.currentMeetingId &&
    (state.mode === 'selected' || state.mode === 'error')
  );
}

function isSameSurface(
  left: AddressableObjectSurfaceContext | null,
  right: AddressableObjectSurfaceContext,
): boolean {
  return Boolean(
    left &&
      left.surfaceId === right.surfaceId &&
      left.route === right.route &&
      left.capabilityCode === right.capabilityCode,
  );
}

const MEETING_PANE_DEFAULT_HEIGHT = 360;
const MEETING_PANE_MIN_HEIGHT = 240;
const MEETING_PANE_MAX_HEIGHT_RATIO = 0.72;
type MeetingPaneSizePreset = 'compact' | 'default' | 'expanded';

function clampMeetingPaneHeight(nextHeight: number, rootHeight: number): number {
  const safeRootHeight = Number.isFinite(rootHeight) && rootHeight > 0 ? rootHeight : MEETING_PANE_DEFAULT_HEIGHT;
  const maxHeight = Math.max(MEETING_PANE_MIN_HEIGHT, Math.floor(safeRootHeight * MEETING_PANE_MAX_HEIGHT_RATIO));
  return Math.min(Math.max(nextHeight, MEETING_PANE_MIN_HEIGHT), maxHeight);
}

function getMeetingPanePresetHeight(preset: MeetingPaneSizePreset, rootHeight: number): number {
  if (preset === 'compact') {
    return MEETING_PANE_MIN_HEIGHT;
  }

  if (preset === 'expanded') {
    return Math.floor(rootHeight * MEETING_PANE_MAX_HEIGHT_RATIO);
  }

  return MEETING_PANE_DEFAULT_HEIGHT;
}

function isPreviewRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isApiPreviewPath(previewUrl: string): boolean {
  return /^https?:\/\/[^/]+\/api\//.test(previewUrl) || previewUrl.startsWith('/api/');
}

function buildApiPreviewUrl(previewUrl: string, apiUrl: string): string {
  if (/^https?:\/\//.test(previewUrl)) {
    return previewUrl;
  }

  if (apiUrl) {
    return new URL(previewUrl, `${apiUrl.replace(/\/$/, '')}/`).toString();
  }

  if (typeof window !== 'undefined') {
    return new URL(previewUrl, window.location.origin).toString();
  }

  return previewUrl;
}

function buildIframePreviewUrl(previewUrl: string): string {
  if (/^https?:\/\//.test(previewUrl)) {
    return previewUrl;
  }

  if (typeof window !== 'undefined') {
    return new URL(previewUrl, window.location.origin).toString();
  }

  return previewUrl;
}

function formatPreviewLabel(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function AddressableObjectPreviewValue({
  value,
  depth = 0,
}: {
  value: unknown;
  depth?: number;
}) {
  if (value === null || value === undefined || value === '') {
    return null;
  }

  if (typeof value === 'string') {
    return (
      <div className="whitespace-pre-wrap break-words text-sm leading-6 text-slate-700 dark:text-slate-200">
        {value}
      </div>
    );
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return (
      <div className="text-sm font-medium text-slate-800 dark:text-slate-100">{String(value)}</div>
    );
  }

  if (Array.isArray(value)) {
    const scalarItems = value.every(
      (item) =>
        typeof item === 'string' ||
        typeof item === 'number' ||
        typeof item === 'boolean',
    );

    if (scalarItems) {
      return (
        <div className="flex flex-wrap gap-2">
          {value.map((item, index) => (
            <span
              key={`${String(item)}-${index}`}
              className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
            >
              {String(item)}
            </span>
          ))}
        </div>
      );
    }

    return (
      <div className="space-y-3">
        {value.map((item, index) => (
          <div
            key={index}
            className="rounded-2xl border border-slate-200 bg-white/90 p-3 dark:border-slate-800 dark:bg-slate-950/60"
          >
            <AddressableObjectPreviewValue value={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    );
  }

  if (isPreviewRecord(value)) {
    const entries = Object.entries(value).filter(([, item]) => item !== null && item !== undefined && item !== '');

    if (entries.length === 0) {
      return null;
    }

    if (depth >= 3) {
      return (
        <pre className="overflow-x-auto rounded-2xl bg-slate-950 px-4 py-3 text-xs leading-6 text-slate-100">
          {JSON.stringify(value, null, 2)}
        </pre>
      );
    }

    return (
      <div className="space-y-4">
        {entries.map(([key, item]) => (
          <div
            key={key}
            className="rounded-2xl border border-slate-200 bg-white/90 p-4 dark:border-slate-800 dark:bg-slate-950/60"
          >
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
              {formatPreviewLabel(key)}
            </div>
            <div className="mt-3">
              <AddressableObjectPreviewValue value={item} depth={depth + 1} />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <pre className="overflow-x-auto rounded-2xl bg-slate-950 px-4 py-3 text-xs leading-6 text-slate-100">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function AddressableObjectSourcePreview({
  summary,
  apiUrl,
  fallbackSurfaceRoute,
}: {
  summary: AddressableObjectSummary | null;
  apiUrl: string;
  fallbackSurfaceRoute?: string | null;
}) {
  const previewUrl = summary?.owner_surface_url || fallbackSurfaceRoute || null;
  const [detailPayload, setDetailPayload] = useState<unknown>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    let isCancelled = false;

    if (!previewUrl || !isApiPreviewPath(previewUrl)) {
      setDetailPayload(null);
      setPreviewError(null);
      setIsLoading(false);
      return () => {
        isCancelled = true;
      };
    }

    const run = async () => {
      setIsLoading(true);
      setPreviewError(null);

      try {
        const response = await fetch(buildApiPreviewUrl(previewUrl, apiUrl));
        const text = await response.text();
        const payload = text ? JSON.parse(text) : null;

        if (!response.ok) {
          throw new Error(
            typeof payload?.detail === 'string'
              ? payload.detail
              : `Failed to load object preview (${response.status})`,
          );
        }

        if (!isCancelled) {
          setDetailPayload(payload);
        }
      } catch (error) {
        if (!isCancelled) {
          setDetailPayload(null);
          setPreviewError(
            error instanceof Error ? error.message : 'Failed to load owner-backed object preview.',
          );
        }
      } finally {
        if (!isCancelled) {
          setIsLoading(false);
        }
      }
    };

    void run();

    return () => {
      isCancelled = true;
    };
  }, [apiUrl, previewUrl]);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center rounded-[22px] border border-slate-200 bg-white/80 px-4 py-6 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-950/60 dark:text-slate-300">
        Loading object preview...
      </div>
    );
  }

  if (detailPayload) {
    return (
      <div
        className="h-full overflow-y-auto rounded-[22px] border border-slate-200 bg-white/80 p-3 dark:border-slate-800 dark:bg-slate-950/60"
        data-testid="aol-object-preview-detail"
      >
        <AddressableObjectPreviewValue value={detailPayload} />
      </div>
    );
  }

  if (previewUrl && !isApiPreviewPath(previewUrl)) {
    return (
      <div className="h-full overflow-hidden rounded-[22px] border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
        <iframe
          src={buildIframePreviewUrl(previewUrl)}
          title={summary?.title || 'Selected object preview'}
          className="h-full w-full"
          data-testid="aol-object-preview-iframe"
        />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto rounded-[22px] border border-slate-200 bg-white/80 p-3 dark:border-slate-800 dark:bg-slate-950/60">
      {previewError ? (
        <div className="rounded-[16px] border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200">
          {previewError}
        </div>
      ) : null}
      {summary?.summary_text ? (
        <div className="rounded-[16px] border border-slate-200 bg-white/90 p-3 dark:border-slate-800 dark:bg-slate-950/60">
          <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
            Summary
          </div>
          <div className="mt-2 whitespace-pre-wrap text-xs leading-5 text-slate-700 dark:text-slate-200">
            {summary.summary_text}
          </div>
        </div>
      ) : null}
      <div className="mt-3 rounded-[16px] border border-slate-200 bg-white/90 p-3 dark:border-slate-800 dark:bg-slate-950/60">
        <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
          Object metadata
        </div>
        <div className="mt-2 space-y-1.5 text-xs text-slate-700 dark:text-slate-200">
          <div>Owner: {summary?.ref.owner_pack || 'unknown'}</div>
          <div>Kind: {summary?.ref.object_kind || 'unknown'}</div>
          <div className="break-all">Object ID: {summary?.ref.object_id || 'unknown'}</div>
          {previewUrl ? (
            <a
              href={previewUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex text-xs font-medium text-blue-600 hover:text-blue-700 dark:text-blue-300 dark:hover:text-blue-200"
            >
              Open source preview
            </a>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function AddressableObjectMeetingPane({
  state,
  paneHeight,
  onClose,
  onResizeStart,
  onSizePreset,
  onSwitchObject,
}: {
  state: AOLPanelState;
  paneHeight: number;
  onClose: () => void;
  onResizeStart: (event: React.PointerEvent<HTMLButtonElement>) => void;
  onSizePreset: (preset: MeetingPaneSizePreset) => void;
  onSwitchObject: () => void;
}) {
  if (state.mode !== 'meeting_opened' || !state.activeSurface) {
    return null;
  }

  const summary = state.resolvedObject?.summary ?? null;

  return (
    <section
      className="relative z-[50] flex shrink-0 flex-col border-t border-slate-200 bg-white shadow-[0_-12px_30px_rgba(15,23,42,0.12)] dark:border-slate-700 dark:bg-slate-950"
      data-testid="aol-meeting-pane"
      role="region"
      aria-label="AOL meeting graph"
      style={{ height: `${paneHeight}px` }}
    >
      <div className="relative flex h-9 shrink-0 items-center justify-center border-b border-slate-200 bg-slate-100/90 dark:border-slate-800 dark:bg-slate-900/90">
        <div className="absolute left-4 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
          Meeting Graph
        </div>
        <button
          type="button"
          onPointerDown={onResizeStart}
          className="inline-flex touch-none cursor-row-resize items-center justify-center rounded-full px-4 py-2"
          data-testid="aol-meeting-pane-resize-handle"
          aria-label="Resize meeting pane"
        >
          <span className="h-1.5 w-16 rounded-full bg-slate-400/80 transition-colors hover:bg-slate-500 dark:bg-slate-500 dark:hover:bg-slate-400" />
        </button>
        <div className="absolute right-20 flex items-center gap-1">
          <button
            type="button"
            onClick={() => onSizePreset('compact')}
            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
            data-testid="aol-meeting-pane-compact"
            aria-label="Compact meeting graph"
            title="Compact"
          >
            <Minimize2 className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => onSizePreset('default')}
            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
            data-testid="aol-meeting-pane-default"
            aria-label="Default meeting graph size"
            title="Default"
          >
            <PanelBottom className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => onSizePreset('expanded')}
            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
            data-testid="aol-meeting-pane-expanded"
            aria-label="Expand meeting graph"
            title="Expand"
          >
            <Maximize2 className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="absolute right-3 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-200 hover:text-slate-900 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
        >
          Close
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        <AOLMeetingBottomShell
          workspaceId={state.activeSurface.workspaceId}
          apiUrl={state.activeSurface.apiUrl}
          meetingId={state.currentMeetingId}
          summary={summary}
          selection={state.selection}
          attachResponse={state.attachResponse}
          surfaceRoute={state.activeSurface.route}
          onSwitchObject={onSwitchObject}
        />
      </div>
    </section>
  );
}

function AddressableObjectPanel({
  state,
  onRequestObjectTargeting,
  onCancelObjectTargeting,
  onClearCurrentObject,
  onAttachCurrentObject,
  onOpenCurrentMeeting,
}: {
  state: AOLPanelState;
  onRequestObjectTargeting: () => void;
  onCancelObjectTargeting: () => void;
  onClearCurrentObject: () => void;
  onAttachCurrentObject: () => void;
  onOpenCurrentMeeting: () => void;
}) {
  if (state.mode === 'idle') {
    return null;
  }

  const summary = state.resolvedObject?.summary ?? null;
  const actions = state.resolvedObject?.actions ?? [];
  const attachAction = findAttachToMeetingAction(state);
  const ownerSurfaceAction = actions.find((action) => action.action_code === 'open_owner_surface') ?? null;
  const warnings = [...state.warnings, ...(state.attachResponse?.errors || [])];
  const statusCopy = buildStatusCopy(state);
  const canAttach = canAttachCurrentObjectToMeeting(state);
  const canOpenMeeting = Boolean(state.currentMeetingId) && state.mode !== 'meeting_opened';

  return (
    <div
      className="w-[360px] max-w-[min(360px,calc(100vw-6rem))] rounded-xl border border-gray-200 bg-white/95 shadow-2xl backdrop-blur dark:border-gray-700 dark:bg-gray-900/95"
      data-testid="aol-host-panel"
      data-aol-mode={state.mode}
    >
      <div className="flex items-start justify-between gap-3 border-b border-gray-200 px-4 py-3 dark:border-gray-700">
        <div className="min-w-0">
          <div className="text-xs font-semibold uppercase tracking-wide text-blue-600 dark:text-blue-300">
            Addressable Object
          </div>
          <div className="mt-1 truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
            {statusCopy.title}
          </div>
          <div className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{statusCopy.description}</div>
        </div>
        <button
          type="button"
          onClick={state.mode === 'selecting' ? onCancelObjectTargeting : onClearCurrentObject}
          className="rounded-md px-2 py-1 text-xs text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100"
        >
          {state.mode === 'selecting' ? 'Cancel' : 'Clear'}
        </button>
      </div>

      <div className="space-y-3 px-4 py-3">
        {state.mode === 'resolving' ? (
          <div className="rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700 dark:bg-blue-950/30 dark:text-blue-200">
            Resolving object context...
          </div>
        ) : null}

        {state.mode === 'attaching' ? (
          <div className="rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700 dark:bg-blue-950/30 dark:text-blue-200">
            Opening meeting pane with object context...
          </div>
        ) : null}

        {state.error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-300">
            {state.error}
          </div>
        ) : null}

        {state.selection ? (
          <div className="rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-600 dark:bg-gray-800/60 dark:text-gray-300">
            <div className="truncate font-medium text-gray-800 dark:text-gray-100">
              {state.selection.label || state.selection.objectId}
            </div>
            <div className="mt-1 truncate">Source surface: {state.selection.sourceSurface || state.activeSurface?.surfaceId || 'unknown'}</div>
          </div>
        ) : null}

        {summary?.labels?.length ? (
          <div className="flex flex-wrap gap-1">
            {summary.labels.map((label) => (
              <span
                key={label}
                className="rounded-full bg-gray-100 px-2 py-1 text-[11px] text-gray-600 dark:bg-gray-800 dark:text-gray-300"
              >
                {label}
              </span>
            ))}
          </div>
        ) : null}

        {state.attachResponse ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 dark:border-emerald-900/40 dark:bg-emerald-950/20">
            <div className="text-xs font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">
              {state.attachResponse.status === 'materialized' ? 'Materialized' : 'Attached'}
            </div>
            <div className="mt-1 text-sm text-emerald-800 dark:text-emerald-100">
              Meeting ID: <span className="font-mono">{state.attachResponse.meeting_id}</span>
            </div>
            {state.attachResponse.review_routes.length > 0 ? (
              <div className="mt-2 space-y-1">
                {state.attachResponse.review_routes.map((route) => (
                  <a
                    key={route}
                    href={route}
                    className="block text-xs text-emerald-700 underline-offset-2 hover:underline dark:text-emerald-300"
                  >
                    Review route: {route}
                  </a>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        {warnings.length > 0 ? (
          <div className="space-y-1">
            {warnings.map((warning) => (
              <div
                key={`${warning.code}:${warning.message}`}
                className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:bg-amber-950/20 dark:text-amber-300"
              >
                {warning.message}
              </div>
            ))}
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2">
          {state.mode !== 'selecting' ? (
            <button
              type="button"
              onClick={onRequestObjectTargeting}
              className="rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
            >
              Select Another Object
            </button>
          ) : null}
          {state.mode === 'selecting' ? (
            <button
              type="button"
              onClick={onCancelObjectTargeting}
              className="rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
            >
              Cancel
            </button>
          ) : null}
          {canAttach ? (
            <button
              type="button"
              onClick={onAttachCurrentObject}
              disabled={state.mode === 'attaching'}
              className="rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {state.mode === 'attaching' ? 'Opening...' : 'Open Meeting'}
            </button>
          ) : null}
          {canOpenMeeting ? (
            <button
              type="button"
              onClick={onOpenCurrentMeeting}
              className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700"
            >
              Reopen Meeting
            </button>
          ) : null}
          {ownerSurfaceAction && summary?.owner_surface_url ? (
            <a
              href={summary.owner_surface_url}
              className="rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
            >
              {ownerSurfaceAction.label}
            </a>
          ) : null}
        </div>

        {summary ? (
          <div className="rounded-lg bg-gray-50 px-3 py-2 text-[11px] text-gray-500 dark:bg-gray-800/60 dark:text-gray-400">
            <div>Owner: {summary.ref.owner_pack}</div>
            <div>Kind: {summary.ref.object_kind}</div>
            <div className="truncate">Object ID: {summary.ref.object_id}</div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function AddressableObjectAnchor({
  state,
  onRequestObjectTargeting,
  onCancelObjectTargeting,
}: {
  state: AOLPanelState;
  onRequestObjectTargeting: () => void;
  onCancelObjectTargeting: () => void;
}) {
  const isActive = state.mode !== 'idle' && state.mode !== 'meeting_opened';
  const label = state.mode === 'selecting' ? 'Cancel object selection' : 'Select object';
  const helper = state.mode === 'meeting_opened' ? 'Select another object' : label;

  return (
    <button
      type="button"
      onClick={state.mode === 'selecting' ? onCancelObjectTargeting : onRequestObjectTargeting}
      className={`inline-flex h-6 w-6 flex-col items-center justify-center rounded-md border text-[9px] font-semibold shadow-sm backdrop-blur transition-colors ${
        isActive
          ? 'border-blue-200 bg-blue-600 text-white hover:bg-blue-700 dark:border-blue-500/40 dark:bg-blue-500 dark:hover:bg-blue-400'
          : 'border-gray-200 bg-white/95 text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900/95 dark:text-gray-100 dark:hover:bg-gray-800'
      }`}
      data-testid="aol-global-anchor"
      aria-pressed={isActive}
      title={helper}
      aria-label={label}
    >
      <MousePointer2 className="h-3 w-3" aria-hidden="true" />
    </button>
  );
}

function AddressableGraphShellAnchor({
  state,
  canOpenGraphShell,
  onOpenGraphShell,
}: {
  state: AOLPanelState;
  canOpenGraphShell: boolean;
  onOpenGraphShell: () => void;
}) {
  const isOpen = state.mode === 'meeting_opened';
  const isBusy = state.mode === 'attaching';
  const isDisabled = !canOpenGraphShell || isBusy;
  const label = isOpen
    ? 'Graph shell is open'
    : canOpenGraphShell
      ? 'Open graph shell'
      : 'No active workbench surface for graph shell';

  return (
    <button
      type="button"
      onClick={onOpenGraphShell}
      disabled={isDisabled}
      className={`inline-flex h-6 w-6 items-center justify-center rounded-md border text-[9px] font-semibold shadow-sm backdrop-blur transition-colors ${
        isOpen
          ? 'border-blue-200 bg-blue-600 text-white hover:bg-blue-700 dark:border-blue-500/40 dark:bg-blue-500 dark:hover:bg-blue-400'
          : isDisabled
            ? 'cursor-not-allowed border-gray-200 bg-gray-100/80 text-gray-400 shadow-none dark:border-gray-800 dark:bg-gray-900/70 dark:text-gray-600'
            : 'border-gray-200 bg-white/95 text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900/95 dark:text-gray-100 dark:hover:bg-gray-800'
      }`}
      data-testid="aol-graph-shell-anchor"
      aria-pressed={isOpen}
      aria-label={label}
      title={label}
    >
      <GitBranch className="h-3 w-3" aria-hidden="true" />
    </button>
  );
}

function AddressableObjectToolRail({
  state,
  canOpenGraphShell,
  onRequestObjectTargeting,
  onCancelObjectTargeting,
  onOpenGraphShell,
}: {
  state: AOLPanelState;
  canOpenGraphShell: boolean;
  onRequestObjectTargeting: () => void;
  onCancelObjectTargeting: () => void;
  onOpenGraphShell: () => void;
}) {
  return (
    <nav
      className="pointer-events-auto flex h-full w-10 shrink-0 flex-col items-center border-l border-gray-200 bg-white/90 pb-3 pt-12 shadow-[-6px_0_18px_rgba(15,23,42,0.08)] backdrop-blur dark:border-gray-700 dark:bg-gray-900/90"
      data-testid="aol-shell-rail"
      aria-label="Addressable object tools"
    >
      <div
        className="flex w-full flex-col items-center gap-1 border-b border-gray-200 px-1 pb-3 dark:border-gray-700"
        data-testid="aol-object-tool-group"
      >
        <AddressableObjectAnchor
          state={state}
          onRequestObjectTargeting={onRequestObjectTargeting}
          onCancelObjectTargeting={onCancelObjectTargeting}
        />
        <div className="text-center text-[6px] uppercase leading-none tracking-normal text-gray-400 dark:text-gray-500">
          Select
        </div>
      </div>
      <div
        className="flex w-full flex-col items-center gap-1 px-1 pt-3"
        data-testid="aol-graph-shell-tool-group"
      >
        <AddressableGraphShellAnchor
          state={state}
          canOpenGraphShell={canOpenGraphShell}
          onOpenGraphShell={onOpenGraphShell}
        />
        <div className="text-center text-[6px] uppercase leading-none tracking-normal text-gray-400 dark:text-gray-500">
          Graph
        </div>
      </div>
    </nav>
  );
}

function AddressableObjectHostProviderInner({
  children,
}: AddressableObjectHostProviderProps) {
  const shellRootRef = useRef<HTMLDivElement | null>(null);
  const registeredSurfacesRef = useRef<RegisteredSurfaceContext[]>([]);
  const [panelState, setPanelState] = useState<AOLPanelState>(IDLE_PANEL_STATE);
  const [meetingPaneHeight, setMeetingPaneHeight] = useState(MEETING_PANE_DEFAULT_HEIGHT);
  const requestEpochRef = useRef(0);

  const invalidateInflightRequests = useCallback(() => {
    requestEpochRef.current += 1;
    return requestEpochRef.current;
  }, []);

  const activateSurface = useCallback((surface: AddressableObjectSurfaceContext, registrationId: string) => {
    registeredSurfacesRef.current = [
      ...registeredSurfacesRef.current.filter((registeredSurface) => registeredSurface.registrationId !== registrationId),
      { ...surface, registrationId },
    ];
    setPanelState((current) => {
      const activeSurface = current.activeSurface;
      if (isSameSurface(activeSurface, surface)) {
        return current;
      }
      return {
        ...current,
        activeSurface: surface,
      };
    });
  }, []);

  const deactivateSurface = useCallback((surface: AddressableObjectSurfaceContext, registrationId: string) => {
    registeredSurfacesRef.current = registeredSurfacesRef.current.filter(
      (registeredSurface) => registeredSurface.registrationId !== registrationId,
    );
    setPanelState((current) => {
      const activeSurface = current.activeSurface;
      if (!isSameSurface(activeSurface, surface)) {
        return current;
      }
      const fallbackRegisteredSurface =
        registeredSurfacesRef.current[registeredSurfacesRef.current.length - 1] ?? null;
      const fallbackSurface = fallbackRegisteredSurface
        ? {
            apiUrl: fallbackRegisteredSurface.apiUrl,
            workspaceId: fallbackRegisteredSurface.workspaceId,
            capabilityCode: fallbackRegisteredSurface.capabilityCode,
            route: fallbackRegisteredSurface.route,
            surfaceId: fallbackRegisteredSurface.surfaceId,
          }
        : null;
      return {
        ...current,
        activeSurface: fallbackSurface,
      };
    });
  }, []);

  const requestObjectTargeting = useCallback(() => {
    invalidateInflightRequests();
    setPanelState((current) => buildSelectingState(current.activeSurface));
  }, [invalidateInflightRequests]);

  const cancelObjectTargeting = useCallback(() => {
    invalidateInflightRequests();
    setPanelState((current) => ({
      ...IDLE_PANEL_STATE,
      activeSurface: current.activeSurface,
    }));
  }, [invalidateInflightRequests]);

  const clearCurrentObject = useCallback(() => {
    invalidateInflightRequests();
    setPanelState((current) => ({
      ...IDLE_PANEL_STATE,
      activeSurface: current.activeSurface,
    }));
  }, [invalidateInflightRequests]);

  const openCurrentMeeting = useCallback(() => {
    setPanelState((current) => {
      if (!current.currentMeetingId) {
        return current;
      }
      return {
        ...current,
        mode: 'meeting_opened',
        error: null,
      };
    });
  }, []);

  const closeCurrentMeeting = useCallback(() => {
    setPanelState((current) => {
      if (current.mode !== 'meeting_opened') {
        return current;
      }
      return {
        ...current,
        mode: current.resolvedObject ? 'selected' : 'idle',
      };
    });
  }, []);

  const resizeMeetingPane = useCallback((clientY: number) => {
    const rootRect = shellRootRef.current?.getBoundingClientRect();
    if (!rootRect) {
      return;
    }
    setMeetingPaneHeight(clampMeetingPaneHeight(rootRect.bottom - clientY, rootRect.height));
  }, []);

  const beginMeetingPaneResize = useCallback(
    (event: React.PointerEvent<HTMLButtonElement>) => {
      event.preventDefault();
      resizeMeetingPane(event.clientY);

      const handlePointerMove = (moveEvent: PointerEvent) => {
        resizeMeetingPane(moveEvent.clientY);
      };
      const handlePointerUp = () => {
        window.removeEventListener('pointermove', handlePointerMove);
        window.removeEventListener('pointerup', handlePointerUp);
      };

      window.addEventListener('pointermove', handlePointerMove);
      window.addEventListener('pointerup', handlePointerUp);
    },
    [resizeMeetingPane],
  );

  const setMeetingPaneSizePreset = useCallback((preset: MeetingPaneSizePreset) => {
    const rootHeight = shellRootRef.current?.getBoundingClientRect().height ?? MEETING_PANE_DEFAULT_HEIGHT;
    setMeetingPaneHeight(clampMeetingPaneHeight(getMeetingPanePresetHeight(preset, rootHeight), rootHeight));
  }, []);

  useEffect(() => {
    if (panelState.mode !== 'meeting_opened') {
      return;
    }

    const clampCurrentHeight = () => {
      const rootHeight = shellRootRef.current?.getBoundingClientRect().height ?? MEETING_PANE_DEFAULT_HEIGHT;
      setMeetingPaneHeight((current) => clampMeetingPaneHeight(current, rootHeight));
    };

    clampCurrentHeight();
    window.addEventListener('resize', clampCurrentHeight);
    return () => {
      window.removeEventListener('resize', clampCurrentHeight);
    };
  }, [panelState.mode]);

  const captureSelection = useCallback(
    async (surface: AddressableObjectSurfaceContext, selection: AddressableSelectionTarget) => {
      const requestEpoch = invalidateInflightRequests();
      setPanelState({
        mode: 'resolving',
        activeSurface: surface,
        selection,
        resolvedObject: null,
        warnings: [],
        attachResponse: null,
        currentMeetingId: null,
        error: null,
      });

      try {
        const response = await resolveAddressableSelection({
          apiUrl: surface.apiUrl,
          workspaceId: surface.workspaceId,
          capabilityCode: surface.capabilityCode,
          route: surface.route,
          surfaceId: surface.surfaceId,
          selection,
        });

        if (requestEpoch !== requestEpochRef.current) {
          return;
        }

        if (response.status !== 'resolved' || response.resolved_objects.length === 0) {
          setPanelState({
            mode: 'error',
            activeSurface: surface,
            selection,
            resolvedObject: null,
            warnings: response.errors,
            attachResponse: null,
            currentMeetingId: null,
            error:
              response.errors[0]?.message ||
              (response.candidate_objects.length > 1
                ? 'Selection resolved to multiple candidates. Disambiguation UI is not implemented yet.'
                : 'Selection did not resolve to an addressable object.'),
          });
          return;
        }

        setPanelState({
          mode: 'selected',
          activeSurface: surface,
          selection,
          resolvedObject: response.resolved_objects[0],
          warnings: response.errors,
          attachResponse: null,
          currentMeetingId: null,
          error: null,
        });
      } catch (resolveError) {
        if (requestEpoch !== requestEpochRef.current) {
          return;
        }

        setPanelState({
          mode: 'error',
          activeSurface: surface,
          selection,
          resolvedObject: null,
          warnings: [],
          attachResponse: null,
          currentMeetingId: null,
          error:
            resolveError instanceof Error
              ? resolveError.message
              : 'Failed to resolve addressable object selection.',
        });
      }
    },
    [invalidateInflightRequests],
  );

  const attachCurrentObject = useCallback(async () => {
    const requestEpoch = invalidateInflightRequests();
    const stateSnapshot = panelState;

    if (!stateSnapshot.resolvedObject || !stateSnapshot.activeSurface) {
      return;
    }

    setPanelState((current) => ({
      ...current,
      mode: 'attaching',
      error: null,
      attachResponse: null,
    }));

    try {
      const response = await attachAddressableObjectToMeeting({
        apiUrl: stateSnapshot.activeSurface.apiUrl,
        workspaceId: stateSnapshot.activeSurface.workspaceId,
        resolvedObject: stateSnapshot.resolvedObject,
        role: (stateSnapshot.selection?.role ?? 'source') as AddressableObjectRole,
      });

      if (requestEpoch !== requestEpochRef.current) {
        return;
      }

      if (response.status === 'rejected') {
        setPanelState((current) => ({
          ...current,
          mode: 'error',
          attachResponse: response,
          currentMeetingId: response.meeting_id || null,
          error: response.errors[0]?.message || 'Meeting attach was rejected.',
        }));
        return;
      }

      setPanelState((current) => ({
        ...current,
        mode: 'meeting_opened',
        attachResponse: response,
        currentMeetingId: response.meeting_id,
        error: null,
      }));
    } catch (attachError) {
      if (requestEpoch !== requestEpochRef.current) {
        return;
      }

      setPanelState((current) => ({
        ...current,
        mode: 'error',
        attachResponse: null,
        currentMeetingId: null,
        error:
          attachError instanceof Error ? attachError.message : 'Failed to attach object to meeting.',
      }));
    }
  }, [invalidateInflightRequests, panelState]);

  const openGraphShellFromRail = useCallback(() => {
    if (panelState.mode === 'meeting_opened') {
      return;
    }
    if (panelState.currentMeetingId) {
      openCurrentMeeting();
      return;
    }
    if (canAttachCurrentObjectToMeeting(panelState)) {
      void attachCurrentObject();
      return;
    }
    if (panelState.activeSurface) {
      setPanelState((current) => ({
        ...current,
        mode: 'meeting_opened',
        error: null,
      }));
    }
  }, [attachCurrentObject, openCurrentMeeting, panelState]);

  const controller = useMemo<AddressableObjectHostController>(
    () => ({
      state: panelState,
      activateSurface,
      deactivateSurface,
      requestObjectTargeting,
      cancelObjectTargeting,
      clearCurrentObject,
      openCurrentMeeting,
      closeCurrentMeeting,
      captureSelection,
      attachCurrentObject,
    }),
    [
      panelState,
      activateSurface,
      deactivateSurface,
      requestObjectTargeting,
      cancelObjectTargeting,
      clearCurrentObject,
      openCurrentMeeting,
      closeCurrentMeeting,
      captureSelection,
      attachCurrentObject,
    ],
  );

  return (
    <AddressableObjectHostContext.Provider value={controller}>
      <div ref={shellRootRef} className="relative flex min-h-0 min-w-0 flex-1 flex-col">
        <div
          className="relative flex min-h-0 min-w-0 flex-1 overflow-hidden"
          data-testid="aol-workspace-region"
        >
          {children}
          <div
            className="pointer-events-none absolute inset-y-0 right-0 z-40 flex h-full items-stretch"
            data-testid="aol-shell-region"
          >
            {panelState.mode === 'idle' || panelState.mode === 'meeting_opened' ? null : (
              <div className="pointer-events-auto flex h-full items-start px-3 pb-4 pt-16">
                <AddressableObjectPanel
                  state={panelState}
                  onRequestObjectTargeting={requestObjectTargeting}
                  onCancelObjectTargeting={cancelObjectTargeting}
                  onClearCurrentObject={clearCurrentObject}
                  onAttachCurrentObject={attachCurrentObject}
                  onOpenCurrentMeeting={openCurrentMeeting}
                />
              </div>
            )}
            <AddressableObjectToolRail
              state={panelState}
              canOpenGraphShell={
                panelState.mode === 'meeting_opened' ||
                Boolean(panelState.currentMeetingId) ||
                canAttachCurrentObjectToMeeting(panelState) ||
                Boolean(panelState.activeSurface)
              }
              onRequestObjectTargeting={requestObjectTargeting}
              onCancelObjectTargeting={cancelObjectTargeting}
              onOpenGraphShell={openGraphShellFromRail}
            />
          </div>
        </div>
        <AddressableObjectMeetingPane
          state={panelState}
          paneHeight={meetingPaneHeight}
          onClose={closeCurrentMeeting}
          onResizeStart={beginMeetingPaneResize}
          onSizePreset={setMeetingPaneSizePreset}
          onSwitchObject={requestObjectTargeting}
        />
      </div>
    </AddressableObjectHostContext.Provider>
  );
}

export function AddressableObjectHostProvider({
  workspaceId,
  children,
}: AddressableObjectHostProviderProps) {
  return (
    <AddressableObjectHostProviderInner workspaceId={workspaceId}>
      {children}
    </AddressableObjectHostProviderInner>
  );
}

function AddressableObjectHostBridgeSlot({
  apiUrl,
  workspaceId,
  capabilityCode,
  route,
  surfaceId,
  children,
}: AddressableObjectHostShellProps) {
  const controller = useContext(AddressableObjectHostContext);
  const registrationIdRef = useRef<string | null>(null);

  if (!controller) {
    throw new Error('AddressableObjectHostBridgeSlot requires AddressableObjectHostProvider.');
  }

  if (!registrationIdRef.current) {
    registrationIdRef.current = `aol-surface-${Math.random().toString(36).slice(2)}`;
  }

  const surfaceContext = useMemo<AddressableObjectSurfaceContext>(
    () => ({
      apiUrl,
      workspaceId,
      capabilityCode,
      route,
      surfaceId,
    }),
    [apiUrl, workspaceId, capabilityCode, route, surfaceId],
  );

  useEffect(() => {
    const registrationId = registrationIdRef.current;
    if (!registrationId) {
      return;
    }
    controller.activateSurface(surfaceContext, registrationId);
    return () => {
      controller.deactivateSurface(surfaceContext, registrationId);
    };
  }, [controller.activateSurface, controller.deactivateSurface, surfaceContext]);

  const hostBridge = useMemo<AddressableObjectHostBridge>(
    () => ({
      mode: controller.state.mode,
      selection: controller.state.selection,
      currentMeetingId: controller.state.currentMeetingId,
      requestObjectTargeting: controller.requestObjectTargeting,
      cancelObjectTargeting: controller.cancelObjectTargeting,
      onSelectObject: (selection) => controller.captureSelection(surfaceContext, selection),
      clearCurrentObject: controller.clearCurrentObject,
      openCurrentMeeting: controller.openCurrentMeeting,
    }),
    [
      controller.captureSelection,
      controller.cancelObjectTargeting,
      controller.clearCurrentObject,
      controller.openCurrentMeeting,
      controller.requestObjectTargeting,
      controller.state.currentMeetingId,
      controller.state.mode,
      controller.state.selection,
      surfaceContext,
    ],
  );

  return <>{children(hostBridge)}</>;
}

export function AddressableObjectHostShell(props: AddressableObjectHostShellProps) {
  const existingController = useContext(AddressableObjectHostContext);

  if (existingController) {
    return <AddressableObjectHostBridgeSlot {...props} />;
  }

  return (
    <AddressableObjectHostProvider workspaceId={props.workspaceId}>
      <AddressableObjectHostBridgeSlot {...props} />
    </AddressableObjectHostProvider>
  );
}

export function useAddressableObjectHostController(): AddressableObjectHostController | null {
  return useContext(AddressableObjectHostContext);
}
