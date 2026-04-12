/**
 * IG Insights API client
 *
 * Queries profile tags, posts, network overlaps, personas, and seed management.
 */

import { MindscapeAPIClient } from '@/api/client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SeedInfo {
    seed: string;
    target_count: number;
    visited_count: number;
    expected_count: number | null;
    bio: string | null;
    profile_picture_url: string | null;
    last_crawled: string | null;
    has_tags: boolean;
    has_posts: boolean;
    has_network: boolean;
    has_personas: boolean;
    execution: SeedExecutionSummary | null;
}

export interface SeedExecutionSummary {
    execution_id: string | null;
    status: string | null;
    queue_position: number | null;
    blocked_reason: string | null;
    failure_reason: string | null;
    created_at: string | null;
    started_at: string | null;
    completed_at: string | null;
}

export interface ProfileTag {
    id: string | null;
    account_handle: string;
    account_type: string | null;
    influence_tier: string | null;
    engagement_potential: number | null;
    follower_following_ratio: number | null;
    bio_keywords_json: string | null;
    bio_detected_locale: string | null;
    computed_at: string | null;
}

export interface PostAnalysis {
    id: string | null;
    account_handle: string;
    post_shortcode: string | null;
    post_type: string | null;
    post_url: string | null;
    thumbnail_url: string | null;
    like_count: number | null;
    comment_count: number | null;
    caption: string | null;
    caption_hashtags_json: string | null;
    caption_topic: string | null;
    caption_sentiment: string | null;
    posted_at: string | null;
    captured_at: string | null;
}

export interface NetworkOverlap {
    target_handle: string;
    overlap_count: number;
    shared_by: string[];
}

export interface Persona {
    id: string | null;
    account_handle: string;
    persona_summary: string | null;
    persona_summary_locale: string | null;
    key_traits_json: string | null;
    content_themes_json: string | null;
    estimated_demographics_json: string | null;
    collaboration_potential: number | null;
    recommended_approach: string | null;
    generated_at: string | null;
}

export interface SeedStatus {
    seed: string;
    workspace_id: string;
    target_count: number;
    tags_count: number;
    posts_count: number;
    edges_count: number;
    personas_count: number;
}

export interface BatchPinMetrics {
    collected_count: number | null;
    pinned_count: number | null;
    duplicate_count: number | null;
    failed_count: number | null;
    target_count: number | null;
    existing_reference_count_before: number | null;
    existing_reference_count_after: number | null;
    remaining_needed_before: number | null;
    remaining_to_target: number | null;
    target_met: boolean | null;
}

export interface BatchPinExecutionSummary {
    execution_id: string;
    status: string;
    created_at: string | null;
    completed_at: string | null;
    target_count: number | null;
    user_data_dir: string | null;
    metrics: BatchPinMetrics | null;
}

export interface LatestBatchPinSummaryResponse {
    latest_attempt: BatchPinExecutionSummary | null;
    latest_completed: BatchPinExecutionSummary | null;
}

export interface PinFailedAttempt {
    id: string;
    dedupe_key: string;
    workspace_id: string;
    source_handle: string | null;
    source_shortcode: string | null;
    source_url: string | null;
    image_url: string | null;
    parent_execution_id: string | null;
    trigger: string | null;
    base64_image_present: boolean;
    error_kind: string;
    error_message: string;
    status: string;
    failure_count: number;
    first_failed_at: string | null;
    last_failed_at: string | null;
    recovered_at: string | null;
    recovered_reference_id: string | null;
    failure_payload: Record<string, unknown> | null;
}

export interface PinFailedAttemptListResponse {
    attempts: PinFailedAttempt[];
    total: number;
}

export interface RetryPinFailedAttemptsResponse {
    retried: number;
    recovered: number;
    still_failed: number;
    results: Array<{
        dedupe_key: string;
        source_shortcode: string | null;
        status: string;
        final_disposition: string | null;
        reference_id: string | null;
        error_kind: string | null;
        error: string | null;
    }>;
}

// ---------------------------------------------------------------------------
// API helpers (now using MindscapeAPIClient)
// ---------------------------------------------------------------------------

async function clientGetJson<T>(client: MindscapeAPIClient, url: string): Promise<T> {
    const res = await client.get(url);
    if (!res.ok) {
        const text = await res.text();
        throw new Error(`API error ${res.status}: ${text}`);
    }
    return res.json();
}

async function clientPostJson<T>(client: MindscapeAPIClient, url: string, body?: Record<string, unknown>): Promise<T> {
    const res = await client.post(url, body);
    if (!res.ok) {
        const text = await res.text();
        throw new Error(`API error ${res.status}: ${text}`);
    }
    return res.json();
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function createInsightsApi(apiUrl: string) {
    const client = MindscapeAPIClient.fromBaseUrl(apiUrl);
    const base = `/api/v1/ig/insights`;

    return {
        /** List all known seeds with analysis status */
        async fetchSeeds(workspaceId: string): Promise<SeedInfo[]> {
            const data = await clientGetJson<{ seeds: SeedInfo[] }>(
                client,
                `${base}/seeds?workspace_id=${encodeURIComponent(workspaceId)}`,
            );
            return data.seeds;
        },

        /** Get detailed status for a single seed */
        async fetchSeedStatus(workspaceId: string, seed: string): Promise<SeedStatus> {
            return clientGetJson<SeedStatus>(
                client,
                `${base}/seed-status?workspace_id=${encodeURIComponent(workspaceId)}&seed=${encodeURIComponent(seed)}`,
            );
        },

        /** Register a handle as a seed */
        async addSeed(workspaceId: string, handle: string): Promise<void> {
            await clientPostJson(
                client,
                `${base}/seeds?workspace_id=${encodeURIComponent(workspaceId)}&handle=${encodeURIComponent(handle)}`,
            );
        },

        /** Remove a seed */
        async removeSeed(workspaceId: string, handle: string): Promise<void> {
            await client.delete(
                `${base}/seeds/${encodeURIComponent(handle)}?workspace_id=${encodeURIComponent(workspaceId)}`,
            );
        },

        /** Query profile tags for a seed or specific handle */
        async fetchProfileTags(
            workspaceId: string,
            seed?: string,
            filters?: { account_type?: string; influence_tier?: string; handle?: string },
        ): Promise<ProfileTag[]> {
            let url = `${base}/profile-tags?workspace_id=${encodeURIComponent(workspaceId)}`;
            if (seed) url += `&seed=${encodeURIComponent(seed)}`;
            if (filters?.handle) url += `&handle=${encodeURIComponent(filters.handle)}`;
            if (filters?.account_type) url += `&account_type=${encodeURIComponent(filters.account_type)}`;
            if (filters?.influence_tier) url += `&influence_tier=${encodeURIComponent(filters.influence_tier)}`;
            return clientGetJson<ProfileTag[]>(client, url);
        },

        /** Query posts for a seed or specific handle */
        async fetchPosts(
            workspaceId: string,
            seedOrNull?: string,
            filters?: { handle?: string; topic?: string; limit?: number },
        ): Promise<PostAnalysis[]> {
            let url = `${base}/posts?workspace_id=${encodeURIComponent(workspaceId)}`;
            if (seedOrNull) url += `&seed=${encodeURIComponent(seedOrNull)}`;
            if (filters?.handle) url += `&handle=${encodeURIComponent(filters.handle)}`;
            if (filters?.topic) url += `&topic=${encodeURIComponent(filters.topic)}`;
            if (filters?.limit) url += `&limit=${filters.limit}`;
            return clientGetJson<PostAnalysis[]>(client, url);
        },

        /** Get latest batch-pin request/result summary for one handle */
        async fetchLatestBatchPinSummary(
            workspaceId: string,
            handle: string,
        ): Promise<LatestBatchPinSummaryResponse> {
            return clientGetJson<LatestBatchPinSummaryResponse>(
                client,
                `${base}/latest-batch-pin-summary?workspace_id=${encodeURIComponent(workspaceId)}&handle=${encodeURIComponent(handle)}`,
            );
        },

        /** List pre-reference pin failures for one account/workspace */
        async fetchPinFailedAttempts(
            workspaceId: string,
            handle?: string,
            status?: string,
            limit = 50,
        ): Promise<PinFailedAttemptListResponse> {
            const params = new URLSearchParams({
                workspace_id: workspaceId,
                limit: String(limit),
            });
            if (handle) params.set('handle', handle);
            if (status) params.set('status', status);
            return clientGetJson<PinFailedAttemptListResponse>(
                client,
                `${base}/pin-failed-attempts?${params.toString()}`,
            );
        },

        /** Retry pre-reference pin failures for one account/workspace */
        async retryPinFailedAttempts(
            workspaceId: string,
            options: { handle?: string; dedupe_keys?: string[]; limit?: number; pinned_by?: string },
        ): Promise<RetryPinFailedAttemptsResponse> {
            return clientPostJson<RetryPinFailedAttemptsResponse>(
                client,
                `${base}/pin-failed-attempts/retry?workspace_id=${encodeURIComponent(workspaceId)}`,
                options,
            );
        },

        /** Query network overlaps across seeds */
        async fetchNetwork(
            workspaceId: string,
            seeds: string[],
            minOverlap = 2,
        ): Promise<NetworkOverlap[]> {
            const url = `${base}/network?workspace_id=${encodeURIComponent(workspaceId)}&seeds=${encodeURIComponent(seeds.join(','))}&min_overlap=${minOverlap}`;
            return clientGetJson<NetworkOverlap[]>(client, url);
        },

        /** Query generated personas */
        async fetchPersonas(
            workspaceId: string,
            opts?: { seed?: string; handles?: string[] },
        ): Promise<Persona[]> {
            let url = `${base}/personas?workspace_id=${encodeURIComponent(workspaceId)}`;
            if (opts?.seed) url += `&seed=${encodeURIComponent(opts.seed)}`;
            if (opts?.handles?.length) url += `&handles=${encodeURIComponent(opts.handles.join(','))}`;
            return clientGetJson<Persona[]>(client, url);
        },
    };
}
