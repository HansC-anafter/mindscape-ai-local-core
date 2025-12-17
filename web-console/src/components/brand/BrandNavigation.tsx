'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useWorkspaceData } from '@/contexts/WorkspaceDataContext';

interface BrandNavigationProps {
  workspaceId: string;
}

export default function BrandNavigation({ workspaceId }: BrandNavigationProps) {
  const pathname = usePathname();
  const { workspace } = useWorkspaceData();

  // Only show brand navigation if workspace_type is 'brand'
  if (!workspace || workspace.workspace_type !== 'brand') {
    return null;
  }

  const navItems = [
    { href: `/workspaces/${workspaceId}/brand`, label: '品牌心智空間', icon: '🏢' },
    { href: `/workspaces/${workspaceId}/brand/cis-mapping`, label: 'CIS 映射', icon: '🗺️' },
    { href: `/workspaces/${workspaceId}/intents`, label: '意圖池', icon: '💭' },
    { href: `/workspaces/${workspaceId}/brand/storylines`, label: '故事線', icon: '📖' },
    { href: `/workspaces/${workspaceId}/executions/timeline`, label: '執行軌跡', icon: '⏱️' },
  ];

  return (
    <nav className="w-64 bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 p-4">
      <div className="space-y-1">
        <h2 className="px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">
          品牌工作區
        </h2>
        {navItems.map((item) => {
          const isActive = pathname === item.href || pathname?.startsWith(item.href + '/');
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center px-3 py-2 text-sm font-medium rounded-md transition-colors ${
                isActive
                  ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >
              <span className="mr-2">{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
