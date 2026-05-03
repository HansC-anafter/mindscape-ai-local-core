'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useWorkspaceData } from '@/contexts/WorkspaceDataContext';
import { BookOpen, Building2, Clock3, Lightbulb, Map } from 'lucide-react';

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
    { href: `/workspaces/${workspaceId}/brand`, label: 'Brand Mindspace', icon: Building2 },
    { href: `/workspaces/${workspaceId}/brand/cis-mapping`, label: 'CIS Mapping', icon: Map },
    { href: `/workspaces/${workspaceId}/intents`, label: 'Intent Pool', icon: Lightbulb },
    { href: `/workspaces/${workspaceId}/brand/storylines`, label: 'Storylines', icon: BookOpen },
    { href: `/workspaces/${workspaceId}/executions/timeline`, label: 'Execution Timeline', icon: Clock3 },
  ];

  return (
    <nav className="w-64 bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 p-4">
      <div className="space-y-1">
        <h2 className="px-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">
          Brand Workspace
        </h2>
        {navItems.map((item) => {
          const isActive = pathname === item.href || pathname?.startsWith(item.href + '/');
          const Icon = item.icon;
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
              <Icon className="mr-2 h-4 w-4" aria-hidden="true" />
              {item.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
