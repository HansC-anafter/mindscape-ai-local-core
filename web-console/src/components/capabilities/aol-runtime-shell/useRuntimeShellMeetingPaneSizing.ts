'use client';

import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type RefObject } from 'react';

import { type MeetingPaneSizePreset } from './RuntimeShellPanel';
import {
  clampMeetingPaneHeight,
  getMeetingPanePresetHeight,
  MEETING_PANE_DEFAULT_HEIGHT,
} from './runtimeShellState';

interface RuntimeShellMeetingPaneSizing {
  shellRootRef: RefObject<HTMLDivElement | null>;
  meetingPaneHeight: number;
  beginMeetingPaneResize: (event: ReactPointerEvent<HTMLButtonElement>) => void;
  setMeetingPaneSizePreset: (preset: MeetingPaneSizePreset) => void;
}

export function useRuntimeShellMeetingPaneSizing(isMeetingOpen: boolean): RuntimeShellMeetingPaneSizing {
  const shellRootRef = useRef<HTMLDivElement | null>(null);
  const [meetingPaneHeight, setMeetingPaneHeight] = useState(MEETING_PANE_DEFAULT_HEIGHT);

  const resizeMeetingPane = useCallback((clientY: number) => {
    const rootRect = shellRootRef.current?.getBoundingClientRect();
    if (!rootRect) {
      return;
    }
    setMeetingPaneHeight(clampMeetingPaneHeight(rootRect.bottom - clientY, rootRect.height));
  }, []);

  const beginMeetingPaneResize = useCallback(
    (event: ReactPointerEvent<HTMLButtonElement>) => {
      event.preventDefault();
      resizeMeetingPane(event.clientY);

      const handlePointerMove = (moveEvent: PointerEvent) => {
        resizeMeetingPane(moveEvent.clientY);
      };
      const handlePointerUp = () => {
        window.removeEventListener('pointermove', handlePointerMove);
        window.removeEventListener('pointerup', handlePointerUp);
      };

      window.addEventListener('pointermove', handlePointerMove);
      window.addEventListener('pointerup', handlePointerUp);
    },
    [resizeMeetingPane],
  );

  const setMeetingPaneSizePreset = useCallback((preset: MeetingPaneSizePreset) => {
    const rootHeight = shellRootRef.current?.getBoundingClientRect().height ?? MEETING_PANE_DEFAULT_HEIGHT;
    setMeetingPaneHeight(clampMeetingPaneHeight(getMeetingPanePresetHeight(preset, rootHeight), rootHeight));
  }, []);

  useEffect(() => {
    if (!isMeetingOpen) {
      return;
    }

    const clampCurrentHeight = () => {
      const rootHeight = shellRootRef.current?.getBoundingClientRect().height ?? MEETING_PANE_DEFAULT_HEIGHT;
      setMeetingPaneHeight((current) => clampMeetingPaneHeight(current, rootHeight));
    };

    clampCurrentHeight();
    window.addEventListener('resize', clampCurrentHeight);
    return () => {
      window.removeEventListener('resize', clampCurrentHeight);
    };
  }, [isMeetingOpen]);

  return {
    shellRootRef,
    meetingPaneHeight,
    beginMeetingPaneResize,
    setMeetingPaneSizePreset,
  };
}
