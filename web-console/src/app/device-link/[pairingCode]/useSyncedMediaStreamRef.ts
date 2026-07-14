'use client';

import { useEffect, useRef } from 'react';

export function useSyncedMediaStreamRef(localStream: MediaStream | null) {
  const streamRef = useRef<MediaStream | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    streamRef.current = localStream;
    if (videoRef.current) {
      videoRef.current.srcObject = localStream;
    }
  }, [localStream]);

  return {
    streamRef,
    videoRef,
  };
}
