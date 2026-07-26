'use client';

import React, { useState } from 'react';
import { useT } from '../../lib/i18n';

export interface RoleCategory {
  id: string;
  nameKey: string;
  icon?: string;
}

export const ROLE_CATEGORIES: RoleCategory[] = [
  { id: 'all', nameKey: 'categoryAll', icon: '📋' },
  { id: 'design', nameKey: 'categoryDesign', icon: '🎨' },
  { id: 'content', nameKey: 'categoryContent', icon: '✍️' },
  { id: 'business', nameKey: 'categoryBusiness', icon: '💼' },
  { id: 'technical', nameKey: 'categoryTechnical', icon: '💻' },
  { id: 'productivity', nameKey: 'categoryProductivity', icon: '⚡' },
  { id: 'coaching', nameKey: 'categoryCoaching', icon: '🧠' },
];

interface RoleFilterSidebarProps {
  searchQuery: string;
  selectedCategories: string[];
  onSearchChange: (query: string) => void;
  onCategoryToggle: (categoryId: string) => void;
}

export default function RoleFilterSidebar({
  searchQuery,
  selectedCategories,
  onSearchChange,
  onCategoryToggle,
}: RoleFilterSidebarProps) {
  const t = useT();
  return (
    <div className="w-64 flex-shrink-0 pr-6">
      <div className="sticky top-8">
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            {t('search' as any)}
          </label>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={t('searchRoles' as any)}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            {t('categories' as any)}
          </label>
          <div className="space-y-2">
            {ROLE_CATEGORIES.map((category) => {
              const isSelected = selectedCategories.includes(category.id);
              return (
                <label
                  key={category.id}
                  className="flex items-center cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 p-2 rounded-md transition-colors"
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => onCategoryToggle(category.id)}
                    className="mr-3 h-4 w-4 text-blue-600 dark:text-blue-400 focus:ring-blue-500 dark:focus:ring-blue-400 border-gray-300 dark:border-gray-600 rounded"
                  />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    {category.icon && <span className="mr-2">{category.icon}</span>}
                    {t(category.nameKey as any)}
                  </span>
                </label>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}




