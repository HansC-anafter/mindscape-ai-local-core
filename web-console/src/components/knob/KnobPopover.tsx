'use client';

import React, { useEffect, useRef, useMemo } from 'react';
import { ControlKnob } from './KnobChip';

interface KnobPopoverProps {
  knob: ControlKnob;
  value: number;
  onChange: (value: number) => void;
  onClose: () => void;
  anchorElement: HTMLElement | null;
}

export function KnobPopover({ knob, value, onChange, onClose, anchorElement }: KnobPopoverProps) {
  const popoverRef = useRef<HTMLDivElement>(null);

  // 點擊外部關閉
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(event.target as Node) &&
        anchorElement &&
        !anchorElement.contains(event.target as Node)
      ) {
        onClose();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose, anchorElement]);

  // 找到兩端的 anchor
  const leftAnchor = knob.anchors[0];
  const rightAnchor = knob.anchors[knob.anchors.length - 1];

  // 計算效果摘要
  const effectSummary = useMemo(() => {
    const summaries: Record<string, Record<string, string>> = {
      intervention_level: {
        low: '介入：旁觀整理｜不主動建議',
        medium: '介入：主動提案｜給 2-3 選項',
        high: '介入：直接執行｜產出可確認草稿',
      },
      convergence: {
        low: '收斂：發散探索｜多種可能性',
        medium: '收斂：平衡｜探索後收斂',
        high: '收斂：強制收斂｜直接給結論',
      },
      verbosity: {
        low: '密度：一句話｜max_tokens ≈ 100',
        medium: '密度：條列式｜max_tokens ≈ 500',
        high: '密度：完整稿｜max_tokens ≈ 2000',
      },
      retrieval_radius: {
        low: '檢索：本對話｜不查其他資料',
        medium: '檢索：本 Workspace｜查本區資料',
        high: '檢索：跨 Workspace｜查所有有權限的',
      },
    };

    const level = value <= 30 ? 'low' : value <= 70 ? 'medium' : 'high';
    return summaries[knob.id]?.[level] || `${knob.label}: ${value}%`;
  }, [knob.id, knob.label, value]);

  // 計算位置
  useEffect(() => {
    if (popoverRef.current && anchorElement) {
      const rect = anchorElement.getBoundingClientRect();
      const popover = popoverRef.current;
      popover.style.position = 'fixed';
      popover.style.bottom = `${window.innerHeight - rect.top + 8}px`;
      popover.style.left = `${rect.left + rect.width / 2}px`;
      popover.style.transform = 'translateX(-50%)';
    }
  }, [anchorElement]);

  return (
    <div
      ref={popoverRef}
      className="knob-popover"
      role="dialog"
      style={{
        position: 'fixed',
        padding: '12px 16px',
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: '14px',
        boxShadow: 'var(--shadow)',
        minWidth: '200px',
        zIndex: 100,
      }}
    >
      {/* v2.4 風險 1 解法：本次會套用的效果摘要 */}
      <div
        className="mb-3 pb-2 text-xs"
        style={{
          borderBottom: '1px solid var(--border)',
          color: 'var(--muted)',
        }}
      >
        {effectSummary}
      </div>

      {/* Slider */}
      <input
        type="range"
        min={knob.min_value}
        max={knob.max_value}
        step={10}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-2 rounded-lg appearance-none cursor-pointer"
        style={{
          background: `linear-gradient(to right, var(--accent) ${value}%, var(--border) ${value}%)`,
        }}
      />

      {/* Anchors（左/右） */}
      <div
        className="flex justify-between mt-2 text-xs"
        style={{ color: 'var(--muted)' }}
      >
        <span>{leftAnchor.label}</span>
        <span>{rightAnchor.label}</span>
      </div>

      {/* 1 行超短描述（避免玄學） */}
      {knob.description && (
        <p className="mt-3 text-xs" style={{ color: 'var(--muted)' }}>
          {knob.description}
        </p>
      )}
    </div>
  );
}

