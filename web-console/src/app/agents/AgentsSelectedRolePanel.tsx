import Link from 'next/link';

import { useT } from '../../lib/i18n';
import { AI_ROLES, getLocalizedRole } from '../../lib/ai-roles';

interface AgentsSelectedRolePanelProps {
  selectedRole: string;
  onClearSelection: () => void;
  onSuggestedTaskSelect: (taskText: string) => void;
}

export default function AgentsSelectedRolePanel({
  selectedRole,
  onClearSelection,
  onSuggestedTaskSelect,
}: AgentsSelectedRolePanelProps) {
  const t = useT();
  const role = AI_ROLES.find((candidate) => candidate.id === selectedRole);

  if (!role) {
    return null;
  }

  const localized = getLocalizedRole(role, t);

  return (
    <div className="mb-8 bg-white dark:bg-gray-800 shadow rounded-lg p-6">
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center">
          <span className="mr-4 inline-flex h-12 w-12 items-center justify-center rounded-lg bg-blue-50 text-sm font-semibold text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
            {role.id.slice(0, 2).toUpperCase()}
          </span>
          <div>
            <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{localized.name}</h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{localized.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onClearSelection}
            className="text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 flex items-center gap-1"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            {t('backToList' as any)}
          </button>
          <button
            type="button"
            onClick={onClearSelection}
            className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
          >
            {t('reselect' as any)}
          </button>
        </div>
      </div>

      <div className="mb-6 bg-gray-50 dark:bg-gray-800/20 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
        <div className="flex items-start">
          <span className="text-sm font-semibold mr-3 text-gray-500 dark:text-gray-400">MS</span>
          <div className="flex-1">
            <p className="text-sm font-medium text-gray-900 dark:text-gray-300 mb-1">
              {t('memberMindscape' as any)}
            </p>
            <p className="text-xs text-gray-700 dark:text-gray-400 mb-2">
              {t('primaryMindscape' as any)}: <span className="font-medium">{t('defaultMindscape' as any)}</span>{t('switchable' as any)}
            </p>
            <p className="text-xs text-gray-600 dark:text-gray-400">
              {t('memberPreferences' as any)}: {t('memberPreferencesDescription' as any)}
            </p>
          </div>
        </div>
      </div>

      {role.playbooks && role.playbooks.length > 0 && (
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            {t('memberPlaybooks' as any)}
          </label>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
            {t('memberPlaybooksDescription' as any)}
          </p>
          <div className="flex flex-wrap gap-2">
            {role.playbooks.map((playbookCode, index) => (
              <Link
                key={index}
                href={`/playbooks?code=${playbookCode}`}
                className="px-4 py-2 text-sm bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-full hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors"
              >
                {playbookCode}
              </Link>
            ))}
          </div>
        </div>
      )}

      {role.aiTeamMembers && role.aiTeamMembers.length > 0 && (
        <div className="mb-6 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
          <div className="flex items-start">
            <span className="text-sm font-semibold mr-3 text-gray-500 dark:text-gray-400">TEAM</span>
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                {role.aiTeamTitleKey ? (t as any)(role.aiTeamTitleKey) : (t as any)('aiTeamBehindThisMember')}
              </p>
              {role.aiTeamDescriptionKey && (
                <p className="text-xs text-gray-600 dark:text-gray-400 mb-3">
                  {(t as any)(role.aiTeamDescriptionKey)}
                </p>
              )}
              <ul className="space-y-2">
                {role.aiTeamMembers.map((memberKey, index) => (
                  <li key={index} className="text-sm text-gray-700 dark:text-gray-300 flex items-start">
                    <span className="mr-2">-</span>
                    <span>{(t as any)(memberKey)}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {(role.id === 'content_editor' || role.id === 'seo_consultant' || role.id === 'project_manager') && (
        <div className="mb-6 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
          <div className="flex items-start">
            <span className="text-sm font-semibold mr-3 text-blue-700 dark:text-blue-300">INFO</span>
            <div className="flex-1">
              <p className="text-sm text-blue-900 dark:text-blue-300 font-medium mb-1">
                {t('wantToHandleWordPressNotion' as any)}
              </p>
              <p className="text-xs text-blue-700 dark:text-blue-400 mb-3">
                {t('connectToolsDescription' as any)}
              </p>
              <Link
                href="/settings"
                className="inline-block px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white text-sm rounded-md hover:bg-blue-700 dark:hover:bg-blue-600"
              >
                {t('goToToolSettings' as any)}
              </Link>
            </div>
          </div>
        </div>
      )}

      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
          {t('suggestedTasks' as any)}
        </label>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
          {t('selectPlaybookFirst' as any)}: {t('selectPlaybookFirstDescription' as any)}
        </p>
        <div className="flex flex-wrap gap-2">
          {localized.suggestedTasks.map((taskText, index) => (
            <button
              key={index}
              type="button"
              onClick={() => onSuggestedTaskSelect(taskText)}
              className="px-4 py-2 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-full hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
            >
              {taskText}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
