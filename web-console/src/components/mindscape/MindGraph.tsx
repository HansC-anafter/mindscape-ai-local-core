'use client';

import React from 'react';
import dynamic from 'next/dynamic';
import { useFullGraph } from '@/lib/graph-api';
import { useT } from '@/lib/i18n';

function MindGraphLoading() {
  const t = useT();
  return (
    <div className="w-full h-[600px] bg-gray-100 rounded-lg animate-pulse flex items-center justify-center">
      <span className="text-gray-400">{t('loading' as any)}</span>
    </div>
  );
}

const SigmaGraphClient = dynamic(
  () => import('./SigmaGraphClient').then(mod => ({ default: mod.SigmaGraphClient })),
  {
    ssr: false,
    loading: () => <MindGraphLoading />,
  }
);

interface MindGraphProps {
  activeLens?: 'all' | 'direction' | 'action';
  onNodeSelect?: (nodeId: string, attributes: any) => void;
  workspaceId?: string;
  onInitialize?: () => void;
}

function GraphSkeleton() {
  const t = useT();
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
  const t = useT();
  return (
    <div className="w-full h-[600px] bg-gray-50 rounded-lg flex flex-col items-center justify-center border-2 border-dashed border-gray-300">
      <div className="text-center max-w-md px-4">
        <div className="text-sm font-semibold text-gray-500 mb-4">Graph</div>
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
  const t = useT();
  const { nodes, edges, isLoading, isError } = useFullGraph(workspaceId);

  if (isLoading) {
    return <GraphSkeleton />;
  }

  if (isError) {
    return (
      <div className="w-full h-[600px] bg-red-50 rounded-lg flex flex-col items-center justify-center">
        <span className="text-red-600 text-lg mb-2">{t('errorLoadingGraph' as any)}</span>
      </div>
    );
  }

  if (nodes.length === 0) {
    return <EmptyGraphState onInitialize={onInitialize} />;
  }

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
