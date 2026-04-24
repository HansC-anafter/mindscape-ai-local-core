import React from 'react';

type DepartmentWorkspaceExcalidrawClientProps = {
  onChange?: (elements: unknown[], appState: Record<string, unknown>) => void;
};

export function DepartmentWorkspaceExcalidrawClient({
  onChange,
}: DepartmentWorkspaceExcalidrawClientProps) {
  React.useEffect(() => {
    onChange?.([], {
      viewBackgroundColor: '#f5f5f4',
      scrollX: 0,
      scrollY: 0,
      zoom: { value: 1 },
      theme: 'light',
    });
  }, [onChange]);

  return <div data-testid="mock-excalidraw-client">Mock Excalidraw</div>;
}
