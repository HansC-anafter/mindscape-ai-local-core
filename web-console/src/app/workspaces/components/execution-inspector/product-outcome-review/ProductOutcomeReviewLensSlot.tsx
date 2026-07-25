'use client';

import { useEffect, useState } from 'react';
import type { ComponentType } from 'react';
import type { UIComponentInfo } from '@/lib/capability-ui-loader';
import { selectPinnedReviewLensComponent } from './reviewLens';
import type { ReviewLensPin } from './types';

interface Props {
  active: boolean;
  apiUrl: string;
  workspaceId: string;
  iterationId: string;
  summaryEndpoint: string;
  genericReviewHref: string;
  pin: ReviewLensPin | null;
}

export function ProductOutcomeReviewLensSlot({
  active,
  apiUrl,
  workspaceId,
  iterationId,
  summaryEndpoint,
  genericReviewHref,
  pin,
}: Props) {
  const [Lens, setLens] = useState<ComponentType<any> | null>(null);

  useEffect(() => {
    setLens(null);
    if (!active || !pin) return;
    const controller = new AbortController();
    const metadataUrl = (
      `${apiUrl}/api/v1/capability-packs/installed-capabilities/`
      + `${encodeURIComponent(pin.capability_code)}/ui-components`
      + `?workspace_id=${encodeURIComponent(workspaceId)}`
    );
    void fetch(metadataUrl, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) return null;
        const components = await response.json() as UIComponentInfo[];
        const selection = selectPinnedReviewLensComponent(components, pin);
        if (!selection) return null;
        const loader = await import('@/lib/capability-ui-loader');
        loader.primeCapabilityUIComponentMetadata(
          pin.capability_code,
          [selection.component],
        );
        return loader.loadCapabilityUIComponent(
          pin.capability_code,
          pin.component_code,
          apiUrl,
          workspaceId,
        );
      })
      .then((Component) => {
        if (!controller.signal.aborted) setLens(() => Component);
      })
      .catch(() => {
        if (!controller.signal.aborted) setLens(null);
      });
    return () => controller.abort();
  }, [active, apiUrl, pin, workspaceId]);

  if (!active || !pin || !Lens) return null;
  return (
    <Lens
      workspaceId={workspaceId}
      iterationId={iterationId}
      summaryEndpoint={summaryEndpoint}
      genericReviewHref={genericReviewHref}
    />
  );
}
