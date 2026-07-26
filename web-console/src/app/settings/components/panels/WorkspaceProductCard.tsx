import type {
  AvailableProduct,
  EffectiveProductAssignment,
} from '@/lib/workspace-product-configuration-api';
import { HostAdmissionDetails } from '@/components/workspace-products/HostAdmissionDetails';

export function WorkspaceProductCard({
  product,
  configuredHere,
  inherited,
  effective,
  editable,
  onToggle,
}: {
  product: AvailableProduct;
  configuredHere: boolean;
  inherited: boolean;
  effective?: EffectiveProductAssignment;
  editable: boolean;
  onToggle: () => void;
}) {
  const closureReady = (
    product.closure_summary.total_packs > 0
    && product.closure_summary.exact_ready_packs === product.closure_summary.total_packs
  );
  const hostReady = effective?.host_ready === true;
  const readinessLabel = effective
    ? hostReady
      ? 'Ready on this host'
      : 'Host admission blocked'
    : closureReady
      ? 'Pack closure ready · not configured'
      : 'Pack closure incomplete';
  const sourceLabel = configuredHere
    ? 'Configured here'
    : inherited
      ? 'Inherited from active group'
      : 'Not configured';

  return (
    <article
      className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950"
      data-testid={`workspace-product-card-${product.pcs_id}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">
            {product.display_name}
          </h3>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
            {product.outcome_summary}
          </p>
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            <span className="rounded bg-indigo-50 px-2 py-1 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
              {sourceLabel}
            </span>
            <span className={`rounded px-2 py-1 ${
              hostReady
                ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300'
                : 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300'
            }`}>
              {readinessLabel}
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={onToggle}
          disabled={!editable}
          aria-pressed={configuredHere}
          className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700"
        >
          {configuredHere ? 'Remove' : 'Configure'}
        </button>
      </div>
      <details className="mt-3 text-xs text-gray-600 dark:text-gray-400">
        <summary className="cursor-pointer font-medium">
          Exact pack closure ({product.closure_summary.exact_ready_packs}/{product.closure_summary.total_packs} ready)
        </summary>
        <ul className="mt-2 space-y-1">
          {product.pack_closure.map((pack) => (
            <li key={`${pack.provider}:${pack.code}@${pack.version}`}>
              {pack.provider}:{pack.code}@{pack.version} · {pack.readiness}
            </li>
          ))}
        </ul>
      </details>
      <HostAdmissionDetails details={effective?.host_admission || []} />
      {!closureReady ? (
        <a
          href="/settings?tab=packs_status&section=packages"
          className="mt-3 inline-block text-xs font-medium text-blue-700 underline dark:text-blue-300"
        >
          Open Capability Packs
        </a>
      ) : null}
    </article>
  );
}
