const DEFAULT_ICE_GATHER_TIMEOUT_MS = 5000;

export async function waitForIceGatheringComplete(
  peerConnection: RTCPeerConnection,
  timeoutMs = DEFAULT_ICE_GATHER_TIMEOUT_MS,
): Promise<void> {
  if (peerConnection.iceGatheringState === 'complete') {
    return;
  }
  await new Promise<void>((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      cleanup();
      reject(new Error('webrtc_ice_gather_timeout'));
    }, timeoutMs);
    const onStateChange = () => {
      if (peerConnection.iceGatheringState === 'complete') {
        cleanup();
        resolve();
      }
    };
    const cleanup = () => {
      window.clearTimeout(timeout);
      peerConnection.removeEventListener('icegatheringstatechange', onStateChange);
    };
    peerConnection.addEventListener('icegatheringstatechange', onStateChange);
    onStateChange();
  });
}

export async function postHttpWebRtcOffer({
  endpoint,
  token,
  sdp,
}: {
  endpoint: string;
  token: string;
  sdp: string;
}): Promise<{ answerSdp: string; resourceUrl: string | null }> {
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      accept: 'application/sdp',
      authorization: `Bearer ${token}`,
      'content-type': 'application/sdp',
    },
    body: sdp,
  });
  if (!response.ok) {
    throw new Error(`http_webrtc_offer_failed_${response.status}`);
  }
  const answerSdp = await response.text();
  if (!answerSdp.trim()) {
    throw new Error('http_webrtc_answer_missing');
  }
  const location = response.headers.get('location');
  return {
    answerSdp,
    resourceUrl: location ? new URL(location, endpoint).toString() : null,
  };
}

export async function deleteHttpWebRtcResource({
  resourceUrl,
  token,
}: {
  resourceUrl: string | null;
  token: string;
}): Promise<void> {
  if (!resourceUrl) {
    return;
  }
  try {
    await fetch(resourceUrl, {
      method: 'DELETE',
      headers: { authorization: `Bearer ${token}` },
      keepalive: true,
    });
  } catch {
    // The server also closes the resource when the peer connection disappears.
  }
}
