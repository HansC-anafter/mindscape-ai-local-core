'use client';

import type { HuggingFaceModelResult } from './types';

interface HuggingFaceDiscoveryModalProps {
  addModelType: string;
  customRepoId: string;
  hfLoading: boolean;
  hfRegistering: string | null;
  hfResults: HuggingFaceModelResult[];
  hfSearchQuery: string;
  onClose: () => void;
  onRegisterCustomId: () => void | Promise<void>;
  onRegisterModel: (modelId: string, modelType: string) => void | Promise<void>;
  onSearch: () => void | Promise<void>;
  onSetAddModelType: (modelType: string) => void;
  onSetCustomRepoId: (value: string) => void;
  onSetSearchQuery: (value: string) => void;
}

export function HuggingFaceDiscoveryModal({
  addModelType,
  customRepoId,
  hfLoading,
  hfRegistering,
  hfResults,
  hfSearchQuery,
  onClose,
  onRegisterCustomId,
  onRegisterModel,
  onSearch,
  onSetAddModelType,
  onSetCustomRepoId,
  onSetSearchQuery,
}: HuggingFaceDiscoveryModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-[560px] max-h-[80vh] flex flex-col border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">新增 HuggingFace 模型</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-lg">
            Close
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">類型:</span>
            {(['chat', 'multimodal', 'embedding'] as const).map((modelType) => (
              <button
                key={modelType}
                onClick={() => onSetAddModelType(modelType)}
                className={`px-2.5 py-1 text-xs rounded-md border transition-colors ${
                  addModelType === modelType
                    ? 'bg-accent text-white border-accent'
                    : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:border-accent/50'
                }`}
              >
                {modelType === 'chat' ? 'Chat' : modelType === 'multimodal' ? 'Multimodal' : 'Embedding'}
              </button>
            ))}
          </div>

          <div className="flex gap-2">
            <input
              type="text"
              placeholder="搜尋 HF 模型（如 Qwen, Llama, Mistral...）"
              value={hfSearchQuery}
              onChange={(event) => onSetSearchQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  onSearch();
                }
              }}
              className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-accent/50"
            />
            <button
              onClick={onSearch}
              disabled={hfLoading}
              className="px-4 py-2 text-sm font-medium rounded-md bg-accent text-white hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              {hfLoading ? '搜尋中...' : '搜尋'}
            </button>
          </div>

          <div className="flex gap-2">
            <input
              type="text"
              placeholder="或直接輸入 Repo ID（如 Qwen/Qwen2-VL-9B-Instruct）"
              value={customRepoId}
              onChange={(event) => onSetCustomRepoId(event.target.value)}
              className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-accent/50"
            />
            <button
              onClick={onRegisterCustomId}
              disabled={!customRepoId.trim() || hfRegistering === customRepoId}
              className="px-4 py-2 text-sm font-medium rounded-md bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
            >
              {hfRegistering === customRepoId ? '註冊中...' : '直接註冊'}
            </button>
          </div>

          {hfResults.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs text-gray-500 dark:text-gray-400">找到 {hfResults.length} 個模型：</p>
              {hfResults.map((result) => (
                <div
                  key={result.model_id}
                  className="flex items-center justify-between p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50 hover:border-accent/40 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                      {result.model_id}
                    </div>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className="text-xs text-gray-500">Downloads {(result.downloads / 1000).toFixed(0)}K</span>
                      <span className="text-xs text-gray-500">Likes {result.likes}</span>
                      <span
                        className={`text-xs px-1.5 py-0.5 rounded ${
                          result.model_type === 'multimodal'
                            ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300'
                            : result.model_type === 'embedding'
                              ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                              : 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                        }`}
                      >
                        {result.model_type}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={() => onRegisterModel(result.model_id, result.model_type)}
                    disabled={hfRegistering === result.model_id}
                    className="ml-3 px-3 py-1.5 text-xs font-medium rounded-md bg-accent text-white hover:opacity-90 disabled:opacity-50 transition-opacity whitespace-nowrap"
                  >
                    {hfRegistering === result.model_id ? '註冊中...' : '加入'}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
