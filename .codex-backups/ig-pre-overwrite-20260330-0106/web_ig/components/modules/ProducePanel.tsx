'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { MindscapeAPIClient } from '@/api/client';
import { CheckCircle2, RefreshCw, Sparkles, Wand2, Recycle, Hash } from 'lucide-react';
import type { IGPost } from '../types';
import HashtagPanel from './HashtagPanel';

type ProduceTab = 'generate' | 'template' | 'reuse' | 'hashtag';

interface ProjectItem {
  id: string;
  title: string;
  type: string;
}

function safeJson(value: any): string {
  try {
    return JSON.stringify(value ?? null, null, 2);
  } catch {
    return String(value ?? '');
  }
}

export default function ProducePanel(props: {
  workspaceId: string;
  apiUrl: string;
  posts: IGPost[];
  selectedPostId: string | null;
  onPostSelect: (postId: string | null) => void;
}) {
  const { workspaceId, apiUrl, posts, selectedPostId, onPostSelect } = props;
  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);

  const selectedPost = useMemo(() => {
    if (!selectedPostId) return null;
    return posts.find((p) => p.id === selectedPostId) || null;
  }, [posts, selectedPostId]);

  const [activeTab, setActiveTab] = useState<ProduceTab>('generate');
  const [loading, setLoading] = useState(false);
  const [selectedProject, setSelectedProject] = useState('');
  const [projects, setProjects] = useState<ProjectItem[]>([]);

  // Fetch projects
  useEffect(() => {
    (async () => {
      try {
        const res = await client.get(`/api/v1/workspaces/${workspaceId}/projects?state=active`);
        if (res.ok) {
          const data = await res.json();
          setProjects(data.projects || data || []);
        }
      } catch { /* ignore */ }
    })();
  }, [workspaceId, client]);

  // Generate (ig_post_generation)
  const [sourceContent, setSourceContent] = useState('');
  const [postCount, setPostCount] = useState(5);
  const [enableImageSearch, setEnableImageSearch] = useState(false);
  const [imageQuery, setImageQuery] = useState('');
  const [genResult, setGenResult] = useState<any | null>(null);
  const [genError, setGenError] = useState<string | null>(null);

  // Template Engine (ig_template_engine)
  const [templateType, setTemplateType] = useState<'carousel' | 'reel' | 'story'>('carousel');
  const [styleTone, setStyleTone] = useState<'high_brand' | 'friendly' | 'coach' | 'sponsored'>('friendly');
  const [purpose, setPurpose] = useState<'save' | 'comment' | 'dm' | 'share'>('save');
  const [generateVariants, setGenerateVariants] = useState(true);
  const [templateSource, setTemplateSource] = useState('');
  const [templateResult, setTemplateResult] = useState<any | null>(null);
  const [templateError, setTemplateError] = useState<string | null>(null);

  // Content Reuse (ig_content_reuse)
  const [reuseAction, setReuseAction] = useState<'article_to_carousel' | 'carousel_to_reel' | 'reel_to_stories'>('article_to_carousel');
  const [targetFolder, setTargetFolder] = useState('generated');
  const [sourcePostPath, setSourcePostPath] = useState('');
  const [carouselPostsText, setCarouselPostsText] = useState('');
  const [sourceReelPath, setSourceReelPath] = useState('');
  const [carouselSlides, setCarouselSlides] = useState<number>(7);
  const [reelDuration, setReelDuration] = useState<number>(30);
  const [storyCount, setStoryCount] = useState<number>(3);
  const [reuseResult, setReuseResult] = useState<any | null>(null);
  const [reuseError, setReuseError] = useState<string | null>(null);

  const runGenerate = async () => {
    const content = (sourceContent || '').trim();
    if (!content) {
      alert('Please input source content');
      return;
    }
    setLoading(true);
    setGenError(null);
    try {
      const response = await client.post(`/api/v1/playbooks/execute`, {
        playbook_code: 'ig_post_generation',
        inputs: {
          workspace_id: workspaceId,
          source_content: content,
          post_count: postCount,
          enable_image_search: enableImageSearch,
          image_query: imageQuery.trim() || undefined,
        },
        execution_mode: 'sync',
      });
      if (!response.ok) {
        const msg = await response.text();
        throw new Error(msg || `Generate failed: ${response.status}`);
      }
      const data = await response.json();
      setGenResult(data.result || data);
    } catch (e) {
      setGenError(e instanceof Error ? e.message : 'Generate failed');
      setGenResult(null);
    } finally {
      setLoading(false);
    }
  };

  const runTemplateEngine = async () => {
    const content = (templateSource || '').trim();
    if (!content) {
      alert('Please input source content');
      return;
    }
    setLoading(true);
    setTemplateError(null);
    try {
      const response = await client.post(`/api/v1/playbooks/execute`, {
        playbook_code: 'ig_template_engine',
        inputs: {
          template_type: templateType,
          style_tone: styleTone,
          purpose,
          source_content: content,
          generate_variants: generateVariants,
        },
        execution_mode: 'sync',
      });
      if (!response.ok) {
        const msg = await response.text();
        throw new Error(msg || `Template engine failed: ${response.status}`);
      }
      const data = await response.json();
      setTemplateResult(data.result || data);
    } catch (e) {
      setTemplateError(e instanceof Error ? e.message : 'Template engine failed');
      setTemplateResult(null);
    } finally {
      setLoading(false);
    }
  };

  const runReuse = async () => {
    const tf = (targetFolder || '').trim();
    if (!tf) {
      alert('Please input target_folder');
      return;
    }

    setLoading(true);
    setReuseError(null);
    try {
      const inputs: any = {
        action: reuseAction,
        workspace_id: workspaceId,
        target_folder: tf,
      };

      if (reuseAction === 'article_to_carousel') {
        inputs.source_post_path = (sourcePostPath || '').trim() || selectedPost?.post_path || undefined;
        inputs.carousel_slides = carouselSlides || undefined;
      } else if (reuseAction === 'carousel_to_reel') {
        const posts = carouselPostsText
          .split('\n')
          .map((s) => s.trim())
          .filter((s) => s.length > 0);
        inputs.carousel_posts = posts.length > 0 ? posts : undefined;
        inputs.reel_duration = reelDuration || undefined;
      } else if (reuseAction === 'reel_to_stories') {
        inputs.source_reel_path = (sourceReelPath || '').trim() || undefined;
        inputs.story_count = storyCount || undefined;
      }

      const response = await client.post(`/api/v1/playbooks/execute`, {
        playbook_code: 'ig_content_reuse',
        inputs,
        execution_mode: 'sync',
      });
      if (!response.ok) {
        const msg = await response.text();
        throw new Error(msg || `Content reuse failed: ${response.status}`);
      }
      const data = await response.json();
      setReuseResult(data.result || data);
    } catch (e) {
      setReuseError(e instanceof Error ? e.message : 'Content reuse failed');
      setReuseResult(null);
    } finally {
      setLoading(false);
    }
  };

  const tabBtn = (id: ProduceTab, label: string, Icon: any) => {
    const active = activeTab === id;
    return (
      <button
        key={id}
        onClick={() => setActiveTab(id)}
        className={`px-3 py-2 text-xs rounded flex items-center gap-2 border ${active
            ? 'bg-blue-600 text-white border-blue-600'
            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700'
          }`}
      >
        <Icon className="w-4 h-4" />
        {label}
      </button>
    );
  };

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-green-600 dark:text-green-400" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Produce</h2>
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400">
          {selectedPost?.post_path ? `Selected: ${selectedPost.post_path}` : 'No post selected'}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 mb-3">
        {tabBtn('generate', 'Generate', Wand2)}
        {tabBtn('template', 'Template', Sparkles)}
        {tabBtn('reuse', 'Reuse', Recycle)}
        {tabBtn('hashtag', 'Hashtag', Hash)}
      </div>

      {/* Project selector */}
      {projects.length > 0 && (
        <div className="mb-3">
          <select
            value={selectedProject}
            onChange={(e) => setSelectedProject(e.target.value)}
            className="w-full text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded px-2 py-1.5"
          >
            <option value="">No project (standalone)</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.title}</option>
            ))}
          </select>
        </div>
      )}

      {activeTab === 'generate' && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3 space-y-3">
          <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">IG Post Generation</div>
          <div className="grid grid-cols-1 gap-2">
            <textarea
              value={sourceContent}
              onChange={(e) => setSourceContent(e.target.value)}
              rows={6}
              className="w-full px-3 py-2 text-sm border rounded dark:bg-gray-800 dark:border-gray-700"
              placeholder="Paste source content..."
            />
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <div>
                <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">post_count</div>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={postCount}
                  onChange={(e) => setPostCount(Number(e.target.value || 0))}
                  className="w-full px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
                />
              </div>
              <div>
                <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">image_query</div>
                <input
                  type="text"
                  value={imageQuery}
                  onChange={(e) => setImageQuery(e.target.value)}
                  className="w-full px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
                  placeholder="optional"
                />
              </div>
              <label className="flex items-center gap-2 text-xs text-gray-700 dark:text-gray-200 mt-5">
                <input
                  type="checkbox"
                  checked={enableImageSearch}
                  onChange={(e) => setEnableImageSearch(e.target.checked)}
                  className="rounded"
                />
                enable_image_search
              </label>
            </div>
            <button
              onClick={() => void runGenerate()}
              disabled={loading}
              className="w-full px-3 py-2 text-sm rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Generate
            </button>
          </div>

          {genError && <div className="text-xs text-red-600 dark:text-red-400 whitespace-pre-wrap">{genError}</div>}
          {genResult && (
            <details className="text-xs" open>
              <summary className="cursor-pointer text-gray-700 dark:text-gray-200 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-green-600 dark:text-green-400" />
                Result
              </summary>
              <pre className="mt-2 bg-gray-100 dark:bg-gray-900 rounded p-2 overflow-x-auto whitespace-pre-wrap">{safeJson(genResult)}</pre>
            </details>
          )}
        </div>
      )}

      {activeTab === 'template' && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3 space-y-3">
          <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">Template Engine</div>

          <div className="grid grid-cols-1 sm:grid-cols-4 gap-2">
            <div>
              <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">template_type</div>
              <select
                value={templateType}
                onChange={(e) => setTemplateType(e.target.value as any)}
                className="w-full px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
              >
                <option value="carousel">carousel</option>
                <option value="reel">reel</option>
                <option value="story">story</option>
              </select>
            </div>
            <div>
              <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">style_tone</div>
              <select
                value={styleTone}
                onChange={(e) => setStyleTone(e.target.value as any)}
                className="w-full px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
              >
                <option value="high_brand">high_brand</option>
                <option value="friendly">friendly</option>
                <option value="coach">coach</option>
                <option value="sponsored">sponsored</option>
              </select>
            </div>
            <div>
              <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">purpose</div>
              <select
                value={purpose}
                onChange={(e) => setPurpose(e.target.value as any)}
                className="w-full px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
              >
                <option value="save">save</option>
                <option value="comment">comment</option>
                <option value="dm">dm</option>
                <option value="share">share</option>
              </select>
            </div>
            <label className="flex items-center gap-2 text-xs text-gray-700 dark:text-gray-200 mt-5">
              <input
                type="checkbox"
                checked={generateVariants}
                onChange={(e) => setGenerateVariants(e.target.checked)}
                className="rounded"
              />
              generate_variants
            </label>
          </div>

          <textarea
            value={templateSource}
            onChange={(e) => setTemplateSource(e.target.value)}
            rows={6}
            className="w-full px-3 py-2 text-sm border rounded dark:bg-gray-800 dark:border-gray-700"
            placeholder="Paste source content..."
          />

          <button
            onClick={() => void runTemplateEngine()}
            disabled={loading}
            className="w-full px-3 py-2 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Apply Template
          </button>

          {templateError && <div className="text-xs text-red-600 dark:text-red-400 whitespace-pre-wrap">{templateError}</div>}
          {templateResult && (
            <details className="text-xs" open>
              <summary className="cursor-pointer text-gray-700 dark:text-gray-200 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-green-600 dark:text-green-400" />
                Result
              </summary>
              <pre className="mt-2 bg-gray-100 dark:bg-gray-900 rounded p-2 overflow-x-auto whitespace-pre-wrap">{safeJson(templateResult)}</pre>
            </details>
          )}
        </div>
      )}

      {activeTab === 'reuse' && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3 space-y-3">
          <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">Content Reuse</div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">action</div>
              <select
                value={reuseAction}
                onChange={(e) => setReuseAction(e.target.value as any)}
                className="w-full px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
              >
                <option value="article_to_carousel">article_to_carousel</option>
                <option value="carousel_to_reel">carousel_to_reel</option>
                <option value="reel_to_stories">reel_to_stories</option>
              </select>
            </div>
            <div>
              <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">target_folder *</div>
              <input
                type="text"
                value={targetFolder}
                onChange={(e) => setTargetFolder(e.target.value)}
                className="w-full px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
              />
            </div>
          </div>

          {reuseAction === 'article_to_carousel' && (
            <div className="grid grid-cols-1 gap-2">
              <div>
                <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">source_post_path (optional)</div>
                <input
                  type="text"
                  value={sourcePostPath}
                  onChange={(e) => setSourcePostPath(e.target.value)}
                  className="w-full px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
                  placeholder={selectedPost?.post_path || 'path/to/post.md'}
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">carousel_slides</div>
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={carouselSlides}
                    onChange={(e) => setCarouselSlides(Number(e.target.value || 0))}
                    className="w-full px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
                  />
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400 flex items-end">
                  If empty, will use selected post path when available.
                </div>
              </div>
            </div>
          )}

          {reuseAction === 'carousel_to_reel' && (
            <div className="grid grid-cols-1 gap-2">
              <div>
                <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">carousel_posts (one path per line)</div>
                <textarea
                  value={carouselPostsText}
                  onChange={(e) => setCarouselPostsText(e.target.value)}
                  rows={4}
                  className="w-full px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
                  placeholder="path/to/carousel1.md\npath/to/carousel2.md"
                />
              </div>
              <div>
                <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">reel_duration (seconds)</div>
                <input
                  type="number"
                  min={5}
                  max={300}
                  value={reelDuration}
                  onChange={(e) => setReelDuration(Number(e.target.value || 0))}
                  className="w-full px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
                />
              </div>
            </div>
          )}

          {reuseAction === 'reel_to_stories' && (
            <div className="grid grid-cols-1 gap-2">
              <div>
                <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">source_reel_path *</div>
                <input
                  type="text"
                  value={sourceReelPath}
                  onChange={(e) => setSourceReelPath(e.target.value)}
                  className="w-full px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
                  placeholder="path/to/reel.md"
                />
              </div>
              <div>
                <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">story_count</div>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={storyCount}
                  onChange={(e) => setStoryCount(Number(e.target.value || 0))}
                  className="w-full px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
                />
              </div>
            </div>
          )}

          <button
            onClick={() => void runReuse()}
            disabled={loading}
            className="w-full px-3 py-2 text-sm rounded bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50 flex items-center justify-center gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Run
          </button>

          {reuseError && <div className="text-xs text-red-600 dark:text-red-400 whitespace-pre-wrap">{reuseError}</div>}
          {reuseResult && (
            <details className="text-xs" open>
              <summary className="cursor-pointer text-gray-700 dark:text-gray-200 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-green-600 dark:text-green-400" />
                Result
              </summary>
              <pre className="mt-2 bg-gray-100 dark:bg-gray-900 rounded p-2 overflow-x-auto whitespace-pre-wrap">{safeJson(reuseResult)}</pre>
            </details>
          )}
        </div>
      )}

      {activeTab === 'hashtag' && (
        <HashtagPanel workspaceId={workspaceId} apiUrl={apiUrl} />
      )}
    </div>
  );
}

