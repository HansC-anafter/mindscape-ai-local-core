'use client';

import React from 'react';

export type WorkspaceToolRailTone = 'light' | 'dark';

export interface WorkspaceToolRailGroup {
  id: string;
  label?: string;
  children: React.ReactNode;
  testId?: string;
}

interface WorkspaceToolRailProps {
  ariaLabel: string;
  groups: WorkspaceToolRailGroup[];
  tone?: WorkspaceToolRailTone;
  testId?: string;
}

interface WorkspaceToolRailButtonProps {
  label: string;
  icon: React.ReactNode;
  active?: boolean;
  disabled?: boolean;
  badge?: number | string | null;
  testId?: string;
  onClick: () => void;
}

function railClassName(tone: WorkspaceToolRailTone): string {
  return tone === 'dark'
    ? 'pointer-events-auto flex h-full w-9 shrink-0 flex-col items-center border-l border-stone-800 bg-black/90 pb-3 pt-12 backdrop-blur'
    : 'pointer-events-auto flex h-full w-10 shrink-0 flex-col items-center border-l border-gray-200 bg-white/90 pb-3 pt-12 shadow-[-6px_0_18px_rgba(15,23,42,0.08)] backdrop-blur dark:border-gray-700 dark:bg-gray-900/90';
}

function groupClassName(tone: WorkspaceToolRailTone, hasDivider: boolean): string {
  const dividerClass = hasDivider
    ? tone === 'dark'
      ? 'border-b border-stone-800 pb-3'
      : 'border-b border-gray-200 pb-3 dark:border-gray-700'
    : '';
  return `flex w-full flex-col items-center gap-1 px-1 ${dividerClass}`.trim();
}

function labelClassName(tone: WorkspaceToolRailTone): string {
  return tone === 'dark'
    ? 'text-center text-[6px] uppercase leading-none tracking-normal text-stone-500'
    : 'text-center text-[6px] uppercase leading-none tracking-normal text-gray-400 dark:text-gray-500';
}

export function WorkspaceToolRail({
  ariaLabel,
  groups,
  tone = 'light',
  testId = 'workspace-tool-rail',
}: WorkspaceToolRailProps) {
  return (
    <nav
      className={railClassName(tone)}
      data-testid={testId}
      data-workspace-tool-rail="true"
      aria-label={ariaLabel}
    >
      {groups.map((group, index) => {
        const hasDivider = index < groups.length - 1;
        return (
          <div
            key={group.id}
            className={index === 0 ? groupClassName(tone, hasDivider) : `${groupClassName(tone, hasDivider)} pt-3`}
            data-testid={group.testId}
          >
            {group.children}
            {group.label ? (
              <div className={labelClassName(tone)}>
                {group.label}
              </div>
            ) : null}
          </div>
        );
      })}
    </nav>
  );
}

export function WorkspaceToolRailButton({
  label,
  icon,
  active = false,
  disabled = false,
  badge = null,
  testId,
  onClick,
}: WorkspaceToolRailButtonProps) {
  const badgeText = badge == null ? '' : String(badge);
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={active}
      disabled={disabled}
      title={label}
      data-testid={testId}
      onClick={onClick}
      className={`relative inline-flex h-8 w-8 items-center justify-center rounded border text-gray-600 transition focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50 dark:text-gray-300 ${
        active
          ? 'border-blue-500 bg-blue-50 text-blue-700 dark:border-blue-400 dark:bg-blue-950/40 dark:text-blue-200'
          : 'border-transparent bg-transparent hover:border-gray-200 hover:bg-gray-50 hover:text-gray-900 dark:hover:border-gray-700 dark:hover:bg-gray-800 dark:hover:text-gray-100'
      }`}
    >
      {icon}
      {badgeText ? (
        <span className="absolute -right-1 -top-1 min-w-[14px] rounded-full bg-red-500 px-1 text-[9px] font-semibold leading-[14px] text-white">
          {badgeText}
        </span>
      ) : null}
    </button>
  );
}

export default WorkspaceToolRail;
