'use client';

import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';

import type { CaptureControlState } from './useDeviceLinkCaptureSessionTypes';

export function useDeviceLinkFullscreen(
  setCaptureControlState: Dispatch<SetStateAction<CaptureControlState>>,
) {
  const captureRootRef = useRef<HTMLElement | null>(null);
  const [fullscreenSupported, setFullscreenSupported] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [fullscreenMessage, setFullscreenMessage] = useState<string | null>(null);

  useEffect(() => {
    const onFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === captureRootRef.current);
      if (document.fullscreenElement === captureRootRef.current) {
        setFullscreenMessage(null);
      }
    };
    const onFullscreenError = () => {
      setFullscreenMessage('Fullscreen was blocked by this browser.');
    };
    setFullscreenSupported(
      typeof document !== 'undefined'
        && typeof document.documentElement.requestFullscreen === 'function',
    );
    document.addEventListener('fullscreenchange', onFullscreenChange);
    document.addEventListener('fullscreenerror', onFullscreenError);
    return () => {
      document.removeEventListener('fullscreenchange', onFullscreenChange);
      document.removeEventListener('fullscreenerror', onFullscreenError);
    };
  }, []);

  const toggleFullscreen = useCallback(async () => {
    const root = captureRootRef.current;
    if (!root || !fullscreenSupported || typeof root.requestFullscreen !== 'function') {
      setFullscreenMessage('Fullscreen unavailable. The capture layout stays edge-to-edge.');
      return;
    }
    setCaptureControlState('fullscreen');
    try {
      if (document.fullscreenElement === root) {
        await document.exitFullscreen();
      } else {
        await root.requestFullscreen();
      }
      setFullscreenMessage(null);
    } catch {
      setFullscreenMessage('Fullscreen was blocked by this browser.');
    } finally {
      setCaptureControlState('idle');
    }
  }, [fullscreenSupported, setCaptureControlState]);

  return {
    captureRootRef,
    fullscreenMessage,
    fullscreenSupported,
    isFullscreen,
    toggleFullscreen,
  };
}
