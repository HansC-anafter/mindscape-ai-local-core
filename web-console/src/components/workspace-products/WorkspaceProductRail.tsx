'use client';

import {
  WorkspaceCapabilitySetProvider,
  useWorkspaceCapabilitySet,
} from './WorkspaceCapabilitySetProvider';

function ProductRailContent({
  workspaceId,
  activeGroupId,
  topologyRevision,
  readOnly,
}: {
  workspaceId: string;
  activeGroupId?: string | null;
  topologyRevision?: number | null;
  readOnly: boolean;
}) {
  const { snapshot, loading, error } = useWorkspaceCapabilitySet();
  const query = new URLSearchParams({
    tab: 'workspace_products',
    workspace_id: workspaceId,
  });
  if (activeGroupId) query.set('active_group_id', activeGroupId);
  if (topologyRevision) query.set('topology_revision', String(topologyRevision));

  if (loading && !snapshot) {
    return <p className="p-3 text-xs text-gray-500">Loading workspace products…</p>;
  }
  if (!snapshot) {
    return (
      <p role="alert" className="p-3 text-xs text-red-700">
        Product configuration unavailable. {error?.message || ''}
      </p>
    );
  }

  return (
    <div className="space-y-3 p-3" data-testid="workspace-product-rail">
      <div className="rounded border border-gray-200 bg-white p-3 dark:border-gray-800 dark:bg-gray-950">
        <div className="text-xs font-semibold">Workspace product intent</div>
        <div className="mt-1 text-[10px] text-gray-500">
          source {snapshot.source_runtime_id} · revision {snapshot.workspace_scope_revision}
          {snapshot.explicit_active_group_id
            ? ` · group ${snapshot.explicit_active_group_id}@${snapshot.group_scope_revision}`
            : ''}
        </div>
        <div className="mt-1 text-[10px] text-gray-500">
          governance {snapshot.workspace_admission_mode}
        </div>
        <div className="mt-1 text-[10px] text-gray-500">
          deployment {snapshot.deployment_control?.mode || 'unavailable'}
          {snapshot.deployment_control?.provider_code
            ? ` · ${snapshot.deployment_control.provider_code}`
            : ''}
        </div>
        {!readOnly ? (
          <a
            href={`/settings?${query.toString()}`}
            className="mt-2 inline-block text-xs font-medium text-blue-700 underline dark:text-blue-300"
          >
            Manage workspace products
          </a>
        ) : null}
      </div>
      {snapshot.available_products.map((product) => {
        const effective = snapshot.effective_assignments.find(
          (item) => item.pcs_id === product.pcs_id && item.pcs_version === product.exact_version,
        );
        const configured = Boolean(effective);
        return (
          <article
            key={`${product.pcs_id}@${product.exact_version}`}
            className="rounded border border-gray-200 bg-white p-3 dark:border-gray-800 dark:bg-gray-950"
          >
            <div className="text-xs font-semibold text-gray-900 dark:text-gray-100">
              {product.display_name}
            </div>
            <p className="mt-1 text-[10px] text-gray-500">{product.outcome_summary}</p>
            <div className="mt-2 flex flex-wrap gap-1 text-[10px]">
              <span className={`rounded px-1.5 py-0.5 ${
                configured ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-600'
              }`}>
                {configured ? 'Configured' : 'Not configured'}
              </span>
              <span className={`rounded px-1.5 py-0.5 ${
                effective?.host_ready
                  ? 'bg-emerald-100 text-emerald-700'
                  : 'bg-amber-100 text-amber-700'
              }`}>
                {effective?.host_ready ? 'Host ready' : 'Host not ready'}
              </span>
              {effective?.configuration_sources.map((source) => (
                <span key={source} className="rounded bg-purple-100 px-1.5 py-0.5 text-purple-700">
                  {source === 'workspace_group' ? 'Inherited from active group' : 'Configured here'}
                </span>
              ))}
            </div>
            <details className="mt-2 text-[10px] text-gray-500">
              <summary>Exact closure</summary>
              {product.pack_closure.map((pack) => (
                <div key={`${pack.provider}:${pack.code}@${pack.version}`}>
                  {pack.code}@{pack.version} · {pack.readiness}
                </div>
              ))}
            </details>
          </article>
        );
      })}
    </div>
  );
}

export function WorkspaceProductRail({
  workspaceId,
  activeGroupId,
  topologyRevision,
  readOnly = false,
}: {
  workspaceId: string;
  activeGroupId?: string | null;
  topologyRevision?: number | null;
  readOnly?: boolean;
}) {
  return (
    <WorkspaceCapabilitySetProvider
      workspaceId={workspaceId}
      activeGroupId={activeGroupId}
      topologyRevision={topologyRevision}
    >
      <ProductRailContent
        workspaceId={workspaceId}
        activeGroupId={activeGroupId}
        topologyRevision={topologyRevision}
        readOnly={readOnly}
      />
    </WorkspaceCapabilitySetProvider>
  );
}
