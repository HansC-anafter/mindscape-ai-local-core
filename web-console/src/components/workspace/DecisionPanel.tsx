'use client';

import React, { useState, useEffect } from 'react';
import { useT } from '@/lib/i18n';
import PendingTasksPanel from '@/app/workspaces/components/PendingTasksPanel';

// IntentCard type definition
export interface IntentCard {
  id: string;
  title: string;
  description?: string;
  status: 'pending_decision' | 'confirmed' | 'rejected';
  priority: 'high' | 'medium' | 'low';
  decisions?: Array<{
    id: string;
    question: string;
    options: string[];
    selectedOption?: string;
  }>;
  createdAt?: string;
}

interface DecisionPanelProps {
  workspaceId: string;
  apiUrl: string;
  onViewArtifact?: (artifact: any) => void;
  onSwitchToOutcomes?: () => void;
  workspace?: {
    playbook_auto_execution_config?: Record<string, {
      confidence_threshold?: number;
      auto_execute?: boolean;
    }>;
  };
}

export function DecisionPanel({
  workspaceId,
  apiUrl,
  onViewArtifact,
  onSwitchToOutcomes,
  workspace,
}: DecisionPanelProps) {
  const t = useT();
  const [intentCards, setIntentCards] = useState<IntentCard[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pendingTaskCount, setPendingTaskCount] = useState(0);

  const loadIntentCards = React.useCallback(async () => {
    try {
      setLoading(true);
      // Fetch all intents to show both pending decisions and history
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/intents`
      );
      if (response.ok) {
        const data = await response.json();
        const cards = (data.intents || []).map((intent: any) => ({
          id: intent.id,
          title: intent.title,
          description: intent.description,
          status: intent.status === 'CANDIDATE' ? 'pending_decision' as const
            : intent.status === 'CONFIRMED' ? 'confirmed' as const
            : 'rejected' as const,
          priority: intent.metadata?.priority || 'medium' as const,
          createdAt: intent.created_at,
        }));
        setIntentCards(cards);
      } else {
        setIntentCards([]);
      }
    } catch (err) {
      console.error('Failed to load intent cards:', err);
      setIntentCards([]);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, apiUrl]);

  useEffect(() => {
    // Load intent cards on mount and when workspaceId/apiUrl changes
    loadIntentCards();

    const handleWorkspaceUpdate = () => {
      loadIntentCards();
    };

    const handleTaskUpdate = () => {
      loadIntentCards();
    };

    const handleVisibilityChange = () => {
      if (!document.hidden) {
        loadIntentCards();
      }
    };

    window.addEventListener('workspace-chat-updated', handleWorkspaceUpdate);
    window.addEventListener('workspace-task-updated', handleTaskUpdate);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.removeEventListener('workspace-chat-updated', handleWorkspaceUpdate);
      window.removeEventListener('workspace-task-updated', handleTaskUpdate);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [workspaceId, apiUrl, loadIntentCards]);

  const pendingCards = intentCards.filter(c => c.status === 'pending_decision');
  const historyCards = intentCards.filter(c => c.status !== 'pending_decision');
  const highPriorityCount = pendingCards.filter(c => c.priority === 'high').length;

  const totalPending = pendingTaskCount + pendingCards.length;

  return (
    <div className="decision-panel flex-1 flex flex-col overflow-hidden">
      {/* Panel Header */}
      <div className={`section-header decision-section-header ${highPriorityCount > 0 ? 'has-high-priority' : ''} px-3 py-2 bg-gray-50 dark:bg-gray-800 border-b dark:border-gray-700`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold">待處理決策</span>
            {totalPending > 0 && (
              <span className="badge pending text-xs px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300">
                {totalPending}
              </span>
            )}
            {highPriorityCount > 0 && (
              <span
                className="badge high-priority text-xs px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300"
                title={`${highPriorityCount} 項高優先級`}
              >
                {highPriorityCount}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Decision Content */}
      <div className="flex-1 overflow-y-auto min-h-0 p-3 space-y-4">
        {/* Pending Tasks Section */}
        <div className="pending-tasks-section">
          <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
            人類需要確認 / 補資料的任務
          </div>
          <PendingTasksPanel
            workspaceId={workspaceId}
            apiUrl={apiUrl}
            onViewArtifact={onViewArtifact}
            onSwitchToOutcomes={onSwitchToOutcomes}
            workspace={workspace}
            onTaskCountChange={setPendingTaskCount}
          />
        </div>

        {/* Intent Cards Section */}
        <div className="intent-cards-section">
          <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
            Intent Card
          </div>
          {loading ? (
            <div className="text-xs text-gray-400 dark:text-gray-500 italic py-2">
              Loading...
            </div>
          ) : pendingCards.length === 0 ? (
            <div className="text-xs text-gray-400 dark:text-gray-500 italic py-2">
              目前沒有需要決策的項目
            </div>
          ) : (
            <div className="space-y-2">
              {pendingCards.map(card => (
                <IntentCardItem
                  key={card.id}
                  card={card}
                  workspaceId={workspaceId}
                  apiUrl={apiUrl}
                  onStatusChange={loadIntentCards}
                />
              ))}
            </div>
          )}
        </div>

        {/* Empty State */}
        {!loading && totalPending === 0 && (
          <div className="text-xs text-gray-400 dark:text-gray-500 italic py-4 text-center">
            目前沒有需要決策的項目
          </div>
        )}

        {/* History Section */}
        {historyCards.length > 0 && (
          <div className="history-intents border-t border-gray-200 dark:border-gray-700 pt-3">
            <button
              className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
              onClick={() => setShowHistory(!showHistory)}
            >
              <span className="chevron">{showHistory ? '▼' : '▶'}</span>
              <span>歷史決策 ({historyCards.length})</span>
            </button>

            {showHistory && (
              <div className="history-list mt-2 space-y-2">
                {historyCards.map(card => (
                  <IntentCardItem
                    key={card.id}
                    card={card}
                    collapsed
                    workspaceId={workspaceId}
                    apiUrl={apiUrl}
                    onStatusChange={loadIntentCards}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function IntentCardItem({
  card,
  collapsed,
  workspaceId,
  apiUrl,
  onStatusChange,
}: {
  card: IntentCard;
  collapsed?: boolean;
  workspaceId: string;
  apiUrl: string;
  onStatusChange?: () => void;
}) {
  const [isProcessing, setIsProcessing] = useState(false);

  const handleConfirm = async () => {
    if (isProcessing) return;
    setIsProcessing(true);
    try {
      const response = await fetch(`${apiUrl}/api/v1/intents/${card.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'CONFIRMED' }),
      });
      if (response.ok) {
        onStatusChange?.();
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
      } else {
        const error = await response.json().catch(() => ({}));
        console.error('Failed to confirm intent:', error);
        alert(`Failed to confirm intent: ${error.detail || 'Unknown error'}`);
      }
    } catch (err: any) {
      console.error('Failed to confirm intent:', err);
      alert(`Failed to confirm intent: ${err.message || 'Unknown error'}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleReject = async () => {
    if (isProcessing) return;
    setIsProcessing(true);
    try {
      const response = await fetch(`${apiUrl}/api/v1/intents/${card.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'REJECTED' }),
      });
      if (response.ok) {
        onStatusChange?.();
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
      } else {
        const error = await response.json().catch(() => ({}));
        console.error('Failed to reject intent:', error);
        alert(`Failed to reject intent: ${error.detail || 'Unknown error'}`);
      }
    } catch (err: any) {
      console.error('Failed to reject intent:', err);
      alert(`Failed to reject intent: ${err.message || 'Unknown error'}`);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className={`intent-card-item border rounded p-2 ${
      card.priority === 'high'
        ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
        : card.priority === 'medium'
        ? 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800'
        : 'bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700'
    } ${collapsed ? 'opacity-60' : ''}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-gray-900 dark:text-gray-100">
          {card.title}
        </span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${
          card.priority === 'high'
            ? 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300'
            : card.priority === 'medium'
            ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300'
            : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
        }`}>
          {card.priority === 'high' ? '高' : card.priority === 'medium' ? '中' : '低'}
        </span>
      </div>
      {!collapsed && card.description && (
        <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">
          {card.description}
        </div>
      )}
      {!collapsed && card.status === 'pending_decision' && (
        <div className="flex items-center gap-1.5 mt-2">
          <button
            onClick={handleConfirm}
            disabled={isProcessing}
            className={`flex-1 px-2 py-1 text-xs font-medium rounded transition-all ${
              isProcessing
                ? 'bg-gray-400 dark:bg-gray-600 text-white cursor-not-allowed opacity-75'
                : 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 hover:bg-gray-50 dark:hover:bg-gray-700 border border-gray-300 dark:border-gray-600'
            }`}
          >
            {isProcessing ? (
              <>
                <div className="w-3 h-3 border-2 border-gray-600 dark:border-gray-300 border-t-transparent rounded-full animate-spin mx-auto"></div>
              </>
            ) : (
              '確認'
            )}
          </button>
          <button
            onClick={handleReject}
            disabled={isProcessing}
            className={`px-2 py-1 text-xs font-medium text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 border border-red-300 dark:border-red-700 rounded hover:bg-red-50 dark:hover:bg-red-900/30 transition-all flex items-center justify-center gap-1 flex-shrink-0 ${
              isProcessing ? 'opacity-50 cursor-not-allowed' : ''
            }`}
          >
            <span>✕</span>
            <span>拒絕</span>
          </button>
        </div>
      )}
    </div>
  );
}

