'use client';

import React, { useState } from 'react';
import { generatePreview } from '@/lib/lens-api';
import type { EffectiveLens, PreviewResult } from '@/lib/lens-api';

interface PreviewBlockProps {
  effectiveLens: EffectiveLens;
  profileId: string;
  workspaceId?: string;
  sessionId: string;
}

export function PreviewBlock({
  effectiveLens,
  profileId,
  workspaceId,
  sessionId,
}: PreviewBlockProps) {
  const [inputText, setInputText] = useState('');
  const [previewType, setPreviewType] = useState<'rewrite' | 'section_pack'>('rewrite');
  const [previewResult, setPreviewResult] = useState<PreviewResult | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);

  const handleGenerate = async () => {
    if (!inputText.trim()) return;

    try {
      setIsGenerating(true);
      const result = await generatePreview({
        profile_id: profileId,
        input_text: inputText,
        preview_type: previewType,
        workspace_id: workspaceId,
        session_id: sessionId,
      });
      setPreviewResult(result);
    } catch (error) {
      console.error('Failed to generate preview:', error);
      alert('Failed to generate preview');
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">輸入文字</label>
        <textarea
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          rows={4}
          placeholder="輸入要預覽的文字..."
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">預覽類型</label>
        <select
          value={previewType}
          onChange={(e) => setPreviewType(e.target.value as 'rewrite' | 'section_pack')}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="rewrite">Rewrite</option>
          <option value="section_pack">Section Pack</option>
        </select>
      </div>

      <button
        onClick={handleGenerate}
        disabled={isGenerating || !inputText.trim()}
        className="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
      >
        {isGenerating ? '生成中...' : '生成預覽'}
      </button>

      {previewResult && (
        <div className="space-y-4 mt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-gray-50 rounded-lg p-4 border border-gray-200 shadow-sm">
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-semibold text-gray-700">Base Output</div>
                <span className="text-xs px-2 py-1 bg-gray-200 text-gray-600 rounded">原始</span>
              </div>
              <div className="text-sm text-gray-900 whitespace-pre-wrap max-h-64 overflow-y-auto">
                {previewResult.base_output || '(無輸出)'}
              </div>
            </div>
            <div className="bg-blue-50 rounded-lg p-4 border border-blue-200 shadow-sm">
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-semibold text-blue-700">Lens Output</div>
                <span className="text-xs px-2 py-1 bg-blue-200 text-blue-700 rounded">Lens</span>
              </div>
              <div className="text-sm text-gray-900 whitespace-pre-wrap max-h-64 overflow-y-auto">
                {previewResult.lens_output || '(無輸出)'}
              </div>
            </div>
          </div>

          <div className="bg-yellow-50 rounded-lg p-4 border border-yellow-200 shadow-sm">
            <div className="flex items-center mb-2">
              <span className="text-lg mr-2">📊</span>
              <div className="text-sm font-semibold text-yellow-700">差異摘要</div>
            </div>
            <div className="text-sm text-yellow-800">{previewResult.diff_summary || '無明顯差異'}</div>
          </div>

          {previewResult.triggered_nodes.length > 0 && (
            <div className="bg-green-50 rounded-lg p-4 border border-green-200 shadow-sm">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center">
                  <span className="text-lg mr-2">✨</span>
                  <div className="text-sm font-semibold text-green-700">觸發的節點</div>
                </div>
                <span className="text-xs px-2 py-1 bg-green-200 text-green-700 rounded font-medium">
                  {previewResult.triggered_nodes.length}
                </span>
              </div>
              <div className="space-y-2">
                {previewResult.triggered_nodes.map((node) => (
                  <div
                    key={node.node_id}
                    className="flex items-center justify-between bg-white rounded p-2 border border-green-100"
                  >
                    <span className="text-sm text-gray-900 font-medium">{node.node_label}</span>
                    <span
                      className={`text-xs px-2 py-1 rounded ${
                        node.state === 'emphasize'
                          ? 'bg-yellow-100 text-yellow-700'
                          : node.state === 'keep'
                          ? 'bg-blue-100 text-blue-700'
                          : 'bg-gray-100 text-gray-600'
                      }`}
                    >
                      {node.state.toUpperCase()}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

