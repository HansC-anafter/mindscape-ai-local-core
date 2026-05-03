interface CacheEntry<T> {
  data: T;
  timestamp: number;
  ttl: number;
}

interface RequestOptions {
  workspaceId?: string;
  profileId?: string;
  timeout?: number;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

export interface ChatModelData {
  chat_model?: {
    model_name: string;
    provider: string;
  };
  available_chat_models?: Array<{
    model_name: string;
    provider: string;
  }>;
  [key: string]: any;
}

class LLMConfigService {
  private configCache: Map<string, CacheEntry<boolean>> = new Map();
  private modelCache: Map<string, CacheEntry<ChatModelData>> = new Map();

  private readonly DEFAULT_TTL = 5 * 60 * 1000;
  private readonly DEFAULT_TIMEOUT = 5000;

  private getCacheKey(apiUrl: string, workspaceId?: string, profileId?: string): string {
    return `${apiUrl}:${workspaceId || 'default'}:${profileId || 'default-user'}`;
  }

  async checkLLMConfiguration(
    apiUrl: string,
    options: RequestOptions = {}
  ): Promise<boolean> {
    const {
      workspaceId,
      profileId = 'default-user',
      timeout = this.DEFAULT_TIMEOUT,
      headers = {},
      signal
    } = options;

    const cacheKey = this.getCacheKey(apiUrl, workspaceId, profileId);
    const cached = this.configCache.get(cacheKey);

    if (cached && Date.now() - cached.timestamp < cached.ttl) {
      return cached.data;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    if (signal) {
      signal.addEventListener('abort', () => controller.abort());
    }

    try {
      const response = await fetch(
        `${apiUrl}/api/v1/config/backend?profile_id=${profileId}`,
        {
          headers: {
            'Content-Type': 'application/json',
            ...headers,
          },
          signal: controller.signal,
        }
      );

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      const available = data.available_backends?.[data.current_mode]?.available || false;

      this.configCache.set(cacheKey, {
        data: available,
        timestamp: Date.now(),
        ttl: this.DEFAULT_TTL,
      });

      return available;
    } catch (error: any) {
      clearTimeout(timeoutId);

      if (error.name === 'AbortError' && cached) {
        return cached.data;
      }

      throw error;
    }
  }

  async loadChatModel(
    apiUrl: string,
    options: RequestOptions = {}
  ): Promise<ChatModelData> {
    const {
      workspaceId,
      profileId = 'default-user',
      timeout = this.DEFAULT_TIMEOUT * 1.6,
      headers = {},
      signal
    } = options;

    const cacheKey = this.getCacheKey(apiUrl, workspaceId, profileId);
    const cached = this.modelCache.get(cacheKey);

    if (cached && Date.now() - cached.timestamp < cached.ttl) {
      return cached.data;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    if (signal) {
      signal.addEventListener('abort', () => controller.abort());
    }

    try {
      const params = new URLSearchParams();
      if (workspaceId) {
        params.set('workspace_id', workspaceId);
      }
      if (profileId) {
        params.set('profile_id', profileId);
      }
      const response = await fetch(
        `${apiUrl}/api/v1/settings/model-route-registry/workspace-chat${params.toString() ? `?${params.toString()}` : ''}`,
        {
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            ...headers,
          },
          signal: controller.signal,
        }
      );

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const text = await response.text();
      if (!text || text.trim().length === 0) {
        throw new Error('Empty response from server');
      }

      let data: ChatModelData;
      try {
        data = JSON.parse(text);
      } catch (parseErr) {
        throw new Error(`Failed to parse JSON response: ${parseErr}`);
      }

      this.modelCache.set(cacheKey, {
        data,
        timestamp: Date.now(),
        ttl: this.DEFAULT_TTL,
      });

      return data;
    } catch (error: any) {
      clearTimeout(timeoutId);

      if (error.name === 'AbortError') {
        if (cached) {
          return cached.data;
        }
        throw error;
      }

      throw error;
    }
  }

  invalidateCache(apiUrl?: string, workspaceId?: string, profileId?: string) {
    if (apiUrl) {
      const cacheKey = this.getCacheKey(apiUrl, workspaceId, profileId);
      this.configCache.delete(cacheKey);
      this.modelCache.delete(cacheKey);
    } else {
      this.configCache.clear();
      this.modelCache.clear();
    }
  }

  cleanupExpiredCache() {
    const now = Date.now();

    for (const [key, entry] of this.configCache.entries()) {
      if (now - entry.timestamp >= entry.ttl) {
        this.configCache.delete(key);
      }
    }

    for (const [key, entry] of this.modelCache.entries()) {
      if (now - entry.timestamp >= entry.ttl) {
        this.modelCache.delete(key);
      }
    }
  }
}

export const llmConfigService = new LLMConfigService();

if (typeof window !== 'undefined') {
  setInterval(() => {
    llmConfigService.cleanupExpiredCache();
  }, 10 * 60 * 1000);
}
