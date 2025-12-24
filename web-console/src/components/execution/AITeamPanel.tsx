'use client';

import React from 'react';

export interface AITeamMember {
  id: string;
  name: string;
  name_zh?: string;
  role: string;
  icon: string;
  status: 'pending' | 'in_progress' | 'completed' | 'error';
}

interface AITeamPanelProps {
  members: AITeamMember[];
  isLoading?: boolean;
}

export default function AITeamPanel({
  members,
  isLoading = false,
}: AITeamPanelProps) {
  if (members.length === 0 && !isLoading) {
    return null;
  }

  const getStatusColor = (status: AITeamMember['status']) => {
    switch (status) {
      case 'in_progress':
        return 'bg-accent dark:bg-blue-500';
      case 'completed':
        return 'bg-green-500';
      case 'error':
        return 'bg-red-500';
      case 'pending':
      default:
        return 'bg-default';
    }
  };

  const getStatusLabel = (status: AITeamMember['status']) => {
    switch (status) {
      case 'in_progress':
        return '執行中';
      case 'completed':
        return '已完成';
      case 'error':
        return '錯誤';
      case 'pending':
      default:
        return '等待中';
    }
  };

  return (
    <div className="ai-team-panel mt-3">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-semibold text-secondary dark:text-gray-400 flex items-center gap-1">
          <span>👥</span>
          <span>本次協作角色</span>
        </h4>
      </div>

      <div className="space-y-2">
        {isLoading && members.length === 0 ? (
          <div className="text-xs text-secondary dark:text-gray-400 italic">
            <span className="inline-flex items-center gap-1">
              <span className="w-1 h-1 bg-accent dark:bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1 h-1 bg-accent dark:bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1 h-1 bg-accent dark:bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </span>
            <span className="ml-2">載入 AI 團隊成員...</span>
          </div>
        ) : (
          members.map((member) => (
            <div
              key={member.id}
              className="flex items-start gap-2 p-2 rounded-lg bg-surface-accent dark:bg-gray-800 border border-default dark:border-gray-700 hover:border-default dark:hover:border-gray-600 transition-colors"
            >
              <div className="flex-shrink-0 text-lg relative">
                {member.icon}
                <span
                  className={`absolute bottom-0 right-0 w-2 h-2 rounded-full border-2 border-surface-accent dark:border-gray-800 ${
                    member.status === 'in_progress' ? 'bg-accent dark:bg-blue-500 animate-pulse' :
                    member.status === 'completed' ? 'bg-green-500' :
                    member.status === 'error' ? 'bg-red-500' :
                    'bg-default'
                  }`}
                />
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <div className="text-xs font-medium text-primary dark:text-gray-100 truncate">
                    {member.name_zh || member.name}
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <span
                      className={`w-1.5 h-1.5 rounded-full ${getStatusColor(member.status)} ${
                        member.status === 'in_progress' ? 'animate-pulse' : ''
                      }`}
                    />
                    <span className="text-[10px] text-secondary dark:text-gray-400">
                      {getStatusLabel(member.status)}
                    </span>
                  </div>
                </div>
                <div className="text-[10px] text-secondary dark:text-gray-400 line-clamp-1">
                  {member.role}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

