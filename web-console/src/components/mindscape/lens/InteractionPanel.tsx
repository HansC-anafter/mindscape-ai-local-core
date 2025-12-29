'use client';

import React, { useState } from 'react';
import { PreviewBlock } from './PreviewBlock';
import { ChangeSetBlock } from './ChangeSetBlock';
import { MindscapeChatPanel } from './MindscapeChatPanel';
import { LensDriftView } from './LensDriftView';
import type { EffectiveLens } from '@/lib/lens-api';

type TabMode = 'mirror' | 'experiment' | 'writeback' | 'drift';

interface InteractionPanelProps {
  effectiveLens: EffectiveLens | null;
  tabMode: TabMode;
  onTabChange: (tab: TabMode) => void;
  sessionId: string;
  profileId: string;
  workspaceId?: string;
  onRefresh: () => void;
  selectedNodeIds?: string[];
}

export function InteractionPanel({
  effectiveLens,
  tabMode: initialTabMode = 'mirror',
  onTabChange: externalOnTabChange,
  sessionId,
  profileId,
  workspaceId,
  onRefresh,
  selectedNodeIds = [],
}: InteractionPanelProps) {
  const [tabMode, setTabMode] = useState<TabMode>(initialTabMode);
  const [showChat, setShowChat] = useState(tabMode === 'mirror' || tabMode === 'experiment');

  const handleTabChange = (tab: TabMode) => {
    setTabMode(tab);
    externalOnTabChange(tab);
  };

  if (!effectiveLens) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 h-full flex items-center justify-center">
        <p className="text-gray-500">No effective lens available</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 h-full flex flex-col">
      {/* Tab Header */}
      <div className="p-4 border-b border-gray-200">
        <div className="flex space-x-2">
          <button
            onClick={() => handleTabChange('mirror')}
            className={`px-3 py-1 rounded text-sm font-medium ${
              tabMode === 'mirror'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            Mirror
          </button>
          <button
            onClick={() => handleTabChange('experiment')}
            className={`px-3 py-1 rounded text-sm font-medium ${
              tabMode === 'experiment'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            Experiment
          </button>
          <button
            onClick={() => handleTabChange('writeback')}
            className={`px-3 py-1 rounded text-sm font-medium ${
              tabMode === 'writeback'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            Writeback
          </button>
          <button
            onClick={() => handleTabChange('drift')}
            className={`px-3 py-1 rounded text-sm font-medium ${
              tabMode === 'drift'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            Drift
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {tabMode === 'mirror' || tabMode === 'experiment' ? (
          <div className="flex-1 flex flex-col h-full">
            {/* Tab 切换：Chat 或 Preview */}
            <div className="p-2 border-b border-gray-200 flex space-x-2">
              <button
                onClick={() => setShowChat(!showChat)}
                className={`px-2 py-1 text-xs rounded ${
                  showChat
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {showChat ? '切換到預覽' : '切換到對話'}
              </button>
            </div>

            {showChat ? (
              <MindscapeChatPanel
                effectiveLens={effectiveLens}
                mode={tabMode}
                sessionId={sessionId}
                profileId={profileId}
                workspaceId={workspaceId}
                selectedNodeIds={selectedNodeIds || []}
              />
            ) : (
              <div className="flex-1 overflow-y-auto p-4">
                <PreviewBlock
                  effectiveLens={effectiveLens}
                  profileId={profileId}
                  workspaceId={workspaceId}
                  sessionId={sessionId}
                />
              </div>
            )}
          </div>
        ) : tabMode === 'writeback' ? (
          <div className="flex-1 overflow-y-auto p-4">
            <ChangeSetBlock
              sessionId={sessionId}
              profileId={profileId}
              workspaceId={workspaceId}
              onRefresh={onRefresh}
            />
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto">
            <LensDriftView profileId={profileId} />
          </div>
        )}
      </div>
    </div>
  );
}

