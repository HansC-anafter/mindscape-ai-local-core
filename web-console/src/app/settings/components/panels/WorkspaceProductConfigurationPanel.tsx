'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';

import {
  WorkspaceCapabilitySetProvider,
  useWorkspaceCapabilitySet,
} from '@/components/workspace-products/WorkspaceCapabilitySetProvider';
import {
  WorkspaceProductApiError,
  type WorkspaceProductScopeKind,
} from '@/lib/workspace-product-configuration-api';
import { WorkspaceProductCard } from './WorkspaceProductCard';
import { WorkspaceProductChangeReview } from './WorkspaceProductChangeReview';
import {
  createDraft,
  draftChanges,
  productConfigured,
  selectedScope,
  toggleProduct,
  type WorkspaceProductDraft,
} from './workspaceProductConfigurationModel';

function Editor() {
  const { snapshot, loading, error, refresh, replace } = useWorkspaceCapabilitySet();
  const [scopeKind, setScopeKind] = useState<WorkspaceProductScopeKind>('workspace');
  const [draft, setDraft] = useState<WorkspaceProductDraft | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const preserveDraftRef = useRef(false);

  useEffect(() => {
    if (!snapshot) return;
    if (preserveDraftRef.current) {
      preserveDraftRef.current = false;
      return;
    }
    setDraft(createDraft(snapshot, scopeKind));
  }, [scopeKind, snapshot, snapshot?.snapshot_hash]);

  const changes = useMemo(
    () => (snapshot && draft ? draftChanges(snapshot, draft) : null),
    [draft, snapshot],
  );
  const changed = Boolean(
    changes
    && (changes.added.length || changes.removed.length || changes.modeChanged),
  );

  if (loading && !snapshot) return <p role="status">Loading workspace products…</p>;
  if (!snapshot || !draft) {
    return (
      <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
        Workspace product configuration is unavailable. {error?.message || ''}
      </div>
    );
  }

  const scope = selectedScope(snapshot, scopeKind);
  const groupAvailable = Boolean(snapshot.explicit_active_group_id);
  const editable = scopeKind === 'workspace'
    ? snapshot.editable_scopes.includes('workspace')
    : groupAvailable && snapshot.editable_scopes.includes('workspace_group');

  const apply = async () => {
    setApplying(true);
    setApplyError(null);
    try {
      const admissionMode = snapshot.workspace_admission_mode === 'legacy_unmanaged'
        ? 'configuration_only'
        : draft.admissionMode;
      await replace(scopeKind, {
        expected_revision: scope?.revision || 0,
        assignments: draft.assignments,
        catalog_hash: snapshot.catalog_hash,
        ...(scopeKind === 'workspace'
          ? { admission_mode: admissionMode }
          : {}),
      });
      setReviewing(false);
    } catch (requestError) {
      if (requestError instanceof WorkspaceProductApiError && requestError.status === 409) {
        setApplyError('Revision conflict. Your draft is preserved; load latest and compare before applying again.');
      } else {
        setApplyError('Configuration could not be applied. No automatic retry was started.');
      }
    } finally {
      setApplying(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="workspace-product-configuration-panel">
      <section className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950">
        <h2 className="text-lg font-semibold">Workspace Products</h2>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
          This is where you decide which products this workspace intends to use.
        </p>
        <dl className="mt-3 grid gap-2 text-xs md:grid-cols-4">
          <div><dt className="text-gray-500">Workspace</dt><dd>{snapshot.workspace_id}</dd></div>
          <div><dt className="text-gray-500">Active group</dt><dd>{snapshot.explicit_active_group_id || 'None selected'}</dd></div>
          <div><dt className="text-gray-500">Source runtime</dt><dd>{snapshot.source_runtime_id}</dd></div>
          <div><dt className="text-gray-500">Mode</dt><dd>{snapshot.workspace_admission_mode}</dd></div>
        </dl>
        <div className="mt-3 rounded border border-gray-200 p-3 text-xs dark:border-gray-800">
          <div className="font-medium">Deployment control</div>
          <div className="mt-1 text-gray-600 dark:text-gray-400">
            {snapshot.deployment_control?.mode || 'unavailable'}
            {snapshot.deployment_control?.provider_code
              ? ` · Commercial control: ${snapshot.deployment_control.provider_code}`
              : ' · Local Core unmanaged'}
            {snapshot.deployment_control
              ? ` · state revision ${snapshot.deployment_control.state_revision}`
              : ''}
          </div>
          <p className="mt-1 text-gray-500">
            Deployment control can narrow configured intent; it never rewrites this workspace assignment.
          </p>
        </div>
      </section>

      <section className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => {
            setScopeKind('workspace');
            setReviewing(false);
            setApplyError(null);
          }}
          aria-pressed={scopeKind === 'workspace'}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm dark:border-gray-700"
        >
          This workspace
        </button>
        <button
          type="button"
          disabled={!groupAvailable}
          onClick={() => {
            setScopeKind('workspace_group');
            setReviewing(false);
            setApplyError(null);
          }}
          aria-pressed={scopeKind === 'workspace_group'}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm disabled:opacity-50 dark:border-gray-700"
        >
          Active workspace group
        </button>
        {!groupAvailable ? (
          <p className="self-center text-xs text-amber-700">
            Select an explicit workspace group in the workspace before editing group scope.
          </p>
        ) : null}
      </section>

      {scopeKind === 'workspace' ? (
        <label className="block rounded-lg border border-gray-200 bg-white p-4 text-sm dark:border-gray-800 dark:bg-gray-950">
          <span className="font-medium">Governance mode</span>
          <select
            value={draft.admissionMode}
            disabled={!editable || snapshot.workspace_admission_mode === 'legacy_unmanaged'}
            onChange={(event) => setDraft({
              ...draft,
              admissionMode: event.target.value as WorkspaceProductDraft['admissionMode'],
            })}
            className="ml-3 rounded border border-gray-300 bg-white px-2 py-1 dark:border-gray-700 dark:bg-gray-900"
          >
            <option value="configuration_only">Configuration only</option>
            <option value="shadow">Shadow</option>
            <option value="enforced">Enforced</option>
          </select>
          <p className="mt-2 text-xs text-gray-500">
            {snapshot.workspace_admission_mode === 'legacy_unmanaged'
              ? 'The first save is always Configuration only. Review host readiness, then advance to Shadow and Enforced in separate reviewed changes.'
              : 'Configuration only saves intent; Shadow records outcomes; Enforced blocks non-permitted new runs.'}
          </p>
        </label>
      ) : null}

      {snapshot.configuration_errors.length ? (
        <div role="alert" className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
          Configuration conflict: {snapshot.configuration_errors.join(', ')}
        </div>
      ) : null}

      <div className="grid gap-3 xl:grid-cols-2">
        {snapshot.available_products.map((product) => {
          const effective = snapshot.effective_assignments.find(
            (item) => item.pcs_id === product.pcs_id && item.pcs_version === product.exact_version,
          );
          const inherited = Boolean(
            effective
            && !productConfigured(draft, product)
            && effective.configuration_sources.some((source) => source !== scopeKind),
          );
          return (
            <WorkspaceProductCard
              key={`${product.pcs_id}@${product.exact_version}`}
              product={product}
              configuredHere={productConfigured(draft, product)}
              inherited={inherited}
              effective={effective}
              editable={Boolean(editable && !inherited)}
              onToggle={() => setDraft(toggleProduct(draft, product))}
            />
          );
        })}
      </div>

      {applyError ? (
        <div role="alert" className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">
          {applyError}
          {applyError.startsWith('Revision conflict') ? (
            <button
              type="button"
              onClick={() => {
                preserveDraftRef.current = true;
                void refresh().catch(() => {
                  preserveDraftRef.current = false;
                });
              }}
              className="ml-2 font-medium underline"
            >
              Load latest and compare
            </button>
          ) : null}
        </div>
      ) : null}

      {reviewing ? (
        <WorkspaceProductChangeReview
          snapshot={snapshot}
          draft={draft}
          applying={applying}
          onCancel={() => setReviewing(false)}
          onApply={() => void apply()}
        />
      ) : (
        <button
          type="button"
          disabled={!editable || !changed}
          onClick={() => setReviewing(true)}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Review changes
        </button>
      )}
    </div>
  );
}

export function WorkspaceProductConfigurationPanel({
  workspaceId,
  activeGroupId,
  topologyRevision,
}: {
  workspaceId?: string;
  activeGroupId?: string;
  topologyRevision?: number;
}) {
  if (!workspaceId) {
    return (
      <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
        Open Workspace Products from a workspace so the workspace_id is explicit.
      </div>
    );
  }
  return (
    <WorkspaceCapabilitySetProvider
      workspaceId={workspaceId}
      activeGroupId={activeGroupId}
      topologyRevision={topologyRevision}
    >
      <Editor />
    </WorkspaceCapabilitySetProvider>
  );
}
