'use client';

/**
 * NodeDetailPanel - Floating panel showing selected node details
 */

import React from 'react';
import { FloatingPanel } from './FloatingPanel';
import { PlaybookExpansionPanel } from './PlaybookExpansionPanel';
import type { MindscapeNode } from '@/lib/mindscape-graph-api';

interface NodeDetailPanelProps {
  node: MindscapeNode | null;
  onClose: () => void;
  onContinueConversation?: () => void;
  onStartNewConversation?: () => void;
}

export function NodeDetailPanel({
  node,
  onClose,
  onContinueConversation,
  onStartNewConversation,
}: NodeDetailPanelProps) {
  const [expandedPlaybook, setExpandedPlaybook] = React.useState<string | null>(null);

  if (!node) return null;

  return (
    <FloatingPanel
      title={`節點詳情`}
      isOpen={true}
      onClose={onClose}
      defaultPosition={{ x: window.innerWidth - 420, y: 120 }}
      defaultSize={{ width: 380, height: 480 }}
    >
      {/* Node Header */}
      <div className="mb-4">
        <div className="flex items-center gap-2 mb-2">
          <span className={`px-2 py-1 rounded text-xs font-medium ${node.type === 'intent' ? 'bg-purple-100 text-purple-700' :
              node.type === 'execution' ? 'bg-green-100 text-green-700' :
                'bg-gray-100 text-gray-700'
            }`}>
            {node.type}
          </span>
          <span className={`px-2 py-1 rounded text-xs ${node.status === 'accepted' ? 'bg-emerald-100 text-emerald-700' :
              node.status === 'rejected' ? 'bg-red-100 text-red-700' :
                'bg-yellow-100 text-yellow-700'
            }`}>
            {node.status}
          </span>
        </div>
        <h4 className="font-medium text-gray-900 text-sm">{node.label}</h4>
        <code className="text-xs text-gray-500 font-mono">{node.id}</code>
      </div>

      {/* Action Buttons */}
      <div className="flex gap-2 mb-4">
        <button
          onClick={onContinueConversation}
          disabled={!node.metadata?.thread_id}
          className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium flex items-center justify-center gap-1 transition-colors ${node.metadata?.thread_id
              ? 'bg-indigo-500 text-white hover:bg-indigo-600'
              : 'bg-gray-100 text-gray-400 cursor-not-allowed'
            }`}
          title={!node.metadata?.thread_id ? '此節點沒有關聯對話' : undefined}
        >
          💬 繼續對話
        </button>
        <button
          onClick={onStartNewConversation}
          className="flex-1 px-3 py-2 rounded-lg text-sm font-medium bg-green-500 text-white hover:bg-green-600 flex items-center justify-center gap-1 transition-colors"
        >
          🆕 開新對話
        </button>
      </div>

      {/* Linked Playbooks */}
      {node.metadata?.linked_playbook_codes?.length > 0 && (
        <div className="mb-4 p-3 bg-violet-50 rounded-lg border border-violet-200">
          <span className="font-medium text-violet-800 text-sm">🎯 關聯 Playbooks</span>
          <div className="mt-2 flex flex-wrap gap-2">
            {node.metadata.linked_playbook_codes.map((code: string) => (
              <button
                key={code}
                onClick={() => setExpandedPlaybook(expandedPlaybook === code ? null : code)}
                className={`px-3 py-1 rounded-full text-xs font-medium border transition-all ${expandedPlaybook === code
                    ? 'bg-violet-600 text-white border-violet-600'
                    : 'bg-violet-100 text-violet-800 border-violet-300 hover:bg-violet-200'
                  }`}
              >
                {code} {expandedPlaybook === code ? '▼' : '▶'}
              </button>
            ))}
          </div>
          {expandedPlaybook && (
            <div className="mt-3">
              <PlaybookExpansionPanel
                playbookCode={expandedPlaybook}
                onClose={() => setExpandedPlaybook(null)}
              />
            </div>
          )}
        </div>
      )}

      {/* Execution Details */}
      {node.type === 'execution' && node.metadata && (
        <div className="mb-4 p-3 bg-emerald-50 rounded-lg border border-emerald-200">
          <span className="font-medium text-emerald-800 text-sm">📊 執行摘要</span>
          <div className="mt-2 space-y-1 text-sm">
            {node.metadata.playbook_code && (
              <div className="flex justify-between">
                <span className="text-gray-600">Playbook:</span>
                <span className="font-medium text-emerald-700">{node.metadata.playbook_code}</span>
              </div>
            )}
            {node.metadata.result_summary && (
              <div className="flex justify-between">
                <span className="text-gray-600">結果:</span>
                <span className="text-gray-800 truncate max-w-[180px]">{node.metadata.result_summary}</span>
              </div>
            )}
            {node.metadata.artifact_count > 0 && (
              <div className="flex justify-between">
                <span className="text-gray-600">產物:</span>
                <span className="font-medium text-blue-600">{node.metadata.artifact_count} items</span>
              </div>
            )}
            {node.metadata.error && (
              <div className="p-2 bg-red-50 border border-red-200 rounded text-red-700 text-xs mt-2">
                ⚠️ {node.metadata.error}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Raw Metadata (collapsed) */}
      <details className="text-sm">
        <summary className="text-gray-500 cursor-pointer hover:text-gray-700">
          原始 Metadata
        </summary>
        <pre className="mt-2 bg-gray-50 p-2 rounded text-xs overflow-auto max-h-32 font-mono">
          {JSON.stringify(node.metadata, null, 2)}
        </pre>
      </details>
    </FloatingPanel>
  );
}
