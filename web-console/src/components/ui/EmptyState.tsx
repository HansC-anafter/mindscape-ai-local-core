'use client';

import React from 'react';
import './EmptyState.css';

export type EmptyStateType =
  | 'aiTeam'
  | 'intents'
  | 'artifacts'
  | 'timeline'
  | 'chapters'
  | 'executions'
  | 'default';

interface EmptyStateProps {
  type?: EmptyStateType;
  customMessage?: string;
  className?: string;
}

const emptyStateMessages: Record<EmptyStateType, string> = {
  aiTeam: 'AI team will appear here after execution starts',
  intents: 'No pending decisions at the moment',
  artifacts: 'Artifacts will appear here after execution completes',
  timeline: 'No activity records yet. Start a conversation to create the first timeline',
  chapters: 'Chapters will appear here after creating a Story Thread',
  executions: 'Select a Playbook to start execution',
  default: 'No data available',
};

export function EmptyState({ type = 'default', customMessage, className }: EmptyStateProps) {
  const message = customMessage || emptyStateMessages[type];

  return (
    <div className={`empty-state ${className || ''}`}>
      <span className="hint">{message}</span>
    </div>
  );
}

