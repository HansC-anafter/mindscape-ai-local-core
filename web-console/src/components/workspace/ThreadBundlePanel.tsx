'use client';

import React, { useState } from 'react';
import { useThreadBundle, ThreadBundle as ThreadBundleType } from '@/hooks/useThreadBundle';
import { getApiBaseUrl } from '@/lib/api-url';
import { formatLocalDateTime } from '@/lib/time';

function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(' ');
}

type BundleSection = 'overview' | 'deliverables' | 'references' | 'runs' | 'sources';

interface ThreadBundlePanelProps {
  threadId: string | null;
  workspaceId: string;
  isOpen: boolean;
  onClose: () => void;
  apiUrl?: string;
  embedded?: boolean;
}

const sectionLabels: Record<BundleSection, string> = {
  overview: 'Overview',
  deliverables: 'Deliverables',
  references: 'References',
  runs: 'Runs',
  sources: 'Sources',
};

export function ThreadBundlePanel({
  threadId,
  workspaceId,
  isOpen,
  onClose,
  apiUrl = getApiBaseUrl(),
  embedded = false,
}: ThreadBundlePanelProps) {
  const { bundle, loading, error } = useThreadBundle(workspaceId, threadId, apiUrl);
  const [activeSection, setActiveSection] = useState<BundleSection>('overview');

  if (!isOpen) return null;

  const sectionNavigation = (
    <div className="flex shrink-0 overflow-x-auto border-b px-2 dark:border-gray-700">
      {(['overview', 'deliverables', 'references', 'runs', 'sources'] as const).map(section => (
        <button
          key={section}
          onClick={() => setActiveSection(section)}
          className={cn(
            "whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors",
            activeSection === section
              ? "border-blue-500 text-blue-600 dark:text-blue-400"
              : "border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
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
          {activeSection === 'references' && <ReferencesSection items={bundle.references} workspaceId={workspaceId} threadId={threadId} apiUrl={apiUrl} />}
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

function OverviewSection({ bundle }: { bundle: ThreadBundleType }) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">Status</h3>
        <div className="text-base font-medium">
          {bundle.overview.status === 'in_progress' && 'In Progress'}
          {bundle.overview.status === 'delivered' && 'Delivered'}
          {bundle.overview.status === 'pending_data' && 'Waiting for Data'}
        </div>
      </div>

      {bundle.overview.summary && (
        <div>
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">Summary</h3>
          <p className="text-sm text-gray-700 dark:text-gray-300">{bundle.overview.summary}</p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 pt-4 border-t dark:border-gray-700">
        <div>
          <div className="text-sm text-gray-500 dark:text-gray-400">Deliverables</div>
          <div className="text-lg font-semibold">{bundle.deliverables.length}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500 dark:text-gray-400">References</div>
          <div className="text-lg font-semibold">{bundle.references.length}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500 dark:text-gray-400">Runs</div>
          <div className="text-lg font-semibold">{bundle.runs.length}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500 dark:text-gray-400">Sources</div>
          <div className="text-lg font-semibold">{bundle.sources.length}</div>
        </div>
      </div>
    </div>
  );
}

function DeliverablesSection({ items }: { items: ThreadBundleType['deliverables'] }) {
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <h3 className="text-lg font-medium mb-2">No Deliverables</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Outputs from completed playbooks will appear here.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div
          key={item.id}
          className="p-3 border dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <h4 className="font-medium text-gray-900 dark:text-gray-100">{item.title}</h4>
              <div className="mt-1 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                <span>{item.artifact_type}</span>
                <span>-</span>
                <span>{item.source}</span>
                <span>-</span>
                <span>{item.status}</span>
              </div>
            </div>
          </div>
          <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
            Updated {formatLocalDateTime(item.updated_at)}
          </div>
        </div>
      ))}
    </div>
  );
}

function ReferencesSection({
  items,
  workspaceId,
  threadId,
  apiUrl
}: {
  items: ThreadBundleType['references'];
  workspaceId: string;
  threadId: string | null;
  apiUrl: string;
}) {
  const [showPicker, setShowPicker] = useState(false);

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <h3 className="text-lg font-medium mb-2">No References</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          Pin external resources such as Obsidian notes, Notion pages, and WordPress articles to this thread.
        </p>
        {threadId && (
          <button
            onClick={() => setShowPicker(true)}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            Add Reference
          </button>
        )}
        {showPicker && threadId && (
          <ReferencePicker
            workspaceId={workspaceId}
            threadId={threadId}
            apiUrl={apiUrl}
            onClose={() => setShowPicker(false)}
            onReferenceAdded={() => {
              setShowPicker(false);
              window.location.reload();
            }}
          />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {threadId && (
        <div className="mb-4">
          <button
            onClick={() => setShowPicker(true)}
            className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            Add Reference
          </button>
        </div>
      )}

      {items.map((item) => (
        <div
          key={item.id}
          className="p-3 border dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <h4 className="font-medium text-gray-900 dark:text-gray-100 mb-1">
                <a
                  href={item.uri}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:underline"
                >
                  {item.title}
                </a>
              </h4>
              <div className="mt-1 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                <span>{item.source_type}</span>
                {item.pinned_by && (
                  <>
                    <span>-</span>
                    <span>{item.pinned_by === 'user' ? 'Pinned by User' : 'Pinned by AI'}</span>
                  </>
                )}
              </div>
              {item.snippet && (
                <p className="mt-2 text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
                  {item.snippet}
                </p>
              )}
              {item.reason && (
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-500 italic">
                  Reason: {item.reason}
                </p>
              )}
            </div>
          </div>
        </div>
      ))}

      {showPicker && threadId && (
        <ReferencePicker
          workspaceId={workspaceId}
          threadId={threadId}
          apiUrl={apiUrl}
          onClose={() => setShowPicker(false)}
          onReferenceAdded={() => {
            setShowPicker(false);
            window.location.reload();
          }}
        />
      )}
    </div>
  );
}

function RunsSection({ items }: { items: ThreadBundleType['runs'] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <h3 className="text-lg font-medium mb-2">No Runs</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Playbook run records will appear here.
        </p>
      </div>
    );
  }

  const statusConfig: Record<string, { color: string; label: string }> = {
    completed: { color: 'text-green-600 dark:text-green-400', label: 'Completed' },
    running: { color: 'text-blue-600 dark:text-blue-400', label: 'Running' },
    failed: { color: 'text-red-600 dark:text-red-400', label: 'Failed' },
    cancelled: { color: 'text-gray-500 dark:text-gray-400', label: 'Cancelled' },
  };

  return (
    <div className="space-y-3">
      {items.map((item) => {
        const sc = statusConfig[item.status] || statusConfig.running;
        const isExpanded = expandedId === item.id;
        const hasDetails = !!(item as any).result_summary;

        return (
          <div
            key={item.id}
            className={cn(
              'p-3 border dark:border-gray-700 rounded-lg transition-colors',
              hasDetails ? 'cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800' : '',
            )}
            onClick={() => hasDetails && setExpandedId(isExpanded ? null : item.id)}
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h4 className="font-medium text-gray-900 dark:text-gray-100">{item.playbook_name}</h4>
                </div>
                <div className="mt-1 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                  <span className={sc.color}>{sc.label}</span>
                  <span>-</span>
                  <span>{item.steps_completed}/{item.steps_total} steps</span>
                  {item.duration_ms && (
                    <>
                      <span>-</span>
                      <span>{(item.duration_ms / 1000).toFixed(1)}s</span>
                    </>
                  )}
                </div>
              </div>
              {hasDetails && (
                <span className="text-xs text-gray-400 mt-1">{isExpanded ? 'Collapse' : 'Expand'}</span>
              )}
            </div>
            <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
              Started {formatLocalDateTime(item.started_at)}
            </div>
            {isExpanded && (item as any).result_summary && (
              <div className="mt-3 pt-3 border-t dark:border-gray-700">
                <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                  {(item as any).result_summary}
                </p>
                {(item as any).storage_ref && (
                  <div className="mt-2 text-xs text-blue-500 dark:text-blue-400">
                    {(item as any).storage_ref}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function SourcesSection({ items }: { items: ThreadBundleType['sources'] }) {
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <h3 className="text-lg font-medium mb-2">No Sources</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Sources and connectors will appear here.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div
          key={item.id}
          className="p-3 border dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <h4 className="font-medium text-gray-900 dark:text-gray-100">{item.display_name}</h4>
              <div className="mt-1 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                <span>{item.type}</span>
                <span>-</span>
                <span>{item.sync_status}</span>
                {item.permissions.length > 0 && (
                  <>
                    <span>-</span>
                    <span>{item.permissions.join(', ')}</span>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyBundleState() {
  return (
    <div className="flex flex-col items-center justify-center h-64 text-center">
      <h3 className="text-lg font-medium mb-2">Start Building the Bundle</h3>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
        Keep this conversation&apos;s outputs and references in one place.
      </p>
    </div>
  );
}

function ReferencePicker({
  workspaceId,
  threadId,
  apiUrl,
  onClose,
  onReferenceAdded,
}: {
  workspaceId: string;
  threadId: string;
  apiUrl: string;
  onClose: () => void;
  onReferenceAdded: () => void;
}) {
  const [sourceType, setSourceType] = useState<string | null>(null);
  const [uri, setUri] = useState('');
  const [title, setTitle] = useState('');
  const [snippet, setSnippet] = useState('');
  const [reason, setReason] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!sourceType || !uri || !title) {
      alert('Fill in all required fields.');
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/threads/${threadId}/references`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            source_type: sourceType,
            uri,
            title,
            snippet: snippet || undefined,
            reason: reason || undefined,
          }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to add reference');
      }

      onReferenceAdded();
    } catch (err: any) {
      console.error('Failed to add reference:', err);
      alert(err.message || 'Failed to add reference');
    } finally {
      setIsSubmitting(false);
    }
  };

  const sourceTypes: Array<{ value: string; label: string }> = [
    { value: 'url', label: 'URL' },
    { value: 'local_file', label: 'Local File' },
    { value: 'obsidian', label: 'Obsidian Note' },
    { value: 'notion', label: 'Notion Page' },
    { value: 'wordpress', label: 'WordPress Article' },
    { value: 'google_drive', label: 'Google Drive' },
  ];

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center">
      <div className="bg-white dark:bg-gray-900 rounded-lg p-6 max-w-md w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">Add Reference</h3>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {!sourceType ? (
          <div className="space-y-3">
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">Select a source type</p>
            <div className="grid grid-cols-2 gap-3">
              {sourceTypes.map((type) => (
                <button
                  key={type.value}
                  onClick={() => setSourceType(type.value)}
                  className="p-3 border dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-left"
                >
                  <div className="text-sm font-medium">{type.label}</div>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Source Type</label>
              <div className="flex items-center gap-2">
                <span className="text-sm">
                  {sourceTypes.find(t => t.value === sourceType)?.label}
                </span>
                <button
                  onClick={() => setSourceType(null)}
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                >
                  Change
                </button>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">
                URI <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={uri}
                onChange={(e) => setUri(e.target.value)}
                placeholder={sourceType === 'url' ? 'https://...' : sourceType === 'local_file' ? 'file://...' : 'obsidian://...'}
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">
                Title <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Reference title"
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Summary</label>
              <textarea
                value={snippet}
                onChange={(e) => setSnippet(e.target.value)}
                placeholder="Short summary (optional)"
                rows={3}
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Reason</label>
              <input
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Why this resource is relevant (optional)"
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
              />
            </div>

            <div className="flex gap-2 pt-4">
              <button
                onClick={onClose}
                className="flex-1 px-4 py-2 text-sm bg-gray-100 dark:bg-gray-800 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={isSubmitting || !uri || !title}
                className="flex-1 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSubmitting ? 'Adding...' : 'Add'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
