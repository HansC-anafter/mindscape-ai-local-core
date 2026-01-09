'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { KnobChip, ControlKnob } from './KnobChip';
import { PresetSelector } from './PresetSelector';

// v2.4 風險 3 解法：新手只露出 3 顆最像「調音」的旋鈕
const PRIMARY_KNOBS = ['intervention_level', 'convergence', 'verbosity'];
const SECONDARY_KNOBS = ['retrieval_radius'];

interface KnobDockProps {
  knobs: ControlKnob[];
  knobValues: Record<string, number>;
  presetValues: Record<string, number>; // 預設值，用於計算 isDirty
  presetId: string | null;
  onKnobChange: (knobId: string, value: number) => void;
  onPresetChange: (presetId: string) => void;
  onResetToPreset: () => void;
  onUnlockKnob?: (knobId: string) => void;
  recentlyChanged?: string[]; // 最近調過的旋鈕 ID
  // Compare Preview props (optional)
  currentProfile?: any;
  inputText?: string;
  apiUrl?: string;
  workspaceId?: string;
  showComparePreview?: boolean;
}

export function KnobDock({
  knobs,
  knobValues,
  presetValues,
  presetId,
  onKnobChange,
  onPresetChange,
  onResetToPreset,
  onUnlockKnob,
  recentlyChanged = [],
  currentProfile,
  inputText,
  apiUrl,
  workspaceId,
  showComparePreview = false,
}: KnobDockProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [showMoreControls, setShowMoreControls] = useState(false);

  // v2.4: 計算是否偏離預設
  const isDirty = useMemo(() => {
    return Object.entries(knobValues).some(([id, val]) =>
      presetValues[id] !== undefined && presetValues[id] !== val
    );
  }, [knobValues, presetValues]);

  // 核心旋鈕分組
  const primaryKnobs = knobs.filter(k => PRIMARY_KNOBS.includes(k.id) && !k.is_advanced);
  const secondaryKnobs = knobs.filter(k => SECONDARY_KNOBS.includes(k.id) && !k.is_advanced);

  // 從屬旋鈕（鎖定狀態）
  const slaveKnobs = knobs.filter(k => k.master_knob_id && k.is_locked_to_master);

  // 進階旋鈕（非從屬）
  const advancedKnobs = knobs.filter(k => k.is_advanced && !k.master_knob_id);

  // 已解鎖的從屬旋鈕
  const unlockedSlaveKnobs = knobs.filter(k => k.master_knob_id && !k.is_locked_to_master);

  // 響應式：窄畫面收斂
  useEffect(() => {
    const mediaQuery = window.matchMedia('(max-width: 768px)');
    setIsCollapsed(mediaQuery.matches);

    const handler = (e: MediaQueryListEvent) => setIsCollapsed(e.matches);
    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }, []);

  if (isCollapsed) {
    return (
      <CollapsedKnobDock
        knobs={knobs}
        knobValues={knobValues}
        onKnobChange={onKnobChange}
        onPresetChange={onPresetChange}
      />
    );
  }

  // 如果沒有旋鈕，顯示提示
  if (knobs.length === 0) {
    return (
      <div className="text-sm text-gray-500">
        無可用旋鈕
      </div>
    );
  }

  return (
    <div className="knob-dock flex items-center gap-2">
      {/* v2.4 風險 3 解法：第一次只露出 3 顆（介入 / 收斂 / 密度） */}
      {primaryKnobs.map((knob) => {
        const value = knobValues[knob.id] ?? knob.default_value;
        const isLocked = knob.master_knob_id && knob.is_locked_to_master;
        const isActive = recentlyChanged.includes(knob.id);

        return (
          <KnobChip
            key={knob.id}
            knob={knob}
            value={value}
            isActive={isActive}
            isLocked={isLocked}
            onChange={(v) => onKnobChange(knob.id, v)}
            onUnlock={() => onUnlockKnob?.(knob.id)}
          />
        );
      })}

      {/* v2.4: 「顯示更多控制」按鈕 */}
      {!showMoreControls ? (
        <button
          className="knob-chip"
          onClick={() => setShowMoreControls(true)}
          style={{
            height: '28px',
            padding: '0 10px',
            borderRadius: '999px',
            border: '1px solid var(--border)',
            background: 'var(--surface-2)',
            color: 'var(--muted)',
            fontSize: '12px',
            cursor: 'pointer',
          }}
        >
          <span>+{secondaryKnobs.length + slaveKnobs.length + advancedKnobs.length + unlockedSlaveKnobs.length}</span>
        </button>
      ) : (
        /* 展開後顯示其餘旋鈕 */
        <>
          {/* 次要核心旋鈕 */}
          {secondaryKnobs.map((knob) => {
            const value = knobValues[knob.id] ?? knob.default_value;
            const isActive = recentlyChanged.includes(knob.id);
            return (
              <KnobChip
                key={knob.id}
                knob={knob}
                value={value}
                isActive={isActive}
                onChange={(v) => onKnobChange(knob.id, v)}
              />
            );
          })}

          {/* 從屬旋鈕（鎖定狀態，可解鎖） */}
          {slaveKnobs.map((knob) => {
            const value = knobValues[knob.id] ?? knob.default_value;
            const isActive = recentlyChanged.includes(knob.id);
            return (
              <KnobChip
                key={knob.id}
                knob={knob}
                value={value}
                isActive={isActive}
                isLocked={true}
                onChange={(v) => onKnobChange(knob.id, v)}
                onUnlock={() => onUnlockKnob?.(knob.id)}
              />
            );
          })}

          {/* 已解鎖的從屬旋鈕 */}
          {unlockedSlaveKnobs.map((knob) => {
            const value = knobValues[knob.id] ?? knob.default_value;
            const isActive = recentlyChanged.includes(knob.id);
            return (
              <KnobChip
                key={knob.id}
                knob={knob}
                value={value}
                isActive={isActive}
                isLocked={false}
                onChange={(v) => onKnobChange(knob.id, v)}
              />
            );
          })}

          {/* 進階旋鈕 */}
          {advancedKnobs.map((knob) => {
            const value = knobValues[knob.id] ?? knob.default_value;
            const isActive = recentlyChanged.includes(knob.id);
            return (
              <KnobChip
                key={knob.id}
                knob={knob}
                value={value}
                isActive={isActive}
                onChange={(v) => onKnobChange(knob.id, v)}
              />
            );
          })}
        </>
      )}

      {/* Preset 選擇器（含 isDirty 提示和 Reset） */}
      <PresetSelector
        currentPreset={presetId}
        isDirty={isDirty}
        onChange={onPresetChange}
        onReset={onResetToPreset}
        currentProfile={currentProfile}
        inputText={inputText}
        apiUrl={apiUrl}
        workspaceId={workspaceId}
        showComparePreview={showComparePreview}
      />
    </div>
  );
}

function CollapsedKnobDock({
  knobs,
  knobValues,
  onKnobChange,
  onPresetChange
}: {
  knobs: ControlKnob[];
  knobValues: Record<string, number>;
  onKnobChange: (knobId: string, value: number) => void;
  onPresetChange: (presetId: string) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      {/* 收斂後的單一按鈕 */}
      <button
        className="knob-chip"
        onClick={() => setIsOpen(true)}
        style={{
          height: '28px',
          padding: '0 10px',
          borderRadius: '999px',
          border: '1px solid var(--border)',
          background: 'var(--surface-2)',
          color: 'var(--text)',
          fontSize: '12px',
          cursor: 'pointer',
        }}
      >
        <span>🎛</span>
        <span>控制({knobs.length})</span>
      </button>

      {/* Bottom Sheet */}
      {isOpen && (
        <div className="fixed inset-0 z-50">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setIsOpen(false)}
          />

          {/* Sheet */}
          <div
            className="absolute bottom-0 left-0 right-0 rounded-t-2xl p-6"
            style={{ background: 'var(--surface)' }}
          >
            <div className="w-12 h-1 bg-gray-300 rounded-full mx-auto mb-6" />

            <h3 className="text-lg font-medium mb-4">控制面板</h3>

            {/* 完整的旋鈕列表 */}
            <div className="space-y-6">
              {knobs.map((knob) => (
                <div key={knob.id}>
                  <div className="flex justify-between mb-2">
                    <span>{knob.label}</span>
                    <span style={{ color: 'var(--accent)' }}>
                      {knobValues[knob.id] ?? knob.default_value}
                    </span>
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={100}
                    value={knobValues[knob.id] ?? 50}
                    onChange={(e) => onKnobChange(knob.id, Number(e.target.value))}
                    className="w-full"
                  />
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

