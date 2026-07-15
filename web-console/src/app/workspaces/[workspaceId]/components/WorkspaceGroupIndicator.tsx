'use client';

import React, { useState } from 'react';

import type { WorkspaceGroupTopology } from '@/contexts/WorkspaceGroupContext';


interface WorkspaceGroupIndicatorProps {
  groups: WorkspaceGroupTopology[];
  activeGroup: WorkspaceGroupTopology | null;
  activeRole: 'dispatch' | 'cell' | null;
  isLoading: boolean;
  onSelect: (groupId: string | null) => void;
}

function roleStyle(role: string) {
  return role === 'dispatch'
    ? 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300'
    : 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300';
}

export default function WorkspaceGroupIndicator({
  groups,
  activeGroup,
  activeRole,
  isLoading,
  onSelect,
}: WorkspaceGroupIndicatorProps) {
  const [isOpen, setIsOpen] = useState(false);

  if (!isLoading && groups.length === 0) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium bg-indigo-50 dark:bg-indigo-900/20 hover:bg-indigo-100 dark:hover:bg-indigo-900/40 text-indigo-600 dark:text-indigo-400 transition-colors"
        title="Workspace Group context"
      >
        <span>GRP</span>
        <span>{isLoading ? 'Loading' : activeGroup?.display_name || 'Single workspace'}</span>
        {activeRole ? <span className="text-[10px] opacity-70">({activeRole})</span> : null}
      </button>

      {isOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
          onClick={() => setIsOpen(false)}
        >
          <div
            className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl border border-gray-200 dark:border-gray-700 w-full max-w-lg mx-4 p-6"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  Workspace Group context
                </h3>
                <p className="text-xs text-gray-500 mt-1">
                  Group mode starts only after an explicit selection.
                </p>
              </div>
              <button type="button" onClick={() => setIsOpen(false)} aria-label="Close">×</button>
            </div>

            <div className="space-y-2">
              <button
                type="button"
                onClick={() => onSelect(null)}
                className={`w-full text-left rounded-lg border p-3 ${!activeGroup ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/30' : 'border-gray-200 dark:border-gray-700'}`}
              >
                <div className="font-medium text-sm">Single workspace</div>
                <div className="text-xs text-gray-500">No cross-workspace dispatch context</div>
              </button>

              {groups.map((group) => (
                <button
                  type="button"
                  key={group.id}
                  onClick={() => onSelect(group.id)}
                  className={`w-full text-left rounded-lg border p-3 ${activeGroup?.id === group.id ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/30' : 'border-gray-200 dark:border-gray-700'}`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="font-medium text-sm text-gray-900 dark:text-gray-100">
                        {group.display_name}
                      </div>
                      <div className="text-xs text-gray-500">
                        revision {group.revision} · {group.members.length} workspace(s)
                      </div>
                    </div>
                    <span className={`rounded px-2 py-0.5 text-[10px] ${group.is_ready ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                      {group.is_ready ? 'ready' : 'setup'}
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {group.members.map((member) => (
                      <span key={member.workspace_id} className={`rounded px-1.5 py-0.5 text-[10px] ${roleStyle(member.role)}`}>
                        {member.title || member.workspace_id} · {member.role}
                      </span>
                    ))}
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
