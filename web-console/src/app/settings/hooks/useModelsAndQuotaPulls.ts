'use client';

import { useCallback, useEffect, useState } from 'react';

import { PullState } from '../components/panels/ModelConfigCard';
import { ModelItem } from '../components/panels/modelsAndQuota/types';
import { showNotification } from './useSettingsNotification';
import { settingsApi } from '../utils/settingsApi';

export function useModelsAndQuotaPulls() {
  const [activePulls, setActivePulls] = useState<Record<string, PullState>>({});

  const startPolling = useCallback((modelId: string, taskId: string) => {
    const intervalId = setInterval(async () => {
      try {
        const response = await fetch(`/api/v1/system-settings/llm-models/pull/${taskId}/progress`);
        if (!response.ok) {
          clearInterval(intervalId);
          setActivePulls((previous) => {
            const next = { ...previous };
            delete next[modelId];
            return next;
          });
          return;
        }

        const progress = await response.json();
        setActivePulls((previous) => ({
          ...previous,
          [modelId]: {
            taskId: progress.task_id,
            progress: progress.progress_pct || 0,
            status: progress.status || '',
            message: progress.message || '',
            totalBytes: progress.total_bytes || 0,
            downloadedBytes: progress.downloaded_bytes || 0,
          },
        }));

        if (progress.status === 'completed') {
          clearInterval(intervalId);
          showNotification('success', progress.message || 'Download completed');
          setTimeout(() => {
            setActivePulls((previous) => {
              const next = { ...previous };
              delete next[modelId];
              return next;
            });
          }, 3000);
        } else if (progress.status === 'failed' || progress.status === 'cancelled') {
          clearInterval(intervalId);
          if (progress.status === 'failed') {
            showNotification('error', progress.message || 'Download failed');
          }
          setTimeout(() => {
            setActivePulls((previous) => {
              const next = { ...previous };
              delete next[modelId];
              return next;
            });
          }, 3000);
        }
      } catch {
        return;
      }
    }, 1000);
    return intervalId;
  }, []);

  const handlePullModel = useCallback(async (model: Pick<ModelItem, 'id' | 'model_name' | 'provider'>) => {
    const modelId = String(model.id);
    try {
      setActivePulls((previous) => ({
        ...previous,
        [modelId]: {
          taskId: '',
          progress: 0,
          status: 'starting',
          message: 'Starting download...',
          totalBytes: 0,
          downloadedBytes: 0,
        },
      }));

      const result = await settingsApi.post<{ success: boolean; task_id?: string; message: string }>(
        '/api/v1/system-settings/llm-models/pull',
        { model_name: model.model_name, provider: model.provider, model_id: modelId }
      );

      if (!result.success || !result.task_id) {
        showNotification('error', result.message || 'Failed to start download');
        setActivePulls((previous) => {
          const next = { ...previous };
          delete next[modelId];
          return next;
        });
        return;
      }

      setActivePulls((previous) => ({
        ...previous,
        [modelId]: {
          ...previous[modelId],
          taskId: result.task_id!,
        },
      }));

      startPolling(modelId, result.task_id);
    } catch (error) {
      showNotification(
        'error',
        `Download failed: ${error instanceof Error ? error.message : 'Unknown error'}`
      );
      setActivePulls((previous) => {
        const next = { ...previous };
        delete next[modelId];
        return next;
      });
    }
  }, [startPolling]);

  const handleCancelPull = useCallback(async (taskId: string) => {
    try {
      await settingsApi.post(`/api/v1/system-settings/llm-models/pull/${taskId}/cancel`, {});
      showNotification('success', 'Download cancelled');
    } catch {
      showNotification('error', 'Failed to cancel download');
    }
  }, []);

  useEffect(() => {
    const recoverPulls = async () => {
      try {
        const response = await fetch('/api/v1/system-settings/llm-models/pull/active');
        if (!response.ok) {
          return;
        }

        const tasks = await response.json();
        for (const task of tasks) {
          const modelId = task.model_id || task.model_name;
          if (!modelId || (task.status !== 'starting' && task.status !== 'downloading')) {
            continue;
          }

          setActivePulls((previous) => ({
            ...previous,
            [modelId]: {
              taskId: task.task_id,
              progress: task.progress_pct || 0,
              status: task.status,
              message: task.message || '',
              totalBytes: task.total_bytes || 0,
              downloadedBytes: task.downloaded_bytes || 0,
            },
          }));
          startPolling(modelId, task.task_id);
        }
      } catch {
        return;
      }
    };

    recoverPulls();
  }, [startPolling]);

  return {
    activePulls,
    handleCancelPull,
    handlePullModel,
  };
}
