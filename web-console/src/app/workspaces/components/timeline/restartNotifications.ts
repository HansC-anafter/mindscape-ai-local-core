interface RestartedNotificationPayload {
  executionId: string;
  workspaceId: string;
  playbookCode?: string;
}

function appendNotification(html: string): void {
  const notification = document.createElement('div');
  notification.innerHTML = html;
  const element = notification.firstElementChild;
  if (!element) {
    return;
  }

  document.body.appendChild(element);
  window.setTimeout(() => {
    if (element.parentElement) {
      element.remove();
    }
  }, 5000);
}

export function showExecutionRestartedNotification({
  executionId,
  workspaceId,
  playbookCode,
}: RestartedNotificationPayload): void {
  appendNotification(`
    <div class="fixed top-4 right-4 z-50 flex items-center gap-3 rounded-lg bg-green-500 px-4 py-3 text-white shadow-lg">
      <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
      </svg>
      <div>
        <p class="font-medium">Execution restarted</p>
        <p class="text-sm opacity-90">${playbookCode || 'Playbook Execution'}</p>
      </div>
      <button
        onclick="window.location.href='/workspaces/${workspaceId}/executions/${executionId}'"
        class="ml-2 rounded bg-white/20 px-2 py-1 text-xs transition-colors hover:bg-white/30"
      >
        View
      </button>
      <button
        onclick="this.parentElement.remove()"
        class="ml-2 text-white/80 transition-colors hover:text-white"
      >
        ×
      </button>
    </div>
  `);
}

export function showExecutionRestartErrorNotification(message: string): void {
  appendNotification(`
    <div class="fixed top-4 right-4 z-50 flex items-center gap-3 rounded-lg bg-red-500 px-4 py-3 text-white shadow-lg">
      <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
      </svg>
      <div>
        <p class="font-medium">Restart failed</p>
        <p class="text-sm opacity-90">${message}</p>
      </div>
      <button
        onclick="this.parentElement.remove()"
        class="ml-2 text-white/80 transition-colors hover:text-white"
      >
        ×
      </button>
    </div>
  `);
}
