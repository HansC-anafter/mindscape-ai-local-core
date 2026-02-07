'use client';

import React from 'react';
import dynamic from 'next/dynamic';
import { useFullGraph } from '@/lib/graph-api';
import { t } from '@/lib/i18n';

// Dynamically import the Sigma.js client component to avoid SSR issues
const SigmaGraphClient = dynamic(
  () => {
    console.log('[MindGraph] Dynamic import: Loading SigmaGraphClient');
    return import('./SigmaGraphClient').then(mod => {
      console.log('[MindGraph] Dynamic import: SigmaGraphClient loaded', mod);
      return { default: mod.SigmaGraphClient };
    }).catch(err => {
      console.error('[MindGraph] Dynamic import: Failed to load SigmaGraphClient', err);
      throw err;
    });
  },
  {
    ssr: false,
    loading: () => {
      console.log('[MindGraph] Dynamic import: Showing loading state');
      return (
        <div className="w-full h-[600px] bg-gray-100 rounded-lg animate-pulse flex items-center justify-center">
          <span className="text-gray-400">{t('loading' as any)}</span>
        </div>
      );
    },
  }
);

interface MindGraphProps {
  activeLens?: 'all' | 'direction' | 'action';
  onNodeSelect?: (nodeId: string, attributes: any) => void;
  workspaceId?: string;
  onInitialize?: () => void;
}

function GraphSkeleton() {
  return (
    <div className="w-full h-[600px] bg-gray-100 rounded-lg animate-pulse flex items-center justify-center">
      <span className="text-gray-400">{t('loading' as any)}</span>
    </div>
  );
}

interface EmptyGraphStateProps {
  onInitialize?: () => void;
}

function EmptyGraphState({ onInitialize }: EmptyGraphStateProps) {
  return (
    <div className="w-full h-[600px] bg-gray-50 rounded-lg flex flex-col items-center justify-center border-2 border-dashed border-gray-300">
      <div className="text-center max-w-md px-4">
        <div className="text-6xl mb-4">📊</div>
        <h3 className="text-lg font-semibold text-gray-900 mb-2">{t('graphEmptyTitle' as any)}</h3>
        <p className="text-sm text-gray-600 mb-4">{t('graphEmptyDescription' as any)}</p>
        {onInitialize && (
          <button
            onClick={onInitialize}
            className="mt-4 px-6 py-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors font-medium"
          >
            {t('graphInitializeButton' as any)}
          </button>
        )}
        <p className="mt-4 text-xs text-gray-500">{t('graphEmptyHint' as any)}</p>
      </div>
    </div>
  );
}

export function MindGraph({
  activeLens = 'all',
  onNodeSelect,
  workspaceId,
  onInitialize,
}: MindGraphProps) {
  const { nodes, edges, isLoading, isError } = useFullGraph(workspaceId);

  // Debug logging
  console.log('[MindGraph] Props:', { activeLens, workspaceId, onInitialize: !!onInitialize });
  console.log('[MindGraph] State:', { nodesCount: nodes.length, edgesCount: edges.length, isLoading, isError });
  console.log('[MindGraph] Nodes:', nodes);
  console.log('[MindGraph] Edges:', edges);

  if (isLoading) {
    console.log('[MindGraph] Rendering: GraphSkeleton (loading)');
    return <GraphSkeleton />;
  }

  if (isError) {
    console.log('[MindGraph] Rendering: Error state');
    return (
      <div className="w-full h-[600px] bg-red-50 rounded-lg flex flex-col items-center justify-center">
        <span className="text-red-600 text-lg mb-2">{t('errorLoadingGraph' as any)}</span>
      </div>
    );
  }

  if (nodes.length === 0) {
    console.log('[MindGraph] Rendering: EmptyGraphState (no nodes)');
    return <EmptyGraphState onInitialize={onInitialize} />;
  }

  console.log('[MindGraph] Rendering: SigmaGraphClient with', nodes.length, 'nodes');
  console.log('[MindGraph] SigmaGraphClient component:', SigmaGraphClient);

  // Pass nodes and edges directly to avoid re-fetching
  return (
    <React.Suspense fallback={<GraphSkeleton />}>
      <SigmaGraphClient
        activeLens={activeLens}
        onNodeSelect={onNodeSelect}
        workspaceId={workspaceId}
      />
    </React.Suspense>
  );
}

export default MindGraph;

