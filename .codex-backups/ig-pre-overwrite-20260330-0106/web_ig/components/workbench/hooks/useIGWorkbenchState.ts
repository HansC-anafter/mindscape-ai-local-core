import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getApiBaseUrl } from '@/lib/api-url';

import type { IGPost, WorkbenchContext, PostStatus } from '../../types';
import type { PostStatusCount, WorkbenchModuleType, WorkbenchViewMode } from '../types';
import type { RunLogCounts } from '../components/WorkbenchExecutionPanel/types';
import { injectWorkspaceIGBrowserProfileInputs } from '../../browserProfile';
import { hasIGRefreshHint, useIGWorkspaceEvents } from '../../hooks/useIGWorkspaceEvents';

const POST_BOUND_MODULES = new Set<WorkbenchModuleType | null>([
  'plan',
  'produce',
  'assets',
  'review',
  'export',
  'publish',
  'measure',
]);

function isLikelyPostArtifact(artifact: any): boolean {
  const metadata = artifact?.metadata || {};
  const artifactType = (artifact?.artifact_type || '').toString().toLowerCase();
  if (artifactType === 'post') return true;
  if (typeof metadata.post_path === 'string' && metadata.post_path.trim()) return true;
  if (
    metadata.frontmatter &&
    typeof metadata.frontmatter === 'object' &&
    (typeof metadata.frontmatter.caption === 'string' ||
      typeof metadata.frontmatter.media_path === 'string')
  ) {
    return true;
  }
  return false;
}

export function useIGWorkbenchState(params: { workspaceId: string; apiUrl?: string }) {
  const { workspaceId, apiUrl } = params;

  const [activeModule, setActiveModule] = useState<WorkbenchModuleType | null>(null);
  const [viewMode, setViewMode] = useState<WorkbenchViewMode>('grid');
  const [statusFilter, setStatusFilter] = useState<PostStatus | 'all'>('all');
  const [selectedPostId, setSelectedPostId] = useState<string | null>(null);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);

  const [posts, setPosts] = useState<IGPost[]>([]);
  const [postsLoading, setPostsLoading] = useState(false);
  const [statusCounts, setStatusCounts] = useState<PostStatusCount>({
    draft: 0,
    review: 0,
    ready: 0,
    scheduled: 0,
    published: 0,
    measured: 0,
    archived: 0,
  });
  const [recentRuns, setRecentRuns] = useState<any[]>([]);
  const [recentGroups, setRecentGroups] = useState<any[]>([]);
  const [runLogCounts, setRunLogCounts] = useState<RunLogCounts>({
    total: 0,
    completed: 0,
    running: 0,
    pending: 0,
    failed: 0,
  });
  const [targetsTotal, setTargetsTotal] = useState<number | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recentRunsInFlightRef = useRef(false);
  const lastRecentRunsFetchAtRef = useRef(0);
  const targetsTotalInFlightRef = useRef(false);
  const lastTargetsTotalFetchAtRef = useRef(0);
  const lifecycleRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const postsLoadedOnceRef = useRef(false);
  const postsAbortControllerRef = useRef<AbortController | null>(null);

  const baseApiUrl = apiUrl || getApiBaseUrl();

  const getSelectedPost = (): IGPost | null => {
    if (!selectedPostId) return null;
    return posts.find((p) => p.id === selectedPostId) || null;
  };

  const loadPosts = useCallback(async () => {
    postsAbortControllerRef.current?.abort();
    const controller = new AbortController();
    postsAbortControllerRef.current = controller;
    setPostsLoading(true);
    try {
      const postArtifactsResponse = await fetch(
        `${baseApiUrl}/api/v1/workspaces/${workspaceId}/artifacts?playbook_code=ig_post_generation&include_content=true&include_preview=false&limit=200`,
        {
          headers: { 'Content-Type': 'application/json' },
          signal: controller.signal,
        }
      );
      if (!postArtifactsResponse.ok) {
        throw new Error(`Failed to load posts: ${postArtifactsResponse.statusText}`);
      }
      const postArtifactsData = await postArtifactsResponse.json();
      let summaryArtifacts = postArtifactsData.artifacts || [];

      // Backward-compatible fallback for older data where posts may not be tagged
      // with ig_post_generation playbook code.
      if (!Array.isArray(summaryArtifacts) || summaryArtifacts.length === 0) {
        const fallbackResponse = await fetch(
          `${baseApiUrl}/api/v1/workspaces/${workspaceId}/artifacts?platform=instagram&include_content=true&include_preview=false&limit=100`,
          {
            headers: { 'Content-Type': 'application/json' },
            signal: controller.signal,
          }
        );
        if (!fallbackResponse.ok) {
          throw new Error(`Failed to load posts: ${fallbackResponse.statusText}`);
        }
        const fallbackData = await fallbackResponse.json();
        summaryArtifacts = (fallbackData.artifacts || []).filter((artifact: any) => isLikelyPostArtifact(artifact));
      }

      const igPosts: IGPost[] = [];

      summaryArtifacts.forEach((artifact: any) => {
        const metadata = artifact.metadata || {};

        let contentItems: any[] = [];
        if (Array.isArray(artifact.content?.content)) {
          contentItems = artifact.content.content;
        } else if (artifact.content?.content) {
          contentItems = [artifact.content.content];
        } else if (artifact.content) {
          contentItems = [artifact.content];
        }

        if (contentItems.length === 0) {
          contentItems = [{}];
        }

        contentItems.forEach((content: any, index: number) => {
          const post_path = metadata.post_path || artifact.storage_path;
          if (!post_path && contentItems.length === 1 && !content.text && !content.caption) {
            return;
          }
          const final_post_path = post_path || (artifact.storage_path ? `${artifact.storage_path}${index > 0 ? `_${index}` : ''}` : undefined);

          igPosts.push({
            id: contentItems.length > 1 ? `${artifact.id}_${index}` : artifact.id,
            artifact_id: artifact.id,
            execution_id: artifact.execution_id,
            text: typeof content.text === 'string' ? content.text :
              typeof content.caption === 'string' ? content.caption :
                typeof content.content === 'string' ? content.content : '',
            hashtags: content.hashtags || metadata.hashtags || [],
            status: (metadata.status || content.status || 'draft') as PostStatus,
            platform: 'instagram',
            created_at: artifact.created_at || new Date().toISOString(),
            updated_at: artifact.updated_at || artifact.created_at || new Date().toISOString(),
            series_id: metadata.series_id || content.series_id,
            images: content.images || content.image_urls || (content.image_url ? [content.image_url] : []),
            post_path: final_post_path,
            post_id: metadata.post_id || content.post_id || artifact.id,
            frontmatter: {
              ...metadata,
              ...(metadata.frontmatter || {}),
              ...(content.frontmatter || {}),
              media_path: metadata.media_path || content.media_path || metadata.image_path || metadata.image_url || content.image_url,
              caption: metadata.caption || content.caption || content.text,
              hashtags: metadata.hashtags || content.hashtags || [],
            },
            content: typeof content.text === 'string' ? content.text :
              typeof content.caption === 'string' ? content.caption :
                typeof content.content === 'string' ? content.content : '',
          });
        });
      });

      setPosts(igPosts);
      postsLoadedOnceRef.current = true;
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        return;
      }
      console.error('Failed to load posts:', err);
    } finally {
      if (postsAbortControllerRef.current === controller) {
        postsAbortControllerRef.current = null;
        setPostsLoading(false);
      }
    }
  }, [baseApiUrl, workspaceId]);

  const calculateStatusCounts = () => {
    const counts: PostStatusCount = {
      draft: 0,
      review: 0,
      ready: 0,
      scheduled: 0,
      published: 0,
      measured: 0,
      archived: 0,
    };

    posts.forEach((post) => {
      const status = post.status || 'draft';
      if (status in counts) {
        counts[status as PostStatus]++;
      }
    });

    setStatusCounts(counts);
  };

  const fetchRecentRuns = useCallback(async (force = false) => {
    const now = Date.now();
    if (!force && now - lastRecentRunsFetchAtRef.current < 4000) {
      return;
    }
    if (recentRunsInFlightRef.current) {
      return;
    }

    recentRunsInFlightRef.current = true;
    try {
      const response = await fetch(
        `${baseApiUrl}/api/v1/ig/workbench/sidebar-summary?workspace_id=${workspaceId}&active_limit=100`,
        {
          headers: { 'Content-Type': 'application/json' },
        }
      );
      if (response.ok) {
        const data = await response.json();
        const nextRuns = Array.isArray(data.active_executions) ? data.active_executions : [];
        const nextCounts: RunLogCounts = {
          total: Number(data?.counts?.total || 0),
          completed: Number(data?.counts?.completed || 0),
          running: Number(data?.counts?.running || 0),
          pending: Number(data?.counts?.pending || 0),
          failed: Number(data?.counts?.failed || 0),
        };

        setRecentGroups([]);
        setRecentRuns((prev) => {
          if (prev.length !== nextRuns.length) return nextRuns;
          const unchanged = prev.every((run, index) => {
            const next = nextRuns[index];
            if (!next) return false;
            return (
              (run?.id || run?.execution_id || '') === (next?.id || next?.execution_id || '') &&
              (run?.status || '') === (next?.status || '') &&
              (run?.playbook_code || '') === (next?.playbook_code || '') &&
              (run?.updated_at || '') === (next?.updated_at || '') &&
              (run?.started_at || '') === (next?.started_at || '') &&
              (run?.created_at || '') === (next?.created_at || '') &&
              JSON.stringify(run?.execution_context || {}) === JSON.stringify(next?.execution_context || {})
            );
          });
          return unchanged ? prev : nextRuns;
        });
        setRunLogCounts((prev) => (
          prev.total === nextCounts.total &&
          prev.completed === nextCounts.completed &&
          prev.running === nextCounts.running &&
          prev.pending === nextCounts.pending &&
          prev.failed === nextCounts.failed
        ) ? prev : nextCounts);
      }
    } catch (err) {
      console.error('Failed to load recent runs:', err);
    } finally {
      recentRunsInFlightRef.current = false;
      lastRecentRunsFetchAtRef.current = Date.now();
    }
  }, [baseApiUrl, workspaceId]);

  const loadRecentRuns = useCallback(async () => {
    await fetchRecentRuns(false);
  }, [fetchRecentRuns]);

  const fetchTargetsTotal = useCallback(async (force = false) => {
    const now = Date.now();
    if (!force && now - lastTargetsTotalFetchAtRef.current < 15000) {
      return;
    }
    if (targetsTotalInFlightRef.current) {
      return;
    }

    targetsTotalInFlightRef.current = true;
    try {
      const response = await fetch(
        `${baseApiUrl}/api/v1/ig/workbench/sidebar-targets-total?workspace_id=${workspaceId}`,
        {
          headers: { 'Content-Type': 'application/json' },
        }
      );
      if (response.ok) {
        const data = await response.json();
        const nextTotal = Number(data?.total ?? 0);
        setTargetsTotal((prev) => (prev === nextTotal ? prev : nextTotal));
      }
    } catch (err) {
      console.error('Failed to load sidebar targets total:', err);
    } finally {
      targetsTotalInFlightRef.current = false;
      lastTargetsTotalFetchAtRef.current = Date.now();
    }
  }, [baseApiUrl, workspaceId]);

  const scheduleRecentRunsRefresh = useCallback((force = true) => {
    if (lifecycleRefreshTimerRef.current) {
      clearTimeout(lifecycleRefreshTimerRef.current);
    }
    lifecycleRefreshTimerRef.current = setTimeout(() => {
      void fetchRecentRuns(force);
      void fetchTargetsTotal(false);
    }, 1500);
  }, [fetchRecentRuns, fetchTargetsTotal]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void fetchTargetsTotal(false);
    }, 1800);
    return () => window.clearTimeout(timer);
  }, [fetchTargetsTotal, workspaceId]);

  useEffect(() => {
    if (POST_BOUND_MODULES.has(activeModule)) {
      if (postsLoading) return;
      if (postsLoadedOnceRef.current) return;
      void loadPosts();
      return;
    }

    if (activeModule !== null) {
      postsAbortControllerRef.current?.abort();
      postsAbortControllerRef.current = null;
      setPostsLoading(false);
      return;
    }

    if (postsLoading) return;
    if (postsLoadedOnceRef.current) return;

    const timer = window.setTimeout(() => {
      void loadPosts();
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [activeModule, loadPosts, postsLoading]);

  useEffect(() => () => {
    postsAbortControllerRef.current?.abort();
    postsAbortControllerRef.current = null;
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void fetchRecentRuns(true);
    }, 900);
    return () => window.clearTimeout(timer);
  }, [fetchRecentRuns]);

  useEffect(() => () => {
    if (lifecycleRefreshTimerRef.current) {
      clearTimeout(lifecycleRefreshTimerRef.current);
      lifecycleRefreshTimerRef.current = null;
    }
  }, []);

  useIGWorkspaceEvents({
    workspaceId,
    apiUrl: baseApiUrl,
    onEvent: (_event, metadata) => {
      if (!hasIGRefreshHint(metadata, 'run_logs')) return;
      scheduleRecentRunsRefresh(true);
    },
  });

  const hasRunningRuns = useMemo(() => {
    return (recentRuns || []).some((run) => {
      const status = ((run?.status || run?.task?.status || '') as string).toLowerCase();
      return status === 'running' || status === 'queued' || status === 'paused';
    });
  }, [recentRuns]);

  const hasActiveOrPendingRuns = useMemo(() => {
    return (recentRuns || []).some((run) => {
      const status = ((run?.status || run?.task?.status || '') as string).toLowerCase();
      return status === 'running' || status === 'queued' || status === 'paused' || status === 'pending';
    });
  }, [recentRuns]);

  useEffect(() => {
    if (!hasActiveOrPendingRuns) return;
    // Workspace lifecycle events are now the primary refresh trigger.
    // This interval is only a safety net for missed events / stale tabs.
    const intervalMs = hasRunningRuns ? 15000 : 60000;
    const interval = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      void fetchRecentRuns(false);
    }, intervalMs);
    return () => clearInterval(interval);
  }, [hasActiveOrPendingRuns, hasRunningRuns, fetchRecentRuns]);

  useEffect(() => {
    if (!hasActiveOrPendingRuns) return;

    const handleVisibilityResume = () => {
      if (typeof document !== 'undefined' && document.hidden) return;
      void fetchRecentRuns(true);
    };

    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', handleVisibilityResume);
    }
    if (typeof window !== 'undefined') {
      window.addEventListener('focus', handleVisibilityResume);
    }

    return () => {
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', handleVisibilityResume);
      }
      if (typeof window !== 'undefined') {
        window.removeEventListener('focus', handleVisibilityResume);
      }
    };
  }, [hasActiveOrPendingRuns, fetchRecentRuns]);

  useEffect(() => {
    calculateStatusCounts();
  }, [posts]);

  const workbenchContext: WorkbenchContext = {
    workspace_id: workspaceId,
    activeModule,
    viewMode,
    statusFilter,
    selectedPostId,
    selectedSeriesId: null,
    selectedAccountId: selectedAccountId,
    selectionScope: selectedPostId ? 'single' : 'filtered',
  };

  const buildPlaybookInputs = (
    playbookCode: string,
    additionalInputs?: Record<string, any>
  ): Record<string, any> => {
    const baseInputs = injectWorkspaceIGBrowserProfileInputs(workspaceId, {
      workspace_id: workbenchContext.workspace_id,
    });

    switch (playbookCode) {
      case 'ig_content_checker':
      case 'ig_frontmatter_validator':
      case 'ig_export_pack_generator': {
        const post = getSelectedPost();
        if (!post) {
          throw new Error('No post selected');
        }
        if (!post.post_path) {
          throw new Error(`Post ${post.id} missing post_path. Cannot execute ${playbookCode}.`);
        }
        return {
          ...baseInputs,
          post_path: post.post_path,
          post_id: post.post_id || post.artifact_id,
          ...additionalInputs,
        };
      }

      case 'ig_publish_content': {
        const post = getSelectedPost();
        if (!post) {
          throw new Error('No post selected');
        }
        const frontmatter = post.frontmatter || {};
        const media_path = frontmatter.media_path || frontmatter.image_path || frontmatter.image_url;
        const caption = frontmatter.caption || post.content || post.text || '';

        if (!additionalInputs?.channel_config_id) {
          throw new Error('channel_config_id is required. Account selection feature will be implemented in Phase 3.');
        }

        if (!media_path) {
          throw new Error(`Post ${post.id} missing media_path`);
        }

        if (!caption) {
          throw new Error(`Post ${post.id} missing caption`);
        }

        return {
          ...baseInputs,
          channel_config_id: additionalInputs.channel_config_id,
          media_path: media_path,
          caption: caption,
          post_id: post.post_id || post.artifact_id,
          ...additionalInputs,
        };
      }

      default:
        return { ...baseInputs, ...additionalInputs };
    }
  };

  const handleRunPlaybook = async (playbookCode: string, additionalInputs?: any) => {
    setIsRunning(true);
    try {
      const inputs = buildPlaybookInputs(playbookCode, additionalInputs);

      const response = await fetch(
        `${baseApiUrl}/api/v1/playbooks/execute`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            playbook_code: playbookCode,
            inputs: inputs,
            execution_mode: 'async',
          }),
        }
      );

      if (response.ok) {
        const data = await response.json();
        setError(null);
        loadRecentRuns();
        await loadPosts();
        // Immediately notify sidebar so it can pin the status card + connect SSE.
        try {
          const execId = (data?.execution_id || '').toString();
          if (execId && typeof window !== 'undefined') {
            window.dispatchEvent(
              new CustomEvent('mindscape:execution_started', {
                detail: {
                  workspaceId,
                  executionId: execId,
                  playbookCode,
                  startedAt: new Date().toISOString(),
                },
              })
            );
          }
        } catch {
          // ignore
        }
        return { success: true, execution_id: data.execution_id };
      } else {
        const errorData = await response.json();
        const errorMsg = errorData.detail || 'Unknown error';
        setError(errorMsg);
        return { success: false, error: errorMsg };
      }
    } catch (err) {
      let errorMsg = 'Unknown error';
      if (err instanceof Error) {
        errorMsg = err.message;
      }
      setError(errorMsg);
      return { success: false, error: errorMsg };
    } finally {
      setIsRunning(false);
    }
  };

  const statusButtons = useMemo(() => {
    return [
      { id: 'all', label: 'All', count: Object.values(statusCounts).reduce((a, b) => a + b, 0) },
      { id: 'draft', label: 'Draft', count: statusCounts.draft },
      { id: 'review', label: 'Review', count: statusCounts.review },
      { id: 'ready', label: 'Ready', count: statusCounts.ready },
      { id: 'scheduled', label: 'Scheduled', count: statusCounts.scheduled },
      { id: 'published', label: 'Published', count: statusCounts.published },
      { id: 'measured', label: 'Measured', count: statusCounts.measured },
    ];
  }, [statusCounts]);

  return {
    baseApiUrl,

    activeModule,
    setActiveModule,
    viewMode,
    setViewMode,
    statusFilter,
    setStatusFilter,
    selectedPostId,
    setSelectedPostId,
    selectedAccountId,
    setSelectedAccountId,

    posts,
    postsLoading,
    statusCounts,
    statusButtons,
    runLogCounts,
    targetsTotal,
    recentRuns,
    recentGroups,
    isRunning,
    error,
    setError,

    loadPosts,
    loadRecentRuns,
    getSelectedPost,
    handleRunPlaybook,
  };
}
