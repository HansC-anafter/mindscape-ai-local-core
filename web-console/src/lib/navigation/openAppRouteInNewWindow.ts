'use client';

export function openAppRouteInNewWindow(href: string): void {
  if (typeof window === 'undefined') {
    return;
  }

  const openedWindow = window.open(href, '_blank', 'noopener,noreferrer');
  if (openedWindow) {
    openedWindow.opener = null;
  }
}
