// 获取初始 API URL（避免循环依赖）
const getInitialApiUrl = (): string => {
  // 优先使用环境变量
  if (process.env.NEXT_PUBLIC_API_URL && process.env.NEXT_PUBLIC_API_URL.startsWith('http')) {
    return process.env.NEXT_PUBLIC_API_URL;
  }

  // 使用同源代理（如果前端和后端在同一域名下）
  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol;
    const hostname = window.location.hostname;
    // 首先尝试从端口配置服务获取（如果可用）
    // 如果失败，回退到实际运行的后端端口（8200，端口配置系统默认值）
    // 注意：端口配置系统默认是 8200
    // 这里使用 8200 作为初始值，后续会通过端口配置 API 动态更新
    return `${protocol}//${hostname}:8200`;
  }

  // 服务端渲染时使用默认值（端口配置系统默认值）
  return 'http://localhost:8200';
};

// 动态获取 API URL（从端口配置服务读取，支持作用域）
let apiUrlCache: string | null = null;
let apiUrlPromise: Promise<string> | null = null;
let lastValidationTime: number = 0;
let failedUrls: Set<string> = new Set(); // 记录验证失败的 URL，避免反复尝试
const VALIDATION_INTERVAL = 30000; // 30 秒内只验证一次

const getApiUrl = async (forceRefresh: boolean = false): Promise<string> => {
  const now = Date.now();

  // 如果已有缓存且不强制刷新
  if (apiUrlCache && !forceRefresh) {
    // 如果缓存的 URL 之前验证失败过，直接跳过验证，使用初始 URL
    if (failedUrls.has(apiUrlCache as string)) {
      const initialUrl = getInitialApiUrl();
      if (initialUrl !== apiUrlCache) {
        // 如果初始 URL 不同，使用初始 URL 并清除失败记录
        apiUrlCache = initialUrl;
        failedUrls.clear();
        return apiUrlCache;
      }
    }

    // 减少验证频率：只在距离上次验证超过 30 秒时才验证
    if (now - lastValidationTime < VALIDATION_INTERVAL) {
      return apiUrlCache; // 直接返回缓存，不验证
    }

    // 快速验证缓存的 URL 是否可访问（仅检查健康端点）
    try {
      const testController = new AbortController();
      const testTimeoutId = setTimeout(() => testController.abort(), 500);
      const testResponse = await fetch(`${apiUrlCache}/health`, {
        signal: testController.signal,
        method: 'GET', // Backend only supports GET, not HEAD
      });
      clearTimeout(testTimeoutId);
      lastValidationTime = now;
      if (testResponse.ok) {
        // 验证成功，清除失败记录
        failedUrls.delete(apiUrlCache);
        return apiUrlCache; // 缓存有效，直接返回
      }
      // 响应不 OK，记录失败并清除缓存
      failedUrls.add(apiUrlCache);
      apiUrlCache = null;
      apiUrlPromise = null;
    } catch (e) {
      // 缓存无效，记录失败并清除缓存
      lastValidationTime = now;
      if (apiUrlCache) {
        failedUrls.add(apiUrlCache);
        console.warn(`缓存的 API URL (${apiUrlCache}) 不可访问，清除缓存并重新获取`);
      }
      apiUrlCache = null;
      apiUrlPromise = null;
    }
  }

  // 如果正在加载，等待加载完成
  if (apiUrlPromise && !forceRefresh) {
    return apiUrlPromise;
  }

  // 首次加载或强制刷新
  apiUrlPromise = (async () => {
    // 先尝试从实际运行的后端端口（8000）获取配置
    const initialUrl = getInitialApiUrl();

    try {
      // 获取当前作用域（优先从全局状态/UI 状态，回退到环境变量）
      let cluster: string | undefined;
      let environment: string | undefined;
      let site: string | undefined;

      // 方法 1: 从全局状态管理器获取（如果存在）
      if (typeof window !== 'undefined' && (window as any).__PORT_CONFIG_SCOPE__) {
        const scope = (window as any).__PORT_CONFIG_SCOPE__;
        cluster = scope.cluster;
        environment = scope.environment;
        site = scope.site;
      }

      // 方法 2: 从 localStorage 获取（UI 设置页面保存的作用域）
      if (typeof window !== 'undefined' && !cluster && !environment && !site) {
        try {
          const savedScope = localStorage.getItem('port_config_scope');
          if (savedScope) {
            const scope = JSON.parse(savedScope);
            cluster = scope.cluster || undefined;
            environment = scope.environment || undefined;
            site = scope.site || undefined;
          }
        } catch (e) {
          // 忽略解析错误
        }
      }

      // 方法 3: 回退到环境变量
      if (!cluster && !environment && !site) {
        cluster = process.env.NEXT_PUBLIC_CLUSTER;
        environment = process.env.NEXT_PUBLIC_ENVIRONMENT;
        site = process.env.NEXT_PUBLIC_SITE;
      }

      // 清理 "default" 值：如果 environment 是 "default"，不传该参数（使用全局配置）
      if (environment === 'default') {
        environment = undefined;
      }

      // 构建带作用域参数的 URL
      const params = new URLSearchParams();
      if (cluster) params.append('cluster', cluster);
      if (environment) params.append('environment', environment);
      if (site) params.append('site', site);

      const url = `${initialUrl}/api/v1/system-settings/ports/urls${params.toString() ? '?' + params.toString() : ''}`;

      // 创建超时控制器（兼容性处理）
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2000); // 减少超时时间到 2 秒

      const response = await fetch(url, {
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (response.ok) {
        const urls: { backend_api_url: string } = await response.json();
        // 验证返回的 URL 是否可访问
        const backendUrl = urls.backend_api_url;
        // 如果返回的 URL 与初始 URL 不同，尝试验证它是否可访问
        if (backendUrl !== initialUrl) {
          try {
            const testController = new AbortController();
            const testTimeoutId = setTimeout(() => testController.abort(), 1000);
            const testResponse = await fetch(`${backendUrl}/health`, {
              signal: testController.signal,
            });
            clearTimeout(testTimeoutId);
            if (testResponse.ok) {
              apiUrlCache = backendUrl;
              failedUrls.delete(backendUrl); // 验证成功，清除失败记录
              return apiUrlCache;
            } else {
              // 验证失败，记录失败的 URL
              failedUrls.add(backendUrl);
            }
          } catch (e) {
            // 如果配置的 URL 不可访问，记录失败并回退到初始 URL
            failedUrls.add(backendUrl);
            console.warn(`配置的 API URL (${backendUrl}) 不可访问，回退到初始 URL (${initialUrl})`);
          }
        } else {
          apiUrlCache = backendUrl;
          failedUrls.delete(backendUrl); // 验证成功，清除失败记录
          return apiUrlCache;
        }
      }
    } catch (error) {
      // 如果无法从端口配置服务获取 URL（可能服务未启动或端口不匹配），
      // 回退到初始 URL（实际运行的后端端口）
      console.warn('无法从配置服务获取 API URL，使用初始 URL:', error);
    }

    // 回退到初始 URL（实际运行的后端端口，通常是 8000）
    const fallbackUrl = getInitialApiUrl();
    apiUrlCache = fallbackUrl;
    failedUrls.delete(fallbackUrl); // 清除失败记录，因为这是可靠的初始 URL
    lastValidationTime = now;
    return apiUrlCache;
  })();

  return apiUrlPromise;
};

// 同步版本的 getApiUrl（用于初始化，返回初始 URL）
const getApiUrlSync = (): string => {
  return getInitialApiUrl();
};

// 导出初始 API URL 获取函数，供其他模块使用
export const getInitialApiUrlForClient = (): string => {
  return getInitialApiUrl();
};

interface ApiError {
  detail?: string;
  message?: string;
}

const parseError = async (response: Response): Promise<string> => {
  try {
    const errorData: ApiError = await response.json();
    return errorData.detail || errorData.message || `HTTP ${response.status}: ${response.statusText}`;
  } catch {
    const text = await response.text();
    return text || `HTTP ${response.status}: ${response.statusText}`;
  }
};

export const settingsApi = {
  baseURL: getApiUrlSync(),
  get: async <T>(endpoint: string, options?: { silent?: boolean }): Promise<T> => {
    const apiUrl = await getApiUrl();
    const url = endpoint.startsWith('http') ? endpoint : `${apiUrl}${endpoint}`;

    try {
      const response = await fetch(url);

      if (!response.ok) {
        // For expected errors (501, 404) with silent flag, return empty/default data instead of throwing
        if (options?.silent && (response.status === 501 || response.status === 404)) {
          // Suppress error for expected cases - return empty object/array based on endpoint
          if (endpoint.includes('/connections') || endpoint.includes('/capability-packs') || endpoint.includes('/capability-suites') || endpoint.includes('/playbooks')) {
            return [] as T;
          }
          return {} as T;
        }

        const errorMessage = await parseError(response);
        throw new Error(errorMessage);
      }

      return response.json();
    } catch (error) {
      // If silent flag is set and it's a network error, return default value
      if (options?.silent) {
        if (endpoint.includes('/connections') || endpoint.includes('/capability-packs') || endpoint.includes('/capability-suites') || endpoint.includes('/playbooks')) {
          return [] as T;
        }
        return {} as T;
      }
      throw error;
    }
  },

  put: async <T>(endpoint: string, data: unknown): Promise<T> => {
    const apiUrl = await getApiUrl();
    const url = endpoint.startsWith('http') ? endpoint : `${apiUrl}${endpoint}`;
    const response = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const errorMessage = await parseError(response);
      throw new Error(errorMessage);
    }

    return response.json();
  },

  post: async <T>(endpoint: string, data?: unknown): Promise<T> => {
    const apiUrl = await getApiUrl();
    const url = endpoint.startsWith('http') ? endpoint : `${apiUrl}${endpoint}`;
    const options: RequestInit = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    };

    if (data) {
      options.body = JSON.stringify(data);
    }

    const response = await fetch(url, options);

    if (!response.ok) {
      const errorMessage = await parseError(response);
      throw new Error(errorMessage);
    }

    return response.json();
  },

  postFormData: async <T>(endpoint: string, formData: FormData): Promise<T> => {
    const apiUrl = await getApiUrl();
    const url = endpoint.startsWith('http') ? endpoint : `${apiUrl}${endpoint}`;
    const response = await fetch(url, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const errorMessage = await parseError(response);
      throw new Error(errorMessage);
    }

    return response.json();
  },

  delete: async <T>(endpoint: string): Promise<T> => {
    const apiUrl = await getApiUrl();
    const url = endpoint.startsWith('http') ? endpoint : `${apiUrl}${endpoint}`;
    const response = await fetch(url, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!response.ok) {
      const errorMessage = await parseError(response);
      throw new Error(errorMessage);
    }

    return response.json();
  },
};
