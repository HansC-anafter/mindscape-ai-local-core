import type {
  AddressableObjectRole,
  AddressableSelectionCandidate,
} from '@/lib/addressable-object-layer';
import type { AOLRuntimeShellState } from './AOLRuntimeShellContext';
import {
  ADDRESSABLE_OBJECT_ROLE_OPTIONS,
  buildStatusCopy,
  canAttachCurrentObjectToMeeting,
} from './runtimeShellState';

function getCandidateTitle(candidate: AddressableSelectionCandidate): string {
  return candidate.summary?.title || candidate.ref.object_id || candidate.ref.uri;
}

function getCandidateSubtitle(candidate: AddressableSelectionCandidate): string {
  const parts = [
    candidate.ref.owner_pack,
    candidate.ref.object_kind,
    candidate.summary?.subtitle || null,
  ].filter(Boolean);
  return parts.join(' / ');
}

function RuntimeObjectRoleSegmentedControl({
  value,
  onChange,
  disabled = false,
}: {
  value: AddressableObjectRole;
  onChange: (role: AddressableObjectRole) => void;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-1.5" data-testid="aol-role-control">
      <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400">
        Context role
      </div>
      <div
        className="grid grid-cols-5 overflow-hidden rounded-lg border border-gray-200 bg-gray-100 p-0.5 dark:border-gray-700 dark:bg-gray-800"
        role="radiogroup"
        aria-label="Object context role"
      >
        {ADDRESSABLE_OBJECT_ROLE_OPTIONS.map((option) => {
          const isActive = option.role === value;
          return (
            <button
              key={option.role}
              type="button"
              role="radio"
              aria-checked={isActive}
              disabled={disabled}
              title={option.title}
              data-testid={`aol-role-option-${option.role}`}
              onClick={() => onChange(option.role)}
              className={`h-8 min-w-0 truncate rounded-md px-1.5 text-[11px] font-medium transition-colors ${
                isActive
                  ? 'bg-white text-blue-700 shadow-sm dark:bg-gray-950 dark:text-blue-300'
                  : 'text-gray-600 hover:bg-white/70 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-900/70 dark:hover:text-gray-100'
              } disabled:cursor-not-allowed disabled:opacity-60`}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function RuntimeObjectCandidatePicker({
  candidates,
  onSelectCandidate,
}: {
  candidates: AddressableSelectionCandidate[];
  onSelectCandidate: (candidate: AddressableSelectionCandidate) => void;
}) {
  if (candidates.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2" data-testid="aol-candidate-picker">
      <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400">
        Candidate objects
      </div>
      <div className="space-y-1.5">
        {candidates.map((candidate) => {
          const title = getCandidateTitle(candidate);
          return (
            <button
              key={candidate.ref.uri}
              type="button"
              onClick={() => onSelectCandidate(candidate)}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-left transition-colors hover:border-blue-300 hover:bg-blue-50 dark:border-gray-700 dark:bg-gray-900 dark:hover:border-blue-700 dark:hover:bg-blue-950/30"
              data-testid={`aol-candidate-${candidate.ref.object_id}`}
            >
              <div className="truncate text-sm font-medium text-gray-900 dark:text-gray-100">
                {title}
              </div>
              <div className="mt-0.5 truncate text-xs text-gray-500 dark:text-gray-400">
                {getCandidateSubtitle(candidate)}
              </div>
              {candidate.summary?.summary_text ? (
                <div className="mt-1 max-h-10 overflow-hidden text-xs leading-5 text-gray-600 dark:text-gray-300">
                  {candidate.summary.summary_text}
                </div>
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function RuntimeObjectPanel({
  state,
  onRequestObjectTargeting,
  onCancelObjectTargeting,
  onClearCurrentObject,
  onAttachCurrentObject,
  onOpenCurrentMeeting,
  onRoleChange,
  onSelectCandidate,
}: {
  state: AOLRuntimeShellState;
  onRequestObjectTargeting: () => void;
  onCancelObjectTargeting: () => void;
  onClearCurrentObject: () => void;
  onAttachCurrentObject: () => void;
  onOpenCurrentMeeting: () => void;
  onRoleChange: (role: AddressableObjectRole) => void;
  onSelectCandidate: (candidate: AddressableSelectionCandidate) => void;
}) {
  if (state.mode === 'idle') {
    return null;
  }

  const summary = state.resolvedObject?.summary ?? null;
  const actions = state.resolvedObject?.actions ?? [];
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

        {state.mode !== 'resolving' && state.mode !== 'attaching' ? (
          <RuntimeObjectRoleSegmentedControl
            value={state.contextRole}
            onChange={onRoleChange}
            disabled={Boolean(state.currentMeetingId)}
          />
        ) : null}

        <RuntimeObjectCandidatePicker
          candidates={state.candidateObjects}
          onSelectCandidate={onSelectCandidate}
        />

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

export const AddressableObjectPanel = RuntimeObjectPanel;
