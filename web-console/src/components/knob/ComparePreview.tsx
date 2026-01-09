'use client';

import React, { useState, useEffect } from 'react';
import { ControlProfile } from '@/hooks/useControlProfile';

interface ComparePreviewProps {
  inputText: string;
  leftProfile: ControlProfile;
  rightProfile: ControlProfile;
  onApplyRight: () => void;
  onCancel: () => void;
  apiUrl: string;
  workspaceId: string;
}

export function ComparePreview({
  inputText,
  leftProfile,
  rightProfile,
  onApplyRight,
  onCancel,
  apiUrl,
  workspaceId,
}: ComparePreviewProps) {
  const [leftOutput, setLeftOutput] = useState<string>('');
  const [rightOutput, setRightOutput] = useState<string>('');
  const [diffSummary, setDiffSummary] = useState<string>('');
  const [disclaimer, setDisclaimer] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (inputText && leftProfile && rightProfile) {
      generateComparison();
    }
  }, [inputText, leftProfile, rightProfile]);

  const generateComparison = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/control-profile/compare-preview`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            input_text: inputText,
            left_profile: leftProfile,
            right_profile: rightProfile,
          }),
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to generate comparison: ${response.status}`);
      }

      const data = await response.json();
      setLeftOutput(data.left_output || '[預覽生成中...]');
      setRightOutput(data.right_output || '[預覽生成中...]');
      setDiffSummary(data.diff_summary || '');
      setDisclaimer(data.preview_disclaimer || '');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate comparison');
      console.error('Failed to generate comparison:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="compare-preview p-4 rounded-lg"
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        maxWidth: '900px',
        margin: '0 auto',
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold" style={{ color: 'var(--text)' }}>
          設定對照預覽
        </h3>
        <button
          onClick={onCancel}
          className="text-sm"
          style={{ color: 'var(--muted)' }}
        >
          ✕ 關閉
        </button>
      </div>

      {/* v2.3: 規則化差異摘要（不靠 LLM 自說自話） */}
      {diffSummary && (
        <div
          className="mb-4 px-3 py-2 rounded-lg text-sm"
          style={{ background: 'var(--accent-2)', color: 'var(--accent)' }}
        >
          {diffSummary}
        </div>
      )}

      {/* Error message */}
      {error && (
        <div
          className="mb-4 px-3 py-2 rounded-lg text-sm"
          style={{ background: 'var(--error-bg)', color: 'var(--error)' }}
        >
          ⚠️ {error}
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="mb-4 text-center text-sm" style={{ color: 'var(--muted)' }}>
          生成預覽中...
        </div>
      )}

      {/* Comparison panels */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Left panel - Current settings */}
        <div
          className="rounded-lg p-4"
          style={{
            border: '1px solid var(--border)',
            background: 'var(--surface-2)',
          }}
        >
          <div className="text-sm mb-2 font-medium" style={{ color: 'var(--muted)' }}>
            目前設定
          </div>
          <div className="text-xs mb-3" style={{ color: 'var(--muted)' }}>
            介入: {leftProfile.knob_values.intervention_level || 50}% |
            收斂: {leftProfile.knob_values.convergence || 50}% |
            密度: {leftProfile.knob_values.verbosity || 50}%
          </div>
          <div
            className="prose prose-sm max-w-none whitespace-pre-wrap"
            style={{ color: 'var(--text)' }}
          >
            {leftOutput || '[等待生成...]'}
          </div>
        </div>

        {/* Right panel - New settings */}
        <div
          className="rounded-lg p-4"
          style={{
            border: '2px solid var(--accent)',
            background: 'var(--accent-2)',
          }}
        >
          <div className="text-sm mb-2 font-medium" style={{ color: 'var(--accent)' }}>
            新設定
          </div>
          <div className="text-xs mb-3" style={{ color: 'var(--accent)' }}>
            介入: {rightProfile.knob_values.intervention_level || 50}% |
            收斂: {rightProfile.knob_values.convergence || 50}% |
            密度: {rightProfile.knob_values.verbosity || 50}%
          </div>
          <div
            className="prose prose-sm max-w-none whitespace-pre-wrap mb-4"
            style={{ color: 'var(--text)' }}
          >
            {rightOutput || '[等待生成...]'}
          </div>
          <button
            onClick={onApplyRight}
            disabled={loading}
            className="w-full px-4 py-2 rounded text-sm font-medium transition-opacity disabled:opacity-50"
            style={{
              background: 'var(--accent)',
              color: 'var(--surface)',
            }}
          >
            套用這個設定
          </button>
        </div>
      </div>

      {/* v2.3: 可信度保護條款 */}
      {disclaimer && (
        <div
          className="mt-4 text-xs text-center"
          style={{ color: 'var(--muted)' }}
        >
          ⚠️ {disclaimer}
        </div>
      )}
    </div>
  );
}

