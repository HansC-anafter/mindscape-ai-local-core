import { useMemo } from 'react';

import {
  useWorkspaceCapabilitySetOptional,
} from '@/components/workspace-products/WorkspaceCapabilitySetProvider';
import {
  resolveMeetingProductAdmission,
} from '@/components/workspace-products/workspaceMeetingAdmission';

export function useMeetingProductAdmission({
  workspaceId,
  capabilityCode,
  surfaceRoute,
}: {
  workspaceId: string;
  capabilityCode: string;
  surfaceRoute: string;
}) {
  const workspaceProducts = useWorkspaceCapabilitySetOptional();
  const productAdmission = useMemo(() => (
    workspaceProducts?.snapshot
      ? resolveMeetingProductAdmission({
          snapshot: workspaceProducts.snapshot,
          workspaceId,
          capabilityCode,
          surfaceRoute,
        })
      : null
  ), [
    capabilityCode,
    surfaceRoute,
    workspaceId,
    workspaceProducts?.snapshot,
  ]);
  const startBlockReason = workspaceProducts?.loading
    ? 'Workspace product configuration is still loading.'
    : (
        workspaceProducts?.snapshot?.workspace_admission_mode === 'enforced'
        && !productAdmission
          ? 'This Meeting surface is not assigned to an active workspace product.'
          : null
      );
  return { productAdmission, startBlockReason };
}
