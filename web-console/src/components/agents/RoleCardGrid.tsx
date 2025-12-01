'use client';

import React, { useMemo } from 'react';
import { AI_ROLES, AIRole } from '../../lib/ai-roles';
import { getLocalizedRole } from '../../lib/ai-roles';
import { t } from '../../lib/i18n';
import RoleCard from './RoleCard';
import DrawRoleCard from './DrawRoleCard';
import { WorkScene } from '../../lib/work-scenes';

interface RoleCardGridProps {
  task: string;
  backendAvailable: boolean;
  onRoleSelect: (role: AIRole) => void;
  onSceneSelected: (scene: WorkScene) => void;
  showDrawCard?: boolean;
  searchQuery?: string;
  selectedCategories?: string[];
}

export default function RoleCardGrid({
  task,
  backendAvailable,
  onRoleSelect,
  onSceneSelected,
  showDrawCard = true,
  searchQuery = '',
  selectedCategories = [],
}: RoleCardGridProps) {
  const filteredRoles = useMemo(() => {
    let roles = AI_ROLES;

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      roles = roles.filter((role) => {
        const localized = getLocalizedRole(role, t as any);
        return (
          localized.name.toLowerCase().includes(query) ||
          localized.description.toLowerCase().includes(query)
        );
      });
    }

    if (selectedCategories.length > 0 && !selectedCategories.includes('all')) {
      roles = roles.filter((role) => {
        if (!role.categories || role.categories.length === 0) {
          return false;
        }
        return role.categories.some((cat) => selectedCategories.includes(cat));
      });
    }

    return roles;
  }, [searchQuery, selectedCategories]);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {showDrawCard && (
        <DrawRoleCard
          task={task}
          backendAvailable={backendAvailable || false}
          onSceneSelected={onSceneSelected}
        />
      )}
      {filteredRoles.map((role) => (
        <RoleCard
          key={role.id}
          role={role}
          onSelect={onRoleSelect}
        />
      ))}
      {filteredRoles.length === 0 && (
        <div className="col-span-full text-center py-12 text-gray-500">
          <p className="text-lg mb-2">{t('noRolesFound')}</p>
          <p className="text-sm">{t('tryDifferentSearch')}</p>
        </div>
      )}
    </div>
  );
}




