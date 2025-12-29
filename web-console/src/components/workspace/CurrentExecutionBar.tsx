'use client';

import React, { useState, useEffect } from 'react';
import { t } from '@/lib/i18n';
import './CurrentExecutionBar.css';
import { CostWarningBanner } from './governance/CostWarningBanner';
import { getApiBaseUrl } from '../../lib/api-url';

export interface CurrentExecution {
  executionId: string;
  playbookCode: string;
  playbookName: string;
  runNumber: number;
  progress: number;
  status: 'running' | 'paused' | 'queued' | 'completed' | 'failed';
  projectId?: string;  // Optional: associated project ID for highlighting
}

interface CurrentExecutionBarProps {
  execution: CurrentExecution | null;
  onViewDetail: () => void;
  onPause: () => void;
  onCancel: () => void;
  workspaceId?: string;
  apiUrl?: string;
}

export function CurrentExecutionBar({
  execution,
  onViewDetail,
  onPause,
  onCancel,
  workspaceId,
  apiUrl = getApiBaseUrl(),
}: CurrentExecutionBarProps) {
  const [costData, setCostData] = useState<{
    currentUsage: number;
    quota: number;
    estimatedCost?: number;
  } | null>(null);

  useEffect(() => {
    if (!workspaceId || !execution) return;

    const loadCostData = async () => {
      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/governance/cost/monitoring?period=day`
        );
        if (response.ok) {
          const data = await response.json();
          setCostData({
            currentUsage: data.current_usage || 0,
            quota: data.quota || 10,
            estimatedCost: data.estimated_cost,
          });
        }
      } catch (err) {
        // Cost monitoring is Cloud-only, ignore errors in Local-Core
        console.debug('Cost monitoring not available:', err);
      }
    };

    loadCostData();
    const interval = setInterval(loadCostData, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, [workspaceId, apiUrl, execution]);

  if (!execution) return null;

  const handleBarClick = (e: React.MouseEvent) => {
    // Prevent event bubbling to avoid triggering parent click handlers
    e.stopPropagation();

    // Behavior: Always highlight project card if projectId exists, never navigate
    if (execution.projectId) {
      window.dispatchEvent(new CustomEvent('highlight-project-card', {
        detail: {
          projectId: execution.projectId,
          executionId: execution.executionId
        }
      }));
    }
    // If no projectId, do nothing (consistent behavior: no navigation)
  };

  const hasProject = !!execution.projectId;
  const tooltipText = hasProject
    ? '點擊高亮項目'
    : '此執行未關聯項目';

  return (
    <div className="current-execution-bar">
      {costData && (
        <div className="mb-2">
          <CostWarningBanner
            currentUsage={costData.currentUsage}
            quota={costData.quota}
            estimatedCost={costData.estimatedCost}
            period="day"
          />
        </div>
      )}
      <div
        className={`execution-info ${hasProject ? 'clickable-area' : ''}`}
        onClick={handleBarClick}
        title={tooltipText}
      >
        <span className="playbook-name">
          {t('executingPlaybook') || 'Executing'}: {execution.playbookName}
        </span>
        <span className="run-number">Run #{execution.runNumber}</span>
        <span className="progress">{execution.progress}%</span>
        {costData?.estimatedCost && (
          <span className="text-xs text-gray-500 dark:text-gray-400 ml-2">
            Est. cost: ${costData.estimatedCost.toFixed(2)}
          </span>
        )}
      </div>

      <div className="progress-bar">
        <div
          className="progress-fill"
          style={{ width: `${execution.progress}%` }}
        />
      </div>

      <div className="execution-actions">
        <button
          className="action-link view-details-button"
          onClick={onViewDetail}
          title="查看執行詳情"
        >
          {t('viewDetails') || 'View Details'} →
        </button>
        {execution.status === 'running' && (
          <>
            <button className="action-link" onClick={onPause}>
              {t('pause') || 'Pause'}
            </button>
            <button className="action-link" onClick={onCancel}>
              {t('cancel') || 'Cancel'}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

