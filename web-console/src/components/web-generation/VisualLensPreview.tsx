"use client";

import React, { useState, useEffect } from "react";
import VisualLensPreviewCard from "@/components/visual-lens/VisualLensPreviewCard";

interface VisualLens {
  id: string;
  lens_id: string;
  name: string;
  description?: string;
  source_photographer?: string;
  source_image_references?: any[];
  schema_data?: any;
  summary?: string;
}

interface VisualLensPreviewProps {
  workspaceId: string;
  projectId?: string;
  lensId?: string;
  onLensChange?: (lensId: string | null) => void;
}

export default function VisualLensPreview({
  workspaceId,
  projectId,
  lensId,
  onLensChange,
}: VisualLensPreviewProps) {
  const [lens, setLens] = useState<VisualLens | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (lensId) {
      loadLens(lensId);
    } else {
      loadProjectLens();
    }
  }, [workspaceId, projectId, lensId]);

  const loadLens = async (id: string) => {
    try {
      setLoading(true);
      setError(null);

      const response = await fetch(
        `/api/v1/workspaces/${workspaceId}/web-generation/visual-lens/${id}`
      );

      if (!response.ok) {
        if (response.status === 404) {
          setLens(null);
          return;
        }
        throw new Error(`Failed to load Visual Lens: ${response.statusText}`);
      }

      const data = await response.json();
      setLens(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Visual Lens");
      setLens(null);
    } finally {
      setLoading(false);
    }
  };

  const loadProjectLens = async () => {
    if (!projectId) {
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const params = new URLSearchParams();
      params.append("project_id", projectId);
      params.append("limit", "1");

      const response = await fetch(
        `/api/v1/workspaces/${workspaceId}/web-generation/visual-lens?${params.toString()}`
      );

      if (!response.ok) {
        throw new Error(`Failed to load Visual Lens: ${response.statusText}`);
      }

      const data = await response.json();
      if (data.items && data.items.length > 0) {
        setLens(data.items[0]);
        if (onLensChange) {
          onLensChange(data.items[0].lens_id);
        }
      } else {
        setLens(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Visual Lens");
      setLens(null);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="p-4 text-center text-gray-500">
        <div>載入 Visual Lens...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
        <strong>錯誤：</strong> {error}
      </div>
    );
  }

  if (!lens) {
    return (
      <div className="p-4 bg-gray-50 border border-gray-200 rounded text-gray-600 text-sm">
        <p className="mb-2">尚未應用 Visual Lens</p>
        <p className="text-xs text-gray-500">
          執行 <code>unsplash_visual_lens_extraction</code> playbook 來創建 Visual Lens
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900">應用的 Visual Lens</h3>
        {onLensChange && (
          <button
            onClick={() => {
              setLens(null);
              onLensChange(null);
            }}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            清除
          </button>
        )}
      </div>
      <VisualLensPreviewCard lens={lens} />
    </div>
  );
}


