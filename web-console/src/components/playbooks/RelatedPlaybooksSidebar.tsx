'use client';

import React, { useMemo } from 'react';
import Link from 'next/link';
import { t } from '../../lib/i18n';

interface Playbook {
  playbook_code: string;
  name: string;
  description?: string;
  icon?: string;
  tags?: string[];
  capability_code?: string;
}

interface RelatedPlaybooksSidebarProps {
  currentPlaybook: Playbook;
  allPlaybooks: Playbook[];
  recentPlaybooks: Playbook[];
}

export default function RelatedPlaybooksSidebar({
  currentPlaybook,
  allPlaybooks,
  recentPlaybooks
}: RelatedPlaybooksSidebarProps) {
  const samePackPlaybooks = useMemo(() => {
    if (!currentPlaybook.capability_code) return [];
    
    return allPlaybooks
      .filter(pb => 
        pb.playbook_code !== currentPlaybook.playbook_code &&
        pb.capability_code === currentPlaybook.capability_code
      )
      .slice(0, 5);
  }, [currentPlaybook, allPlaybooks]);

  const relatedTagsPlaybooks = useMemo(() => {
    if (!currentPlaybook.tags || currentPlaybook.tags.length === 0) return [];
    
    const currentTags = new Set(currentPlaybook.tags);
    
    return allPlaybooks
      .filter(pb => {
        if (pb.playbook_code === currentPlaybook.playbook_code) return false;
        if (!pb.tags || pb.tags.length === 0) return false;
        return pb.tags.some(tag => currentTags.has(tag));
      })
      .sort((a, b) => {
        const aMatchCount = (a.tags || []).filter(tag => currentTags.has(tag)).length;
        const bMatchCount = (b.tags || []).filter(tag => currentTags.has(tag)).length;
        return bMatchCount - aMatchCount;
      })
      .slice(0, 5);
  }, [currentPlaybook, allPlaybooks]);

  return (
    <div className="bg-surface-secondary dark:bg-gray-900 shadow h-[calc(100vh-7rem)] overflow-y-auto p-4 sticky top-[7rem]">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">{t('relatedPlaybooks')}</h3>

      {/* Same Pack Playbooks */}
      {samePackPlaybooks.length > 0 && (
        <div className="mb-4">
          <h4 className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">{t('samePackPlaybooks')}</h4>
          <div className="space-y-2">
            {samePackPlaybooks.map((pb) => (
              <Link
                key={pb.playbook_code}
                href={`/playbooks/${pb.playbook_code}`}
                scroll={false}
                className="block p-2 rounded-lg transition-colors hover:bg-tertiary dark:hover:bg-gray-800 border border-transparent"
              >
                <div className="flex items-start gap-2">
                  {pb.icon && <span className="text-sm flex-shrink-0">{pb.icon}</span>}
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium truncate text-gray-900 dark:text-gray-100">
                      {pb.name}
                    </div>
                    {pb.description && (
                      <div className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2 mt-1">
                        {pb.description}
                      </div>
                    )}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Related Tags Playbooks */}
      {relatedTagsPlaybooks.length > 0 && (
        <div className="mb-4">
          <h4 className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">{t('relatedTagsPlaybooks')}</h4>
          <div className="space-y-2">
            {relatedTagsPlaybooks.map((pb) => (
              <Link
                key={pb.playbook_code}
                href={`/playbooks/${pb.playbook_code}`}
                scroll={false}
                className="block p-2 rounded-lg transition-colors hover:bg-tertiary dark:hover:bg-gray-800 border border-transparent"
              >
                <div className="flex items-start gap-2">
                  {pb.icon && <span className="text-sm flex-shrink-0">{pb.icon}</span>}
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium truncate text-gray-900 dark:text-gray-100">
                      {pb.name}
                    </div>
                    {pb.description && (
                      <div className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2 mt-1">
                        {pb.description}
                      </div>
                    )}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Recent Views */}
      {recentPlaybooks.length > 0 && (
        <div className="mb-4">
          <h4 className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">{t('recentUsage')}</h4>
          <div className="space-y-2">
            {recentPlaybooks.map((pb) => (
              <Link
                key={pb.playbook_code}
                href={`/playbooks/${pb.playbook_code}`}
                scroll={false}
                className="block p-2 rounded-lg transition-colors hover:bg-tertiary dark:hover:bg-gray-800 border border-transparent"
              >
                <div className="flex items-start gap-2">
                  {pb.icon && <span className="text-sm flex-shrink-0">{pb.icon}</span>}
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium truncate text-gray-900 dark:text-gray-100">
                      {pb.name}
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {samePackPlaybooks.length === 0 && relatedTagsPlaybooks.length === 0 && recentPlaybooks.length === 0 && (
        <div className="text-xs text-gray-500 dark:text-gray-400 text-center py-4">
          {t('noRelatedPlaybooks')}
        </div>
      )}
    </div>
  );
}

