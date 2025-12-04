const getApiUrl = (): string => {
  if (typeof window === 'undefined') {
    return 'http://localhost:8000';
  }
  const envUrl = process.env.NEXT_PUBLIC_API_URL;
  if (envUrl && envUrl.startsWith('http')) {
    return envUrl;
  }
  return 'http://localhost:8000';
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
  baseURL: getApiUrl(),
  get: async <T>(endpoint: string, options?: { silent?: boolean }): Promise<T> => {
    const apiUrl = getApiUrl();
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
    const apiUrl = getApiUrl();
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
    const apiUrl = getApiUrl();
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
    const apiUrl = getApiUrl();
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
    const apiUrl = getApiUrl();
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
