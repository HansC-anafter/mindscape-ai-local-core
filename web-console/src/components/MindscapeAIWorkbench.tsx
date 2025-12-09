'use client';

import React, { useState, useEffect, useRef } from 'react';
import { t } from '@/lib/i18n';
import ContextCard from './ContextCard';
import SuggestedNextStepsCard from './SuggestedNextStepsCard';

interface WorkbenchData {
  current_context: {
    workspace_focus: string;
    recent_file?: {
      name: string;
      uploaded_at: string;
    } | null;
    detected_intents: Array<{
      id: string;
      title: string;
      source: string;
      status: string;
    }>;
  };
  suggested_next_steps: Array<{
    type?: string;
    title: string;
    description: string;
    action: string;
    params?: Record<string, any>;
    cta_label: string;
    priority: 'high' | 'medium' | 'low';
    side_effect_level?: 'readonly' | 'soft_write' | 'hard_write';
  }>;
  suggestion_history?: Array<{
    round_id: string;
    timestamp: string;
    suggestions: Array<{
      type?: string;
      title: string;
      description: string;
      action: string;
      params?: Record<string, any>;
      cta_label: string;
      priority: 'high' | 'medium' | 'low';
      side_effect_level?: 'readonly' | 'soft_write' | 'hard_write';
    }>;
  }>;
  system_status: {
    llm_configured: boolean;
    llm_provider?: string;
    vector_db_connected: boolean;
    tools: Record<string, {
      connected: boolean;
      status: string;
      connection_count?: number;
    }>;
    critical_issues_count: number;
    has_issues: boolean;
  };
}

interface MindscapeAIWorkbenchProps {
  workspaceId: string;
  apiUrl?: string;
  activeTab?: 'timeline' | 'workbench' | 'settings';
  onTabChange?: (tab: string) => void;
  refreshTrigger?: number; // Add refresh trigger prop
}

export default function MindscapeAIWorkbench({
  workspaceId,
  apiUrl = '',
  activeTab = 'workbench',
  onTabChange,
  refreshTrigger = 0
}: MindscapeAIWorkbenchProps) {
  const [workbenchData, setWorkbenchData] = useState<WorkbenchData | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Event visibility states for fade-in animation
  const [showContext, setShowContext] = useState(false);
  const [showRecentFile, setShowRecentFile] = useState(false);
  const [showDetectedIntents, setShowDetectedIntents] = useState(false);
  const [showSuggestedSteps, setShowSuggestedSteps] = useState(false);

  // Track last loaded workspaceId and refreshTrigger to prevent duplicate loads
  const lastWorkspaceIdRef = useRef<string | null>(null);
  const lastRefreshTriggerRef = useRef(0);

  useEffect(() => {
    // Only load if workspaceId changed or refreshTrigger increased
    const workspaceIdChanged = lastWorkspaceIdRef.current !== workspaceId;
    const refreshTriggered = refreshTrigger > lastRefreshTriggerRef.current;

    if (workspaceIdChanged || refreshTriggered) {
      loadWorkbenchData();
      lastWorkspaceIdRef.current = workspaceId;
      lastRefreshTriggerRef.current = refreshTrigger;
    }
  }, [workspaceId, refreshTrigger]);

  useEffect(() => {
    // Debounce workbench refresh to avoid excessive API calls
    let debounceTimer: NodeJS.Timeout | null = null;
    let isRefreshing = false;

    const handleWorkbenchRefresh = () => {
      // Debounce: only refresh after 1.5 seconds of no events
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
      debounceTimer = setTimeout(() => {
        if (!isRefreshing) {
          isRefreshing = true;
          loadWorkbenchData().finally(() => {
            isRefreshing = false;
          });
        }
      }, 1500);
    };

    window.addEventListener('workbench-refresh', handleWorkbenchRefresh);
    return () => {
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
      window.removeEventListener('workbench-refresh', handleWorkbenchRefresh);
    };
  }, [workspaceId, apiUrl]);

  useEffect(() => {
    // Reset all visibility states when data changes
    setShowContext(false);
    setShowRecentFile(false);
    setShowDetectedIntents(false);
    setShowSuggestedSteps(false);

    if (workbenchData) {
      // Sequence: Show events one by one with fade-in animation
      // 1. Context (workspace_focus) - immediate
      setTimeout(() => setShowContext(true), 100);

      // 2. Recent file - after 300ms
      if (workbenchData.current_context.recent_file) {
        setTimeout(() => setShowRecentFile(true), 400);
      }

      // 3. Detected intents - after 600ms
      if (workbenchData.current_context.detected_intents && workbenchData.current_context.detected_intents.length > 0) {
        setTimeout(() => setShowDetectedIntents(true), 700);
      }

      // 4. Suggested next steps - after 900ms
      if (workbenchData.suggested_next_steps && workbenchData.suggested_next_steps.length > 0) {
        setTimeout(() => setShowSuggestedSteps(true), 1000);
      }
    }
  }, [workbenchData]);

  const loadWorkbenchData = async () => {
    try {
      setError(null);
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/workbench`);
      if (response.ok) {
        const data = await response.json();
        setWorkbenchData(data);
      } else {
        setError('Failed to load workbench data');
      }
    } catch (err) {
      console.error('[MindscapeAIWorkbench] Failed to load workbench data:', err);
      setError('Failed to load workbench data');
    }
  };

  if (error) {
    return (
      <div className="p-2">
        <div className="text-xs text-red-600">{error}</div>
        <button
          onClick={loadWorkbenchData}
          className="mt-1.5 text-xs text-blue-600 hover:text-blue-800 underline"
        >
          {t('refresh')}
        </button>
      </div>
    );
  }

  // Don't render anything if no data yet (no loading state, just wait)
  if (!workbenchData) {
    return null; // No loading message, just wait for data
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto space-y-2">

        {/* (2) Suggested Next Steps Card - Middle - Fade in */}
        {/*
          This shows SYSTEM SUGGESTIONS from workbench API:
          - Generated by SuggestionGenerator based on context
          - These are NOT actual tasks yet, just recommendations
          - Clicking CTA may create a task or execute directly

          Difference from "AI Team 協作中" below:
          - "建議下一步": Suggestions (not tasks yet)
          - "AI Team 協作中": Actual tasks (PENDING/RUNNING status)
        */}
        {workbenchData.suggested_next_steps && workbenchData.suggested_next_steps.length > 0 && (
          <div
            className={`transition-opacity duration-500 ease-in ${
              showSuggestedSteps ? 'opacity-100' : 'opacity-0'
            }`}
            style={{ minHeight: showSuggestedSteps ? 'auto' : '0px' }}
          >
            <SuggestedNextStepsCard
              nextSteps={workbenchData.suggested_next_steps}
              workspaceId={workspaceId}
              apiUrl={apiUrl}
              suggestionHistory={workbenchData.suggestion_history}
            />
          </div>
        )}
      </div>
    </div>
  );
}
