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
}

const sectionLabels: Record<BundleSection, string> = {
  overview: '概覽',
  deliverables: '交付物',
  references: '引用',
  runs: '執行',
  sources: '來源',
};

export function ThreadBundlePanel({
  threadId,
  workspaceId,
  isOpen,
  onClose,
  apiUrl = getApiBaseUrl(),
}: ThreadBundlePanelProps) {
  const { bundle, loading, error } = useThreadBundle(workspaceId, threadId, apiUrl);
  const [activeSection, setActiveSection] = useState<BundleSection>('overview');

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed inset-y-0 right-0 w-[480px] bg-white dark:bg-gray-900
                      shadow-2xl border-l dark:border-gray-700 z-50
                      transform transition-transform duration-300">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b dark:border-gray-700">
          <h2 className="text-lg font-semibold">Thread Bundle</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
              title="關閉"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Section Navigation */}
        <div className="flex border-b dark:border-gray-700 px-2 overflow-x-auto">
          {(['overview', 'deliverables', 'references', 'runs', 'sources'] as const).map(section => (
            <button
              key={section}
              onClick={() => setActiveSection(section)}
              className={cn(
                "px-3 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap",
                activeSection === section
                  ? "border-blue-500 text-blue-600 dark:text-blue-400"
                  : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
              )}
            >
              {sectionLabels[section]}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 h-[calc(100vh-120px)]">
          {loading && (
            <div className="flex items-center justify-center h-64">
              <div className="text-gray-500 dark:text-gray-400">載入中...</div>
            </div>
          )}

          {error && (
            <div className="flex items-center justify-center h-64">
              <div className="text-red-500 dark:text-red-400">錯誤：{error}</div>
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
        </div>
      </div>
    </>
  );
}

function OverviewSection({ bundle }: { bundle: ThreadBundleType }) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">狀態</h3>
        <div className="text-base font-medium">
          {bundle.overview.status === 'in_progress' && '進行中'}
          {bundle.overview.status === 'delivered' && '已交付'}
          {bundle.overview.status === 'pending_data' && '等待資料'}
        </div>
      </div>

      {bundle.overview.summary && (
        <div>
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">摘要</h3>
          <p className="text-sm text-gray-700 dark:text-gray-300">{bundle.overview.summary}</p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 pt-4 border-t dark:border-gray-700">
        <div>
          <div className="text-sm text-gray-500 dark:text-gray-400">交付物</div>
          <div className="text-lg font-semibold">{bundle.deliverables.length}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500 dark:text-gray-400">引用</div>
          <div className="text-lg font-semibold">{bundle.references.length}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500 dark:text-gray-400">執行記錄</div>
          <div className="text-lg font-semibold">{bundle.runs.length}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500 dark:text-gray-400">來源</div>
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
        <div className="text-4xl mb-4">📄</div>
        <h3 className="text-lg font-medium mb-2">尚無交付物</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          執行 Playbook 後，產出的成果會顯示在這裡
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
                <span>•</span>
                <span>{item.source}</span>
                <span>•</span>
                <span>{item.status}</span>
              </div>
            </div>
          </div>
          <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
            更新於 {formatLocalDateTime(item.updated_at)}
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
        <div className="text-4xl mb-4">🔗</div>
        <h3 className="text-lg font-medium mb-2">尚無引用</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          將外部資源（Obsidian 筆記、Notion 頁面、WordPress 文章等）釘選到這個 Thread
        </p>
        {threadId && (
          <button
            onClick={() => setShowPicker(true)}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            添加引用
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
            + 添加引用
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
                    <span>•</span>
                    <span>{item.pinned_by === 'user' ? '用戶釘選' : 'AI 釘選'}</span>
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
                  引用原因：{item.reason}
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
        <div className="text-4xl mb-4">⚙️</div>
        <h3 className="text-lg font-medium mb-2">尚無執行記錄</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          執行 Playbook 後，執行記錄會顯示在這裡
        </p>
      </div>
    );
  }

  const statusConfig: Record<string, { icon: string; color: string; label: string }> = {
    completed: { icon: '✅', color: 'text-green-600 dark:text-green-400', label: '完成' },
    running: { icon: '⏳', color: 'text-blue-600 dark:text-blue-400', label: '執行中' },
    failed: { icon: '❌', color: 'text-red-600 dark:text-red-400', label: '失敗' },
    cancelled: { icon: '⛔', color: 'text-gray-500 dark:text-gray-400', label: '已取消' },
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
                  <span className="text-sm">{sc.icon}</span>
                  <h4 className="font-medium text-gray-900 dark:text-gray-100">{item.playbook_name}</h4>
                </div>
                <div className="mt-1 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                  <span className={sc.color}>{sc.label}</span>
                  <span>•</span>
                  <span>{item.steps_completed}/{item.steps_total} 步驟</span>
                  {item.duration_ms && (
                    <>
                      <span>•</span>
                      <span>{(item.duration_ms / 1000).toFixed(1)} 秒</span>
                    </>
                  )}
                </div>
              </div>
              {hasDetails && (
                <span className="text-xs text-gray-400 mt-1">{isExpanded ? '▲' : '▼'}</span>
              )}
            </div>
            <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
              開始於 {formatLocalDateTime(item.started_at)}
            </div>
            {isExpanded && (item as any).result_summary && (
              <div className="mt-3 pt-3 border-t dark:border-gray-700">
                <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                  {(item as any).result_summary}
                </p>
                {(item as any).storage_ref && (
                  <div className="mt-2 text-xs text-blue-500 dark:text-blue-400">
                    📁 {(item as any).storage_ref}
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
        <div className="text-4xl mb-4">🔌</div>
        <h3 className="text-lg font-medium mb-2">尚無來源</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          來源/Connector 會顯示在這裡
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
                <span>•</span>
                <span>{item.sync_status}</span>
                {item.permissions.length > 0 && (
                  <>
                    <span>•</span>
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
      <div className="text-4xl mb-4">📦</div>
      <h3 className="text-lg font-medium mb-2">開始建立你的成果包</h3>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
        將這次對話的產出和參考資料集中管理
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
      alert('請填寫所有必填欄位');
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
      alert(err.message || '添加引用失敗');
    } finally {
      setIsSubmitting(false);
    }
  };

  const sourceTypes: Array<{ value: string; label: string; icon: string }> = [
    { value: 'url', label: '網址 URL', icon: '🔗' },
    { value: 'local_file', label: '本地檔案', icon: '📁' },
    { value: 'obsidian', label: 'Obsidian 筆記', icon: '📓' },
    { value: 'notion', label: 'Notion 頁面', icon: '📝' },
    { value: 'wordpress', label: 'WordPress 文章', icon: '🌐' },
    { value: 'google_drive', label: 'Google Drive', icon: '📊' },
  ];

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center">
      <div className="bg-white dark:bg-gray-900 rounded-lg p-6 max-w-md w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">添加引用</h3>
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
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">選擇來源類型</p>
            <div className="grid grid-cols-2 gap-3">
              {sourceTypes.map((type) => (
                <button
                  key={type.value}
                  onClick={() => setSourceType(type.value)}
                  className="p-3 border dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-left"
                >
                  <div className="text-2xl mb-1">{type.icon}</div>
                  <div className="text-sm font-medium">{type.label}</div>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">來源類型</label>
              <div className="flex items-center gap-2">
                <span className="text-sm">
                  {sourceTypes.find(t => t.value === sourceType)?.icon}{' '}
                  {sourceTypes.find(t => t.value === sourceType)?.label}
                </span>
                <button
                  onClick={() => setSourceType(null)}
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                >
                  更改
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
                標題 <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="引用標題"
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">摘要</label>
              <textarea
                value={snippet}
                onChange={(e) => setSnippet(e.target.value)}
                placeholder="簡短摘要（可選）"
                rows={3}
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">引用原因</label>
              <input
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="為何引用此資源（可選）"
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
              />
            </div>

            <div className="flex gap-2 pt-4">
              <button
                onClick={onClose}
                className="flex-1 px-4 py-2 text-sm bg-gray-100 dark:bg-gray-800 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700"
              >
                取消
              </button>
              <button
                onClick={handleSubmit}
                disabled={isSubmitting || !uri || !title}
                className="flex-1 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSubmitting ? '添加中...' : '添加'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
