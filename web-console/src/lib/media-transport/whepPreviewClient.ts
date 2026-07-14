import {
  deleteHttpWebRtcResource,
  postHttpWebRtcOffer,
  waitForIceGatheringComplete,
} from './httpWebRtcNegotiation';
import type { WebRTCSessionState } from './webrtcSessionTypes';

export type WhepPreviewHandle = {
  peerConnection: RTCPeerConnection;
  stop: () => void;
};

export async function startWhepPreview({
  endpoint,
  token,
  receiveAudio = true,
  onRemoteStream,
  onState,
  onError,
}: {
  endpoint: string;
  token: string;
  receiveAudio?: boolean;
  onRemoteStream?: (stream: MediaStream) => void;
  onState?: (state: WebRTCSessionState) => void;
  onError?: (error: Error) => void;
}): Promise<WhepPreviewHandle> {
  const peerConnection = new RTCPeerConnection();
  const remoteStream = new MediaStream();
  let resourceUrl: string | null = null;
  let stopped = false;
  let streamDelivered = false;
  peerConnection.addTransceiver('video', { direction: 'recvonly' });
  if (receiveAudio) {
    peerConnection.addTransceiver('audio', { direction: 'recvonly' });
  }
  peerConnection.ontrack = (event) => {
    remoteStream.addTrack(event.track);
    if (!streamDelivered) {
      streamDelivered = true;
      onRemoteStream?.(remoteStream);
    }
  };
  peerConnection.onconnectionstatechange = () => {
    if (peerConnection.connectionState === 'connected') {
      onState?.('connected');
    }
    if (peerConnection.connectionState === 'failed') {
      onError?.(new Error('whep_connection_failed'));
    }
  };

  try {
    const offer = await peerConnection.createOffer();
    await peerConnection.setLocalDescription(offer);
    onState?.('offer_sent');
    await waitForIceGatheringComplete(peerConnection);
    const localSdp = peerConnection.localDescription?.sdp;
    if (!localSdp) {
      throw new Error('whep_local_description_missing');
    }
    const answer = await postHttpWebRtcOffer({ endpoint, token, sdp: localSdp });
    resourceUrl = answer.resourceUrl;
    await peerConnection.setRemoteDescription({ type: 'answer', sdp: answer.answerSdp });
    onState?.('answer_received');
  } catch (error) {
    peerConnection.close();
    const normalized = error instanceof Error ? error : new Error('whep_preview_failed');
    onError?.(normalized);
    throw normalized;
  }

  return {
    peerConnection,
    stop: () => {
      if (stopped) {
        return;
      }
      stopped = true;
      peerConnection.close();
      for (const track of remoteStream.getTracks()) {
        track.stop();
      }
      void deleteHttpWebRtcResource({ resourceUrl, token });
      onState?.('closed');
    },
  };
}
