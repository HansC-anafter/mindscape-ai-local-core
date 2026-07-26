'use client';

import { useState, useEffect, useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useT, useLocale } from '../../lib/i18n';
import { getPlaybookRegistry } from '../../playbook';
import { PlaybooksPageView } from './PlaybooksPageView';
import {
  createWorkspaceForPlaybook,
  fetchPlaybooks,
  fetchSupportedTestPlaybooks,
  patchPlaybookFavorite,
  reindexPlaybooks,
  togglePinnedPlaybook,
} from './playbooksPageApi';
import type { Playbook } from './playbooksPageTypes';
import {
  buildWorkspaceTitle,
  extractCapabilityCode,
  filterPlaybooksBySearch,
  getAvailableCapabilityCodes,
  groupPlaybooksByCapability,
} from './playbooksPageTransforms';

export default function PlaybooksPage() {
  const t = useT();
  const [locale] = useLocale();
  const router = useRouter();
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [supportedTestPlaybooks, setSupportedTestPlaybooks] = useState<Set<string>>(new Set());
  const [creatingWorkspace, setCreatingWorkspace] = useState<string | null>(null);
  const [reloading, setReloading] = useState(false);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(null);
  const [filter, setFilter] = useState<string | null>(null);
  const [selectedCapability, setSelectedCapability] = useState<string>('system');

  useEffect(() => {
    const loadSupportedTests = async () => {
      try {
        setSupportedTestPlaybooks(await fetchSupportedTestPlaybooks());
      } catch (err) {
        console.error('Failed to load supported test playbooks:', err);
      }
    };
    loadSupportedTests();
  }, []);

  const loadPlaybooks = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const validPlaybooks = await fetchPlaybooks({
        selectedTags,
        locale,
        selectedWorkspaceId,
        filter,
      });

      setPlaybooks(validPlaybooks);
      setError(null);
      validPlaybooks.forEach((playbook) => {
        extractCapabilityCode(playbook);
      });
    } catch (err: any) {
      console.error('Failed to load playbooks:', err);
      if (err.name === 'AbortError') {
        setError('Request timeout: Playbook loading took too long');
      } else {
        setError(err.message || 'Failed to load playbooks. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  }, [selectedTags, locale, selectedWorkspaceId, filter]);

  useEffect(() => {
    loadPlaybooks();
  }, [loadPlaybooks]);

  useEffect(() => {
    const searchParams = new URLSearchParams(window.location.search);
    const workspaceParam = searchParams?.get('workspace' as any);

    if (workspaceParam !== selectedWorkspaceId) {
      if (selectedWorkspaceId) {
        searchParams.set('workspace', selectedWorkspaceId);
      } else {
        searchParams.delete('workspace');
      }
      const newUrl = `${window.location.pathname}${searchParams.toString() ? '?' + searchParams.toString() : ''}`;
      window.history.replaceState({}, '', newUrl);
    }
  }, [selectedWorkspaceId]);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const searchParams = new URLSearchParams(window.location.search);
      const workspaceParam = searchParams?.get('workspace' as any);
      if (workspaceParam) {
        setSelectedWorkspaceId(workspaceParam);
      }
    }
  }, []);

  const toggleFavorite = async (playbook: Playbook) => {
    try {
      await patchPlaybookFavorite(playbook.playbook_code, !(playbook.user_meta?.favorite || false));
      setSelectedTags((prev) => [...prev]);
    } catch (err) {
      console.error('Failed to toggle favorite:', err);
    }
  };

  const handleExecuteNow = async (event: React.MouseEvent, playbook: Playbook) => {
    event.preventDefault();
    event.stopPropagation();

    if (creatingWorkspace) return;

    try {
      setCreatingWorkspace(playbook.playbook_code);
      let targetWorkspaceId = selectedWorkspaceId;

      if (!targetWorkspaceId) {
        const response = await createWorkspaceForPlaybook(
          buildWorkspaceTitle(playbook.playbook_code),
          playbook.name
        );

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          alert(t('workspaceCreateFailed' as any) + ': ' + (errorData.detail || response.statusText));
          return;
        }

        const newWorkspace = await response.json();
        targetWorkspaceId = newWorkspace.id;
      }

      const registry = getPlaybookRegistry();
      const playbookPackage = registry.get(playbook.playbook_code);

      if (playbookPackage?.uiLayout) {
        router.push(`/workspaces/${targetWorkspaceId}/playbook/${playbook.playbook_code}`);
      } else {
        router.push(`/workspaces/${targetWorkspaceId}`);
      }
    } catch (err) {
      console.error('Failed to create workspace:', err);
      alert(t('workspaceCreateFailed' as any) + ': ' + (err instanceof Error ? err.message : String(err)));
    } finally {
      setCreatingWorkspace(null);
    }
  };

  const handleReload = async () => {
    if (reloading) return;
    try {
      setReloading(true);
      setError(null);

      try {
        const reindexResponse = await reindexPlaybooks();
        if (!reindexResponse.ok) {
          console.warn('Reindex failed, but continuing with reload');
        }
      } catch (reindexErr: any) {
        if (reindexErr.name !== 'AbortError') {
          console.warn('Reindex error, but continuing with reload:', reindexErr);
        }
      }

      await loadPlaybooks();
    } catch (err) {
      console.error('Failed to reload playbooks:', err);
      setError('Failed to reload playbooks. Please try again.');
    } finally {
      setReloading(false);
    }
  };

  const handleTogglePin = async (playbook: Playbook) => {
    if (!selectedWorkspaceId) {
      return;
    }

    const isPinned = playbook.pinned_workspaces?.some((workspace) => workspace.id === selectedWorkspaceId) || false;
    try {
      const response = await togglePinnedPlaybook(selectedWorkspaceId, playbook.playbook_code, isPinned);

      if (response.ok) {
        await loadPlaybooks();
      } else {
        const errorData = await response.json().catch(() => ({}));
        alert(t('pinOperationFailed', {
          action: isPinned ? t('unpin' as any) : t('pin' as any),
          error: errorData.detail || response.statusText,
        }));
      }
    } catch (err) {
      console.error('Failed to toggle pin:', err);
      alert(t('pinOperationFailed', {
        action: isPinned ? t('unpin' as any) : t('pin' as any),
        error: err instanceof Error ? err.message : 'Unknown error',
      }));
    }
  };

  const filteredPlaybooks = useMemo(
    () => filterPlaybooksBySearch(playbooks, searchTerm),
    [playbooks, searchTerm]
  );

  const playbooksByCapability = useMemo(
    () => groupPlaybooksByCapability(filteredPlaybooks),
    [filteredPlaybooks]
  );

  useEffect(() => {
    const capabilityCodesWithPlaybooks = getAvailableCapabilityCodes(playbooksByCapability);
    if (capabilityCodesWithPlaybooks.length > 0 && !capabilityCodesWithPlaybooks.includes(selectedCapability)) {
      setSelectedCapability(capabilityCodesWithPlaybooks[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playbooksByCapability]);

  return (
    <PlaybooksPageView
      locale={locale}
      playbooks={playbooks}
      filteredPlaybooks={filteredPlaybooks}
      playbooksByCapability={playbooksByCapability}
      selectedCapability={selectedCapability}
      onCapabilityChange={setSelectedCapability}
      selectedTags={selectedTags}
      onTagsChange={setSelectedTags}
      selectedWorkspaceId={selectedWorkspaceId}
      onWorkspaceChange={setSelectedWorkspaceId}
      filter={filter}
      onFilterChange={setFilter}
      searchTerm={searchTerm}
      onSearchTermChange={setSearchTerm}
      loading={loading}
      error={error}
      reloading={reloading}
      onReload={handleReload}
      onInstallSuccess={loadPlaybooks}
      supportedTestPlaybooks={supportedTestPlaybooks}
      creatingWorkspace={creatingWorkspace}
      onOpenPlaybook={(playbookCode) => router.push(`/playbooks/${playbookCode}`)}
      onToggleFavorite={toggleFavorite}
      onExecuteNow={handleExecuteNow}
      onTogglePin={handleTogglePin}
      onDiscoverPlaybook={(playbookCode) => router.push(`/playbooks/${playbookCode}`)}
    />
  );
}
