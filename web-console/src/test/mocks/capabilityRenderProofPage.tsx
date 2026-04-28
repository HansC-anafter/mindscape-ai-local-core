'use client';

import React from 'react';

import type { AddressableObjectHostBridge } from '@/lib/addressable-object-layer';

interface CapabilityRenderProofPageProps {
  workspaceId?: string;
  apiUrl?: string;
  aolHost?: AddressableObjectHostBridge;
}

export default function CapabilityRenderProofPage({
  workspaceId,
  apiUrl,
  aolHost,
}: CapabilityRenderProofPageProps) {
  const isSelecting = aolHost?.mode === 'selecting';

  return (
    <main className="space-y-4 p-6" data-testid="render-proof-component">
      <header>
        <h1 className="text-xl font-semibold">Render Proof Capability Page</h1>
        <p className="text-sm text-gray-500">workspace={workspaceId || 'unknown'} api={apiUrl || 'unknown'}</p>
      </header>

      <button
        type="button"
        data-testid="render-proof-object-card"
        onClick={() => {
          if (!isSelecting) {
            return;
          }
          void aolHost?.onSelectObject({
            ownerPack: 'demo_render_proof',
            objectKind: 'reference',
            objectId: 'demo-ref-1',
            sourceSurface: 'demo_render_proof.capability_page',
            elementId: 'demo-render-proof-object',
            label: 'Render Proof Object',
            role: 'source',
          });
        }}
        className={`block w-full rounded-xl border px-4 py-4 text-left transition ${
          isSelecting
            ? 'cursor-crosshair border-cyan-300 bg-cyan-50 text-cyan-900'
            : 'cursor-default border-gray-200 bg-white text-gray-700'
        }`}
      >
        <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Render Proof Object
        </div>
        <div className="mt-2 text-sm">
          {isSelecting
            ? 'Selecting mode active. Click this object to emit the AOL candidate.'
            : 'Idle state. Use the global AOL anchor first.'}
        </div>
      </button>
    </main>
  );
}
