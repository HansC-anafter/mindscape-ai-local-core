'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import {
  getEffectiveWorkspaceProductConfiguration,
  type AvailableProduct,
  type WorkspaceCapabilitySetSnapshot,
} from '@/lib/workspace-product-configuration-api';

const MAX_CAPABILITY_LINKS = 64;

interface WorkspaceSummary {
  id: string;
  name: string;
  status: string | null;
}

interface CapabilityLink {
  code: string;
  label: string;
}

interface LandingState {
  workspace: WorkspaceSummary;
  capabilities: CapabilityLink[];
  products: AvailableProduct[];
  productSnapshot: WorkspaceCapabilitySetSnapshot;
}

function boundedText(value: unknown, maximum: number): string {
  return typeof value === 'string' ? value.trim().slice(0, maximum) : '';
}

function normalizeWorkspaceSummary(payload: unknown, workspaceId: string): WorkspaceSummary {
  const row = payload && typeof payload === 'object' && !Array.isArray(payload)
    ? payload as Record<string, unknown>
    : {};
  if (boundedText(row.id, 128) !== workspaceId) {
    throw new Error('workspace_summary_identity_mismatch');
  }
  return {
    id: workspaceId,
    name: boundedText(row.name, 160) || `Workspace ${workspaceId}`,
    status: boundedText(row.status, 64) || null,
  };
}

function normalizeCapabilityLinks(payload: unknown): CapabilityLink[] {
  if (!Array.isArray(payload)) return [];
  const seen = new Set<string>();
  const links: CapabilityLink[] = [];
  for (const item of payload) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) continue;
    const row = item as Record<string, unknown>;
    const code = boundedText(row.code || row.id, 128).toLowerCase();
    if (!/^[a-z0-9][a-z0-9_-]*$/.test(code) || seen.has(code)) continue;
    seen.add(code);
    links.push({
      code,
      label: boundedText(row.display_name, 160) || code,
    });
    if (links.length === MAX_CAPABILITY_LINKS) break;
  }
  return links;
}

async function readJson(response: Response): Promise<unknown> {
  if (!response.ok) throw new Error(`remote_workspace_request_failed:${response.status}`);
  return response.json();
}

export default function RemoteWorkspaceLanding({
  workspaceId,
  activeGroupId,
  topologyRevision,
}: {
  workspaceId: string;
  activeGroupId?: string;
  topologyRevision?: number;
}) {
  const [state, setState] = useState<LandingState | null>(null);
  const [failed, setFailed] = useState(false);
  const groupQuery = new URLSearchParams({
    ...(activeGroupId ? { active_group_id: activeGroupId } : {}),
    ...(topologyRevision ? { topology_revision: String(topologyRevision) } : {}),
  }).toString();

  useEffect(() => {
    const controller = new AbortController();
    const encodedWorkspaceId = encodeURIComponent(workspaceId);
    void Promise.all([
      fetch(`/api/v1/workspaces/${encodedWorkspaceId}/summary`, {
        credentials: 'same-origin',
        signal: controller.signal,
      }).then(readJson),
      fetch(
        `/api/v1/capability-packs/installed-capabilities?workspace_id=${encodedWorkspaceId}`,
        { credentials: 'same-origin', signal: controller.signal },
      ).then(readJson),
      getEffectiveWorkspaceProductConfiguration({
        workspaceId,
        activeGroupId,
        topologyRevision,
        signal: controller.signal,
      }),
    ])
      .then(([workspace, capabilities, productSnapshot]) => {
        setState({
          workspace: normalizeWorkspaceSummary(workspace, workspaceId),
          capabilities: normalizeCapabilityLinks(capabilities),
          products: productSnapshot.available_products,
          productSnapshot,
        });
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          console.error('[RemoteWorkspaceLanding] Failed to load bounded landing data:', error);
          setFailed(true);
        }
      });
    return () => controller.abort();
  }, [activeGroupId, topologyRevision, workspaceId]);

  return (
    <main className="min-h-screen bg-surface px-6 py-10 text-primary dark:bg-gray-950 dark:text-gray-100">
      <div className="mx-auto max-w-4xl space-y-8">
        <header className="space-y-2">
          <p className="text-sm font-medium text-secondary dark:text-gray-400">Remote workspace</p>
          <h1 className="text-3xl font-semibold">
            {state?.workspace.name || `Workspace ${workspaceId}`}
          </h1>
          <p className="text-sm text-secondary dark:text-gray-400">Workspace ID: {workspaceId}</p>
          {state?.workspace.status ? (
            <p className="text-sm text-secondary dark:text-gray-400">
              Status: {state.workspace.status}
            </p>
          ) : null}
        </header>

        <section aria-labelledby="remote-products-heading" className="space-y-4">
          <div>
            <h2 id="remote-products-heading" className="text-xl font-semibold">Workspace products</h2>
            <p className="text-sm text-secondary dark:text-gray-400">
              Read-only configuration from source runtime {state?.productSnapshot.source_runtime_id || '…'}.
            </p>
          </div>
          {state ? (
            <ul className="grid gap-3 sm:grid-cols-2" data-testid="remote-workspace-product-rail">
              {state.products.map((product) => {
                const effective = state.productSnapshot.effective_assignments.find(
                  (item) => item.pcs_id === product.pcs_id
                    && item.pcs_version === product.exact_version,
                );
                return (
                  <li
                    key={`${product.pcs_id}@${product.exact_version}`}
                    className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
                  >
                    <div className="font-medium">{product.display_name}</div>
                    <p className="mt-1 text-sm text-secondary dark:text-gray-400">
                      {product.outcome_summary}
                    </p>
                    <p className="mt-2 text-xs text-secondary dark:text-gray-400">
                      {effective ? 'Configured' : 'Not configured'} · {effective?.host_ready ? 'Host ready' : 'Host not ready'}
                    </p>
                  </li>
                );
              })}
            </ul>
          ) : null}
        </section>

        <section aria-labelledby="remote-capabilities-heading" className="space-y-4">
          <div>
            <h2 id="remote-capabilities-heading" className="text-xl font-semibold">Available tools</h2>
            <p className="text-sm text-secondary dark:text-gray-400">
              Only installed tools approved for this workspace are shown.
            </p>
          </div>
          {!state && !failed ? <p role="status">Loading available tools…</p> : null}
          {failed ? (
            <p role="alert">This workspace summary is temporarily unavailable.</p>
          ) : null}
          {state && state.capabilities.length === 0 ? (
            <p>No approved tools are currently installed.</p>
          ) : null}
          {state && state.capabilities.length > 0 ? (
            <ul className="grid gap-3 sm:grid-cols-2">
              {state.capabilities.map((capability) => (
                <li key={capability.code}>
                  <Link
                    className="block rounded-lg border border-gray-200 bg-white p-4 font-medium hover:border-blue-500 dark:border-gray-800 dark:bg-gray-900"
                    href={
                      `/workspaces/${encodeURIComponent(workspaceId)}`
                      + `/capability-ui-hosts/${encodeURIComponent(capability.code)}`
                      + (groupQuery ? `?${groupQuery}` : '')
                    }
                    prefetch={false}
                  >
                    {capability.label}
                  </Link>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      </div>
    </main>
  );
}
