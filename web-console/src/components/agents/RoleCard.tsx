'use client';

import React from 'react';
import { t } from '../../lib/i18n';
import { AIRole, getLocalizedRole } from '../../lib/ai-roles';

interface RoleCardProps {
  role: AIRole;
  onSelect: (role: AIRole) => void;
}

export default function RoleCard({ role, onSelect }: RoleCardProps) {
  const localized = getLocalizedRole(role, t);

  return (
    <button
      type="button"
      onClick={() => onSelect(role)}
      className="p-5 border-2 rounded-lg text-left transition-all hover:border-blue-300 hover:bg-blue-50 border-gray-200 bg-white"
    >
      <div className="flex items-start mb-3">
        <span className="text-3xl mr-3">{role.icon}</span>
        <div className="flex-1">
          <h3 className="font-semibold text-gray-900 text-lg mb-1">{localized.name}</h3>
          <p className="text-sm text-gray-600">{localized.description}</p>
        </div>
      </div>
    </button>
  );
}




