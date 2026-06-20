import {
  createPresentationStream,
  getStreamAudioTracks,
  getStreamVideoTracks,
} from './webrtcPresentationStream';
import {
  createLanPeerConnection,
  openWebRTCSignalSocket,
} from './webrtcSignalClient';
import type {
  BrowserMediaSourceSessionInput,
  CameraFacingMode,
  CaptureOrientation,
  DesktopBrowserSourceSessionInput,
  PhoneBrowserSourceSessionInput,
  WebRTCSessionHandle,
  WebRTCSignalSocket,
  WorkspaceReceiverSessionInput,
} from './webrtcSessionTypes';

export {
  buildWebRTCSignalWebSocketUrl,
  createLanPeerConnection,
  openWebRTCSignalSocket,
} from './webrtcSignalClient';
export type {
  BrowserMediaSourceSessionInput,
  CameraFacingMode,
  CaptureOrientation,
  DesktopBrowserSourceSessionInput,
  MediaSignalEvent,
  MediaSignalMessage,
  MediaSignalParticipant,
  MediaSourceKind,
  MediaStreamRef,
  OpenWebRTCSignalSocketInput,
  PhoneBrowserSourceSessionInput,
  WebRTCSessionHandle,
  WebRTCSessionState,
  WebRTCSignalSocket,
  WorkspaceReceiverSessionInput,
} from './webrtcSessionTypes';

export function buildPhoneVideoConstraints(facingMode?: CameraFacingMode): MediaTrackConstraints {
  return {
    facingMode: { ideal: facingMode || 'environment' },
    width: { ideal: 1280 },
    height: { ideal: 720 },
    frameRate: { max: 30 },
  };
}

export async function startBrowserMediaSourceSession(
  input: BrowserMediaSourceSessionInput,
): Promise<WebRTCSessionHandle> {
  let videoOrientation = input.videoOrientation;
  let rawStream = await navigator.mediaDevices.getUserMedia({
    video: input.video,
    audio: input.audio ?? true,
  });
  let presentation = await createPresentationStream({
    rawStream,
    orientation: videoOrientation,
  });
  let stream = presentation.stream;
  input.onLocalStream?.(stream);
  input.onState?.('local_stream_ready');

  let stopped = false;
  let joined = false;
  let peerConnection: RTCPeerConnection | null = null;
  let signalSocket: WebRTCSignalSocket;

  const ensurePeerConnection = () => {
    if (peerConnection) {
      return peerConnection;
    }
    peerConnection = createLanPeerConnection({
      onIceCandidate: (candidate) => signalSocket.send({ type: 'ice_candidate', candidate }),
      onConnectionStateChange: (state) => {
        if (state === 'connected') {
          input.onState?.('connected');
        }
      },
    });
    for (const track of stream.getTracks()) {
      peerConnection.addTrack(track, stream);
    }
    return peerConnection;
  };

  const sendOffer = async () => {
    if (!joined || stopped) {
      return;
    }
    const peer = ensurePeerConnection();
    const offer = await peer.createOffer();
    await peer.setLocalDescription(offer);
    signalSocket.send({ type: 'offer', sdp: offer.sdp || '' });
    input.onState?.('offer_sent');
  };

  const resendOfferIfNeeded = async () => {
    const hasUnansweredOffer = peerConnection?.localDescription?.type === 'offer'
      && !peerConnection.remoteDescription;
    if (hasUnansweredOffer) {
      return;
    }
    await sendOffer();
  };

  const stop = () => {
    if (stopped) {
      return;
    }
    stopped = true;
    try {
      signalSocket.send({ type: 'close', reason: 'source_stopped' });
    } catch {
      // Ignore shutdown races.
    }
    signalSocket.close();
    peerConnection?.close();
    presentation.cleanup();
    for (const track of rawStream.getTracks()) {
      track.stop();
    }
    input.onState?.('closed');
  };

  const replacePeerVideoTrack = async (nextStream: MediaStream) => {
    const [nextVideoTrack] = nextStream.getVideoTracks();
    if (!nextVideoTrack) {
      throw new Error('replacement_video_track_missing');
    }
    if (peerConnection) {
      const videoSender = peerConnection.getSenders().find((sender) => sender.track?.kind === 'video');
      if (videoSender && typeof videoSender.replaceTrack === 'function') {
        await videoSender.replaceTrack(nextVideoTrack);
      } else {
        peerConnection.addTrack(nextVideoTrack, nextStream);
      }
    }
  };

  const setVideoOrientation = async (orientation: CaptureOrientation): Promise<MediaStream> => {
    if (stopped) {
      throw new Error('media_session_stopped');
    }
    videoOrientation = orientation;
    const nextPresentation = await createPresentationStream({
      rawStream,
      orientation,
    });
    if (!nextPresentation.transformed) {
      nextPresentation.cleanup();
      throw new Error('capture_orientation_transform_unavailable');
    }
    await replacePeerVideoTrack(nextPresentation.stream);
    presentation.cleanup();
    presentation = nextPresentation;
    stream = nextPresentation.stream;
    input.onLocalStream?.(stream);
    return stream;
  };

  const replaceVideoTrack = async (
    video: MediaTrackConstraints,
    options?: { orientation?: CaptureOrientation },
  ): Promise<MediaStream> => {
    if (stopped) {
      throw new Error('media_session_stopped');
    }
    const oldRawVideoTracks = getStreamVideoTracks(rawStream);
    let releasedOldCamera = false;
    let nextVideoStream: MediaStream | null = null;
    try {
      try {
        nextVideoStream = await navigator.mediaDevices.getUserMedia({
          video,
          audio: false,
        });
      } catch {
        for (const track of oldRawVideoTracks) {
          track.stop();
        }
        releasedOldCamera = true;
        nextVideoStream = await navigator.mediaDevices.getUserMedia({
          video,
          audio: false,
        });
      }

      const [nextVideoTrack] = nextVideoStream.getVideoTracks();
      if (!nextVideoTrack) {
        throw new Error('replacement_video_track_missing');
      }

      const audioTracks = getStreamAudioTracks(rawStream);
      const nextRawStream = new MediaStream([...audioTracks, nextVideoTrack]);
      videoOrientation = options?.orientation || videoOrientation;
      const nextPresentation = await createPresentationStream({
        rawStream: nextRawStream,
        orientation: videoOrientation,
      });
      if (videoOrientation && !nextPresentation.transformed) {
        nextPresentation.cleanup();
        throw new Error('capture_orientation_transform_unavailable');
      }
      await replacePeerVideoTrack(nextPresentation.stream);

      if (!releasedOldCamera) {
        for (const track of oldRawVideoTracks) {
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
      if (nextVideoStream) {
        for (const track of nextVideoStream.getTracks()) {
          track.stop();
        }
      }
      input.onError?.(error instanceof Error ? error : new Error('video_track_replace_failed'));
      throw error;
    }
  };

  signalSocket = openWebRTCSignalSocket({
    apiBase: input.apiBase,
    workspaceId: input.workspaceId,
    deviceSessionId: input.deviceSessionId,
    mediaSessionId: input.mediaSessionId,
    onOpen: () => {
      input.onState?.('signal_open');
      signalSocket.send({ type: 'source_join' });
    },
    onEvent: async (event) => {
      if (event.type === 'participant_joined' && event.sender === 'source') {
        joined = true;
        input.onState?.('signal_joined');
        await sendOffer();
        return;
      }
      if (event.type === 'participant_joined' && event.sender === 'workspace') {
        await resendOfferIfNeeded();
        return;
      }
      if (event.type === 'answer' && event.sdp) {
        const peer = ensurePeerConnection();
        await peer.setRemoteDescription({ type: 'answer', sdp: event.sdp });
        input.onState?.('answer_received');
        return;
      }
      if (event.type === 'ice_candidate' && event.candidate) {
        await ensurePeerConnection().addIceCandidate(event.candidate);
        return;
      }
      if (event.type === 'close' || event.type === 'session_error') {
        stop();
      }
    },
    onError: input.onError,
    onClose: () => input.onState?.('closed'),
  });

  return {
    stop,
    get peerConnection() {
      return peerConnection;
    },
    get localStream() {
      return stream;
    },
    replaceVideoTrack,
    setVideoOrientation,
  };
}

export async function startPhoneBrowserSourceSession(
  input: PhoneBrowserSourceSessionInput,
): Promise<WebRTCSessionHandle> {
  return startBrowserMediaSourceSession({
    ...input,
    sourceKind: 'phone_camera',
    video: buildPhoneVideoConstraints(input.facingMode),
    videoOrientation: input.videoOrientation === 'landscape' ? input.videoOrientation : undefined,
  });
}

export async function startDesktopBrowserSourceSession(
  input: DesktopBrowserSourceSessionInput,
): Promise<WebRTCSessionHandle> {
  return startBrowserMediaSourceSession({
    apiBase: input.apiBase,
    workspaceId: input.workspaceId,
    deviceSessionId: input.deviceSessionId,
    mediaSessionId: input.mediaSessionId,
    sourceKind: input.sourceKind,
    audio: false,
    video: {
      ...(input.deviceId ? { deviceId: { exact: input.deviceId } } : {}),
      width: { ideal: 1280 },
      height: { ideal: 720 },
      frameRate: { max: 30 },
    },
    onLocalStream: input.onLocalStream,
    onState: input.onState,
    onError: input.onError,
  });
}

export function startWorkspaceReceiverSession(
  input: WorkspaceReceiverSessionInput,
): WebRTCSessionHandle {
  let stopped = false;
  let peerConnection: RTCPeerConnection | null = null;
  let remoteDescriptionReady = false;
  const pendingCandidates: RTCIceCandidateInit[] = [];
  let signalSocket: WebRTCSignalSocket;

  const ensurePeerConnection = () => {
    if (peerConnection) {
      return peerConnection;
    }
    peerConnection = createLanPeerConnection({
      onIceCandidate: (candidate) => signalSocket.send({ type: 'ice_candidate', candidate }),
      onRemoteStream: input.onRemoteStream,
      onConnectionStateChange: (state) => {
        if (state === 'connected') {
          input.onState?.('connected');
        }
      },
    });
    return peerConnection;
  };

  const flushCandidates = async () => {
    const peer = ensurePeerConnection();
    while (pendingCandidates.length) {
      const candidate = pendingCandidates.shift();
      if (candidate) {
        await peer.addIceCandidate(candidate);
      }
    }
  };

  const stop = () => {
    if (stopped) {
      return;
    }
    stopped = true;
    try {
      signalSocket.send({ type: 'close', reason: 'workspace_stopped' });
    } catch {
      // Ignore shutdown races.
    }
    signalSocket.close();
    peerConnection?.close();
    input.onState?.('closed');
  };

  signalSocket = openWebRTCSignalSocket({
    apiBase: input.apiBase,
    workspaceId: input.workspaceId,
    deviceSessionId: input.deviceSessionId,
    mediaSessionId: input.mediaSessionId,
    onOpen: () => {
      input.onState?.('signal_open');
      signalSocket.send({ type: 'workspace_join' });
    },
    onEvent: async (event) => {
      if (event.type === 'participant_joined' && event.sender === 'workspace') {
        input.onState?.('signal_joined');
        return;
      }
      if (event.type === 'offer' && event.sdp) {
        const peer = ensurePeerConnection();
        await peer.setRemoteDescription({ type: 'offer', sdp: event.sdp });
        remoteDescriptionReady = true;
        await flushCandidates();
        const answer = await peer.createAnswer();
        await peer.setLocalDescription(answer);
        signalSocket.send({ type: 'answer', sdp: answer.sdp || '' });
        input.onState?.('answer_sent');
        return;
      }
      if (event.type === 'ice_candidate' && event.candidate) {
        if (!remoteDescriptionReady) {
          pendingCandidates.push(event.candidate);
          return;
        }
        await ensurePeerConnection().addIceCandidate(event.candidate);
        return;
      }
      if (event.type === 'close' || event.type === 'session_error') {
        stop();
      }
    },
    onError: input.onError,
    onClose: () => input.onState?.('closed'),
  });

  return {
    stop,
    get peerConnection() {
      return peerConnection;
    },
  };
}
