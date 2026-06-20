import type { CaptureOrientation } from './webrtcSessionTypes';

export function getStreamAudioTracks(stream: MediaStream): MediaStreamTrack[] {
  return typeof stream.getAudioTracks === 'function'
    ? stream.getAudioTracks().filter((track) => track.readyState !== 'ended')
    : stream.getTracks().filter((track) => track.kind === 'audio' && track.readyState !== 'ended');
}

export function getStreamVideoTracks(stream: MediaStream): MediaStreamTrack[] {
  return typeof stream.getVideoTracks === 'function'
    ? stream.getVideoTracks().filter((track) => track.readyState !== 'ended')
    : stream.getTracks().filter((track) => track.kind === 'video' && track.readyState !== 'ended');
}

function getCanvasOutputSize(orientation: CaptureOrientation): { width: number; height: number } {
  return orientation === 'portrait'
    ? { width: 720, height: 1280 }
    : { width: 1280, height: 720 };
}

function shouldAvoidCanvasPresentationStream(): boolean {
  if (typeof navigator === 'undefined') {
    return false;
  }
  const userAgent = navigator.userAgent || '';
  return /\b(iPad|iPhone|iPod)\b/.test(userAgent) && /WebKit/i.test(userAgent);
}

export async function createPresentationStream({
  rawStream,
  orientation,
}: {
  rawStream: MediaStream;
  orientation?: CaptureOrientation;
}): Promise<{ stream: MediaStream; cleanup: () => void; transformed: boolean }> {
  const [rawVideoTrack] = getStreamVideoTracks(rawStream);
  const fallback = { stream: rawStream, cleanup: () => undefined, transformed: false };
  if (!rawVideoTrack || !orientation || typeof document === 'undefined') {
    return fallback;
  }
  if (shouldAvoidCanvasPresentationStream()) {
    return fallback;
  }
  const canvas = document.createElement('canvas');
  if (typeof canvas.captureStream !== 'function') {
    return fallback;
  }
  const video = document.createElement('video');
  const sourceVideoStream = new MediaStream([rawVideoTrack]);
  const { width, height } = getCanvasOutputSize(orientation);
  canvas.width = width;
  canvas.height = height;
  video.muted = true;
  video.playsInline = true;
  video.srcObject = sourceVideoStream;
  try {
    await video.play();
  } catch {
    video.srcObject = null;
    return fallback;
  }
  const context = canvas.getContext('2d');
  if (!context) {
    video.pause();
    video.srcObject = null;
    return fallback;
  }

  let frameId = 0;
  let active = true;
  const draw = () => {
    if (!active) {
      return;
    }
    const sourceWidth = video.videoWidth || width;
    const sourceHeight = video.videoHeight || height;
    const scale = Math.max(width / sourceWidth, height / sourceHeight);
    const drawWidth = sourceWidth * scale;
    const drawHeight = sourceHeight * scale;
    const drawX = (width - drawWidth) / 2;
    const drawY = (height - drawHeight) / 2;
    context.clearRect(0, 0, width, height);
    try {
      context.drawImage(video, drawX, drawY, drawWidth, drawHeight);
    } catch {
      // Video metadata can briefly be unavailable on mobile browsers.
    }
    frameId = window.requestAnimationFrame(draw);
  };
  draw();

  const transformedVideoStream = canvas.captureStream(30);
  const [transformedVideoTrack] = transformedVideoStream.getVideoTracks();
  if (!transformedVideoTrack) {
    active = false;
    window.cancelAnimationFrame(frameId);
    video.pause();
    video.srcObject = null;
    return fallback;
  }
  const stream = new MediaStream([...getStreamAudioTracks(rawStream), transformedVideoTrack]);
  const cleanup = () => {
    active = false;
    window.cancelAnimationFrame(frameId);
    transformedVideoTrack.stop();
    video.pause();
    video.srcObject = null;
  };
  return { stream, cleanup, transformed: true };
}
