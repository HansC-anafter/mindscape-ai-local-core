'use client';

import React, { useState } from 'react';
import { ComparePreview } from './ComparePreview';
import { ControlProfile } from '@/hooks/useControlProfile';

const PRESETS = [
  { id: 'observer', label: '整理模式', icon: '👁️' },
  { id: 'advisor', label: '提案模式', icon: '💡' },
  { id: 'executor', label: '可直接交付', icon: '🚀' },
];

interface PresetSelectorProps {
  currentPreset: string | null;
  isDirty?: boolean;
  onChange: (presetId: string) => void;
  onReset?: () => void;
  // Compare Preview props
  currentProfile?: ControlProfile;
  inputText?: string;
  apiUrl?: string;
  workspaceId?: string;
  showComparePreview?: boolean;
}

export function PresetSelector({
  currentPreset,
  isDirty = false,
  onChange,
  onReset,
  currentProfile,
  inputText = '',
  apiUrl,
  workspaceId,
  showComparePreview = false,
}: PresetSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [previewPresetId, setPreviewPresetId] = useState<string | null>(null);
  const [previewProfile, setPreviewProfile] = useState<ControlProfile | null>(null);

  const current = PRESETS.find(p => p.id === currentPreset) || PRESETS[0];

  const handlePresetClick = async (presetId: string) => {
    if (showComparePreview && currentProfile && apiUrl && workspaceId && inputText) {
      // Load preset profile for comparison
      try {
        const presetsResponse = await fetch(`${apiUrl}/api/v1/workspaces/control-profile/presets`);
        if (presetsResponse.ok) {
          const presetsData = await presetsResponse.json();
          const preset = presetsData.presets.find((p: any) => p.id === presetId);
          if (preset) {
            const previewProfile: ControlProfile = {
              ...currentProfile,
              preset_id: presetId,
              knob_values: preset.knob_values,
            };
            setPreviewProfile(previewProfile);
            setPreviewPresetId(presetId);
            setShowPreview(true);
            setIsOpen(false);
            return;
          }
        }
      } catch (err) {
        console.error('Failed to load preset for preview:', err);
      }
    }
    // No preview, apply directly
    onChange(presetId);
    setIsOpen(false);
  };

  const handleApplyPreview = () => {
    if (previewPresetId) {
      onChange(previewPresetId);
      setShowPreview(false);
      setPreviewProfile(null);
      setPreviewPresetId(null);
    }
  };

  const handleCancelPreview = () => {
    setShowPreview(false);
    setPreviewProfile(null);
    setPreviewPresetId(null);
  };

  return (
    <div className="relative flex items-center gap-2">
      {/* Preset 選擇器 */}
      <button
        className="knob-chip"
        onClick={() => setIsOpen(!isOpen)}
        style={{
          height: '28px',
          padding: '0 10px',
          borderRadius: '999px',
          border: '1px solid var(--border)',
          background: 'var(--surface-2)',
          color: 'var(--text)',
          fontSize: '12px',
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          cursor: 'pointer',
        }}
      >
        <span>{current.icon}</span>
        <span>{current.label}</span>
        {/* v2.4 風險 2 解法：偏離預設時顯示小點提示 */}
        {isDirty && (
          <span
            className="w-2 h-2 rounded-full"
            style={{ background: 'var(--accent)' }}
            title="已偏離預設"
          />
        )}
        <span style={{ color: 'var(--muted)' }}>▾</span>
      </button>

      {/* v2.4 風險 2 解法：一鍵 Reset to Preset */}
      {isDirty && onReset && (
        <button
          className="knob-chip"
          onClick={onReset}
          title="重置為預設值"
          style={{
            height: '28px',
            padding: '0 8px',
            borderRadius: '999px',
            border: '1px solid var(--border)',
            background: 'var(--surface-2)',
            color: 'var(--text)',
            fontSize: '12px',
            cursor: 'pointer',
          }}
        >
          ↺
        </button>
      )}

      {isOpen && (
        <div
          className="knob-popover"
          style={{
            position: 'absolute',
            bottom: '100%',
            left: 0,
            marginBottom: '8px',
            padding: '12px 16px',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: '14px',
            boxShadow: 'var(--shadow)',
            minWidth: '160px',
            zIndex: 100,
          }}
        >
          {PRESETS.map((preset) => (
            <button
              key={preset.id}
              className="w-full text-left px-3 py-2 rounded-lg flex items-center gap-2"
              style={{
                background: preset.id === currentPreset ? 'var(--accent-2)' : 'transparent',
              }}
              onClick={() => handlePresetClick(preset.id)}
            >
              <span>{preset.icon}</span>
              <span>{preset.label}</span>
              {preset.id === currentPreset && (
                <span className="ml-auto" style={{ color: 'var(--accent)' }}>✓</span>
              )}
            </button>
          ))}

          {/* 分隔線 + Reset 選項 */}
          {isDirty && onReset && (
            <>
              <div className="my-2" style={{ borderTop: '1px solid var(--border)' }} />
              <button
                className="w-full text-left px-3 py-2 rounded-lg flex items-center gap-2"
                onClick={() => {
                  onReset();
                  setIsOpen(false);
                }}
              >
                <span>↺</span>
                <span>重置為預設值</span>
              </button>
            </>
          )}
        </div>
      )}

      {/* Compare Preview Modal */}
      {showPreview && currentProfile && previewProfile && apiUrl && workspaceId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{
            background: 'rgba(0, 0, 0, 0.5)',
          }}
          onClick={handleCancelPreview}
        >
          <div
            className="max-w-4xl w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <ComparePreview
              inputText={inputText}
              leftProfile={currentProfile}
              rightProfile={previewProfile}
              onApplyRight={handleApplyPreview}
              onCancel={handleCancelPreview}
              apiUrl={apiUrl}
              workspaceId={workspaceId}
            />
          </div>
        </div>
      )}
    </div>
  );
}

