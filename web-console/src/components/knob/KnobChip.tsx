'use client';

import React, { useState, useRef, useMemo } from 'react';
import { KnobPopover } from './KnobPopover';

export interface MasterValueRange {
  min_value: number;
  max_value: number;
  slave_value: number;
}

export interface ControlKnob {
  id: string;
  label: string;
  icon?: string;
  min_value: number;
  max_value: number;
  default_value: number;
  step?: number;
  anchors: Array<{ value: number; label: string; description?: string }>;
  description?: string;

  // Master-slave relationship
  master_knob_id?: string;
  is_locked_to_master?: boolean;
  master_value_mapping?: MasterValueRange[];

  // Parameter exclusivity
  exclusive_param?: string;

  // Effects (simplified for frontend - full details in backend)
  prompt_patch?: {
    template: string;
    position?: string;
    condition?: string;
    use_natural_language?: boolean;
  };
  model_params_delta?: {
    temperature_delta?: number;
    top_p_delta?: number;
    presence_penalty_delta?: number;
    frequency_penalty_delta?: number;
    max_tokens_delta?: number;
  };
  runtime_policy_delta?: {
    max_questions_per_turn_delta?: number;
    assume_defaults_override?: boolean;
    auto_read_override?: boolean;
    confirm_soft_write_override?: boolean;
    confirm_external_write_override?: boolean;
    retrieval_scope?: string;
  };

  // Calibration
  calibration_examples?: Array<{
    knob_value: number;
    input_example: string;
    output_example: string;
    explanation?: string;
  }>;

  // Metadata
  knob_type?: string; // "hard" | "soft"
  category?: string;
  is_advanced?: boolean;
  is_enabled?: boolean;
  version?: string;
  created_by?: string;
}

interface KnobChipProps {
  knob: ControlKnob;
  value: number;
  isActive?: boolean;
  isLocked?: boolean;
  onChange: (value: number) => void;
  onUnlock?: () => void;
}

export function KnobChip({
  knob,
  value,
  isActive = false,
  isLocked = false,
  onChange,
  onUnlock
}: KnobChipProps) {
  const [isOpen, setIsOpen] = useState(false);
  const chipRef = useRef<HTMLButtonElement>(null);

  // 格式化顯示值
  const displayValue = useMemo(() => {
    if (knob.id === 'retrieval_radius') {
      if (value <= 30) return '本對話';
      if (value <= 70) return '本區';
      return '跨區';
    }
    return value;
  }, [knob.id, value]);

  const handleClick = () => {
    if (isLocked) {
      // 提示用戶可以解鎖
      if (confirm('此旋鈕已鎖定跟隨主旋鈕。要解鎖進階調整嗎？')) {
        onUnlock?.();
      }
      return;
    }
    setIsOpen(!isOpen);
  };

  return (
    <div className="relative inline-block">
      <button
        ref={chipRef}
        className="knob-chip"
        data-active={isActive}
        data-locked={isLocked}
        onClick={handleClick}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        style={{
          height: '28px',
          padding: '0 10px',
          borderRadius: '999px',
          border: `1px solid ${isActive ? 'var(--accent)' : 'var(--border)'}`,
          background: isActive ? 'var(--accent-2)' : 'var(--surface-2)',
          color: isLocked ? 'var(--muted)' : 'var(--text)',
          fontSize: '12px',
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          cursor: isLocked ? 'not-allowed' : 'pointer',
          opacity: isLocked ? 0.5 : 1,
          transition: 'all 0.15s ease',
          boxShadow: isActive ? '0 0 0 3px var(--accent-2)' : 'none',
        }}
      >
        <span className="knob-chip-label">{knob.label}</span>
        <span className="knob-chip-value" style={{ color: 'var(--accent)' }}>
          {displayValue}
        </span>
        {isLocked && <span style={{ fontSize: '10px' }}>🔒</span>}
      </button>

      {/* Popover */}
      {isOpen && !isLocked && (
        <KnobPopover
          knob={knob}
          value={value}
          onChange={onChange}
          onClose={() => setIsOpen(false)}
          anchorElement={chipRef.current}
        />
      )}
    </div>
  );
}

