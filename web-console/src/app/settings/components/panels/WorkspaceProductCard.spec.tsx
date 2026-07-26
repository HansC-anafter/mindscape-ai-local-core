import '@testing-library/jest-dom/vitest';
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type {
  AvailableProduct,
  EffectiveProductAssignment,
} from '@/lib/workspace-product-configuration-api';
import { WorkspaceProductCard } from './WorkspaceProductCard';

function product(
  exactReadyPacks: number,
  totalPacks = 3,
): AvailableProduct {
  return {
    pcs_id: 'instagram_workspace_intelligence',
    exact_version: '1.0.0',
    display_name: 'Instagram Workspace Intelligence',
    outcome_summary: 'Govern Instagram references as one workspace product.',
    surface_ids: ['instagram.workspace.references'],
    product_surfaces: [],
    closure_summary: {
      total_packs: totalPacks,
      exact_ready_packs: exactReadyPacks,
      missing_packs: totalPacks - exactReadyPacks,
      disabled_packs: 0,
      version_mismatch_packs: 0,
    },
    pack_closure: [],
  };
}

function effective(hostReady: boolean): EffectiveProductAssignment {
  return {
    pcs_id: 'instagram_workspace_intelligence',
    pcs_version: '1.0.0',
    product_surface_ids: ['instagram.workspace.references'],
    configuration_sources: ['workspace'],
    host_ready: hostReady,
    host_admission: hostReady ? [] : [{
      pack_code: 'live_interface_interpreter',
      requirement_code: 'live_interface_automation',
      operation: 'watch-screenshots',
      admitted: false,
      blockers: ['grant_missing'],
    }],
  };
}

function renderCard(
  targetProduct: AvailableProduct,
  targetEffective?: EffectiveProductAssignment,
) {
  render(
    <WorkspaceProductCard
      product={targetProduct}
      configuredHere={Boolean(targetEffective)}
      inherited={false}
      effective={targetEffective}
      editable
      onToggle={vi.fn()}
    />,
  );
}

describe('WorkspaceProductCard readiness', () => {
  it('does not claim host readiness before the product is configured', () => {
    renderCard(product(3));

    expect(screen.getByText('Pack closure ready · not configured')).toBeInTheDocument();
    expect(screen.queryByText('Ready on this host')).not.toBeInTheDocument();
  });

  it('shows an incomplete closure as not ready before configuration', () => {
    renderCard(product(2));

    expect(screen.getByText('Pack closure incomplete')).toBeInTheDocument();
  });

  it('uses effective assignment readiness after configuration', () => {
    renderCard(product(3), effective(false));

    expect(screen.getByText('Host admission blocked')).toBeInTheDocument();
    expect(screen.getByText('grant_missing')).toBeInTheDocument();
  });
});
