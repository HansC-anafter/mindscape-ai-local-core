import {
  deleteHttpWebRtcResource,
  postHttpWebRtcOffer,
  waitForIceGatheringComplete,
} from './httpWebRtcNegotiation';
import type { WebRTCSessionState } from './webrtcSessionTypes';

export type WhipPublisherHandle = {
  peerConnection: RTCPeerConnection;
  stop: () => void;
};

export async function startWhipPublisher({
  endpoint,
  token,
  stream,
  onState,
  onError,
}: {
  endpoint: string;
  token: string;
  stream: MediaStream;
  onState?: (state: WebRTCSessionState) => void;
  onError?: (error: Error) => void;
}): Promise<WhipPublisherHandle> {
  const peerConnection = new RTCPeerConnection();
  let resourceUrl: string | null = null;
  let stopped = false;
  for (const track of stream.getTracks()) {
    peerConnection.addTrack(track, stream);
  }
  peerConnection.onconnectionstatechange = () => {
    if (peerConnection.connectionState === 'connected') {
      onState?.('connected');
    }
    if (peerConnection.connectionState === 'failed') {
      onError?.(new Error('whip_connection_failed'));
    }
  };

  try {
    const offer = await peerConnection.createOffer();
    await peerConnection.setLocalDescription(offer);
    onState?.('offer_sent');
    await waitForIceGatheringComplete(peerConnection);
    const localSdp = peerConnection.localDescription?.sdp;
    if (!localSdp) {
      throw new Error('whip_local_description_missing');
    }
    const answer = await postHttpWebRtcOffer({ endpoint, token, sdp: localSdp });
    resourceUrl = answer.resourceUrl;
    await peerConnection.setRemoteDescription({ type: 'answer', sdp: answer.answerSdp });
    onState?.('answer_received');
  } catch (error) {
    peerConnection.close();
    const normalized = error instanceof Error ? error : new Error('whip_publish_failed');
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
      void deleteHttpWebRtcResource({ resourceUrl, token });
      onState?.('closed');
    },
  };
}
