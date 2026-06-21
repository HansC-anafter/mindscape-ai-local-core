import type { ModelItem } from './types';

export const MAX_OUTPUT_TOKEN_SLIDER_MAX = 131072;
export const LOCAL_MLX_MAX_OUTPUT_TOKENS_CAP = 12288;

export function getDefaultMaxTokens(model: ModelItem): number {
  const name = (model.model_name || '').toLowerCase();
  if (name.includes('qwen')) return 16384;
  if (name.includes('gemini')) return 8192;
  if (name.includes('gpt-5') || name.includes('o1') || name.includes('o3')) return 8000;
  if (name.includes('llama') || name.includes('mistral') || name.includes('claude')) return 8192;

  const params = model.metadata?.hf_parameters;
  if (params && params < 3e9) return 8192;
  if (params && params < 9e9) return 16384;
  return 4096;
}

export function getLocalRuntimeMaxTokensCap(model: ModelItem, engine: string): number | null {
  const metadataCap = Number(
    model.metadata?.local_max_output_tokens_cap
      ?? model.metadata?.runtime_max_output_tokens_cap
      ?? model.metadata?.max_output_tokens_cap
  );
  if (Number.isFinite(metadataCap) && metadataCap > 0) {
    return metadataCap;
  }

  const name = (model.model_name || '').toLowerCase();
  const provider = (model.provider || '').toLowerCase();
  const resolvedEngine = (engine || 'auto').toLowerCase();
  const routesToLocalMlx =
    resolvedEngine === 'mlx'
    || (resolvedEngine === 'auto' && (name.includes('mlx-community') || name.includes('mlx')));

  if (model.model_type === 'multimodal' && routesToLocalMlx && (provider === 'huggingface' || provider === 'mlx')) {
    return LOCAL_MLX_MAX_OUTPUT_TOKENS_CAP;
  }

  return null;
}

export function resolveInitialMaxOutputTokens(model: ModelItem, defaultMaxTokens: number, runtimeEngine: string): number {
  const localRuntimeCap = getLocalRuntimeMaxTokensCap(model, runtimeEngine);
  return Math.min(
    model.metadata?.max_output_tokens ?? defaultMaxTokens,
    localRuntimeCap ?? MAX_OUTPUT_TOKEN_SLIDER_MAX
  );
}
