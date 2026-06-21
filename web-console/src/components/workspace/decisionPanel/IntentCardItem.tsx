'use client';

import { useState } from 'react';
import type { IntentCard } from './types';

interface IntentCardItemProps {
  card: IntentCard;
  collapsed?: boolean;
  workspaceId: string;
  apiUrl: string;
  onStatusChange?: () => void;
}

export function IntentCardItem({
  card,
  collapsed,
  workspaceId,
  apiUrl,
  onStatusChange,
}: IntentCardItemProps) {
  const [isProcessing, setIsProcessing] = useState(false);
  void workspaceId;

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
        : 'bg-surface dark:bg-gray-800 border-default dark:border-gray-700'
    } ${collapsed ? 'opacity-60' : ''}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-primary dark:text-gray-100">
          {card.title}
        </span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${
          card.priority === 'high'
            ? 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300'
            : card.priority === 'medium'
            ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300'
            : 'bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300'
        }`}>
          {card.priority === 'high' ? 'High' : card.priority === 'medium' ? 'Medium' : 'Low'}
        </span>
      </div>
      {!collapsed && card.description && (
        <div className="text-xs text-secondary dark:text-gray-400 mt-1">
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
                : 'bg-surface-accent dark:bg-gray-800 text-primary dark:text-gray-100 hover:bg-surface-secondary dark:hover:bg-gray-700 border border-default dark:border-gray-600'
            }`}
          >
            {isProcessing ? (
              <>
                <div className="w-3 h-3 border-2 border-secondary dark:border-gray-300 border-t-transparent rounded-full animate-spin mx-auto"></div>
              </>
            ) : (
              'Confirm'
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
            <span>Reject</span>
          </button>
        </div>
      )}
    </div>
  );
}
