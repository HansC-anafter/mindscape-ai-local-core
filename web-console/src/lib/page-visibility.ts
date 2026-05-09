export function isDocumentHidden(): boolean {
  return typeof document !== 'undefined' && document.visibilityState === 'hidden';
}

export function onDocumentVisible(callback: () => void): () => void {
  if (typeof document === 'undefined') {
    return () => {};
  }

  const handler = () => {
    if (document.visibilityState === 'visible') {
      callback();
    }
  };

  document.addEventListener('visibilitychange', handler);
  return () => document.removeEventListener('visibilitychange', handler);
}
