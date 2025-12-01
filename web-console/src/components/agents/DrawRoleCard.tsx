'use client';

import React, { useState } from 'react';
import { t } from '../../lib/i18n';
import { WORK_SCENES, WorkScene } from '../../lib/work-scenes';

interface DrawRoleCardProps {
  task: string;
  backendAvailable: boolean;
  onSceneSelected: (scene: WorkScene) => void;
}

export default function DrawRoleCard({ task, backendAvailable, onSceneSelected }: DrawRoleCardProps) {
  const [drawingCard, setDrawingCard] = useState(false);
  const [suggestedScene, setSuggestedScene] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  const handleDrawRoleCard = async () => {
    if (!task.trim()) {
      setError(t('pleaseEnterTaskDescription'));
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
      setError(err.message || t('drawRoleCardFailed'));
    } finally {
      setDrawingCard(false);
    }
  };

  return (
    <button
      type="button"
      onClick={handleDrawRoleCard}
      disabled={!task.trim() || drawingCard || !backendAvailable}
      className="p-5 border-2 rounded-lg text-left transition-all hover:border-purple-300 hover:bg-purple-50 border-purple-200 bg-gradient-to-br from-purple-50 to-blue-50 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:border-purple-200 disabled:hover:bg-gradient-to-br disabled:hover:from-purple-50 disabled:hover:to-blue-50"
    >
      <div className="flex items-start mb-3">
        <span className="text-3xl mr-3">🎯</span>
        <div className="flex-1">
          <h3 className="font-semibold text-gray-900 text-lg mb-1">{t('drawRoleCard')}</h3>
          <p className="text-sm text-gray-600">{t('drawRoleCardDescription')}</p>
        </div>
      </div>
      {suggestedScene && (
        <div className="mt-3 bg-white rounded-lg p-3 border border-purple-200">
          <div className="flex items-center mb-2">
            <span className="text-xl mr-2">{suggestedScene.suggested_scene?.icon || '🎯'}</span>
            <div className="flex-1">
              <h4 className="font-semibold text-gray-900 text-sm">{t('suggestedScene')}: {suggestedScene.suggested_scene?.name}</h4>
              <p className="text-xs text-gray-500">
                {t('confidence')}: {Math.round(suggestedScene.confidence * 100)}%
              </p>
            </div>
          </div>
        </div>
      )}
      {error && (
        <div className="mt-2 text-xs text-red-600">{error}</div>
      )}
      {drawingCard && (
        <div className="mt-2 text-xs text-gray-500">{t('drawRoleCardLoading')}</div>
      )}
    </button>
  );
}




