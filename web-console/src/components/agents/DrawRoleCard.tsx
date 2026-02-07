'use client';

import React, { useState } from 'react';
import { t } from '../../lib/i18n';
import { WORK_SCENES, WorkScene } from '../../lib/work-scenes';
import { getApiBaseUrl } from '../../lib/api-url';

const API_URL = getApiBaseUrl();

interface DrawRoleCardProps {
  task: string;
  backendAvailable: boolean;
  onSceneSelected: (scene: WorkScene) => void;
}

export default function DrawRoleCard({ task, backendAvailable, onSceneSelected }: DrawRoleCardProps) {
  const [drawingCard, setDrawingCard] = useState(false);
  const [suggestedScene, setSuggestedScene] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const handleDrawRoleCard = async () => {
    if (!task.trim()) {
      setError(t('pleaseEnterTaskDescription' as any));
      return;
    }

    setDrawingCard(true);
    setError(null);
    setSuggestedScene(null);

    try {
      const profileId = 'default-user';
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(`${apiUrl}/api/v1/agent/suggest-scene?profile_id=${profileId}&task=${encodeURIComponent(task)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        throw new Error('Failed to suggest scene');
      }

      const data = await response.json();
      setSuggestedScene(data);

      const scene = WORK_SCENES.find(s => s.id === data.suggested_scene_id);
      if (scene) {
        onSceneSelected(scene);
      }
    } catch (err: any) {
      setError(err.message || t('drawRoleCardFailed' as any));
    } finally {
      setDrawingCard(false);
    }
  };

  return (
    <button
      type="button"
      onClick={handleDrawRoleCard}
      disabled={!task.trim() || drawingCard || !backendAvailable}
      className="p-5 border-2 rounded-lg text-left transition-all hover:border-gray-400 dark:hover:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800/20 border-gray-200 dark:border-gray-600 bg-gradient-to-br from-gray-50 to-blue-50 dark:from-gray-800/20 dark:to-blue-900/20 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:border-gray-200 dark:disabled:hover:border-gray-600 disabled:hover:bg-gradient-to-br disabled:hover:from-gray-50 disabled:hover:to-blue-50 dark:disabled:hover:from-gray-800/20 dark:disabled:hover:to-blue-900/20"
    >
      <div className="flex items-start mb-3">
        <span className="text-3xl mr-3">🎯</span>
        <div className="flex-1">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100 text-lg mb-1">{t('drawRoleCard' as any)}</h3>
          <p className="text-sm text-gray-600 dark:text-gray-400">{t('drawRoleCardDescription' as any)}</p>
        </div>
      </div>
      {suggestedScene && (
        <div className="mt-3 bg-white dark:bg-gray-800 rounded-lg p-3 border border-gray-200 dark:border-gray-600">
          <div className="flex items-center mb-2">
            <span className="text-xl mr-2">{suggestedScene.suggested_scene?.icon || '🎯'}</span>
            <div className="flex-1">
              <h4 className="font-semibold text-gray-900 dark:text-gray-100 text-sm">{t('suggestedScene' as any)}: {suggestedScene.suggested_scene?.name}</h4>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {t('confidence' as any)}: {Math.round(suggestedScene.confidence * 100)}%
              </p>
            </div>
          </div>
        </div>
      )}
      {error && (
        <div className="mt-2 text-xs text-red-600 dark:text-red-400">{error}</div>
      )}
      {drawingCard && (
        <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">{t('drawRoleCardLoading' as any)}</div>
      )}
    </button>
  );
}



