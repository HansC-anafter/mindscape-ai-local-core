import React from 'react';

type ExcalidrawProps = {
  initialData?: { elements?: unknown[] };
  onChange?: (elements: unknown[], appState: Record<string, unknown>) => void;
};

export function Excalidraw({ initialData, onChange }: ExcalidrawProps) {
  React.useEffect(() => {
    onChange?.(
      initialData?.elements || [],
      {
        viewBackgroundColor: '#f8fafc',
        scrollX: 0,
        scrollY: 0,
        zoom: { value: 1 },
        theme: 'light',
      },
    );
  }, [initialData?.elements, onChange]);

  return <div data-testid="excalidraw-package-mock" />;
}

export default Excalidraw;
