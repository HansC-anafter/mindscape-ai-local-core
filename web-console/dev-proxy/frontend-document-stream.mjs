import http from 'node:http';
import {
  DEFAULT_FRONTEND_DOCUMENT_SINGLEFLIGHT_MAX_BODY_BYTES,
  isFrontendDocumentRequest,
  normalizeFrontendDocumentSingleflightKey,
} from './document-singleflight.mjs';
import {
  copyProxyRequestHeaders,
  copyProxyResponseHeaders,
} from './proxy-headers.mjs';

const FRONTEND_DOCUMENT_SINGLEFLIGHT_MAX_BODY_BYTES = Number.parseInt(
  process.env.FRONTEND_DOCUMENT_SINGLEFLIGHT_MAX_BODY_BYTES
    || String(DEFAULT_FRONTEND_DOCUMENT_SINGLEFLIGHT_MAX_BODY_BYTES),
  10,
);
const frontendDocumentStreamInflight = new Map();

export function clearFrontendDocumentSingleflightForTests() {
  frontendDocumentStreamInflight.clear();
}

function writeFrontendDocumentSubscriberError(subscriber, errorCode) {
  if (typeof subscriber.markTerminalError === 'function') {
    subscriber.markTerminalError(errorCode);
  }
  if (!subscriber.res.headersSent) {
    subscriber.res.writeHead(502, { 'content-type': 'application/json', 'cache-control': 'no-store' });
  }
  if (!subscriber.res.destroyed && !subscriber.res.writableEnded) {
    subscriber.res.end(JSON.stringify({ error: 'next_dev_proxy_unavailable' }));
  }
}

function writeFrontendDocumentSubscriberHeaders(flight, subscriber) {
  if (!flight.headers || subscriber.res.headersSent || subscriber.res.destroyed || subscriber.res.writableEnded) {
    return;
  }
  subscriber.res.writeHead(
    flight.statusCode || 502,
    copyProxyResponseHeaders(flight.headers, subscriber.req.url, subscriber.req.method, flight.statusCode || 502),
  );
}

function writeFrontendDocumentSubscriberChunk(subscriber, chunk) {
  if (subscriber.res.destroyed || subscriber.res.writableEnded) {
    return;
  }
  try {
    subscriber.res.write(chunk);
  } catch (error) {
    if (error?.code !== 'EPIPE' && error?.code !== 'ECONNRESET') {
      throw error;
    }
  }
}

function endFrontendDocumentSubscriber(subscriber) {
  if (subscriber.res.destroyed || subscriber.res.writableEnded) {
    return;
  }
  try {
    subscriber.res.end();
    subscriber.logCompletion('finish', {
      document_singleflight: subscriber.shared ? 'shared' : 'origin',
    });
  } catch (error) {
    if (error?.code !== 'EPIPE' && error?.code !== 'ECONNRESET') {
      throw error;
    }
  }
}

function detachFrontendDocumentSubscriber(flight, key, subscriber) {
  flight.subscribers.delete(subscriber);
  if (
    flight.subscribers.size === 0
    && !flight.ended
    && !flight.errorCode
  ) {
    frontendDocumentStreamInflight.delete(key);
    if (flight.upstream && !flight.upstream.destroyed) {
      flight.upstream.destroy(new Error('frontend_document_subscribers_closed'));
    }
  }
}

function attachFrontendDocumentSubscriber(flight, key, subscriber) {
  flight.subscribers.add(subscriber);
  const detach = () => {
    detachFrontendDocumentSubscriber(flight, key, subscriber);
  };
  subscriber.res.on('close', detach);

  if (flight.errorCode) {
    writeFrontendDocumentSubscriberError(subscriber, flight.errorCode);
    return;
  }

  if (flight.headers) {
    writeFrontendDocumentSubscriberHeaders(flight, subscriber);
    if (flight.replayable) {
      for (const chunk of flight.chunks) {
        writeFrontendDocumentSubscriberChunk(subscriber, chunk);
      }
    } else if (subscriber.shared) {
      writeFrontendDocumentSubscriberError(subscriber, 'frontend_document_singleflight_replay_unavailable');
      return;
    }
  }

  if (flight.ended) {
    endFrontendDocumentSubscriber(subscriber);
  }
}

function failFrontendDocumentFlight(flight, key, errorCode) {
  flight.errorCode = errorCode;
  frontendDocumentStreamInflight.delete(key);
  for (const subscriber of Array.from(flight.subscribers)) {
    writeFrontendDocumentSubscriberError(subscriber, errorCode);
  }
  flight.subscribers.clear();
}

function startFrontendDocumentFlight(req, target, key) {
  const flight = {
    chunks: [],
    ended: false,
    errorCode: null,
    headers: null,
    replayable: true,
    statusCode: null,
    subscribers: new Set(),
    totalBytes: 0,
    upstream: null,
  };
  frontendDocumentStreamInflight.set(key, flight);

  const upstream = http.request(
    {
      hostname: target.hostname,
      port: target.port,
      method: 'GET',
      path: target.path,
      headers: copyProxyRequestHeaders(req.headers, target),
    },
    (upstreamRes) => {
      flight.statusCode = upstreamRes.statusCode || 502;
      flight.headers = upstreamRes.headers;
      for (const subscriber of Array.from(flight.subscribers)) {
        writeFrontendDocumentSubscriberHeaders(flight, subscriber);
      }
      upstreamRes.on('data', (chunk) => {
        flight.totalBytes += chunk.length;
        if (flight.totalBytes <= FRONTEND_DOCUMENT_SINGLEFLIGHT_MAX_BODY_BYTES && flight.replayable) {
          flight.chunks.push(Buffer.from(chunk));
        } else {
          flight.replayable = false;
          flight.chunks.length = 0;
        }
        for (const subscriber of Array.from(flight.subscribers)) {
          writeFrontendDocumentSubscriberChunk(subscriber, chunk);
        }
      });
      upstreamRes.on('end', () => {
        flight.ended = true;
        frontendDocumentStreamInflight.delete(key);
        for (const subscriber of Array.from(flight.subscribers)) {
          endFrontendDocumentSubscriber(subscriber);
        }
        flight.subscribers.clear();
      });
      upstreamRes.on('error', (error) => {
        failFrontendDocumentFlight(
          flight,
          key,
          error?.code || error?.message || 'upstream_response_error',
        );
      });
    },
  );
  flight.upstream = upstream;

  upstream.on('error', (error) => {
    failFrontendDocumentFlight(flight, key, error?.code || error?.message || 'unknown');
  });
  upstream.end();
  return flight;
}

export function tryProxySingleflightNextDocument(req, res, target, logCompletion, markTerminalError = null) {
  const key = normalizeFrontendDocumentSingleflightKey(req.method, req.url);
  if (!key || !isFrontendDocumentRequest(req.method, req.url)) {
    return false;
  }

  let flight = frontendDocumentStreamInflight.get(key);
  const shared = Boolean(flight);
  if (!flight) {
    flight = startFrontendDocumentFlight(req, target, key);
  }
  attachFrontendDocumentSubscriber(flight, key, {
    logCompletion,
    markTerminalError,
    req,
    res,
    shared,
  });
  return true;
}
