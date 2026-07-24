import type {
  AvailableProduct,
  WorkspaceCapabilitySetSnapshot,
} from '@/lib/workspace-product-configuration-api';

export interface MeetingProductAdmissionRequest {
  active_group_id?: string;
  observed_topology_revision?: number;
  product_surface_id: string;
  product_selector_kind: 'api_prefix';
  product_selector_key: string;
  operation_type: 'generate';
  execution_backend: 'local';
}

function normalizeRoute(value: string): string {
  const path = value.split(/[?#]/, 1)[0] || '';
  return path.length > 1 ? path.replace(/\/+$/, '') : path;
}

function surfaceRouteMatches(
  template: string,
  actualRoute: string,
  workspaceId: string,
): boolean {
  const expected = normalizeRoute(
    template.replaceAll('{workspace_id}', encodeURIComponent(workspaceId)),
  );
  const actual = normalizeRoute(actualRoute);
  return actual === expected || actual.startsWith(`${expected}/`);
}

function assignedProductIds(
  snapshot: WorkspaceCapabilitySetSnapshot,
): Set<string> {
  return new Set(
    snapshot.effective_assignments.map(
      (assignment) => `${assignment.pcs_id}@${assignment.pcs_version}`,
    ),
  );
}

function productIsAssigned(
  product: AvailableProduct,
  assignments: Set<string>,
): boolean {
  return assignments.has(`${product.pcs_id}@${product.exact_version}`);
}

export function resolveMeetingProductAdmission({
  snapshot,
  workspaceId,
  capabilityCode,
  surfaceRoute,
}: {
  snapshot: WorkspaceCapabilitySetSnapshot;
  workspaceId: string;
  capabilityCode: string;
  surfaceRoute: string;
}): MeetingProductAdmissionRequest | null {
  const assignments = assignedProductIds(snapshot);
  const candidates = snapshot.available_products.flatMap((product) => {
    if (
      !productIsAssigned(product, assignments)
      || !product.pack_closure.some((pack) => pack.code === capabilityCode)
    ) {
      return [];
    }
    return product.product_surfaces.flatMap((surface) => {
      const routeMatches = surface.selectors.ui_routes.some((route) => (
        surfaceRouteMatches(route, surfaceRoute, workspaceId)
      ));
      const selector = surface.selectors.api_prefixes[0];
      return routeMatches && selector ? [{ surface, selector }] : [];
    });
  });
  if (candidates.length !== 1) {
    return null;
  }
  const [{ surface, selector }] = candidates;
  return {
    ...(snapshot.explicit_active_group_id
      ? { active_group_id: snapshot.explicit_active_group_id }
      : {}),
    ...(snapshot.topology_revision
      ? { observed_topology_revision: snapshot.topology_revision }
      : {}),
    product_surface_id: surface.id,
    product_selector_kind: 'api_prefix',
    product_selector_key: selector,
    operation_type: 'generate',
    execution_backend: 'local',
  };
}
