'use client';

import React, { useState, useEffect } from 'react';
import { useT } from '@/lib/i18n';

interface ExecutionSession {
  execution_id: string;
  workspace_id: string;
  status: string;
  playbook_code?: string;
  trigger_source?: string;
  current_step_index: number;
  total_steps: number;
  paused_at?: string;
  origin_intent_label?: string;
  [key: string]: any;
}

interface ExecutionStep {
  id: string;
  execution_id: string;
  step_index: number;
  step_name: string;
  status: string;
  confirmation_prompt?: string;
  requires_confirmation: boolean;
  confirmation_status?: string;
  [key: string]: any;
}

interface PendingTimelineItemProps {
  execution: ExecutionSession;
  currentStep: ExecutionStep;
  apiUrl: string;
  workspaceId: string;
  onAction?: (action: 'confirmed' | 'rejected') => void;
  onClick?: () => void;
}

export default function PendingTimelineItem({
  execution,
  currentStep,
  apiUrl,
  workspaceId,
  onAction,
  onClick
}: PendingTimelineItemProps) {
  const t = useT();
  const [isVisible, setIsVisible] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);

  useEffect(() => {
    // Fade in animation on mount
    const timer = setTimeout(() => {
      setIsVisible(true);
    }, 100);
    return () => clearTimeout(timer);
  }, []);

  const handleConfirm = async () => {
    if (isProcessing) return;
    setIsProcessing(true);

    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${execution.execution_id}/steps/${currentStep.id}/confirm`,
        { method: 'POST' }
      );

      if (response.ok) {
        // Fade out animation before calling onAction
        setIsVisible(false);
        setTimeout(() => {
          if (onAction) {
            onAction('confirmed');
          }
        }, 300); // Wait for fade out animation
      } else {
        const error = await response.json();
        console.error('Failed to confirm step:', error);
        alert(`Failed to confirm: ${error.detail || t('unknownError' as any)}`);
        setIsProcessing(false);
      }
    } catch (err: any) {
      console.error('Failed to confirm step:', err);
      alert(`Failed to confirm: ${err.message || t('unknownError' as any)}`);
      setIsProcessing(false);
    }
  };

  const handleReject = async () => {
    if (isProcessing) return;
    setIsProcessing(true);

    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${execution.execution_id}/steps/${currentStep.id}/reject`,
        { method: 'POST' }
      );

      if (response.ok) {
        // Fade out animation before calling onAction
        setIsVisible(false);
        setTimeout(() => {
          if (onAction) {
            onAction('rejected');
          }
        }, 300); // Wait for fade out animation
      } else {
        const error = await response.json();
        console.error('Failed to reject step:', error);
        alert(`Failed to reject: ${error.detail || t('unknownError' as any)}`);
        setIsProcessing(false);
      }
    } catch (err: any) {
      console.error('Failed to reject step:', err);
      alert(`Failed to reject: ${err.message || t('unknownError' as any)}`);
      setIsProcessing(false);
    }
  };

  return (
    <>
      <style dangerouslySetInnerHTML={{
        __html: `
          @keyframes fadeInPulse {
            0%, 100% {
              opacity: 1;
              transform: translateY(0);
            }
            50% {
              opacity: 0.85;
              transform: translateY(-1px);
            }
          }
        `
      }} />
      <div
        className={`bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded p-2 shadow-sm transition-all duration-300 ${
          isVisible
            ? 'opacity-100 translate-y-0'
            : 'opacity-0 translate-y-2'
        }`}
        style={{
          animation: isVisible ? 'fadeInPulse 2s ease-in-out infinite' : undefined
        }}
      >

      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <svg
            className="h-4 w-4 text-amber-600 dark:text-amber-500 animate-pulse"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
              clipRule="evenodd"
            />
          </svg>
          <span className="text-xs font-medium text-amber-900 dark:text-amber-300">
            {execution.playbook_code || 'Playbook Execution'}
          </span>
          {execution.trigger_source && (
            <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-700">
              {execution.trigger_source}
            </span>
          )}
        </div>
        <span className="text-xs text-amber-600 dark:text-amber-400 font-medium">
          Step {execution.current_step_index + 1}/{execution.total_steps}
        </span>
      </div>

      {/* Confirmation Prompt */}
      <div className="mb-3">
        {currentStep.confirmation_prompt ? (
          <p className="text-xs text-amber-800 dark:text-amber-300 leading-relaxed bg-amber-100 dark:bg-amber-900/30 rounded p-2 border border-amber-300 dark:border-amber-700">
            {currentStep.confirmation_prompt}
          </p>
        ) : (
          <p className="text-xs text-amber-800 dark:text-amber-300 leading-relaxed">
            This step requires your confirmation to continue.
          </p>
        )}
        {currentStep.step_name && (
          <p className="text-xs text-amber-700 dark:text-amber-400 mt-1 font-medium">
            Step: {currentStep.step_name}
          </p>
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex gap-2">
        <button
          onClick={handleConfirm}
          disabled={isProcessing}
          className={`flex-1 px-3 py-1.5 text-xs font-medium text-white rounded transition-all ${
            isProcessing
              ? 'bg-amber-400 dark:bg-amber-600 cursor-not-allowed'
              : 'bg-amber-600 dark:bg-amber-700 hover:bg-amber-700 dark:hover:bg-amber-600 active:bg-amber-800 dark:active:bg-amber-800'
          }`}
        >
          {isProcessing ? 'Processing...' : 'Confirm'}
        </button>
        <button
          onClick={handleReject}
          disabled={isProcessing}
          className={`flex-1 px-3 py-1.5 text-xs font-medium text-amber-700 dark:text-amber-300 rounded border transition-all ${
            isProcessing
              ? 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 cursor-not-allowed opacity-50'
              : 'bg-amber-100 dark:bg-amber-900/30 border-amber-300 dark:border-amber-700 hover:bg-amber-200 dark:hover:bg-amber-900/40 active:bg-amber-300 dark:active:bg-amber-900/50'
          }`}
        >
          {isProcessing ? 'Processing...' : 'Reject'}
        </button>
      </div>
      </div>
    </>
  );
}

