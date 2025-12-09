'use client';

import React from 'react';
import { t } from '@/lib/i18n';
import './CurrentExecutionBar.css';

export interface CurrentExecution {
  executionId: string;
  playbookCode: string;
  playbookName: string;
  runNumber: number;
  progress: number;
  status: 'running' | 'paused' | 'queued' | 'completed' | 'failed';
}

interface CurrentExecutionBarProps {
  execution: CurrentExecution | null;
  onViewDetail: () => void;
  onPause: () => void;
  onCancel: () => void;
}

export function CurrentExecutionBar({
  execution,
  onViewDetail,
  onPause,
  onCancel
}: CurrentExecutionBarProps) {
  if (!execution) return null;

  return (
    <div className="current-execution-bar">
      <div className="execution-info">
        <span className="playbook-name">
          {t('executingPlaybook') || 'Executing'}: {execution.playbookName}
        </span>
        <span className="run-number">Run #{execution.runNumber}</span>
        <span className="progress">{execution.progress}%</span>
      </div>

      <div className="progress-bar">
        <div
          className="progress-fill"
          style={{ width: `${execution.progress}%` }}
        />
      </div>

      <div className="execution-actions">
        <button className="action-link" onClick={onViewDetail}>
          {t('viewDetails') || 'View Details'}
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

