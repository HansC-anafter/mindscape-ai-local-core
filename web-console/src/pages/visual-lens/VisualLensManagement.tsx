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

interface VisualLensManagementProps {
  workspaceId: string;
  projectId?: string;
}

export default function VisualLensManagement({
  workspaceId,
  projectId,
}: VisualLensManagementProps) {
  const [lenses, setLenses] = useState<VisualLens[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedLensId, setSelectedLensId] = useState<string | null>(null);

  useEffect(() => {
    loadLenses();
  }, [workspaceId, projectId]);

  const loadLenses = async () => {
    try {
      setLoading(true);
      setError(null);

      const params = new URLSearchParams();
      if (projectId) {
        params.append("project_id", projectId);
      }
      params.append("limit", "50");
      params.append("offset", "0");

      const response = await fetch(
        `/api/v1/workspaces/${workspaceId}/web-generation/visual-lens?${params.toString()}`
      );

      if (!response.ok) {
        throw new Error(`Failed to load Visual Lenses: ${response.statusText}`);
      }

      const data = await response.json();
      setLenses(data.items || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Visual Lenses");
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = (lensId: string) => {
    setSelectedLensId(lensId);
    // TODO: Apply lens to project or show selection confirmation
  };

  const handleEdit = (lensId: string) => {
    // TODO: Navigate to edit page or open edit modal
    console.log("Edit lens:", lensId);
  };

  const handleDelete = async (lensId: string) => {
    if (!confirm(`確定要刪除 Visual Lens "${lensId}" 嗎？`)) {
      return;
    }

    try {
      const response = await fetch(
        `/api/v1/workspaces/${workspaceId}/web-generation/visual-lens/${lensId}`,
        {
          method: "DELETE",
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to delete Visual Lens: ${response.statusText}`);
      }

      await loadLenses();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete Visual Lens");
    }
  };

  if (loading) {
    return (
      <div className="p-8 text-center">
        <div className="text-gray-500">載入中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="bg-red-50 border border-red-200 rounded p-4 text-red-700">
          <strong>錯誤：</strong> {error}
        </div>
        <button
          onClick={loadLenses}
          className="mt-4 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          重試
        </button>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Visual Lens 管理</h1>
        <p className="text-gray-600">
          管理視覺風格規範，從 Unsplash 攝影師作品抽取的視覺風格
        </p>
      </div>

      {selectedLensId && (
        <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded">
          已選用：<strong>{selectedLensId}</strong>
        </div>
      )}

      {lenses.length === 0 ? (
        <div className="text-center py-12 bg-gray-50 rounded">
          <p className="text-gray-500 mb-4">尚未創建任何 Visual Lens</p>
          <p className="text-sm text-gray-400">
            執行 <code>unsplash_visual_lens_extraction</code> playbook 來創建第一個 Visual Lens
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {lenses.map((lens) => (
            <VisualLensPreviewCard
              key={lens.id}
              lens={lens}
              onSelect={handleSelect}
              onEdit={handleEdit}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}


