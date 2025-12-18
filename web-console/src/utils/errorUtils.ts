/**
 * Check if error is a network or timeout error.
 *
 * @param error - Error to check
 * @returns True if error is network/timeout related
 */
export function isNetworkError(error: any): boolean {
  if (!error) return false;

  if (error.name === 'AbortError') return true;

  if (error.name === 'TypeError' && error.message?.includes('Failed to fetch')) {
    return true;
  }

  if (error.message?.includes('Content-Length')) return true;

  if (error.message?.includes('ERR_CONTENT_LENGTH_MISMATCH')) return true;

  return false;
}

/**
 * Check if error is a Content-Length mismatch error.
 *
 * @param error - Error to check
 * @returns True if error is Content-Length mismatch
 */
export function isContentLengthError(error: any): boolean {
  if (!error) return false;

  if (error.message?.includes('Content-Length')) return true;

  if (error.message?.includes('ERR_CONTENT_LENGTH_MISMATCH')) return true;

  return false;
}

/**
 * Get user-friendly error message from error object.
 *
 * @param error - Error object
 * @param fallback - Fallback message
 * @returns User-friendly error message
 */
export function getErrorMessage(error: any, fallback: string = 'An error occurred'): string {
  if (!error) return fallback;

  if (typeof error === 'string') return error;

  if (error.user_message) return error.user_message;

  if (error.message) return error.message;

  return fallback;
}

/**
 * Check if error should be retried.
 *
 * @param error - Error to check
 * @returns True if error should be retried
 */
export function shouldRetryError(error: any): boolean {
  return isNetworkError(error) || isContentLengthError(error);
}

