import {
  LATENCY_BUCKETS,
} from './constants.mjs';
import {
  toFiniteNumber,
  toInteger,
} from './normalizers.mjs';

export function createLatencyBucketRows() {
  return LATENCY_BUCKETS.map((bucket) => ({
    label: bucket.label,
    upper_bound_ms: bucket.upper_bound_ms,
    count: 0,
  }));
}

export function addDurationToLatencyBuckets(latencyBuckets, durationMs) {
  const duration = toFiniteNumber(durationMs, 0);
  const bucket = latencyBuckets.find((candidate) =>
    candidate.upper_bound_ms === null || duration <= candidate.upper_bound_ms);
  if (bucket) {
    bucket.count += 1;
  }
}

export function computeAverage(values = []) {
  if (!values.length) {
    return null;
  }
  const total = values.reduce((sum, value) => sum + toFiniteNumber(value, 0), 0);
  return Math.round((total / values.length) * 100) / 100;
}

export function computePercentile(values = [], percentile = 0.95) {
  if (!values.length) {
    return null;
  }
  const sorted = values
    .map((value) => toFiniteNumber(value, 0))
    .sort((left, right) => left - right);
  const index = Math.max(0, Math.min(sorted.length - 1, Math.ceil(sorted.length * percentile) - 1));
  return Math.round(sorted[index] * 100) / 100;
}

export function mapToSortedRows(map, projector, limit = 5) {
  return Array.from(map.values())
    .sort((left, right) => {
      const requestDelta = toInteger(right.requests, 0) - toInteger(left.requests, 0);
      if (requestDelta !== 0) {
        return requestDelta;
      }
      return toInteger(right.response_bytes, 0) - toInteger(left.response_bytes, 0);
    })
    .slice(0, limit)
    .map(projector);
}

export function summarizeRouteClassRows(routeClassMap) {
  return Array.from(routeClassMap.values())
    .sort((left, right) => left.route_class.localeCompare(right.route_class))
    .map((row) => ({
      route_class: row.route_class,
      requests: row.requests,
      denied: row.denied,
      errors: row.errors,
      response_bytes: row.response_bytes,
      avg_duration_ms: computeAverage(row.duration_values),
    }));
}
