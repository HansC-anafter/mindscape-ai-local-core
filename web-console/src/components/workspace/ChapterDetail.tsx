'use client';

import React, { useState, useEffect } from 'react';
import { EmptyState } from '../ui/EmptyState';
import './ChapterDetail.css';

interface ExecutionRecord {
  executionId: string;
  runNumber: number;
  playbookCode: string;
  playbookName: string;
  status: 'running' | 'paused' | 'completed' | 'failed';
  progress: number;
  startedAt: string;
  artifacts?: Array<{
    id: string;
    name: string;
    type: string;
    url?: string;
  }>;
}

interface ChapterDetailProps {
  chapterId: string;
  storyThreadId: string;
  apiUrl: string;
}

export function ChapterDetail({
  chapterId,
  storyThreadId,
  apiUrl,
}: ChapterDetailProps) {
  const [executions, setExecutions] = useState<ExecutionRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadExecutions();
  }, [chapterId, storyThreadId, apiUrl]);

  const loadExecutions = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        `${apiUrl}/api/v1/story-threads/${storyThreadId}/chapters/${chapterId}/executions`
      );
      if (response.ok) {
        const data = await response.json();
        setExecutions(data.executions || []);
      } else {
        setExecutions([]);
      }
    } catch (err) {
      setExecutions([]);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="chapter-detail-content">
        <EmptyState customMessage="Loading execution records..." />
      </div>
    );
  }

  return (
    <div className="chapter-detail-content">
      <div className="detail-header">Chapter Execution Records</div>
      {executions.length === 0 ? (
        <EmptyState customMessage="No execution records for this chapter" />
      ) : (
        <div className="playbook-runs">
          {executions.map(execution => (
            <ExecutionRecordItem key={execution.executionId} execution={execution} />
          ))}
        </div>
      )}
    </div>
  );
}

interface ExecutionRecordItemProps {
  execution: ExecutionRecord;
}

function ExecutionRecordItem({ execution }: ExecutionRecordItemProps) {
  const statusLabels = {
    running: 'Running',
    paused: 'Paused',
    completed: 'Completed',
    failed: 'Failed',
  };

  return (
    <div className={`execution-record-item ${execution.status}`}>
      <div className="execution-header">
        <span className="playbook-name">{execution.playbookName}</span>
        <span className={`status-badge ${execution.status}`}>
          {statusLabels[execution.status]}
        </span>
      </div>
      <div className="execution-info">
        <span className="run-number">Run #{execution.runNumber}</span>
        <span className="progress">{execution.progress}%</span>
        <span className="started-at">
          {new Date(execution.startedAt).toLocaleDateString()}
        </span>
      </div>
      {execution.artifacts && execution.artifacts.length > 0 && (
        <div className="artifacts-count">
          {execution.artifacts.length} artifact(s)
        </div>
      )}
    </div>
  );
}

