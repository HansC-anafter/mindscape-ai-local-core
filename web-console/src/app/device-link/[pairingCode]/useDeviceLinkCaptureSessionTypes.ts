export type SourceMode = 'phone' | 'camera';

export type LinkState =
  | 'idle'
  | 'connecting'
  | 'paired'
  | 'streaming'
  | 'closed'
  | 'secure_context_required'
  | 'error';

export type ReferenceLessonState = {
  chapter_ref?: string;
  title?: string;
  timestamp_ms?: number;
  poster_ref?: string;
  focus_cue?: string;
};

export type CaptureControlState =
  | 'idle'
  | 'switching_camera'
  | 'switching_orientation'
  | 'fullscreen';

export interface DeviceLinkCaptureSessionOptions {
  pairingCode: string;
  workspaceId: string;
  initialSourceMode?: SourceMode;
}
