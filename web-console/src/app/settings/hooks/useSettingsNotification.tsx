'use client';

import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { InlineAlert } from '../components/InlineAlert';

interface Notification {
  id: string;
  type: 'success' | 'error';
  message: string;
  onDismiss: () => void;
}

let notifications: Notification[] = [];
let listeners: Set<() => void> = new Set();

function notifyListeners() {
  listeners.forEach(listener => listener());
}

export function showNotification(type: 'success' | 'error', message: string, onDismiss?: () => void) {
  const id = `notification-${Date.now()}-${Math.random()}`;
  const notification: Notification = {
    id,
    type,
    message,
    onDismiss: onDismiss || (() => {
      notifications = notifications.filter(n => n.id !== id);
      notifyListeners();
    }),
  };
  notifications.push(notification);
  notifyListeners();

  // Auto-dismiss after 5 seconds for success messages
  if (type === 'success') {
    setTimeout(() => {
      notifications = notifications.filter(n => n.id !== id);
      notifyListeners();
    }, 5000);
  }

  return notification.id;
}

export function dismissNotification(id: string) {
  notifications = notifications.filter(n => n.id !== id);
  notifyListeners();
}

export function useSettingsNotification() {
  const [notificationsState, setNotificationsState] = useState<Notification[]>([]);

  useEffect(() => {
    const update = () => {
      setNotificationsState([...notifications]);
    };
    listeners.add(update);
    update();
    return () => {
      listeners.delete(update);
    };
  }, []);

  return notificationsState;
}

export function SettingsNotificationContainer() {
  const notifications = useSettingsNotification();
  const container = typeof window !== 'undefined' ? document.getElementById('settings-notifications') : null;

  if (!container || notifications.length === 0) {
    return null;
  }

  // In header, only show the latest notification to avoid breaking layout
  const latestNotification = notifications[notifications.length - 1];

  return createPortal(
    <InlineAlert
      key={latestNotification.id}
      type={latestNotification.type}
      message={latestNotification.message}
      onDismiss={latestNotification.onDismiss}
      className="mb-0"
    />,
    container
  );
}

