export type XttsHealthResult = {
  available: boolean;
  reason?: string;
};

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

function apiUrl(apiBase: string, path: string): string {
  return `${trimTrailingSlash(apiBase)}${path}`;
}

export async function fetchXttsHealth(apiBase: string): Promise<XttsHealthResult> {
  try {
    const response = await fetch(apiUrl(apiBase, '/api/v1/host/services/xtts/health'));
    const body = await response.json().catch(() => ({}));
    if (!response.ok || body?.status !== 'healthy') {
      return {
        available: false,
        reason: body?.reason || body?.error || body?.status || response.statusText,
      };
    }
    return { available: true };
  } catch (error) {
    return {
      available: false,
      reason: error instanceof Error ? error.message : 'xtts_health_unavailable',
    };
  }
}

export async function synthesizeXttsSpeech({
  apiBase,
  text,
  language = 'zh-cn',
}: {
  apiBase: string;
  text: string;
  language?: string;
}): Promise<Blob> {
  const response = await fetch(apiUrl(apiBase, '/api/v1/host/services/xtts/tts'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      text,
      language,
      output_format: 'wav',
    }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const reason = body?.detail?.reason || body?.detail?.error || response.statusText;
    throw new Error(reason || 'xtts_synthesis_failed');
  }
  return response.blob();
}

export class VoicePlaybackQueue {
  private activeAudio: HTMLAudioElement | null = null;
  private urls: string[] = [];

  enqueue(blob: Blob): void {
    if (typeof Audio === 'undefined' || typeof URL === 'undefined') {
      return;
    }
    const url = URL.createObjectURL(blob);
    this.urls.push(url);
    if (!this.activeAudio) {
      this.playUrl(url);
    }
  }

  interrupt(): void {
    if (this.activeAudio) {
      this.activeAudio.pause();
      this.activeAudio.src = '';
      this.activeAudio = null;
    }
    this.urls.forEach((url) => URL.revokeObjectURL(url));
    this.urls = [];
  }

  private playUrl(url: string): void {
    const audio = new Audio(url);
    this.activeAudio = audio;
    audio.onended = () => {
      URL.revokeObjectURL(url);
      this.urls = this.urls.filter((item) => item !== url);
      this.activeAudio = null;
      const next = this.urls[0];
      if (next) {
        this.playUrl(next);
      }
    };
    void audio.play().catch(() => {
      this.interrupt();
    });
  }
}
