import React, { useEffect, useState } from 'react';
import { FileText, Hash, Loader2, RefreshCw, CheckCircle } from 'lucide-react';

import type { PostAnalysis } from '../../insightsApi';
import { createInsightsApi } from '../../insightsApi';
import { getPostThumbnailUrl, getProxiedImageUrl } from '../../utils';

interface ContentAnalysisPanelProps {
    workspaceId: string;
    apiUrl: string;
    seed?: string;
    handle?: string;
    onRunPlaybook?: (playbookCode: string, params: Record<string, unknown>) => void;
}

export function ContentAnalysisPanel({ workspaceId, apiUrl, seed, handle, onRunPlaybook }: ContentAnalysisPanelProps) {
    const [posts, setPosts] = useState<PostAnalysis[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [topicFilter, setTopicFilter] = useState('');
    const [postsCount, setPostsCount] = useState(9);
    const [analyzing, setAnalyzing] = useState(false);
    const [analyzeStatus, setAnalyzeStatus] = useState<'idle' | 'launched'>('idle');
    const [failedPostThumbnails, setFailedPostThumbnails] = useState<Record<string, true>>({});

    const api = createInsightsApi(apiUrl);

    const loadPosts = async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await api.fetchPosts(workspaceId, seed || undefined, {
                topic: topicFilter || undefined,
                limit: 200,
                handle: handle || undefined,
            });
            setPosts(result);
            setFailedPostThumbnails({});
        } catch (e: any) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    const handleAnalyze = async () => {
        if (!onRunPlaybook || analyzing) return;
        setAnalyzing(true);
        setAnalyzeStatus('idle');
        try {
            await onRunPlaybook('ig_analyze_content', { seed, posts_per_account: postsCount });
            setAnalyzeStatus('launched');
            // Auto-clear the "launched" status after 4 seconds
            setTimeout(() => setAnalyzeStatus('idle'), 4000);
        } catch (e) {
            console.error('[ContentAnalysis] Failed to launch:', e);
        } finally {
            setAnalyzing(false);
        }
    };

    useEffect(() => {
        loadPosts();
    }, [seed, handle, topicFilter]);

    // Topic distribution
    const topicCounts: Record<string, number> = {};
    posts.forEach((p) => {
        const t = p.caption_topic || 'unclassified';
        topicCounts[t] = (topicCounts[t] || 0) + 1;
    });
    const sortedTopics = Object.entries(topicCounts).sort((a, b) => b[1] - a[1]);
    const maxTopicCount = Math.max(...Object.values(topicCounts), 1);

    // Hashtag aggregation
    const hashtagCounts: Record<string, number> = {};
    posts.forEach((p) => {
        try {
            const tags: string[] = p.caption_hashtags_json ? JSON.parse(p.caption_hashtags_json) : [];
            tags.forEach((tag) => {
                hashtagCounts[tag] = (hashtagCounts[tag] || 0) + 1;
            });
        } catch { /* ignore */ }
    });
    const topHashtags = Object.entries(hashtagCounts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 30);

    return (
        <div className="h-full flex flex-col overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-green-500" />
                    <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">Content Analysis</span>
                    <span className="text-xs text-gray-500">({posts.length} posts)</span>
                </div>
                <div className="flex items-center gap-2">
                    <select
                        value={postsCount}
                        onChange={(e) => setPostsCount(Number(e.target.value))}
                        className="px-2 py-1 text-xs border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300"
                        disabled={analyzing}
                    >
                        <option value={9}>9 posts</option>
                        <option value={12}>12 posts</option>
                        <option value={30}>30 posts</option>
                    </select>
                    <button
                        onClick={handleAnalyze}
                        disabled={analyzing}
                        className={`flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${analyzing
                                ? 'bg-green-400 text-white cursor-wait'
                                : analyzeStatus === 'launched'
                                    ? 'bg-green-600 text-white'
                                    : 'bg-green-500 text-white hover:bg-green-600'
                            }`}
                    >
                        {analyzing ? (
                            <>
                                <Loader2 className="w-3 h-3 animate-spin" />
                                Launching…
                            </>
                        ) : analyzeStatus === 'launched' ? (
                            <>
                                <CheckCircle className="w-3 h-3" />
                                Launched ✓
                            </>
                        ) : (
                            <>
                                <RefreshCw className="w-3 h-3" />
                                Analyze Content
                            </>
                        )}
                    </button>
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto">
                {loading ? (
                    <div className="flex items-center justify-center h-32">
                        <Loader2 className="w-5 h-5 animate-spin text-green-500" />
                    </div>
                ) : error ? (
                    <div className="p-4 text-sm text-red-500">{error}</div>
                ) : posts.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-32 text-gray-500 dark:text-gray-400">
                        <FileText className="w-8 h-8 mb-2 opacity-30" />
                        <p className="text-sm">No posts analyzed yet. Run content analysis first.</p>
                    </div>
                ) : (
                    <div className="p-4 space-y-4">
                        {/* Topic Distribution */}
                        <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-3">
                            <div className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">Topic Distribution</div>
                            <div className="space-y-1.5">
                                {sortedTopics.slice(0, 8).map(([topic, count]) => (
                                    <button
                                        key={topic}
                                        onClick={() => setTopicFilter(topicFilter === topic ? '' : topic)}
                                        className={`flex items-center gap-2 w-full text-left ${topicFilter === topic ? 'bg-blue-50 dark:bg-blue-900/20 rounded' : ''}`}
                                    >
                                        <span className="text-xs w-24 text-gray-500 truncate capitalize">{topic}</span>
                                        <div className="flex-1 h-4 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                            <div
                                                className="h-full bg-green-400 dark:bg-green-600 rounded-full"
                                                style={{ width: `${(count / maxTopicCount) * 100}%` }}
                                            />
                                        </div>
                                        <span className="text-xs w-6 text-right text-gray-500">{count}</span>
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Hashtag Cloud */}
                        {topHashtags.length > 0 && (
                            <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-3">
                                <div className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">
                                    <Hash className="w-3 h-3 inline mr-1" />
                                    Top Hashtags
                                </div>
                                <div className="flex flex-wrap gap-1.5">
                                    {topHashtags.map(([tag, count]) => (
                                        <span
                                            key={tag}
                                            className="px-2 py-1 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-full text-xs text-gray-700 dark:text-gray-300"
                                        >
                                            #{tag} <span className="text-gray-400 ml-0.5">{count}</span>
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Posts Grid */}
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                            {posts.slice(0, 48).map((post, idx) => {
                                const thumbnailKey = `${post.id || post.post_shortcode || idx}:${post.thumbnail_url || ''}`;
                                const thumbnailFailed = !!failedPostThumbnails[thumbnailKey];
                                const thumbnailSrc = !thumbnailFailed
                                    ? (
                                        post.post_shortcode
                                            ? getPostThumbnailUrl(apiUrl, post.post_shortcode)
                                            : getProxiedImageUrl(apiUrl, post.thumbnail_url)
                                    )
                                    : undefined;

                                return (
                                    <a
                                        key={post.id || post.post_shortcode || idx}
                                        href={post.post_url || '#'}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="group block bg-gray-100 dark:bg-gray-800 rounded-lg overflow-hidden hover:ring-2 hover:ring-blue-400 transition-all"
                                    >
                                        <div className="relative w-full aspect-square">
                                            {thumbnailSrc ? (
                                                <img
                                                    src={thumbnailSrc}
                                                    alt={`Post ${post.post_shortcode}`}
                                                    className="w-full h-full object-cover"
                                                    loading="lazy"
                                                    onError={() => {
                                                        setFailedPostThumbnails((prev) => {
                                                            if (prev[thumbnailKey]) return prev;
                                                            return { ...prev, [thumbnailKey]: true };
                                                        });
                                                    }}
                                                />
                                            ) : null}
                                            <div className={`post-placeholder w-full h-full flex items-center justify-center bg-gray-200 dark:bg-gray-700 ${thumbnailSrc ? 'hidden absolute inset-0' : ''}`}>
                                                <FileText className="w-6 h-6 text-gray-400" />
                                            </div>
                                        </div>
                                        <div className="p-2">
                                            <div className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">
                                                @{post.account_handle}
                                            </div>
                                            <div className="flex items-center gap-2 text-xs text-gray-500">
                                                {post.like_count != null && <span>❤ {post.like_count}</span>}
                                                {post.comment_count != null && <span>💬 {post.comment_count}</span>}
                                            </div>
                                            {post.caption_topic && (
                                                <span className="inline-block mt-1 px-1.5 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded text-xs capitalize">
                                                    {post.caption_topic}
                                                </span>
                                            )}
                                        </div>
                                    </a>
                                );
                            })}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
