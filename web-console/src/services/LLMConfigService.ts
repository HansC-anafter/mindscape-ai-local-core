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

/**
 * Service for managing LLM configuration and chat model data.
 *
 * Provides:
 * - Multi-dimensional caching (by apiUrl, workspaceId, profileId)
 * - Authentication header support
 * - Timeout and abort signal handling
 * - Error fallback to cached values
 * - Cache invalidation and cleanup mechanisms
 */
class LLMConfigService {
  private configCache: Map<string, CacheEntry<boolean>> = new Map();
  private modelCache: Map<string, CacheEntry<ChatModelData>> = new Map();

  private readonly DEFAULT_TTL = 5 * 60 * 1000;
  private readonly DEFAULT_TIMEOUT = 5000;

  private getCacheKey(apiUrl: string, workspaceId?: string, profileId?: string): string {
    return `${apiUrl}:${workspaceId || 'default'}:${profileId || 'default-user'}`;
  }

  /**
   * Check LLM configuration availability.
   *
   * @param apiUrl - API base URL
   * @param options - Request options
   * @returns Promise resolving to configuration availability status
   */
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
        console.warn('[LLMConfigService] Request timeout, using cached value');
        return cached.data;
      }

      console.error('[LLMConfigService] Failed to check LLM configuration:', error);
      throw error;
    }
  }

  /**
   * Load chat model data.
   *
   * @param apiUrl - API base URL
   * @param options - Request options
   * @returns Promise resolving to chat model data
   */
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
      const response = await fetch(
        `${apiUrl}/api/v1/system-settings/llm-models`,
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

      if (error.name === 'AbortError' && cached) {
        console.warn('[LLMConfigService] Request timeout, using cached value');
        return cached.data;
      }

      console.error('[LLMConfigService] Failed to load chat model:', error);
      throw error;
    }
  }

  /**
   * Invalidate cache for specific dimensions or all cache.
   *
   * @param apiUrl - Optional API URL (if provided, only invalidate for this URL)
   * @param workspaceId - Optional workspace ID (if provided, only invalidate for this workspace)
   * @param profileId - Optional profile ID (if provided, only invalidate for this profile)
   */
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

  /**
   * Clean up expired cache entries.
   */
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

