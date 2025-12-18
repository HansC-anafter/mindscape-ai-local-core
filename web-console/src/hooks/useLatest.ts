import { useRef } from 'react';

/**
 * Hook to maintain a stable reference while always accessing the latest value.
 *
 * Returns a read-only ref object whose current property always points to the latest value.
 * Useful for useEffect/useCallback dependencies where you need the latest value without
 * triggering re-subscriptions when the value changes.
 *
 * @param value - The value to stabilize
 * @returns A read-only ref object with current property always pointing to the latest value
 *
 * @example
 * ```tsx
 * const latestValue = useLatest(value);
 *
 * useEffect(() => {
 *   const timer = setInterval(() => {
 *     console.log(latestValue.current);
 *   }, 1000);
 *   return () => clearInterval(timer);
 * }, [latestValue]);
 * ```
 */
export function useLatest<T>(value: T): { readonly current: T } {
  const ref = useRef(value);
  ref.current = value;
  return ref;
}

