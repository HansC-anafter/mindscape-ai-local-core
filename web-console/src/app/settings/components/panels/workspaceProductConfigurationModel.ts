import type {
  AvailableProduct,
  ProductAssignment,
  ScopeConfiguration,
  WorkspaceCapabilitySetSnapshot,
  WorkspaceProductAdmissionMode,
  WorkspaceProductScopeKind,
} from '@/lib/workspace-product-configuration-api';

export interface WorkspaceProductDraft {
  scopeKind: WorkspaceProductScopeKind;
  assignments: ProductAssignment[];
  admissionMode: Exclude<WorkspaceProductAdmissionMode, 'legacy_unmanaged'>;
}

export function selectedScope(
  snapshot: WorkspaceCapabilitySetSnapshot,
  scopeKind: WorkspaceProductScopeKind,
): ScopeConfiguration | null {
  const scopeId = scopeKind === 'workspace'
    ? snapshot.workspace_id
    : snapshot.explicit_active_group_id;
  return snapshot.scope_configurations.find(
    (scope) => scope.scope_kind === scopeKind && scope.scope_id === scopeId,
  ) || null;
}

export function createDraft(
  snapshot: WorkspaceCapabilitySetSnapshot,
  scopeKind: WorkspaceProductScopeKind,
): WorkspaceProductDraft {
  const scope = selectedScope(snapshot, scopeKind);
  const mode = snapshot.workspace_admission_mode === 'legacy_unmanaged'
    ? 'configuration_only'
    : snapshot.workspace_admission_mode;
  return {
    scopeKind,
    assignments: scope?.assignments.map((assignment) => ({ ...assignment })) || [],
    admissionMode: mode,
  };
}

export function assignmentKey(assignment: ProductAssignment): string {
  return `${assignment.pcs_id}@${assignment.pcs_version}`;
}

export function toggleProduct(
  draft: WorkspaceProductDraft,
  product: AvailableProduct,
): WorkspaceProductDraft {
  const target = `${product.pcs_id}@${product.exact_version}`;
  const exists = draft.assignments.some((item) => assignmentKey(item) === target);
  return {
    ...draft,
    assignments: (
      exists
        ? draft.assignments.filter((item) => assignmentKey(item) !== target)
        : [
            ...draft.assignments,
            { pcs_id: product.pcs_id, pcs_version: product.exact_version },
          ]
    ).sort((left, right) => assignmentKey(left).localeCompare(assignmentKey(right))),
  };
}

export function productConfigured(
  draft: WorkspaceProductDraft,
  product: AvailableProduct,
): boolean {
  const target = `${product.pcs_id}@${product.exact_version}`;
  return draft.assignments.some((item) => assignmentKey(item) === target);
}

export function draftChanges(
  snapshot: WorkspaceCapabilitySetSnapshot,
  draft: WorkspaceProductDraft,
): { added: string[]; removed: string[]; modeChanged: boolean } {
  const current = selectedScope(snapshot, draft.scopeKind);
  const before = new Set((current?.assignments || []).map(assignmentKey));
  const after = new Set(draft.assignments.map(assignmentKey));
  return {
    added: [...after].filter((key) => !before.has(key)).sort(),
    removed: [...before].filter((key) => !after.has(key)).sort(),
    modeChanged: draft.scopeKind === 'workspace'
      && draft.admissionMode !== (
        snapshot.workspace_admission_mode === 'legacy_unmanaged'
          ? 'configuration_only'
          : snapshot.workspace_admission_mode
      ),
  };
}

