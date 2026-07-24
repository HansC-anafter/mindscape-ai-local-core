import type { WorkspaceCapabilitySetSnapshot } from '@/lib/workspace-product-configuration-api';
import {
  draftChanges,
  selectedScope,
  type WorkspaceProductDraft,
} from './workspaceProductConfigurationModel';

export function WorkspaceProductChangeReview({
  snapshot,
  draft,
  applying,
  onCancel,
  onApply,
}: {
  snapshot: WorkspaceCapabilitySetSnapshot;
  draft: WorkspaceProductDraft;
  applying: boolean;
  onCancel: () => void;
  onApply: () => void;
}) {
  const changes = draftChanges(snapshot, draft);
  const scope = selectedScope(snapshot, draft.scopeKind);
  return (
    <section
      className="rounded-lg border border-indigo-300 bg-indigo-50 p-4 dark:border-indigo-800 dark:bg-indigo-950/30"
      data-testid="workspace-product-change-review"
    >
      <h3 className="font-semibold text-gray-900 dark:text-gray-100">Review changes</h3>
      <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">
        Scope: {draft.scopeKind} · current revision {scope?.revision || 0}
      </p>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <div>
          <div className="text-xs font-semibold uppercase text-gray-500">Add</div>
          <div className="text-sm">{changes.added.join(', ') || 'None'}</div>
        </div>
        <div>
          <div className="text-xs font-semibold uppercase text-gray-500">Remove</div>
          <div className="text-sm">{changes.removed.join(', ') || 'None'}</div>
        </div>
      </div>
      {draft.scopeKind === 'workspace' ? (
        <p className="mt-3 text-sm">Governance mode after apply: {draft.admissionMode}</p>
      ) : null}
      <p className="mt-3 text-sm text-gray-700 dark:text-gray-300">
        New runs use the new configuration. Already admitted runs and history are preserved.
      </p>
      <div className="mt-4 flex gap-2">
        <button
          type="button"
          onClick={onApply}
          disabled={applying}
          className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {applying ? 'Applying…' : 'Apply configuration'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={applying}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium dark:border-gray-700"
        >
          Back to draft
        </button>
      </div>
    </section>
  );
}

