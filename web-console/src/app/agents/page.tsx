'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import Header from '../../components/Header';
import { t } from '../../lib/i18n';
import { WORK_SCENES, WorkScene, getWorkSceneById } from '../../lib/work-scenes';
import { AI_ROLES, AIRole, getRoleById, getLocalizedRole } from '../../lib/ai-roles';
import RoleCardGrid from '../../components/agents/RoleCardGrid';
import RoleFilterSidebar from '../../components/agents/RoleFilterSidebar';
import { getApiBaseUrl } from '../../lib/api-url';

const API_URL = getApiBaseUrl();

export default function AgentsPage() {
  const [selectedScene, setSelectedScene] = useState<string | null>(null);
  const [selectedRole, setSelectedRole] = useState<string | null>(null);
  const [task, setTask] = useState('');
  const [agentType, setAgentType] = useState('planner');
  const [agentTypeDescription, setAgentTypeDescription] = useState('');
  const [useMindscape, setUseMindscape] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [suggestedPlaybooks, setSuggestedPlaybooks] = useState<string[]>([]);
  const [backendAvailable, setBackendAvailable] = useState<boolean | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [onboardingContext, setOnboardingContext] = useState<string | null>(null);
  const [runningAll, setRunningAll] = useState(false);
  const [allAgentsResults, setAllAgentsResults] = useState<any[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategories, setSelectedCategories] = useState<string[]>(['all']);

  const handleSceneSelect = (scene: WorkScene) => {
    setSelectedScene(scene.id);
    setAgentType(scene.defaultAgentType);
    setTask(scene.defaultPromptTemplate);
  };

  const handleRoleSelect = (role: AIRole) => {
    setSelectedRole(role.id);
    setAgentType(role.agentType);
    setSelectedScene(null);
  };

  const handleSuggestedTaskSelect = (taskText: string) => {
    setTask(taskText);
  };

  const handleCategoryToggle = (categoryId: string) => {
    if (categoryId === 'all') {
      setSelectedCategories(['all']);
    } else {
      setSelectedCategories((prev) => {
        const newCategories = prev.includes(categoryId)
          ? prev.filter((id) => id !== categoryId)
          : [...prev.filter((id) => id !== 'all'), categoryId];
        return newCategories.length === 0 ? ['all'] : newCategories;
      });
    }
  };

  useEffect(() => {
    const checkBackendAvailability = async () => {
      try {
        const apiUrl = API_URL.startsWith('http') ? API_URL : '';
        const response = await fetch(`${apiUrl}/api/v1/config/backend?profile_id=default-user`, {
          headers: { 'Content-Type': 'application/json' },
        });
        if (response.ok) {
          const config = await response.json();
          const currentBackend = config.available_backends?.[config.current_mode];
          setBackendAvailable(currentBackend?.available || false);
          if (!currentBackend?.available) {
            setConfigError(t('apiKeyNotConfigured' as any));
          }
        }
      } catch (err) {
        setBackendAvailable(false);
        setConfigError('Unable to check backend configuration status.');
      }
    };
    checkBackendAvailability();
  }, []);

  useEffect(() => {
    const loadSuggestedPlaybooks = async () => {
      try {
        const apiUrl = API_URL.startsWith('http') ? API_URL : '';
        const response = await fetch(`${apiUrl}/api/v1/playbooks`, {
          headers: { 'Content-Type': 'application/json' },
        });
        if (response.ok) {
          const playbooks = await response.json();
          setSuggestedPlaybooks(playbooks.slice(0, 3).map((p: any) => p.metadata.playbook_code));
        }
      } catch (err) {
      }
    };
    loadSuggestedPlaybooks();
  }, []);

  const handleRunAgent = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const profileId = 'default-user';
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';

      const response = await fetch(`${apiUrl}/api/v1/agent/run?profile_id=${profileId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          task,
          agent_type: agentType,
          agent_type_description: agentTypeDescription || undefined,
          use_mindscape: useMindscape,
          intent_ids: [],
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to run agent');
      }

      const data = await response.json();
      setResult(data);
    } catch (err: any) {
      let errorMessage = err.message || 'Failed to run agent';
      if (errorMessage.includes('No LLM providers configured') ||
          errorMessage.includes('OPENAI_API_KEY') ||
          errorMessage.includes('ANTHROPIC_API_KEY')) {
        errorMessage = t('apiKeyNotConfigured' as any);
      }
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };


  const handleRunAllAgents = async (e: React.FormEvent) => {
    e.preventDefault();
    setRunningAll(true);
    setError(null);
    setAllAgentsResults([]);

    try {
      const profileId = 'default-user';
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';

      const response = await fetch(`${apiUrl}/api/v1/agent/run-all?profile_id=${profileId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          task,
          agent_type: 'planner',
          use_mindscape: useMindscape,
          intent_ids: [],
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to run all agents');
      }

      const data = await response.json();
      setAllAgentsResults(data);
    } catch (err: any) {
      setError(err.message || t('error' as any));
    } finally {
      setRunningAll(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <Header />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-3">{t('pageTitle' as any)}</h1>
          <p className="text-lg text-gray-700 dark:text-gray-300 mb-2">{t('pageSubtitle' as any)}</p>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">{t('mindscapeHint' as any)}</p>
          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
            <p className="text-sm text-blue-800 dark:text-blue-300">
              <strong>💡 {t('hint' as any)}：</strong> {t('selectAIRole' as any)} {t('drawRoleCardDescription' as any)}，或直接從下方選擇一個 AI 成員開始。
            </p>
          </div>
        </div>

        {!selectedRole && (
          <div className="mb-8">
            <div className="flex gap-8">
              <RoleFilterSidebar
                searchQuery={searchQuery}
                selectedCategories={selectedCategories}
                onSearchChange={setSearchQuery}
                onCategoryToggle={handleCategoryToggle}
              />
              <div className="flex-1">
                <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">{t('aiRoles' as any)}</h2>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">{t('selectAIRole' as any)}</p>
                <RoleCardGrid
                  task={task}
                  backendAvailable={backendAvailable || false}
                  onRoleSelect={handleRoleSelect}
                  onSceneSelected={handleSceneSelect}
                  showDrawCard={true}
                  searchQuery={searchQuery}
                  selectedCategories={selectedCategories}
                />
              </div>
            </div>
          </div>
        )}

        {selectedRole && (() => {
          const role = AI_ROLES.find(r => r.id === selectedRole);
          if (!role) return null;
          const localized = getLocalizedRole(role, t);

          return (
            <div className="mb-8 bg-white dark:bg-gray-800 shadow rounded-lg p-6">
              <div className="flex items-start justify-between mb-6">
                <div className="flex items-center">
                  <span className="text-4xl mr-4">{role.icon}</span>
                  <div>
                    <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{localized.name}</h2>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{localized.description}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedRole(null);
                      setTask('');
                    }}
                    className="text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 flex items-center gap-1"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                    </svg>
                    {t('backToList' as any)}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedRole(null);
                      setTask('');
                    }}
                    className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
                  >
                    {t('reselect' as any)}
                  </button>
                </div>
              </div>

              <div className="mb-6 bg-gray-50 dark:bg-gray-800/20 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                <div className="flex items-start">
                  <span className="text-xl mr-3">🧠</span>
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-300 mb-1">
                      {t('memberMindscape' as any)}
                    </p>
                    <p className="text-xs text-gray-700 dark:text-gray-400 mb-2">
                      {t('primaryMindscape' as any)}: <span className="font-medium">{t('defaultMindscape' as any)}</span>{t('switchable' as any)}
                    </p>
                    <p className="text-xs text-gray-600 dark:text-gray-400">
                      {t('memberPreferences' as any)}：{t('memberPreferencesDescription' as any)}
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
                    <span className="text-xl mr-3">👥</span>
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
                            <span className="mr-2">•</span>
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
                    <span className="text-xl mr-3">💡</span>
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
                        {t('goToToolSettings' as any)} →
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
                  {t('selectPlaybookFirst' as any)}：{t('selectPlaybookFirstDescription' as any)}
                </p>
                <div className="flex flex-wrap gap-2">
                  {localized.suggestedTasks.map((taskText, index) => (
                    <button
                      key={index}
                      type="button"
                      onClick={() => handleSuggestedTaskSelect(taskText)}
                      className="px-4 py-2 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-full hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                    >
                      {taskText}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          );
        })()}

        {backendAvailable === false && configError && (
          <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4 mb-6">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-yellow-400 dark:text-yellow-500" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3 flex-1">
                <p className="text-sm text-yellow-800 dark:text-yellow-300">{configError}</p>
                <div className="mt-2">
                  <a
                    href="/settings"
                    className="text-sm font-medium text-yellow-800 dark:text-yellow-300 underline hover:text-yellow-900 dark:hover:text-yellow-200"
                  >
                    {t('goToSettingsConfigure' as any)} →
                  </a>
                </div>
              </div>
            </div>
          </div>
        )}

        <form onSubmit={handleRunAgent} className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 mb-6">
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {t('task' as any)}
              </label>
              <textarea
                value={task}
                onChange={(e) => setTask(e.target.value)}
                rows={6}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                placeholder={t('taskPlaceholder' as any)}
                required
              />
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setTask(t('taskExample1') + ': ' + 'Help me plan this week\'s work priorities and list important tasks for each day.')}
                  className="px-3 py-1 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-full hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                >
                  {t('taskExample1')}
                </button>
                <button
                  type="button"
                  onClick={() => setTask(t('taskExample2') + ': ' + 'Help me plan the content structure for the fundraising page, including required sections, key points for each section, and overall narrative logic.')}
                  className="px-3 py-1 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-full hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                >
                  {t('taskExample2')}
                </button>
                <button
                  type="button"
                  onClick={() => setTask(t('taskExample3') + ': ' + 'Help me create a learning plan, including goal setting, learning path, practice methods, and how to track progress.')}
                  className="px-3 py-1 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-full hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                >
                  {t('taskExample3')}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {t('agentType' as any)}
              </label>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">{t('agentTypeDescriptionNew' as any)}</p>
              <textarea
                value={agentTypeDescription}
                onChange={(e) => setAgentTypeDescription(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                placeholder={t('agentTypePlaceholder' as any)}
              />
            </div>

            <div className="border-t dark:border-gray-700 pt-4">
              <div className="flex items-start">
                <input
                  type="checkbox"
                  id="useMindscape"
                  checked={useMindscape}
                  onChange={(e) => setUseMindscape(e.target.checked)}
                  className="mt-1 mr-2"
                />
                <div className="flex-1">
                  <label htmlFor="useMindscape" className="text-sm font-medium text-gray-700 dark:text-gray-300 block">
                    {t('useMindscape' as any)}
                  </label>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    {t('useMindscapeDescription' as any)}
                  </p>
                </div>
              </div>
            </div>

            <div>
              <button
                type="submit"
                disabled={loading || !task.trim() || backendAvailable === false || (!selectedRole && !selectedScene)}
                className={`w-full px-4 py-2 rounded-md font-medium transition-colors ${
                  !task.trim() || backendAvailable === false || (!selectedRole && !selectedScene)
                    ? 'bg-gray-300 dark:bg-gray-600 text-gray-500 dark:text-gray-400 cursor-not-allowed'
                    : 'bg-blue-600 dark:bg-blue-700 text-white hover:bg-blue-700 dark:hover:bg-blue-600'
                } ${loading ? 'opacity-50' : ''}`}
              >
                {loading ? t('loading' as any) : selectedRole ? (() => {
                  const role = AI_ROLES.find(r => r.id === selectedRole);
                  return role ? t('launchRole' as any).replace('{roleName}', getLocalizedRole(role, t).name) : t('runAgent' as any);
                })() : t('runAgent' as any)}
              </button>
              {!selectedRole && !selectedScene && (
                <p className="text-xs text-gray-500 dark:text-gray-400 text-center mt-2">
                  {t('pleaseSelectAIMemberFirst' as any)}
                </p>
              )}
              {!task.trim() && (selectedRole || selectedScene) && (
                <p className="text-xs text-gray-500 dark:text-gray-400 text-center mt-2">
                  {t('pleaseDescribeTask' as any)}
                </p>
              )}
              {backendAvailable === false && task.trim() && (selectedRole || selectedScene) && (
                <p className="text-xs text-gray-500 dark:text-gray-400 text-center mt-2">
                  {t('configureApiKeyFirst' as any)}
                </p>
              )}
            </div>
          </div>
        </form>

        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-6">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-red-400 dark:text-red-500" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3 flex-1">
                <p className="text-sm text-red-800 dark:text-red-300">{error}</p>
                {(error.includes('API') || error.includes('api')) && (
                  <div className="mt-2">
                    <a
                      href="/settings"
                      className="text-sm font-medium text-red-800 dark:text-red-300 underline hover:text-red-900 dark:hover:text-red-200"
                    >
                      {t('goToSettings' as any)} →
                    </a>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {result && (
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">{t('executionResult' as any)}</h2>
            <div className="bg-gray-50 dark:bg-gray-700 rounded-md p-4">
              <pre className="whitespace-pre-wrap text-sm text-gray-800 dark:text-gray-200">
                {result.output || result.error_message}
              </pre>
            </div>
            {result.metadata && (
              <div className="mt-4 text-sm text-gray-600 dark:text-gray-400">
                <p>{t('executionId' as any)}: {result.execution_id}</p>
                <p>{t('status' as any)}: {result.status}</p>
              </div>
            )}
          </div>
        )}

        {suggestedPlaybooks.length > 0 && (
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 mt-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">{t('suggestedPlaybooks' as any)}</h2>
            <div className="space-y-2">
              {suggestedPlaybooks.map(code => (
                <Link
                  key={code}
                  href={`/playbooks/${code}`}
                  className="block text-sm text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300"
                >
                  → {code}
                </Link>
              ))}
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-4">
              {t('playbookHelp' as any)}
            </p>
          </div>
        )}

        <div className="mt-8 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
          <p className="text-sm text-blue-800 dark:text-blue-300">
            <strong>{t('hint' as any)}：</strong> {t('settingsHint' as any)}
          </p>
        </div>
      </main>
    </div>
  );
}
