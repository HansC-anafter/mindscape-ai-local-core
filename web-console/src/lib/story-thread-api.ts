/**
 * Story Thread API client
 * Communicates with Cloud API for Story Thread operations
 */

const CLOUD_API_URL = process.env.NEXT_PUBLIC_CLOUD_API_URL || 'http://localhost:8001';

export interface StoryThread {
  thread_id: string;
  name: string;
  description?: string;
  mind_lens_id: string;
  workspace_id: string;
  owner_user_id: string;
  chapters: Chapter[];
  current_chapter_id?: string;
  shared_context: Record<string, any>;
  timeline: TimelineEvent[];
  version: number;
  snapshots: Snapshot[];
  created_at: string;
  updated_at: string;
}

export interface Chapter {
  chapter_id: string;
  thread_id: string;
  name: string;
  description?: string;
  status: 'planned' | 'in_progress' | 'completed';
  playbooks_used: string[];
  artifacts: string[];
  context_additions: Record<string, any>;
  created_at: string;
  updated_at: string;
  completed_at?: string;
}

export interface TimelineEvent {
  event_id: string;
  thread_id: string;
  chapter_id?: string;
  event_type: string;
  description: string;
  metadata?: Record<string, any>;
  timestamp: string;
}

export interface Snapshot {
  snapshot_id: string;
  thread_id: string;
  version: number;
  shared_context: Record<string, any>;
  chapters_state: Record<string, any>[];
  created_at: string;
  created_by: string;
}

export interface CreateStoryThreadRequest {
  name: string;
  description?: string;
  mind_lens_id: string;
  workspace_id: string;
  owner_user_id: string;
  initial_context?: Record<string, any>;
}

export interface UpdateStoryThreadRequest {
  name?: string;
  description?: string;
  current_chapter_id?: string;
}

export interface CreateChapterRequest {
  name: string;
  description?: string;
  status?: 'planned' | 'in_progress' | 'completed';
}

export interface UpdateContextRequest {
  updates: Record<string, any>;
  merge_strategy?: 'merge' | 'append' | 'preserve' | 'versioned' | 'replace';
}

class StoryThreadAPI {
  private baseUrl: string;

  constructor(baseUrl: string = CLOUD_API_URL) {
    this.baseUrl = baseUrl;
  }

  async createThread(request: CreateStoryThreadRequest): Promise<StoryThread> {
    const response = await fetch(`${this.baseUrl}/api/v1/story-threads`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`Failed to create thread: ${response.statusText}`);
    }

    return response.json();
  }

  async getThread(threadId: string): Promise<StoryThread> {
    const response = await fetch(`${this.baseUrl}/api/v1/story-threads/${threadId}`);

    if (!response.ok) {
      throw new Error(`Failed to get thread: ${response.statusText}`);
    }

    return response.json();
  }

  async updateThread(threadId: string, request: UpdateStoryThreadRequest): Promise<StoryThread> {
    const response = await fetch(`${this.baseUrl}/api/v1/story-threads/${threadId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`Failed to update thread: ${response.statusText}`);
    }

    return response.json();
  }

  async deleteThread(threadId: string): Promise<void> {
    const response = await fetch(`${this.baseUrl}/api/v1/story-threads/${threadId}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      throw new Error(`Failed to delete thread: ${response.statusText}`);
    }
  }

  async listThreads(params?: {
    workspace_id?: string;
    mind_lens_id?: string;
    owner_user_id?: string;
  }): Promise<StoryThread[]> {
    const queryParams = new URLSearchParams();
    if (params?.workspace_id) queryParams.append('workspace_id', params.workspace_id);
    if (params?.mind_lens_id) queryParams.append('mind_lens_id', params.mind_lens_id);
    if (params?.owner_user_id) queryParams.append('owner_user_id', params.owner_user_id);

    const response = await fetch(`${this.baseUrl}/api/v1/story-threads?${queryParams.toString()}`);

    if (!response.ok) {
      throw new Error(`Failed to list threads: ${response.statusText}`);
    }

    return response.json();
  }

  async createChapter(threadId: string, request: CreateChapterRequest): Promise<Chapter> {
    const response = await fetch(`${this.baseUrl}/api/v1/story-threads/${threadId}/chapters`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`Failed to create chapter: ${response.statusText}`);
    }

    return response.json();
  }

  async getChapters(threadId: string): Promise<Chapter[]> {
    const response = await fetch(`${this.baseUrl}/api/v1/story-threads/${threadId}/chapters`);

    if (!response.ok) {
      throw new Error(`Failed to get chapters: ${response.statusText}`);
    }

    return response.json();
  }

  async getChapter(threadId: string, chapterId: string): Promise<Chapter> {
    const response = await fetch(`${this.baseUrl}/api/v1/story-threads/${threadId}/chapters/${chapterId}`);

    if (!response.ok) {
      throw new Error(`Failed to get chapter: ${response.statusText}`);
    }

    return response.json();
  }

  async updateChapter(threadId: string, chapterId: string, request: Partial<Chapter>): Promise<Chapter> {
    const response = await fetch(`${this.baseUrl}/api/v1/story-threads/${threadId}/chapters/${chapterId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`Failed to update chapter: ${response.statusText}`);
    }

    return response.json();
  }

  async getContext(threadId: string): Promise<Record<string, any>> {
    const response = await fetch(`${this.baseUrl}/api/v1/story-threads/${threadId}/context`);

    if (!response.ok) {
      throw new Error(`Failed to get context: ${response.statusText}`);
    }

    return response.json();
  }

  async updateContext(threadId: string, request: UpdateContextRequest): Promise<Record<string, any>> {
    const response = await fetch(`${this.baseUrl}/api/v1/story-threads/${threadId}/context`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`Failed to update context: ${response.statusText}`);
    }

    return response.json();
  }

  async getTimeline(threadId: string, limit: number = 100): Promise<TimelineEvent[]> {
    const response = await fetch(`${this.baseUrl}/api/v1/story-threads/${threadId}/timeline?limit=${limit}`);

    if (!response.ok) {
      throw new Error(`Failed to get timeline: ${response.statusText}`);
    }

    return response.json();
  }

  async createTimelineEvent(threadId: string, event: {
    event_type: string;
    description: string;
    chapter_id?: string;
    metadata?: Record<string, any>;
  }): Promise<TimelineEvent> {
    const response = await fetch(`${this.baseUrl}/api/v1/story-threads/${threadId}/timeline/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(event),
    });

    if (!response.ok) {
      throw new Error(`Failed to create timeline event: ${response.statusText}`);
    }

    return response.json();
  }

  async getSnapshots(threadId: string): Promise<Snapshot[]> {
    const response = await fetch(`${this.baseUrl}/api/v1/story-threads/${threadId}/snapshots`);

    if (!response.ok) {
      throw new Error(`Failed to get snapshots: ${response.statusText}`);
    }

    return response.json();
  }

  async createSnapshot(threadId: string, createdBy: string): Promise<Snapshot> {
    const response = await fetch(`${this.baseUrl}/api/v1/story-threads/${threadId}/snapshots?created_by=${encodeURIComponent(createdBy)}`, {
      method: 'POST',
    });

    if (!response.ok) {
      throw new Error(`Failed to create snapshot: ${response.statusText}`);
    }

    return response.json();
  }
}

export const storyThreadAPI = new StoryThreadAPI();
export default storyThreadAPI;

