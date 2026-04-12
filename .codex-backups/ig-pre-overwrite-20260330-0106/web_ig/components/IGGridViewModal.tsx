'use client';

import React, { useState, useEffect } from 'react';
import { BaseModal } from '@/components/BaseModal';
import { getApiBaseUrl } from '@/lib/api-url';
import IGGridView from './IGGridView';
import IGTimelineView from './IGTimelineView';
import type { IGPost } from './types';

interface IGGridViewModalProps {
  isOpen: boolean;
  onClose: () => void;
  workspaceId: string;
}

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

function normalizeContentItems(artifact: any): any[] {
  if (Array.isArray(artifact?.content?.content)) return artifact.content.content;
  if (artifact?.content?.content) return [artifact.content.content];
  if (artifact?.content) return [artifact.content];
  return [{}];
}

function collectImages(content: any, metadata: any): string[] {
  const values: string[] = [];

  const append = (v: any) => {
    if (typeof v === 'string' && v.trim()) values.push(v);
  };
  const appendList = (v: any) => {
    if (Array.isArray(v)) v.forEach(append);
  };

  appendList(content?.images);
  appendList(content?.image_urls);
  append(content?.image_url);
  append(content?.photo_url);

  appendList(metadata?.images);

  const frontmatter = metadata?.frontmatter || {};
  append(frontmatter?.image_url);
  append(frontmatter?.image_path);
  append(frontmatter?.media_path);

  return Array.from(new Set(values));
}

function mapArtifactToPosts(artifact: any): IGPost[] {
  const metadata = artifact?.metadata || {};
  const contentItems = normalizeContentItems(artifact);
  const isMulti = Array.isArray(artifact?.content?.content);

  return contentItems
    .map((content: any, index: number) => {
      const postPath = metadata.post_path || artifact.storage_path;
      const finalPostPath =
        postPath ||
        (artifact.storage_path
          ? `${artifact.storage_path}${index > 0 ? `_${index}` : ''}`
          : undefined);
      const text =
        typeof content?.text === 'string'
          ? content.text
          : typeof content?.caption === 'string'
          ? content.caption
          : typeof content?.content === 'string'
          ? content.content
          : typeof artifact?.content_preview === 'string'
          ? artifact.content_preview
          : typeof artifact?.description === 'string'
          ? artifact.description
          : '';
      const hashtags = Array.isArray(content?.hashtags)
        ? content.hashtags
        : Array.isArray(metadata?.hashtags)
        ? metadata.hashtags
        : [];
      if (!finalPostPath && !text && hashtags.length === 0) return null;

      const postId = isMulti ? `${artifact.id}-${index}` : artifact.id;
      return {
        id: postId,
        artifact_id: artifact.id,
        execution_id: artifact.execution_id,
        text,
        hashtags,
        images: collectImages(content, metadata),
        status: metadata?.status || content?.status || 'draft',
        platform: artifact.platform || metadata?.platform || 'instagram',
        created_at: artifact.created_at,
        updated_at: artifact.updated_at,
        series_id: metadata?.series_id || content?.series_id,
        arc_id: metadata?.arc_id,
        scheduled_time: metadata?.scheduled_time,
        narrative_phase: metadata?.narrative_phase,
        emotion: metadata?.emotion,
      } satisfies IGPost;
    })
    .filter(Boolean) as IGPost[];
}

export default function IGGridViewModal({
  isOpen,
  onClose,
  workspaceId,
}: IGGridViewModalProps) {
  const [viewMode, setViewMode] = useState<'grid' | 'timeline'>('grid');
  const [posts, setPosts] = useState<IGPost[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadPosts();
    }
  }, [isOpen, workspaceId]);

  async function loadPosts() {
    setLoading(true);
    setError(null);
    try {
      const apiBaseUrl = getApiBaseUrl();

      // 1) Load lightweight post summaries first.
      const summaryResponse = await fetch(
        `${apiBaseUrl}/api/v1/workspaces/${workspaceId}/artifacts?playbook_code=ig_post_generation&include_content=false&include_preview=false&limit=200`,
        {
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );
      if (!summaryResponse.ok) {
        throw new Error(`Failed to load posts: ${summaryResponse.statusText}`);
      }

      const summaryData = await summaryResponse.json();
      let summaryArtifacts = summaryData.artifacts || [];

      // Backward-compatible fallback: older workspaces may not have playbook_code on posts.
      if (!Array.isArray(summaryArtifacts) || summaryArtifacts.length === 0) {
        const fallbackResponse = await fetch(
          `${apiBaseUrl}/api/v1/workspaces/${workspaceId}/artifacts?platform=instagram&include_content=false&include_preview=false&limit=100`,
          {
            headers: {
              'Content-Type': 'application/json',
            },
          }
        );
        if (!fallbackResponse.ok) {
          throw new Error(`Failed to load posts: ${fallbackResponse.statusText}`);
        }
        const fallbackData = await fallbackResponse.json();
        summaryArtifacts = (fallbackData.artifacts || []).filter((a: any) =>
          isLikelyPostArtifact(a)
        );
      }

      // 2) Load full content only for post candidates.
      const detailedArtifacts = await Promise.all(
        summaryArtifacts.map(async (artifact: any) => {
          const artifactId = artifact?.id;
          if (!artifactId) return artifact;
          try {
            const detailResponse = await fetch(
              `${apiBaseUrl}/api/v1/artifacts/${artifactId}?include_content=true&include_preview=false`,
              {
                headers: {
                  'Content-Type': 'application/json',
                },
              }
            );
            if (!detailResponse.ok) return artifact;
            return await detailResponse.json();
          } catch {
            return artifact;
          }
        })
      );

      const igPosts = detailedArtifacts.flatMap((artifact: any) => mapArtifactToPosts(artifact));
      setPosts(igPosts);
    } catch (err) {
      console.error('Failed to load posts:', err);
      setError(err instanceof Error ? err.message : 'Failed to load posts');
    } finally {
      setLoading(false);
    }
  }

  async function handleSchedule(postId: string, scheduledTime: string) {
    try {
      // TODO: If scheduling requires cloud services, Local-Core backend should provide
      // a proxy endpoint. For now, we'll update the artifact metadata via Local-Core API.
      const apiBaseUrl = getApiBaseUrl();

      // Prefer mapped artifact_id to avoid truncating UUID-like post IDs.
      const matchedPost = posts.find((p) => p.id === postId);
      const artifactId = matchedPost?.artifact_id || postId;

      // Update artifact metadata with scheduled_time
      const response = await fetch(
        `${apiBaseUrl}/api/v1/workspaces/${workspaceId}/artifacts/${artifactId}`,
        {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            metadata: {
              scheduled_time: scheduledTime,
            },
          }),
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to schedule post: ${response.statusText}`);
      }

      await loadPosts();
    } catch (err) {
      console.error('Failed to schedule post:', err);
      setError(err instanceof Error ? err.message : 'Failed to schedule post');
    }
  }

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      title="Instagram Posts"
      maxWidth="max-w-7xl"
    >
      <div className="h-[85vh] flex flex-col">
        {/* View mode toggle */}
        <div className="flex gap-2 p-4 border-b dark:border-gray-700">
          <button
            onClick={() => setViewMode('grid')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              viewMode === 'grid'
                ? 'bg-accent dark:bg-blue-600 text-white'
                : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
            }`}
          >
            Grid View
          </button>
          <button
            onClick={() => setViewMode('timeline')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              viewMode === 'timeline'
                ? 'bg-accent dark:bg-blue-600 text-white'
                : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
            }`}
          >
            Timeline View
          </button>
        </div>

        {/* View content */}
        <div className="flex-1 overflow-hidden">
          {loading && (
            <div className="flex items-center justify-center h-full">
              <div className="text-gray-500 dark:text-gray-400">Loading posts...</div>
            </div>
          )}
          {error && (
            <div className="flex items-center justify-center h-full">
              <div className="text-red-500 dark:text-red-400">Error: {error}</div>
            </div>
          )}
          {!loading && !error && viewMode === 'grid' && (
            <IGGridView posts={posts} onRefresh={loadPosts} />
          )}
          {!loading && !error && viewMode === 'timeline' && (
            <IGTimelineView posts={posts} onSchedule={handleSchedule} />
          )}
        </div>
      </div>
    </BaseModal>
  );
}
