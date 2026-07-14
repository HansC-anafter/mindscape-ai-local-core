import type { LiveMediaSessionAccess } from './liveMediaSessionClient';
import {
  createPresentationStream,
  getStreamAudioTracks,
  getStreamVideoTracks,
} from './webrtcPresentationStream';
import type {
  CameraFacingMode,
  CaptureOrientation,
  MediaSourceKind,
  WebRTCSessionHandle,
  WebRTCSessionState,
} from './webrtcSessionTypes';
import { startWhipPublisher, type WhipPublisherHandle } from './whipPublisherClient';

type RelaySourceSessionInput = {
  access: LiveMediaSessionAccess;
  sourceKind: MediaSourceKind;
  video: MediaTrackConstraints;
  audio?: boolean;
  videoOrientation?: CaptureOrientation;
  onLocalStream?: (stream: MediaStream) => void;
  onState?: (state: WebRTCSessionState) => void;
  onError?: (error: Error) => void;
};

export type PhoneRelaySourceSessionInput = Omit<
  RelaySourceSessionInput,
  'sourceKind' | 'video'
> & {
  facingMode?: CameraFacingMode;
};

export type DesktopRelaySourceSessionInput = Omit<
  RelaySourceSessionInput,
  'video'
> & {
  sourceKind: Extract<MediaSourceKind, 'desktop_camera' | 'usb_camera' | 'virtual_camera'>;
  deviceId?: string;
};

export function buildPhoneRelayVideoConstraints(
  facingMode?: CameraFacingMode,
): MediaTrackConstraints {
  return {
    facingMode: { ideal: facingMode || 'environment' },
    width: { ideal: 1280 },
    height: { ideal: 720 },
    frameRate: { max: 30 },
  };
}

async function startRelayMediaSourceSession(
  input: RelaySourceSessionInput,
): Promise<WebRTCSessionHandle> {
  let orientation = input.videoOrientation;
  let rawStream = await navigator.mediaDevices.getUserMedia({
    video: input.video,
    audio: input.audio ?? true,
  });
  let presentation = await createPresentationStream({ rawStream, orientation });
  let stream = presentation.stream;
  let publisher: WhipPublisherHandle | null = null;
  let stopped = false;
  input.onLocalStream?.(stream);
  input.onState?.('local_stream_ready');

  const cleanupStreams = () => {
    presentation.cleanup();
    for (const track of rawStream.getTracks()) {
      track.stop();
    }
  };

  try {
    publisher = await startWhipPublisher({
      endpoint: input.access.session.endpoints.whip_publish_url,
      token: input.access.tokens.publish,
      stream,
      onState: input.onState,
      onError: input.onError,
    });
  } catch (error) {
    cleanupStreams();
    throw error;
  }

  const replacePublisherVideoTrack = async (nextStream: MediaStream) => {
    const [nextTrack] = nextStream.getVideoTracks();
    if (!nextTrack) {
      throw new Error('replacement_video_track_missing');
    }
    const sender = publisher?.peerConnection
      .getSenders()
      .find((candidate) => candidate.track?.kind === 'video');
    if (!sender) {
      throw new Error('whip_video_sender_missing');
    }
    await sender.replaceTrack(nextTrack);
  };

  const replaceVideoTrack = async (
    constraints: MediaTrackConstraints,
    options?: { orientation?: CaptureOrientation },
  ): Promise<MediaStream> => {
    if (stopped) {
      throw new Error('media_session_stopped');
    }
    const previousVideoTracks = getStreamVideoTracks(rawStream);
    let previousCameraReleased = false;
    let replacementCapture: MediaStream | null = null;
    try {
      try {
        replacementCapture = await navigator.mediaDevices.getUserMedia({
          video: constraints,
          audio: false,
        });
      } catch {
        for (const track of previousVideoTracks) {
          track.stop();
        }
        previousCameraReleased = true;
        replacementCapture = await navigator.mediaDevices.getUserMedia({
          video: constraints,
          audio: false,
        });
      }
      const [replacementVideoTrack] = replacementCapture.getVideoTracks();
      if (!replacementVideoTrack) {
        throw new Error('replacement_video_track_missing');
      }
      const nextRawStream = new MediaStream([
        ...getStreamAudioTracks(rawStream),
        replacementVideoTrack,
      ]);
      orientation = options?.orientation || orientation;
      const nextPresentation = await createPresentationStream({
        rawStream: nextRawStream,
        orientation,
      });
      if (orientation && !nextPresentation.transformed) {
        nextPresentation.cleanup();
        throw new Error('capture_orientation_transform_unavailable');
      }
      await replacePublisherVideoTrack(nextPresentation.stream);
      if (!previousCameraReleased) {
        for (const track of previousVideoTracks) {
          track.stop();
        }
      }
      presentation.cleanup();
      rawStream = nextRawStream;
      presentation = nextPresentation;
      stream = nextPresentation.stream;
      input.onLocalStream?.(stream);
      return stream;
    } catch (error) {
      for (const track of replacementCapture?.getTracks() || []) {
        track.stop();
      }
      const normalized = error instanceof Error ? error : new Error('video_track_replace_failed');
      input.onError?.(normalized);
      throw normalized;
    }
  };

  const setVideoOrientation = async (
    nextOrientation: CaptureOrientation,
  ): Promise<MediaStream> => {
    if (stopped) {
      throw new Error('media_session_stopped');
    }
    const nextPresentation = await createPresentationStream({
      rawStream,
      orientation: nextOrientation,
    });
    if (!nextPresentation.transformed) {
      nextPresentation.cleanup();
      throw new Error('capture_orientation_transform_unavailable');
    }
    await replacePublisherVideoTrack(nextPresentation.stream);
    orientation = nextOrientation;
    presentation.cleanup();
    presentation = nextPresentation;
    stream = nextPresentation.stream;
    input.onLocalStream?.(stream);
    return stream;
  };

  return {
    stop: () => {
      if (stopped) {
        return;
      }
      stopped = true;
      publisher?.stop();
      cleanupStreams();
      input.onState?.('closed');
    },
    get peerConnection() {
      return publisher?.peerConnection || null;
    },
    get localStream() {
      return stream;
    },
    replaceVideoTrack,
    setVideoOrientation,
  };
}

export async function startPhoneRelayMediaSourceSession(
  input: PhoneRelaySourceSessionInput,
): Promise<WebRTCSessionHandle> {
  return startRelayMediaSourceSession({
    ...input,
    sourceKind: 'phone_camera',
    video: buildPhoneRelayVideoConstraints(input.facingMode),
    videoOrientation: input.videoOrientation === 'landscape'
      ? input.videoOrientation
      : undefined,
  });
}

export async function startDesktopRelayMediaSourceSession(
  input: DesktopRelaySourceSessionInput,
): Promise<WebRTCSessionHandle> {
  return startRelayMediaSourceSession({
    ...input,
    audio: false,
    video: {
      ...(input.deviceId ? { deviceId: { exact: input.deviceId } } : {}),
      width: { ideal: 1280 },
      height: { ideal: 720 },
      frameRate: { max: 30 },
    },
  });
}
