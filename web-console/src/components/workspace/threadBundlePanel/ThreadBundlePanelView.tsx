import React from 'react';

import type { ThreadBundle } from '@/hooks/useThreadBundle';

import { DeliverablesSection } from './DeliverablesSection';
import { EmptyBundleState } from './EmptyBundleState';
import { OverviewSection } from './OverviewSection';
import { ReferencesSection } from './ReferencesSection';
import { RunsSection } from './RunsSection';
import { SourcesSection } from './SourcesSection';
import {
  bundleSections,
  cn,
  sectionLabels,
} from './sectionConfig';
import type { BundleSection } from './types';

interface ThreadBundlePanelViewProps {
  activeSection: BundleSection;
  apiUrl: string;
  bundle: ThreadBundle | null;
  embedded: boolean;
  error: string | null;
  loading: boolean;
  threadId: string | null;
  workspaceId: string;
  onClose: () => void;
  onReferenceAdded: () => void;
  onSectionChange: (section: BundleSection) => void;
}

export function ThreadBundlePanelView({
  activeSection,
  apiUrl,
  bundle,
  embedded,
  error,
  loading,
  threadId,
  workspaceId,
  onClose,
  onReferenceAdded,
  onSectionChange,
}: ThreadBundlePanelViewProps) {
  const sectionNavigation = (
    <div className="flex shrink-0 overflow-x-auto border-b px-2 dark:border-gray-700">
      {bundleSections.map((section) => (
        <button
          key={section}
          onClick={() => onSectionChange(section)}
          className={cn(
            'whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors',
            activeSection === section
              ? 'border-blue-500 text-blue-600 dark:text-blue-400'
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300',
          )}
        >
          {sectionLabels[section]}
        </button>
      ))}
    </div>
  );

  const content = (
    <>
      {loading && (
        <div className="flex h-64 items-center justify-center">
          <div className="text-gray-500 dark:text-gray-400">Loading...</div>
        </div>
      )}

      {error && (
        <div className="flex h-64 items-center justify-center">
          <div className="text-red-500 dark:text-red-400">Error: {error}</div>
        </div>
      )}

      {!loading && !error && bundle && (
        <>
          {activeSection === 'overview' && <OverviewSection bundle={bundle} />}
          {activeSection === 'deliverables' && <DeliverablesSection items={bundle.deliverables} />}
          {activeSection === 'references' && (
            <ReferencesSection
              apiUrl={apiUrl}
              items={bundle.references}
              threadId={threadId}
              workspaceId={workspaceId}
              onReferenceAdded={onReferenceAdded}
            />
          )}
          {activeSection === 'runs' && <RunsSection items={bundle.runs} />}
          {activeSection === 'sources' && <SourcesSection items={bundle.sources} />}
        </>
      )}

      {!loading && !error && !bundle && (
        <EmptyBundleState />
      )}
    </>
  );

  if (embedded) {
    return (
      <div className="flex h-full min-h-0 flex-col bg-white dark:bg-gray-900">
        {sectionNavigation}
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {content}
        </div>
      </div>
    );
  }

  return (
    <>
      <div
        className="fixed inset-0 bg-black/50 z-40"
        onClick={onClose}
      />

      <div className="fixed inset-y-0 right-0 w-[480px] bg-white dark:bg-gray-900
                      shadow-2xl border-l dark:border-gray-700 z-50
                      transform transition-transform duration-300">
        <div className="flex items-center justify-between px-4 py-3 border-b dark:border-gray-700">
          <h2 className="text-lg font-semibold">Thread Bundle</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
              title="Close"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {sectionNavigation}

        <div className="flex-1 overflow-y-auto p-4 h-[calc(100vh-120px)]">
          {content}
        </div>
      </div>
    </>
  );
}
